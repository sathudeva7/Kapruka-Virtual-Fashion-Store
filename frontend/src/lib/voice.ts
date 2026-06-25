// The voice/data client: owns the mic, the /live WebSocket (English/Tamil) and
// the turn-based Sinhala upload, and dispatches every backend frame into the
// zustand store. Ported from static/index.html, refactored from DOM mutation to
// state so the 3D scene and HUD can subscribe.
import { wsUrl, voiceSinhala } from "./api";
import { downsampleToPCM16, pcm16ToWav, TARGET_RATE } from "./audio";
import { getSessionId } from "./session";
import { useStore, type Lang, type ProductItem, type OrderItem, type TryonItem, type TrackingItem } from "./store";

type Mode = "live" | "sinhala_live" | "sinhala" | null;

// Sinhala uses Azure (Gemini Live can't speak it). Default to the hands-free
// continuous path (/live_sinhala); flip to false to fall back to the original
// push-to-talk upload (/voice_sinhala) if Azure continuous misbehaves.
const SINHALA_CONTINUOUS = true;

interface MicHandle {
  ctx: AudioContext;
  stream: MediaStream;
  node: ScriptProcessorNode;
}

export class VoiceClient {
  private mode: Mode = null;
  private ws: WebSocket | null = null;
  private mic: MicHandle | null = null;
  private chunks: Float32Array[] = [];

  // 24 kHz assistant-audio playback scheduler
  private outCtx: AudioContext | null = null;
  private nextStart = 0;
  private sources: AudioBufferSourceNode[] = [];

  get active(): boolean {
    return this.mode !== null;
  }

  // --- mic ---------------------------------------------------------------
  private async openMic(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    const src = ctx.createMediaStreamSource(stream);
    const node = ctx.createScriptProcessor(4096, 1, 1);
    src.connect(node);
    node.connect(ctx.destination);
    this.mic = { ctx, stream, node };
  }

  private closeMic(): void {
    try {
      this.mic?.node.disconnect();
    } catch {}
    try {
      this.mic?.ctx.close();
    } catch {}
    try {
      this.mic?.stream.getTracks().forEach((t) => t.stop());
    } catch {}
    this.mic = null;
  }

  // --- assistant audio playback -----------------------------------------
  private playPCM24(int16: Int16Array): void {
    if (!this.outCtx) {
      this.outCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    }
    const f32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 0x8000;
    const buf = this.outCtx.createBuffer(1, f32.length, 24000);
    buf.getChannelData(0).set(f32);
    const node = this.outCtx.createBufferSource();
    node.buffer = buf;
    node.connect(this.outCtx.destination);
    const now = this.outCtx.currentTime;
    if (this.nextStart < now) this.nextStart = now;
    node.start(this.nextStart);
    this.nextStart += buf.duration;
    this.sources.push(node);
    node.onended = () => {
      this.sources = this.sources.filter((s) => s !== node);
    };
  }

  private stopPlayback(): void {
    // barge-in: drop queued assistant audio
    this.sources.forEach((s) => {
      try {
        s.stop();
      } catch {}
    });
    this.sources = [];
    this.nextStart = 0;
  }

  // --- realtime path (English / Tamil) via /live ------------------------
  private async startLive(lang: Lang): Promise<void> {
    const store = useStore.getState();
    store.setConnection("connecting");
    const ws = new WebSocket(
      wsUrl("/live", { session_id: getSessionId(), lang })
    );
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    this.mode = "live";

    ws.onmessage = (ev) => this.onLiveFrame(ev, lang);
    ws.onclose = () => {
      if (this.mode === "live") this.teardownLive();
    };

    await new Promise<void>((res, rej) => {
      ws.onopen = () => res();
      ws.onerror = () => rej(new Error("Could not connect to the voice service."));
    });

    await this.openMic();
    this.mic!.node.onaudioprocess = (e) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      const pcm = downsampleToPCM16(e.inputBuffer.getChannelData(0), this.mic!.ctx.sampleRate);
      this.ws.send(pcm.buffer);
    };
    useStore.getState().setConnection("live");
  }

  private onLiveFrame(ev: MessageEvent, lang: Lang): void {
    const store = useStore.getState();
    if (typeof ev.data !== "string") {
      this.playPCM24(new Int16Array(ev.data as ArrayBuffer));
      return;
    }
    let evt: Record<string, unknown>;
    try {
      evt = JSON.parse(ev.data);
    } catch {
      return;
    }
    switch (evt.type) {
      case "product":
        store.addProduct(evt.item as ProductItem);
        break;
      case "tryon_image":
        store.addTryon(evt as unknown as TryonItem);
        break;
      case "order":
        store.addOrder(evt as unknown as OrderItem);
        break;
      case "tracking":
        store.addTracking(evt as unknown as TrackingItem);
        break;
      case "tool":
        store.setToolStatus(
          evt.name === "fitting_room_agent" ? "Creating your try-on look…" : `Searching the store…`
        );
        break;
      case "user_text":
        store.setUserCaption(String(evt.content || ""));
        store.newBotTurn();
        store.beginBatch(); // a new utterance => the next results replace the wall
        break;
      case "text":
        store.appendBotCaption(String(evt.content || ""));
        break;
      case "no_results":
        // A search ran but found nothing: clear the pending fresh-batch flag so
        // the wall isn't wiped/replaced — the assistant says so in its reply.
        store.endBatch();
        break;
      case "turn_complete":
        store.setToolStatus(null);
        store.endBatch(); // safety net: a turn that emitted no product clears the flag
        break;
      case "interrupted":
        this.stopPlayback();
        break;
      case "go_away":
        this.restartLive(lang);
        break;
      case "error":
        store.setError(String(evt.content || "Voice error."));
        break;
    }
  }

  private teardownLive(): void {
    try {
      this.ws?.close();
    } catch {}
    this.ws = null;
    this.closeMic();
    this.stopPlayback();
    this.mode = null;
    useStore.getState().setConnection("idle");
  }

  // --- realtime Sinhala (hands-free) via /live_sinhala ------------------
  // Same streaming shape as startLive, but Azure does STT+TTS server-side, so
  // there's no lang param and no go_away/time-cap reconnect. Assistant audio
  // arrives as 24 kHz PCM binary frames and plays through the same scheduler.
  private async startSinhalaLive(): Promise<void> {
    const store = useStore.getState();
    store.setConnection("connecting");
    const ws = new WebSocket(wsUrl("/live_sinhala", { session_id: getSessionId() }));
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    this.mode = "sinhala_live";

    ws.onmessage = (ev) => this.onLiveFrame(ev, "si");
    ws.onclose = () => {
      if (this.mode === "sinhala_live") this.teardownLive();
    };

    await new Promise<void>((res, rej) => {
      ws.onopen = () => res();
      ws.onerror = () => rej(new Error("Could not connect to the Sinhala voice service."));
    });

    await this.openMic();
    this.mic!.node.onaudioprocess = (e) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      const pcm = downsampleToPCM16(e.inputBuffer.getChannelData(0), this.mic!.ctx.sampleRate);
      this.ws.send(pcm.buffer);
    };
    useStore.getState().setConnection("live");
  }

  private async restartLive(lang: Lang): Promise<void> {
    // reconnect on the Live session time-cap (go_away) without dropping the mic UX
    try {
      this.ws?.close();
    } catch {}
    this.ws = null;
    await this.startLive(lang);
  }

  // --- Sinhala push-to-talk -> /voice_sinhala ---------------------------
  private async startSinhalaRecording(): Promise<void> {
    this.mode = "sinhala";
    this.chunks = [];
    await this.openMic();
    this.mic!.node.onaudioprocess = (e) => {
      this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    useStore.getState().setConnection("recording");
  }

  private async stopSinhalaRecording(): Promise<void> {
    const store = useStore.getState();
    const rate = this.mic ? this.mic.ctx.sampleRate : 48000;
    this.closeMic();
    this.mode = null;
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const merged = new Float32Array(total);
    let o = 0;
    for (const c of this.chunks) {
      merged.set(c, o);
      o += c.length;
    }
    this.chunks = [];
    if (total === 0) {
      store.setConnection("idle");
      return;
    }
    store.setConnection("thinking");
    const wav = pcm16ToWav(downsampleToPCM16(merged, rate), TARGET_RATE);
    try {
      const out = await voiceSinhala(getSessionId(), wav);
      if (out.status === "no_speech") {
        store.setToolStatus(out.message || "Didn't catch that — please try again.");
      } else if (out.status !== "ok") {
        throw new Error(out.message || "Sinhala voice failed.");
      } else {
        if (out.transcript) store.setUserCaption(out.transcript);
        store.newBotTurn();
        store.beginBatch(); // fresh search => replace the wall
        const products = out.products || [];
        products.forEach((p) => store.addProduct(p as ProductItem));
        if (products.length === 0) store.endBatch(); // nothing found => keep the wall
        (out.tryon_images || []).forEach((t) => store.addTryon(t as TryonItem));
        (out.orders || []).forEach((ord) => store.addOrder(ord as OrderItem));
        (out.tracking || []).forEach((trk) => store.addTracking(trk as TrackingItem));
        if (out.reply_text) store.appendBotCaption(out.reply_text);
        if (out.audio_mp3_base64) {
          new Audio("data:audio/mp3;base64," + out.audio_mp3_base64).play().catch(() => {});
        }
      }
    } catch (err) {
      store.setError("Sinhala voice failed: " + (err as Error).message);
    } finally {
      store.setConnection("idle");
    }
  }

  // --- public toggle -----------------------------------------------------
  async start(lang: Lang): Promise<void> {
    if (lang === "si") {
      if (SINHALA_CONTINUOUS) await this.startSinhalaLive();
      else await this.startSinhalaRecording();
    } else await this.startLive(lang);
  }

  async stop(): Promise<void> {
    if (this.mode === "sinhala") await this.stopSinhalaRecording();
    else this.teardownLive(); // "live" and "sinhala_live" both tear down here
  }
}

// One client for the page.
let _client: VoiceClient | null = null;
export function getVoiceClient(): VoiceClient {
  if (!_client) _client = new VoiceClient();
  return _client;
}
