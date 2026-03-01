import time
from .record import Recorder

class GestureAPI:
    def __init__(self, hw):
        self.hw = hw
        self.rec = Recorder()

    def connect(self):
        self.hw.connect()
        return True, "Glove connected."

    def calibrate(self):
        self.hw.calibrate()
        return True, "Calibration started."

    def start_record(self, label):
        self.hw.start_recording(label)
        path = self.rec.start(label)
        return True, f"Recording '{label}'", path

    def stop_record(self):
        self.hw.stop_recording()
        self.rec.stop()
        return True, "Recording stopped."

    def status(self):
        st = self.hw.get_status()
        return True, f"Glove connected={st.connected} transport={st.transport}", st

    def pump(self):
        reading = self.hw.poll_latest()
        if reading:
            reading = dict(reading)
            reading.setdefault("ts", time.time())
            reading.setdefault("source", getattr(self.hw, "transport_name", "unknown"))
            self.rec.write(reading)