import json
import os
from dataclasses import dataclass
from typing import Optional

MEMORY_FILE = "phrase_memory.json"

@dataclass
class PhraseHit:
    found: bool
    phrase: Optional[str] = None
    meaning: Optional[str] = None
    intent_override: Optional[str] = None

def load_phrase_memory() -> dict:
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_phrase_memory(mem: dict) -> None:
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)

import re

def normalize(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s]", "", s)  # remove punctuation
    return " ".join(s.split())

def find_phrase(text: str, mem: dict) -> PhraseHit:
    t = normalize(text)
    # exact match first
    if t in mem:
        entry = mem[t]
        return PhraseHit(True, t, entry.get("meaning"), entry.get("intent_override"))
    return PhraseHit(False)

def teach_phrase(phrase: str, meaning: str, intent_override: str, mem: dict) -> dict:
    p = normalize(phrase)
    mem[p] = {"meaning": meaning.strip(), "intent_override": intent_override}
    return mem
