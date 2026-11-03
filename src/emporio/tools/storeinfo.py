"""Store facts tool: address, contact, today's date and whether the store is open."""

from datetime import time

from emporio.services.store import OPENING_HOURS, STORE_INFO, get_status, is_holiday
from emporio.tools.base import JsonDict, Tool, ToolInput
from emporio.tools.context import ToolContext

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class NoInput(ToolInput):
    pass


def _fmt(hours: tuple[time, time] | None) -> str:
    return "closed" if hours is None else f"{hours[0]:%H:%M}-{hours[1]:%H:%M}"


def _store_info(ctx: ToolContext) -> JsonDict:
    now = ctx.clock.now()
    status = get_status(now)
    closed_reason = None
    if not status.is_open:
        if is_holiday(now.date()):
            closed_reason = "HOLIDAY"
        elif OPENING_HOURS[now.weekday()] is None:
            closed_reason = "NON_BUSINESS_DAY"
        else:
            closed_reason = "OUTSIDE_HOURS"
    return {
        "name": STORE_INFO.name,
        "address": STORE_INFO.address,
        "phone": STORE_INFO.phone,
        "email": STORE_INFO.email,
        "today": now.date().isoformat(),
        "weekday": _WEEKDAYS[now.weekday()],
        "local_time": now.strftime("%H:%M"),
        "is_open_now": status.is_open,
        "closed_reason": closed_reason,
        "closes_at": status.closes_at.isoformat() if status.closes_at else None,
        "next_opens_at": status.next_opens_at.isoformat() if status.next_opens_at else None,
        "next_opens_weekday": (
            _WEEKDAYS[status.next_opens_at.weekday()] if status.next_opens_at else None
        ),
        "weekly_hours": {name: _fmt(OPENING_HOURS[i]) for i, name in enumerate(_WEEKDAYS)},
        "holidays_note": "Closed on national and Mato Grosso do Sul holidays.",
    }


def storeinfo_tools(ctx: ToolContext) -> list[Tool]:
    return [
        Tool(
            name="get_store_info",
            description=(
                "Store address, phone, email, weekly opening hours, today's date and whether "
                "the store is open right now (with next opening time when closed). Use it for "
                "any question about hours, location, contact or 'today'."
            ),
            input_model=NoInput,
            handler=lambda _args: _store_info(ctx),
        )
    ]
