from __future__ import annotations

import random
import time
from dataclasses import dataclass, field


@dataclass
class Backoff:
    """Exponential backoff with full jitter (AWS-style)."""

    initial: float = 1.0
    max_seconds: float = 60.0
    multiplier: float = 2.0
    _attempt: int = field(default=0, init=False)

    def reset(self) -> None:
        self._attempt = 0

    def next_delay(self) -> float:
        """Seconds to sleep before the next attempt."""
        cap = min(self.initial * (self.multiplier**self._attempt), self.max_seconds)
        self._attempt += 1
        # Full jitter in [0, cap]
        return random.uniform(0.0, cap)

    def peek_cap(self) -> float:
        return min(self.initial * (self.multiplier** max(0, self._attempt - 1)), self.max_seconds)
