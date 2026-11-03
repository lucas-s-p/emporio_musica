"""Static store facts and opening hours (policy sections 1 and 2)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache

import holidays


@dataclass(frozen=True)
class StoreInfo:
    name: str
    address: str
    phone: str
    email: str


# The manual shows two phone numbers and an email with and without accent. Assumption:
# use the official company data (section 1.2) and the accent-free email.
STORE_INFO = StoreInfo(
    name="Empório da Música",
    address="Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333",
    phone="(67) 3341-4444",
    email="contato@emporiodamusica.com.br",
)

# Monday = 0. None means closed.
OPENING_HOURS: dict[int, tuple[time, time] | None] = {
    0: (time(9), time(18)),
    1: (time(9), time(18)),
    2: (time(9), time(18)),
    3: (time(9), time(18)),
    4: (time(9), time(18)),
    5: (time(9), time(13)),
    6: None,
}


@lru_cache(maxsize=8)
def _holidays_of(year: int) -> holidays.HolidayBase:
    return holidays.country_holidays("BR", subdiv="MS", years=year)


def is_holiday(day: date) -> bool:
    """National and Mato Grosso do Sul holidays. Optional days (e.g. Carnival) are not included."""
    return day in _holidays_of(day.year)


@dataclass(frozen=True)
class StoreStatus:
    is_open: bool
    closes_at: datetime | None
    next_opens_at: datetime | None


def _hours_on(day: date, holiday_check: Callable[[date], bool]) -> tuple[time, time] | None:
    return None if holiday_check(day) else OPENING_HOURS[day.weekday()]


def get_status(now: datetime, holiday_check: Callable[[date], bool] = is_holiday) -> StoreStatus:
    """Whether the store is open at `now` and, if not, when it opens next.

    Opening is inclusive and closing exclusive: at 18:00 sharp on a weekday it is closed.
    """
    hours = _hours_on(now.date(), holiday_check)
    if hours and hours[0] <= now.time() < hours[1]:
        closes_at = datetime.combine(now.date(), hours[1], tzinfo=now.tzinfo)
        return StoreStatus(True, closes_at, None)

    for offset in range(0, 15):
        day = now.date() + timedelta(days=offset)
        day_hours = _hours_on(day, holiday_check)
        if not day_hours:
            continue
        opens_at = datetime.combine(day, day_hours[0], tzinfo=now.tzinfo)
        if opens_at > now:
            return StoreStatus(False, None, opens_at)
    return StoreStatus(False, None, None)