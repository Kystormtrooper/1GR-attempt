print("[BOOT] starting file:", __file__)
import faulthandler
import sys
import os
import builtins
import time
import re
import threading
import queue

faulthandler.enable()

print("✅ DEBUG __name__ =", __name__)
sys.stdout.flush()

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Force UTF-8 console
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 🔧 Disable progress-bar console bugs (fixes OSError 9 in openwakeword on Windows)
os.environ["PYTHONUTF8"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TQDM_DISABLE"] = "1"
os.environ["RICH_DISABLE"] = "1"
os.environ["TERM"] = "dumb"

print("✅ Gabe_Gabriel_AI running from:", os.path.abspath(__file__))
print("✅ reached top of file")

import atexit

def _on_exit():
    try:
        import sys
        sys.__stderr__.write("[atexit] program is exiting\n")
        sys.__stderr__.flush()
    except Exception:
        pass

atexit.register(_on_exit)


# --- Core imports ---
from collections import deque
from transformers import pipeline
import sounddevice as sd
import Gabe_phrase_memory
print("[debug] phrase_memory loaded from:", Gabe_phrase_memory.__file__)
print("[debug] phrase_memory has:", [x for x in ["load_phrase_memory","save_phrase_memory","find_phrase","teach_phrase"] if hasattr(Gabe_phrase_memory, x)])

from Gabe_wakeword import listen_for_wakeword
import Gabe_wakeword
print("🔎 wakeword imported from:", Gabe_wakeword.__file__)
print("🔎 wakeword has return-float version? MIN_SCORE =", getattr(Gabe_wakeword, "MIN_SCORE", None))
#from intent import detect_intent, respond
from Gabe_phrase_memory import load_phrase_memory, save_phrase_memory, find_phrase, teach_phrase
from Gabe_voice_in import record_wav
print("[debug] record_wav imported OK ->", record_wav)
print("[debug] STEP G: reached post-import section")
from Gabe_intent import detect_intent as nlp_detect_intent
from Gabe_intent import respond as nlp_respond
from Gabe_helpers import safe_speak, transcribe_wav, extract_note_payload, save_note_json
from Gabe_voice_utils import calibrate_noise_floor, record_and_gate
from Gabe_chat_brain import smart_chat
print("✅ imports finished")
print("✅ after imports: about to set up TTS / memory / main loop")

sys.stdout.flush()

# ---------------- GLOBAL SETTINGS ---------------- 
LISTEN_MODE = False
WAKEWORD = "hey_jarvis"      # your wake phrase
WAKE_THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.65"))
         # detection sensitivity (0.3–0.8 typical)

RECORD_SECONDS = int(os.getenv("RECORD_SECONDS", "4"))
MIC_DEVICE = int(os.getenv("MIC_DEVICE", "12"))
TTS_OUT_DEVICE = int(os.getenv("TTS_OUT_DEVICE", "11"))
TTS_TARGET_SR = int(os.getenv("TTS_TARGET_SR", "44100"))
VOICE_SESSION_TIMEOUT_S = 30       # give human thinking time
VOICE_MAX_TURNS = 12
VOICE_END_SPOKEN = False          # only speak "standing by" when asked
VOICE_TTS_COOLDOWN_S = 0.25       # prevent calibrating during TTS tail
from Gabe_commands import NotesStore, GestureAPI, CommandDispatcher

notes = NotesStore("memory_notes.json")
gesture = GestureAPI()
dispatcher = CommandDispatcher(notes=notes, gesture=gesture)

from Gabe_memory import (
    load_memory, remember_fact, forget_fact, get_fact,
    list_facts, parse_remember, parse_forget, save_memory
)
print("[debug] helpers import OK ->", safe_speak, transcribe_wav)
from Gabe_memory import save_memory



MEM = load_memory()
MAX_TURNS = 10        # how many recent messages to remember
VOICE_RATE = 175


VOICE_MIN_RMS = 0.015        # float RMS gate (start here)
VOICE_MIN_ACTIVE = 0.05      # noisy room: slightly easier than 0.12
VOICE_FRAME_MS = 30
VOICE_RETRY_ON_FAIL = 1
LAST_REPLY = ""
LAST_INTENT = ""


# --- MEMORY ---
memory = deque(maxlen=MAX_TURNS)   # stores conversation history
phrase_mem = load_phrase_memory()

# --- LOAD MODEL ---
emotion_model = None
print("ℹ️ Emotion model disabled for now (emotion_model=None)")
GENERIC_REPLIES = {
    "Okay.",
    "I'm here.",
    "Good question. I'm still learning, but I'm listening.",
    "I'm not sure what you mean yet. Try rephrasing.",
}

def is_generic(reply: str) -> bool:
    r = (reply or "").strip()
    if not r:
        return True
    if r in GENERIC_REPLIES:
        return True
    # short non-answer vibe
    if len(r) < 8:
        return True
    return False

def handle_text(text: str):
    print(f"[route] handle_text hit: {text!r}")
    global LISTEN_MODE, MEM
    global LAST_REPLY, LAST_INTENT
    global VOICE_END_SPOKEN
    stripped = text.strip()
    lower = stripped.lower()
    text = re.sub(r"^\s*(hey\s+)?jarvis[\s,.:;-]*", "", text, flags=re.I).strip()
    # Guard: PowerShell commands typed into AI prompt
    if stripped.startswith("&") or "python.exe" in lower or lower.startswith("python ") or lower.startswith("pip "):
        safe_speak("That’s a PowerShell command. Run it at the PS prompt, not inside the AI 🙂")
        return

    # Normalize command tokens
    norm_cmd = re.sub(r"[^a-z0-9\s]", "", lower)
    norm_cmd = re.sub(r"\s+", " ", norm_cmd).strip()

    # Hard exit words (works for voice transcript too)
    if norm_cmd in {"q", "quit", "exit", "stop", "shutdown"}:
        raise SystemExit

    if norm_cmd in {"stand by", "go to sleep", "sleep", "quiet"}:
        VOICE_END_SPOKEN = True
        safe_speak("Standing by.")
        raise StopIteration

    # Follow-up glue
    if norm_cmd in {"what do you mean", "explain that", "tell me more"} and LAST_REPLY:
        safe_speak(LAST_REPLY)
        return
    # --- Phrase memory override (exact phrase match) ---
    
    hit = find_phrase(text, phrase_mem)
    if hit.found:
        print(f"[phrase] matched='{hit.phrase}' override={hit.intent_override!r}")
    
        # Optional intent overrides
        if hit.intent_override == "LISTEN_ON":
            LISTEN_MODE = True
        elif hit.intent_override == "LISTEN_OFF":
            LISTEN_MODE = False

        # Speak meaning (or fallback)
        if hit.meaning:
            safe_speak(hit.meaning)
        else:
            safe_speak("I matched a phrase, but it has no meaning saved.")
        return
    # --- Memory commands FIRST ---
    rem = parse_remember(text)
    if rem:
        k, v = rem
        remember_fact(MEM, k, v)
        save_memory(MEM)
        safe_speak(f"Locked in. I’ll remember {k} is {v}.")
        return

    fg = parse_forget(text)
    if fg:
        if fg == "__ALL__":
            MEM["facts"] = {}
            save_memory(MEM)
            safe_speak("Memory wiped. Fresh slate.")
        else:
            ok = forget_fact(MEM, fg)
            save_memory(MEM)
            safe_speak(f"Forgot {fg}." if ok else f"I don’t have {fg} saved.")
        return

    # --- Commands dispatcher (notes, gesture, etc.) ---
    try:
        cmd_result = dispatcher.handle(text)
    except Exception as e:
        print(f"[cmd] dispatcher crashed: {e!r}")
        cmd_result = None

    if cmd_result and cmd_result.ok:
        print(f"[cmd] {cmd_result.message}")
        safe_speak(cmd_result.message)

        if cmd_result.data:
            if "set_listen_mode" in cmd_result.data:
                LISTEN_MODE = bool(cmd_result.data["set_listen_mode"])

        return

    # --- NLP fallback ---
    intent_result = nlp_detect_intent(text)

    print(f"[intent] {intent_result.intent} conf={intent_result.confidence:.2f} matched={intent_result.matched}")

    # ================================
    # SMART RESPONSE (cloud-first)
    # ================================
    print("[chat] calling smart_chat... mode=", os.getenv("CHAT_MODE"), "base=", bool(os.getenv("CLOUD_BASE_URL")), "key=", bool(os.getenv("CLOUD_API_KEY")), "model=", os.getenv("CLOUD_MODEL"))
    memory.append({"role": "user", "content": text})

    smart = smart_chat(text, list(memory))
    print(f"[chat] smart_len={len(smart) if smart else 0}")  # DEBUG

    if smart:
        safe_speak(smart)
        memory.append({"role": "assistant", "content": smart})
        return

    # If cloud/local chat fails, fall back to intent reply
    reply = nlp_respond(text, intent_result) if intent_result else None
    if reply:
        safe_speak(reply)
        memory.append({"role": "assistant", "content": reply})
        return

    safe_speak("Okay.")
    memory.append({"role": "assistant", "content": "Okay."})
    return
def voice_conversation_loop():
    global LISTEN_MODE, VOICE_END_SPOKEN

    VOICE_END_SPOKEN = False
    print("[voice] session started")

    # Cooldown after "Yes?" so calibration doesn't learn your TTS tail
    import time as pytime
    pytime.sleep(VOICE_TTS_COOLDOWN_S)

    # Calibrate ONCE per session
    noise_rms = calibrate_noise_floor(MIC_DEVICE, sr=48000, seconds=0.35)
    noise_rms = min(noise_rms, 0.020)            # allow higher real noise
    min_rms = min(0.03, max(0.0035, noise_rms * 1.3))
    print(f"[cal] session noise_rms={noise_rms:.4f} -> min_rms={min_rms:.4f}")

    session_last_heard = pytime.time()
    turns = 0
    fails = 0

    while True:
        if not LISTEN_MODE:
            print("[voice] LISTEN_MODE off, ending session")
            return

        # End session after silence timeout
        if pytime.time() - session_last_heard > VOICE_SESSION_TIMEOUT_S:
            print("[voice] session timeout (silence)")
            # speak only if user asked to
            if VOICE_END_SPOKEN:
                safe_speak("Standing by.")
            print("[voice] session ended")
            return

        if turns >= VOICE_MAX_TURNS:
            print("[voice] max turns reached")
            print("[voice] session ended")
            return

        wav_path = record_and_gate(
            seconds=RECORD_SECONDS,
            min_rms=min_rms,
            record_wav=record_wav,
            speak=None,  # IMPORTANT: don't talk while recording
        )

        if wav_path is None:
            fails += 1
            pytime.sleep(0.12)
            # If we fail repeatedly, recalibrate
            if fails >= 4:
                noise_rms = calibrate_noise_floor(MIC_DEVICE, sr=48000, seconds=0.25)
                noise_rms = min(noise_rms, 0.012)
                min_rms = min(0.06, max(0.008, noise_rms * 2.5))
                print(f"[cal] recal noise_rms={noise_rms:.4f} -> min_rms={min_rms:.4f}")
                fails = 0
            continue

        fails = 0
        session_last_heard = pytime.time()

        text = transcribe_wav(wav_path).strip()
        print(f"[stt] text='{text}'")

        if not text:
            continue

        turns += 1

        try:
            handle_text(text)
        except StopIteration:
            # user said "stand by / sleep" etc.
            print("[voice] user ended session explicitly")
            print("[voice] session ended")
            return
import re
import time
import serial
from playsound import playsound

G_RE = re.compile(r"^G(\d{2})$")

def open_gesture_serial(port="COM3", baud=115200):
    ser = serial.Serial(port, baud, timeout=0)  # timeout=0 => non-blocking
    ser.reset_input_buffer()
    print(f"[gesture][serial] listening on {port} @ {baud}")
    return ser

from typing import Optional

def read_gesture_if_available(ser) -> Optional[int]:
    ...
    if ser.in_waiting <= 0:
        return None
    line = ser.readline().decode("utf-8", errors="replace").strip()
    if len(line) > 8:   # ignore long debug lines fast
        return None
    m = G_RE.match(line)
    if not m:
        return None
    return int(m.group(1))

def start_serial_gesture_thread(port: str, baud: int, on_gesture):
    ser = open_gesture_serial(port, baud)

    def worker():
        while True:
            gid = read_gesture_if_available(ser)
            if gid is not None:
                try:
                    on_gesture(gid)
                except Exception as e:
                    print(f"[gesture][error] handler crashed: {e!r}")
            time.sleep(0.01)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return ser, t
def main():
    print("🟩 main() entered")
    # ... your existing code ...

    print("🟥 main() about to return")
    global LISTEN_MODE
    print("[BOOT] entered main()")

    # Response buckets (1 clip each for now)
    BUCKETS = {
        "watching_you": [r"audio\watching_you.wav"],
    }

    last_bucket_time = {}

    def play_bucket(bucket_name: str, cooldown=0.6):
        now = time.time()
        if now - last_bucket_time.get(bucket_name, 0) < cooldown:
            return
        last_bucket_time[bucket_name] = now

        clip = BUCKETS[bucket_name][0]
        print(f"[bucket] {bucket_name} -> {clip}")
        playsound(clip)
    def handle_gesture(gid: int):
        # Map gesture IDs -> buckets
        if gid == 21:
            play_bucket("watching_you")
    # Start gesture reader thread (does not block your voice loop)
    ser, gesture_thread = start_serial_gesture_thread("COM3", 115200, handle_gesture)

    while True:
        try:
            if LISTEN_MODE:
                detected = listen_for_wakeword(keyword=WAKEWORD, threshold=WAKE_THRESHOLD)
                print(f"[wake] listen_for_wakeword() returned: {detected!r}")

                # If float score, enforce threshold
                if isinstance(detected, (int, float)) and detected < WAKE_THRESHOLD:
                    print(f"[wake] ignored low score={detected:.2f}")
                    continue
                if not isinstance(detected, (int, float)) and not detected:
                    continue

                safe_speak("Yes?")
                voice_conversation_loop()
                continue
            # ================================
            # KEYBOARD MODE
            # ================================
            user = input("You (type, or 'q' to quit): ").strip()
            if not user:
                continue

            lower_user = user.lower()

            # Listen mode toggles
            if lower_user in {"listen on", "arm", "mic on"}:
                LISTEN_MODE = True
                safe_speak("Listening enabled. Say the wake word when ready.")
                continue

            if lower_user in {"listen off", "disarm", "mic off"}:
                LISTEN_MODE = False
                safe_speak("Listening disabled.")
                continue
            if lower_user in {"memory list", "list memory"}:
                facts = list_facts(MEM)
                if not facts:
                    safe_speak("No saved facts yet.")
                else:
                    for k, v in facts.items():
                        print(f"- {k}: {v}")
                    safe_speak(f"I have {len(facts)} saved facts.")
                continue

            handle_text(user)

        except SystemExit:
            safe_speak("Stopping.")
            break
        except KeyboardInterrupt:
            safe_speak("Stopping.")
            break
        except Exception as e:
            print(f"[error] main loop crashed: {e!r}")
            try:
                sd.stop()
            except Exception:
                pass
            safe_speak("Something crashed. Back to keyboard mode.")
            LISTEN_MODE = False
            continue

if __name__ == "__main__":
    print("🚀 Gabe Gabriel AI is live. Listening for 'hey_jarvis'...")
    
