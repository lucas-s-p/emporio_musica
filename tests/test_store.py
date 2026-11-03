from datetime import date, datetime
from zoneinfo import ZoneInfo

from emporio.services.clock import STORE_TZ, FixedClock, SystemClock, build_clock
from emporio.services.store import STORE_INFO, get_status, is_holiday

TZ = ZoneInfo("America/Campo_Grande")


def at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


def test_open_on_weekday() -> None:
    status = get_status(at(2026, 11, 3, 10))  # Tuesday
    assert status.is_open
    assert status.closes_at == at(2026, 11, 3, 18)


def test_closing_time_is_exclusive() -> None:
    status = get_status(at(2026, 11, 3, 18))
    assert not status.is_open
    assert status.next_opens_at == at(2026, 11, 4, 9)


def test_before_opening() -> None:
    assert get_status(at(2026, 11, 3, 8, 59)).next_opens_at == at(2026, 11, 3, 9)


def test_saturday_closes_at_13() -> None:
    assert get_status(at(2026, 11, 7, 12, 59)).is_open
    status = get_status(at(2026, 11, 7, 13))
    assert not status.is_open
    assert status.next_opens_at == at(2026, 11, 9, 9)  # Monday


def test_sunday_closed() -> None:
    status = get_status(at(2026, 11, 8, 10))
    assert not status.is_open
    assert status.next_opens_at == at(2026, 11, 9, 9)


def test_holiday_is_closed_even_on_a_weekday() -> None:
    assert is_holiday(date(2026, 11, 2))  # Finados, a Monday
    status = get_status(at(2026, 11, 2, 10))
    assert not status.is_open
    assert status.next_opens_at == at(2026, 11, 3, 9)


def test_next_opening_skips_holiday_and_weekend() -> None:
    # Friday 2026-11-13 evening; Sunday 11-15 is a holiday too; next is Monday 11-16.
    assert get_status(at(2026, 11, 13, 19)).next_opens_at == at(2026, 11, 14, 9)
    assert get_status(at(2026, 11, 14, 14)).next_opens_at == at(2026, 11, 16, 9)


def test_custom_holiday_check() -> None:
    status = get_status(at(2026, 11, 3, 10), holiday_check=lambda d: d == date(2026, 11, 3))
    assert not status.is_open


def test_store_info_uses_official_contact() -> None:
    assert STORE_INFO.phone == "(67) 3341-4444"
    assert "ó" not in STORE_INFO.email


def test_build_clock() -> None:
    fixed = build_clock(date(2026, 2, 20))
    assert isinstance(fixed, FixedClock)
    assert fixed.today() == date(2026, 2, 20)
    assert get_status(fixed.now()).is_open  # 2026-02-20 is a Friday, pinned at 10:00
    assert isinstance(build_clock(None), SystemClock)
    assert SystemClock().now().tzinfo == STORE_TZ