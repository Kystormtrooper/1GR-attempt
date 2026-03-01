# commands.py
from __future__ import annotations

import json
import os
import re
import time
import platform
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional, List
from Gabe_intent import detect_intent as nlp_detect_intent

# -----------------------------
# Data structures
# -----------------------------

@dataclass
class CommandResult:
    ok: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@dataclass
class Intent:
    name: str
    slots: Dict[str, Any]
    confidence: float = 1.0


# -----------------------------
# Simple Notes Store (JSON)
# -----------------------------

class NotesStore:
    def __init__(self, path: str = "memory_notes.json"):
        self.path = path
        if not os.path.exists(self.path):
            self._write([])

    def _read(self) -> List[Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write(self, notes: List[Dict[str, Any]]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)

    def add(self, text: str) -> None:
        notes = self._read()
        notes.append({"ts": int(time.time()), "text": text})
        self._write(notes)

    def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        notes = self._read()
        return notes[-limit:]


# -----------------------------
# Gesture API stub
# Replace these with your real calls later
# -----------------------------

class GestureAPI:
    def calibrate(self) -> CommandResult:
        return CommandResult(True, "Glove calibration started (stub).")

    def start_record(self, label: str) -> CommandResult:
        return CommandResult(True, f"Recording gesture labeled '{label}' (stub).")

    def stop_record(self) -> CommandResult:
        return CommandResult(True, "Stopped gesture recording (stub).")

    def status(self) -> CommandResult:
        return CommandResult(True, "Glove status: connected? (stub).", data={"connected": None})


# -----------------------------
# Skill dispatcher
# -----------------------------

class CommandDispatcher:
    def __init__(self, notes: NotesStore, gesture: GestureAPI):
        self.notes = notes
        self.gesture = gesture
        self.skills: Dict[str, Callable[[Dict[str, Any]], CommandResult]] = {
            "help": self._help,
            "note.add": self._note_add,
            "note.list": self._note_list,
            "system.status": self._system_status,
            "glove.calibrate": self._glove_calibrate,
            "glove.record": self._glove_record,
            "glove.stop": self._glove_stop,
            "glove.status": self._glove_status,
        }

    @staticmethod
    def _normalize(text: str) -> str:
        t = text.strip().lower()
        t = re.sub(r"[^a-z0-9\s]", "", t)   # remove punctuation like "." "," "?"
        t = re.sub(r"\s+", " ", t).strip()  # normalize spaces
        return t

    def handle(self, text: str) -> CommandResult | None:
        """
        Return:
          - CommandResult if this input should be handled as a command
          - None if it is NOT a command (so caller can fall through to other logic)
        """
        t = self._normalize(text)

        # -----------------------------
        # LISTEN MODE (voice control)
        # -----------------------------
        if t in {"listen off", "disarm", "mic off", "stop listening"}:
            return CommandResult(True, "Listening disabled.", data={"set_listen_mode": False})

        if t in {"listen on", "arm", "mic on", "start listening"}:
            return CommandResult(True, "Listening enabled. Say the wake word.", data={"set_listen_mode": True})

        # -----------------------------
        # NATURAL NOTE COMMANDS
        # -----------------------------
        # Examples:
        #  "remember buy solder"
        #  "make a note to buy solder"
        #  "leave me a note buy solder"
        m = re.match(
            r"^(remember|leave( me)? a? note|make a note|take a note|add note|create a note|create note)\s+(to\s+)?(.+)$",
            t,
        )
        if m:
            note = m.group(4).strip()
            return self._note_add({"note": note})

     
    # ---- Skills ----

    def _help(self, slots: Dict[str, Any]) -> CommandResult:
        msg = (
            "Commands:\n"
            "• help\n"
            "• remember <note>\n"
            "• note list  (or: note list <N>)\n"
            "• system status\n"
            "• glove calibrate\n"
            "• glove record <label>\n"
            "• glove stop\n"
            "• glove status\n"
            "• listen on / listen off"
        )
        return CommandResult(True, msg)

    def _note_add(self, slots: Dict[str, Any]) -> CommandResult:
        note = (slots.get("note") or "").strip()
        if not note:
            return CommandResult(False, "What should I remember? Example: 'remember buy solder'")
        self.notes.add(note)
        return CommandResult(True, f"Saved note: {note}")

    def _note_list(self, slots: Dict[str, Any]) -> CommandResult:
        limit = int(slots.get("limit", 10))
        limit = max(1, min(limit, 50))
        recent = self.notes.list_recent(limit=limit)
        if not recent:
            return CommandResult(True, "No notes yet.")
        lines = [f"- {n['text']}" for n in recent]
        return CommandResult(True, "Recent notes:\n" + "\n".join(lines))

    def _system_status(self, slots: Dict[str, Any]) -> CommandResult:
        info = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
        }
        msg = (
            f"System status:\n"
            f"• Python: {info['python']}\n"
            f"• Platform: {info['platform']}\n"
            f"• Working dir: {info['cwd']}"
        )
        return CommandResult(True, msg, data=info)

    def _glove_calibrate(self, slots: Dict[str, Any]) -> CommandResult:
        return self.gesture.calibrate()

    def _glove_record(self, slots: Dict[str, Any]) -> CommandResult:
        label = (slots.get("label") or "").strip()
        if not label:
            return CommandResult(False, "Give a label. Example: 'glove record salute'")
        return self.gesture.start_record(label)

    def _glove_stop(self, slots: Dict[str, Any]) -> CommandResult:
        return self.gesture.stop_record()

    def _glove_status(self, slots: Dict[str, Any]) -> CommandResult:
        return self.gesture.status()
