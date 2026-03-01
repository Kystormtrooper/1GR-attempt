import os
import time
import numpy as np
import sounddevice as sd
import openwakeword
from openwakeword.model import Model
from Gabe_wakeword import listen_for_wakeword
import Gabe_wakeword
# --- environment: keep console quiet on Windows ---
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TQDM_DISABLE"] = "1"
os.environ["RICH_DISABLE"] = "1"
os.environ["TERM"] = "dumb"

WAKEWORD_VERSION = "wakeword.py v7-fixed"
print("🚨 USING WAKEWORD FILE:", os.path.abspath(__file__))
print("🚨 VERSION:", WAKEWORD_VERSION)
print("🚨 LAST MODIFIED:", time.ctime(os.path.getmtime(__file__)))
print("✅ wakeword.py loaded from:", os.path.abspath(__file__))

# ---------------- settings ----------------
FRAME_MS = 20
MIC_DEVICE = 12           # <-- you confirmed 12 records successfully (WASAPI mic)
MIN_SCORE = 0.65
MARGIN = 0.15

WAKEWORDS = {"alexa", "hey_mycroft", "hey_jarvis", "hey_rhasspy"}

_OWW = None
_MODELS_READY = False


def pick_input_sr(device_index: int) -> int:
    # common Windows-friendly rates; prefer 48k if possible
    for sr in (48000, 44100, 16000):
        try:
            sd.check_input_settings(device=device_index, channels=1, samplerate=sr)
            return sr
        except Exception:
            pass
    return int(sd.query_devices(device_index)["default_samplerate"])


def downsample_to_16k(x: np.ndarray, src_rate: int) -> np.ndarray:
    """Linear-resample 1D float array from src_rate -> 16k."""
    if src_rate == 16000:
        return x.astype(np.float32)

    n_src = len(x)
    n_dst = int(n_src * 16000 / src_rate)
    if n_dst <= 0:
        return np.zeros((0,), dtype=np.float32)

    src_idx = np.arange(n_src)
    dst_idx = np.linspace(0, n_src - 1, n_dst)
    y = np.interp(dst_idx, src_idx, x)
    return y.astype(np.float32)


def listen_for_wakeword(keyword: str = "hey_jarvis", threshold: float = MIN_SCORE):
    """
    Returns:
      - float score (0..1-ish) if the chosen wakeword was detected
      - False otherwise (for compatibility)
    """
    global _OWW, _MODELS_READY

    print(f"[wake] threshold param = {threshold!r} (MIN_SCORE={MIN_SCORE})")

    # --- caching block ---
    if not _MODELS_READY:
        print("[wake] step 1: download_models()")
        openwakeword.utils.download_models()
        print("[wake] step 1 ok")
        _MODELS_READY = True

    if _OWW is None:
        print("[wake] step 2: Model()")
        _OWW = Model()
        print("[wake] step 2 ok")

    oww = _OWW
    available = list(oww.models.keys())
    print("[wake] step 3: models loaded:", available)

    if not available:
        raise RuntimeError("No wakeword models found.")

    if keyword not in oww.models:
        keyword = available[0]
        print(f"[wake] keyword not found, using {keyword}")

    info = sd.query_devices(MIC_DEVICE)
    print(
        f"[wake] MIC_DEVICE={MIC_DEVICE} name='{info['name']}' "
        f"IN={info['max_input_channels']} OUT={info['max_output_channels']}"
    )
    if info["max_input_channels"] <= 0:
        raise RuntimeError(f"MIC_DEVICE {MIC_DEVICE} is not an input device: {info['name']}")

    native_rate = pick_input_sr(MIC_DEVICE)
    block = int(native_rate * FRAME_MS / 1000)
    last_detect = 0.0
    DETECT_COOLDOWN = 1.5
    ...
    if hit_count >= HIT_FRAMES_REQUIRED and (time.time() - last_detect) > DETECT_COOLDOWN:
        last_detect = time.time()
        return best_v
    print(f"[wake] opening InputStream rate={native_rate} FRAME_MS={FRAME_MS} read_block={block}")

    try:
        with sd.InputStream(
            device=MIC_DEVICE,
            channels=1,
            samplerate=native_rate,
            dtype="float32",
            blocksize=block,     # let PortAudio choose
            latency="high",
        ) as stream:
            print("[wake] listening...")

            next_preds_print = time.time() + 2.0
            last_note = 0.0
            HIT_FRAMES_REQUIRED = 5
            hit_count = 0
            while True:
                data, overflowed = stream.read(block)
                if overflowed:
                    print("[wake] ⚠️ overflow")

                x = data[:, 0]  # float32

                # scale to int16-ish range (openwakeword expects int16 samples)
                pcm = (x * 32767.0).astype(np.float32)
                x16_f = downsample_to_16k(pcm, native_rate)
                x16_i16 = np.clip(x16_f, -32768, 32767).astype(np.int16)

                preds = oww.predict(x16_i16)

                # best wakeword among the set
                best_k = None
                best_v = -1.0
                second_v = -1.0

                for k, v in preds.items():
                    if k not in WAKEWORDS:
                        continue
                    v = float(v)
                    if v > best_v:
                        second_v = best_v
                        best_v = v
                        best_k = k
                    elif v > second_v:
                        second_v = v

                # occasional debug
                if time.time() >= next_preds_print:
                    next_preds_print = time.time() + 2.0
                    if best_k is not None:
                        print(f"[wake] best={best_k}:{best_v:.3f} second={second_v:.3f}")

                # decide hit
                hit = (best_k == keyword and best_v >= threshold and (best_v - second_v) >= MARGIN)

                if hit:
                    hit_count += 1
                else:
                    hit_count = 0

                if hit_count >= HIT_FRAMES_REQUIRED:
                    print(f"[wake] ✅ DETECTED {best_k} score={best_v:.2f}")
                    return best_v

                # (optional) note other hot model sometimes
                if best_k and best_v >= 0.40 and (time.time() - last_note) > 1.5 and best_k != keyword:
                    last_note = time.time()
                    print(f"[wake] NOTE: other hot model best={best_k}:{best_v:.4f}")

    except Exception as e:
        print(f"[wake] ❌ stream/model failed: {e!r}")
        raise

    return False


if __name__ == "__main__":
    print("[wakeword.py] self-test... say 'hey jarvis'")
    while True:
        score = listen_for_wakeword(keyword="hey_jarvis", threshold=MIN_SCORE)
        print(f"[wakeword.py] returned: {score!r}")