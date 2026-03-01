# helpers.py
import traceback
import winsound

import pyttsx3
import json
from pathlib import Path
from datetime import datetime, time

NOTES_PATH = Path(__file__).parent / "notes.json"

def save_note_json(note_text: str) -> None:
    note_text = (note_text or "").strip()
    if not note_text:
        return

    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing notes
    if NOTES_PATH.exists():
        try:
            data = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
    else:
        data = []

    # Append new note
    data.append({
        "text": note_text,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })

    NOTES_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[cmd] Saved note: {note_text}")
# ---------------------------
# TTS (text-to-speech)
# ---------------------------
_tts = None

import re

def extract_note_payload(text: str) -> str:
    t = text.strip()

    prefixes = [
        r"(?i)make\s+(me\s+)?a\s+note\s+(to\s+)?",
        r"(?i)create\s+(me\s+)?a\s+note\s+(to\s+)?",
        r"(?i)add\s+(me\s+)?a\s+note\s+(to\s+)?",
        r"(?i)write\s+(me\s+)?a\s+note\s+(to\s+)?",
        r"(?i)remind\s+me\s+to\s+",
        r"(?i)note\s+to\s+",
        r"(?i)note\s+that\s+",
        r"(?i)add\s+to\s+(my\s+)?(list|notes)\s*:\s*",
    ]

    for p in prefixes:
        t2 = re.sub(p, "", t).strip()
        if t2 != t:
            t = t2
            break

    return t.strip().rstrip(".!")
def speak(text: str):
    """Basic TTS. May throw if audio/TTS fails."""
    global _tts
    if _tts is None:
        _tts = pyttsx3.init()
        print("[tts] engine:", _tts)
        print("[tts] voice:", _tts.getProperty("voice"))
        print("[tts] rate:", _tts.getProperty("rate"))
                # Rate
        _tts.setProperty("rate", 185)

        # Voice selection (prefer David if available)
        try:
            voices = _tts.getProperty("voices") or []
            chosen_id = None

            for v in voices:
                if "David" in (v.name or ""):
                    chosen_id = v.id
                    break

            if chosen_id is None and voices:
                chosen_id = voices[0].id  # fallback

            if chosen_id is not None:
                _tts.setProperty("voice", chosen_id)

        except Exception:
            # Don't let voice selection break TTS
            pass

    _tts.say(text)
    _tts.runAndWait()
from faster_whisper import WhisperModel

_WHISPER_MODEL = None

def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        print("[stt] loading whisper model...")
        _WHISPER_MODEL = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _WHISPER_MODEL

def transcribe_wav(wav_path: str) -> str:
    try:
        model = get_whisper_model()
        segments, info = model.transcribe(wav_path, beam_size=5)
        return " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as e:
        print(f"[transcribe_wav] failed: {e!r}")
        return ""
# --- TTS via edge-tts -> wav -> sounddevice (forced device + forced SR) ---
import os, asyncio, tempfile, time as pytime
import numpy as np
import sounddevice as sd
import soundfile as sf

def get_tts_out_device() -> int:
    return int(os.getenv("TTS_OUT_DEVICE", "11"))

def get_tts_target_sr() -> int:
    return int(os.getenv("TTS_TARGET_SR", "44100"))

async def _edge_tts_to_wav(text: str, out_wav: str):
    import edge_tts
    voice = os.getenv("TTS_VOICE", "en-US-GuyNeural")
    await edge_tts.Communicate(text, voice).save(out_wav)

def _resample_linear(audio: np.ndarray, sr: int, target_sr: int):
    if sr == target_sr:
        return audio, sr

    if audio.ndim == 1:
        audio = audio[:, None]

    n_src = audio.shape[0]
    n_dst = int(n_src * target_sr / sr)
    if n_dst < 10:
        return audio, sr

    src_idx = np.arange(n_src)
    dst_idx = np.linspace(0, n_src - 1, n_dst)

    out = np.empty((n_dst, audio.shape[1]), dtype=np.float32)
    for ch in range(audio.shape[1]):
        out[:, ch] = np.interp(dst_idx, src_idx, audio[:, ch]).astype(np.float32)

    return out, target_sr

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    return asyncio.run(coro)

def safe_speak(text: str):
    text = (text or "").strip()
    if not text:
        return

    out_dev = get_tts_out_device()
    target_sr = get_tts_target_sr()

    print(f"[tts] {text}")
    print(f"[tts] output device={out_dev} target_sr={target_sr}")

    wav_path = None
    try:
        # release any PortAudio locks
        try:
            sd.stop()
            sd.default.reset()
            pytime.sleep(0.05)
        except Exception:
            pass

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        _run_async(_edge_tts_to_wav(text, wav_path))
        audio, sr = sf.read(wav_path, dtype="float32")

        # force stereo (Windows outputs often expect 2ch)
        if audio.ndim == 1:
            audio = np.column_stack([audio, audio]).astype(np.float32)

        # force sample rate
        audio, sr = _resample_linear(audio, sr, target_sr)

        sd.play(audio, sr, device=out_dev)
        sd.wait()
        print("[tts] speak() finished OK")

    except Exception as e:
        print(f"[tts] FAILED: {e!r}")
        print(f"Assistant: {text}")

    finally:
        if wav_path:
            try: os.remove(wav_path)
            except Exception: pass