"""Phase 5.3 — Comprehensive evaluation harness.

Runs 8 test scenarios (4 Sandbox + 4 Grid) x 4 policies x 20 episodes each.
Loads XGBoost and rival policy meta from JSON, generates 2 plots, saves results JSON.

CLI:  python -m pitiq.ml.evaluate
"""

from __future__ import annotations

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import json
import logging
import random
from pathlib import Path
from typing import Any, Callable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from stable_baselines3 import PPO

from pitiq.envs.grid import GridRaceEnv
from pitiq.envs.sandbox import SandboxRaceEnv
from pitiq.ml.compound_constants import COMPOUND_CLIFF_LAP

logging.basicConfig(level=logging.WARNING)

_REPO_ROOT   = Path(__file__).parents[4]
_MODELS_DIR  = _REPO_ROOT / "models"
_FIGURES_DIR = _MODELS_DIR / "figures"

_COMPOUNDS_ORDER = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]

# ── 2024 qualifying grids ─────────────────────────────────────────────────────

_BAHRAIN_GRID = [
    "VER", "LEC", "RUS", "SAI", "PER",
    "ALO", "NOR", "PIA", "HAM", "TSU",
    "STR", "MAG", "OCO", "GAS", "ALB",
    "BOT", "HUL", "ZHO", "SAR", "RIC",
]

_MONZA_GRID = [
    "LEC", "PIA", "NOR", "RUS", "VER",
    "SAI", "HAM", "ALO", "TSU", "STR",
    "PER", "MAG", "OCO", "GAS", "ALB",
    "BOT", "HUL", "ZHO", "SAR", "RIC",
]

_SPA_GRID = [
    "RUS", "NOR", "LEC", "SAI", "HAM",
    "PIA", "ALO", "TSU", "STR", "PER",
    "MAG", "OCO", "GAS", "ALB", "BOT",
    "HUL", "ZHO", "SAR", "RIC", "VER",
]

# Bahrain ZHO P15: swap ZHO (index 17) and ALB (index 14)
_BAHRAIN_ZHO_P15 = list(_BAHRAIN_GRID)
_BAHRAIN_ZHO_P15[14], _BAHRAIN_ZHO_P15[17] = _BAHRAIN_ZHO_P15[17], _BAHRAIN_ZHO_P15[14]

# Spa HAM P6: HAM at index 4 (P5) → swap with PIA at index 5 (P6)
_SPA_HAM_P6 = list(_SPA_GRID)
_SPA_HAM_P6[4], _SPA_HAM_P6[5] = _SPA_HAM_P6[5], _SPA_HAM_P6[4]

# ── Scenario definitions ──────────────────────────────────────────────────────

SANDBOX_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "Bahrain VER P1",
        "options": {
            "circuit":                    "Bahrain Grand Prix",
            "driver":                     "VER",
            "year":                       2024,
            "total_laps":                 57,
            "starting_position":          1,
            "starting_compound":          "SOFT",
            "two_compound_rule_enforced": True,
        },
    },
    {
        "name": "Bahrain ZHO P15",
        "options": {
            "circuit":                    "Bahrain Grand Prix",
            "driver":                     "ZHO",
            "year":                       2024,
            "total_laps":                 57,
            "starting_position":          15,
            "starting_compound":          "SOFT",
            "two_compound_rule_enforced": True,
        },
    },
    {
        "name": "Italian NOR P3",
        "options": {
            "circuit":                    "Italian Grand Prix",
            "driver":                     "NOR",
            "year":                       2024,
            "total_laps":                 53,
            "starting_position":          3,
            "starting_compound":          "MEDIUM",
            "two_compound_rule_enforced": True,
        },
    },
    {
        "name": "Belgian HAM P6",
        "options": {
            "circuit":                    "Belgian Grand Prix",
            "driver":                     "HAM",
            "year":                       2024,
            "total_laps":                 44,
            "starting_position":          6,
            "starting_compound":          "MEDIUM",
            "two_compound_rule_enforced": True,
        },
    },
]

GRID_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "Bahrain VER P1",
        "options": {
            "circuit":               "Bahrain Grand Prix",
            "year":                  2024,
            "total_laps":            57,
            "ego_driver":            "VER",
            "ego_starting_position": 1,
            "starting_grid":         _BAHRAIN_GRID,
            "starting_compounds":    {d: "SOFT" for d in _BAHRAIN_GRID},
            "weather": {"air_temp": 24.0, "track_temp": 38.0, "humidity": 45.0, "is_wet": False},
            "two_compound_rule_enforced": True,
        },
    },
    {
        "name": "Bahrain ZHO P15",
        "options": {
            "circuit":               "Bahrain Grand Prix",
            "year":                  2024,
            "total_laps":            57,
            "ego_driver":            "ZHO",
            "ego_starting_position": 15,
            "starting_grid":         _BAHRAIN_ZHO_P15,
            "starting_compounds":    {d: "SOFT" for d in _BAHRAIN_ZHO_P15},
            "weather": {"air_temp": 24.0, "track_temp": 38.0, "humidity": 45.0, "is_wet": False},
            "two_compound_rule_enforced": True,
        },
    },
    {
        "name": "Italian NOR P3",
        "options": {
            "circuit":               "Italian Grand Prix",
            "year":                  2024,
            "total_laps":            53,
            "ego_driver":            "NOR",
            "ego_starting_position": 3,
            "starting_grid":         _MONZA_GRID,
            "starting_compounds":    {d: "MEDIUM" for d in _MONZA_GRID},
            "two_compound_rule_enforced": True,
        },
    },
    {
        "name": "Belgian HAM P6",
        "options": {
            "circuit":               "Belgian Grand Prix",
            "year":                  2024,
            "total_laps":            44,
            "ego_driver":            "HAM",
            "ego_starting_position": 6,
            "starting_grid":         _SPA_HAM_P6,
            "starting_compounds":    {d: "MEDIUM" for d in _SPA_HAM_P6},
            "two_compound_rule_enforced": True,
        },
    },
]


# ── Sandbox policies ──────────────────────────────────────────────────────────

def _make_sandbox_ppo(model: PPO) -> Callable:
    def _fn(obs: np.ndarray, _env: SandboxRaceEnv) -> int:
        action, _ = model.predict(obs, deterministic=True)
        return int(action)
    return _fn


def _cliff_pit(obs: np.ndarray, _env: SandboxRaceEnv) -> int:
    tire_age     = float(obs[6])
    compound_idx = int(obs[1:6].argmax())
    compound     = _COMPOUNDS_ORDER[compound_idx]
    cliff        = COMPOUND_CLIFF_LAP.get(compound, 999)
    return 3 if tire_age >= cliff else 0


def _never_pit(obs: np.ndarray, _env: SandboxRaceEnv) -> int:
    return 0


def _sandbox_random(obs: np.ndarray, env: SandboxRaceEnv) -> int:
    return int(env.action_space.sample())


# ── Grid policies ─────────────────────────────────────────────────────────────

def _make_grid_ppo(model: PPO) -> Callable:
    def _fn(obs: np.ndarray, _lap: int) -> int:
        action, _ = model.predict(obs, deterministic=True)
        return int(action)
    return _fn


def _make_sandbox_ppo_in_grid(model: PPO) -> Callable:
    """Run 13-dim sandbox PPO inside 25-dim grid env by slicing obs."""
    def _fn(obs: np.ndarray, _lap: int) -> int:
        action, _ = model.predict(obs[:13], deterministic=True)
        return int(action)
    return _fn


def _fixed_lap18(obs: np.ndarray, lap_num: int) -> int:
    return 3 if lap_num == 18 else 0


def _grid_random(obs: np.ndarray, _lap: int) -> int:
    return random.randint(0, 3)


# ── Episode runners ───────────────────────────────────────────────────────────

def _run_sandbox_episode(policy_fn: Callable, options: dict, seed: int) -> dict:
    env = SandboxRaceEnv()
    obs, _ = env.reset(seed=seed, options=options)
    total_reward = 0.0
    terminated = truncated = False
    info: dict = {}
    while not (terminated or truncated):
        obs, reward, terminated, truncated, info = env.step(policy_fn(obs, env))
        total_reward += reward
    return {
        "reward":         total_reward,
        "final_position": info.get("position", 20),
        "race_time":      info.get("cumulative_race_time", 0.0),
    }


def _run_grid_episode(policy_fn: Callable, options: dict, seed: int) -> dict:
    env = GridRaceEnv()
    obs, _ = env.reset(seed=seed, options=options)
    total_reward = 0.0
    terminated = truncated = False
    lap_num = 1
    info: dict = {}
    while not (terminated or truncated):
        action = policy_fn(obs, lap_num)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        lap_num += 1
    return {
        "reward":         total_reward,
        "final_position": info.get("ego_position", 20),
        "race_time":      info.get("ego_cumulative_time", 0.0),
    }


def _aggregate(rows: list[dict], starting_position: int) -> dict:
    rewards    = [r["reward"]         for r in rows]
    positions  = [r["final_position"] for r in rows]
    times      = [r["race_time"]      for r in rows]
    pos_gained = [starting_position - p for p in positions]
    return {
        "mean_reward":      float(np.mean(rewards)),
        "std_reward":       float(np.std(rewards)),
        "mean_position":    float(np.mean(positions)),
        "std_position":     float(np.std(positions)),
        "mean_race_time_s": float(np.mean(times)),
        "win_rate":         float(sum(1 for p in positions if p == 1) / len(positions)),
        "mean_pos_gained":  float(np.mean(pos_gained)),
    }


def _eval_sandbox(policy_fn: Callable, options: dict, n: int = 20) -> dict:
    rows = [_run_sandbox_episode(policy_fn, options, seed=i) for i in range(n)]
    return _aggregate(rows, options["starting_position"])


def _eval_grid(policy_fn: Callable, options: dict, n: int = 20) -> dict:
    rows = [_run_grid_episode(policy_fn, options, seed=i) for i in range(n)]
    return _aggregate(rows, options["ego_starting_position"])


# ── Plots ─────────────────────────────────────────────────────────────────────

def _style_ax(ax: plt.Axes) -> None:
    ax.set_facecolor("#0d1117")
    ax.tick_params(colors="white")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color("white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")


def _plot_position_gains(all_results: dict, out: Path) -> None:
    scenario_names   = [s["name"] for s in SANDBOX_SCENARIOS]
    sandbox_policies = ["PPO Sandbox", "Cliff-pit", "Never-pit", "Random"]
    grid_policies    = ["PPO Grid", "PPO Sandbox", "Fixed lap-18", "Random"]
    colors = ["#e8002d", "#1e90ff", "#ff8800", "#888888"]
    x = np.arange(len(scenario_names))
    w = 0.18

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.patch.set_facecolor("#0d1117")

    for ax_idx, (env_type, policy_keys) in enumerate(
        [("sandbox", sandbox_policies), ("grid", grid_policies)]
    ):
        ax = axes[ax_idx]
        for p_idx, policy_name in enumerate(policy_keys):
            gains = [
                all_results.get(f"{env_type}|{sn}|{policy_name}", {}).get("mean_pos_gained", 0.0)
                for sn in scenario_names
            ]
            bars = ax.bar(
                x + (p_idx - 1.5) * w, gains, w,
                label=policy_name, color=colors[p_idx], alpha=0.9, edgecolor="#ffffff44",
            )
            ax.bar_label(bars, labels=[f"{g:+.1f}" for g in gains],
                         padding=3, fontsize=7, color="white")
        ax.axhline(0, color="white", lw=0.5, alpha=0.4)
        ax.set_xticks(x)
        ax.set_xticklabels(scenario_names, rotation=15, ha="right", fontsize=8)
        ax.set_ylabel("Mean Positions Gained (↑ better)")
        ax.set_title(f"{env_type.capitalize()} Mode — Positions Gained from Start")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.2, axis="y", color="white")
        _style_ax(ax)

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Position gains → {out}")


def _plot_reward_comparison(all_results: dict, out: Path) -> None:
    scenario_names   = [s["name"] for s in SANDBOX_SCENARIOS]
    sandbox_policies = ["PPO Sandbox", "Cliff-pit", "Never-pit", "Random"]
    grid_policies    = ["PPO Grid", "PPO Sandbox", "Fixed lap-18", "Random"]
    colors = ["#e8002d", "#1e90ff", "#ff8800", "#888888"]
    x = np.arange(len(scenario_names))
    w = 0.18

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.patch.set_facecolor("#0d1117")

    for ax_idx, (env_type, policy_keys) in enumerate(
        [("sandbox", sandbox_policies), ("grid", grid_policies)]
    ):
        ax = axes[ax_idx]
        for p_idx, policy_name in enumerate(policy_keys):
            rewards = [
                all_results.get(f"{env_type}|{sn}|{policy_name}", {}).get("mean_reward", 0.0)
                for sn in scenario_names
            ]
            bars = ax.bar(
                x + (p_idx - 1.5) * w, rewards, w,
                label=policy_name, color=colors[p_idx], alpha=0.9, edgecolor="#ffffff44",
            )
            ax.bar_label(bars, labels=[f"{r:+.1f}" for r in rewards],
                         padding=3, fontsize=7, color="white")
        ax.axhline(0, color="white", lw=0.5, alpha=0.4)
        ax.set_xticks(x)
        ax.set_xticklabels(scenario_names, rotation=15, ha="right", fontsize=8)
        ax.set_ylabel("Mean Episode Reward (20 eps)")
        ax.set_title(f"{env_type.capitalize()} Mode — Reward Comparison")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.2, axis="y", color="white")
        _style_ax(ax)

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Reward comparison → {out}")


# ── Output helpers ────────────────────────────────────────────────────────────

def _print_table(scenario_name: str, policy_results: dict[str, dict]) -> None:
    print(f"\n=== {scenario_name} ===")
    hdr = (
        f"{'Policy':<20} | {'Reward':>8} ± {'SD':>5}"
        f" | {'Pos':>5} ± {'SD':>4}"
        f" | {'Race(s)':>8} | {'WinRate':>7} | {'PosGain':>7}"
    )
    print(hdr)
    print("-" * len(hdr))
    for policy_name, m in policy_results.items():
        print(
            f"{policy_name:<20} | {m['mean_reward']:>+8.2f} ± {m['std_reward']:>5.2f}"
            f" | {m['mean_position']:>5.1f} ± {m['std_position']:>4.2f}"
            f" | {m['mean_race_time_s']:>8.1f} | {m['win_rate']:>7.2f}"
            f" | {m['mean_pos_gained']:>+7.1f}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 64)
    print("  Phase 5.3 — PitIQ Evaluation Harness")
    print("  8 scenarios × 4 policies × 20 episodes = 640 episodes")
    print("=" * 64)

    # Load PPO models
    print("\nLoading models...")
    sandbox_ppo = PPO.load(_MODELS_DIR / "ppo_sandbox_best.zip")
    grid_ppo    = PPO.load(_MODELS_DIR / "ppo_grid_best.zip")
    print(f"  Sandbox PPO: {_MODELS_DIR / 'ppo_sandbox_best.zip'}")
    print(f"  Grid PPO:    {_MODELS_DIR / 'ppo_grid_best.zip'}")

    # Load meta JSONs (not hardcoded — read from disk)
    xgb_baseline_meta = json.loads((_MODELS_DIR / "xgb_baseline_meta.json").read_text())
    xgb_styled_meta   = json.loads((_MODELS_DIR / "xgb_styled_meta.json").read_text())
    rival_meta        = json.loads((_MODELS_DIR / "rival_pit_policy_meta.json").read_text())

    # Policy factories
    sandbox_policies: dict[str, Callable] = {
        "PPO Sandbox": _make_sandbox_ppo(sandbox_ppo),
        "Cliff-pit":   _cliff_pit,
        "Never-pit":   _never_pit,
        "Random":      _sandbox_random,
    }
    grid_policies: dict[str, Callable] = {
        "PPO Grid":     _make_grid_ppo(grid_ppo),
        "PPO Sandbox":  _make_sandbox_ppo_in_grid(sandbox_ppo),
        "Fixed lap-18": _fixed_lap18,
        "Random":       _grid_random,
    }

    all_results: dict[str, dict] = {}

    # ── Sandbox evaluation ─────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  SANDBOX EVALUATION (20 episodes each)")
    print("=" * 64)

    sandbox_by_scenario: dict[str, dict] = {}
    for scenario in SANDBOX_SCENARIOS:
        scen_name = scenario["name"]
        policy_results: dict[str, dict] = {}
        for policy_name, policy_fn in sandbox_policies.items():
            m = _eval_sandbox(policy_fn, scenario["options"], n=20)
            policy_results[policy_name] = m
            all_results[f"sandbox|{scen_name}|{policy_name}"] = m
        sandbox_by_scenario[scen_name] = policy_results
        _print_table(scen_name, policy_results)

    # ── Grid evaluation ────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  GRID EVALUATION (20 episodes each)")
    print("=" * 64)

    grid_by_scenario: dict[str, dict] = {}
    for scenario in GRID_SCENARIOS:
        scen_name = scenario["name"]
        policy_results = {}
        for policy_name, policy_fn in grid_policies.items():
            m = _eval_grid(policy_fn, scenario["options"], n=20)
            policy_results[policy_name] = m
            all_results[f"grid|{scen_name}|{policy_name}"] = m
        grid_by_scenario[scen_name] = policy_results
        _print_table(scen_name, policy_results)

    # ── Plots ──────────────────────────────────────────────────────────────────
    print("\nGenerating plots...")
    _plot_position_gains(all_results, _FIGURES_DIR / "eval_position_gains.png")
    _plot_reward_comparison(all_results, _FIGURES_DIR / "eval_reward_comparison.png")

    # ── Save JSON ──────────────────────────────────────────────────────────────
    bm = xgb_baseline_meta["metrics"]
    sm = xgb_styled_meta["metrics"]

    output: dict[str, Any] = {
        "sandbox": {s["name"]: sandbox_by_scenario[s["name"]] for s in SANDBOX_SCENARIOS},
        "grid":    {s["name"]: grid_by_scenario[s["name"]]    for s in GRID_SCENARIOS},
        "xgb_baseline": {
            "mae":        bm["mae"],
            "stable_mae": bm["stable_mae"],
            "sparse_mae": bm["sparse_mae"],
        },
        "xgb_styled": {
            "mae":        sm["mae"],
            "stable_mae": sm["stable_mae"],
            "sparse_mae": sm["sparse_mae"],
        },
        "rival_policy": {
            "auc_roc":          rival_meta["auc_roc_test"],
            "avg_precision":    rival_meta["avg_precision_test"],
            "precision_at_030": rival_meta["precision_at_030"],
            "recall_at_030":    rival_meta["recall_at_030"],
        },
    }

    out_json = _MODELS_DIR / "evaluation_results.json"
    out_json.write_text(json.dumps(output, indent=2))
    print(f"\n  Results JSON → {out_json}")

    print("\n" + "=" * 64)
    print("  Phase 5.3 evaluation complete.")
    print(f"  models/evaluation_results.json")
    print(f"  models/figures/eval_position_gains.png")
    print(f"  models/figures/eval_reward_comparison.png")
    print("=" * 64)


if __name__ == "__main__":
    main()
