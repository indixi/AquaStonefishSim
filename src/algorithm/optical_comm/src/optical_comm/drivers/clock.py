import time

class MonotonicClock:
    """Local elapsed time only; peers never exchange or compare absolute clocks."""
    def now(self):
        return time.monotonic()
