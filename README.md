# Wanderduck's Orbit Wars Submission

-   This project contains my submission to the Kaggle Competition: [Orbit Wars](https://www.kaggle.com/competitions/orbit-wars/overview)

[[[ **NOTE**: This README.md is incomplete; this is just a placeholder.]]]

## File Structure

-   **docs/**: directory containing various documentation files, primarily in Markdown format
-   **src/**: directory containing any user created `.py` or otherwise scripts I may use to develop or submit my competition submission
-   **notebooks**: directory containing any `.ipynb` files for creating, editing, or submitting my submission (if needed)
-   **images**: directory containing any images used in `.ipynb` notebooks or `.md` Markdown files (or anywhere else)

---

## Codebase Flow

Visual map of the Orbit Wars repository: how the source tree is laid out, which file imports which, and what runs at submission time vs. local development time.

The submission entry point is `src/main.py`. Everything else is either a helper module that backs the agent (`src/orbit_wars/`), a local-only opponent or RL scaffold (not packaged into submissions), or developer tooling (`src/tools/`, `tests/`).

---

### 1. Module dependency graph (`src/`)

Top-down view of the import graph. An arrow `A --> B` means "A imports from B". Third-party packages (`scipy`, `numpy`, `torch`, `gymnasium`, `typer`, `kaggle_environments`) are shown only where they materially shape the design.

```mermaid
graph TD
    classDef entry fill:#1f6feb,stroke:#0d419d,color:#fff
    classDef core fill:#2ea043,stroke:#1a7f37,color:#fff
    classDef heuristic fill:#9a6700,stroke:#7d4e00,color:#fff
    classDef opponent fill:#8250df,stroke:#5a32a3,color:#fff
    classDef tool fill:#6e7781,stroke:#424a53,color:#fff
    classDef rl fill:#bf3989,stroke:#7d2660,color:#fff
    classDef ext fill:#eaeef2,stroke:#6e7781,color:#1f2328

    main["src/main.py<br/><i>agent</i> (Kaggle entry)"]:::entry

    subgraph orbit_wars["src/orbit_wars/"]
        geometry["geometry.py<br/>dist · fleet_speed · safe_angle_and_distance"]:::core
        state["state.py<br/>ObservationView · obs_get"]:::core
        rotation["rotation.py<br/>predict_planet_position"]:::core
        world["world.py<br/>WorldModel · aim_with_prediction<br/>path_collision_predicted · estimate_fleet_eta"]:::core

        subgraph heuristic["heuristic/"]
            strategy["strategy.py<br/>agent · _decide<br/>_plan_offense_greedy / _hungarian<br/>find_threats · plan_defense"]:::heuristic
            config["config.py<br/>HeuristicConfig"]:::heuristic
        end

        subgraph opponents["opponents/ (local sparring only)"]
            comp["competent_sniper.py"]:::opponent
            agg["aggressive_swarm.py"]:::opponent
            def_t["defensive_turtle.py"]:::opponent
            peer["peer_mdmahfuzsumon.py"]:::opponent
        end

        subgraph rl["rl/ (v2+ stubs)"]
            rl_env["env.py"]:::rl
            rl_pol["policy.py"]:::rl
            rl_train["train.py"]:::rl
            rl_eval["eval.py"]:::rl
            rl_remote["remote.py"]:::rl
        end
    end

    subgraph tools["src/tools/"]
        cli["cli.py (Typer app)"]:::tool
        diag["diagnostic.py"]:::tool
        trace["trace_launch.py"]:::tool
        pcoll["path_collision_instrumentation.py"]:::tool
        pack["pack.py"]:::tool
    end

    kenv["kaggle_environments<br/>(orbit_wars env)"]:::ext
    scipy["scipy.optimize"]:::ext
    torch["torch / gymnasium"]:::ext

    main --> strategy

    strategy --> world
    strategy --> state
    strategy --> geometry
    strategy --> config
    strategy --> scipy

    world --> geometry
    world --> rotation
    world --> state

    rotation --> geometry
    rotation --> state

    state --> kenv
    peer --> kenv

    rl_pol --> torch
    rl_env --> torch
    rl --> rl_pol

    cli --> pack
    diag --> strategy
    diag --> config
    trace --> strategy
    trace --> config
    trace --> geometry
    trace --> main
    pcoll --> strategy
    pcoll --> world
    pcoll --> geometry

    cli -. "imports at runtime<br/>(opponent registry)" .-> opponents
    cli -. "subprocess via env.run" .-> main
```

Key takeaways:

-   The submission's transitive closure is just `main.py → heuristic.strategy → {world, state, geometry, rotation, heuristic.config}`. That is the entire set of files bundled into `submission.tar.gz`.
-   `opponents/`, `rl/`, and `tools/` are **never imported by `main.py`**. They exist for local play, future RL work, and developer tooling respectively.
-   `state.py` is the single seam to `kaggle_environments` for tuple/struct types (`Planet`, `Fleet`, etc.). Everything downstream consumes the `ObservationView` adapter rather than raw `obs`.

---

### 2. Per-turn agent call flow

What actually runs when Kaggle calls `agent(obs)` once per turn (≤ 1 second wall clock). Sequence of function calls inside `heuristic.strategy._decide`.

```mermaid
sequenceDiagram
    autonumber
    participant Kaggle as Kaggle harness
    participant Main as src/main.py<br/>agent
    participant Strat as heuristic.strategy<br/>_decide
    participant World as world.WorldModel
    participant Threats as strategy.find_threats
    participant Def as strategy.plan_defense
    participant Offense as strategy._plan_offense_*
    participant Aim as world.aim_with_prediction
    participant Path as world.path_collision_predicted

    Kaggle->>Main: agent(obs, config=<env Struct>)
    Main->>Strat: agent(obs, cfg)
    Note over Strat: isinstance(config, HeuristicConfig)<br/>guard — env Struct ⇒ DEFAULT
    Strat->>Strat: ObservationView.from_raw(obs)
    Strat->>World: WorldModel.from_observation(view, horizon)
    World-->>Strat: base_timeline + ledger

    Strat->>Threats: find_threats(view, world, cfg)
    Threats-->>Strat: list[Threat]
    Strat->>Def: plan_defense(view, world, threats, cfg)
    Def->>Path: path_collision_predicted(...)
    Def-->>Strat: defensive moves + reserved ships

    Strat->>Offense: _plan_offense_greedy or _hungarian
    Offense->>Aim: aim_with_prediction(target, ETA)
    Offense->>Path: path_collision_predicted(src, dst, ships)
    Offense->>World: world.min_ships_to_own_by(target, ETA)
    Offense-->>Strat: offensive moves

    Strat-->>Main: list[[src_id, dst_id, ships], ...]
    Main-->>Kaggle: action list
```

Critical invariants (from `CLAUDE.md`):

-   `agent` is **stateless by contract**. Any module-level cache must be keyed by `obs.player` or reset per episode.
-   The `config=None` second positional arg trap: `kaggle_environments` passes its env Struct as `config`. The `isinstance(config, HeuristicConfig)` guard in `_decide` is what prevents the silent `[]`-every-turn failure mode.
-   Path-clearance must use the moving-planet predictor (`path_collision_predicted`), not a static-position check at launch time.

---

### 3. CLI surface (`uv run orbit-play …`)

`tools.cli` is a Typer app that wires together opponents, the diagnostic harness, and the submission packager. It is the only file that knows how to mix-and-match the rest of the repo.

```mermaid
graph LR
    classDef cmd fill:#1f6feb,stroke:#0d419d,color:#fff
    classDef tool fill:#6e7781,stroke:#424a53,color:#fff
    classDef src fill:#2ea043,stroke:#1a7f37,color:#fff
    classDef ext fill:#eaeef2,stroke:#6e7781,color:#1f2328

    user(("uv run<br/>orbit-play"))

    user --> play["play"]:::cmd
    user --> ladder["ladder"]:::cmd
    user --> replay["replay"]:::cmd
    user --> packcmd["pack"]:::cmd
    user --> train["train"]:::cmd
    user --> evalc["eval"]:::cmd

    play --> resolve_opp["_resolve_opponent<br/>(import opponent module)"]
    ladder --> resolve_opp
    resolve_opp --> opponents_pkg["orbit_wars.opponents.*"]:::src

    play --> kenv1["kaggle_environments.make<br/>('orbit_wars')"]:::ext
    ladder --> kenv1
    kenv1 --> mainfile["src/main.py<br/>(loaded as 'main')"]:::src

    packcmd --> pack["tools/pack.py<br/>pack_submission"]:::tool
    pack --> tar["submission.tar.gz<br/>(main.py + helpers)"]
    pack --> smoke["_smoke_test<br/>(unpack, run G4)"]

    train --> rl_train_cli["orbit_wars.rl.train"]:::src
    evalc --> rl_eval_cli["orbit_wars.rl.eval"]:::src
```

Notes:

-   `pack` runs a built-in G4 smoke test that unpacks the tarball into a temp dir and invokes the bundled `main.py` against `random` — catches missing helper modules before submission.
-   `play` and `ladder` invoke `main.py` via subprocess paths handled by `kaggle_environments.env.run`; the file is loaded as a module named `main`, which is also the name `tools/trace_launch.py` imports under.

---

### 4. Diagnostic tooling

When the agent loses or behaves oddly, **diagnose before fixing**. Three instrumentation tools attach to the agent at different layers.

```mermaid
graph TD
    classDef tool fill:#6e7781,stroke:#424a53,color:#fff
    classDef strat fill:#9a6700,stroke:#7d4e00,color:#fff
    classDef artefact fill:#1f6feb,stroke:#0d419d,color:#fff

    diag["tools/diagnostic.py<br/>diagnose_seed · summarize"]:::tool
    trace["tools/trace_launch.py<br/>trace_fleet · planets_on_ray"]:::tool
    pcoll["tools/path_collision_instrumentation.py<br/>_make_instrumented · _run_one_seed"]:::tool

    decide["strategy.decide_with_decisions<br/>(returns moves + LaunchDecision log)"]:::strat
    pcp["world.path_collision_predicted"]:::strat
    agent_fn["strategy.agent<br/>(v15g_agent)"]:::strat

    diag --> decide
    diag --> json1["docs/iteration_logs/<v>/diag.json<br/>+ markdown summary"]:::artefact

    trace --> decide
    trace --> agent_fn
    trace --> json2["per-launch trajectory walk<br/>(rich table to stdout)"]:::artefact

    pcoll --> agent_fn
    pcoll -. "monkeypatches" .-> pcp
    pcoll --> json3["FP-rate report<br/>(aborts vs counterfactual)"]:::artefact
```

What each tool answers:

-   **`diagnostic.py`** — *Why did this game's launches not capture?* Walks `env.steps` to label every launch (`captured`, `still-neutral-at-arrival`, `fleet-destroyed-in-transit`, etc).
-   **`trace_launch.py`** — *Where exactly did this one fleet die?* Picks specific launches by target type and walks the env step-by-step.
-   **`path_collision_instrumentation.py`** — *Is the path-collision predictor too aggressive?* Monkey-patches the predictor, logs every abort, and computes a false-positive rate against counterfactual replays. (Closed the loop on the v1.5G `0.3% FP` rate result.)

---

### 5. Test-to-source map

`tests/` mirrors the `orbit_wars` package one-to-one for the geometry/world math. `test_opponents.py` is the only integration test — it spins up `kaggle_environments` and runs full episodes.

```mermaid
graph LR
    classDef test fill:#bf3989,stroke:#7d2660,color:#fff
    classDef src fill:#2ea043,stroke:#1a7f37,color:#fff
    classDef ext fill:#eaeef2,stroke:#6e7781,color:#1f2328

    tg["test_geometry.py<br/>(hypothesis property tests)"]:::test --> geometry["orbit_wars.geometry"]:::src
    tr["test_rotation.py"]:::test --> rotation["orbit_wars.rotation"]:::src
    tr --> state["orbit_wars.state"]:::src
    tw["test_world.py<br/>(ArrivalEvent · WorldModel)"]:::test --> world["orbit_wars.world"]:::src
    tw --> state
    to["test_opponents.py<br/>(integration, runs episodes)"]:::test --> kenv["kaggle_environments.make"]:::ext
    to --> opponents["orbit_wars.opponents.*"]:::src
```

Run all: `uv run pytest -q` (37 tests, ~1s for unit tests, slower for opponent integration). Mark slow tests with `@pytest.mark.slow` and gate via `-m slow`.

---

## Quick reference: what ships vs. what doesn't

| Path | Shipped in `submission.tar.gz`? | Purpose |
| :-------: | :-------: | :-------: |
| `src/main.py` | yes (as `main.py` at tar root) |Kaggle entry point |
| `src/orbit_wars/{state,world,rotation,geometry}.py` |yes| Math + observation adapters |
| `src/orbit_wars/heuristic/{strategy,config}.py` | yes | Decision logic|
| `src/orbit_wars/opponents/*` | **no** | Local sparring partners only |

`src/orbit_wars/rl/*`

**no**

v2+ RL scaffold (stubs)

`src/tools/*`

**no**

Developer CLI / instrumentation

`tests/*`

**no**

Test suite

The submission tarball is built by `tools/pack.py:pack_submission`, which flattens the `orbit_wars` package next to `main.py` (Kaggle unpacks into a single working directory — no package layout).