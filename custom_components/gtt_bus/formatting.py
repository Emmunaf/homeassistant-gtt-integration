from __future__ import annotations

from .const import SENSOR_STATE_MAX_LENGTH
from .models import GttDeparture


def format_departure_summary(departures: list[GttDeparture]) -> str:
    if not departures:
        return "No departures"

    parts: list[str] = []
    for departure in departures:
        candidate = format_departure(departure)
        next_parts = [*parts, candidate]
        if len(" | ".join(next_parts)) > SENSOR_STATE_MAX_LENGTH:
            break
        parts.append(candidate)

    hidden_count = len(departures) - len(parts)
    if hidden_count:
        more = f"+{hidden_count} more"
        while parts and len(" | ".join([*parts, more])) > SENSOR_STATE_MAX_LENGTH:
            parts.pop()
            hidden_count += 1
            more = f"+{hidden_count} more"
        if len(more) <= SENSOR_STATE_MAX_LENGTH:
            parts.append(more)

    return " | ".join(parts)


def format_departure(departure: GttDeparture) -> str:
    relative_time = format_minutes(departure.minutes_until)
    if relative_time == "now":
        return f"{departure.line} now"
    return f"{departure.line} in {relative_time}"


def format_minutes(minutes: int) -> str:
    if minutes <= 0:
        return "now"
    if minutes == 1:
        return "1 min"
    return f"{minutes} min"
