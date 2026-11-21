"""Small per-process limit for abusive API traffic; edge limits remain required."""
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int = 120, window: int = 60, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> int:
        """Return seconds to wait (zero when allowed)."""
        now = self.clock()
        with self._lock:
            if len(self._hits) >= 10000 and key not in self._hits:
                for old_key in list(self._hits):
                    hits = self._hits[old_key]
                    if not hits or hits[-1] <= now - self.window:
                        del self._hits[old_key]
                if len(self._hits) >= 10000:
                    self._hits.pop(next(iter(self._hits)))
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, int(hits[0] + self.window - now) + 1)
            hits.append(now)
            return 0


limiter = RateLimiter()
