from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
import types
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "gtt_bus"


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {module_name} from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType("gtt_bus")
package.__path__ = [str(MODULE_ROOT)]
sys.modules.setdefault("gtt_bus", package)

_load_module("gtt_bus.const", MODULE_ROOT / "const.py")
models = _load_module("gtt_bus.models", MODULE_ROOT / "models.py")
formatting = _load_module("gtt_bus.formatting", MODULE_ROOT / "formatting.py")

GttDeparture = models.GttDeparture
failed_stop_update = models.failed_stop_update
parse_departure = models.parse_departure
successful_stop_update = models.successful_stop_update
format_departure_summary = formatting.format_departure_summary


class GttDepartureParsingTests(unittest.TestCase):
    def test_parse_departure_accepts_gtt_seconds_payload(self) -> None:
        now = datetime(2026, 6, 6, 14, 54, 30)

        departure = parse_departure(
            {"line": "2", "hour": "14:55:20", "realtime": True}, now
        )

        self.assertIsNotNone(departure)
        assert departure is not None
        self.assertEqual(departure.line, "2")
        self.assertEqual(departure.scheduled_time, "14:55:20")
        self.assertTrue(departure.realtime)
        self.assertEqual(departure.departure_at, datetime(2026, 6, 6, 14, 55, 20))
        self.assertEqual(departure.minutes_until, 1)

    def test_parse_departure_accepts_legacy_hour_minute_payload(self) -> None:
        now = datetime(2026, 6, 6, 14, 54, 30)

        departure = parse_departure(
            {"line": "64", "hour": "15:12", "realtime": "false"}, now
        )

        self.assertIsNotNone(departure)
        assert departure is not None
        self.assertEqual(departure.line, "64")
        self.assertFalse(departure.realtime)
        self.assertEqual(departure.departure_at, datetime(2026, 6, 6, 15, 12, 0))

    def test_parse_departure_rolls_after_midnight(self) -> None:
        now = datetime(2026, 6, 6, 23, 59, 0)

        departure = parse_departure(
            {"line": "2", "hour": "00:05:00", "realtime": True}, now
        )

        self.assertIsNotNone(departure)
        assert departure is not None
        self.assertEqual(departure.departure_at, datetime(2026, 6, 7, 0, 5, 0))
        self.assertEqual(departure.minutes_until, 6)

    def test_parse_departure_rejects_invalid_time(self) -> None:
        now = datetime(2026, 6, 6, 14, 54, 30)

        self.assertIsNone(
            parse_departure({"line": "2", "hour": "14:55:99", "realtime": True}, now)
        )


class GttDepartureFormattingTests(unittest.TestCase):
    def test_summary_includes_multiple_departures_for_one_stop(self) -> None:
        now = datetime(2026, 6, 6, 14, 54, 30)
        payload = [
            {"line": "2", "hour": "14:55:20", "realtime": True},
            {"line": "64", "hour": "15:12:47", "realtime": False},
            {"line": "2", "hour": "15:13:54", "realtime": True},
            {"line": "2", "hour": "15:28:35", "realtime": False},
            {"line": "64", "hour": "15:38:34", "realtime": True},
            {"line": "2", "hour": "15:44:35", "realtime": True},
        ]
        departures = [parse_departure(item, now) for item in payload]

        summary = format_departure_summary([item for item in departures if item])

        self.assertEqual(
            summary,
            "2 in 1 min | 64 in 19 min | 2 in 20 min | "
            "2 in 35 min | 64 in 45 min | 2 in 51 min",
        )

    def test_summary_never_exceeds_home_assistant_state_limit(self) -> None:
        now = datetime(2026, 6, 6, 14, 54, 30)
        departures = [
            GttDeparture(
                line=f"very-long-line-name-{index}",
                scheduled_time="15:00:00",
                realtime=True,
                departure_at=now,
                minutes_until=index,
            )
            for index in range(40)
        ]

        summary = format_departure_summary(departures)

        self.assertLessEqual(len(summary), 255)
        self.assertIn("more", summary)


class StopUpdateReliabilityTests(unittest.TestCase):
    def test_failed_update_keeps_previous_departures_as_stale_data(self) -> None:
        updated_at = datetime(2026, 6, 6, 14, 54, 30)
        departure = GttDeparture(
            line="2",
            scheduled_time="14:55:20",
            realtime=True,
            departure_at=datetime(2026, 6, 6, 14, 55, 20),
            minutes_until=1,
        )
        previous = successful_stop_update([departure], updated_at)

        update = failed_stop_update(RuntimeError("Network unreachable"), previous)

        self.assertTrue(update.has_data)
        self.assertTrue(update.stale)
        self.assertEqual(update.departures, [departure])
        self.assertEqual(update.last_successful_update, updated_at.isoformat())
        self.assertEqual(update.last_error, "Network unreachable")

    def test_failed_update_can_refresh_cached_relative_minutes(self) -> None:
        updated_at = datetime(2026, 6, 6, 14, 54, 30)
        departure = GttDeparture(
            line="2",
            scheduled_time="14:59:20",
            realtime=True,
            departure_at=datetime(2026, 6, 6, 14, 59, 20),
            minutes_until=5,
        )
        previous = successful_stop_update([departure], updated_at)

        update = failed_stop_update(
            RuntimeError("Network unreachable"), previous, datetime(2026, 6, 6, 14, 57, 0)
        )

        self.assertTrue(update.has_data)
        self.assertEqual(update.departures[0].minutes_until, 3)

    def test_failed_update_without_previous_data_has_no_displayable_data(self) -> None:
        update = failed_stop_update(RuntimeError("Network unreachable"), None)

        self.assertFalse(update.has_data)
        self.assertTrue(update.stale)
        self.assertEqual(update.departures, [])
        self.assertEqual(update.last_error, "Network unreachable")


if __name__ == "__main__":
    unittest.main()
