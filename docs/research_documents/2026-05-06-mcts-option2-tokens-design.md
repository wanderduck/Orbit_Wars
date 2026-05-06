---
title: "MCTS Option 2 — single-launch token action space (architectural revision)"
date: 2026-05-06
status: design proposal
authors: claude (general-purpose subagent under user direction)
references:
  - docs/research_documents/2026-05-06-mcts-algorithm-design.md  # design v2 §3.2, §7
  - docs/research_documents/mcts/  # Aljabasini 2021 thesis (PW + FPU + decoupled UCT)
  - memory/mcts_m2_0wins_20games.md  # the failure motivating this rewrite
  - src/orbit_wars/mcts/{ranking.py,search.py,node.py,config.py}  # current compound-variant impl
  - src/orbit_wars/sim/simulator.py  # one-env-turn step interface
  - src/orbit_wars/heuristic/strategy.py  # decide_with_decisions + LaunchDecision
supersedes_for_section: design v2 §3.2 (move ordering) and §7 question 3 (open issue)
---

# MCTS Option 2 — Single-Launch Token Action Space

## 1. Problem statement

### 1.1 Why option 2 exists at all

The current MCTS (M3, commit `df5f8ca`) uses a **compound-variant action space**: at each
node the move-ordering function returns up to 8 candidate `list[list[float|int]]` action
lists (variant 0 = full heuristic; variant 1 = HOLD; variants 2..k = heuristic with one
launch dropped, using a **lightweight nearest-target ranker** rather than the real
heuristic). Each MCTS step picks ONE variant per player and the simulator advances ONE
env-turn.

Two failures, one root cause (per `memory/mcts_m2_0wins_20games.md`):

- **M2** (vanilla UCB1 + argmax-mean): 0 wins / 0 ties / 20 losses paired-seat vs the
  heuristic. UCB1's `+inf` for unvisited variants forces visiting the dumb drop-one
  perturbations equally with variant 0; argmax-mean then picks whichever happens to land
  high by noise.
- **M3** (PW + FPU + robust child): pins to variant 0 in 99.6%-100% of turns. M3 IS the
  heuristic with ~200ms search overhead. No regression but no lift.

The diagnosis is unambiguous: **the variant set has no candidate that can beat variant 0.**
Variants 2..k are strictly dumber than the heuristic (they're produced by a lightweight
ranker and then degraded by dropping one of its launches). The search is doing exactly
what it should — picking the best candidate it's offered. Garbage in, garbage out.

### 1.2 What option 2 must achieve

Functional requirements:

1. **The action space must contain candidates capable of beating the full heuristic.**
   Concretely: at least one selectable action sequence per turn that the heuristic
   wouldn't choose, but that has higher true expected value.
2. **Canonical SM-MCTS shape.** Per Aljabasini 2021 §2.1, the algorithm assumes a finite
   per-node action set with PW + FPU + decoupled UCT. Compound bundles where each
   "action" is itself the full per-turn output is a degenerate special case (depth-1 tree
   above each env-turn, branching factor = K). Single-launch tokens align with the
   literature's intended structure.
3. **Iteration cost stays inside ~7ms target** (per design v2 §3.6) so we still get
   ~80-100 iterations per turn at 700ms budget.
4. **Always-safe heuristic fallback preserved.** The wrapper guarantees that even if
   token-space search returns nothing useful, we never ship `[]` to the env.

Non-goals (deliberately deferred):

- Tree reuse across env turns (still rebuilt per turn, per design v2 §6).
- Learned opponent model (still symmetric heuristic, per design v2 §3.4).
- AlphaZero PUCT prior (heuristic ranking remains the prior).
- 4P-specific opponent modeling (treat the 3 opponents independently with the same
  symmetric heuristic).

### 1.3 Critical pushback before we start

Before designing, I want to flag two things that the user-supplied scaffolding does NOT
make explicit but that should temper expectations:

1. **The compound-variant ceiling result is a CEILING ON THE CURRENT VARIANT SET, not on
   compound variants in general.** A compound variant set with candidates like "heuristic
   minus the worst launch" or "heuristic with the largest launch resized to 75%" would
   plausibly beat variant 0 sometimes. The memory doc lists this as Pivot Option #1
   ("Heuristic-perturbation variants, ~half-day"). Option 2 (single-launch tokens) is
   pivot option #2, ~2 days, "high lift" but unproven. **The user has chosen the
   higher-cost / higher-uncertainty path.** This design honors that choice but flags that
   if option 2 fails its gate, falling back to pivot option #1 should be on the table
   before deeper sophistication.

2. **Aljabasini 2021's PW examples are board games (Hex, Kuhn poker variants) where one
   "action" = one move. Orbit Wars' action is a SET of launches per turn.** The
   literature does NOT directly address composing an action *set* from a tree of
   single-launch picks within one env-turn. §4 of this doc is the design's most novel
   piece and the most likely to need empirical iteration. I have specific concerns
   about sub-tree decoupled UCT that I'll articulate there.

## 2. Action-space conceptual model

### 2.1 Launch token definition

```python
@dataclass(frozen=True, slots=True)
class LaunchToken:
    """One atomic launch decision. Cardinality below.

    A token represents a single launch from one source planet to one target with a
    discretized ship fraction. The agent's per-turn action is composed of an ORDERED
    SEQUENCE of tokens (each chosen at successive depths in the per-turn sub-tree),
    terminated by a COMMIT_TURN sentinel.
    """

    src_planet_id: int       # owned planet id (must own at decision time)
    target_planet_id: int    # any planet (enemy/neutral/comet) — defensive launches
                             # use src=our_planet, target=our_planet (reinforcement is
                             # the heuristic's existing pattern; tokens just lift it)
    ship_fraction_bucket: int  # 0..N_BUCKETS-1; resolved against src.ships at COMMIT
                             # time using cfg.ship_fraction_buckets

    # NOT part of the token: angle. The token is "logical" — angle is computed at
    # serialization time using the heuristic's existing aim/intercept logic. This
    # avoids exploding the action space by 360× and keeps angle correct under
    # rotation/comet motion (matching the heuristic's aim_with_prediction). See §5.3.
```

Plus a singleton sentinel:

```python
COMMIT_TURN = LaunchToken(src_planet_id=-1, target_planet_id=-1, ship_fraction_bucket=-1)
```

`COMMIT_TURN` signals "no more launches this env-turn — advance simulator". Selecting
it as the next sub-tree action triggers `Simulator.step()` with the accumulated launches
for both players.

### 2.2 Cardinality

Per the field reading from real env states (CLAUDE.md `sim_planet_count_28_not_6.md`,
plus `tools.sim_perf_probe` output):

- ~28 planets total (mid-game)
- ~6 owned planets per player typical (range 2-12)
- ~22 non-self targets typical (enemies + neutrals; comets aliased)
- 4 fraction buckets (per current `MCTSConfig.ship_fraction_buckets = (0.25, 0.5, 0.75, 1.0)`)

**Per-player token cardinality at a node:** `~6 sources × ~22 targets × 4 buckets = ~530
tokens` plus `COMMIT_TURN`. This is **3-4× larger than design v2 §3.2 estimated** (which
said ~150). The estimate matters because it sets PW's growth profile (§7).

### 2.3 Generation: on-demand, not pre-enumerated

Pre-enumerating all ~530 tokens at every node and ranking them is expensive. The full
heuristic produces a ranked LaunchDecision list of typically 4-12 launches per call; we
get the top tokens for free from this. But the heuristic's output IS the prior — it
doesn't enumerate the long tail.

**Generation strategy:**

1. **Top-of-list (heuristic-derived) tokens — pre-enumerated at root and every new node.**
   Run `decide_with_decisions(obs_dict, cfg)` from the player's perspective. For each
   `LaunchDecision` it returns, generate one token per fraction bucket whose ship count
   is within ±20% of the LaunchDecision's chosen ship count. This caps tokens-per-launch
   at ~2-3 buckets typically. For 4-12 LaunchDecisions, that's ~8-36 prioritized tokens
   plus `COMMIT_TURN`.
2. **Long-tail tokens — generated on demand only when PW asks for k > len(prioritized).**
   At PW position k = len(prioritized), enumerate `(src, target, bucket)` for src in
   owned planets, target in non-owned planets, bucket in all 4 — sorted by a cheap
   distance-based score (mirroring the lightweight ranker that ranking.py already
   exposes). This bounds long-tail enumeration cost to O(sources × targets × buckets) =
   ~530 ops, only when needed.

This keeps the typical-case ranking call ≤ 5ms (full heuristic) plus ~0.5ms (token
expansion). The long tail only materializes at high visit counts, where iteration cost
amortizes anyway.

### 2.4 Why fraction buckets are 4 (not 5 from design v2 §3.2)

Design v2 §3.2 listed `{ALL, 75%, 50%, 25%, MIN_LAUNCH}` — 5 buckets including
`MIN_LAUNCH`. But the existing `MCTSConfig.ship_fraction_buckets` already drops
`MIN_LAUNCH` and uses `(0.25, 0.5, 0.75, 1.0)`. Reasons to keep 4:

- `MIN_LAUNCH` (currently 20 in `HeuristicConfig`) is a fixed integer floor, not a
  fraction. A token system that mixes "fraction of available" with "absolute min" is
  awkward to UCB-rank.
- The heuristic already enforces `MIN_LAUNCH` at serialization. If a fraction bucket
  resolves to < MIN_LAUNCH ships, the token is silently rejected at validate time
  (§5.4) and the player effectively COMMITs that turn (or picks a different token).
- 4 buckets keeps cardinality tractable. Adding a 5th would mean `~660` tokens per
  player per node.

If empirical results show fine-grained sizing matters, M5 can swap the bucket scheme.

## 3. Multi-launch composition (the §7 open question)

### 3.1 The three approaches enumerated

**(a) Sub-tree per env-turn (depth-step = single launch).** Each MCTS depth-step adds
ONE token. The simulator advances only when COMMIT_TURN is the chosen token. Decoupled
UCT is applied PER SUB-NODE, and the sub-tree is owned by the current env-turn-state
node. After both players COMMIT (or hit a max-launches-per-turn cap), the simulator
advances and we descend into the next env-turn-state node.

**(b) Per-turn batch (sequential UCB picks within one node).** At each env-turn-state
node, each player PICKS A SET of tokens via repeated UCB selection within the same
node's stats — like multi-arm bandit with replacement. Then sim advances. No sub-tree.

**(c) Hybrid (cap launches per turn, expand only those depths).** Like (a) but bound
the per-turn sub-tree to MAX_LAUNCHES_PER_TURN (say 3-4) levels.

### 3.2 The recommendation: **(a) Sub-tree per env-turn with hybrid cap.**

I.e., (a) + (c) jointly. Justification with explicit pushback against (b).

#### 3.2.1 Why NOT (b) — per-turn batch

Approach (b) says "at this node, the player picks 0-N tokens by sequentially UCB-ing
into the same stats dict, then COMMITs". On the surface this avoids sub-tree complexity.
In practice it's incompatible with decoupled UCT for two reasons:

1. **The stats need to be conditional on prior token picks WITHIN THE SAME TURN.** If
   player picks token A first (ALL ships from planet 5 → planet 9), then planet 5 has
   0 ships left — token B (50% from planet 5 → planet 7) is now invalid. Vanilla
   bandit-with-replacement doesn't model this conditional invalidation. You'd need
   per-(state, prior_picks) UCB stats — which IS a sub-tree, just denormalized.

2. **The opponent's pick is interleaved, not batched.** In a true SM-MCTS, decoupled UCT
   means BOTH players' joint actions resolve simultaneously each step. If we let our
   player batch-pick within a node while the opponent atomically picks one compound
   action, we've broken the symmetry. The opponent's prior turn-token choices ALSO
   constrain their next ones (same source-planet ship-pool argument).

Per Aljabasini 2021 §2.1.2 (decoupled UCT): the joint action drives ONE sim step. The
literature pattern requires that "one MCTS step = one sim step". (b) breaks this.

#### 3.2.2 Why (a) + (c) jointly — sub-tree with per-turn cap

The clean formulation that respects decoupled UCT:

- Each env-turn-state node has, conceptually, an embedded **per-turn launch sub-tree**
  whose internal nodes encode "which tokens has each player picked SO FAR this env-turn".
- At each sub-tree node, both players have per-player UCB stats over their available
  next tokens (excluding tokens already picked this turn AND excluding tokens whose src
  no longer has enough ships after intra-turn deductions).
- A "sub-tree leaf" is reached when BOTH players have selected `COMMIT_TURN` (or the
  hybrid cap is hit and we force-COMMIT). At that point, the simulator advances ONE env
  turn, and the resulting state becomes a new env-turn-state node — the next "real"
  level of the tree.

The hybrid cap (`MAX_LAUNCHES_PER_TURN = 4`) bounds sub-tree depth. Per the heuristic's
typical output (4-12 launches per turn for a mid-game player), 4 is the median — capping
here means MCTS can express the heuristic's decision span but not go arbitrarily deeper.
This caps per-env-turn sub-tree size at `(K_PW + 1)^4` worst case which is reasonable.

#### 3.2.3 Stats and node identity

Concretely (this is the core of the design):

- A SINGLE `MCTSNode` carries the env-turn STATE and contains its own sub-tree.
- The sub-tree is keyed by `(player_picks_so_far_p0, player_picks_so_far_p1, ...)` —
  one frozenset of tokens per alive player. We canonicalize this as a sorted tuple of
  tuples of token ids. Each unique combo is a `SubNode` inside the parent MCTSNode.
- Stats live AT THE SUBNODE, not the MCTSNode. UCB scoring at depth d of the sub-tree
  uses (subnode_visits, subnode_value_sum) per (player_id, next_token_id).
- After all players hit COMMIT, the joint per-player launch lists are passed to
  `Simulator.step()`; the resulting state populates a child MCTSNode keyed by the joint
  COMMIT'd token sets (canonical hash of player_picks).

The MCTSNode's existing `children: dict[JointAction, MCTSNode]` field is repurposed:
`JointAction` becomes `tuple[frozenset[TokenID], frozenset[TokenID], ...]` (one
frozenset per player, in player_id order). The existing `stats` field moves to the
SubNode level.

#### 3.2.4 Pseudo-code

```python
@dataclass(slots=True)
class SubNode:
    """One node in the per-turn launch sub-tree.

    `picks_per_player` is the token ids each player has chosen so far this turn,
    in pick order (NOT a set — order matters for ship-pool deductions).
    `committed_per_player[p]` is True iff player p has selected COMMIT_TURN.
    """
    picks_per_player: tuple[tuple[int, ...], ...]  # one tuple per player
    committed_per_player: tuple[bool, ...]
    stats: dict[int, dict[int, list[float]]]  # per-player stats: token_idx -> [visits, value_sum]
    visits: int = 0


@dataclass(slots=True)
class MCTSNode:
    """One env-turn state. Contains the per-turn launch sub-tree as `subnodes`.

    `state` is the env-turn-state. `subtree_root` is the SubNode where no player
    has picked anything yet. `committed_children` maps a fully-committed joint
    pick to the child MCTSNode (post-sim-step state).
    """
    state: SimState
    visits: int = 0
    # Per-player ranked tokens at THIS env-turn-state. Computed once on first visit.
    ranked_tokens: dict[int, list[LaunchToken]] = field(default_factory=dict)
    subtree_root: SubNode = field(default_factory=lambda: SubNode((), (), {}))
    # Cache of subnodes by canonical key (picks_per_player). Reused across iterations.
    subnodes: dict[tuple, SubNode] = field(default_factory=dict)
    # Children keyed by the COMMITTED joint picks (frozensets of token_ids per player).
    children: dict[tuple, MCTSNode] = field(default_factory=dict)


def smmcts_iteration(node: MCTSNode, sim: Simulator, cfg: MCTSConfig, depth: int) -> dict[int, float]:
    """One full SM-MCTS iteration starting at this env-turn-state node.

    Returns per-player values backed up the path.
    """
    # Terminal / depth limit on env-turns
    if depth >= cfg.max_depth or is_terminal(node.state):
        return {p: value_estimate(node.state, p) for p in node.state.alive_players()}

    # Lazy-compute ranked tokens for this node's state
    if not node.ranked_tokens:
        for p in node.state.alive_players():
            node.ranked_tokens[p] = generate_ranked_tokens(node.state, p, cfg)

    # Walk down the per-turn sub-tree, picking one token per player per sub-step
    sub = node.subtree_root
    while not all_committed(sub, node.state.alive_players()) and \
          len(sub.picks_per_player[0]) < cfg.max_launches_per_turn:
        # Decoupled UCT: each not-yet-committed player picks next token via PW + FPU
        next_picks = []  # one (player_id, token_idx) per alive, not-yet-committed player
        for p_idx, p in enumerate(sorted(node.state.alive_players())):
            if sub.committed_per_player[p_idx]:
                next_picks.append((p, COMMIT_TURN_IDX))
                continue
            available_tokens = filter_invalid(node.ranked_tokens[p], sub.picks_per_player[p_idx], node.state)
            k = pw_k(sub.visits, cfg)
            considered = available_tokens[:k]
            chosen_idx = ucb_select(sub, p_idx, considered, cfg)
            next_picks.append((p, chosen_idx))
        # Move to the sub-child reflecting these picks
        new_picks_per_player = tuple(
            sub.picks_per_player[i] + (idx,) if idx != COMMIT_TURN_IDX else sub.picks_per_player[i]
            for i, (_, idx) in enumerate(next_picks)
        )
        new_committed = tuple(
            sub.committed_per_player[i] or (idx == COMMIT_TURN_IDX)
            for i, (_, idx) in enumerate(next_picks)
        )
        sub_key = (new_picks_per_player, new_committed)
        if sub_key not in node.subnodes:
            node.subnodes[sub_key] = SubNode(new_picks_per_player, new_committed, {})
        sub = node.subnodes[sub_key]

    # All players committed (or hit cap) — descend into the env-turn child
    committed_key = canonicalize_committed(sub.picks_per_player, node.ranked_tokens)
    if committed_key not in node.children:
        # Expansion: build env actions, sim-step, evaluate leaf
        env_actions = serialize_picks_to_env_actions(sub.picks_per_player, node.ranked_tokens, node.state)
        next_state = sim.step(node.state, env_actions)
        child = MCTSNode(state=next_state)
        node.children[committed_key] = child
        leaf_values = {p: value_estimate(next_state, p) for p in node.state.alive_players()}
    else:
        child = node.children[committed_key]
        leaf_values = smmcts_iteration(child, sim, cfg, depth + 1)

    # Backprop UP THE SUB-TREE PATH
    backprop_subtree_path(node, sub, leaf_values)
    node.visits += 1
    return leaf_values
```

Key details glossed in the pseudo-code (spelled out in §5):

- `filter_invalid` removes tokens whose source planet doesn't have enough ships
  after subtracting prior intra-turn picks, plus any token already picked.
- `serialize_picks_to_env_actions` resolves the bucket fraction to ships, computes
  angle via heuristic intercept logic, builds `[from_id, angle, ships]` triples, and
  validates each via `validate_move`.
- `backprop_subtree_path` walks back up from the committed sub-leaf through every
  sub-node visited this iteration, incrementing visits and value_sum for the chosen
  per-player token at each sub-node.

#### 3.2.5 Cost analysis

Per iteration:

- Token generation (root + every new env-turn-state child): ~5ms (heuristic call) +
  ~0.5ms (long-tail expansion if needed) = ~5.5ms ONCE per new MCTSNode.
- Per sub-step (1-4 sub-steps per env-turn): UCB selection (~µs) + pick filtering (~µs).
  Sub-step total: ~10-50 µs. Sub-tree total: ~40-200 µs per env-turn iteration.
- Sim-step: 1.77ms.
- Backprop: ~µs.

**Per env-turn iteration cost: ~7.5ms (dominated by token-gen amortized + sim-step).**
At 700ms budget: ~93 iterations per turn. Matches design v2's projected envelope.

The CRITICAL caveat is that token-gen (~5.5ms) runs only at expansion (new MCTSNode).
Re-visited MCTSNodes have ranked_tokens cached. So the actual cost converges toward
~2ms/iteration (sim + backprop) once the tree is populated, allowing ~350 iterations on
re-visited paths. This is favorable: deep tree exploration becomes cheaper.

## 4. Data structures (concrete)

### 4.1 New module: `src/orbit_wars/mcts/token.py`

```python
"""LaunchToken — atomic action element for option-2 MCTS.

A token is a (src, target, fraction) triple representing one launch. The full per-turn
action is a SEQUENCE of tokens (chosen at successive sub-tree depths) terminated by
COMMIT_TURN. Bucket fractions and angle resolve at serialization time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class LaunchToken:
    src_planet_id: int
    target_planet_id: int
    ship_fraction_bucket: int  # index into MCTSConfig.ship_fraction_buckets

    # Sentinel singleton accessed as LaunchToken.COMMIT
    COMMIT: ClassVar["LaunchToken"]

    def is_commit(self) -> bool:
        return self.src_planet_id == -1

    def __hash__(self) -> int:
        return hash((self.src_planet_id, self.target_planet_id, self.ship_fraction_bucket))


LaunchToken.COMMIT = LaunchToken(-1, -1, -1)


def token_id(token: LaunchToken) -> int:
    """Stable integer id for token (used as key in stats dicts).

    Encoding: ((src+1) << 20) | ((target+1) << 8) | (bucket+1). Supports up to 4096
    planets and 256 buckets — well clear of game limits. -1 sentinel maps to 0.
    """
    if token.is_commit():
        return 0
    return ((token.src_planet_id + 1) << 20) | ((token.target_planet_id + 1) << 8) | (token.ship_fraction_bucket + 1)
```

### 4.2 Modified `src/orbit_wars/mcts/node.py`

The existing `MCTSNode` becomes per-env-turn-state and gains a sub-tree. The
`JointAction` type changes meaning: it's now the COMMITTED joint pick set, NOT the
per-player chosen variant index.

```python
from __future__ import annotations

from dataclasses import dataclass, field

from orbit_wars.sim.state import SimState

from .token import LaunchToken


# Canonical committed-picks key: tuple of frozensets of token_ids per player (sorted by player_id).
JointCommit = tuple[frozenset[int], ...]


@dataclass(slots=True)
class SubNode:
    """One state in the per-env-turn launch sub-tree.

    Identity is (picks_per_player, committed_per_player). Stats live here.
    """
    picks_per_player: tuple[tuple[int, ...], ...]  # token_idx tuples, in pick order
    committed_per_player: tuple[bool, ...]
    # Per-player UCB stats: player_idx -> {token_idx: [visits, value_sum]}
    stats: dict[int, dict[int, list[float]]] = field(default_factory=dict)
    visits: int = 0

    def get_stat(self, player_idx: int, token_idx: int) -> tuple[int, float]:
        pstats = self.stats.get(player_idx)
        if pstats is None:
            return 0, 0.0
        s = pstats.get(token_idx)
        if s is None:
            return 0, 0.0
        return int(s[0]), float(s[1])

    def update_stat(self, player_idx: int, token_idx: int, value: float) -> None:
        pstats = self.stats.setdefault(player_idx, {})
        s = pstats.setdefault(token_idx, [0.0, 0.0])
        s[0] += 1
        s[1] += value


@dataclass(slots=True)
class MCTSNode:
    """One env-turn state. Owns its per-turn launch sub-tree."""
    state: SimState
    visits: int = 0
    # Per-player ranked tokens (lazy on first visit). Indexed 0..K-1; index 0 reserved for COMMIT_TURN.
    ranked_tokens: dict[int, list[LaunchToken]] = field(default_factory=dict)
    # Sub-tree state. subnode_cache is keyed by (picks_per_player, committed_per_player).
    subnode_cache: dict[tuple, SubNode] = field(default_factory=dict)
    # Children indexed by JointCommit. Populated lazily on sub-leaf expansion.
    children: dict[JointCommit, "MCTSNode"] = field(default_factory=dict)

    def root_subnode(self, alive_players: list[int]) -> SubNode:
        """Get or create the root sub-node (no picks yet, no commits)."""
        empty_picks = tuple(() for _ in alive_players)
        empty_committed = tuple(False for _ in alive_players)
        key = (empty_picks, empty_committed)
        sub = self.subnode_cache.get(key)
        if sub is None:
            sub = SubNode(empty_picks, empty_committed)
            self.subnode_cache[key] = sub
        return sub
```

### 4.3 Modified `src/orbit_wars/mcts/ranking.py`

Becomes `tokens.py` (or rename the existing module — see §8.3). Replace
`ranked_actions_for` with `generate_ranked_tokens(state, player_id, cfg)` returning
`list[LaunchToken]`. Index 0 is **always** `LaunchToken.COMMIT`. Indices 1..N are
heuristic-derived tokens (sorted by LaunchDecision rank then bucket distance from
heuristic's chosen ship count). Beyond that, long-tail tokens are appended on demand.

```python
def generate_ranked_tokens(
    state: SimState, player_id: int, cfg: MCTSConfig
) -> list[LaunchToken]:
    """Return ranked tokens for `player_id` at `state`.

    Index 0 is always COMMIT_TURN (the "stop launching" sentinel — selecting it
    means "advance the simulator"). Indices 1..N are heuristic-derived; long-tail
    are appended lazily by `extend_with_long_tail()`.
    """
    tokens: list[LaunchToken] = [LaunchToken.COMMIT]

    # Run the heuristic from `player_id`'s perspective.
    obs_dict = _simstate_to_env_dict(state)
    obs_dict["player"] = player_id
    obs_dict["remainingOverageTime"] = 60.0
    _, decisions = decide_with_decisions(obs_dict, None)

    # For each LaunchDecision, generate tokens for the buckets nearest the chosen ship
    # count. This caps tokens-per-launch at 2-3 typically.
    n_buckets = len(cfg.ship_fraction_buckets)
    for decision in decisions:
        src = state.planet_by_id(decision.src_id)
        if src is None or src.ships <= 0:
            continue
        chosen_fraction = decision.ships / max(src.ships, 1)
        # Buckets sorted by distance from chosen_fraction
        bucket_order = sorted(
            range(n_buckets),
            key=lambda i: abs(cfg.ship_fraction_buckets[i] - chosen_fraction),
        )
        for bucket_idx in bucket_order[:cfg.tokens_per_decision]:
            tokens.append(LaunchToken(
                src_planet_id=decision.src_id,
                target_planet_id=decision.target_id,
                ship_fraction_bucket=bucket_idx,
            ))

    return tokens


def extend_with_long_tail(
    tokens: list[LaunchToken], state: SimState, player_id: int, cfg: MCTSConfig
) -> list[LaunchToken]:
    """Append long-tail tokens (all sources × all targets × all buckets minus existing),
    sorted by distance-based score. Called only when PW asks for k > len(tokens).

    Idempotent — if long-tail is already appended, returns tokens unchanged.
    """
    # Implementation detail: ~530 tokens worst case, sorted by L2 distance.
    ...
```

### 4.4 Modified `src/orbit_wars/mcts/search.py`

Replace `_simmcts_iteration` with `smmcts_iteration` that walks the sub-tree per §3.2.4.
Robust child selection at the OUTER root (env-turn-state level): pick the most-visited
COMMIT-key from `root.children`. Then look up the sub-tree path that led to that commit
to recover the actual token sequence — but a simpler approach (and what I recommend) is:

**At end-of-search, REPLAY the search's preferred sub-tree path from the root subnode.**
Walk the sub-tree following argmax-visits at each step, until COMMIT — the sequence of
picks IS our chosen action. This is the "robust child" generalization to a sub-tree.

### 4.5 Modified `src/orbit_wars/mcts/config.py`

Add fields:

```python
# ---- Option 2 (token-space) knobs ----
tokens_per_decision: int = 3   # number of ship fraction buckets per LaunchDecision in the prior
max_launches_per_turn: int = 4  # cap per-turn sub-tree depth (the hybrid cap from §3.2)
use_token_variants: bool = True  # feature flag: True = option 2; False = legacy compound variants
long_tail_enabled: bool = True  # whether to append long-tail tokens when PW asks for k > prior
```

The `use_token_variants` flag lets us feature-flag the rollout (per §8.4).

### 4.6 Token serialization to env actions

```python
def serialize_picks_to_env_actions(
    picks_per_player: tuple[tuple[int, ...], ...],
    ranked_tokens_per_player: dict[int, list[LaunchToken]],
    state: SimState,
    alive_players: list[int],
) -> dict[int, list[Action]]:
    """Convert picked token-idx sequences into env-format Action lists.

    For each player's pick sequence:
      1. Look up tokens by index into ranked_tokens_per_player[player_id]
      2. For each non-COMMIT token, resolve fraction → ship count using the player's
         CURRENT planet ships AT decision time (respecting prior intra-turn deductions)
      3. Compute angle via aim_with_prediction on the target planet (live; matches
         heuristic's intercept logic — see §5.3)
      4. Build [from_id, angle, ships] and validate via validate_move
      5. Skip silently if validation fails (matches env L482-491 behavior)
    """
    env_actions: dict[int, list[Action]] = {}
    for p_idx, p in enumerate(alive_players):
        picks = picks_per_player[p_idx]
        actions: list[Action] = []
        ship_pool = {pl.id: pl.ships for pl in state.planets if pl.owner == p}
        for token_idx in picks:
            token = ranked_tokens_per_player[p][token_idx]
            if token.is_commit():
                break
            available = ship_pool.get(token.src_planet_id, 0)
            if available <= 0:
                continue
            fraction = cfg.ship_fraction_buckets[token.ship_fraction_bucket]
            ships = max(1, int(available * fraction))
            # Resolve angle via heuristic intercept (or current-position aim for static)
            angle = compute_angle_for_target(state, token.src_planet_id, token.target_planet_id, ships)
            if angle is None:
                continue  # sun-blocked or unreachable; silently skip
            action = Action(token.src_planet_id, angle, ships)
            if not validate_move(state, p, action):
                continue
            actions.append(action)
            ship_pool[token.src_planet_id] -= ships
        env_actions[p] = actions
    return env_actions
```

The `compute_angle_for_target` is a thin wrapper around the heuristic's
`aim_with_prediction` (via the `WorldModel`) so we get correct intercept aim for
orbiting/comet targets without re-implementing the math. Keeping the angle computation
identical to the heuristic ensures token semantics match what the heuristic would do for
the same (src, target, ships) tuple — preserving variant-0 equivalence at the limit.

## 5. Move-ordering function `f`

### 5.1 The pipeline

```
state, player_id
        │
        ▼
_simstate_to_env_dict(state) + set obs_dict["player"] = player_id
        │
        ▼
heuristic.decide_with_decisions(obs_dict, None) → (moves, decisions)
        │           ↑
        │           note: `moves` is the env-format action list. decisions is the
        │           per-launch metadata. We use decisions.
        ▼
For each decision in decisions (in heuristic-rank order):
  chosen_fraction = decision.ships / src.ships
  Pick `tokens_per_decision` buckets nearest chosen_fraction
  Emit one LaunchToken per chosen bucket
        │
        ▼
Prepend LaunchToken.COMMIT at index 0
        │
        ▼
return list[LaunchToken]
```

### 5.2 Why COMMIT at index 0 (not lowest priority)

Two options for COMMIT placement:

- **(A) Index 0** (highest prior): "default to stopping unless a token looks better".
- **(B) Index N+1** (lowest prior): "default to launching everything possible, COMMIT
  only when no token beats it".

I recommend **(A)**. Justification:

- The heuristic itself often launches NOTHING (HOLD turns) — empty action lists are
  common when ships are below MIN_LAUNCH or all paths are sun-blocked. COMMIT-first
  matches this behavior.
- PW with α=0.5 and C=2 starts with k=2 (visits 0,1) — index 0 + index 1 are the only
  considered tokens. If COMMIT is at index 0, the FIRST tokens MCTS evaluates are
  "do nothing" vs "the heuristic's best launch" — exactly the comparison we want.
- (B) would mean MCTS always tries to launch SOMETHING first and only learns to HOLD
  via low UCB scores after many iterations. This biases shallow searches toward
  over-launching.

### 5.3 Angle: deferred to serialization, not encoded in the token

The token is `(src, target, fraction)`. **Angle is NOT in the token.** It's resolved at
serialization time by re-running the heuristic's intercept calculation on the live
state. Justifications:

- Adding 360 angle buckets to every token would explode cardinality to ~190K tokens per
  player per node. Untenable.
- The heuristic already chooses near-optimal angles (sun-safe, intercept-aware). MCTS
  isn't going to find a better angle than `aim_with_prediction` — it would need to
  enumerate angles and test each. Out of scope.
- For comets and orbiting planets, angle DEPENDS ON ETA which DEPENDS ON SHIPS (via
  fleet_speed). Encoding angle in the token would force an early commitment to ETA
  before the bucket → ships resolution is complete.

**Risk:** The serialized angle can fail (sun-blocked, unreachable). Per §4.6 we
silently drop such tokens — the player effectively "wasted" that pick. This is fine in
expectation but could degrade if a high-prior token is consistently invalid in similar
states. Mitigation: at token-generation time, skip tokens whose `compute_angle_for_target`
on the source state returns None. This pre-filters at ranking time rather than
serialization time.

### 5.4 What "no launch" means

Two distinct concepts:

- **COMMIT_TURN token** = "I'm done launching this env-turn; advance simulator". This
  is the sub-tree's terminator.
- **Empty `picks_per_player[p]`** = "player p has 0 launches this turn". Achieved by
  the player picking COMMIT_TURN as their FIRST pick.

These are the same in env semantics (player submits `[]`) but distinct in MCTS bookkeeping.

## 6. PW + FPU + UCB behavior with this action space

### 6.1 PW growth at scale

With ~200 valid tokens per player at a typical mid-game state (after filtering invalid
src/no-ships tokens), PW's k-grows-with-visits behavior matters more than at K=8.

| Sub-node visits | PW k (C=2, α=0.5) | Tokens considered |
|---|---|---|
| 0 | 2 | COMMIT + top 1 heuristic |
| 1 | 2 | (same) |
| 4 | 4 | COMMIT + top 3 heuristic |
| 16 | 8 | COMMIT + top 7 heuristic (likely all heuristic-prior tokens) |
| 64 | 16 | + first 8 long-tail (only triggered if sub-node revisited 64×) |
| 256 | 32 | + 24 long-tail |
| 1024 | 64 | (theoretical; sub-nodes won't see this many visits) |

At ~93 iterations per turn, the ROOT sub-node sees ~93 visits but DEEPER sub-nodes
(after picking 1-3 tokens) see far fewer (the 93 visits split across all the picks tried
at depth 1, then again at depth 2, etc.). Realistic deeper-sub-node visit count: ~10-30.

**This means the long tail (>= 8 token candidates) is rarely activated outside the root
sub-node.** Which is fine — the heuristic-derived prior tokens are the high-signal
choices. Long-tail is there to ensure asymptotic completeness: given infinite budget,
MCTS could eventually find ANY launch combination. At our budget, ~99% of evaluation is
in the prior.

### 6.2 FPU recalibration

In M3, FPU=0.5 was sufficient because variant 0 (heuristic) consistently scored ~0.55+,
so unvisited variants (FPU=0.5) lost UCB and never got picked. **In option 2, the prior
tokens are MORE varied.** Some heuristic launches in the prior may have value below 0.5
(e.g., a defensive reinforcement that only marginally helps); others well above (a
high-value capture).

The risk per `mcts_m2_0wins_20games.md`: if FPU is too LOW relative to the average
visited token's value, exploration starves (M3 mode). If FPU is too HIGH (close to 1.0),
MCTS round-robins through all PW-considered tokens before exploiting (M2 mode).

**Recommendation: start FPU at 0.6 (slightly above the asset-proxy median of ~0.5)**.
Rationale: most random launches in the prior should have value near 0.5 (asset-share
proxy is symmetric around 0.5 in early game). Setting FPU just above this gives
unvisited tokens a slight edge over visited-and-found-mediocre tokens, encouraging
exploration but not round-robin.

This is a tunable. M5 should A/B FPU ∈ {0.4, 0.5, 0.6, 0.7} with token variants
enabled.

### 6.3 UCB at sub-node level

UCB exploration term is computed against the SUB-NODE's visit count, not the
MCTSNode's. This matters because sub-nodes have far fewer visits than the parent
MCTSNode (the parent's visits split across all sub-tree leaves explored).

```python
# At sub-node `sub`, picking next token for player p:
explore = ucb_c * sqrt(log(max(sub.visits, 1)) / sub_token_visits)
```

This is standard UCB1 — just applied at the sub-node level.

### 6.4 Robust child at ROOT — sub-tree replay

After search, recover our player's chosen action by walking the sub-tree from
`root.subtree_root` following argmax-visits at each step until COMMIT:

```python
def extract_action_for_player(root: MCTSNode, player_id: int, alive_players: list[int]) -> list[Action]:
    p_idx = alive_players.index(player_id)
    sub = root.root_subnode(alive_players)
    picks: list[int] = []
    while True:
        # Find argmax-visits token for player_id at this sub
        considered = root.ranked_tokens[player_id]
        # Filter invalid based on prior picks (matches search-time filter)
        valid = filter_invalid(considered, picks, root.state)
        best_idx = 0
        best_visits = -1
        for tok_idx in range(len(valid)):
            v, _ = sub.get_stat(p_idx, tok_idx)
            if v > best_visits:
                best_visits, best_idx = v, tok_idx
        if best_visits <= 0:
            break  # never visited; treat as COMMIT
        token = valid[best_idx]
        if token.is_commit():
            break
        picks.append(token_to_idx_in_root(token, root.ranked_tokens[player_id]))
        # Walk to next sub-node: requires reconstructing the sub-key after this pick.
        # (Other players' picks are part of the key; for replay we use whatever picks
        # they actually made on this argmax-visits path — i.e., recurse into subnode_cache.)
        # IMPLEMENTATION DETAIL: see §9 open question 1 for the multi-player replay subtlety.
        ...
    # Serialize picks to env actions for OUR player only
    return serialize_for_player(picks, root.ranked_tokens[player_id], root.state, player_id)
```

## 7. Cost / iteration table

Concrete per-iteration cost breakdown (measured-style, calibrated to existing perf
probe at 1.77ms/sim-step):

| Cost component | New MCTSNode | Cached MCTSNode |
|---|---|---|
| Token gen (heuristic call + bucket expansion) | ~5.5ms | 0 (cached) |
| Long-tail expansion (lazy, only at PW>=8 visits typical) | ~0.5ms (rare) | ~0.5ms (rare) |
| Sub-tree walk (~3 sub-steps avg, UCB selection per player per step) | ~0.1ms | ~0.1ms |
| Serialize picks → env actions (incl. angle re-computation) | ~1ms | ~1ms |
| Sim step | 1.77ms | 1.77ms |
| Backprop sub-tree path | ~0.05ms | ~0.05ms |
| **Total** | **~8.5ms** | **~3ms** |

At 700ms budget:
- Pure new-node iterations: ~80 iterations
- Pure cached-node iterations: ~230 iterations
- Realistic mix (most iterations re-visit the root, expand 1-2 new env-turn children):
  **~120-150 iterations per turn**

This is comparable to design v2's projected 80-100 and noticeably better than the M3
result (where heuristic call cost limited iterations).

## 8. Transition plan from current compound architecture

### 8.1 Files to ADD

```
src/orbit_wars/mcts/token.py       # LaunchToken dataclass + token_id encoder
src/orbit_wars/mcts/tokens.py      # generate_ranked_tokens + extend_with_long_tail (renamed from ranking.py? see §8.3)
src/orbit_wars/mcts/serialize.py   # serialize_picks_to_env_actions + compute_angle_for_target
src/orbit_wars/mcts/subnode.py     # SubNode dataclass (or inline in node.py — see §8.3)
tests/test_mcts_tokens.py          # token generation, ranking, long-tail
tests/test_mcts_subtree.py         # sub-tree walk, sub-node UCB, COMMIT semantics
tests/test_mcts_serialize.py       # token → env action conversion + validation
tests/test_mcts_option2_e2e.py     # full M3-equivalent search w/ token variants
```

### 8.2 Files to MODIFY

| File | Change |
|---|---|
| `src/orbit_wars/mcts/node.py` | Add `SubNode`, `JointCommit` type alias; modify `MCTSNode` to include `ranked_tokens`, `subnode_cache`, change `children` key type. Move per-player stats from MCTSNode to SubNode. |
| `src/orbit_wars/mcts/search.py` | Replace `_simmcts_iteration` with sub-tree-aware version. Replace robust-child block with sub-tree replay. Add `use_token_variants` branch (delegates to new path or legacy path). |
| `src/orbit_wars/mcts/config.py` | Add `tokens_per_decision`, `max_launches_per_turn`, `use_token_variants`, `long_tail_enabled` fields. |
| `src/orbit_wars/mcts/agent.py` | No structural change; the agent dispatches via `cfg.use_token_variants` (handled inside `search.search`). |
| `src/orbit_wars/heuristic/strategy.py` | NO CHANGE. We re-use `decide_with_decisions` as-is. |
| `src/main.py` | NO CHANGE. The agent module already calls `mcts_agent`; the toggle is in MCTSConfig. |

### 8.3 Files to DELETE OR KEEP-AS-LEGACY

`src/orbit_wars/mcts/ranking.py` (current compound-variant ranker):

**Recommendation: KEEP, gated by `use_token_variants=False`.** Reasons:

- M3 IS a known-good no-regression baseline. Throwing it away loses our floor.
- The feature flag lets us A/B option 1 (heuristic-perturbation variants — the memory
  doc's "pivot option #1") later if option 2 fails its gate. Variants 1..k could be
  retooled into perturbations within the same compound architecture.
- `ranked_actions_with_heuristic` is referenced from `search.py`. Keeping it lets us
  ship M3 unchanged while testing option 2 in parallel.

Rename plan: extract `MCTSNode` modifications behind a `legacy=False` constructor flag,
or keep two parallel node types. I recommend **two node types** — cleaner separation,
no flag-rot inside a single class:

```
src/orbit_wars/mcts/node_legacy.py    # current MCTSNode (compound variants)
src/orbit_wars/mcts/node.py            # NEW MCTSNode (token-based with sub-tree)
```

Search dispatches at the top:

```python
def search(state, cfg, our_player, *, deadline_s=None):
    if cfg.use_token_variants:
        return _search_tokens(state, cfg, our_player, deadline_s)
    return _search_legacy(state, cfg, our_player, deadline_s)
```

### 8.4 Feature-flag rollout (default = OFF for first ladder submission)

Initial submission with `use_token_variants=True` is risky — option 2 is unproven on
ladder. Plan:

1. **Ship M3 (current) ladder build with `use_token_variants=False`**: continues to be
   the known no-regression baseline.
2. **Local A/B**: 100-seed paired-seat tournament with `use_token_variants=True` vs
   `=False`. Gate: token variants ≥ +5% local win rate vs M3 (small but detectable
   given local opponent saturation).
3. **First ladder submission with token variants**: tag explicitly as `mcts-tokens-v1`.
4. **Per CLAUDE.md ladder noise note**: don't conclude lift/regression from one
   submission. ≥3 submissions to confirm.

### 8.5 Test migration

Existing tests:

- `tests/test_mcts_m1_skeleton.py`: NO CHANGE. M1 was just plumbing.
- `tests/test_mcts_m3_pw_fpu.py`: KEEP, runs with `use_token_variants=False`. The PW/FPU
  math itself doesn't change.

New tests (per §8.1).

## 9. Test strategy

### 9.1 Unit tests

**Token generation (`tests/test_mcts_tokens.py`):**

- Empty state (no owned planets) → `[LaunchToken.COMMIT]` only.
- State with 1 owned, 1 enemy → COMMIT + 4 buckets × 1 (src,tgt) = 5 tokens prior; long-
  tail unchanged.
- State with rich heuristic output → tokens count = 1 (COMMIT) + n_decisions ×
  tokens_per_decision; verify ordering (decision 0 first).
- Long-tail: verify it appends `(sources × non-self-targets × buckets) - prior` tokens.

**Sub-tree walk (`tests/test_mcts_subtree.py`):**

- Single iteration: root sub-node has visits=1, exactly one sub-leaf reached.
- Per-iteration sub-tree depth bounded by `max_launches_per_turn`.
- COMMIT short-circuits sub-tree (player picking COMMIT first → sub-leaf at depth 0
  for that player).
- Both players COMMIT immediately → MCTSNode child created with empty actions for
  both; sim step advances.
- After 64 iterations on a fixed state, root subnode visit count ≈ 64.

**Token serialization (`tests/test_mcts_serialize.py`):**

- Token resolves to ships > MIN_LAUNCH for valid bucket; resolves to 0 → skipped.
- Sequence with same src twice: ships pool decremented correctly between picks.
- Invalid token (src=enemy planet) silently dropped (matches env L482-491).
- Angle resolution falls back / fails gracefully when sun-blocked.

**Robust child replay (`tests/test_mcts_replay.py`):**

- After search, replay produces SAME action MCTS would commit to in the next iteration.
- Replay handles unvisited paths (returns COMMIT at first uncommitted depth).

### 9.2 Integration tests

- **Self-play single seed**: token-variants vs token-variants on seed 0; verify game
  completes, both agents legal-move, no exceptions.
- **Token-variants vs heuristic, paired-seat 10 seeds**: gate is "≥ 5 ties or wins out
  of 20 paired games" — i.e., NOT-zero-wins. The M3 result was 0 ties, 0 wins; we want
  non-trivial improvement.

### 9.3 Local A/B (the success gate before Kaggle)

100-seed paired-seat (200 games total) with `use_token_variants=True` vs `=False`.

- **Pass gate**: token-variants ≥ +5% win rate (i.e., ≥105/200 wins, vs ~100 expected
  if equal). This is small but detectable given local opponents' saturation.
- **Fail gate**: token-variants < 90/200. Investigate before any Kaggle submission.
- **In between (90-104)**: marginal; still ladder-test it (Kaggle ladder may
  differentiate where local doesn't), but flag concerns.

### 9.4 Kaggle ladder gate

Per design v2 §1: **≥3 consecutive submissions show ladder μ ≥ best_heuristic + 50.**
With 3/day submission limit and 4-6h μ stabilization (CLAUDE.md), this is ~3 days
minimum. For option 2 specifically, lower the gate to **+30 μ** for first cut — the
literature evidence is for a successful *integration*, not for any specific lift; even
small lift ratifies the architecture.

### 9.5 Tools to build / extend

- **Reuse `src/tools/mcts_picks_diag.py`**: it currently logs `our_action_idx` per turn.
  Extend to log the COMMITTED token sequence per turn. Track variant-pick distribution
  + token diversity. M3's "100% variant 0" was the smoking gun; equivalent for option 2
  should be "tokens diversify across the ranking" — if option 2 always picks
  COMMIT-COMMIT, that's the same failure mode as M3 (heuristic-equivalent + overhead).
- **New: `src/tools/mcts_subtree_diag.py`**: dump the sub-tree structure for one turn
  (token visit counts at each sub-node, value sums). Visual debugging when a particular
  game goes wrong.

## 10. Risk register

### Risk 1: Per-iteration cost explosion if token cardinality scales worse than expected

**Severity: HIGH**

The §2.2 estimate was ~530 tokens per player per node. If a real mid-game state has 12
owned planets and 24 targets, that's 12 × 24 × 4 = 1152 tokens. Long-tail expansion
becomes ~1ms even with cheap distance sort. PW caps the *considered* set, but
generation must still touch all candidates.

**Mitigation:**
- Long-tail is OFF by default (`long_tail_enabled=False`); only the heuristic-derived
  prior tokens are used. This caps tokens per node at ~25-40.
- If empirical results show long-tail matters, enable selectively (e.g., only at root)
  and profile.
- Hard cap on `len(ranked_tokens)` at ~200 — beyond that, drop lowest-priority tail.

### Risk 2: Incorrect token-to-env-action serialization

**Severity: HIGH**

The serializer must:
1. Resolve fraction → ships against the CURRENT (post-prior-picks) ship pool.
2. Compute angle correctly for static / orbiting / comet targets (matching heuristic).
3. Validate via `validate_move` before emitting.

A bug in any of these silently corrupts the token semantics. MCTS would learn against a
"phantom" version of the game.

**Mitigation:**
- Property test: for any (state, player, picks) triple, the serialized actions when
  passed to `Simulator.step()` produce the same next-state as if the heuristic had made
  the same launches with the same (src, target, ships) tuples. Run on 100 random
  states.
- Spot test: a single token (src=A, target=B, bucket=ALL) serializes to exactly the
  heuristic's launch from A to B with all available ships, with the same angle.

### Risk 3: Opponent-modeling mismatch — opponents submit compound actions while we compose token-by-token

**Severity: MEDIUM-HIGH**

In an env turn, the opponent submits `list[list[float|int]]` atomically. Our MCTS sub-
tree treats each opponent's action as a SEQUENCE of token picks. **Inside one env-turn,
the opponent has no actual choice** — they submit one action list, period. Modeling
their per-turn launches as decoupled UCT picks at each sub-step is a fiction.

This is technically OK because:
- The fiction only affects the SEARCH STRATEGY (how we explore the opponent's possible
  actions during planning). The actual opponent's submitted action is fixed at sim time.
- The fiction's bias is symmetric — we model the opponent the same way we model
  ourselves. If our token-by-token decomposition is good for us, modeling the opponent
  the same way is reasonable.

But the fiction's CORRECTNESS depends on whether token-by-token decomposition can
EXPRESS the opponent's compound action. If the opponent uses a launch combination that
no token sequence can produce (e.g., their angle is hand-tuned, not via
aim_with_prediction), we under-model them.

**Mitigation:**
- The symmetric-heuristic assumption (design v2 §3.4) means we model opponents using
  OUR heuristic's action distribution. So token-by-token correctly decomposes WHATEVER
  the heuristic would produce — no expressiveness gap.
- For non-heuristic opponents (top-agent ladder players), the gap is real but it's
  ALSO present in the legacy compound-variant approach (variants are still
  heuristic-derived). So this isn't a regression vs M3 — it's an unavoidable cost of
  not having a learned opponent model.
- M5+: revisit if/when an opponent model lands.

### Risk 4: Simulator API mismatch — `Simulator.step()` expects atomic per-turn actions

**Severity: LOW (already designed around)**

`Simulator.step(state, actions: dict[player, list[Action]]) -> SimState` advances ONE
env turn given EACH player's full per-turn actions. Our sub-tree composes these
incrementally inside one MCTS iteration, then calls step ONCE at the sub-leaf.

The risk is if the simulator ALSO has internal per-launch state that gets desynchronized
when we compose actions outside the simulator. E.g., if the simulator's
`_phase_2_apply_actions` cared about LAUNCH ORDER (which it does — env L489 process
players in sorted player_id order), then our composition must respect that order.

**Mitigation:**
- We always call `Simulator.step()` once per env-turn, with all launches batched.
  Simulator's launch ordering is preserved.
- Test (`test_mcts_serialize.py`): launches A then B (two tokens in sequence) produces
  same sim state as launches B then A IFF sources don't share. If sources DO share,
  ordering matters and the sub-tree composition must match the env's sorted-player-id
  order. Verify by running both orderings and comparing.

### Risk 5: Value proxy collapse — depth doesn't capture multi-launch turn outcome

**Severity: MEDIUM**

The asset-count proxy at leaf is computed at the end of one env-turn (not at end of
sub-tree). If the multi-launch composition produces a turn that's good in immediate
sense (captured a planet) but bad in 2-3 turn sense (the captured planet flips back),
asset-count at depth 1 would over-estimate.

This is a generic problem but it's amplified by option 2 because the token space
ENCOURAGES exploring multi-launch combinations the heuristic wouldn't try, which may
include unconventional choices that look good immediately but bad later.

**Mitigation:**
- Already partially mitigated by the asset proxy's `production_horizon=8` lookahead
  (in `value.py`).
- M4 (heuristic value at leaf) directly addresses this. With option 2, prioritize M4.
- Add a NEGATIVE-CONTROL test: states where the heuristic picks "do nothing" because
  all launches lose ships. With option 2, MCTS should also pick mostly-COMMIT — verify
  this.

### Risk 6: Variant-0 fallback parity — option 2 must reduce to heuristic in the limit

**Severity: MEDIUM**

In M3, variant 0 = full heuristic, so worst-case MCTS pick = heuristic exactly. In
option 2, no single token IS the heuristic; the heuristic's full action is reproduced
as a SEQUENCE of tokens. If MCTS picks any subset of those tokens, the action diverges
from heuristic.

This is by design (we WANT MCTS to deviate). But it means we lose the "MCTS-equivalent-
to-heuristic" guarantee that M3's variant 0 provided. If MCTS times out at iteration 1,
the resulting action might be far worse than heuristic.

**Mitigation:**
- Time-pressure fallback: if elapsed time exceeds 80% of budget AND root subnode visits
  < threshold (e.g., 20), fall through to direct heuristic call. Already supported by
  the fallback path in `agent.py`; just need to plumb the visit-count check.
- Default to COMMIT-first for any player whose root sub-node has 0 visits at end of
  search (instead of arbitrarily returning the first ranked token).

### Risk 7: Replay ambiguity — multi-player robust child

**Severity: LOW-MEDIUM**

When walking the sub-tree from root to extract OUR action, the path also depends on the
OPPONENT's robust child at each step. If the opponent's argmax-visits path diverges
from what they actually picked in the most-visited committed key, our extracted action
may not be the one we'd commit to.

**Mitigation:**
- Use the most-visited COMMITTED CHILD (`root.children[committed_key]`) to find the
  joint pick set, then extract OUR player's part. This guarantees our action is from
  the actually-most-explored branch.
- See §9 open question 1 for the implementation detail.

## 11. Open questions (flagged for human decision)

1. **Multi-player sub-tree replay — should we use most-visited COMMITTED CHILD or argmax-
   visits sub-tree walk?**
   - Most-visited committed child is unambiguous but may not align with our player's
     argmax visits at each sub-step.
   - Argmax-visits walk is independent for our player but ambiguous about opponent's
     path (which affects which sub-nodes are visited).
   - **Default in this design: most-visited COMMITTED CHILD.** Cleanest semantics.
     Empirical test in M2-equivalent gate would catch issues.

2. **Should `tokens_per_decision` be 2, 3, or 4?**
   - 2: minimal per-decision tokens (chosen + 1 nearby bucket). Smaller prior, faster
     ranking.
   - 3: chosen + 2 nearby. Default I picked.
   - 4: all buckets per decision. Largest prior.
   - **Default: 3.** A/B test in M5.

3. **Should COMMIT_TURN be a SHARED token across all players (joint pick at sub-step)
   or per-player?**
   - Per-player (this design's choice): each player independently commits when ready.
     Asymmetric commits supported.
   - Shared: both players must agree to commit before sim advances. Forces alignment.
   - **Default: per-player.** Aligns with decoupled UCT's independence assumption.

4. **Should the long-tail be ranked by L2 distance or by full heuristic re-call with
   modified parameters?**
   - L2 distance: cheap (~µs), no re-rank cost.
   - Full heuristic re-call with e.g. bumped `weak_enemy_threshold`: more accurate but
     ~5ms per call.
   - **Default: L2 distance.** Long tail is rarely activated; not worth the cost.

5. **Should we abandon option 2 and pivot to "Heuristic-perturbation variants" (memory
   doc Pivot #1) if local A/B fails?**
   - Per §1.3, this is the strategically-correct fallback. The user has chosen option 2
     first; if it fails the local gate (§9.3), pivot to perturbation variants is
     ~half-day work (vs ~2 days for option 2).
   - **Recommendation: explicit decision after local A/B. If win rate < 90/200, pivot.**

6. **Should `use_token_variants` default to True or False on first ladder submission?**
   - True: gives us actual ladder data on option 2. But high downside risk (-100 μ
     possible if option 2 underperforms).
   - False: ships M3 as the baseline, runs token variants only via local A/B until proven.
   - **Recommendation: False by default. Submit token variants as a SECOND submission
     once local A/B passes. Rationale: ladder slots are scarce (3/day), and CLAUDE.md
     notes per-submission noise of ±100 μ — a regression on a key submission burns
     attention budget for days.**

## 12. Summary of architectural choices

- **Action element**: `LaunchToken(src, target, fraction_bucket)`; angle deferred to
  serialization. ~25-40 prior tokens per player per node typical; ~530 with long-tail.
- **Multi-launch composition**: APPROACH (a) + (c) — sub-tree per env-turn, capped at
  `MAX_LAUNCHES_PER_TURN=4`. SubNode owns per-player UCB stats; MCTSNode owns env-turn
  state and committed-children dict.
- **Move-ordering function `f`**: heuristic's `decide_with_decisions` → bucketed tokens.
  COMMIT at index 0.
- **PW + FPU**: PW with C=2, α=0.5 (unchanged). FPU recalibrated to 0.6 (slightly
  above asset-proxy median).
- **Robust child**: most-visited COMMITTED CHILD at root (NOT argmax-visits-walk).
- **Feature flag**: `MCTSConfig.use_token_variants` (default False on first ladder
  submission; True after local A/B passes).
- **Test gate**: ≥105/200 paired-seat wins locally before Kaggle submission. Then
  ≥+30 μ over 3 ladder submissions to confirm.
