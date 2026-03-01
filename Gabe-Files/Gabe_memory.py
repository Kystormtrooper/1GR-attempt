import json, os, time
from typing import Dict, Any, Tuple, Optional

MEM_PATH = os.path.join(os.path.dirname(__file__), "memory.json")

def load_memory() -> Dict[str, Any]:
    if not os.path.exists(MEM_PATH):
        return {"facts": {}, "updated": time.time()}
    try:
        with open(MEM_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"facts": {}, "updated": time.time()}

def save_memory(mem: Dict[str, Any]) -> None:
    mem["updated"] = time.time()
    with open(MEM_PATH, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)

def remember_fact(mem: Dict[str, Any], key: str, value: str) -> None:
    mem.setdefault("facts", {})
    mem["facts"][key.strip().lower()] = value.strip()
    save_memory(mem)

def forget_fact(mem: Dict[str, Any], key: str) -> bool:
    key = key.strip().lower()
    facts = mem.setdefault("facts", {})
    if key in facts:
        del facts[key]
        save_memory(mem)
        return True
    return False

def get_fact(mem: Dict[str, Any], key: str) -> Optional[str]:
    return mem.get("facts", {}).get(key.strip().lower())

def list_facts(mem: Dict[str, Any]) -> Dict[str, str]:
    return dict(mem.get("facts", {}))

def parse_remember(text: str) -> Optional[Tuple[str, str]]:

    t = text.strip()
    low = t.lower()

    if not low.startswith("remember"):
        return None

    # strip 'remember' / 'remember that'
    body = t[len("remember"):].strip()
    if body.lower().startswith("that "):
        body = body[5:].strip()

    for sep in [" is ", " = ", ": "]:
        if sep in body:
            k, v = body.split(sep, 1)
            k, v = k.strip(), v.strip()
            if k and v:
                return (k, v)
    return None

def parse_forget(text: str) -> Optional[str]:
    low = text.strip().lower()
    if low.startswith("forget "):
        return text.strip()[len("forget "):].strip()
    if low in ("forget", "delete memory", "clear memory"):
        return "__ALL__"
    return None
