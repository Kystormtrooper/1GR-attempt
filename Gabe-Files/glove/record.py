import json
import os
import time

class Recorder:
    def __init__(self, live_path="data/live_readings.jsonl"):
        self.live_path = live_path
        os.makedirs(os.path.dirname(live_path), exist_ok=True)
        self.record_file = None
        self.label = None

    def write_live(self, reading):
        with open(self.live_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(reading) + "\n")

    def start(self, label):
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = f"data/record_{label}_{ts}.jsonl"
        self.record_file = open(path, "a", encoding="utf-8")
        self.label = label
        return path

    def stop(self):
        if self.record_file:
            self.record_file.close()
        self.record_file = None
        self.label = None

    def write(self, reading):
        self.write_live(reading)
        if self.record_file:
            obj = dict(reading)
            obj["label"] = self.label
            self.record_file.write(json.dumps(obj) + "\n")