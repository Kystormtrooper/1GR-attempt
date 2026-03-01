# Gabe-Files/chat_brain.py
from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from typing import List, Dict


def _messages_from_memory(memory_turns: List[Dict[str, str]], user_text: str) -> List[Dict[str, str]]:
    sys = {
        "role": "system",
        "content": (
            "You are Gabriel, a helpful voice assistant. "
            "Be concise, practical, and friendly. "
            "If unsure, ask one clarifying question. "
            "Avoid long lectures unless asked."
        ),
    }

    msgs = [sys]

    # keep last 8 turns
    for m in memory_turns[-8:]:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})

    msgs.append({"role": "user", "content": user_text})
    return msgs


def cloud_chat_openai(user_text: str, memory_turns: List[Dict[str, str]]) -> str:
    base = os.getenv("CLOUD_BASE_URL", "").rstrip("/")
    key = os.getenv("CLOUD_API_KEY", "")
    model = os.getenv("CLOUD_MODEL", "")

    if not base or not key or not model:
        return ""

    url = f"{base}/responses"

    # Build a compact prompt from memory
    lines = [
        "You are Gabriel, a helpful voice assistant. Be concise, practical, friendly.",
        "If unsure, ask one clarifying question.",
        "",
        "Conversation:",
    ]
    for m in memory_turns[-8:]:
        r = m.get("role", "")
        c = (m.get("content") or "").strip()
        if r in ("user", "assistant") and c:
            lines.append(f"{r.upper()}: {c}")
    lines.append(f"USER: {user_text}")
    lines.append("ASSISTANT:")

    payload = {
        "model": model,
        "input": "\n".join(lines),
        "max_output_tokens": 220,
        "temperature": 0.6,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return (data.get("output_text") or "").strip()
    except urllib.error.HTTPError as e:
        # Print body too (very helpful)
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        print(f"[cloud_chat] HTTPError {e.code}: {e.reason} body={body[:300]!r}")
        return ""
    except Exception as e:
        print(f"[cloud_chat] failed: {e!r}")
        return ""

def ollama_chat(user_text: str, memory_turns: List[Dict[str, str]]) -> str:
    """
    Local Ollama (generate endpoint).
    Env:
      OLLAMA_URL   default http://localhost:11434/api/generate
      OLLAMA_MODEL default llama3.1:8b
    """
    url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    # Simple prompt format
    context_lines = []
    for m in memory_turns[-8:]:
        r = m.get("role", "")
        c = (m.get("content") or "").strip()
        if c and r in ("user", "assistant"):
            context_lines.append(f"{r.upper()}: {c}")

    prompt = (
        "You are Gabriel, a helpful voice assistant. Be concise and practical.\n"
        + "\n".join(context_lines)
        + f"\nUSER: {user_text}\nASSISTANT:"
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.6, "top_p": 0.9, "num_predict": 160},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return (data.get("response") or "").strip()
    except Exception:
        return ""


def smart_chat(user_text: str, memory_turns: List[Dict[str, str]]) -> str:
    """
    Master switch:
      CHAT_MODE = local | cloud | hybrid
      hybrid = try cloud, then local
    """
    mode = os.getenv("CHAT_MODE", "hybrid").strip().lower()

    if mode == "cloud":
        return cloud_chat_openai(user_text, memory_turns) or ""
    if mode == "local":
        return ollama_chat(user_text, memory_turns) or ""

    # hybrid default
    out = cloud_chat_openai(user_text, memory_turns)
    if out:
        return out
    return ollama_chat(user_text, memory_turns) or ""