"""CMA-ES + Modal heuristic tuning framework for Orbit Wars HeuristicConfig.

Architecture:
- LOCAL ENTRYPOINT (`@app.local_entrypoint() main()`): runs the CMA-ES outer
  loop on the user's machine. Per generation: ask, dispatch via .starmap(),
  tell, log.
- MODAL FUNCTION (`@app.function evaluate_fitness`): runs ONE candidate's
  sanity gate + fitness games in a fresh container with isolated random state.
  popsize-many containers run in parallel.

Run profiles (see CLI flags):
    --smoke      popsize=4, gens=1, games=4         (~$0.10)
    --iteration  popsize=20, gens=15, games=30      (~$12)
    --default    popsize=50, gens=15, games=69      (~$55)   [no flag]
    --extended   popsize=50, gens=30, games=69      (~$110)
    --max-quality popsize=100, gens=30, games=100   (~$285)

Cost estimates updated 2026-05-02 after dropping peer_mdmahfuzsumon from
FITNESS_OPPONENTS (saturated opponent — see code comments). Real Modal billing
can run ~30-50% higher than these meter-based estimates due to container
startup/idle overhead. Verify dashboard balance before each non-smoke run.

Examples:
    uv run modal run src/tools/modal_tuner.py --smoke
    uv run modal run src/tools/modal_tuner.py --iteration --confirm-cost
    uv run modal run src/tools/modal_tuner.py --confirm-cost   # default profile

Outputs to: docs/research_documents/tuning_runs/<UTC-ISO-timestamp>/
"""

from __future__ import annotations

import sys

# Modal container compatibility: when this module is loaded inside a Modal
# container, the file lands at /root/modal_tuner.py and /app/src/ holds our
# source tree (copied via .add_local_dir). /app/src is NOT on sys.path at
# module-load time, so `from tools.X import Y` would fail before any function
# body runs. Inserting /app/src here makes the import work in containers and
# is a no-op locally (the path doesn't exist locally; tools is on sys.path
# via the project install).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

import json  # noqa: E402  (import after sys.path setup is intentional)
import random  # noqa: E402
import time  # noqa: E402
from dataclasses import asdict  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

from tools.heuristic_tuner_param_space import (  # noqa: E402
    INT_DIM_INDICES,
    NUMERIC_FIELDS,
    PARAM_SPACE,
    decode,
    encode,
    validate_param_space,
)

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


def run_one_game_vs_config(
    cfg_dict_us: dict, cfg_dict_opp: dict, seed: int,
) -> float:
    """Run one game between two HeuristicConfig instances. Used for archive matchups.

    Both sides are our heuristic agent, just with different configs. Returns
    reward margin (us - opponent). Same env-seed semantics as run_one_game.
    """
    from kaggle_environments import make

    me = make_configured_agent(cfg_dict_us)
    opp = make_configured_agent(cfg_dict_opp)

    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run([me, opp])
    last = env.steps[-1]
    return float(last[0].reward) - float(last[1].reward)


# Sentinel returned when a candidate fails the sanity gate.
# Large negative — CMA-ES is minimizing -fitness, so this maps to +1e9 cost,
# making the candidate strictly worse than any sanity-passing one.
DISQUALIFIED_FITNESS: float = -1e9

# Fitness anchor — the always-present "don't regress against current production"
# opponent. v15g_stock is "our agent with default config" (self-play asymmetry).
# Earlier had a fixed multi-opponent panel, but spot-check revealed all our
# local opponents are saturated against default (94-100% winrate) — only
# v15g_stock self-play differentiates. Lock it as the anchor; archive entries
# (see ROLLING ARCHIVE below) provide the diversity that local opponents can't.
FITNESS_ANCHOR: str = "v15g_stock"

# Sanity gate panel — opponents the agent must beat reliably to be coherent.
# Threshold is sanity_threshold (default 0.91).
SANITY_OPPONENTS: tuple[str, ...] = ("aggressive_swarm", "defensive_turtle")

# ----- Rolling-archive co-evolution (Path G; spec Phase 3.5) -----
#
# Every ARCHIVE_UPDATE_INTERVAL generations, the current best-so-far config is
# appended to the archive. From then on, fitness includes "did this candidate
# beat the past archive entries?" alongside the v15g_stock anchor.
#
# Why: BEST_v2 hit 614 μ on ladder despite +1.12 margin vs default locally
# because all our local opponents are saturated. With archive entries, CMA-ES
# has to keep beating its own evolving best, which provides naturally-
# adversarial diversity that fixed local opponents cannot.
#
# Weight scheme: anchor takes ANCHOR_WEIGHT, archive entries equally share
# ARCHIVE_WEIGHT_TOTAL. With archive_size=N: weight_per_archive = 0.5/N.
ARCHIVE_MAX_SIZE: int = 3            # FIFO eviction beyond this
ARCHIVE_UPDATE_INTERVAL: int = 3     # generations between archive appends
ANCHOR_WEIGHT: float = 0.5           # v15g_stock weight (always)
ARCHIVE_WEIGHT_TOTAL: float = 0.5    # split equally across archive entries

# Backward-compat shim — old callers still reference these
FITNESS_OPPONENTS: tuple[str, ...] = (FITNESS_ANCHOR,)
FITNESS_WEIGHTS: dict[str, float] = {FITNESS_ANCHOR: 1.0}


def _winrate(margins: list[float]) -> float:
    """Fraction of games with margin > 0 (strict win, ties don't count)."""
    if not margins:
        return 0.0
    wins = sum(1 for m in margins if m > 0)
    return wins / len(margins)


# ---------------------------------------------------------------------------
# 4P fitness helpers (Plan A retool, 2026-05-05 kickoff brief)
# ---------------------------------------------------------------------------

# Per-rank score for graduated_scores. 1st gets +1, 2nd gets +1/3, etc.
# Sum is 0 (zero-sum across the 4 players).
GRADUATED_RANK_SCORES: tuple[float, ...] = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)


def graduated_scores(asset_counts: list[float]) -> list[float]:
    """Compute graduated placement scores [+1, +1/3, -1/3, -1] from asset counts.

    Players are ranked by ``asset_counts`` (highest = rank 1). Tied players
    receive the AVERAGE of their tied ranks' scores. Sum across all returned
    scores equals zero (zero-sum tournament scoring).

    Returns scores in the SAME ORDER as ``asset_counts`` (i.e. result[i] is
    player i's score, not the i-th best score).

    Example:
        graduated_scores([100, 50, 30, 0]) → [+1, +1/3, -1/3, -1]
        graduated_scores([100, 100, 30, 0]) → [+2/3, +2/3, -1/3, -1]
                                              # players 0,1 tied at top → avg(1, 1/3) = 2/3
        graduated_scores([100, 50, 50, 50]) → [+1, -1/9, -1/9, -1/9]
                                              # players 1,2,3 tied → avg(1/3, -1/3, -1) = -1/9
    """
    if len(asset_counts) != 4:
        raise ValueError(
            f"graduated_scores expects exactly 4 players (4P fitness); got {len(asset_counts)}"
        )

    # Group player indices by asset count (descending). Tied groups share scores.
    indexed = sorted(enumerate(asset_counts), key=lambda kv: -kv[1])
    scores = [0.0] * 4

    i = 0
    while i < 4:
        # Find the run of players tied with indexed[i].
        j = i
        while j < 4 and indexed[j][1] == indexed[i][1]:
            j += 1
        # Average the rank scores for ranks [i, j).
        tied_avg = sum(GRADUATED_RANK_SCORES[k] for k in range(i, j)) / (j - i)
        for k in range(i, j):
            scores[indexed[k][0]] = tied_avg
        i = j

    return scores


def _select_4p_opponents(
    archive_opponents: list[dict],
    *,
    num_needed: int = 3,
    rng: random.Random | None = None,
) -> list[dict | str]:
    """Pick `num_needed` opponents for a 4P fitness game.

    Strategy (per kickoff brief Section 2.1):
      - Pure rolling-archive co-evolution: sample WITHOUT replacement when
        the archive has enough entries.
      - Fall back to "starter" (the env's built-in baseline) when archive
        has too few entries to fill all 3 slots.

    Returns a list of length ``num_needed`` where each entry is either:
      - a dict with keys {"name": str, "cfg_dict": dict} (archive entry), OR
      - the string ``"starter"`` (built-in baseline fallback).

    The dict-or-string union mirrors the env-side dispatch in run_one_game_4p.

    Use a seeded ``rng`` (random.Random(seed)) for reproducible sampling
    within a generation; default uses the module-level random state.
    """
    if rng is None:
        rng = random
    if len(archive_opponents) >= num_needed:
        return list(rng.sample(archive_opponents, num_needed))
    # Not enough archive entries — use what we have, pad with starter.
    chosen: list[dict | str] = list(archive_opponents)
    while len(chosen) < num_needed:
        chosen.append("starter")
    return chosen


def run_one_game_4p(
    candidate_cfg: dict, opponents: list[dict | str], seed: int,
) -> list[float]:
    """Run one 4P FFA Orbit Wars game; return graduated_scores per player.

    Players assigned:
      - position 0: candidate_cfg (the candidate being evaluated)
      - positions 1-3: opponents[0..2] — each is either an archive dict
        ({"name": str, "cfg_dict": dict}) or the literal string "starter"
        (the env's built-in baseline agent)

    Returns a list of length 4 where result[i] is player i's graduated
    placement score for this game (summing to zero across the 4).

    Uses compute_player_assets on the FINAL observation to derive ranks,
    then graduated_scores for the [+1, +1/3, -1/3, -1] mapping.
    """
    from kaggle_environments import make

    if len(opponents) != 3:
        raise ValueError(
            f"run_one_game_4p needs exactly 3 opponents (4P FFA total); got {len(opponents)}"
        )

    agents: list = [make_configured_agent(candidate_cfg)]
    for opp in opponents:
        if opp == "starter":
            agents.append("starter")
        elif isinstance(opp, dict) and "cfg_dict" in opp:
            agents.append(make_configured_agent(opp["cfg_dict"]))
        else:
            raise TypeError(
                f"Opponent must be 'starter' or dict with 'cfg_dict'; got {opp!r}"
            )

    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run(agents)
    # Final observation has the post-game asset state.
    final_obs = env.steps[-1][0].observation
    assets = compute_player_assets(final_obs)
    # Pad to 4 if anyone is missing (eliminated player has zero assets and
    # might not appear in the inferred owner-id range).
    while len(assets) < 4:
        assets.append(0.0)
    return graduated_scores(assets[:4])


def compute_player_assets(obs) -> list[float]:
    """Sum each player's planet ships + in-flight fleet ships.

    Mirrors env L687-693 alive-player logic (a player is alive iff they own
    >=1 planet OR have >=1 fleet in flight). For graduated scoring we want
    the actual asset COUNT, not just alive/dead, so we sum.

    Returns a list of length ``num_players`` where index i = player i's total.
    """
    num_players = len(set(p[1] for p in obs.planets if p[1] != -1)) or 0
    # Robust: derive num_players from agent count if obs has it; otherwise
    # max owner id + 1 (env uses 0..N-1).
    max_owner = -1
    for p in obs.planets:
        if p[1] != -1 and p[1] > max_owner:
            max_owner = p[1]
    for f in obs.fleets:
        if f[1] > max_owner:
            max_owner = f[1]
    num_players = max(num_players, max_owner + 1)
    if num_players <= 0:
        return []

    assets = [0.0] * num_players
    for p in obs.planets:
        if p[1] != -1:
            assets[p[1]] += float(p[5])  # planet ships
    for f in obs.fleets:
        assets[f[1]] += float(f[6])  # fleet ships
    return assets


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

    diff_section = "\n".join(diffs) if diffs else "| (no changes — best == baseline) | | | |"

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
{diff_section}

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


def evaluate_fitness_local(
    cfg_dict: dict,
    candidate_id: int,
    generation: int,
    sanity_n_per_opponent: int = 10,
    fitness_n_per_opponent: int = 33,
    sanity_threshold: float = 0.91,
    archive_opponents: list[dict] | None = None,
) -> dict:
    """Run sanity gate (2P), then 4P fitness games for one candidate. Pure Python; no Modal.

    Plan A 4P retool (kickoff brief 2026-05-05): the fitness phase is now
    4P FFA games using graduated placement scoring (rank → [+1, +1/3,
    -1/3, -1] with tie-averaging). Each game pairs the candidate (player 0)
    with 3 opponents drawn from `archive_opponents` via `_select_4p_opponents`
    (falls back to "starter" when archive has fewer than 3 entries).

    Sanity gate stays 2P — it just checks the candidate is coherent enough
    to play. SANITY_OPPONENTS, sanity_n_per_opponent, and sanity_threshold
    semantics unchanged. Sanity-fail returns DISQUALIFIED_FITNESS as before.

    `fitness_n_per_opponent`: keeping the parameter name for backward compat
    with the Modal `evaluate_fitness` wrapper, but in 4P mode this is the
    number of 4P GAMES per candidate (kickoff brief: N=33).

    `archive_opponents`: same shape as before — list of dicts with keys
    {"name": str, "cfg_dict": dict}. None or empty → all-starter opponents.

    Reseeds Python's global random state once at entry so games are
    reproducible across containers (each container is its own fresh
    process, so this gives every candidate identical RNG consumption per
    generation).

    Returns `per_opp = {"4p_graduated": mean_score}`. The single-key shape
    keeps downstream report writers happy (they iterate per_opp.items()).
    """
    random.seed(GLOBAL_TUNER_SEED)
    started = time.time()
    archive_opponents = archive_opponents or []

    # ----- Sanity gate (2P, unchanged) -----
    sanity_winrates: dict[str, float] = {}
    sanity_pass = True
    for opp in SANITY_OPPONENTS:
        margins = [run_one_game(cfg_dict, opp, seed=s)
                   for s in range(sanity_n_per_opponent)]
        wr = _winrate(margins)
        sanity_winrates[opp] = wr
        if wr < sanity_threshold:
            sanity_pass = False
            break  # early exit, skip remaining sanity opps + fitness phase

    if not sanity_pass:
        return {
            "candidate_id": candidate_id,
            "generation": generation,
            "sanity_pass": False,
            "fitness": DISQUALIFIED_FITNESS,
            "per_opp": {"4p_graduated": 0.0},
            "sanity_winrates": sanity_winrates,
            "wall_clock_seconds": time.time() - started,
        }

    # ----- Fitness phase: N 4P FFA games -----
    candidate_scores: list[float] = []
    for game_idx in range(fitness_n_per_opponent):
        opponents = _select_4p_opponents(archive_opponents, num_needed=3)
        # Game seed = game_idx so every candidate sees the same env seeds
        # (fair comparison within the generation).
        scores = run_one_game_4p(cfg_dict, opponents, seed=game_idx)
        candidate_scores.append(scores[0])  # candidate is at position 0

    fitness = sum(candidate_scores) / len(candidate_scores)

    return {
        "candidate_id": candidate_id,
        "generation": generation,
        "sanity_pass": True,
        "fitness": float(fitness),
        "per_opp": {"4p_graduated": float(fitness)},
        "sanity_winrates": sanity_winrates,
        "wall_clock_seconds": time.time() - started,
    }


# ---------------------------------------------------------------------------
# CMA-ES outer loop helpers
# ---------------------------------------------------------------------------

# Profile presets: (popsize, generations, fitness_n_per_opponent, est_cost_usd).
# Estimates updated 2026-05-02 (rolling archive added). Effective opponent count
# grows from 1 (anchor only, gens 0..K-1) to 1+M (anchor + max archive) over a
# run, averaging ~2.8 fitness opponents per candidate for the default profile.
# These meter-based numbers run ~4-5x HIGHER than actual Modal billing per the
# user's dashboard — so divide by 4-5 for real $$$.
PROFILES: dict[str, tuple[int, int, int, float]] = {
    # popsize, generations, fitness_n_per_opponent (= 4P games per eval), est_cost_usd
    # 4P retool 2026-05-05: kickoff brief recommends N=33 games per eval.
    # 4P games are ~4× the agent-call work of 2P, so per-evaluation wall-clock
    # is roughly 33*4 / 69*1 ≈ 2× the old 2P default. Cost estimates bumped
    # accordingly. Modal cost-meter overestimates 4-5× per memory; defer to
    # the user's billing dashboard for actual $$.
    "smoke":       (4,   1,  4,   0.20),
    "iteration":   (20,  15, 33,  50.0),
    "default":     (50,  15, 33,  130.0),
    "extended":    (50,  30, 33,  260.0),
    "max-quality": (100, 30, 33,  500.0),
}


def _avg_archive_size_during_run(generations: int, interval: int, max_size: int) -> float:
    """Average archive size over a run, accounting for warmup + FIFO cap."""
    total = 0
    for g in range(generations):
        # archive_at_eval(g) = min(g // interval, max_size)
        total += min(g // interval, max_size)
    return total / generations if generations > 0 else 0.0


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
    # Recompute estimated cost if any override applied.
    # Per-passing-candidate sec = (sanity_n × n_sanity_opps + games × n_fitness_opps) × 3 sec/game
    # Per-failing-candidate sec = ~60 sec (early-exit on first sanity opponent)
    # We observed 0% sanity-fail rate post-fitness-fix, so model 0% fail
    # (slightly over-estimates if some configs do fail, which is fine).
    if (popsize_override, generations_override, fitness_games_override) != (None, None, None):
        sanity_n = 10
        # Effective fitness opponents = 1 (anchor) + average archive size
        avg_archive = _avg_archive_size_during_run(
            generations, ARCHIVE_UPDATE_INTERVAL, ARCHIVE_MAX_SIZE,
        )
        avg_fitness_opps = 1.0 + avg_archive
        per_pass_sec = (
            sanity_n * len(SANITY_OPPONENTS) + fitness_games * avg_fitness_opps
        ) * 3
        cost_per_pass = per_pass_sec * 2 * 0.000131
        # 0% sanity-fail rate observed in practice → use cost_per_pass for all
        est_cost = generations * popsize * cost_per_pass
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


# ---------------------------------------------------------------------------
# Modal app — image, function, local entrypoint
# ---------------------------------------------------------------------------

import modal  # noqa: E402  (intentionally below pure helpers)

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
    timeout=120 * MINUTES,  # raised from 30 — accommodates worker preemption restart + archive-saturated wall-clock
)
def evaluate_fitness(
    cfg_dict: dict,
    candidate_id: int,
    generation: int,
    sanity_n_per_opponent: int,
    fitness_n_per_opponent: int,
    sanity_threshold: float,
    archive_opponents: list[dict] | None = None,
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
        archive_opponents=archive_opponents,
    )


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
    print("=== CMA-ES tuning run ===")
    print(f"  profile         : {profile}")
    print(f"  popsize         : {pop}")
    print(f"  generations     : {gens}")
    print(f"  fitness games/op: {fit_games}")
    print(f"  sanity games/op : {sanity_n_per_opponent} (threshold {sanity_threshold:.2f})")
    print(f"  estimated cost  : ${est_cost:.2f}")
    if est_cost > 20.0 and not confirm_cost:
        print(f"\nERROR: estimated cost ${est_cost:.2f} exceeds $20 sentinel.")
        print("Re-run with --confirm-cost to proceed.")
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
        "fitness_anchor": FITNESS_ANCHOR,
        "anchor_weight": ANCHOR_WEIGHT,
        "archive_max_size": ARCHIVE_MAX_SIZE,
        "archive_update_interval": ARCHIVE_UPDATE_INTERVAL,
        "archive_weight_total": ARCHIVE_WEIGHT_TOTAL,
        "sanity_opponents": list(SANITY_OPPONENTS),
        "param_space": {n: list(b) for n, b in PARAM_SPACE.items()},
        "baseline_config": asdict(HeuristicConfig.default()),
        "cma_options": {k: v for k, v in cma_opts.items() if k != "integer_variables"},
        "estimated_cost_usd": est_cost,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "config.json").write_text(json.dumps(config_blob, indent=2))

    # 6. CMA-ES loop with rolling archive
    best_fitness_so_far = float("-inf")
    best_cfg_dict_so_far: dict | None = None
    best_per_opp_so_far: dict | None = None
    accumulated_cost = 0.0
    gen_log_path = out_dir / "generations.jsonl"
    archive: list[dict] = []  # [{"name": str, "cfg_dict": dict, "added_gen": int}, ...]

    # Per-gen best history — used to pick the "robust BEST" at end of run.
    # Each entry: {gen, fitness, cfg_dict, per_opp, archive_size_at_eval}.
    # We pick the saved BEST from gens with the maximum archive_size_at_eval
    # ever seen, so the saved config has been measured against the toughest
    # fitness landscape that existed during the run (not against an early-
    # warmup landscape that no later candidate could beat).
    gen_best_history: list[dict] = []
    robust_best_archive_size: int = -1
    robust_best_fitness: float = float("-inf")
    robust_best_cfg: dict | None = None
    robust_best_per_opp: dict | None = None

    for gen in range(gens):
        gen_started = time.time()
        candidates_norm = es.ask()  # list of np.ndarray in normalized [0,1] space

        # Build the archive_opponents payload for this generation
        archive_opponents = [
            {"name": a["name"], "cfg_dict": a["cfg_dict"]} for a in archive
        ]
        archive_size_at_eval = len(archive_opponents)

        # Denormalize and decode each candidate to a HeuristicConfig dict
        args = []
        for i, c_norm in enumerate(candidates_norm):
            c_real = _denormalize(np.asarray(c_norm), lowers, uppers)
            cfg_dict = asdict(decode(c_real))
            args.append((
                cfg_dict, i, gen,
                sanity_n_per_opponent, fit_games, sanity_threshold,
                archive_opponents,
            ))

        # PARALLEL: dispatch all candidates to Modal.
        # return_exceptions=True is critical: without it, ANY single-input
        # failure (FunctionTimeoutError from preemption-restart, OOM, etc.)
        # propagates to the local driver and kills the whole sweep mid-run.
        # We map exceptions to a synthetic disqualified-result so CMA-ES sees
        # them as DISQUALIFIED_FITNESS and steers away from that region.
        raw_results = list(evaluate_fitness.starmap(args, return_exceptions=True))
        results = []
        n_failed_eval = 0
        for i, r in enumerate(raw_results):
            if isinstance(r, BaseException):
                n_failed_eval += 1
                _cfg_dict, cand_id, gen_id, *_ = args[i]
                empty_per_opp = {FITNESS_ANCHOR: 0.0}
                for arch in archive_opponents:
                    empty_per_opp[arch["name"]] = 0.0
                results.append({
                    "candidate_id": cand_id,
                    "generation": gen_id,
                    "sanity_pass": False,
                    "fitness": DISQUALIFIED_FITNESS,
                    "per_opp": empty_per_opp,
                    "sanity_winrates": {},
                    "wall_clock_seconds": 0.0,
                    "failure_reason": f"{type(r).__name__}: {r}",
                })
            else:
                results.append(r)
        if n_failed_eval:
            print(
                f"  [resilience] gen {gen}: {n_failed_eval}/{len(args)} candidates "
                f"failed infra-side (treated as disqualified)"
            )

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

        # Track gen-best for end-of-run robust selection
        gen_best_idx = fitnesses.index(gen_best)
        gen_best_result = results[gen_best_idx]
        gen_best_history.append({
            "gen": gen,
            "fitness": gen_best,
            "cfg_dict": args[gen_best_idx][0],
            "per_opp": gen_best_result["per_opp"],
            "archive_size_at_eval": archive_size_at_eval,
        })

        # Best-EVER tracker (informational — what was the highest fitness
        # ever seen, regardless of archive state). May be biased toward
        # early-archive gens with weaker fitness landscapes.
        if gen_best > best_fitness_so_far:
            best_fitness_so_far = gen_best
            best_cfg_dict_so_far = args[gen_best_idx][0]
            best_per_opp_so_far = gen_best_result["per_opp"]

        # Robust BEST: pick from generations with max archive_size_at_eval.
        # When archive grows (eval gen has > previous max archive size), reset
        # the running robust-best to this gen's best — earlier gens were
        # measured against an easier landscape and are no longer comparable.
        if archive_size_at_eval > robust_best_archive_size:
            robust_best_archive_size = archive_size_at_eval
            robust_best_fitness = gen_best
            robust_best_cfg = args[gen_best_idx][0]
            robust_best_per_opp = gen_best_result["per_opp"]
            _write_best_config_py(
                out_dir / "best_config.py",
                robust_best_cfg, run_id, robust_best_fitness, robust_best_per_opp,
            )
        elif archive_size_at_eval == robust_best_archive_size and gen_best > robust_best_fitness:
            robust_best_fitness = gen_best
            robust_best_cfg = args[gen_best_idx][0]
            robust_best_per_opp = gen_best_result["per_opp"]
            _write_best_config_py(
                out_dir / "best_config.py",
                robust_best_cfg, run_id, robust_best_fitness, robust_best_per_opp,
            )

        # Rolling archive update: every K gens, append current robust-best
        archive_event = None
        if (gen + 1) % ARCHIVE_UPDATE_INTERVAL == 0 and best_cfg_dict_so_far is not None:
            # Use best-ever for archive seeding (even if from earlier gen) — we
            # WANT the archive to include the strongest individuals as
            # opponents for next gens. Robust-best is for OUTPUT, not archive.
            new_entry = {
                "name": f"archive_gen{gen}",
                "cfg_dict": best_cfg_dict_so_far,
                "added_gen": gen,
            }
            archive.append(new_entry)
            evicted = None
            if len(archive) > ARCHIVE_MAX_SIZE:
                evicted = archive.pop(0)["name"]  # FIFO eviction
            archive_event = {
                "added": new_entry["name"],
                "evicted": evicted,
                "size_after": len(archive),
            }

        # Log generation
        # n_disqualified counts ALL DISQUALIFIED_FITNESS results (sanity-fail
        # plus infra-fail). n_failed_eval is the infra-fail subset, broken out
        # so we can tell "candidate was bad" from "Modal preempted/timed out."
        gen_record = {
            "gen": gen,
            "best_fitness": gen_best,
            "mean_fitness": gen_mean,
            "fitness_stddev": gen_std,
            "n_disqualified": n_disqualified,
            "n_failed_eval": n_failed_eval,
            "best_candidate": args[gen_best_idx][0],
            "per_opponent_breakdown": gen_best_result["per_opp"],
            "archive_size_at_eval": len(archive_opponents),  # what THIS gen used
            "archive_event": archive_event,                  # update at end of this gen
            "wall_clock_seconds": wall,
            "estimated_cost_usd": gen_cost,
            "accumulated_cost_usd": accumulated_cost,
        }
        with gen_log_path.open("a") as f:
            f.write(json.dumps(gen_record) + "\n")

        archive_str = (
            f"archive={len(archive_opponents)}"
            + (f"+1" if archive_event and archive_event["added"] else "")
        )
        print(
            f"gen {gen+1:>3}/{gens}  best={gen_best:+.4f}  mean={gen_mean:+.4f}  "
            f"stddev={gen_std:.4f}  disq={n_disqualified}/{pop} (infra-fail={n_failed_eval})  "
            f"{archive_str}  wall={wall:.0f}s  cost=${gen_cost:.2f}  total=${accumulated_cost:.2f}"
        )

    # 7. Write final report. The "BEST" we report is the ROBUST best — best
    # candidate from a generation with the maximum archive size achieved (i.e.,
    # measured against the toughest fitness landscape). best_fitness_so_far
    # is also reported for context (best ever seen, possibly biased to early
    # warmup gens).
    completed = datetime.now(timezone.utc).isoformat()
    config_blob["completed_at"] = completed
    config_blob["final_accumulated_cost_usd"] = accumulated_cost
    config_blob["robust_best_fitness"] = robust_best_fitness
    config_blob["robust_best_archive_size"] = robust_best_archive_size
    config_blob["best_ever_fitness"] = best_fitness_so_far
    (out_dir / "config.json").write_text(json.dumps(config_blob, indent=2))

    _write_final_report(
        out_dir / "final_report.md",
        run_id=run_id,
        profile=profile,
        gen_log_path=gen_log_path,
        best_cfg=robust_best_cfg if robust_best_archive_size >= 0 else best_cfg_dict_so_far,
        best_fitness=robust_best_fitness if robust_best_archive_size >= 0 else best_fitness_so_far,
        best_per_opp=robust_best_per_opp if robust_best_archive_size >= 0 else best_per_opp_so_far,
        accumulated_cost=accumulated_cost,
        baseline_cfg=asdict(HeuristicConfig.default()),
    )

    print("\n=== Done ===")
    print(f"  ROBUST best fitness  : {robust_best_fitness:+.4f}  (vs archive_size={robust_best_archive_size})")
    print(f"  best-EVER fitness    : {best_fitness_so_far:+.4f}  (informational)")
    if robust_best_archive_size >= 0:
        print(f"  ROBUST best per-opp  : {robust_best_per_opp}")
    print(f"  total cost spent     : ${accumulated_cost:.2f}")
    print(f"  output dir           : {out_dir}")
