import time

class LatencyTracker:
    def __init__(self):
        self.timestamps = {}

    def mark(self, label: str):
        self.timestamps[label] = time.time()

    def report(self):
        labels = list(self.timestamps.keys())
        results = {}

        for i in range(1, len(labels)):
            delta = (self.timestamps[labels[i]] - self.timestamps[labels[i - 1]]) * 1000
            results[f"{labels[i - 1]} → {labels[i]}"] = round(delta, 2)

        return results