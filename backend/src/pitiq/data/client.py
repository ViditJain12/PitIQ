"""FastF1 session loader with persistent disk cache and retry/backoff."""

import logging
import time
from pathlib import Path

import fastf1

logger = logging.getLogger(__name__)

# Resolved relative to the repo root regardless of cwd
_REPO_ROOT = Path(__file__).parents[4]  # …/PitIQ/
_CACHE_DIR = _REPO_ROOT / "data" / "raw" / "fastf1_cache"

_cache_enabled = False


def _ensure_cache() -> None:
    global _cache_enabled
    if not _cache_enabled:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(_CACHE_DIR))
        _cache_enabled = True


# Enable cache on module import
_ensure_cache()


def load_session(
    year: int,
    race_name: str,
    session_type: str,
    *,
    load_laps: bool = True,
    load_telemetry: bool = False,
    max_retries: int = 4,
    base_delay: float = 2.0,
) -> fastf1.core.Session:
    """Load a FastF1 session, retrying on transient network failures.

    Args:
        year: Championship year (e.g. 2024).
        race_name: Race name or partial name recognised by FastF1 (e.g. "Monza").
        session_type: "R" (race), "Q" (qualifying), "FP1", "FP2", "FP3", "S" (sprint).
        load_laps: Whether to call session.load(laps=True).
        load_telemetry: Whether to include telemetry in the session load (slow).
        max_retries: Maximum number of attempts before re-raising.
        base_delay: Initial retry delay in seconds; doubles each attempt.

    Returns:
        A loaded fastf1.core.Session object.

    Raises:
        Exception: The last exception after all retries are exhausted.
    """
    _ensure_cache()

    last_exc: Exception | None = None
    delay = base_delay

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Loading session: %d %s %s (attempt %d/%d)",
                year, race_name, session_type, attempt, max_retries,
            )
            session = fastf1.get_session(year, race_name, session_type)
            session.load(laps=load_laps, telemetry=load_telemetry, weather=False, messages=False)
            logger.info("Session loaded OK: %d %s %s", year, race_name, session_type)
            return session

        except Exception as exc:
            last_exc = exc
            # Don't retry on clearly non-transient errors
            if _is_fatal(exc):
                logger.error("Non-retryable error loading session: %s", exc)
                raise

            if attempt < max_retries:
                logger.warning(
                    "Attempt %d failed (%s: %s) — retrying in %.1fs",
                    attempt, type(exc).__name__, exc, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 60.0)  # cap at 60s
            else:
                logger.error(
                    "All %d attempts failed for %d %s %s",
                    max_retries, year, race_name, session_type,
                )

    assert last_exc is not None
    raise last_exc


def _is_fatal(exc: Exception) -> bool:
    """Return True for errors that retrying won't fix."""
    msg = str(exc).lower()
    fatal_fragments = (
        "invalid session",
        "no session",
        "not found",
        "keyerror",
        "valueerror",
    )
    if any(f in msg for f in fatal_fragments):
        return True
    # TypeError / AttributeError are almost always programming errors
    return isinstance(exc, (TypeError, AttributeError))
