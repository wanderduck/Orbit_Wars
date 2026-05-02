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

import random
import time
from pathlib import Path

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
