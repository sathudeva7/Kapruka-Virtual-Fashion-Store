// Audio helpers ported verbatim (behaviour) from the legacy static/index.html.
// The mic gives us Float32 at the device rate (often 48 kHz); the backend / Live
// API / Azure all want 16 kHz PCM16.

export const TARGET_RATE = 16000;

// Float32 (any rate) -> Int16 PCM at TARGET_RATE. Averages each output sample
// over its source window (a simple anti-aliasing low-pass) — naive nearest-
// sample decimation aliases and garbles speech enough that VAD/ASR fails.
export function downsampleToPCM16(float32: Float32Array, inRate: number): Int16Array {
  const ratio = inRate / TARGET_RATE;
  const outLen = Math.floor(float32.length / ratio);
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(float32.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    let n = 0;
    for (let j = start; j < end; j++) {
      sum += float32[j];
      n++;
    }
    let s = n ? sum / n : float32[start] || 0;
    s = Math.max(-1, Math.min(1, s));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

// Wrap Int16 PCM in a minimal WAV container (for the Sinhala upload).
export function pcm16ToWav(int16: Int16Array, rate: number): Blob {
  const buf = new ArrayBuffer(44 + int16.length * 2);
  const dv = new DataView(buf);
  const ws = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) dv.setUint8(off + i, s.charCodeAt(i));
  };
  ws(0, "RIFF");
  dv.setUint32(4, 36 + int16.length * 2, true);
  ws(8, "WAVE");
  ws(12, "fmt ");
  dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true);
  dv.setUint16(22, 1, true);
  dv.setUint32(24, rate, true);
  dv.setUint32(28, rate * 2, true);
  dv.setUint16(32, 2, true);
  dv.setUint16(34, 16, true);
  ws(36, "data");
  dv.setUint32(40, int16.length * 2, true);
  for (let i = 0; i < int16.length; i++) dv.setInt16(44 + i * 2, int16[i], true);
  return new Blob([buf], { type: "audio/wav" });
}
