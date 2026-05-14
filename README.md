# PitIQ

PitIQ is an F1 race strategy simulator that helps answer the question every pit wall is chasing: when should we stop, what tire should we fit, and how will the race change if everyone else reacts?

It combines historical Formula 1 timing data, driver-specific pace modeling, tire degradation curves, and reinforcement learning to turn pit strategy into an interactive decision tool.

## What You Can Do

**Test a strategy.** Choose a driver, circuit, starting tire, and pit plan, then simulate the race lap by lap to see projected lap times, tire behavior, stops, race time, and finishing position.

**Find a better strategy.** Run the optimizer to let an RL agent search for a faster pit plan while accounting for rival behavior, undercut windows, tire age, and track-specific pit loss.

**Compare against history.** Explore historical race conditions and check how simulated outcomes line up with real-world results.

**Watch the race unfold.** Replay the simulated race to see position changes, pit stops, and strategy swings lap by lap.

## Why PitIQ Is Different

PitIQ does not treat every driver as interchangeable. Each prediction is adjusted using a driver style profile built from historical data, including pace trends, tire preservation, braking aggression, throttle smoothness, wet-weather performance, and sector strengths.

That means a long stint for one driver can degrade differently than the same stint for another driver, even on the same compound at the same circuit.

## Modes

- **Sandbox:** Manually build a race strategy and inspect the projected outcome.
- **Optimizer:** Let the model recommend a strategy against a simulated 20-car grid.
- **Historical:** Review past races and compare model behavior with real results.

## Under the Hood

PitIQ uses FastF1 data from recent seasons, an XGBoost lap-time model, custom race simulation environments, PPO reinforcement learning agents, a FastAPI backend, and a React frontend.

The goal is not to perfectly recreate every bit of F1 chaos. The goal is to make strategy tradeoffs visible, testable, and fun to reason about.

---

## Running Locally

**Requirements:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

```bash
# Clone the repo
git clone ...
cd PitIQ

# Start the full stack (backend + frontend)
docker compose up --build
```

Open [http://localhost](http://localhost) in your browser.

To stop:
```bash
docker compose down
```
