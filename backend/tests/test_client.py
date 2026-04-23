"""Tests for pitiq.data.client — run against real FastF1 cache (no mocking)."""

import time
import pytest
import fastf1

from pitiq.data.client import load_session, _CACHE_DIR


def test_cache_dir_exists():
    assert _CACHE_DIR.exists(), f"Cache dir not found: {_CACHE_DIR}"


def test_load_session_returns_session():
    s = load_session(2024, "Monza", "R")
    assert isinstance(s, fastf1.core.Session)


def test_load_session_has_laps():
    s = load_session(2024, "Monza", "R")
    assert len(s.laps) > 0


def test_cache_hit_is_fast():
    """Second call must complete well under 3s (cache, no network)."""
    load_session(2024, "Monza", "R")  # warm cache
    t0 = time.perf_counter()
    load_session(2024, "Monza", "R")
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0, f"Cache hit took {elapsed:.2f}s — expected < 3s"


def test_invalid_session_raises():
    with pytest.raises(Exception):
        load_session(2024, "Monza", "INVALID_TYPE")
