from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class Backoff:
    """
    Exponential backoff with jitter and a minimum delay.

    This prevents tight reconnect loops that can consume high CPU
    when the backend/websocket is unavailable.
    """

    initial: float = 1.0
    max_seconds: float = 60.0
    multiplier: float = 2.0
    min_seconds: float = 1.0
    _attempt: int = field(default=0, init=False)

    def reset(self) -> None:
        """Reset retry attempt counter after successful connection."""
        self._attempt = 0

    def next_delay(self) -> float:
        """Seconds to sleep before the next reconnect attempt."""
        cap = min(
            self.initial * (self.multiplier ** self._attempt),
            self.max_seconds,
        )

        self._attempt += 1

        # Ensure delay is never too small.
        if cap <= self.min_seconds:
            return self.min_seconds

        # Jitter between min_seconds and cap.
        return random.uniform(self.min_seconds, cap)

    def peek_cap(self) -> float:
        """Current capped delay value for logging/debugging."""
        return min(
            self.initial * (self.multiplier ** max(0, self._attempt - 1)),
            self.max_seconds,
        )