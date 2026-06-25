"""Azure Speech wrappers for the Sinhala voice path.

Gemini Live cannot do Sinhala, and Google Cloud TTS has no Sinhala voice
(verified June 2026). Azure Speech is the one vendor that does BOTH sides of
Sinhala: STT `si-LK` and neural TTS `si-LK-ThiliniNeural` (F) / `si-LK-SameeraNeural`
(M). So the Sinhala turn is: browser audio -> transcribe() -> existing agent
graph (run_async) -> synthesize() -> audio back.

The `azure-cognitiveservices-speech` SDK is imported lazily so main.py stays
importable (and the English/Tamil Live path keeps working) even if the package
or the Azure keys are absent. Requires AZURE_SPEECH_KEY + AZURE_SPEECH_REGION.
"""

import os
import tempfile

# Defaults are overridable via .env. Thilini = female Sinhala neural voice.
SINHALA_STT_LANG = os.getenv("AZURE_STT_LANG", "si-LK")
SINHALA_TTS_VOICE = os.getenv("AZURE_TTS_VOICE", "si-LK-ThiliniNeural")


class AzureSpeechError(RuntimeError):
    """Raised when Azure speech is misconfigured or a call fails."""


def is_configured() -> bool:
    """True if both the SDK is importable and the Azure keys are present."""
    if not (os.getenv("AZURE_SPEECH_KEY") and os.getenv("AZURE_SPEECH_REGION")):
        return False
    try:
        import azure.cognitiveservices.speech  # noqa: F401
    except Exception:
        return False
    return True


def _speech_config():
    """Build a SpeechConfig from env, or raise a clear error."""
    key = os.getenv("AZURE_SPEECH_KEY")
    region = os.getenv("AZURE_SPEECH_REGION")
    if not key or not region:
        raise AzureSpeechError(
            "Sinhala voice needs AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in .env."
        )
    try:
        import azure.cognitiveservices.speech as speechsdk
    except Exception as exc:  # pragma: no cover - install-time issue
        raise AzureSpeechError(
            "azure-cognitiveservices-speech is not installed in .venv."
        ) from exc
    return speechsdk, speechsdk.SpeechConfig(subscription=key, region=region)


def transcribe(audio_wav: bytes, language: str = SINHALA_STT_LANG) -> str:
    """Recognise one utterance of Sinhala (default) from a WAV byte blob.

    Expects a complete WAV container (PCM 16-bit mono, 16 kHz recommended) — the
    frontend wraps captured PCM in a WAV header before upload. Returns the
    transcript text (empty string if nothing was recognised).
    """
    speechsdk, config = _speech_config()
    config.speech_recognition_language = language

    # AudioConfig(filename=...) lets Azure parse the WAV header itself, which is
    # more robust than pushing raw PCM with a hand-built format.
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(audio_wav)
        tmp.flush()
        audio_config = speechsdk.audio.AudioConfig(filename=tmp.name)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=config, audio_config=audio_config
        )
        result = recognizer.recognize_once()

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text or ""
    if result.reason == speechsdk.ResultReason.NoMatch:
        return ""
    # Canceled / error
    detail = getattr(result, "cancellation_details", None)
    raise AzureSpeechError(f"Sinhala STT failed: {getattr(detail, 'reason', result.reason)}")


def synthesize(text: str, voice: str = SINHALA_TTS_VOICE) -> bytes:
    """Synthesise `text` to spoken audio (MP3 bytes) with a Sinhala neural voice."""
    speechsdk, config = _speech_config()
    config.speech_synthesis_voice_name = voice
    config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
    )
    # audio_config=None → keep the bytes in-memory instead of playing on a device.
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return bytes(result.audio_data)
    detail = getattr(result, "cancellation_details", None)
    raise AzureSpeechError(f"Sinhala TTS failed: {getattr(detail, 'reason', result.reason)}")


def synthesize_pcm(text: str, voice: str = SINHALA_TTS_VOICE) -> bytes:
    """Synthesise `text` to RAW PCM (24 kHz, 16-bit, mono) bytes.

    Same as `synthesize()` but un-containered PCM instead of MP3 — for the live
    Sinhala WebSocket, which streams assistant audio as binary frames the browser
    plays through the same 24 kHz scheduler as the Gemini Live path (no MP3
    decode, no per-utterance <audio> element)."""
    speechsdk, config = _speech_config()
    config.speech_synthesis_voice_name = voice
    config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm
    )
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return bytes(result.audio_data)
    detail = getattr(result, "cancellation_details", None)
    raise AzureSpeechError(f"Sinhala TTS failed: {getattr(detail, 'reason', result.reason)}")


# Process-wide cache for fixed phrases (greeting, acknowledgement filler) so they
# replay instantly without a TTS round-trip. Keyed by voice + text.
_PCM_CACHE: dict[str, bytes] = {}
# Bytes per AudioDataStream.read_data() pull while streaming (~0.17s of audio).
_STREAM_CHUNK_BYTES = 8000


def synthesize_pcm_cached(text: str, voice: str = SINHALA_TTS_VOICE) -> bytes:
    """`synthesize_pcm` with a process-wide cache — for fixed phrases that repeat
    every session (greeting, "let me check…" filler), so they cost one synth ever."""
    key = f"{voice}\x00{text}"
    pcm = _PCM_CACHE.get(key)
    if pcm is None:
        pcm = synthesize_pcm(text, voice)
        _PCM_CACHE[key] = pcm
    return pcm


def synthesize_pcm_stream(text: str, on_chunk, voice: str = SINHALA_TTS_VOICE) -> int:
    """Synthesise `text` to RAW PCM (24 kHz, 16-bit, mono) and call `on_chunk(bytes)`
    for each chunk AS it is produced — lower first-byte latency than synthesize_pcm,
    which waits for the whole utterance. Returns the total PCM byte count.

    Uses start_speaking_text_async() + AudioDataStream so audio starts flowing as
    soon as Azure produces the first bytes. `on_chunk` runs on the calling thread
    (run this under asyncio.to_thread and marshal chunks back to the loop)."""
    speechsdk, config = _speech_config()
    config.speech_synthesis_voice_name = voice
    config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm
    )
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
    result = synthesizer.start_speaking_text_async(text).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioStarted:
        detail = getattr(result, "cancellation_details", None)
        raise AzureSpeechError(f"Sinhala TTS failed: {getattr(detail, 'reason', result.reason)}")

    stream = speechsdk.AudioDataStream(result)
    total = 0
    while True:
        buffer = bytes(_STREAM_CHUNK_BYTES)
        n = stream.read_data(buffer)  # blocks until data; 0 when finished
        if n == 0:
            break
        on_chunk(buffer[:n])
        total += n
    return total


def start_continuous(on_recognized, on_speech_start=None, language: str = SINHALA_STT_LANG):
    """Start hands-free Sinhala recognition over a push audio stream.

    This is what makes the live (no push-to-talk) Sinhala path possible: instead
    of recording one blob and calling `recognize_once`, the caller streams mic
    PCM into the returned push stream and Azure's own VAD fires `on_recognized`
    with the transcript each time the speaker finishes an utterance.

    Args:
        on_recognized: called (on an Azure SDK thread) with the final transcript
            string of each completed utterance. Bridge it onto your event loop
            with `loop.call_soon_threadsafe(...)`.
        on_speech_start: optional, called (Azure thread) when speech begins — a
            barge-in cue for later; unused by the half-duplex v1.
        language: STT locale (default si-LK).

    Returns:
        `(recognizer, push_stream)`. Feed mic audio with
        `push_stream.write(pcm16_16khz_mono_bytes)`; on teardown call
        `recognizer.stop_continuous_recognition()` then `push_stream.close()`.
    """
    speechsdk, config = _speech_config()
    config.speech_recognition_language = language
    fmt = speechsdk.audio.AudioStreamFormat(
        samples_per_second=16000, bits_per_sample=16, channels=1
    )
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=fmt)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=config, audio_config=audio_config
    )

    def _recognized(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = (evt.result.text or "").strip()
            if text:
                on_recognized(text)

    recognizer.recognized.connect(_recognized)
    if on_speech_start is not None:
        recognizer.speech_start_detected.connect(lambda _evt: on_speech_start())

    recognizer.start_continuous_recognition()
    return recognizer, push_stream
