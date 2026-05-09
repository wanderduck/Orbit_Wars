"""CMA-ES + Modal heuristic tuning framework for Orbit Wars HeuristicConfig.

VASTLY IMPROVED VERSION: Integrates ProcessPool multiprocessing for massive performance scaling
(bypassing the Python GIL locally in each Modal container), paired with intelligent
Successive Halving / Early Stopping logic to rapidly abort misconfigured candidates and
drastically slash wasted cloud compute costs.
"""

from __future__ import annotations

import sys
import concurrent.futures

if "/app/src" not in sys.path:
	sys.path.insert(0, "/app/src")

import json
import random
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from orbit_wars.heuristic.heuristic_overhaul.heuristic_tuner_param_space import (
	INT_DIM_INDICES, NUMERIC_FIELDS, PARAM_SPACE, decode, encode, validate_param_space,
	)

GLOBAL_TUNER_SEED = 42

OPPONENT_REGISTRY: dict[str, str] = {
	"aggressive_swarm": "orbit_wars.opponents.aggressive_swarm:agent",
	"defensive_turtle": "orbit_wars.opponents.defensive_turtle:agent",
	"peer_mdmahfuzsumon": "orbit_wars.opponents.peer_mdmahfuzsumon:agent",
	"v15g_stock": "orbit_wars.heuristic.heuristic_overhaul.strategy:agent",
	}


def _resolve_opponent(name: str):
	if name not in OPPONENT_REGISTRY:
		raise KeyError(f"Unknown opponent {name!r}.")
	module_path, attr = OPPONENT_REGISTRY[name].split(":", 1)
	import importlib
	mod = importlib.import_module(module_path)
	return getattr(mod, attr)


def make_configured_agent(cfg_dict: dict):
	from orbit_wars.heuristic.heuristic_overhaul.config import HeuristicConfig
	from orbit_wars.heuristic.heuristic_overhaul.strategy import agent as agent_strategy
	cfg = HeuristicConfig(**cfg_dict)

	def configured_agent(obs):
		return agent_strategy(obs, cfg)

	return configured_agent


def run_one_game(cfg_dict: dict, opponent_name: str, seed: int) -> float:
	from kaggle_environments import make
	me = make_configured_agent(cfg_dict)
	opponent_fn = _resolve_opponent(opponent_name)
	env = make("orbit_wars", configuration={"seed": seed}, debug=False)
	env.run([me, opponent_fn])
	last = env.steps[-1]
	return float(last[0].reward) - float(last[1].reward)


DISQUALIFIED_FITNESS: float = -1e9
FITNESS_ANCHOR: str = "v15g_stock"
SANITY_OPPONENTS: tuple[str, ...] = ("aggressive_swarm", "defensive_turtle")

ARCHIVE_MAX_SIZE: int = 3
ARCHIVE_UPDATE_INTERVAL: int = 3
ANCHOR_WEIGHT: float = 0.5
ARCHIVE_WEIGHT_TOTAL: float = 0.5


def _winrate(margins: list[float]) -> float:
	if not margins: return 0.0
	return sum(1 for m in margins if m > 0) / len(margins)


GRADUATED_RANK_SCORES: tuple[float, ...] = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)


def graduated_scores(asset_counts: list[float]) -> list[float]:
	indexed = sorted(enumerate(asset_counts), key=lambda kv: -kv[1])
	scores = [0.0] * 4
	i = 0
	while i < 4:
		j = i
		while j < 4 and indexed[j][1] == indexed[i][1]:
			j += 1
		tied_avg = sum(GRADUATED_RANK_SCORES[k] for k in range(i, j)) / (j - i)
		for k in range(i, j): scores[indexed[k][0]] = tied_avg
		i = j
	return scores


def _select_4p_opponents(
		archive_opponents: list[dict], default_cfg: dict, *, num_needed: int = 3, rng: random.Random | None = None
		) -> list[dict | str]:
	if rng is None: rng = random
	valid_archive = [o for o in archive_opponents if "cfg_dict" in o]
	if len(valid_archive) >= num_needed:
		return list(rng.sample(valid_archive, num_needed))
	chosen: list[dict | str] = list(valid_archive)
	while len(chosen) < num_needed:
		# Inject our tuned baseline to drastically boost evolutionary pressure
		chosen.append({"name": "v15g_stock", "cfg_dict": default_cfg})
	return chosen


def run_one_game_4p(candidate_cfg: dict, opponents: list[dict | str], seed: int) -> list[float]:
	from kaggle_environments import make
	agents: list = [make_configured_agent(candidate_cfg)]
	for opp in opponents:
		if opp == "starter":
			agents.append("starter")
		elif isinstance(opp, dict) and "cfg_dict" in opp:
			agents.append(make_configured_agent(opp["cfg_dict"]))
	env = make("orbit_wars", configuration={"seed": seed}, debug=False)
	env.run(agents)

	final_obs = env.steps[-1][0].observation
	max_owner = -1
	for p in final_obs.planets:
		if p[1] != -1 and p[1] > max_owner: max_owner = p[1]
	for f in final_obs.fleets:
		if f[1] > max_owner: max_owner = f[1]
	num_players = max_owner + 1

	if num_players <= 0: return [0.0] * 4
	assets = [0.0] * num_players
	for p in final_obs.planets:
		if p[1] != -1: assets[p[1]] += float(p[5])
	for f in final_obs.fleets: assets[f[1]] += float(f[6])

	while len(assets) < 4: assets.append(0.0)
	return graduated_scores(assets[:4])


def _run_one_game_wrapper(cfg_dict, opp, s):
	"""Module-level wrapper required for valid ProcessPoolExecutor Pickling."""
	return run_one_game(cfg_dict, opp, seed=s)


def _run_one_game_4p_wrapper(cfg_dict, archive_opponents, default_cfg, game_idx, global_seed):
	"""Module-level wrapper required for valid ProcessPoolExecutor Pickling."""
	rng = random.Random(global_seed + game_idx * 1000)
	opponents = _select_4p_opponents(archive_opponents, default_cfg, num_needed=3, rng=rng)
	return run_one_game_4p(cfg_dict, opponents, seed=game_idx)


def evaluate_fitness_local(
		cfg_dict: dict, candidate_id: int, generation: int, sanity_n_per_opponent: int = 10,
		fitness_n_per_opponent: int = 33, sanity_threshold: float = 0.91, archive_opponents: list[dict] | None = None,
		) -> dict:
	from orbit_wars.heuristic.heuristic_overhaul.config import HeuristicConfig

	random.seed(GLOBAL_TUNER_SEED + generation * 1000 + candidate_id)
	started = time.time()
	archive_opponents = archive_opponents or []
	default_cfg = asdict(HeuristicConfig.default())

	# ----- Sanity gate -----
	sanity_winrates: dict[str, float] = {}
	sanity_pass = True

	with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
		for opp in SANITY_OPPONENTS:
			futures = [executor.submit(_run_one_game_wrapper, cfg_dict, opp, s) for s in range(sanity_n_per_opponent)]
			margins = []
			for f in concurrent.futures.as_completed(futures):
				margins.append(f.result())
			wr = _winrate(margins)
			sanity_winrates[opp] = wr
			if wr < sanity_threshold:
				sanity_pass = False
				break

	if not sanity_pass:
		return {
			"candidate_id": candidate_id, "generation": generation, "sanity_pass": False,
			"fitness": DISQUALIFIED_FITNESS, "per_opp": {"4p_graduated": 0.0},
			"sanity_winrates": sanity_winrates, "wall_clock_seconds": time.time() - started,
			}

	# ----- Fitness phase: Parallel Multiprocessing + Successive Halving Early Stops -----
	candidate_scores: list[float] = []

	with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
		futures = []
		for game_idx in range(fitness_n_per_opponent):
			futures.append(executor.submit(_run_one_game_4p_wrapper, cfg_dict, archive_opponents, default_cfg, game_idx,
			                               GLOBAL_TUNER_SEED + generation * 100 + candidate_id))

		for i, f in enumerate(concurrent.futures.as_completed(futures)):
			scores = f.result()
			candidate_scores.append(scores[0])

			# Mathematical Early Stopping (Save massive Cloud Compute Costs)
			if i == 10 and sum(candidate_scores) / len(candidate_scores) < -0.4:
				for fut in futures:
					fut.cancel()
				candidate_scores.extend([-1.0] * (fitness_n_per_opponent - len(candidate_scores)))
				break

	fitness = sum(candidate_scores) / len(candidate_scores)

	return {
		"candidate_id": candidate_id, "generation": generation, "sanity_pass": True,
		"fitness": float(fitness), "per_opp": {"4p_graduated": float(fitness)},
		"sanity_winrates": sanity_winrates, "wall_clock_seconds": time.time() - started,
		}


def _write_best_config_py(path: Path, cfg_dict: dict, run_id: str, fitness: float, per_opp: dict) -> None:
	per_opp_str = ", ".join(f"{k}={v:+.4f}" for k, v in per_opp.items())
	field_lines = ",\n    ".join(f"{k}={v!r}" for k, v in sorted(cfg_dict.items()))
	path.write_text(
		f'"""Best config from CMA-ES run {run_id}.\n\nBest fitness: {fitness:+.4f}\nPer-opponent: {per_opp_str}\n"""\n\nfrom orbit_wars.heuristic.heuristic_overhaul.config import HeuristicConfig\n\nBEST = HeuristicConfig(\n    {field_lines},\n)\n')


def _write_final_report(
		path: Path, run_id: str, profile: str, gen_log_path: Path, best_cfg: dict | None, best_fitness: float,
		best_per_opp: dict | None, accumulated_cost: float, baseline_cfg: dict
		) -> None:
	if best_cfg is None: return path.write_text(f"# CMA-ES Run {run_id} — NO RESULTS\n")
	gen_records = [json.loads(line) for line in gen_log_path.read_text().strip().split('\n') if line]
	diffs = [f"| `{k}` | `{baseline_cfg.get(k)}` | `{best_cfg[k]}` | `{best_cfg[k] - baseline_cfg.get(k):+}` |" for k in
	         sorted(best_cfg) if isinstance(best_cfg[k], (int, float)) and baseline_cfg.get(k) != best_cfg[k]]
	diff_section = "\n".join(diffs) if diffs else "| (no changes) | | | |"
	md = f"""# CMA-ES Tuning Run — {run_id}\n\n**Total cost:** ${accumulated_cost:.2f}\n\n## Best vs baseline\n| Field | Baseline | Best | Δ |\n|-------|----------|------|---|\n{diff_section}"""
	path.write_text(md)


PROFILES: dict[str, tuple[int, int, int, float]] = {
	"smoke": (4, 1, 4, 0.20),
	"iteration": (20, 15, 33, 50.0),
	"default": (50, 15, 33, 130.0),
	"extended": (88, 69, 69, 260.0),
	"max-quality": (100, 30, 33, 500.0),
	}


def _choose_profile(profile_name, popsize_override, generations_override, fitness_games_override):
	popsize, generations, fitness_games, est_cost = PROFILES[profile_name]
	if popsize_override is not None: popsize = popsize_override
	if generations_override is not None: generations = generations_override
	if fitness_games_override is not None: fitness_games = fitness_games_override
	return popsize, generations, fitness_games, est_cost


def _build_cma_options(popsize: int, num_dims: int) -> dict:
	return {
		"popsize": popsize, "bounds": [[0.0] * num_dims, [1.0] * num_dims], "integer_variables": INT_DIM_INDICES,
		"tolfun": 1e-3, "verbose": -9, "seed": GLOBAL_TUNER_SEED
		}


def _normalize(x: np.ndarray, lowers: np.ndarray, uppers: np.ndarray) -> np.ndarray: return (x - lowers) / (
			uppers - lowers)


def _denormalize(x_norm: np.ndarray, lowers: np.ndarray, uppers: np.ndarray) -> np.ndarray: return lowers + x_norm * (
			uppers - lowers)


import modal

MINUTES = 60

tuner_image = (
	modal.Image.debian_slim(python_version="3.13")
	.uv_pip_install("cma>=3.3.0", "scipy>=1.14", "numpy>=2.0", "kaggle_environments>=1.18.0")
	.add_local_dir(local_path=str(Path(__file__).parent.parent), remote_path="/app/src", copy=True)
)

app = modal.App("orbit-wars-cma-tuner", image=tuner_image)


@app.function(image=tuner_image, cpu=4.0, memory=4096, timeout=120 * MINUTES)
def evaluate_fitness(
		cfg_dict, candidate_id, generation, sanity_n_per_opponent, fitness_n_per_opponent, sanity_threshold,
		archive_opponents=None
		):
	import sys as _sys
	if "/app/src" not in _sys.path: _sys.path.insert(0, "/app/src")
	return evaluate_fitness_local(cfg_dict, candidate_id, generation, sanity_n_per_opponent, fitness_n_per_opponent,
	                              sanity_threshold, archive_opponents)


@app.local_entrypoint()
def main(
		smoke: bool = False, iteration: bool = False, extended: bool = False, max_quality: bool = False,
		popsize: int = 0, generations: int = 0, fitness_games_per_opponent: int = 0,
		sanity_n_per_opponent: int = 10, sanity_threshold: float = 0.91, confirm_cost: bool = False,
		output_root: str = "docs/research_documents/tuning_runs",
		):
	import cma
	profile = "smoke" if smoke else "iteration" if iteration else "extended" if extended else "max-quality" if max_quality else "default"
	pop, gens, fit_games, est_cost = _choose_profile(profile, popsize if popsize > 0 else None,
	                                                 generations if generations > 0 else None,
	                                                 fitness_games_per_opponent if fitness_games_per_opponent > 0 else None)

	validate_param_space()
	run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
	out_dir = Path(output_root) / run_id
	out_dir.mkdir(parents=True, exist_ok=True)

	from orbit_wars.heuristic.heuristic_overhaul.config import HeuristicConfig
	lowers = np.array([PARAM_SPACE[n][0] for n in NUMERIC_FIELDS], dtype=np.float64)
	uppers = np.array([PARAM_SPACE[n][1] for n in NUMERIC_FIELDS], dtype=np.float64)
	x0_real = encode(HeuristicConfig.default())
	x0_norm = _normalize(x0_real, lowers, uppers)
	cma_opts = _build_cma_options(pop, num_dims=len(NUMERIC_FIELDS))
	es = cma.CMAEvolutionStrategy(x0_norm.tolist(), 0.25, cma_opts)

	best_fitness_so_far, best_cfg_dict_so_far, best_per_opp_so_far = float("-inf"), None, None
	accumulated_cost = 0.0
	gen_log_path = out_dir / "generations.jsonl"
	archive = []
	robust_best_archive_size, robust_best_fitness, robust_best_cfg, robust_best_per_opp = -1, float("-inf"), None, None

	for gen in range(gens):
		gen_started = time.time()
		candidates_norm = es.ask()
		archive_opponents = [{"name": a["name"], "cfg_dict": a["cfg_dict"]} for a in archive]
		archive_size_at_eval = len(archive_opponents)

		args = [
			(asdict(decode(_denormalize(np.asarray(c_norm), lowers, uppers))), i, gen, sanity_n_per_opponent, fit_games,
			 sanity_threshold, archive_opponents) for i, c_norm in enumerate(candidates_norm)]
		raw_results = list(evaluate_fitness.starmap(args, return_exceptions=True))

		results, n_failed_eval = [], 0
		for i, r in enumerate(raw_results):
			if isinstance(r, BaseException):
				n_failed_eval += 1
				empty_per_opp = {FITNESS_ANCHOR: 0.0}
				for arch in archive_opponents: empty_per_opp[arch["name"]] = 0.0
				results.append({
					               "candidate_id": args[i][1], "generation": gen, "sanity_pass": False,
					               "fitness": DISQUALIFIED_FITNESS, "per_opp": empty_per_opp, "sanity_winrates": {},
					               "wall_clock_seconds": 0.0, "failure_reason": str(r)
					               })
			else:
				results.append(r)

		results.sort(key=lambda r: r["candidate_id"])
		fitnesses = [r["fitness"] for r in results]
		es.tell(candidates_norm, [-f for f in fitnesses])

		gen_best = max(fitnesses)
		gen_cost = sum(r["wall_clock_seconds"] * 2 * 0.000131 for r in results)
		accumulated_cost += gen_cost
		gen_best_idx = fitnesses.index(gen_best)
		gen_best_result = results[gen_best_idx]

		if gen_best > best_fitness_so_far:
			best_fitness_so_far, best_cfg_dict_so_far, best_per_opp_so_far = gen_best, args[gen_best_idx][0], \
			gen_best_result["per_opp"]

		if archive_size_at_eval > robust_best_archive_size or (
				archive_size_at_eval == robust_best_archive_size and gen_best > robust_best_fitness):
			robust_best_archive_size, robust_best_fitness, robust_best_cfg, robust_best_per_opp = archive_size_at_eval, gen_best, \
			args[gen_best_idx][0], gen_best_result["per_opp"]
			_write_best_config_py(out_dir / "best_config.py", robust_best_cfg, run_id, robust_best_fitness,
			                      robust_best_per_opp)

		archive_event = None
		if (gen + 1) % ARCHIVE_UPDATE_INTERVAL == 0 and best_cfg_dict_so_far is not None:
			new_entry = {"name": f"archive_gen{gen}", "cfg_dict": best_cfg_dict_so_far, "added_gen": gen}
			archive.append(new_entry)
			archive_event = {
				"added": new_entry["name"],
				"evicted": archive.pop(0)["name"] if len(archive) > ARCHIVE_MAX_SIZE else None,
				"size_after": len(archive)
				}

		with gen_log_path.open("a") as f:
			f.write(json.dumps({
				                   "gen": gen, "best_fitness": gen_best, "n_failed_eval": n_failed_eval,
				                   "wall_clock_seconds": time.time() - gen_started,
				                   "accumulated_cost_usd": accumulated_cost
				                   }) + "\n")
		print(f"gen {gen + 1:>3}/{gens}  best={gen_best:+.4f}  cost=${gen_cost:.2f}  total=${accumulated_cost:.2f}")

	_write_final_report(out_dir / "final_report.md", run_id, profile, gen_log_path,
	                    robust_best_cfg if robust_best_archive_size >= 0 else best_cfg_dict_so_far,
	                    robust_best_fitness if robust_best_archive_size >= 0 else best_fitness_so_far,
	                    robust_best_per_opp if robust_best_archive_size >= 0 else best_per_opp_so_far, accumulated_cost,
	                    asdict(HeuristicConfig.default()))
	print("\n=== Done ===")