from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class GloveStatus:
    connected: bool
    transport: str
    last_packet_ts: Optional[float] = None
    last_reading: Optional[Dict[str, Any]] = None