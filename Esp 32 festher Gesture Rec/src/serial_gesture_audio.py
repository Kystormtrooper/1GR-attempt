# serial_gesture_audio.py
import random
import time
import serial
import re
import threading
from pathlib import Path
from playsound import playsound  # pip install playsound==1.2.2
import msvcrt
PORT = "COM3"
BAUD = 115200

DEBUG_SERIAL = True

BASE_DIR = Path(__file__).resolve().parent
SOUNDS = BASE_DIR / "sounds"
STORM_DIR = SOUNDS / "stormtrooper"
print("STORM_DIR =", STORM_DIR)
print("WAV count =", len(list(STORM_DIR.glob("*.wav"))))
GCODE_RE = re.compile(r"^(?:EVT=)?(G\d{2})$")

INTENT_NAMES = {
    "G21": "Watching You",
    "G07": "Move Out",
    "G12": "Move Along"
}

_last_played = {}  # code -> filename last played
_last_seen = {}          # code -> last time we accepted it
DEBOUNCE_SEC = 0.40      # tune 0.25–0.70
# ... imports ...

def get_bucket_files(code: str):
    bucket_prefix = {
        "G21": "watching_you_",
        "G07": "move_out_",
        "G12": "move_along_",
    }.get(code)

    if not bucket_prefix:
        return []

    return [f for f in STORM_DIR.glob(f"{bucket_prefix}*.wav")
            if f.suffix.lower() == ".wav"]


def startup_debug():
    print("STORM_DIR =", STORM_DIR)
    wavs = sorted([p.name for p in STORM_DIR.glob("*.wav")])
    print("WAV count =", len(wavs))
    print("WAVs =", wavs)
    print("G07 files =", [p.name for p in get_bucket_files("G07")])
    print("G12 files =", [p.name for p in get_bucket_files("G12")])
    print("G21 files =", [p.name for p in get_bucket_files("G21")])


def main():
    startup_debug()
    print(f"Listening on {PORT} @ {BAUD}...")
    print(f"Expecting WAVs in: {STORM_DIR.resolve()}")
    # ... rest of your serial loop ...
def get_bucket_files(code: str):
    bucket_prefix = {
        "G21": "watching_you_",
        "G07": "move_out_",
        "G12": "move_along_",
    }.get(code)

    if not bucket_prefix:
        return []

    return [f for f in STORM_DIR.glob(f"{bucket_prefix}*.wav")
            if f.suffix.lower() == ".wav"]


def play_bucket(code: str):
    # --- debounce repeats ---
    now = time.time()
    last = _last_seen.get(code, 0.0)
    if now - last < DEBOUNCE_SEC:
        if DEBUG_SERIAL:
            print(f"🧯 Debounced {code}")
        return
    _last_seen[code] = now

    # --- load bucket files ---
    files = get_bucket_files(code)
    if not files:
        print(f"🎛️ No bucket files found for {code} in {STORM_DIR}")
        return

    # --- avoid same clip twice in a row ---
    last_name = _last_played.get(code)
    choices = [f for f in files if f.name != last_name] or files

    f = random.choice(choices)
    _last_played[code] = f.name

    intent_name = INTENT_NAMES.get(code, code)
    print(f"🔊 {intent_name} -> {f.name}")

    # Non-blocking audio so we keep reading serial
    threading.Thread(target=playsound, args=(str(f),), daemon=True).start()

def main():
    print(f"Listening on {PORT} @ {BAUD}...")
    print(f"Expecting WAVs in: {STORM_DIR.resolve()}")

    # --- startup sanity check: do we see the wav files? ---
    all_wavs = list(STORM_DIR.glob("*.wav"))

    print("G07 files =", [p.name for p in get_bucket_files("G07")])
    print("G12 files =", [p.name for p in get_bucket_files("G12")])
    print("G21 files =", [p.name for p in get_bucket_files("G21")])

    with serial.Serial(PORT, BAUD, timeout=1) as ser:
        time.sleep(2)
        ...
        while True:
            ALLOWED_KEYS = set(b"bBkKrRdD0123456789qQ")

            if msvcrt.kbhit():
                key = msvcrt.getch()

                if key in (b"q", b"Q"):
                    print("👋 quitting")
                    break

                if key in ALLOWED_KEYS:
                    ser.write(key)
                    print(f"➡️ sent {key!r}")
                else:
                    if DEBUG_SERIAL:
                        print(f"🙅 ignored key {key!r}")
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue

            print("📥", repr(line))

            # Try to extract a gesture code from *either* plain lines or debug lines
            candidate = line
            if candidate.startswith("#"):
                candidate = candidate.lstrip("#").strip()   # "# EVT=G12" -> "EVT=G12"

            m = GCODE_RE.match(candidate)
            if m:
                play_bucket(m.group(1))
                continue

            # Now normal debug handling
            if line.startswith("#"):
                if DEBUG_SERIAL:
                    print("🧾", line)
                continue


if __name__ == "__main__":
    main()
