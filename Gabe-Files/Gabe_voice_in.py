import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from faster_whisper import WhisperModel

_WHISPER_MODEL = None

def get_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        print("[stt] loading whisper model...")
        _WHISPER_MODEL = WhisperModel("base", compute_type="int8")
    return _WHISPER_MODEL


MODEL_SIZE = "base"  # "tiny" faster, "small" more accurate

# Use your stable WASAPI mic device index (from earlier: 22)
MIC_DEVICE = 12

TARGET_RATE = 16000

def resample_int16_to_16k(pcm16: np.ndarray, src_rate: int) -> np.ndarray:
    """Resample int16 PCM from src_rate to 16kHz using linear interpolation."""
    if pcm16 is None or pcm16.size == 0:
        return np.zeros((0,), dtype=np.int16)
    if src_rate == TARGET_RATE:
        return pcm16.astype(np.int16)

    # int16 -> float32 in [-1, 1]
    x = pcm16.astype(np.float32) / 32768.0

    n_src = len(x)
    n_dst = int(n_src * TARGET_RATE / src_rate)
    if n_dst <= 0:
        return np.zeros((0,), dtype=np.int16)

    src_idx = np.arange(n_src, dtype=np.float32)
    dst_idx = np.linspace(0, n_src - 1, n_dst, dtype=np.float32)
    y = np.interp(dst_idx, src_idx, x).astype(np.float32)

    # float [-1,1] -> int16
    y = np.clip(y, -1.0, 1.0)
    return (y * 32767.0).astype(np.int16)

def voice_activity_ratio(pcm, sr: int, frame_ms: int = 30) -> float:
    if pcm is None:
        return 0.0

    x = np.asarray(pcm)

    if x.size == 0:
        return 0.0

    # Flatten to 1D
    x = x.reshape(-1)

    # If audio looks like float [-1, 1], convert to int16-like scale for thresholds
    # (This keeps your thr=80 logic meaningful.)
    if np.issubdtype(x.dtype, np.floating) and np.max(np.abs(x)) <= 1.5:
        x = (x.astype(np.float32) * 32767.0)
    else:
        x = x.astype(np.float32)

    frame = int(sr * frame_ms / 1000)
    if frame <= 0:
        return 0.0

    n = (len(x) // frame) * frame
    if n <= 0:
        return 0.0

    x = x[:n].reshape(-1, frame)
    rms_frames = np.sqrt(np.mean(x * x, axis=1))

    med = float(np.median(rms_frames))
    thr = max(80.0, med * 2.5)  # robust gate in int16-ish units

    return float(np.mean(rms_frames > thr))

import numpy as np
import sounddevice as sd
import wave
import time

def record_wav(path="voice.wav", seconds=4):
    dev = sd.query_devices(MIC_DEVICE, "input")
    native_rate = int(dev["default_samplerate"])

    chunk_frames = int(native_rate * 0.2)   # 0.2s chunks
    frames_total = int(seconds * native_rate)

    print(f"[voice_in] recording from device={MIC_DEVICE} '{dev['name']}' native_rate={native_rate} seconds={seconds}")

    chunks = []
    frames_remaining = frames_total

    # Use InputStream so we control dtype + avoid weird RawInputStream byte handling
    with sd.InputStream(
        device=MIC_DEVICE,
        channels=1,
        samplerate=native_rate,
        dtype="int16",
        blocksize=chunk_frames,
        latency="low",
    ) as stream:
        while frames_remaining > 0:
            n = min(chunk_frames, frames_remaining)
            data, overflowed = stream.read(n)   # data shape: (n, 1), dtype int16
            if overflowed:
                print("[voice_in] ⚠️ overflow")

            chunks.append(data.copy())
            frames_remaining -= n

    pcm16 = np.concatenate(chunks, axis=0).reshape(-1)  # 1D int16

    # Metrics (int16 scale)
    rms = float(np.sqrt(np.mean(pcm16.astype(np.float32) ** 2))) if pcm16.size else 0.0
    peak = float(np.max(np.abs(pcm16))) if pcm16.size else 0.0
    print(f"[voice_in] rms={rms:.1f} peak={peak:.0f}")

    # Debug clipping in raw PCM
    clip_frac = float(np.mean(np.abs(pcm16) > 32000)) if pcm16.size else 0.0
    print(f"[voice_in] clip_frac(abs>32000)={clip_frac:.2f}")

    # Write proper PCM16 WAV
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)         # 16-bit
        wf.setframerate(native_rate)
        wf.writeframes(pcm16.tobytes())

    return path




def transcribe_wav(path="voice.wav"):
    model = get_model()
    segments, _info = model.transcribe(path)
    return " ".join(seg.text.strip() for seg in segments).strip()
