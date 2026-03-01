import os
import wave
import numpy as np
import sounddevice as sd
import builtins

# These must match your main settings
VOICE_RETRY_ON_FAIL = 1
VOICE_FRAME_MS = 30
VOICE_MIN_ACTIVE = 0.05


def load_wav_mono_float32(wav_path: str):
    with wave.open(wav_path, "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth} bytes")

    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)

    return audio, sr


def voice_activity_ratio(pcm, sr: int, frame_ms: int = 30) -> float:
    pcm = np.asarray(pcm).reshape(-1).astype(np.float32)
    if pcm.size == 0:
        return 0.0

    frame = int(sr * frame_ms / 1000)
    if frame <= 0:
        return 0.0

    n = (len(pcm) // frame) * frame
    if n <= 0:
        return 0.0

    x = pcm[:n].reshape(-1, frame)
    rms_frames = np.sqrt(np.mean(x * x, axis=1))
    med = float(np.median(rms_frames))
    thr = max(0.008, med * 2.0)

    return float(np.mean(rms_frames > thr))


def calibrate_noise_floor(device, sr=48000, seconds=0.4):
    print("[cal] listening to room noise...")
    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="int16", device=device)
    sd.wait()

    pcm = audio.reshape(-1).astype(np.float32) / 32768.0
    noise_rms = float(np.sqrt(np.mean(pcm * pcm))) if pcm.size else 0.0
    print(f"[cal] noise_rms={noise_rms:.4f}")
    return noise_rms


def record_and_gate(seconds: int, min_rms: float, record_wav, speak=None):
    attempt = 0

    while attempt <= VOICE_RETRY_ON_FAIL:
        audio_result = record_wav(seconds=seconds)

        if isinstance(audio_result, str):
            wav_path = audio_result
            if not os.path.exists(wav_path):
                raise FileNotFoundError(f"record_wav returned path but file not found: {wav_path}")
            pcm, sr = load_wav_mono_float32(wav_path)

        elif isinstance(audio_result, (tuple, list)) and len(audio_result) == 3:
            pcm, sr, wav_path = audio_result
        else:
            raise TypeError(f"record_wav returned unexpected type: {type(audio_result)}")

        pcm = np.asarray(pcm).reshape(-1)

        rms = float(np.sqrt(np.mean(pcm * pcm))) if pcm.size else 0.0
        active = voice_activity_ratio(pcm, sr, frame_ms=VOICE_FRAME_MS)

        print(f"[voice] gate rms={rms:.4f} active={active:.2f} (min_rms={min_rms:.4f})")

        if rms < min_rms or active < VOICE_MIN_ACTIVE:
            attempt += 1
            
            continue

        return wav_path

    return None
