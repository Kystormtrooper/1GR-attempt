import os
print("✅ intent.py loaded from:", os.path.abspath(__file__))

import re
from dataclasses import dataclass
from typing import Optional

NOTE_PATTERNS = [
    r"\b(make|create|add|write)\s+(me\s+)?a\s+note\b",
    r"\b(note\s+to)\b",
    r"\b(note\s+that)\b",
    r"\b(remind\s+me\s+to)\b",
    r"\b(add\s+to\s+(my\s+)?(list|notes))\b",
]

def looks_like_note(text: str) -> bool:
    t = text.strip().lower()
    return any(re.search(p, t) for p in NOTE_PATTERNS)

@dataclass
class IntentResult:
    intent: str
    confidence: float
    matched: Optional[str] = None

CHECKIN = {
    "how are you",
    "how are you?",
    "are you there",
    "are you there?",
    "can you hear me",
    "can you hear me?",
    "hello",
    "hello?",
    "you there",
    "you there?",
    "hey",
    "hey?",
}

# Simple keyword/regex patterns per intent
INTENT_PATTERNS = [
    ("EXIT", 0.99, r"^(q|quit|exit|goodbye|bye|stop)$"),
    ("TEACH", 0.90, r"^teach:\s*.+\s*=\s*.+$"),
    ("STATUS", 0.90, r"\b(system status|status report|what's my status|whats my status|are you online|system check|check status)\b"),
    # Feedback
    ("FEEDBACK_POS", 0.95, r"\b(good job|nice|perfect|correct|yes|yep|right|that's it|that’s it|awesome|great|really good|so good|love that|nailed it)\b"),
    ("FEEDBACK_NEG", 0.95, r"\b(no|nope|wrong|not that|stop that|bad|incorrect)\b"),

    # Clarification signals
    ("CLARIFICATION", 0.85, r"\b(i meant|what i meant|actually|to clarify|that was a reference|i was referring to)\b"),

    # Commands
    ("COMMAND", 0.20, r"\b(turn on|turn off|set|open|close|start|play|pause|resume|switch)\b"),

    # Questions (either starts like a question OR ends with '?')
    ("QUESTION", 0.75, r"^\s*(what|why|how|when|where|who|can you|do you|are you|is it)\b"),
    ("QUESTION", 0.65, r"\?$"),

    # Greeting (simple)
    ("GREETING", 0.90, r"^\s*(hi|hello|hey|yo|sup|howdy)\b"),

    # Topic/statement (robust)
    ("STATEMENT", 0.70, r"^\s*(an|a|the|my|our|this|that|im|i'm|i am|we're|we are|building|making|creating)\b"),
    ("CHOICE", 0.85, r"^\s*(talk|voice|speech|gestures?|gesture|commands?|command|actions?)\s*$"),
    ("TOPIC", 0.60, r"\b(ai|a\.i\.|ml|machine learning|nlp|module|model|assistant|gesture|gestures|raspberry\s*pi|esp32|pi)\b"),
]

def detect_intent(text: str) -> IntentResult:
    if not text:
        return IntentResult("SMALLTALK", 0.01)

    t = text.lower().strip()

    # FLEXIBLE CHECKIN (regex FIRST)
    if re.search(r"\bhow are (you|we) doing\b", t):
        return IntentResult("CHECKIN", 0.90, matched="how are you/we doing")

    # Exact check-in shortcuts
    if t in CHECKIN:
        return IntentResult("CHECKIN", 0.90, matched=t)

    # ✅ NOTE INSERT (must be BEFORE INTENT_PATTERNS loop)
    if looks_like_note(t):
        # pick the first pattern that matched for debugging
        matched_pat = None
        for p in NOTE_PATTERNS:
            if re.search(p, t):
                matched_pat = p
                break
        return IntentResult("NOTE", 0.90, matched=matched_pat or "note")
    # STATUS intent (put before patterns loop so it wins)
    if re.search(r"\b(status|system status|status report|system check|check status|glove status)\b", t):
        return IntentResult("STATUS", 0.90, matched="status keyword")
    # Regex patterns
    for intent_name, conf, pattern in INTENT_PATTERNS:
        if re.search(pattern, t, flags=re.IGNORECASE):
            return IntentResult(intent_name, conf, matched=pattern)

    # Fallback question heuristic
    if "?" in t:
        return IntentResult("QUESTION", 0.65, matched="?")

    return IntentResult("SMALLTALK", 0.65)


from datetime import datetime

def respond(text: str, intent_result):
    intent = intent_result.intent
    t = text.lower().strip()

    # --- BASIC ROUTES ---
    if intent == "CHECKIN":
        return "I'm here and listening."

    if intent == "GREETING":
        return "Hey there."
    
    if intent == "STATUS":
        return "Online. Wake word is armed. Notes are ready."
    
    if intent == "QUESTION":
        return "Good question. I'm still learning, but I'm listening."

    if intent == "NOTE":
        return "Got it. Saving that note."

    if intent == "COMMAND":
        return "Command received."

    if intent == "FEEDBACK_POS":
        return "Nice."

    if intent == "FEEDBACK_NEG":
        return "Got it, adjusting."

    if intent == "CLARIFICATION":
        return "Okay, clarifying."

    if intent == "TOPIC":
        return "Let's talk about it."

    if intent == "SMALLTALK":
        return "I'm here."

    if intent == "EXIT":
        return "Stopping."

    # fallback
    return "I heard you."