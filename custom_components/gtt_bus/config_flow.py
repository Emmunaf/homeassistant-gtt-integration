from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_STOPS,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_STOP_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class GttBusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            data = _validate_user_input(user_input, errors)
            if data is not None:
                await self.async_set_unique_id(
                    f"gtt_bus:{','.join(sorted(data[CONF_STOPS]))}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_config_schema(),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return GttBusOptionsFlow(config_entry)


class GttBusOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            data = _validate_options_input(user_input, errors)
            if data is not None:
                return self.async_create_entry(title="", data=data)

        current_stops = self._config_entry.options.get(
            CONF_STOPS, self._config_entry.data[CONF_STOPS]
        )
        current_scan_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(current_stops, current_scan_interval),
            errors=errors,
        )


def _validate_user_input(
    user_input: dict[str, Any], errors: dict[str, str]
) -> dict[str, Any] | None:
    stops = _validate_stops(user_input.get(CONF_STOPS), errors)
    scan_interval = _validate_scan_interval(user_input.get(CONF_SCAN_INTERVAL), errors)
    if errors:
        return None

    return {
        CONF_NAME: str(user_input.get(CONF_NAME) or DEFAULT_NAME).strip() or DEFAULT_NAME,
        CONF_STOPS: stops,
        CONF_SCAN_INTERVAL: scan_interval,
    }


def _validate_options_input(
    user_input: dict[str, Any], errors: dict[str, str]
) -> dict[str, Any] | None:
    stops = _validate_stops(user_input.get(CONF_STOPS), errors)
    scan_interval = _validate_scan_interval(user_input.get(CONF_SCAN_INTERVAL), errors)
    if errors:
        return None

    return {
        CONF_STOPS: stops,
        CONF_SCAN_INTERVAL: scan_interval,
    }


def _validate_stops(value: Any, errors: dict[str, str]) -> list[str]:
    raw_stops = re.split(r"[\s,;]+", str(value or ""))
    stops: list[str] = []
    for stop_id in raw_stops:
        stop_id = stop_id.strip()
        if not stop_id:
            continue
        if not _STOP_PATTERN.fullmatch(stop_id):
            errors[CONF_STOPS] = "invalid_stop"
            return []
        if stop_id not in stops:
            stops.append(stop_id)

    if not stops:
        errors[CONF_STOPS] = "no_stops"

    return stops


def _validate_scan_interval(value: Any, errors: dict[str, str]) -> int:
    try:
        scan_interval = int(value or DEFAULT_SCAN_INTERVAL)
    except (TypeError, ValueError):
        errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
        return DEFAULT_SCAN_INTERVAL

    if scan_interval < MIN_SCAN_INTERVAL:
        errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"

    return scan_interval


def _config_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_STOPS): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.Coerce(int),
        }
    )


def _options_schema(stops: list[str], scan_interval: int) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_STOPS, default=", ".join(stops)): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.Coerce(int),
        }
    )
