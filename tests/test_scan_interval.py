"""Tests intervalle de rafraîchissement et capteur diagnostic."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.optifamily.const import (
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    clamp_scan_interval,
    scan_interval_from_minutes,
)
from custom_components.optifamily.sensor import OptieFamilyLastRefreshSensor


def test_default_scan_interval_is_30_minutes() -> None:
    assert DEFAULT_SCAN_INTERVAL == 1800
    assert DEFAULT_SCAN_INTERVAL == 30 * 60


def test_scan_interval_bounds() -> None:
    assert MIN_SCAN_INTERVAL == 5 * 60
    assert MAX_SCAN_INTERVAL == 120 * 60
    assert MIN_SCAN_INTERVAL <= DEFAULT_SCAN_INTERVAL <= MAX_SCAN_INTERVAL


def test_clamp_scan_interval_bounds_and_fallback() -> None:
    assert clamp_scan_interval(60) == MIN_SCAN_INTERVAL
    assert clamp_scan_interval(10_000) == MAX_SCAN_INTERVAL
    assert clamp_scan_interval(1800) == 1800
    assert clamp_scan_interval(None) == DEFAULT_SCAN_INTERVAL
    assert clamp_scan_interval("nope") == DEFAULT_SCAN_INTERVAL
    assert clamp_scan_interval(900.7) == 900


def test_scan_interval_from_minutes() -> None:
    assert scan_interval_from_minutes(30) == 1800
    assert scan_interval_from_minutes(1) == MIN_SCAN_INTERVAL
    assert scan_interval_from_minutes(999) == MAX_SCAN_INTERVAL
    assert scan_interval_from_minutes(None) == DEFAULT_SCAN_INTERVAL
    assert scan_interval_from_minutes("x") == DEFAULT_SCAN_INTERVAL


def test_last_refresh_sensor_exposes_timestamp_and_interval() -> None:
    when = datetime(2026, 9, 3, 17, 30, tzinfo=UTC)
    coordinator = SimpleNamespace(
        last_update_success=when,
        scan_interval=1800,
        data=None,
    )
    entry = MagicMock()
    entry.entry_id = "entry-test"
    entry.data = {}

    sensor = OptieFamilyLastRefreshSensor(coordinator, entry)  # type: ignore[arg-type]

    assert sensor.native_value == when
    assert sensor.extra_state_attributes == {
        "intervalle_secondes": 1800,
        "intervalle_minutes": 30,
    }
    assert sensor._attr_unique_id == "entry-test_dernier_rafraichissement"
