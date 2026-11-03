"""Injectable clock, so tests and examples can pin "today"."""

from abc import ABC, abstractmethod
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("America/Campo_Grande")
DEFAULT_FIXED_TIME = time(10, 0)  # inside opening hours, so a pinned date reads as an open day


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """Current time, timezone-aware."""

    def today(self) -> date:
        return self.now().date()


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(STORE_TZ)


class FixedClock(Clock):
    def __init__(self, moment: datetime) -> None:
        self._moment = moment if moment.tzinfo else moment.replace(tzinfo=STORE_TZ)

    def now(self) -> datetime:
        return self._moment


def build_clock(store_today: date | None) -> Clock:
    """A fixed clock when STORE_TODAY is set, otherwise the system clock."""
    if store_today is None:
        return SystemClock()
    return FixedClock(datetime.combine(store_today, DEFAULT_FIXED_TIME, tzinfo=STORE_TZ))