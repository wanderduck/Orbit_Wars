# E5: bovard-getting-started

## Source
https://www.kaggle.com/code/bovard/getting-started

## Fetch method
kaggle kernels pull (succeeded). The uv run kaggle kernels pull bovard/getting-started -p PROJECT_PATH -m command worked when targeted at a path inside the project tree (sandbox blocked /tmp writes for that command). Notebook landed at the findings directory along with kernel-metadata.json. Two prior WebFetch attempts to kaggle.com/code/... returned only the page title (Kaggle is JS-rendered and reCAPTCHA-gated). The notebook is small: 13 cells total (7 code, 6 markdown), no recorded execution outputs in the pulled JSON.

## Goal
Provide an officially-blessed onboarding walkthrough for the Orbit Wars competition: install kaggle-environments>=1.28.0, instantiate the env, inspect the observation shape, build a single deterministic baseline agent (nearest planet sniper), run it against the built-in random opponent in both 2P and 4P FFA, then write the agent to main.py and submit. The notebook is deliberately minimal -- it only ships ONE custom agent (the sniper). It does NOT define standalone random_agent or idle_agent reference implementations; instead it relies on the env built-in string aliases (notably random).

## Methods
- Framework: kaggle_environments v1.28.0+ (cell 1 forces upgrade), make("orbit_wars", debug=True) to construct the env (cells 2, 4, 7, 9).
- Agent execution: env.run([agent_a, agent_b]) accepts either Python callables or string names of built-ins. "random" is used as the string-name baseline (cells 4, 7).
- Observation handling: dual-mode access pattern guarding for both dict-style and attribute-style obs via isinstance(obs, dict) (cells 4, 6, 11). This is the single most important reusable idiom.
- Decoding helpers: Planet and Fleet named tuples imported from kaggle_environments.envs.orbit_wars.orbit_wars (cells 4, 6, 11). The notebook never instantiates Fleet even though it imports it in cell 4 -- the sniper agent ignores in-flight fleets entirely.
- Algorithm: greedy nearest-neighbor heuristic. For each owned planet, pick the closest non-owned planet (Euclidean), compute atan2(dy, dx) for the launch angle, send max(target.ships + 1, 20) ships if available (cell 6).
- Visualization: env.render(mode="ipython", width=800, height=600) for in-notebook playback (cells 7, 9).
- Submission: %%writefile main.py cell magic dumps the agent function into a top-level main.py (cell 11). Bovard explicitly notes three submission paths: web Submit Agent button, Kaggle CLI, or notebook submission with a main.py/submission.tar.gz (cell 10).

## Numerical params / hyperparams
- kaggle-environments>=1.28.0 -- minimum env version (cell 1).
- episodeSteps printed but not overridden -- defaults to 500 per the competition docs (cell 2).
- Render dimensions: width=800, height=600 (cells 7, 9).
- Min-ship floor for a launch: 20 -- agent will not launch fewer than 20 ships even if target.ships + 1 < 20 (cell 6, 11). This is the ONE magic number in the agent and is not justified in commentary.
- Ship surplus over target garrison: +1 (cell 6, 11). Note: this assumes the target garrison is static during fleet transit, which bovard later flags as a known bug.
- Player slice for observation peek: env.steps[1][0] -- step 1 (first action step, NOT step 0 which is initial state), agent index 0 (cell 4).
- 4-player FFA test uses 4 instances of the same nearest_planet_sniper callable (cell 9) -- mirror match.

## Reusable code patterns

cell 1 (code) -- install pin:
```python
%%capture
!pip install --upgrade "kaggle-environments>=1.28.0"
```

cell 2 (code) -- env handshake / spec inspection:
```python
from kaggle_environments import make

env = make("orbit_wars", debug=True)
print(f"Environment: {env.name} v{env.version}")
print(f"Players: {env.specification.agents}")
print(f"Max steps: {env.configuration.episodeSteps}")
```

cell 4 (code) -- observation decode + named-tuple imports + step-1 peek:
```python
env = make("orbit_wars", debug=True)
env.run(["random", "random"])

from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet

obs = env.steps[1][0].observation  # step 1 = first action step
planets = [Planet(*p) for p in obs.planets]
print(f"Player: {obs.player}")
print(f"Angular velocity: {obs.angular_velocity:.4f} rad/turn")
print(f"\nPlanets ({len(planets)}):")
for p in planets[:6]:
    owner_str = f"Player {p.owner}" if p.owner >= 0 else "Neutral"
    print(f"  id={p.id} owner={owner_str:10s} pos=({p.x:.1f}, {p.y:.1f}) r={p.radius:.1f} ships={p.ships} prod={p.production}")
```

cell 6 (code) -- the canonical dual-mode obs unpack + nearest-target launcher (lift verbatim):
```python
import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet

def nearest_planet_sniper(obs):
    moves = []
    player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    planets = [Planet(*p) for p in raw_planets]

    # Separate our planets from targets
    my_planets = [p for p in planets if p.owner == player]
    targets = [p for p in planets if p.owner != player]

    if not targets:
        return moves

    for mine in my_planets:
        # Find the nearest planet we do not own
        nearest = None
        min_dist = float("inf")
        for t in targets:
            dist = math.sqrt((mine.x - t.x)**2 + (mine.y - t.y)**2)
            if dist < min_dist:
                min_dist = dist
                nearest = t

        if nearest is None:
            continue

        # How many ships do we need? Target garrison + 1
        ships_needed = max(nearest.ships + 1, 20)

        # Only send if we have enough
        if mine.ships >= ships_needed:
            # Calculate angle from our planet to the target
            angle = math.atan2(nearest.y - mine.y, nearest.x - mine.x)
            moves.append([mine.id, angle, ships_needed])

    return moves
```

cell 7 (code) -- canonical local-test recipe + reward inspection + render:
```python
env = make("orbit_wars", debug=True)
env.run([nearest_planet_sniper, "random"])

final = env.steps[-1]
for i, s in enumerate(final):
    print(f"Player {i}: reward={s.reward}, status={s.status}")

env.render(mode="ipython", width=800, height=600)
```

cell 9 (code) -- 4-player FFA mirror-match recipe:
```python
env4 = make("orbit_wars", debug=True)
env4.run([nearest_planet_sniper, nearest_planet_sniper, nearest_planet_sniper, nearest_planet_sniper])

final = env4.steps[-1]
for i, s in enumerate(final):
    print(f"Player {i}: reward={s.reward}, status={s.status}")

env4.render(mode="ipython", width=800, height=600)
```

cell 11 (code) -- submission packaging:
```python
%%writefile main.py
import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet

def nearest_planet_sniper(obs):
    # ... [identical body to cell 6]
```
The body of the function in cell 11 is byte-for-byte identical to cell 6.

## Reported leaderboard score
n/a

## Anything novel worth replicating
- The dual-mode observation unpack (isinstance(obs, dict)) is the safest Orbit Wars idiom and should be the project standard agent preamble. It survives both local debug runs and the Kaggle judging harness, which apparently disagree on dict-vs-object obs.
- Using env.steps[1] (NOT env.steps[0]) to grab the first observation that contains an action-time view -- step 0 is the pre-action initial state and confusingly does not carry the same fields.
- Using string aliases like random as opponents in env.run(...) instead of writing your own random agent. Cleaner CI tests; one less file to maintain.
- The 4-player mirror match env.run([agent, agent, agent, agent]) as a quick stability/sanity check before submitting -- exposes degenerate behavior when an agent is its own opponent.
- %%writefile main.py directly from the notebook is the lowest-friction way to keep the prototyping notebook and submission file in lockstep -- worth adopting for our own sub-notebooks.
- Environment version pin >=1.28.0 is a tight floor; we should mirror this in our own pyproject.toml.
- The max(target.ships + 1, 20) floor implies bovard knows raw +1 launches are extremely fragile (any production tick during travel flips the outcome). A 20-ship cushion is the simplest mitigation; we should probably scale this by predicted travel time, not use a flat constant.

## Direct quotes / code snippets to preserve

cell 0 (md), the canonical one-liner that should headline our README:
> Conquer planets rotating around a sun! Players send fleets of ships between planets to capture territory in a continuous 100x100 space.

cell 8 (md), the explicit list of starter-agent failure modes -- bovard is openly telegraphing improvement axes:
> The sniper agent has a few problems:
> - It does not account for travel time -- the target planet produces ships while the fleet is in transit
> - It sends fleets from every planet, even if multiple are targeting the same planet
> - It ignores the sun -- fleets aimed through the center get destroyed
> - It holds ships on planets that have no nearby targets instead of consolidating

cell 10 (md), submission options enumerated:
> You can either submit a main.py, a tar.gz (or zip) with a main.py in it, or submit a notebook with a main.py or submission.tar.gz
>
> There are three ways to subit.
> 1. using the Submit Agent button on the homepage and uploading the file
> 2. using the Kaggle CLI (as described in agents.py in the competition dataset)
> 3. submitting a notebook with a main.py or submission.tar.gz

Note bovard typo "subit" preserved verbatim. He also references an agents.py file in the competition dataset; we should locate that file for further patterns.

cell 12 (md), submit-button instruction:
> Now that we have a main.py, all you need to do is click Submit to competition on the right and watch your entry show up on the competition leaderboard! Best of luck!

## Open questions / things I could not determine
- bovard references an agents.py in the competition dataset (cell 10) for CLI submission instructions. The pulled kernel-metadata.json lists competition_sources: [orbit-wars] but no dataset, so the referenced file lives in the competition data download (kaggle competitions download orbit-wars). We have not inspected it yet -- it likely contains additional reference agent code or shell snippets.
- No leaderboard score for the sniper itself is mentioned anywhere in the notebook; we have no calibration point for what does a naive baseline look like.
- The notebook does NOT actually demonstrate fleet observation parsing despite importing Fleet. Bovard intent there is unclear -- possibly stub for a future cell, possibly a hint that students should extend the agent to react to incoming fleets.
- The 20-ship minimum is unjustified. There is no explanation of why this magnitude (vs. 10, 50, or scaling by target.production * estimated_travel_turns).
- The notebook includes no explicit timeout / actTimeout discussion (default 1s per turn per the competition docs). The sniper is O(my_planets * targets) which is trivial, but for any non-trivial agent we will need to budget against this.
- Cell 1 uses %%capture to silence the install. The pulled .ipynb had no execution outputs cached (no execution_count, no stdout), so we cannot see what version actually got installed at the time of authorship -- we only know the pin floor.
- No mention of self-play tournament infrastructure, ELO tracking, or scripted opponents beyond random. The notebook is intentionally narrow.
