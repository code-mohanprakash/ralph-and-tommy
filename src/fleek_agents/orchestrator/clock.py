"""Time, passed in rather than read from the computer, so tests can skip two days instantly."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, by: timedelta) -> None:
        if by < timedelta(0):
            raise ValueError("Time only goes forward")
        self._now += by
