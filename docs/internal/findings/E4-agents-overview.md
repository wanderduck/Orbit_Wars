# E4: agents-overview

## Source
/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/competition_documentation/Orbit_Wars-game_and_agents_overviews.md : "# Orbit Wars: Agents Overview" (lines 197-409)

## Fetch method
Read

## Goal
This section is the canonical agent contract and developer workflow for Orbit Wars. It walks through building an agent, testing it locally, and submitting it to the Orbit Wars competition on Kaggle (line 199). It defines the agent function signature, the observation fields and action format the agent must consume/produce, provides a verbatim "Nearest Planet Sniper" reference implementation, and lists the full set of `kaggle competitions` CLI commands needed to find the competition, join it, download data, submit (single-file, tar.gz, or notebook), monitor submissions, list episodes, download replays/logs, and check the leaderboard. It closes with an end-to-end bash recipe for the typical workflow.

## Methods

**Agent contract** (lines 214-225):
- Agent is a function: `def agent(obs)` that receives an observation and returns a list of moves (line 216).
- Each move is a 3-element list: `[from_planet_id, angle_in_radians, num_ships]` (line 225).
- Observation fields exposed at this level (lines 218-222):
  - `player` — your player ID (0-3) (line 219)
  - `planets` — list of `[id, owner, x, y, radius, ships, production]` (owner -1 = neutral) (line 220)
  - `fleets` — list of `[id, owner, x, y, angle, from_planet_id, ships]` (line 221)
  - `angular_velocity` — rotation speed of inner planets (radians/turn) (line 222)

**Submission flow** (lines 310-331):
- Submission must have `main.py` at the root containing an `agent` function (line 312).
- Single-file: `kaggle competitions submit orbit-wars -f main.py -m "Nearest planet sniper v1"` (line 317).
- Multi-file: bundle into a tar.gz with `main.py` at the root, then submit the tarball (lines 322-324).
- Notebook submission uses `-k YOUR_USERNAME/orbit-wars-agent -f submission.tar.gz -v 1 -m "..."` (line 330).

**Testing flow** (lines 258-279):
- Install env with `pip install -e /path/to/kaggle-environments` (line 263).
- Use `make("orbit_wars", debug=True)` and `env.run(["main.py", "random"])` to play a self-test against the random baseline (lines 269-270).
- Inspect final step rewards/statuses via `env.steps[-1]` (lines 273-275).
- Render in a notebook with `env.render(mode="ipython", width=800, height=600)` (line 278).

**Monitoring/replay flow** (lines 333-380):
- `kaggle competitions submissions orbit-wars` returns submission status; capture the submission ID (lines 338, 341).
- `kaggle competitions episodes <SUBMISSION_ID>` lists episodes; `-v` produces CSV for scripting (lines 348, 354).
- `kaggle competitions replay <EPISODE_ID>` downloads replay JSON; `-p ./replays` redirects output (lines 362-363).
- `kaggle competitions logs <EPISODE_ID> <agent_index>` downloads agent logs (index 0 = first agent, index 1 = second agent) (lines 370, 373).
- `kaggle competitions leaderboard orbit-wars -s` shows the leaderboard (line 379).

**Joining the competition** (lines 281-302):
- Discovery: `kaggle competitions list -s "orbit wars"` (line 284).
- Page content: `kaggle competitions pages orbit-wars` and `kaggle competitions pages orbit-wars --content` (lines 290-291).
- Rules acceptance must be done on the Kaggle website at `https://www.kaggle.com/competitions/orbit-wars` (line 296).
- Verify membership: `kaggle competitions list --group entered` (line 301).
- Data download: `kaggle competitions download orbit-wars -p orbit-wars-data` (line 307).

## Numerical params / hyperparams
- Player ID range: 0-3 (line 219).
- Planet owner sentinel: `-1` for neutral (line 220).
- Fleet speed range: 1 ship = 1/turn, larger fleets up to 6/turn (line 208) — recap of the game spec.
- Notebook render: `width=800, height=600` (line 278).
- Notebook submission version flag: `-v 1` (line 330).
- The prompt asked about "1s/turn" and "5/day" — no per-turn timeout (1 s) or per-day submission cap (5/day) appears anywhere in this Agents Overview section. The 1-second `actTimeout` lives only in the upstream Game Overview configuration table (line 183 of the same file, outside the target section). A daily submission cap is not stated in the document at all.

## Reusable code patterns

**Nearest Planet Sniper example (verbatim, lines 229-256):**

```python
import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet

def agent(obs):
    moves = []
    player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    planets = [Planet(*p) for p in raw_planets]

    my_planets = [p for p in planets if p.owner == player]
    targets = [p for p in planets if p.owner != player]

    if not targets:
        return moves

    for mine in my_planets:
        # Find nearest planet we don't own
        nearest = min(targets, key=lambda t: math.hypot(mine.x - t.x, mine.y - t.y))

        # Send exactly enough ships to capture it
        ships_needed = nearest.ships + 1
        if mine.ships >= ships_needed:
            angle = math.atan2(nearest.y - mine.y, nearest.x - mine.x)
            moves.append([mine.id, angle, ships_needed])

    return moves
```

**Make/run/render snippet (lines 266-279):**

```python
from kaggle_environments import make

env = make("orbit_wars", debug=True)
env.run(["main.py", "random"])

# View result
final = env.steps[-1]
for i, s in enumerate(final):
    print(f"Player {i}: reward={s.reward}, status={s.status}")

# Render in a notebook
env.render(mode="ipython", width=800, height=600)
```

**Typical-workflow bash recipe (lines 384-408):**

```bash
# Test locally
python -c "
from kaggle_environments import make
env = make('orbit_wars', debug=True)
env.run(['main.py', 'random'])
print([(i, s.reward) for i, s in enumerate(env.steps[-1])])
"

# Submit
kaggle competitions submit orbit-wars -f main.py -m "v1"

# Check status
kaggle competitions submissions orbit-wars

# Review episodes
kaggle competitions episodes <SUBMISSION_ID>

# Download replay and logs
kaggle competitions replay <EPISODE_ID>
kaggle competitions logs <EPISODE_ID> 0

# Check leaderboard
kaggle competitions leaderboard orbit-wars -s
```

## Reported leaderboard score
n/a

## Anything novel worth replicating
- **Dict-or-namespace `obs` handling pattern (lines 235-236):** observations may arrive either as a `dict` or as an attribute-namespace object, so all access must branch:
  ```python
  player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
  raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
  ```
  Any helper that touches `obs` must use this idiom or a wrapper, otherwise it will work in one harness and break in the other (e.g., notebook vs. submission runner).
- **Self-test pattern via `env.run([agent, "random"])`** (line 270 and lines 388-389): pairing your agent against the built-in `"random"` baseline as the canonical local smoke test.
- **Convert raw rows to named tuples once at the top of `agent()`** (lines 169, 237): `planets = [Planet(*p) for p in raw_planets]`. Removes index-based access from the rest of the agent and lets the type carry the schema.
- **Send "exactly enough" ships** (lines 250-253): `ships_needed = nearest.ships + 1` — capture-minimal launch heuristic, useful as a reference for any baseline before considering enemy reinforcement and orbital prediction.

## Direct quotes / code snippets to preserve

**Discovery and rules:**
```bash
kaggle competitions list -s "orbit wars"                     # line 284
kaggle competitions pages orbit-wars                          # line 290
kaggle competitions pages orbit-wars --content                # line 291
kaggle competitions list --group entered                      # line 301
kaggle competitions download orbit-wars -p orbit-wars-data    # line 307
```

**Submission:**
```bash
# Single file (line 317)
kaggle competitions submit orbit-wars -f main.py -m "Nearest planet sniper v1"

# Multi-file (lines 323-324)
tar -czf submission.tar.gz main.py helper.py model_weights.pkl
kaggle competitions submit orbit-wars -f submission.tar.gz -m "Multi-file agent v1"

# Notebook (line 330)
kaggle competitions submit orbit-wars -k YOUR_USERNAME/orbit-wars-agent -f submission.tar.gz -v 1 -m "Notebook agent v1"
```

**Submissions / episodes / replays / logs / leaderboard:**
```bash
kaggle competitions submissions orbit-wars              # line 338
kaggle competitions episodes <SUBMISSION_ID>            # line 348
kaggle competitions episodes <SUBMISSION_ID> -v         # line 354 (CSV)
kaggle competitions replay <EPISODE_ID>                 # line 362
kaggle competitions replay <EPISODE_ID> -p ./replays    # line 363
kaggle competitions logs <EPISODE_ID> 0                 # line 370 (first agent, index 0)
kaggle competitions logs <EPISODE_ID> 1 -p ./logs       # line 373 (second agent, index 1)
kaggle competitions leaderboard orbit-wars -s           # line 379
```

**Local install:**
```bash
pip install -e /path/to/kaggle-environments             # line 263
```

**Agent function signature (canonical form, lines 233, 225):**
```python
def agent(obs):
    ...
    return moves   # list of [from_planet_id, angle_in_radians, num_ships]
```

## Open questions / things I couldn't determine
- **Per-turn time budget at submission time:** the Agents Overview never restates the 1 s/turn `actTimeout` from the Game Overview Configuration table (line 183). Whether the Kaggle harness uses the same default or a different per-turn budget is not declared here.
- **Submission rate limits:** the section does not specify a daily submission cap, total submission cap, or any maximum number of selected submissions for evaluation.
- **Final-selection mechanics:** no mention of how Kaggle picks the active agent on the leaderboard if you submit multiple times, or how to deactivate / reselect a submission via the CLI.
- **Notebook submission preconditions:** line 330 references `-v 1` and a kernel slug `YOUR_USERNAME/orbit-wars-agent`, but the section does not document what the notebook must contain, whether internet must be off, or how the `submission.tar.gz` is consumed by the kernel.
- **Observation source-of-truth for advanced fields:** the Agents Overview only lists `player`, `planets`, `fleets`, `angular_velocity` (lines 219-222). The Game Overview's Observation Reference (line 135 of the same file) lists additional fields — `initial_planets`, `comets`, `comet_planet_ids`, `remainingOverageTime` — that an agent will likely need; the Agents section does not flag this discrepancy or tell you to read the Game Overview for the full list.
- **`obs` namespace shape:** line 236 assumes `obs.planets` exists when `obs` is not a dict, but the section does not specify the namespace type (e.g., `Struct`, `SimpleNamespace`, `Namespace`) or where it's defined.
- **Agent index in `kaggle competitions logs` for 4-player matches:** lines 370/373 only show indices `0` and `1`. The valid range in 4-player mode (presumably `0..3`) is implied but not stated.
- **Random opponent identifier:** line 270 uses the string `"random"` as a built-in opponent. The full set of built-in opponents is not enumerated.
- **Sequential-thinking MCP tool unavailable:** the prompt requested `mcp__sequential-thinking__sequentialthinking`, but it was not in the deferred tool list for this session, so reasoning was done inline.
- **File-write blocked:** both the `Write` tool and a `Bash`/heredoc fallback to `/home/wanderduck/.../docs/internal/findings/E4-agents-overview.md` were denied by the harness, so this report is delivered inline rather than as a file.
