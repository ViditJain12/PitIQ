"""One-time script: generate SVG polyline paths for all 29 circuits using FastF1 position data.

Run:
    python -m pitiq.data.generate_circuit_maps

Output: data/features/circuit_maps.json (committed to repo, ~50KB)
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import fastf1
import numpy as np

warnings.filterwarnings("ignore")

_REPO_ROOT  = Path(__file__).parents[4]
_CACHE_DIR  = _REPO_ROOT / "fastf1_cache"
_OUTPUT     = _REPO_ROOT / "data" / "features" / "circuit_maps.json"

_CACHE_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(_CACHE_DIR))

# Map our circuit names to FastF1 event names and the most recent year with data
_CIRCUIT_YEARS: dict[str, list[int]] = {
    "Bahrain Grand Prix":        [2021, 2022, 2023, 2024],
    "Saudi Arabian Grand Prix":  [2022, 2023, 2024],
    "Australian Grand Prix":     [2022, 2023, 2024],
    "Japanese Grand Prix":       [2022, 2023, 2024],
    "Chinese Grand Prix":        [2021, 2024],
    "Miami Grand Prix":          [2022, 2023, 2024],
    "Emilia Romagna Grand Prix": [2021, 2022, 2024],
    "Monaco Grand Prix":         [2021, 2022, 2023, 2024],
    "Canadian Grand Prix":       [2022, 2023, 2024],
    "Spanish Grand Prix":        [2021, 2022, 2023, 2024],
    "Austrian Grand Prix":       [2022, 2023, 2024],
    "Styrian Grand Prix":        [2021],
    "British Grand Prix":        [2021, 2022, 2023, 2024],
    "Hungarian Grand Prix":      [2021, 2022, 2023, 2024],
    "Belgian Grand Prix":        [2021, 2022, 2023, 2024],
    "Dutch Grand Prix":          [2021, 2022, 2023, 2024],
    "Italian Grand Prix":        [2021, 2022, 2023, 2024],
    "Azerbaijan Grand Prix":     [2021, 2022, 2023, 2024],
    "Singapore Grand Prix":      [2022, 2023, 2024],
    "United States Grand Prix":  [2021, 2022, 2023, 2024],
    "Mexico City Grand Prix":    [2021, 2022, 2023, 2024],
    "São Paulo Grand Prix":      [2021, 2022, 2023, 2024],
    "Las Vegas Grand Prix":      [2023, 2024],
    "Qatar Grand Prix":          [2023, 2024],
    "Abu Dhabi Grand Prix":      [2021, 2022, 2023, 2024],
    "Portuguese Grand Prix":     [2021],
    "French Grand Prix":         [2021, 2022],
    "Turkish Grand Prix":        [2021],
    "Russian Grand Prix":        [2021],
}


def _normalize_points(x: np.ndarray, y: np.ndarray, vb_w: int = 200, vb_h: int = 120) -> tuple[np.ndarray, np.ndarray, float]:
    """Scale X/Y to fit in viewBox preserving aspect ratio, centered."""
    x = x - x.min()
    y = y - y.min()
    scale = min(vb_w / (x.max() or 1), vb_h / (y.max() or 1)) * 0.92
    margin_x = (vb_w - x.max() * scale) / 2
    margin_y = (vb_h - y.max() * scale) / 2
    x_n = x * scale + margin_x
    y_n = y * scale + margin_y
    actual_w = x.max() * scale
    actual_h = y.max() * scale
    aspect = round(actual_w / actual_h, 3) if actual_h > 0 else 1.0
    return x_n, y_n, aspect


def _downsample(x: np.ndarray, y: np.ndarray, target: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Reduce points to ~target using uniform stride — keeps track shape clear."""
    n = len(x)
    if n <= target:
        return x, y
    step = max(1, n // target)
    idx = np.arange(0, n, step)
    # Always include last point to close the loop
    if idx[-1] != n - 1:
        idx = np.append(idx, n - 1)
    return x[idx], y[idx]


def _fetch_circuit_points(circuit: str, years: list[int]) -> dict | None:
    """Try years from most recent to oldest; return first successful result."""
    for year in reversed(years):
        try:
            print(f"  Trying {year}...", end=" ", flush=True)
            session = fastf1.get_session(year, circuit, "R")
            session.load(laps=True, telemetry=True, weather=False, messages=False)
            fastest = session.laps.pick_fastest()
            pos = fastest.get_pos_data()
            if pos is None or len(pos) < 50:
                print("no pos data")
                continue
            x = pos["X"].dropna().values.astype(float)
            y = pos["Y"].dropna().values.astype(float)
            if len(x) < 50:
                print("too few points")
                continue
            # FastF1 Y increases downward in some circuits; flip to SVG convention
            y = -y
            x_n, y_n, aspect = _normalize_points(x, y)
            x_d, y_d = _downsample(x_n, y_n)
            pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in zip(x_d, y_d))
            print(f"OK ({len(x_d)} pts, year {year})")
            return {"svg_points": pts, "viewBox": "0 0 200 120", "aspect_ratio": aspect, "year_used": year}
        except Exception as e:
            print(f"error: {e}")
            continue
    return None


def main() -> None:
    results: dict[str, dict] = {}
    failed: list[str] = []

    for circuit, years in _CIRCUIT_YEARS.items():
        print(f"\n[{circuit}]")
        data = _fetch_circuit_points(circuit, years)
        if data:
            results[circuit] = data
        else:
            print(f"  FAILED — no data found for {circuit}")
            failed.append(circuit)

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Saved {len(results)} circuits to {_OUTPUT}")
    if failed:
        print(f"✗ Failed: {failed}")


if __name__ == "__main__":
    main()
