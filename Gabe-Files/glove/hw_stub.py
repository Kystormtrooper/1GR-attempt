import time
from .types import GloveStatus

class StubGlove:
    transport_name = "stub"

    def __init__(self):
        self.connected = False
        self.last_reading = None

    def connect(self):
        self.connected = True

    def calibrate(self):
        if not self.connected:
            raise RuntimeError("Glove not connected (stub).")

    def start_recording(self, label):
        if not self.connected:
            raise RuntimeError("Glove not connected (stub).")

    def stop_recording(self):
        if not self.connected:
            raise RuntimeError("Glove not connected (stub).")

    def get_status(self):
        return GloveStatus(
            connected=self.connected,
            transport="stub",
            last_packet_ts=time.time(),
            last_reading=self.last_reading,
        )

    def poll_latest(self):
        if not self.connected:
            return None
        # Fake sensor values (replace later with BLE)
        self.last_reading = {
            "flex": [4020, 3890, 4050, 3970],
            "gesture": None
        }
        return self.last_reading