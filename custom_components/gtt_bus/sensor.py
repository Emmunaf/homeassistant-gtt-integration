from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .api import GttApiClient
from .const import (
    ATTRIBUTION,
    DEPARTURE_SENSOR_COUNT,
    CONF_SCAN_INTERVAL,
    CONF_STOPS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .formatting import format_departure, format_departure_summary
from .models import GttDeparture, StopUpdate, failed_stop_update, successful_stop_update

_LOGGER = logging.getLogger(__name__)


class GttBusDataUpdateCoordinator(DataUpdateCoordinator[dict[str, StopUpdate]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: GttApiClient,
        stops: list[str],
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._client = client
        self._stops = stops

    async def _async_update_data(self) -> dict[str, StopUpdate]:
        now = dt_util.now()
        previous_data = self.data or {}
        results = await asyncio.gather(
            *(self._client.async_get_departures(stop_id, now) for stop_id in self._stops),
            return_exceptions=True,
        )

        updates: dict[str, StopUpdate] = {}
        for stop_id, result in zip(self._stops, results, strict=True):
            if isinstance(result, Exception):
                previous_update = previous_data.get(stop_id)
                updates[stop_id] = failed_stop_update(result, previous_update, now)
                if previous_update is not None and previous_update.has_data:
                    _LOGGER.debug(
                        "Unable to update GTT stop %s, keeping previous data: %s",
                        stop_id,
                        result,
                    )
                else:
                    _LOGGER.warning(
                        "Unable to update GTT stop %s and no previous data is available: %s",
                        stop_id,
                        result,
                    )
            else:
                updates[stop_id] = successful_stop_update(result, now)

        return updates


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = hass.data[DOMAIN][entry.entry_id]
    stops = entry.options.get(CONF_STOPS, entry.data[CONF_STOPS])
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    coordinator = GttBusDataUpdateCoordinator(hass, client, stops, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    entities: list[SensorEntity] = []
    for stop_id in stops:
        entities.append(GttBusStopSummarySensor(coordinator, entry, stop_id))
        entities.extend(
            GttBusDepartureSensor(coordinator, entry, stop_id, index)
            for index in range(DEPARTURE_SENSOR_COUNT)
        )

    async_add_entities(entities)


class GttBusBaseSensor(CoordinatorEntity[GttBusDataUpdateCoordinator], SensorEntity):
    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_icon = "mdi:bus-clock"

    def __init__(
        self,
        coordinator: GttBusDataUpdateCoordinator,
        entry: ConfigEntry,
        stop_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._stop_id = stop_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"stop_{stop_id}")},
            name=f"GTT Stop {stop_id}",
            manufacturer="GTT",
            model="Transit stop",
        )

    @property
    def available(self) -> bool:
        stop_update = self._stop_update
        return super().available and stop_update is not None and stop_update.has_data

    @property
    def _stop_update(self) -> StopUpdate | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._stop_id)


class GttBusStopSummarySensor(GttBusBaseSensor):
    def __init__(
        self,
        coordinator: GttBusDataUpdateCoordinator,
        entry: ConfigEntry,
        stop_id: str,
    ) -> None:
        super().__init__(coordinator, entry, stop_id)
        self._attr_name = "Departures"
        self._attr_unique_id = f"{entry.entry_id}_{stop_id}"

    @property
    def native_value(self) -> str | None:
        stop_update = self._stop_update
        if stop_update is None or not stop_update.has_data:
            return None
        return format_departure_summary(stop_update.departures)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attributes: dict[str, object] = {"stop_id": self._stop_id}
        stop_update = self._stop_update
        if stop_update is None:
            return attributes
        attributes["stale"] = stop_update.stale
        if stop_update.last_error is not None:
            attributes["last_error"] = stop_update.last_error
        if stop_update.last_successful_update is not None:
            attributes["last_successful_update"] = stop_update.last_successful_update
        if not stop_update.has_data:
            return attributes

        departures = stop_update.departures
        attributes["departure_count"] = len(departures)
        attributes["upcoming"] = [departure.as_attribute() for departure in departures]
        if not departures:
            return attributes

        next_departure = departures[0]
        attributes.update(
            {
                "next_line": next_departure.line,
                "next_scheduled_time": next_departure.scheduled_time,
                "next_departure_at": next_departure.departure_at.isoformat(),
                "minutes_until": next_departure.minutes_until,
                "realtime": next_departure.realtime,
            }
        )
        return attributes


class GttBusDepartureSensor(GttBusBaseSensor):
    def __init__(
        self,
        coordinator: GttBusDataUpdateCoordinator,
        entry: ConfigEntry,
        stop_id: str,
        index: int,
    ) -> None:
        super().__init__(coordinator, entry, stop_id)
        self._index = index
        self._attr_name = f"Departure {index + 1}"
        self._attr_unique_id = f"{entry.entry_id}_{stop_id}_departure_{index + 1}"

    @property
    def available(self) -> bool:
        return super().available and self._departure is not None

    @property
    def native_value(self) -> str | None:
        departure = self._departure
        if departure is None:
            return None
        return format_departure(departure)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attributes: dict[str, object] = {
            "stop_id": self._stop_id,
            "position": self._index + 1,
        }

        stop_update = self._stop_update
        if stop_update is not None:
            attributes["stale"] = stop_update.stale
            if stop_update.last_error is not None:
                attributes["last_error"] = stop_update.last_error
            if stop_update.last_successful_update is not None:
                attributes["last_successful_update"] = stop_update.last_successful_update

        departure = self._departure
        if departure is None:
            return attributes

        attributes.update(departure.as_attribute())
        return attributes

    @property
    def _departure(self) -> GttDeparture | None:
        stop_update = self._stop_update
        if stop_update is None or not stop_update.has_data:
            return None
        if self._index >= len(stop_update.departures):
            return None
        return stop_update.departures[self._index]
