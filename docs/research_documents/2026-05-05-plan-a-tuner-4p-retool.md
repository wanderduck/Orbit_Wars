# Plan A — 4P Tuner Retool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retool `src/tools/modal_tuner.py` so each fitness eval runs N=33 4P FFA games (candidate + 3 archive samples, falling back to `starter` when archive is small) and scores by graduated placement (1st=+1, 2nd=+1/3, 3rd=−1/3, 4th=−1). Launch one CMA-ES sweep on Modal and submit the resulting BEST config to the Kaggle ladder.

**Architecture:** In-place modification. Add 4P helpers (`graduated_scores`, `compute_player_assets`, `run_one_game_4p`, `_select_4p_opponents`); modify `evaluate_fitness_local` to use 4P games for the fitness phase. Keep the existing 2P sanity gate intact (testing baseline competence vs. fixed opponents). Preserve all anti-regression invariants (resilient starmap, robust-BEST save, 120-min timeout).

**Tech Stack:** Python 3.13, `cma` library, `kaggle_environments`, Modal, pytest, `uv`.

**Companion spec:** `docs/research_documents/2026-05-05-mcts-path-a-c-kickoff.md` (Section 2).

---

## File structure

| File | Role | Change |
|---|---|---|
| `src/tools/modal_tuner.py` | Tuner entrypoint (Modal app + CMA-ES loop) | Add 4 helpers + modify `evaluate_fitness_local`; keep 2P helpers for sanity + fallback |
| `tests/test_modal_tuner_4p.py` | Unit tests for new helpers | Create |
| `docs/research_documents/tuning_runs/<run-id>/` | Sweep output (auto-created) | Run output |
| `submission-bestv5-<date>.tar.gz` | Submission tarball | Build at end |

---

## Task 1: graduated_scores pure helper

**Files:**
- Modify: `src/tools/modal_tuner.py` (add new function near other helpers ~line 188)
- Test: `tests/test_modal_tuner_4p.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_modal_tuner_4p.py`:

```python
"""Unit tests for the 4P-retool helpers added to modal_tuner."""
from __future__ import annotations

import math

import pytest

from tools.modal_tuner import graduated_scores


class TestGraduatedScores:
    def test_distinct_counts_returns_canonical_ranks(self):
        # Player order [P0, P1, P2, P3] with assets [100, 50, 25, 10]
        # Ranks: P0=1st(+1), P1=2nd(+1/3), P2=3rd(-1/3), P3=4th(-1)
        scores = graduated_scores([100, 50, 25, 10])
        assert scores == pytest.approx([1.0, 1.0 / 3, -1.0 / 3, -1.0])

    def test_two_way_tie_at_top_averages(self):
        # [50, 50, 25, 10] → P0,P1 tied at ranks 1-2 → (1 + 1/3)/2 = 2/3
        scores = graduated_scores([50, 50, 25, 10])
        assert scores[0] == pytest.approx(2.0 / 3)
        assert scores[1] == pytest.approx(2.0 / 3)
        assert scores[2] == pytest.approx(-1.0 / 3)
        assert scores[3] == pytest.approx(-1.0)

    def test_two_way_tie_in_middle_zero(self):
        # [100, 50, 50, 10] → P1,P2 tied at ranks 2-3 → (1/3 + -1/3)/2 = 0
        scores = graduated_scores([100, 50, 50, 10])
        assert scores == pytest.approx([1.0, 0.0, 0.0, -1.0])

    def test_three_way_tie_at_bottom(self):
        # [100, 50, 50, 50] → P1,P2,P3 tied at 2-3-4 → (1/3 + -1/3 + -1)/3 = -1/3
        scores = graduated_scores([100, 50, 50, 50])
        assert scores[0] == pytest.approx(1.0)
        assert scores[1] == pytest.approx(-1.0 / 3)
        assert scores[2] == pytest.approx(-1.0 / 3)
        assert scores[3] == pytest.approx(-1.0 / 3)

    def test_all_equal_all_zero(self):
        # 4-way tie at 1-2-3-4 → (1 + 1/3 + -1/3 + -1)/4 = 0
        scores = graduated_scores([42, 42, 42, 42])
        for s in scores:
            assert math.isclose(s, 0.0, abs_tol=1e-9)

    def test_preserves_player_order_not_rank_order(self):
        # Returns scores in the same order as the input, NOT sorted
        scores = graduated_scores([10, 100, 25, 50])
        # Ranks: P1(100)=1st, P3(50)=2nd, P2(25)=3rd, P0(10)=4th
        assert scores == pytest.approx([-1.0, 1.0, -1.0 / 3, 1.0 / 3])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_modal_tuner_4p.py -v`
Expected: ImportError or AttributeError (`graduated_scores` not defined yet).

- [ ] **Step 3: Implement `graduated_scores`**

Edit `src/tools/modal_tuner.py`, add after the `_winrate` function (~line 195):

```python
# Graduated placement scoring constants for 4P FFA fitness.
# Per kickoff brief Section 2.2: 1st=+1, 2nd=+1/3, 3rd=-1/3, 4th=-1.
RANK_SCORES_4P: tuple[float, ...] = (1.0, 1.0 / 3, -1.0 / 3, -1.0)


def graduated_scores(asset_counts: list[float]) -> list[float]:
    """Convert per-player final asset counts → graduated placement scores.

    Returns scores in the SAME ORDER as the input (NOT sorted by rank). Ties
    at any rank are resolved by averaging the canonical scores for the tied
    rank positions.

    Per kickoff brief Section 2.2:
        1st = +1, 2nd = +1/3, 3rd = -1/3, 4th = -1.
        Ties: average the canonical scores for the tied positions.
        Example: 2-way tie at ranks 1-2 → both get (1 + 1/3)/2 = 2/3.

    Args:
        asset_counts: sequence of length 4 (one per player). Higher = better.
    """
    n = len(asset_counts)
    if n != len(RANK_SCORES_4P):
        raise ValueError(
            f"graduated_scores requires exactly 4 players; got {n}"
        )
    # Sort player indices by asset count descending; stable order
    order = sorted(range(n), key=lambda i: asset_counts[i], reverse=True)

    # Walk groups of tied counts; assign mean of canonical rank scores
    scores = [0.0] * n
    i = 0
    while i < n:
        j = i + 1
        # Extend group while next player has same asset count
        while j < n and asset_counts[order[j]] == asset_counts[order[i]]:
            j += 1
        tied_indices = order[i:j]
        mean_score = sum(RANK_SCORES_4P[i:j]) / (j - i)
        for idx in tied_indices:
            scores[idx] = mean_score
        i = j
    return scores
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestGraduatedScores -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git status -s   # verify only the two intended files staged
git add src/tools/modal_tuner.py tests/test_modal_tuner_4p.py
git commit -m "$(cat <<'EOF'
feat(tuner): add graduated_scores helper for 4P placement fitness

Pure helper that maps per-player asset counts to graduated placement
scores (1st=+1, 2nd=+1/3, 3rd=-1/3, 4th=-1) with tie-averaging. First
piece of the 4P-retool per kickoff brief Section 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: compute_player_assets pure helper

The env's per-player reward is binary (+1/-1), but graduated fitness needs continuous final-asset counts. Walk the final observation and sum owned planets' ships + in-flight fleet ships. Per env L679-711 reward calc.

**Files:**
- Modify: `src/tools/modal_tuner.py`
- Test: `tests/test_modal_tuner_4p.py`

- [ ] **Step 1: Add tests to `tests/test_modal_tuner_4p.py`**

Append:

```python
class TestComputePlayerAssets:
    def test_owned_planets_only(self):
        from tools.modal_tuner import compute_player_assets

        # Env planet shape: [id, owner, x, y, radius, ships, production]
        obs = type("Obs", (), {})()
        obs.planets = [
            [0, 0, 0, 0, 2, 50, 1],  # owned by player 0, 50 ships
            [1, 0, 1, 1, 2, 25, 1],  # owned by player 0, 25 ships
            [2, 1, 2, 2, 2, 80, 1],  # owned by player 1, 80 ships
        ]
        obs.fleets = []
        assert compute_player_assets(obs, player_id=0) == 75
        assert compute_player_assets(obs, player_id=1) == 80
        assert compute_player_assets(obs, player_id=2) == 0

    def test_includes_in_flight_fleets(self):
        from tools.modal_tuner import compute_player_assets

        # Env fleet shape: [id, owner, x, y, angle, from_id, ships]
        obs = type("Obs", (), {})()
        obs.planets = [
            [0, 0, 0, 0, 2, 30, 1],  # player 0: 30 on planet
        ]
        obs.fleets = [
            [10, 0, 5, 5, 0.0, 0, 12],  # player 0: 12 in flight
            [11, 1, 6, 6, 0.0, 0, 99],  # player 1: 99 in flight
        ]
        assert compute_player_assets(obs, player_id=0) == 42
        assert compute_player_assets(obs, player_id=1) == 99

    def test_eliminated_player_returns_zero(self):
        from tools.modal_tuner import compute_player_assets

        obs = type("Obs", (), {})()
        obs.planets = [
            [0, -1, 0, 0, 2, 10, 1],  # neutral
            [1, 0, 1, 1, 2, 100, 1],  # player 0
        ]
        obs.fleets = []
        assert compute_player_assets(obs, player_id=2) == 0
        assert compute_player_assets(obs, player_id=-1) == 0  # don't sum neutrals
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestComputePlayerAssets -v`
Expected: ImportError (`compute_player_assets` not defined).

- [ ] **Step 3: Implement**

Add to `src/tools/modal_tuner.py` immediately after `graduated_scores`:

```python
def compute_player_assets(observation, player_id: int) -> int:
    """Sum of ships owned by `player_id` (planets + in-flight fleets).

    Mirrors env L687-693 reward computation: a player's "score" is total ships
    on their owned planets plus total ships in their in-flight fleets.

    `observation` may be a dict OR a Struct (env observations are Structs;
    accept both for test ergonomics). Uses attribute access.

    Returns 0 for player_id that owns nothing (eliminated or never-existed).
    """
    total = 0
    # Env planet shape: [id, owner, x, y, radius, ships, production]
    for p in observation.planets:
        if p[1] == player_id:
            total += int(p[5])
    # Env fleet shape: [id, owner, x, y, angle, from_id, ships]
    for f in observation.fleets:
        if f[1] == player_id:
            total += int(f[6])
    return total
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestComputePlayerAssets -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/tools/modal_tuner.py tests/test_modal_tuner_4p.py
git commit -m "$(cat <<'EOF'
feat(tuner): add compute_player_assets for graduated 4P fitness

Reads final observation, sums ships on player-owned planets and in
player-owned in-flight fleets. Mirrors env L687-693 reward calc.
Needed because env's per-player reward is binary; graduated placement
needs the underlying continuous asset count.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: run_one_game_4p — 4-agent game runner

**Files:**
- Modify: `src/tools/modal_tuner.py`
- Test: `tests/test_modal_tuner_4p.py`

- [ ] **Step 1: Add a test to `tests/test_modal_tuner_4p.py`**

Append:

```python
class TestRunOneGame4P:
    def test_returns_four_graduated_scores(self):
        from dataclasses import asdict

        from orbit_wars.heuristic.config import HeuristicConfig
        from tools.modal_tuner import run_one_game_4p

        default_dict = asdict(HeuristicConfig.default())
        # 4 identical configs → asset counts may differ from random/seed but
        # graduated_scores returns 4 floats in [-1, +1].
        scores = run_one_game_4p(
            agents=[default_dict, default_dict, default_dict, default_dict],
            seed=11,
        )
        assert len(scores) == 4
        for s in scores:
            assert -1.0 <= s <= 1.0

    def test_accepts_string_opponents(self):
        from dataclasses import asdict

        from orbit_wars.heuristic.config import HeuristicConfig
        from tools.modal_tuner import run_one_game_4p

        default_dict = asdict(HeuristicConfig.default())
        # Mix dict-cfg with built-in env agent names. "starter" is the
        # always-available env-built-in opponent.
        scores = run_one_game_4p(
            agents=[default_dict, "starter", "starter", "starter"],
            seed=13,
        )
        assert len(scores) == 4
        for s in scores:
            assert -1.0 <= s <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestRunOneGame4P -v`
Expected: ImportError (`run_one_game_4p` not defined).

- [ ] **Step 3: Implement**

Add to `src/tools/modal_tuner.py` after `run_one_game_vs_config`:

```python
def run_one_game_4p(
    agents: list[dict | str], seed: int,
) -> list[float]:
    """Run one 4P FFA game; return per-player graduated placement scores.

    `agents` is a list of length 4. Each entry is EITHER:
      - a `dict` of HeuristicConfig field values (wrapped via make_configured_agent), OR
      - a `str` interpreted as either an OPPONENT_REGISTRY key or a
        kaggle_environments built-in agent name (e.g. "starter", "random").

    Returns a length-4 list of graduated scores aligned with `agents` order
    (index 0's score is the first agent's score). Per-player scores are
    computed by summing the final observation's planets + fleets per player
    (compute_player_assets) and ranking by graduated_scores.

    Seed semantics match run_one_game: deterministic per call within a process.
    """
    from kaggle_environments import make

    if len(agents) != 4:
        raise ValueError(f"run_one_game_4p requires 4 agents; got {len(agents)}")

    resolved: list = []
    for a in agents:
        if isinstance(a, dict):
            resolved.append(make_configured_agent(a))
        elif isinstance(a, str):
            # Try our local registry first; fall back to env built-in name.
            if a in OPPONENT_REGISTRY:
                resolved.append(_resolve_opponent(a))
            else:
                resolved.append(a)  # let kaggle_environments resolve built-ins
        else:
            raise TypeError(f"agents[i] must be dict or str; got {type(a).__name__}")

    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run(resolved)
    final_obs = env.steps[-1][0].observation
    asset_counts = [compute_player_assets(final_obs, pid) for pid in range(4)]
    return graduated_scores(asset_counts)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestRunOneGame4P -v`
Expected: 2 passed (these are slower; each runs a full episode — ~10-20s each).

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/tools/modal_tuner.py tests/test_modal_tuner_4p.py
git commit -m "$(cat <<'EOF'
feat(tuner): add run_one_game_4p — 4P FFA game runner with graduated scoring

Accepts dict-configs OR string opponent names (registry + env built-ins).
Returns graduated placement scores per player in input order. Composes
make_configured_agent + compute_player_assets + graduated_scores.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: _select_4p_opponents — archive sampling with starter fallback

**Files:**
- Modify: `src/tools/modal_tuner.py`
- Test: `tests/test_modal_tuner_4p.py`

- [ ] **Step 1: Add a test**

Append to `tests/test_modal_tuner_4p.py`:

```python
class TestSelect4POpponents:
    def test_empty_archive_returns_three_starters(self):
        from tools.modal_tuner import _select_4p_opponents

        opps = _select_4p_opponents(archive=[], seed=0)
        assert opps == ["starter", "starter", "starter"]

    def test_one_archive_entry_pads_with_two_starters(self):
        from tools.modal_tuner import _select_4p_opponents

        archive = [{"name": "g3", "cfg_dict": {"foo": 1}}]
        opps = _select_4p_opponents(archive=archive, seed=0)
        # Order is "archive entries first, then starter padding"
        assert opps[0] == archive[0]["cfg_dict"]
        assert opps[1] == "starter"
        assert opps[2] == "starter"

    def test_full_archive_returns_three_archive_entries(self):
        from tools.modal_tuner import _select_4p_opponents

        archive = [
            {"name": "g3", "cfg_dict": {"a": 1}},
            {"name": "g6", "cfg_dict": {"b": 2}},
            {"name": "g9", "cfg_dict": {"c": 3}},
        ]
        opps = _select_4p_opponents(archive=archive, seed=0)
        assert len(opps) == 3
        assert all(isinstance(o, dict) for o in opps)
        # Should contain exactly the 3 archive cfgs (order may vary by seed)
        cfgs = [o for o in opps]
        assert {tuple(sorted(c.items())) for c in cfgs} == {
            (("a", 1),), (("b", 2),), (("c", 3),)
        }

    def test_oversize_archive_samples_three(self):
        import random as _rand
        from tools.modal_tuner import _select_4p_opponents

        archive = [
            {"name": f"g{i}", "cfg_dict": {"i": i}} for i in range(5)
        ]
        opps = _select_4p_opponents(archive=archive, seed=42)
        assert len(opps) == 3
        # Deterministic with seed: re-run same call → same selection
        opps2 = _select_4p_opponents(archive=archive, seed=42)
        assert opps == opps2

    def test_different_seed_may_select_differently(self):
        from tools.modal_tuner import _select_4p_opponents

        archive = [
            {"name": f"g{i}", "cfg_dict": {"i": i}} for i in range(5)
        ]
        # With different seeds we expect to see different orderings or
        # selections at least some of the time across many seeds.
        seen = set()
        for s in range(20):
            opps = _select_4p_opponents(archive=archive, seed=s)
            seen.add(tuple(sorted(o["i"] for o in opps)))
        assert len(seen) > 1, "Sampling appears deterministic across seeds"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestSelect4POpponents -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Add to `src/tools/modal_tuner.py` (near other archive helpers, ~line 410):

```python
def _select_4p_opponents(
    archive: list[dict], seed: int, fallback_name: str = "starter",
) -> list[dict | str]:
    """Pick 3 opponent slots for one 4P fitness game.

    Returns a length-3 list. Each entry is either a `cfg_dict` (from the
    archive) or a string `fallback_name` (default "starter") used to pad
    when the archive has fewer than 3 entries.

    When `len(archive) >= 3`, samples 3 entries WITHOUT replacement using a
    local Random seeded by `seed` (reproducible per call; does not perturb
    Python's global RNG). When `len(archive) < 3`, takes ALL archive cfgs
    in their stored order then pads with `fallback_name`.
    """
    import random as _rand

    if len(archive) < 3:
        # Order: archive entries (stored order) then fallback padding
        cfgs: list[dict | str] = [a["cfg_dict"] for a in archive]
        cfgs.extend([fallback_name] * (3 - len(archive)))
        return cfgs

    rng = _rand.Random(seed)
    sampled = rng.sample(archive, k=3)
    return [a["cfg_dict"] for a in sampled]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestSelect4POpponents -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/tools/modal_tuner.py tests/test_modal_tuner_4p.py
git commit -m "$(cat <<'EOF'
feat(tuner): add _select_4p_opponents for archive-driven 4P slots

Picks 3 opponent slots: 3 archive samples when archive>=3 (seeded RNG,
no global state perturbation), else all archive entries padded with
'starter'. Used by 4P fitness phase per kickoff brief Section 2.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Modify evaluate_fitness_local — replace 2P fitness with 4P graduated

**Files:**
- Modify: `src/tools/modal_tuner.py` (`evaluate_fitness_local` function)
- Test: `tests/test_modal_tuner_4p.py`

The sanity gate (2P vs SANITY_OPPONENTS) STAYS UNCHANGED. The fitness phase is replaced. Per-opponent reporting changes from `{opp_name: avg_margin}` to `{game_idx: graduated_score}` aggregated to mean.

- [ ] **Step 1: Add a test**

Append to `tests/test_modal_tuner_4p.py`:

```python
class TestEvaluateFitnessLocal4P:
    def test_returns_4p_fitness_with_empty_archive(self):
        from dataclasses import asdict

        from orbit_wars.heuristic.config import HeuristicConfig
        from tools.modal_tuner import evaluate_fitness_local

        default_dict = asdict(HeuristicConfig.default())
        # With games_per_eval=2 to keep the test fast (~30-60s).
        result = evaluate_fitness_local(
            cfg_dict=default_dict,
            candidate_id=0,
            generation=0,
            sanity_n_per_opponent=2,
            games_per_eval=2,
            sanity_threshold=0.0,         # disable sanity filter for the test
            archive_opponents=[],
        )
        assert result["sanity_pass"] is True
        assert "fitness" in result
        assert -1.0 <= result["fitness"] <= 1.0
        assert "per_game_scores" in result
        assert len(result["per_game_scores"]) == 2
        assert result["games_per_eval"] == 2
        assert result["archive_size_at_eval"] == 0

    def test_disqualifies_on_sanity_fail(self):
        from dataclasses import asdict

        from orbit_wars.heuristic.config import HeuristicConfig
        from tools.modal_tuner import DISQUALIFIED_FITNESS, evaluate_fitness_local

        default_dict = asdict(HeuristicConfig.default())
        result = evaluate_fitness_local(
            cfg_dict=default_dict,
            candidate_id=0,
            generation=0,
            sanity_n_per_opponent=1,
            games_per_eval=2,
            sanity_threshold=2.0,         # impossibly high → guaranteed fail
            archive_opponents=[],
        )
        assert result["sanity_pass"] is False
        assert result["fitness"] == DISQUALIFIED_FITNESS
        # No per-game scores when sanity fails — early exit
        assert result.get("per_game_scores", []) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestEvaluateFitnessLocal4P -v`
Expected: TypeError (unknown kwarg `games_per_eval`) OR sanity_pass test fails because old 2P fitness path is still in use.

- [ ] **Step 3: Modify `evaluate_fitness_local` to use 4P graduated fitness**

Replace the function body in `src/tools/modal_tuner.py`. Find the existing function (~line 296-385) and replace with:

```python
def evaluate_fitness_local(
    cfg_dict: dict,
    candidate_id: int,
    generation: int,
    sanity_n_per_opponent: int = 10,
    games_per_eval: int = 33,
    sanity_threshold: float = 0.91,
    archive_opponents: list[dict] | None = None,
    # Backward-compat shim — old callers may still pass this; ignored.
    fitness_n_per_opponent: int | None = None,
) -> dict:
    """Run sanity gate (2P), then 4P graduated fitness games. Pure Python; no Modal.

    Sanity gate is unchanged from the 2P version: candidate must beat each
    SANITY_OPPONENTS entry at >= sanity_threshold winrate over
    sanity_n_per_opponent games.

    Fitness phase (NEW per 2026-05-05 retool): runs `games_per_eval` 4P FFA
    games. Each game's opponent slots are filled by `_select_4p_opponents`
    (3 archive samples when len(archive) >= 3, else padded with 'starter').
    Per game, `graduated_scores` ranks the 4 players by final asset count
    (planets+fleets) and returns scores in [-1, +1]. Candidate's score is
    index 0. Fitness = mean of per-game candidate scores across N games.

    Reseeds Python's global random state once at entry so games are
    reproducible across containers. Each opponent-selection call uses a
    DIFFERENT seed (game_idx) so different games sample different opponents
    when archive is large.
    """
    random.seed(GLOBAL_TUNER_SEED)
    started = time.time()
    archive_opponents = archive_opponents or []

    # ----- Sanity gate (UNCHANGED — still 2P vs SANITY_OPPONENTS) -----
    sanity_winrates: dict[str, float] = {}
    sanity_pass = True
    for opp in SANITY_OPPONENTS:
        margins = [run_one_game(cfg_dict, opp, seed=s)
                   for s in range(sanity_n_per_opponent)]
        wr = _winrate(margins)
        sanity_winrates[opp] = wr
        if wr < sanity_threshold:
            sanity_pass = False
            break

    if not sanity_pass:
        return {
            "candidate_id": candidate_id,
            "generation": generation,
            "sanity_pass": False,
            "fitness": DISQUALIFIED_FITNESS,
            "per_game_scores": [],
            "games_per_eval": games_per_eval,
            "archive_size_at_eval": len(archive_opponents),
            "sanity_winrates": sanity_winrates,
            "wall_clock_seconds": time.time() - started,
        }

    # ----- Fitness phase: N 4P FFA games with graduated placement -----
    per_game_scores: list[float] = []
    for game_idx in range(games_per_eval):
        # Seed for opponent SELECTION (different per game so we sample
        # different archive subsets when archive size > 3).
        opp_seed = GLOBAL_TUNER_SEED * 1000 + game_idx
        opp_specs = _select_4p_opponents(
            archive=archive_opponents, seed=opp_seed, fallback_name="starter",
        )
        agents = [cfg_dict, *opp_specs]
        # Env seed: distinct per game so we don't replay the same RNG stream.
        env_seed = game_idx
        scores_4p = run_one_game_4p(agents=agents, seed=env_seed)
        per_game_scores.append(scores_4p[0])  # candidate is index 0

    fitness = sum(per_game_scores) / len(per_game_scores)

    return {
        "candidate_id": candidate_id,
        "generation": generation,
        "sanity_pass": True,
        "fitness": float(fitness),
        "per_game_scores": per_game_scores,
        "games_per_eval": games_per_eval,
        "archive_size_at_eval": len(archive_opponents),
        "sanity_winrates": sanity_winrates,
        "wall_clock_seconds": time.time() - started,
    }
```

- [ ] **Step 4: Update the Modal-side `evaluate_fitness` wrapper signature**

Find the `@app.function evaluate_fitness` (~line 506-533) and update its signature + body to match:

```python
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
    games_per_eval: int,
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
        games_per_eval=games_per_eval,
        sanity_threshold=sanity_threshold,
        archive_opponents=archive_opponents,
    )
```

- [ ] **Step 5: Update the local entrypoint's call site**

In the `main()` function (~line 668-676), find this block:

```python
        args = []
        for i, c_norm in enumerate(candidates_norm):
            c_real = _denormalize(np.asarray(c_norm), lowers, uppers)
            cfg_dict = asdict(decode(c_real))
            args.append((
                cfg_dict, i, gen,
                sanity_n_per_opponent, fit_games, sanity_threshold,
                archive_opponents,
            ))
```

Rename `fit_games` references to `games_per_eval` in this scope (both the variable from `_choose_profile` return and the kwarg). Update the rename in `_choose_profile` itself (~line 416-452):

Find:

```python
def _choose_profile(
    profile_name: str,
    popsize_override: int | None,
    generations_override: int | None,
    fitness_games_override: int | None,
) -> tuple[int, int, int, float]:
```

Replace with (rename and update internal var):

```python
def _choose_profile(
    profile_name: str,
    popsize_override: int | None,
    generations_override: int | None,
    games_per_eval_override: int | None,
) -> tuple[int, int, int, float]:
    """Resolve profile preset + per-flag overrides → (popsize, gens, games_per_eval, est_cost).

    `games_per_eval` is the number of 4P FFA games per candidate per
    generation (kickoff brief Section 2; default N=33).
    """
    if profile_name not in PROFILES:
        raise ValueError(
            f"Unknown profile {profile_name!r}. Choose from: {sorted(PROFILES)}"
        )
    popsize, generations, games_per_eval, est_cost = PROFILES[profile_name]
    if popsize_override is not None:
        popsize = popsize_override
    if generations_override is not None:
        generations = generations_override
    if games_per_eval_override is not None:
        games_per_eval = games_per_eval_override
    # Recompute estimated cost if any override applied.
    # 4P games ~= 2× 2P wall-clock (4 agent calls/turn vs 2). Keep the same
    # 0.000131 $/cpu-sec multiplier from the original cost model. Sanity
    # phase cost is unchanged (still 2P).
    if (popsize_override, generations_override, games_per_eval_override) != (None, None, None):
        sanity_n = 10
        per_pass_sec = (
            sanity_n * len(SANITY_OPPONENTS) * 3        # 3 sec/2P-game
            + games_per_eval * 6                          # 6 sec/4P-game (~2x 2P)
        )
        cost_per_pass = per_pass_sec * 2 * 0.000131
        est_cost = generations * popsize * cost_per_pass
    return popsize, generations, games_per_eval, est_cost
```

Update PROFILES preset values (~line 398-404) to N=33 default:

```python
PROFILES: dict[str, tuple[int, int, int, float]] = {
    # (popsize, generations, games_per_eval, est_cost_usd)
    # Cost estimates assume 4P games at ~6sec each (vs 3sec 2P).
    "smoke":       (4,   1,  4,   0.10),
    "iteration":   (20,  15, 33,  16.0),
    "default":     (50,  15, 33,  40.0),
    "extended":    (50,  30, 33,  80.0),
    "max-quality": (100, 30, 50, 240.0),
}
```

In `main()`, rename the CLI flag (~line 548):

```python
    fitness_games_per_opponent: int = 0,      # 0 → use profile default
```

to:

```python
    games_per_eval: int = 0,                  # 0 → use profile default; 4P games per candidate
```

And update the call to `_choose_profile` (~line 575-580):

```python
    pop, gens, games_per_eval, est_cost = _choose_profile(
        profile,
        popsize_override=popsize if popsize > 0 else None,
        generations_override=generations if generations > 0 else None,
        games_per_eval_override=games_per_eval if games_per_eval > 0 else None,
    )
```

And update the print line (~line 588):

```python
    print(f"  fitness games   : {games_per_eval} (4P FFA, graduated placement)")
```

And update `args.append((...))` block (~line 668-676):

```python
        args = []
        for i, c_norm in enumerate(candidates_norm):
            c_real = _denormalize(np.asarray(c_norm), lowers, uppers)
            cfg_dict = asdict(decode(c_real))
            args.append((
                cfg_dict, i, gen,
                sanity_n_per_opponent, games_per_eval, sanity_threshold,
                archive_opponents,
            ))
```

And update the disqualified-result synthesis when starmap raises (~line 691-703):

```python
        for i, r in enumerate(raw_results):
            if isinstance(r, BaseException):
                n_failed_eval += 1
                _cfg_dict, cand_id, gen_id, *_ = args[i]
                results.append({
                    "candidate_id": cand_id,
                    "generation": gen_id,
                    "sanity_pass": False,
                    "fitness": DISQUALIFIED_FITNESS,
                    "per_game_scores": [],
                    "games_per_eval": games_per_eval,
                    "archive_size_at_eval": len(archive_opponents),
                    "sanity_winrates": {},
                    "wall_clock_seconds": 0.0,
                    "failure_reason": f"{type(r).__name__}: {r}",
                })
            else:
                results.append(r)
```

And update `gen_record` to drop `per_opponent_breakdown` (no longer meaningful) and replace with `per_game_scores_summary` (~line 797-811):

```python
        gen_record = {
            "gen": gen,
            "best_fitness": gen_best,
            "mean_fitness": gen_mean,
            "fitness_stddev": gen_std,
            "n_disqualified": n_disqualified,
            "n_failed_eval": n_failed_eval,
            "best_candidate": args[gen_best_idx][0],
            "best_per_game_scores": gen_best_result.get("per_game_scores", []),
            "games_per_eval": games_per_eval,
            "archive_size_at_eval": len(archive_opponents),
            "archive_event": archive_event,
            "wall_clock_seconds": wall,
            "estimated_cost_usd": gen_cost,
            "accumulated_cost_usd": accumulated_cost,
        }
```

And update `config_blob` (~line 615-634): replace `fitness_games_per_opponent` with `games_per_eval`:

```python
        "games_per_eval": games_per_eval,
```

And update `_write_best_config_py` and `_write_final_report` callers — they take a `per_opp` dict. After the retool, "per opponent" doesn't exist; we have per-game scores. Pass an empty dict or pass game-score summary. For minimal change, pass `{"mean_score": fitness}` to keep the writer signatures the same:

In `main()` where `_write_best_config_py` is called (~line 759-770), wherever the `robust_best_per_opp` dict is built, ensure it's `{"mean_4p_score": robust_best_fitness}` or similar. The simplest: track `gen_best_per_opp = {"mean_4p_score": gen_best_result["fitness"]}` and pass that through.

Update the gen-best-history append (~line 734-740):

```python
        gen_best_history.append({
            "gen": gen,
            "fitness": gen_best,
            "cfg_dict": args[gen_best_idx][0],
            "per_opp": {"mean_4p_score": gen_best},
            "archive_size_at_eval": archive_size_at_eval,
        })
```

And in the best-ever and robust-best updates (~line 745-770), use the same `{"mean_4p_score": gen_best}` shape for `gen_best_per_opp`:

```python
        if gen_best > best_fitness_so_far:
            best_fitness_so_far = gen_best
            best_cfg_dict_so_far = args[gen_best_idx][0]
            best_per_opp_so_far = {"mean_4p_score": gen_best}

        if archive_size_at_eval > robust_best_archive_size:
            robust_best_archive_size = archive_size_at_eval
            robust_best_fitness = gen_best
            robust_best_cfg = args[gen_best_idx][0]
            robust_best_per_opp = {"mean_4p_score": gen_best}
            _write_best_config_py(
                out_dir / "best_config.py",
                robust_best_cfg, run_id, robust_best_fitness, robust_best_per_opp,
            )
        elif archive_size_at_eval == robust_best_archive_size and gen_best > robust_best_fitness:
            robust_best_fitness = gen_best
            robust_best_cfg = args[gen_best_idx][0]
            robust_best_per_opp = {"mean_4p_score": gen_best}
            _write_best_config_py(
                out_dir / "best_config.py",
                robust_best_cfg, run_id, robust_best_fitness, robust_best_per_opp,
            )
```

- [ ] **Step 6: Run new tests**

Run: `uv run pytest tests/test_modal_tuner_4p.py::TestEvaluateFitnessLocal4P -v`
Expected: 2 passed (slow — each runs multiple full episodes; budget ~3-5 minutes total).

- [ ] **Step 7: Verify nothing else broke**

Run: `uv run pytest tests/test_modal_tuner_4p.py -v`
Expected: all tests pass (graduated_scores 6, compute_player_assets 3, run_one_game_4p 2, _select_4p_opponents 5, evaluate_fitness_local 2 = 18 total).

- [ ] **Step 8: Commit**

```bash
git status -s
git add src/tools/modal_tuner.py tests/test_modal_tuner_4p.py
git commit -m "$(cat <<'EOF'
feat(tuner): replace 2P fitness with 4P graduated placement (N=33 default)

Sanity gate unchanged (2P vs SANITY_OPPONENTS at 0.91). Fitness phase now
runs games_per_eval 4P FFA games per candidate (default N=33), each with
3 archive samples (or starter padding when archive<3). Score per game =
graduated placement of candidate (1st=+1, 2nd=+1/3, 3rd=-1/3, 4th=-1).
Fitness = mean of per-game candidate scores.

Renames CLI flag fitness_games_per_opponent -> games_per_eval. Profile
defaults updated to N=33 with new 4P-game cost model (~2x 2P wall-clock).
All anti-regression invariants preserved: starmap return_exceptions=True,
robust-BEST save from max-archive-size gen, 120min function timeout.

Per kickoff brief 2026-05-05 Section 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Local smoke test of full main() loop

**Files:** none modified; verifies the changes work end-to-end before paying for Modal.

- [ ] **Step 1: Run the smoke profile locally (no Modal)**

The Modal `evaluate_fitness` wrapper just calls `evaluate_fitness_local`. To smoke-test without Modal, create a one-off script call. Run inline:

```bash
uv run python -c "
from dataclasses import asdict
from orbit_wars.heuristic.config import HeuristicConfig
from tools.modal_tuner import evaluate_fitness_local

result = evaluate_fitness_local(
    cfg_dict=asdict(HeuristicConfig.default()),
    candidate_id=0,
    generation=0,
    sanity_n_per_opponent=2,
    games_per_eval=4,
    sanity_threshold=0.0,
    archive_opponents=[],
)
print('fitness:', result['fitness'])
print('per_game_scores:', result['per_game_scores'])
print('games_per_eval:', result['games_per_eval'])
print('sanity_pass:', result['sanity_pass'])
print('wall_clock_seconds:', result['wall_clock_seconds'])
"
```

Expected: `sanity_pass: True`, `fitness` in `[-1.0, 1.0]`, `per_game_scores` is a 4-element list, `wall_clock_seconds` ~30-60s.

If `sanity_pass: False` → bug in changes; investigate.
If errors raised → fix before proceeding to Modal.

- [ ] **Step 2: Run cloud-side smoke via Modal**

```bash
uv run modal run src/tools/modal_tuner.py --smoke
```

Expected: prints "=== CMA-ES tuning run ===" with `profile: smoke`, `popsize: 4`, `generations: 1`, `fitness games: 4`. Runs one generation (~2-5 minutes), writes `docs/research_documents/tuning_runs/<TS>/{config.json, generations.jsonl, best_config.py, final_report.md}`.

If Modal auth fails: `uv run modal token info` to verify auth (per CLAUDE.md memory — NOT `modal token current`).

- [ ] **Step 3: Inspect the smoke output**

```bash
ls docs/research_documents/tuning_runs/$(ls -t docs/research_documents/tuning_runs/ | head -1)/
cat docs/research_documents/tuning_runs/$(ls -t docs/research_documents/tuning_runs/ | head -1)/generations.jsonl
```

Expected: 4 files present (config.json, generations.jsonl, best_config.py, final_report.md). The generations.jsonl has one JSON line with `gen: 0`, `games_per_eval: 4`, no infra failures. `best_per_game_scores` is a 4-element list.

If `n_failed_eval > 0` in the smoke run, debug before launching the real sweep — it usually indicates a Modal-side import error (sys.path drift, missing dep).

- [ ] **Step 4: Commit smoke run output (optional — only if it captures useful info)**

If the smoke succeeded cleanly, the run dir contains useful "first 4P sweep ever" history. Otherwise skip:

```bash
# Note: tuning_runs/ is gitignored per chore commit 6827504. Smoke output
# stays local only. No commit needed.
```

---

## Task 7: Launch the iteration sweep on Modal

**Files:** none modified; produces a sweep output dir.

- [ ] **Step 1: Estimate cost and confirm**

```bash
uv run modal run src/tools/modal_tuner.py --iteration --confirm-cost
```

Per the updated PROFILES preset, iteration is `popsize=20, generations=15, games_per_eval=33`. Estimated cost ~$16 by the meter (Modal cost meter overestimates ~4-5x per memory, so real billing likely $3-4). Confirms with `--confirm-cost` flag.

- [ ] **Step 2: Monitor sweep progress**

The sweep runs cloud-side. Local entrypoint prints per-generation lines:

```
gen   1/15  best=+0.1234  mean=-0.0567  stddev=0.4321  disq=0/20 (infra-fail=0)  archive=0  wall=240s  cost=$1.10  total=$1.10
```

Watch for:
- `n_failed_eval > 0` recurring → infra problem; abort and debug
- `stddev` collapsing to near-0 too fast (gen 3-4) → CMA-ES overconfident; future runs should bump N from 33 to 64 (note in followup, do not abort this run)
- Generation wall-clock far exceeding budget → reduce population or games_per_eval next time

- [ ] **Step 3: Wait for completion (~30-60 minutes)**

Sweep finishes when `=== Done ===` is printed. Run dir: `docs/research_documents/tuning_runs/<TS>/`.

- [ ] **Step 4: Inspect results**

```bash
RUN=$(ls -t docs/research_documents/tuning_runs/ | head -1)
cat docs/research_documents/tuning_runs/$RUN/final_report.md
cat docs/research_documents/tuning_runs/$RUN/best_config.py
```

Expected: `best_config.py` contains a `BEST = HeuristicConfig(...)` whose fields differ from `HeuristicConfig.default()` in plausible directions. `final_report.md` shows fitness curve trending upward across generations.

If `robust_best_fitness` is negative or essentially zero, the sweep didn't find anything better than 1v3 baseline — that's evidence the 4P-tuner doesn't help with default landscape. Document and pause Path A iteration.

---

## Task 8: Bundle and submit BEST as v5 to Kaggle ladder

**Files:**
- Create: `submission_main_bestv5.py` (temporary, for tarball)
- Create: `submission-bestv5-2026-05-05.tar.gz` (tarball)

Per CLAUDE.md "Submitting CMA-ES-tuned configs" pattern. Build a custom main.py that bakes BEST values + agent wrapper.

- [ ] **Step 1: Build the submission directory**

```bash
RUN=$(ls -t docs/research_documents/tuning_runs/ | head -1)
SUBMIT_DIR=$(mktemp -d)
mkdir -p $SUBMIT_DIR/orbit_wars
cp -r src/orbit_wars/* $SUBMIT_DIR/orbit_wars/

# Verify the BEST config exists
test -f docs/research_documents/tuning_runs/$RUN/best_config.py && echo "OK: best_config.py present"
```

- [ ] **Step 2: Generate the submission main.py**

Inspect existing pattern (recently shipped):

```bash
tar -tzf submission-bestv4-2026-05-04.tar.gz | head
tar -xzOf submission-bestv4-2026-05-04.tar.gz main.py | head -50
```

Reuse that shape. Create `$SUBMIT_DIR/main.py` (one-shot via `tee`):

```bash
RUN=$(ls -t docs/research_documents/tuning_runs/ | head -1)
# Extract BEST field assignments from best_config.py — strip header, keep field=value lines
sed -n '/^BEST = HeuristicConfig(/,/^)/p' docs/research_documents/tuning_runs/$RUN/best_config.py > /tmp/best_block.py

cat > $SUBMIT_DIR/main.py <<'EOF'
"""Orbit Wars submission: bestv5 (4P-tuned, 2026-05-05)."""
from orbit_wars.heuristic.config import HeuristicConfig
from orbit_wars.heuristic import strategy

EOF
cat /tmp/best_block.py >> $SUBMIT_DIR/main.py
cat >> $SUBMIT_DIR/main.py <<'EOF'

def agent(obs, _env_config=None):
    # _env_config guard: env passes a Struct as 2nd positional arg, not a HeuristicConfig.
    return strategy.agent(obs, BEST)
EOF

cat $SUBMIT_DIR/main.py | head -20
```

- [ ] **Step 3: Create the tarball**

```bash
tar -czf submission-bestv5-2026-05-05.tar.gz -C $SUBMIT_DIR main.py orbit_wars
ls -lh submission-bestv5-2026-05-05.tar.gz
```

- [ ] **Step 4: Smoke-test the tarball locally before submitting**

```bash
TEST_DIR=$(mktemp -d)
tar -xzf submission-bestv5-2026-05-05.tar.gz -C $TEST_DIR
cd $TEST_DIR && uv run python -c "
import main
from kaggle_environments import make
env = make('orbit_wars', debug=True)
env.run([main.agent, 'random'])
last = env.steps[-1]
print('rewards:', [s.reward for s in last])
print('statuses:', [s.status for s in last])
"
cd -
```

Expected: `rewards: [1.0, -1.0]` (or similar, our agent winning vs random) and `statuses: ['DONE', 'DONE']`. If our agent loses to random or errors, do NOT submit — debug.

- [ ] **Step 5: Submit to Kaggle**

```bash
kaggle competitions submit orbit-wars -f submission-bestv5-2026-05-05.tar.gz -m "v5: 4P-tuned (graduated placement, N=33, archive co-evo) — first 4P-aware tuner output"
kaggle competitions submissions orbit-wars | head -10
```

Note the new submission ID. The result row will show `pending` then `complete` after some minutes/hours.

- [ ] **Step 6: Wait for ladder μ to drift-resolve (4-6 hours per CLAUDE.md)**

Per CLAUDE.md memory: "Initial readings after submission drift ±50 μ over hours as more episodes run. BEST_v2 read 614 μ at first check → 663.7 μ ~12 hours later. Wait at least 4-6 hours before drawing conclusions."

After 4-6 hours (or next day):

```bash
kaggle competitions submissions orbit-wars | head -5
# Note the latest μ for the new submission and the pre-existing baseline (~700)
```

- [ ] **Step 7: Record the data point**

Create `docs/iteration_logs/2026-05-05-bestv5-4p-tuner-result.md` (or append to existing iteration log if present). Capture:
- BEST config diff vs `HeuristicConfig.default()` (paste from `best_config.py`)
- Sweep run-id and dir
- Submission ID
- Initial ladder μ
- Drift-resolved ladder μ at +6h
- Comparison to current baseline (~700)
- Decision per kickoff brief Section 4 coordination table

This task's done criterion is the data point recorded; the *implication* (continue Path A vs commit to C) is a separate decision.

---

## Self-review

**Spec coverage check (against kickoff brief Section 2):**
- ✅ N=33 → Task 5 sets default in PROFILES; Task 6 smoke test uses 4 (not 33) for speed but Task 7 launches with 33.
- ✅ 3-archive opponents with starter fallback → Task 4.
- ✅ Graduated placement (1st=+1, 2nd=+1/3, 3rd=-1/3, 4th=-1) → Task 1.
- ✅ Tie averaging → Task 1 tests cover 2-way, 3-way, all-equal cases.
- ✅ Asset-count via final observation → Task 2.
- ✅ Anti-regressions preserved (resilient starmap, robust-BEST save, 120min timeout) → Task 5 explicitly does NOT touch the starmap or robust-best logic; Task 5 commit message asserts this.
- ✅ Submit to Kaggle ladder + record data point → Tasks 7-8.

**Placeholder scan:** none found. All commands are concrete; all code is complete.

**Type consistency:** `games_per_eval` is consistently named after Task 5 rename (was `fitness_n_per_opponent` / `fit_games`). `archive_opponents` is a `list[dict]` everywhere. `cfg_dict` is a `dict` (asdict of HeuristicConfig). `agents` parameter to `run_one_game_4p` is `list[dict | str]`.

**Gap/risk noted:** Task 5 modifies a long function across many sites in one commit. If the sub-step rename is interrupted partway, the file is inconsistent. Recommendation for the executor: do all of Task 5 in one focused work block; do not split it across sessions. If interruption happens, `git diff` to see what's partially done before resuming.

**Out of plan (deliberate):** No revert path back to the 2P tuner; the 2P fitness path is removed. If the 4P retool turns out to be a bad idea, recovery is `git revert <Task 5 commit>`.
