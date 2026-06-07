from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import math
from typing import Any


@dataclass(frozen=True)
class GttDeparture:
    line: str
    scheduled_time: str
    realtime: bool
    departure_at: datetime
    minutes_until: int

    def as_attribute(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "scheduled_time": self.scheduled_time,
            "departure_at": self.departure_at.isoformat(),
            "minutes_until": self.minutes_until,
            "realtime": self.realtime,
        }


@dataclass(frozen=True)
class StopUpdate:
    departures: list[GttDeparture]
    has_data: bool
    stale: bool = False
    last_error: str | None = None
    last_successful_update: str | None = None


def successful_stop_update(
    departures: list[GttDeparture], updated_at: datetime
) -> StopUpdate:
    return StopUpdate(
        departures=departures,
        has_data=True,
        last_successful_update=updated_at.isoformat(),
    )


def failed_stop_update(
    error: Exception, previous: StopUpdate | None, updated_at: datetime | None = None
) -> StopUpdate:
    error_message = str(error) or error.__class__.__name__
    if previous is not None and previous.has_data:
        departures = previous.departures
        if updated_at is not None:
            departures = refresh_departure_relative_times(departures, updated_at)

        return StopUpdate(
            departures=departures,
            has_data=True,
            stale=True,
            last_error=error_message,
            last_successful_update=previous.last_successful_update,
        )

    return StopUpdate(
        departures=[],
        has_data=False,
        stale=True,
        last_error=error_message,
    )


def refresh_departure_relative_times(
    departures: list[GttDeparture], now: datetime
) -> list[GttDeparture]:
    return [
        replace(
            departure,
            minutes_until=max(
                0, math.ceil((departure.departure_at - now).total_seconds() / 60)
            ),
        )
        for departure in departures
    ]


def parse_departure(item: dict[str, Any], now: datetime) -> GttDeparture | None:
    line = str(item.get("line", "")).strip()
    scheduled_time = str(item.get("hour", "")).strip()
    if not line or not scheduled_time:
        return None

    parts = scheduled_time.split(":")
    if len(parts) not in (2, 3):
        return None

    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except (TypeError, ValueError):
        return None

    if minute < 0 or minute > 59 or second < 0 or second > 59 or hour < 0 or hour > 24:
        return None

    add_day = hour == 24
    if add_day:
        hour = 0

    departure_at = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if add_day or departure_at < now - timedelta(minutes=2):
        departure_at += timedelta(days=1)

    minutes_until = max(0, math.ceil((departure_at - now).total_seconds() / 60))
    realtime_raw = item.get("realtime", False)
    realtime = (
        realtime_raw
        if isinstance(realtime_raw, bool)
        else str(realtime_raw).strip().lower() in ("true", "1", "yes")
    )

    return GttDeparture(
        line=line,
        scheduled_time=scheduled_time,
        realtime=realtime,
        departure_at=departure_at,
        minutes_until=minutes_until,
    )
