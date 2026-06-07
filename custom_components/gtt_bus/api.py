from __future__ import annotations

import asyncio
from datetime import datetime

import aiohttp

from .const import (
    API_MAX_ATTEMPTS,
    API_RETRY_DELAY_SECONDS,
    API_TIMEOUT_SECONDS,
    API_URL,
)
from .models import GttDeparture, parse_departure


class GttApiError(Exception):
    """Raised when the GTT Pirate API cannot be queried or parsed."""


class GttApiClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_get_departures(
        self, stop_id: str, now: datetime
    ) -> list[GttDeparture]:
        last_error: GttApiError | None = None
        for attempt in range(API_MAX_ATTEMPTS):
            try:
                request_time = now if attempt == 0 else _fresh_now(now)
                return await self._async_get_departures_once(stop_id, request_time)
            except GttApiError as err:
                last_error = err
                if attempt < API_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(API_RETRY_DELAY_SECONDS)

        if last_error is None:
            raise GttApiError(f"Could not fetch stop {stop_id}")
        raise last_error

    async def _async_get_departures_once(
        self, stop_id: str, now: datetime
    ) -> list[GttDeparture]:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS)

        try:
            async with self._session.get(
                API_URL, params={"stop": stop_id}, timeout=timeout
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GttApiError(f"Could not fetch stop {stop_id}: {err}") from err
        except ValueError as err:
            raise GttApiError(f"GTT API returned invalid JSON for stop {stop_id}") from err

        if not isinstance(payload, list):
            raise GttApiError(f"GTT API returned an unexpected payload for stop {stop_id}")

        departures: list[GttDeparture] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            departure = parse_departure(item, now)
            if departure is not None:
                departures.append(departure)

        return sorted(departures, key=lambda departure: departure.departure_at)


def _fresh_now(reference: datetime) -> datetime:
    return datetime.now(tz=reference.tzinfo) if reference.tzinfo else datetime.now()
