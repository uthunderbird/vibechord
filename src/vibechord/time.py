"""Clock implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class SystemClock:
    """Real UTC clock."""

    def now(self) -> str:
        """Return the current UTC timestamp."""

        return datetime.now(UTC).isoformat()


@dataclass
class FakeClock:
    """Deterministic clock for tests and harnesses.

    Example:
        >>> clock = FakeClock()
        >>> first = clock.now()
        >>> second = clock.now()
        >>> first < second
        True
    """

    current: datetime = datetime(2026, 5, 23, tzinfo=UTC)
    step: timedelta = timedelta(seconds=1)

    def now(self) -> str:
        """Return the current timestamp and advance by one step."""

        value = self.current
        self.current = self.current + self.step
        return value.isoformat()
