# CMA-ES + Modal Heuristic Tuning Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CMA-ES tuning framework that runs the CMA-ES outer loop locally and dispatches per-candidate fitness evaluations to parallel Modal containers, producing a tuned `HeuristicConfig` that ideally beats v1.5G's stock config on a fixed multi-opponent panel.

**Architecture:** Single Modal app file (`src/tools/modal_tuner.py`) holds the `@app.local_entrypoint() main()` (CMA-ES loop on user's machine) AND the `@app.function evaluate_fitness(...)` (one container per candidate, dispatched via `.starmap()`). Pure-Python `ParamSpace` module (`src/tools/heuristic_tuner_param_space.py`) handles encode/decode of `HeuristicConfig ↔ np.ndarray`. Each container runs sanity gate + fitness games for one candidate, returns a JSON dict. Local entrypoint aggregates results and writes a per-run output directory.

**Tech Stack:** Python 3.13, `cma` (CMA-ES), `modal>=1.4.2` (cloud parallelism), `scipy`/`numpy` (already in deps), `kaggle_environments` (already in deps), `pytest` for tests.

**Source spec:** `docs/superpowers/specs/2026-05-02-cma-es-tuning-framework-design.md` (signed off 2026-05-02).

---

## Pre-flight context for the implementing engineer

You are implementing a CMA-ES hyperparameter tuner for an Orbit Wars Kaggle competition agent. Critical things to know that aren't in the code:

1. **The `HeuristicConfig` dataclass at `src/orbit_wars/heuristic/config.py` is frozen + slots.** It has 48 numeric fields and 2 booleans. Construct via `HeuristicConfig(**dict_of_field_values)`. Use `dataclasses.fields(HeuristicConfig)` to introspect; never hand-list fields.

2. **The agent function signature has a config-arg trap.** `src/orbit_wars/heuristic/strategy.py:agent(obs, config=None)`. When called by `kaggle_environments.env.run`, the second arg is the env config Struct, NOT a HeuristicConfig. The agent guards with `isinstance(config, HeuristicConfig)` and falls back to default. To pass a candidate config, wrap the agent in a closure with explicit `obs` parameter (see `make_configured_agent` in Task 4). NEVER write a closure with `*args, **kwargs` — `kaggle_environments` calls it via `inspect.signature` and will see 0 required params and call it with NO args.

3. **`kaggle_environments`' env consumes Python's global random state.** Within a single Python process, identical configs on identical env seeds can produce different outcomes depending on stream position. **Modal container isolation solves this for free** — each container is a fresh process. We exploit this by calling `random.seed(GLOBAL_TUNER_SEED)` ONCE at the top of `evaluate_fitness` inside every container.

4. **Cost is real.** Your test runs that hit Modal cost actual dollars from the user's $60 credit. The `--smoke` profile is bounded at <$0.10. Anything bigger needs explicit cost-confirm.

5. **Working directory is `/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars`.** Use absolute paths in commands when in doubt. Run all Python commands via `uv run`.

---

## File structure

**Create:**
- `src/tools/heuristic_tuner_param_space.py` — ParamSpace table + `encode()` / `decode()` / `validate_param_space()`. Pure Python; no Modal/heavy imports. Importable from both the local entrypoint and inside Modal containers.
- `src/tools/modal_tuner.py` — Modal app: image build, `@app.function evaluate_fitness`, `@app.local_entrypoint() main()`. Also contains `evaluate_fitness_local` (the same body, reusable by tests) and `run_one_game` helper.
- `tests/test_heuristic_tuner.py` — pytest tests covering ParamSpace coverage, encode/decode round-trip, and a local-only smoke of `evaluate_fitness_local`.

**Modify:**
- `pyproject.toml` — add `cma>=3.3.0` to `[project.dependencies]`.

**Do NOT touch:**
- `src/main.py`
- `src/orbit_wars/heuristic/*` (config, strategy, etc.)
- `src/orbit_wars/opponents/*`
- Any other production code.

**Output target (created at runtime, not in source):**
- `docs/research_documents/tuning_runs/<UTC-ISO-timestamp>/` containing `config.json`, `generations.jsonl`, `best_config.py`, `final_report.md`.

---

## Task 1: Add `cma` dependency and verify install

**Files:**
- Modify: `pyproject.toml`

- [x] **Step 1: Read pyproject.toml dependencies section to find insertion point**

Run: `grep -n "^dependencies = \[" pyproject.toml`

Note the line number. The dependencies list ends at the line containing `"modal>=1.4.2",`.

- [x] **Step 2: Add `cma>=3.3.0` to dependencies**

Insert immediately above the closing `]` of the `dependencies` list. After edit, verify via:
Run: `grep -A 30 "^dependencies = \[" pyproject.toml | grep cma`
Expected: `    "cma>=3.3.0",`

- [x] **Step 3: Sync the lockfile and install**

Run: `uv sync`
Expected: completes without errors, downloads cma wheel.

- [x] **Step 4: Verify cma is importable**

Run: `uv run python -c "import cma; print(cma.__version__)"`
Expected: prints a version like `3.3.0` or higher (anything ≥3.3.0). Should NOT raise ImportError.

- [x] **Step 5: Commit**

```bash
git status -s  # MUST run first per CLAUDE.md — verify only pyproject.toml + uv.lock are staged
git add pyproject.toml uv.lock
git commit -m "deps: add cma>=3.3.0 for Phase 3 CMA-ES tuning framework"
```

If `git status -s` shows other files staged from parallel GitHub Desktop work, `git reset HEAD <file>` to unstage them BEFORE committing.

---

## Task 2: ParamSpace coverage test (failing)

**Files:**
- Create: `tests/test_heuristic_tuner.py`

- [x] **Step 1: Create the failing test file**

```python
"""Tests for the CMA-ES heuristic tuning framework.

These tests run locally (no Modal calls). They validate:
1. ParamSpace covers every numeric HeuristicConfig field.
2. encode/decode round-trip preserves all field values.
3. evaluate_fitness_local runs end-to-end on a tiny budget.

Modal end-to-end testing is a manual `--smoke` run (see plan Task 12) — not in
pytest because it costs real money against the user's Modal credit.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from orbit_wars.heuristic.config import HeuristicConfig
from tools.heuristic_tuner_param_space import (
    PARAM_SPACE,
    decode,
    encode,
    validate_param_space,
)


class TestParamSpaceCoverage:
    def test_param_space_covers_every_numeric_field(self) -> None:
        """Adding a new HeuristicConfig field must fail the test until its bound is added.

        Per spec deliverable #2: derive field list from `dataclasses.fields`,
        not by hand-enumeration.
        """
        validate_param_space()  # raises if any numeric field missing from PARAM_SPACE

    def test_param_space_excludes_booleans(self) -> None:
        """Bools (`reinforce_enabled`, `use_hungarian_offense`) are pinned, not tuned."""
        bool_fields = [f.name for f in fields(HeuristicConfig)
                       if f.type in (bool, "bool")]
        assert bool_fields, "expected at least one bool field in HeuristicConfig"
        for name in bool_fields:
            assert name not in PARAM_SPACE, f"{name} is bool — should be pinned, not in PARAM_SPACE"

    def test_param_space_bound_tuples_are_valid(self) -> None:
        """Each entry must be (lower, upper, is_int) with lower < upper."""
        for name, bounds in PARAM_SPACE.items():
            assert len(bounds) == 3, f"{name}: bounds must be (lower, upper, is_int)"
            lower, upper, is_int = bounds
            assert lower < upper, f"{name}: lower ({lower}) must be < upper ({upper})"
            assert isinstance(is_int, bool), f"{name}: is_int must be bool"
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_heuristic_tuner.py -v`
Expected: ImportError or ModuleNotFoundError on `from tools.heuristic_tuner_param_space import ...`. Tests cannot collect.

---

## Task 3: ParamSpace module — minimum to pass coverage tests

**Files:**
- Create: `src/tools/heuristic_tuner_param_space.py`

- [x] **Step 1: Create the module with PARAM_SPACE table for all 48 numeric fields**

Create file with this exact content (the bounds carry over from `docs/research_documents/ParamSpace_meta.md` which the user researched in Phase 3 brainstorm):

```python
"""ParamSpace table for CMA-ES tuning of HeuristicConfig.

48 numeric fields. Each entry is (lower, upper, is_int).

Booleans (`reinforce_enabled`, `use_hungarian_offense`) are NOT in the table —
they're pinned at v1.5G defaults per the spec.

Bound philosophy (from ParamSpace_meta.md): wide enough to let CMA-ES explore
qualitatively different strategies, but constrained by gameplay sanity (e.g.
min_launch >= 1; multipliers >= 0; turn-counters within episode length 500).
"""

from __future__ import annotations

from dataclasses import fields

import numpy as np

from orbit_wars.heuristic.config import HeuristicConfig

__all__ = [
    "PARAM_SPACE",
    "NUMERIC_FIELDS",
    "INT_DIM_INDICES",
    "encode",
    "decode",
    "validate_param_space",
]

# (lower, upper, is_int) per field — 48 entries
PARAM_SPACE: dict[str, tuple[float, float, bool]] = {
    # ----- Time horizons -----
    "sim_horizon": (40, 200, True),
    "route_search_horizon": (20, 120, True),

    # ----- Mission cost weights -----
    "attack_cost_turn_weight": (0.1, 1.5, False),
    "snipe_cost_turn_weight": (0.1, 1.5, False),
    "defense_cost_turn_weight": (0.1, 1.5, False),
    "reinforce_cost_turn_weight": (0.1, 1.5, False),

    # ----- Value multipliers -----
    "static_neutral_value_mult": (0.3, 3.0, False),
    "static_hostile_value_mult": (0.3, 3.0, False),
    "rotating_opening_value_mult": (0.2, 2.5, False),
    "hostile_target_value_mult": (0.5, 3.5, False),
    "opening_hostile_target_value_mult": (0.3, 3.0, False),
    "safe_neutral_value_mult": (0.3, 2.5, False),
    "contested_neutral_value_mult": (0.2, 2.0, False),
    "early_neutral_value_mult": (0.3, 2.5, False),
    "comet_value_mult": (0.1, 2.0, False),
    "reinforce_value_mult": (0.5, 3.0, False),

    # ----- Send margins -----
    "safety_margin": (0, 5, True),
    "home_reserve": (0, 10, True),
    "min_launch": (5, 50, True),
    "defense_buffer": (0, 8, True),

    # ----- Endgame -----
    "total_war_remaining_turns": (15, 100, True),
    "late_remaining_turns": (20, 120, True),
    "very_late_remaining_turns": (10, 60, True),
    "late_immediate_ship_value": (0.1, 2.0, False),
    "elimination_bonus": (5.0, 40.0, False),
    "weak_enemy_threshold": (10, 100, True),

    # ----- Reinforce mission -----
    "reinforce_min_production": (0, 10, True),
    "reinforce_max_travel_turns": (5, 60, True),
    "reinforce_safety_margin": (0, 8, True),
    "reinforce_max_source_fraction": (0.2, 0.95, False),
    "reinforce_min_future_turns": (10, 100, True),
    "reinforce_hold_lookahead": (5, 60, True),

    # ----- Time budget -----
    "soft_act_deadline_fraction": (0.5, 0.95, False),
    "heavy_route_planet_limit": (8, 80, True),

    # ----- Opening / phase markers -----
    "early_turn_limit": (10, 100, True),
    "opening_turn_limit": (30, 150, True),

    # ----- Score multipliers -----
    "static_target_score_mult": (0.5, 2.5, False),
    "early_static_neutral_score_mult": (0.5, 2.5, False),
    "snipe_score_mult": (0.5, 2.5, False),
    "swarm_score_mult": (0.5, 2.5, False),
    "crash_exploit_score_mult": (0.5, 2.5, False),
    "defense_frontier_score_mult": (0.5, 2.5, False),

    # ----- Domination thresholds -----
    "behind_domination": (-0.5, 0.0, False),
    "ahead_domination": (0.0, 0.5, False),
    "finishing_domination": (0.1, 0.7, False),
    "finishing_prod_ratio": (1.0, 2.5, False),
    "behind_attack_margin_penalty": (0.0, 0.3, False),
    "ahead_attack_margin_bonus": (0.0, 0.3, False),
}

# Stable ordering of tunable fields (matches PARAM_SPACE insertion order)
NUMERIC_FIELDS: list[str] = list(PARAM_SPACE.keys())

# Indices into the encoded vector that correspond to integer fields
INT_DIM_INDICES: list[int] = [
    i for i, name in enumerate(NUMERIC_FIELDS)
    if PARAM_SPACE[name][2]
]


def validate_param_space() -> None:
    """Fail-loud check: every numeric HeuristicConfig field must be in PARAM_SPACE.

    Called by tests; called also at tuner startup to catch config drift.
    """
    numeric_field_names = {
        f.name for f in fields(HeuristicConfig)
        if f.type in (int, float, "int", "float")
    }
    missing = numeric_field_names - set(PARAM_SPACE)
    extra = set(PARAM_SPACE) - numeric_field_names
    if missing:
        raise ValueError(
            f"PARAM_SPACE missing bounds for HeuristicConfig fields: {sorted(missing)}. "
            f"Add them to PARAM_SPACE in src/tools/heuristic_tuner_param_space.py."
        )
    if extra:
        raise ValueError(
            f"PARAM_SPACE has bounds for fields that don't exist on HeuristicConfig: "
            f"{sorted(extra)}. Did a field get renamed?"
        )


def encode(cfg: HeuristicConfig) -> np.ndarray:
    """HeuristicConfig → flat float vector in NUMERIC_FIELDS order."""
    return np.array([float(getattr(cfg, name)) for name in NUMERIC_FIELDS], dtype=np.float64)


def decode(x: np.ndarray) -> HeuristicConfig:
    """Float vector → HeuristicConfig. Integer fields are rounded; bools use defaults."""
    if x.shape != (len(NUMERIC_FIELDS),):
        raise ValueError(
            f"decode: expected shape ({len(NUMERIC_FIELDS)},), got {x.shape}"
        )
    kwargs: dict[str, int | float] = {}
    for i, name in enumerate(NUMERIC_FIELDS):
        _, _, is_int = PARAM_SPACE[name]
        kwargs[name] = int(round(float(x[i]))) if is_int else float(x[i])
    return HeuristicConfig(**kwargs)
```

- [x] **Step 2: Run the coverage tests**

Run: `uv run pytest tests/test_heuristic_tuner.py::TestParamSpaceCoverage -v`
Expected: all 3 tests PASS.

If `test_param_space_covers_every_numeric_field` fails with "missing bounds for ['<some-field>']", that means HeuristicConfig has a field this plan didn't anticipate. Add the missing field to PARAM_SPACE with a sensible bound and re-run.

- [x] **Step 3: Commit**

```bash
git status -s  # verify only the new files are staged
git add tests/test_heuristic_tuner.py src/tools/heuristic_tuner_param_space.py
git commit -m "feat(tuner): ParamSpace table covering all 48 numeric HeuristicConfig fields"
```

---

## Task 4: encode/decode round-trip test + verification

**Files:**
- Modify: `tests/test_heuristic_tuner.py`

- [x] **Step 1: Add round-trip tests to existing test file**

Append to `tests/test_heuristic_tuner.py` after the `TestParamSpaceCoverage` class:

```python
class TestEncodeDecodeRoundTrip:
    def test_default_config_round_trips_exactly(self) -> None:
        """encode(decode(encode(default))) == encode(default), per dim."""
        cfg = HeuristicConfig.default()
        x = encode(cfg)
        cfg_round = decode(x)
        x_round = encode(cfg_round)
        np.testing.assert_array_almost_equal(x, x_round, decimal=6)

    def test_decode_snaps_integer_fields_to_int(self) -> None:
        """Integer fields decoded from non-integer floats must round to ints."""
        from tools.heuristic_tuner_param_space import NUMERIC_FIELDS, PARAM_SPACE
        x = encode(HeuristicConfig.default())
        # Bump every field by 0.4 to force rounding
        x_perturbed = x + 0.4
        cfg = decode(x_perturbed)
        for i, name in enumerate(NUMERIC_FIELDS):
            _, _, is_int = PARAM_SPACE[name]
            value = getattr(cfg, name)
            if is_int:
                assert isinstance(value, int), f"{name}: expected int, got {type(value).__name__}"
                # decode(x+0.4) for int should round to round(x+0.4) which is x or x+1 depending on x's fractional part
            else:
                assert isinstance(value, float), f"{name}: expected float, got {type(value).__name__}"

    def test_decode_rejects_wrong_shape(self) -> None:
        with pytest.raises(ValueError, match="expected shape"):
            decode(np.zeros(5))
```

- [x] **Step 2: Run round-trip tests**

Run: `uv run pytest tests/test_heuristic_tuner.py::TestEncodeDecodeRoundTrip -v`
Expected: all 3 tests PASS. (encode/decode were already written in Task 3 to support these.)

- [x] **Step 3: Commit**

```bash
git status -s
git add tests/test_heuristic_tuner.py
git commit -m "test(tuner): add encode/decode round-trip tests"
```

---

## Task 5: `run_one_game` helper (no Modal, real env)

**Files:**
- Create: `src/tools/modal_tuner.py`

- [x] **Step 1: Add a failing test for `run_one_game`**

Append to `tests/test_heuristic_tuner.py`:

```python
class TestRunOneGame:
    def test_run_one_game_returns_finite_margin(self) -> None:
        """Run one game (default cfg vs aggressive_swarm, seed=0). Margin should be finite."""
        from tools.modal_tuner import run_one_game

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        margin = run_one_game(cfg_dict, opponent_name="aggressive_swarm", seed=0)
        # In Orbit Wars, reward margin is typically -1, 0, or +1 (sometimes float)
        assert isinstance(margin, float)
        assert -10.0 <= margin <= 10.0, f"margin {margin} outside sanity range"

    def test_run_one_game_unknown_opponent_raises(self) -> None:
        from tools.modal_tuner import run_one_game

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        with pytest.raises(KeyError):
            run_one_game(cfg_dict, opponent_name="not_a_real_opponent", seed=0)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_heuristic_tuner.py::TestRunOneGame -v`
Expected: ImportError on `from tools.modal_tuner import run_one_game`.

- [x] **Step 3: Create `src/tools/modal_tuner.py` with the run_one_game helper**

Create file with this content:

```python
"""CMA-ES + Modal heuristic tuning framework for Orbit Wars HeuristicConfig.

Architecture:
- LOCAL ENTRYPOINT (`@app.local_entrypoint() main()`): runs the CMA-ES outer
  loop on the user's machine. Per generation: ask, dispatch via .starmap(),
  tell, log.
- MODAL FUNCTION (`@app.function evaluate_fitness`): runs ONE candidate's
  sanity gate + fitness games in a fresh container with isolated random state.
  popsize-many containers run in parallel.

Run profiles (see CLI flags):
    --smoke      popsize=4, gens=1, games=4         (~$0.05)
    --iteration  popsize=20, gens=15, games=30      (~$8)
    --default    popsize=50, gens=15, games=69      (~$54)  [no flag]
    --extended   popsize=50, gens=30, games=69      (~$108)
    --max-quality popsize=100, gens=30, games=100   (~$240)

Examples:
    uv run modal run src/tools/modal_tuner.py --smoke
    uv run modal run src/tools/modal_tuner.py --iteration --confirm-cost
    uv run modal run src/tools/modal_tuner.py --confirm-cost   # default profile

Outputs to: docs/research_documents/tuning_runs/<UTC-ISO-timestamp>/
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GLOBAL_TUNER_SEED = 42

# ---------------------------------------------------------------------------
# Pure helpers (no Modal — importable from tests and from inside containers)
# ---------------------------------------------------------------------------

# Opponent registry: name → "module_path:agent_function_name"
# Resolved lazily inside run_one_game so this module can be imported without
# kaggle_environments or src/ on sys.path (matters for Modal local entrypoint).
OPPONENT_REGISTRY: dict[str, str] = {
    "aggressive_swarm": "orbit_wars.opponents.aggressive_swarm:agent",
    "defensive_turtle": "orbit_wars.opponents.defensive_turtle:agent",
    "peer_mdmahfuzsumon": "orbit_wars.opponents.peer_mdmahfuzsumon:agent",
    # v15g_stock = our agent with the default config (baseline)
    "v15g_stock": "orbit_wars.heuristic.strategy:agent",
}


def _resolve_opponent(name: str):
    """Look up an opponent's agent function by registry name. Raises KeyError if unknown."""
    if name not in OPPONENT_REGISTRY:
        raise KeyError(f"Unknown opponent {name!r}. Known: {sorted(OPPONENT_REGISTRY)}")
    module_path, attr = OPPONENT_REGISTRY[name].split(":", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


def make_configured_agent(cfg_dict: dict):
    """Wrap our heuristic agent in a closure that pins it to a given config.

    CRITICAL: do NOT use *args, **kwargs — kaggle_environments uses inspect.signature
    to determine argument count and a *args-only closure is called with NO args.
    The returned function has an explicit `obs` parameter only.
    """
    from orbit_wars.heuristic.config import HeuristicConfig
    from orbit_wars.heuristic.strategy import agent as agent_strategy

    cfg = HeuristicConfig(**cfg_dict)

    def configured_agent(obs):
        return agent_strategy(obs, cfg)

    return configured_agent


def run_one_game(cfg_dict: dict, opponent_name: str, seed: int) -> float:
    """Run one Orbit Wars game; return reward margin (us - opponent).

    `cfg_dict`: dict of HeuristicConfig field values for OUR side.
    `opponent_name`: must be in OPPONENT_REGISTRY.
    `seed`: env seed (deterministic per call within one process).

    Returns: float margin. Typically in [-1, +1] but env may produce other floats.
    """
    from kaggle_environments import make

    me = make_configured_agent(cfg_dict)
    opponent_fn = _resolve_opponent(opponent_name)

    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run([me, opponent_fn])
    last = env.steps[-1]
    return float(last[0].reward) - float(last[1].reward)
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/test_heuristic_tuner.py::TestRunOneGame -v`
Expected: both tests PASS. The aggressive_swarm game should complete in ~3 seconds.

If the game test times out or returns NaN, check that:
1. `kaggle_environments` is installed (`uv run python -c "import kaggle_environments"`).
2. `orbit_wars.opponents.aggressive_swarm` exists and exports `agent`.

- [x] **Step 5: Commit**

```bash
git status -s
git add tests/test_heuristic_tuner.py src/tools/modal_tuner.py
git commit -m "feat(tuner): run_one_game helper + opponent registry"
```

---

## Task 6: `evaluate_fitness_local` — pure-Python fitness evaluator

**Files:**
- Modify: `src/tools/modal_tuner.py`
- Modify: `tests/test_heuristic_tuner.py`

- [x] **Step 1: Add a failing test for evaluate_fitness_local with a tiny budget**

Append to `tests/test_heuristic_tuner.py`:

```python
class TestEvaluateFitnessLocal:
    def test_local_smoke_returns_well_formed_dict(self) -> None:
        """Run a tiny budget end-to-end. Verify output dict has expected keys + types."""
        from tools.modal_tuner import evaluate_fitness_local

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        result = evaluate_fitness_local(
            cfg_dict=cfg_dict,
            candidate_id=0,
            generation=0,
            sanity_n_per_opponent=2,
            fitness_n_per_opponent=2,
            sanity_threshold=0.91,
        )
        # Required keys per spec Architecture/Modal-function section
        for key in ("candidate_id", "generation", "sanity_pass", "fitness",
                    "per_opp", "sanity_winrates", "wall_clock_seconds"):
            assert key in result, f"missing key {key!r} in result"
        assert result["candidate_id"] == 0
        assert result["generation"] == 0
        assert isinstance(result["sanity_pass"], bool)
        assert isinstance(result["fitness"], float)
        assert "v15g_stock" in result["per_opp"]
        assert "peer_mdmahfuzsumon" in result["per_opp"]
        assert "aggressive_swarm" in result["sanity_winrates"]
        assert "defensive_turtle" in result["sanity_winrates"]

    def test_local_disqualifies_obviously_bad_config(self) -> None:
        """A clearly broken config (min_launch=999, can never afford to launch) should
        fail sanity and return fitness == DISQUALIFIED_FITNESS."""
        from tools.modal_tuner import DISQUALIFIED_FITNESS, evaluate_fitness_local

        cfg_dict = {f.name: getattr(HeuristicConfig.default(), f.name)
                    for f in fields(HeuristicConfig)}
        cfg_dict["min_launch"] = 999  # can't ever launch — will lose every game

        result = evaluate_fitness_local(
            cfg_dict=cfg_dict,
            candidate_id=99,
            generation=0,
            sanity_n_per_opponent=2,
            fitness_n_per_opponent=2,
            sanity_threshold=0.91,
        )
        assert result["sanity_pass"] is False
        assert result["fitness"] == DISQUALIFIED_FITNESS
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_heuristic_tuner.py::TestEvaluateFitnessLocal -v`
Expected: ImportError on `evaluate_fitness_local` / `DISQUALIFIED_FITNESS`.

- [x] **Step 3: Add `evaluate_fitness_local` to `src/tools/modal_tuner.py`**

Append to `src/tools/modal_tuner.py` after the `run_one_game` function:

```python
# Sentinel returned when a candidate fails the sanity gate.
# Large negative — CMA-ES is minimizing -fitness, so this maps to +1e9 cost,
# making the candidate strictly worse than any sanity-passing one.
DISQUALIFIED_FITNESS: float = -1e9

# Fitness opponent panel (matches spec § Fitness function)
FITNESS_OPPONENTS: tuple[str, ...] = ("v15g_stock", "peer_mdmahfuzsumon")
FITNESS_WEIGHTS: dict[str, float] = {
    "v15g_stock": 0.6,
    "peer_mdmahfuzsumon": 0.4,
}

# Sanity gate panel
SANITY_OPPONENTS: tuple[str, ...] = ("aggressive_swarm", "defensive_turtle")


def _winrate(margins: list[float]) -> float:
    """Fraction of games with margin > 0 (strict win, ties don't count)."""
    if not margins:
        return 0.0
    wins = sum(1 for m in margins if m > 0)
    return wins / len(margins)


def evaluate_fitness_local(
    cfg_dict: dict,
    candidate_id: int,
    generation: int,
    sanity_n_per_opponent: int = 10,
    fitness_n_per_opponent: int = 69,
    sanity_threshold: float = 0.91,
) -> dict:
    """Run sanity gate, then fitness games for one candidate. Pure Python; no Modal.

    Reseeds Python's global random state once at entry so games are reproducible
    across containers (each container is its own fresh process, so this gives
    every candidate identical RNG consumption per generation).
    """
    random.seed(GLOBAL_TUNER_SEED)
    started = time.time()

    # ----- Sanity gate -----
    sanity_winrates: dict[str, float] = {}
    sanity_pass = True
    for opp in SANITY_OPPONENTS:
        margins = [run_one_game(cfg_dict, opp, seed=s)
                   for s in range(sanity_n_per_opponent)]
        wr = _winrate(margins)
        sanity_winrates[opp] = wr
        if wr < sanity_threshold:
            sanity_pass = False
            # Early exit: don't run remaining sanity opponents OR fitness phase
            break

    if not sanity_pass:
        return {
            "candidate_id": candidate_id,
            "generation": generation,
            "sanity_pass": False,
            "fitness": DISQUALIFIED_FITNESS,
            "per_opp": dict.fromkeys(FITNESS_OPPONENTS, 0.0),
            "sanity_winrates": sanity_winrates,
            "wall_clock_seconds": time.time() - started,
        }

    # ----- Fitness phase -----
    per_opp: dict[str, float] = {}
    for opp in FITNESS_OPPONENTS:
        margins = [run_one_game(cfg_dict, opp, seed=s)
                   for s in range(fitness_n_per_opponent)]
        per_opp[opp] = sum(margins) / len(margins)

    fitness = sum(FITNESS_WEIGHTS[opp] * per_opp[opp] for opp in FITNESS_OPPONENTS)

    return {
        "candidate_id": candidate_id,
        "generation": generation,
        "sanity_pass": True,
        "fitness": float(fitness),
        "per_opp": per_opp,
        "sanity_winrates": sanity_winrates,
        "wall_clock_seconds": time.time() - started,
    }
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/test_heuristic_tuner.py::TestEvaluateFitnessLocal -v --timeout=120`
Expected: both tests PASS. The smoke test runs 4 sanity games + 4 fitness games = ~24 sec wall-clock.

If the test exceeds 120s, the games may be running slower than expected — check with:
Run: `time uv run python -c "from tools.modal_tuner import run_one_game; from dataclasses import fields; from orbit_wars.heuristic.config import HeuristicConfig; cfg={f.name:getattr(HeuristicConfig.default(),f.name) for f in fields(HeuristicConfig)}; print(run_one_game(cfg,'aggressive_swarm',0))"`
Expected: completes in <5 seconds.

- [x] **Step 5: Commit**

```bash
git status -s
git add tests/test_heuristic_tuner.py src/tools/modal_tuner.py
git commit -m "feat(tuner): evaluate_fitness_local with sanity gate + fitness phase"
```

---

## Task 7: Modal app skeleton + `evaluate_fitness` Modal wrapper

**Files:**
- Modify: `src/tools/modal_tuner.py`

- [x] **Step 1: Add Modal image, app, and `evaluate_fitness` wrapper at the bottom of the file**

Append to `src/tools/modal_tuner.py`:

```python
# ---------------------------------------------------------------------------
# Modal app — image, function, local entrypoint
# ---------------------------------------------------------------------------

import modal

MINUTES = 60

# Image: Python 3.13 + project deps + our src/ tree.
# `add_local_dir(..., copy=True)` bakes src/ into the image so it's available
# at /app/src inside the container.
tuner_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install(
        "cma>=3.3.0",
        "scipy>=1.14",
        "numpy>=2.0",
        "kaggle_environments>=1.18.0",
    )
    .add_local_dir(
        local_path=str(Path(__file__).parent.parent),  # = src/
        remote_path="/app/src",
        copy=True,
    )
)

app = modal.App("orbit-wars-cma-tuner", image=tuner_image)


@app.function(
    image=tuner_image,
    cpu=2.0,
    memory=4096,
    timeout=20 * MINUTES,
)
def evaluate_fitness(
    cfg_dict: dict,
    candidate_id: int,
    generation: int,
    sanity_n_per_opponent: int,
    fitness_n_per_opponent: int,
    sanity_threshold: float,
) -> dict:
    """Modal-side wrapper: ensures src/ is on sys.path, then delegates."""
    import sys as _sys
    if "/app/src" not in _sys.path:
        _sys.path.insert(0, "/app/src")
    return evaluate_fitness_local(
        cfg_dict=cfg_dict,
        candidate_id=candidate_id,
        generation=generation,
        sanity_n_per_opponent=sanity_n_per_opponent,
        fitness_n_per_opponent=fitness_n_per_opponent,
        sanity_threshold=sanity_threshold,
    )
```

- [x] **Step 2: Verify the file imports cleanly (no Modal call yet)**

Run: `uv run python -c "from tools.modal_tuner import evaluate_fitness, app, tuner_image; print('Modal app:', app.name)"`
Expected: prints `Modal app: orbit-wars-cma-tuner` with no errors.

- [x] **Step 3: Re-run the existing tests to ensure nothing broke**

Run: `uv run pytest tests/test_heuristic_tuner.py -v --timeout=120`
Expected: all tests still PASS.

- [x] **Step 4: Commit**

```bash
git status -s
git add src/tools/modal_tuner.py
git commit -m "feat(tuner): add Modal app + evaluate_fitness container wrapper"
```

---

## Task 8: CMA-ES outer loop + local entrypoint

**Files:**
- Modify: `src/tools/modal_tuner.py`

- [x] **Step 1: Add the `_log_generation` helper and `_choose_profile` function**

Append to `src/tools/modal_tuner.py` BEFORE the `# Modal app` section (so they're regular helpers, not Modal-decorated):

Find the line `# ---------------------------------------------------------------------------\n# Modal app —` and insert above it:

```python
# ---------------------------------------------------------------------------
# CMA-ES outer loop helpers
# ---------------------------------------------------------------------------

# Profile presets: (popsize, generations, fitness_n_per_opponent, est_cost_usd)
PROFILES: dict[str, tuple[int, int, int, float]] = {
    "smoke":       (4,   1,  4,   0.05),
    "iteration":   (20,  15, 30,  8.0),
    "default":     (50,  15, 69,  54.0),
    "extended":    (50,  30, 69,  108.0),
    "max-quality": (100, 30, 100, 240.0),
}


def _choose_profile(
    profile_name: str,
    popsize_override: int | None,
    generations_override: int | None,
    fitness_games_override: int | None,
) -> tuple[int, int, int, float]:
    """Resolve profile preset + per-flag overrides → (popsize, gens, games, est_cost)."""
    if profile_name not in PROFILES:
        raise ValueError(
            f"Unknown profile {profile_name!r}. Choose from: {sorted(PROFILES)}"
        )
    popsize, generations, fitness_games, est_cost = PROFILES[profile_name]
    if popsize_override is not None:
        popsize = popsize_override
    if generations_override is not None:
        generations = generations_override
    if fitness_games_override is not None:
        fitness_games = fitness_games_override
    # Recompute estimated cost if any override applied
    if (popsize_override, generations_override, fitness_games_override) != (None, None, None):
        # Per-passing-candidate compute: (sanity_n*2 + games*2) * 3 sec * 2 cores * $0.000131
        # Per-failing-candidate: 1 min * 2 cores * $0.000131 = $0.0157
        # Assume 50% pass rate
        sanity_n = 10
        per_pass_sec = (sanity_n * 2 + fitness_games * 2) * 3
        cost_per_pass = per_pass_sec * 2 * 0.000131
        cost_per_fail = 60 * 2 * 0.000131
        est_cost = generations * (popsize / 2) * (cost_per_pass + cost_per_fail)
    return popsize, generations, fitness_games, est_cost


def _build_cma_options(popsize: int, num_dims: int) -> dict:
    """Construct the cma library options dict per spec §CMA-ES hyperparameters."""
    return {
        "popsize": popsize,
        "bounds": [[0.0] * num_dims, [1.0] * num_dims],  # normalized [0,1] per dim
        "integer_variables": INT_DIM_INDICES,
        "tolfun": 1e-3,
        "verbose": -9,  # quiet; we do our own logging
        "seed": GLOBAL_TUNER_SEED,
    }


def _normalize(x: np.ndarray, lowers: np.ndarray, uppers: np.ndarray) -> np.ndarray:
    """Real-space → normalized [0,1] per dim."""
    return (x - lowers) / (uppers - lowers)


def _denormalize(x_norm: np.ndarray, lowers: np.ndarray, uppers: np.ndarray) -> np.ndarray:
    """Normalized [0,1] → real-space."""
    return lowers + x_norm * (uppers - lowers)
```

Add at the top of the file with the other imports (after `import time`):

```python
import numpy as np

from tools.heuristic_tuner_param_space import (
    INT_DIM_INDICES,
    NUMERIC_FIELDS,
    PARAM_SPACE,
    decode,
    encode,
    validate_param_space,
)
```

- [x] **Step 2: Add the `@app.local_entrypoint() main()` at the bottom of the file**

Append to `src/tools/modal_tuner.py`:

```python
# ---------------------------------------------------------------------------
# Local entrypoint — CMA-ES outer loop
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main(
    smoke: bool = False,
    iteration: bool = False,
    extended: bool = False,
    max_quality: bool = False,
    popsize: int = 0,                         # 0 → use profile default
    generations: int = 0,                     # 0 → use profile default
    fitness_games_per_opponent: int = 0,      # 0 → use profile default
    sanity_n_per_opponent: int = 10,
    sanity_threshold: float = 0.91,
    confirm_cost: bool = False,
    output_root: str = "docs/research_documents/tuning_runs",
):
    """CMA-ES outer loop. See module docstring for run-profile examples.

    NOTE on `int = 0` defaults: Modal's CLI parser doesn't reliably accept
    `int | None` typing across all SDK versions, so we use `0` as a sentinel
    for "no override; use the profile default." Negative or zero override
    values are coerced to None internally.
    """
    import cma

    # 1. Resolve profile
    if smoke:
        profile = "smoke"
    elif iteration:
        profile = "iteration"
    elif extended:
        profile = "extended"
    elif max_quality:
        profile = "max-quality"
    else:
        profile = "default"

    pop, gens, fit_games, est_cost = _choose_profile(
        profile,
        popsize_override=popsize if popsize > 0 else None,
        generations_override=generations if generations > 0 else None,
        fitness_games_override=fitness_games_per_opponent if fitness_games_per_opponent > 0 else None,
    )

    # 2. Validate & confirm cost
    validate_param_space()
    print(f"=== CMA-ES tuning run ===")
    print(f"  profile         : {profile}")
    print(f"  popsize         : {pop}")
    print(f"  generations     : {gens}")
    print(f"  fitness games/op: {fit_games}")
    print(f"  sanity games/op : {sanity_n_per_opponent} (threshold {sanity_threshold:.2f})")
    print(f"  estimated cost  : ${est_cost:.2f}")
    if est_cost > 20.0 and not confirm_cost:
        print(f"\nERROR: estimated cost ${est_cost:.2f} exceeds $20 sentinel.")
        print(f"Re-run with --confirm-cost to proceed.")
        sys.exit(2)

    # 3. Set up output directory
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = Path(output_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  output dir      : {out_dir}\n")

    # 4. Set up CMA-ES on normalized [0,1] space
    from orbit_wars.heuristic.config import HeuristicConfig

    lowers = np.array([PARAM_SPACE[n][0] for n in NUMERIC_FIELDS], dtype=np.float64)
    uppers = np.array([PARAM_SPACE[n][1] for n in NUMERIC_FIELDS], dtype=np.float64)

    x0_real = encode(HeuristicConfig.default())
    x0_norm = _normalize(x0_real, lowers, uppers)
    sigma0 = 0.25  # 25% of normalized range per Hansen
    cma_opts = _build_cma_options(pop, num_dims=len(NUMERIC_FIELDS))
    es = cma.CMAEvolutionStrategy(x0_norm.tolist(), sigma0, cma_opts)

    # 5. Write config.json
    config_blob = {
        "run_id": run_id,
        "profile": profile,
        "popsize": pop,
        "num_generations": gens,
        "fitness_games_per_opponent": fit_games,
        "sanity_n_per_opponent": sanity_n_per_opponent,
        "sanity_threshold": sanity_threshold,
        "fitness_weights": FITNESS_WEIGHTS,
        "fitness_opponents": list(FITNESS_OPPONENTS),
        "sanity_opponents": list(SANITY_OPPONENTS),
        "param_space": {n: list(b) for n, b in PARAM_SPACE.items()},
        "baseline_config": asdict(HeuristicConfig.default()),
        "cma_options": {k: v for k, v in cma_opts.items() if k != "integer_variables"},
        "estimated_cost_usd": est_cost,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "config.json").write_text(json.dumps(config_blob, indent=2))

    # 6. CMA-ES loop
    best_fitness_so_far = float("-inf")
    best_cfg_dict_so_far: dict | None = None
    best_per_opp_so_far: dict | None = None
    accumulated_cost = 0.0
    gen_log_path = out_dir / "generations.jsonl"

    for gen in range(gens):
        gen_started = time.time()
        candidates_norm = es.ask()  # list of np.ndarray in normalized [0,1] space

        # Denormalize and decode each candidate to a HeuristicConfig dict
        args = []
        for i, c_norm in enumerate(candidates_norm):
            c_real = _denormalize(np.asarray(c_norm), lowers, uppers)
            cfg_dict = asdict(decode(c_real))
            args.append((cfg_dict, i, gen, sanity_n_per_opponent, fit_games, sanity_threshold))

        # PARALLEL: dispatch all candidates to Modal
        results = list(evaluate_fitness.starmap(args))

        # Sort results by candidate_id so they line up with candidates_norm
        results.sort(key=lambda r: r["candidate_id"])
        fitnesses = [r["fitness"] for r in results]

        # Tell CMA-ES (negate because cma minimizes)
        es.tell(candidates_norm, [-f for f in fitnesses])

        # Generation stats
        finite_fits = [f for f in fitnesses if f > DISQUALIFIED_FITNESS / 2]
        n_disqualified = sum(1 for f in fitnesses if f <= DISQUALIFIED_FITNESS / 2)
        gen_best = max(fitnesses)
        gen_mean = sum(finite_fits) / len(finite_fits) if finite_fits else float("nan")
        gen_std = (
            float(np.std(finite_fits)) if len(finite_fits) > 1 else 0.0
        )
        wall = time.time() - gen_started
        gen_cost = sum(r["wall_clock_seconds"] * 2 * 0.000131 for r in results)
        accumulated_cost += gen_cost

        # Update best-so-far
        gen_best_idx = fitnesses.index(gen_best)
        gen_best_result = results[gen_best_idx]
        if gen_best > best_fitness_so_far:
            best_fitness_so_far = gen_best
            best_cfg_dict_so_far = args[gen_best_idx][0]
            best_per_opp_so_far = gen_best_result["per_opp"]
            _write_best_config_py(
                out_dir / "best_config.py",
                best_cfg_dict_so_far,
                run_id,
                best_fitness_so_far,
                best_per_opp_so_far,
            )

        # Log generation
        gen_record = {
            "gen": gen,
            "best_fitness": gen_best,
            "mean_fitness": gen_mean,
            "fitness_stddev": gen_std,
            "n_disqualified": n_disqualified,
            "best_candidate": args[gen_best_idx][0],
            "per_opponent_breakdown": gen_best_result["per_opp"],
            "wall_clock_seconds": wall,
            "estimated_cost_usd": gen_cost,
            "accumulated_cost_usd": accumulated_cost,
        }
        with gen_log_path.open("a") as f:
            f.write(json.dumps(gen_record) + "\n")

        print(
            f"gen {gen+1:>3}/{gens}  best={gen_best:+.4f}  mean={gen_mean:+.4f}  "
            f"stddev={gen_std:.4f}  disq={n_disqualified}/{pop}  wall={wall:.0f}s  "
            f"cost=${gen_cost:.2f}  total=${accumulated_cost:.2f}"
        )

    # 7. Write final report
    completed = datetime.now(timezone.utc).isoformat()
    config_blob["completed_at"] = completed
    config_blob["final_accumulated_cost_usd"] = accumulated_cost
    (out_dir / "config.json").write_text(json.dumps(config_blob, indent=2))

    _write_final_report(
        out_dir / "final_report.md",
        run_id=run_id,
        profile=profile,
        gen_log_path=gen_log_path,
        best_cfg=best_cfg_dict_so_far,
        best_fitness=best_fitness_so_far,
        best_per_opp=best_per_opp_so_far,
        accumulated_cost=accumulated_cost,
        baseline_cfg=asdict(HeuristicConfig.default()),
    )

    print(f"\n=== Done ===")
    print(f"  best fitness     : {best_fitness_so_far:+.4f}")
    print(f"  best per-opp     : {best_per_opp_so_far}")
    print(f"  total cost spent : ${accumulated_cost:.2f}")
    print(f"  output dir       : {out_dir}")
```

- [x] **Step 3: Add the output writers as helpers near the top of the file (after `_winrate`)**

Append after `_winrate` and before `evaluate_fitness_local`:

```python
def _write_best_config_py(
    path: Path,
    cfg_dict: dict,
    run_id: str,
    fitness: float,
    per_opp: dict,
) -> None:
    """Write `best_config.py` with importable BEST = HeuristicConfig(...)."""
    per_opp_str = ", ".join(f"{k}={v:+.4f}" for k, v in per_opp.items())
    field_lines = ",\n    ".join(
        f"{k}={v!r}" for k, v in sorted(cfg_dict.items())
    )
    path.write_text(
        f'"""Best config from CMA-ES tuning run {run_id}.\n\n'
        f"Best fitness: {fitness:+.4f}\n"
        f"Per-opponent: {per_opp_str}\n"
        f'"""\n\n'
        f"from orbit_wars.heuristic.config import HeuristicConfig\n\n"
        f"BEST = HeuristicConfig(\n    {field_lines},\n)\n"
    )


def _write_final_report(
    path: Path,
    run_id: str,
    profile: str,
    gen_log_path: Path,
    best_cfg: dict | None,
    best_fitness: float,
    best_per_opp: dict | None,
    accumulated_cost: float,
    baseline_cfg: dict,
) -> None:
    """Write `final_report.md` with run summary, fitness curve, top configs."""
    if best_cfg is None:
        path.write_text(
            f"# CMA-ES Run {run_id} — NO RESULTS\n\nAll candidates disqualified.\n"
        )
        return

    # Read generations.jsonl
    gen_records: list[dict] = []
    with gen_log_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                gen_records.append(json.loads(line))

    # Diff best vs baseline
    diffs = []
    for k in sorted(best_cfg):
        b = baseline_cfg.get(k)
        v = best_cfg[k]
        if isinstance(b, (int, float)) and isinstance(v, (int, float)) and b != v:
            diffs.append(f"| `{k}` | `{b}` | `{v}` | `{v - b:+}` |")

    fitness_curve = "\n".join(
        f"| {r['gen']:>3} | {r['best_fitness']:+.4f} | {r['mean_fitness']:+.4f} | "
        f"{r['fitness_stddev']:.4f} | {r['n_disqualified']:>3} |"
        for r in gen_records
    )

    per_opp_str = ", ".join(f"`{k}`={v:+.4f}" for k, v in (best_per_opp or {}).items())

    md = f"""# CMA-ES Tuning Run — {run_id}

**Profile:** `{profile}`
**Generations:** {len(gen_records)}
**Total cost:** ${accumulated_cost:.2f}

## Best result

- **Fitness:** {best_fitness:+.4f}
- **Per-opponent margins:** {per_opp_str}
- See `best_config.py` for the importable HeuristicConfig.

## Best vs baseline — changed fields

| Field | Baseline | Best | Δ |
|-------|----------|------|---|
{chr(10).join(diffs) if diffs else '| (no changes — best == baseline) | | | |'}

## Fitness curve (per generation)

| Gen | Best | Mean | StdDev | Disq |
|----:|-----:|-----:|-------:|-----:|
{fitness_curve}

## Files in this run directory

- `config.json` — run hyperparameters + param space + baseline + cma options
- `generations.jsonl` — one JSON object per generation
- `best_config.py` — importable best-so-far HeuristicConfig
- `final_report.md` — this file
"""
    path.write_text(md)
```

- [x] **Step 4: Verify the file imports cleanly**

Run: `uv run python -c "from tools.modal_tuner import main, evaluate_fitness, _choose_profile; print('OK')"`
Expected: prints `OK`.

- [x] **Step 5: Test profile selection**

Run: `uv run python -c "from tools.modal_tuner import _choose_profile; print(_choose_profile('default', None, None, None))"`
Expected: prints `(50, 15, 69, 54.0)`.

Run: `uv run python -c "from tools.modal_tuner import _choose_profile; print(_choose_profile('smoke', None, None, None))"`
Expected: prints `(4, 1, 4, 0.05)`.

- [x] **Step 6: Re-run all tests to ensure nothing broke**

Run: `uv run pytest tests/test_heuristic_tuner.py -v --timeout=120`
Expected: all tests still PASS.

- [x] **Step 7: Commit**

```bash
git status -s
git add src/tools/modal_tuner.py
git commit -m "feat(tuner): CMA-ES outer loop + output writers + profile presets"
```

---

## Task 9: Add `--smoke` profile path test (no Modal yet)

**Files:**
- Modify: `tests/test_heuristic_tuner.py`

- [x] **Step 1: Add a test that exercises the profile resolution + cost guard logic**

Append to `tests/test_heuristic_tuner.py`:

```python
class TestProfileAndCostGuard:
    def test_smoke_profile_under_cost_threshold(self) -> None:
        from tools.modal_tuner import _choose_profile
        pop, gens, games, cost = _choose_profile("smoke", None, None, None)
        assert pop == 4 and gens == 1 and games == 4
        assert cost < 1.0

    def test_default_profile_at_expected_cost(self) -> None:
        from tools.modal_tuner import _choose_profile
        pop, gens, games, cost = _choose_profile("default", None, None, None)
        assert pop == 50 and gens == 15 and games == 69
        assert 40.0 <= cost <= 70.0  # ~$54 plus tolerance

    def test_overrides_recompute_cost(self) -> None:
        from tools.modal_tuner import _choose_profile
        # Override popsize down → cost should drop proportionally
        _, _, _, default_cost = _choose_profile("default", None, None, None)
        _, _, _, half_cost = _choose_profile("default", popsize_override=25, generations_override=None, fitness_games_override=None)
        # Note: cost recompute formula uses 50% sanity-pass model so it may not be exactly half;
        # but it should be meaningfully smaller.
        assert half_cost < default_cost * 0.7

    def test_unknown_profile_raises(self) -> None:
        from tools.modal_tuner import _choose_profile
        with pytest.raises(ValueError, match="Unknown profile"):
            _choose_profile("not_a_profile", None, None, None)
```

- [x] **Step 2: Run the new tests**

Run: `uv run pytest tests/test_heuristic_tuner.py::TestProfileAndCostGuard -v`
Expected: all 4 tests PASS.

- [x] **Step 3: Commit**

```bash
git status -s
git add tests/test_heuristic_tuner.py
git commit -m "test(tuner): profile preset + cost-guard logic tests"
```

---

## Task 10: Run full pytest suite + verify Modal app metadata

**Files:** none modified

- [x] **Step 1: Run the full project pytest suite (catches accidental regressions in existing tests)**

Run: `uv run pytest -q --timeout=120`
Expected: all tests pass (existing 37 + new ones from this plan = ~50+).

If any pre-existing test fails that was passing before, investigate before continuing — likely a circular import or an accidental change to a shared module.

- [x] **Step 2: Verify the Modal app inspects cleanly**

Run: `uv run python -c "from tools.modal_tuner import app; print('App:', app.name); print('Functions:', list(app.registered_functions.keys()))"`

Expected output (function name will be `evaluate_fitness`):
```
App: orbit-wars-cma-tuner
Functions: ['evaluate_fitness']
```

- [x] **Step 3: Verify the modal CLI sees the file as a valid Modal app**

Run: `uv run modal run src/tools/modal_tuner.py --help 2>&1 | head -30`

Expected: shows usage with `--smoke`, `--iteration`, `--popsize`, etc. as flags for the local entrypoint `main`. No syntax errors.

If you see "no @app.local_entrypoint() found", the `main` function isn't decorated properly — check Task 8.

If `modal run FILE --help` doesn't show the entrypoint flags (depends on Modal SDK version), verify by direct introspection instead:

Run: `uv run python -c "import inspect; from tools.modal_tuner import main; print(inspect.signature(main))"`
Expected: prints the signature of `main` showing all the CLI flags.

- [x] **Step 4: Commit (if any incidental fixes were needed; else skip)**

```bash
git status -s  # if clean, skip the commit
```

---

## Task 11: Manual `--smoke` Modal run (real money — confirm with user first)

**Files:** none modified — this is a manual verification task.

- [x] **Step 1: Confirm Modal auth and credit balance**

Run: `uv run modal token info`
Expected: prints the user's Modal token info (NOT "no token configured"). If missing, instruct the user to run `uv run modal token new` interactively.

(Note: the `modal token current` form was an error in an earlier draft of this plan — the correct CLI command is `modal token info`.)

Run: `uv run modal app list 2>&1 | head -5`
Expected: lists existing Modal apps OR prints "No deployed apps". Either is fine.

**Ask the user to verify their Modal credit balance in the dashboard** (https://modal.com/settings/usage) BEFORE proceeding. The smoke run costs <$0.10 but you want to be sure they have at least $1 left.

- [x] **Step 2: Run the smoke profile**

Run: `uv run modal run src/tools/modal_tuner.py --smoke`

Expected behavior:
- Prints "=== CMA-ES tuning run ===" header with popsize=4, gens=1, games=4
- Estimated cost printed (~$0.05); under $20 threshold so no `--confirm-cost` needed
- Modal builds the image (~2-5 min on first run; cached after)
- 4 candidates dispatched in parallel
- Each container runs 4+4=8 sanity games + ≤8 fitness games (16 total max) at ~3 sec each = ≤ 50 sec wall-clock per container
- Generation 1 logged to stdout
- Run completes in ~5-10 min total (mostly image build) and ~30-60 sec on subsequent smoke runs
- Output dir created under `docs/research_documents/tuning_runs/<timestamp>/` containing 4 files: `config.json`, `generations.jsonl`, `best_config.py`, `final_report.md`

If Modal can't import `orbit_wars.heuristic.config` inside the container, the `add_local_dir` path is wrong — check Task 7 step 1, the `local_path=` argument should resolve to the project's `src/` directory.

- [x] **Step 3: Inspect the smoke run output**

Run: `ls -la docs/research_documents/tuning_runs/`
Expected: at least one timestamped directory.

Run: `cat docs/research_documents/tuning_runs/*/final_report.md | head -40` (use the most recent dir)
Expected: a well-formed markdown report with fitness curve table.

Run: `head -10 docs/research_documents/tuning_runs/*/best_config.py`
Expected: a Python module importable with `from <path> import BEST`.

- [x] **Step 4: Verify the best_config.py is actually importable**

Find the most recent run dir, then test the import. Run as one shell command:

```bash
LATEST=$(ls -td docs/research_documents/tuning_runs/*/ | head -1)
echo "Testing: $LATEST"
uv run python -c "
import sys
sys.path.insert(0, '$LATEST'.rstrip('/'))
from best_config import BEST
print(type(BEST).__name__, len(BEST.__dataclass_fields__))
"
```

Expected: prints `HeuristicConfig 50` (50 = 48 numeric + 2 bool fields).

- [x] **Step 5: Commit any docs / output that the user wants in version control**

The output directory `docs/research_documents/tuning_runs/<timestamp>/` is generated artifact. The user may or may not want it committed. Check with the user before adding:

```bash
git status -s
# Do NOT auto-add docs/research_documents/tuning_runs/ — ask first
```

If user says yes, commit. If no, add to `.gitignore` (the `tuning_runs/` directory under `docs/research_documents/`).

---

## Task 12: Final documentation pass + handoff

**Files:**
- Modify: `src/tools/modal_tuner.py` (docstring updates only if needed)

- [x] **Step 1: Verify the module docstring is complete**

Read the top of `src/tools/modal_tuner.py`. Confirm the docstring includes:
- All 5 profile names + their (popsize, gens, games, cost) tuples
- At least one example invocation per profile
- Output directory path

If anything is stale or wrong, update.

- [x] **Step 2: Print user-facing summary**

Print this summary to the user (in chat, not to a file):

```
CMA-ES + Modal heuristic tuning framework is implemented and smoke-tested.

To run an iteration sweep (~$8):
  uv run modal run src/tools/modal_tuner.py --iteration --confirm-cost

To run the default sweep (~$54, fits $60 credit):
  uv run modal run src/tools/modal_tuner.py --confirm-cost

Outputs land in docs/research_documents/tuning_runs/<timestamp>/.
The best_config.py is importable as `from <that path> import BEST`.

Recommended next steps:
1. Run --iteration first to validate the framework end-to-end on a small budget.
2. If iteration looks healthy (fitness improving generation-by-generation,
   sanity-pass rate >50%), run the default sweep.
3. Take BEST from the best run, copy values into a new HeuristicConfig in
   src/orbit_wars/heuristic/config.py (or import directly), pack a tarball
   per CLAUDE.md instructions, submit to Kaggle.
```

- [x] **Step 3: Mark all checklist items in this plan as complete**

Edit this plan file: change `- [ ]` to `- [x]` for every step. Commit:

```bash
git add docs/superpowers/plans/2026-05-02-cma-es-tuning-framework.md
git commit -m "docs(tuner): mark implementation plan as complete"
```

---

## Spec coverage self-check (for the implementing engineer to verify)

Before marking the plan complete, confirm each spec deliverable is implemented:

| Spec deliverable | Implemented in task |
|---|---|
| `src/tools/modal_tuner.py` (Modal app + local entrypoint) | Tasks 5, 7, 8 |
| `src/tools/heuristic_tuner_param_space.py` (ParamSpace, encode/decode, fail-loud check) | Tasks 2, 3 |
| Per-run output dir with `config.json`, `generations.jsonl`, `best_config.py`, `final_report.md` | Task 8 (writers) + Task 11 (verified at runtime) |
| Smoke tests at `tests/test_heuristic_tuner.py` (encode/decode round-trip, ParamSpace coverage, local fitness eval) | Tasks 2, 4, 6, 9 |
| Modal end-to-end manual smoke (`uv run modal run ... --smoke`) | Task 11 |
| `cma` in pyproject.toml + uv.lock | Task 1 |
| `modal>=1.4.2` already present | Verified pre-Task 1 |
| CLI flags: `--popsize`, `--generations`, `--fitness-games-per-opponent` | Task 8 |
| Profile presets + cost guard (`--confirm-cost` if est > $20) | Task 8 (cost guard) + Task 9 (tested) |
| Per-generation cost printout | Task 8 |
| Random-state isolation via Modal containers | Task 6 (`random.seed(GLOBAL_TUNER_SEED)` in `evaluate_fitness_local`) |
| 91% sanity threshold | Task 6 (default arg `sanity_threshold=0.91`) |
| Bools pinned (not tuned) | Task 3 (excluded from PARAM_SPACE) |
| Image bakes in src/ | Task 7 (`.add_local_dir`) |
| HeuristicConfig serialized as dict | Tasks 5, 6 (`asdict()` from local; `HeuristicConfig(**cfg_dict)` in container) |
| No Modal Volume in MVP | Verified by absence (we only use return values) |
| No edits to production code | Confirmed: only `pyproject.toml` modified outside `src/tools/` and `tests/` |
