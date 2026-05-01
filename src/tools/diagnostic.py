"""Per-launch instrumented runner for our heuristic agent.

Plays our agent against ``random`` for one or more seeds, and for every launch
decision the agent makes, records:
- launch metadata (src, target, ships, eta)
- target state at launch
- target state at arrival (eta turns later)
- inferred outcome (captured / missed / enemy-owned / etc.)

Used by Phase 2 of the v1.1 heuristic iteration plan to identify the dominant
failure mode empirically before applying any strategy fixes.

Usage::

    uv run python -m tools.diagnostic run --seeds 0,1,2,3,4 \\
        --out docs/iteration_logs/v1.1/diagnostic_seeds_0-4.json
"""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import typer
from kaggle_environments import make
from rich.console import Console

from orbit_wars.heuristic.config import HeuristicConfig
from orbit_wars.heuristic.strategy import LaunchDecision, decide_with_decisions

app = typer.Typer(help="Diagnostic harness for heuristic v1.1 iteration.")
console = Console()


@dataclass
class LaunchOutcome:
    """A single launch decision plus its resolved outcome at arrival."""

    seed: int
    step: int
    src_id: int
    target_id: int
    angle: float
    ships: int
    eta: int
    src_ships_pre_launch: int
    target_ships_at_launch: int
    target_owner_at_launch: int
    target_x: float
    target_y: float
    target_radius: float
    target_is_static: bool
    target_is_comet: bool
    arrival_step: int
    target_owner_at_arrival: int  # -1 = neutral, 0 = us, 1+ = enemy; -2 if no longer in obs
    target_ships_at_arrival: int  # -1 if no longer in obs
    captured: bool
    failure_reason: str | None  # None if captured; one of the reasons below otherwise

    @classmethod
    def from_decision(cls, seed: int, step: int, decision: LaunchDecision) -> LaunchOutcome:
        return cls(
            seed=seed,
            step=step,
            src_id=decision.src_id,
            target_id=decision.target_id,
            angle=decision.angle,
            ships=decision.ships,
            eta=decision.eta,
            src_ships_pre_launch=decision.src_ships_pre_launch,
            target_ships_at_launch=decision.target_ships_at_launch,
            target_owner_at_launch=decision.target_owner,
            target_x=decision.target_x,
            target_y=decision.target_y,
            target_radius=decision.target_radius,
            target_is_static=decision.target_is_static,
            target_is_comet=decision.target_is_comet,
            arrival_step=step + decision.eta,
            target_owner_at_arrival=-2,
            target_ships_at_arrival=-1,
            captured=False,
            failure_reason=None,
        )


def diagnose_seed(seed: int, cfg: HeuristicConfig) -> tuple[list[LaunchOutcome], int, int]:
    """Run agent vs random for one seed; return all launch outcomes plus final scores.

    Uses ``main.agent`` (the production agent) for env.run so the diagnostic captures
    actual production behavior — kaggle_environments has different harness treatment
    for module-level functions vs closures, which produces different game outcomes
    despite both producing identical moves on the same obs. The post-hoc loop uses
    ``decide_with_decisions`` directly for decision capture, which is fine because
    both code paths are functionally equivalent on the same observation.
    """
    import importlib
    import sys
    sys.path.insert(0, "src")
    main_module = importlib.import_module("main")

    env = make("orbit_wars", debug=False, configuration={"seed": seed})
    env.run([main_module.agent, "random"])

    # Now post-hoc walk env.steps and re-run decide on each step's obs to recover decisions
    outcomes: list[LaunchOutcome] = []
    for step_idx in range(1, len(env.steps)):
        obs = env.steps[step_idx][0].observation
        if not getattr(obs, "planets", None):
            continue
        _moves, decisions = decide_with_decisions(obs, cfg)
        for d in decisions:
            outcomes.append(LaunchOutcome.from_decision(seed, step_idx, d))

    # Resolve each outcome by inspecting state at arrival_step
    for o in outcomes:
        # Try arrival_step and a 2-turn slack window
        resolved = False
        for offset in (0, 1, 2):
            check_step = o.arrival_step + offset
            if check_step >= len(env.steps):
                continue
            obs = env.steps[check_step][0].observation
            target = next((p for p in obs.planets if p[0] == o.target_id), None)
            if target is None:
                # Comet may have left the board
                continue
            owner, ships = target[1], target[5]
            o.target_owner_at_arrival = owner
            o.target_ships_at_arrival = ships
            if owner == 0:
                # Captured at this point
                o.captured = True
                o.failure_reason = None
                resolved = True
                break
            if offset == 2:
                # Final check; target is not ours within slack window
                resolved = True
                break

        if not resolved:
            # arrival_step was past episode end
            o.failure_reason = "arrival-after-episode-end"
            continue

        if not o.captured:
            # Classify why
            if o.target_owner_at_arrival == -2:
                o.failure_reason = "target-vanished"  # comet expired
            elif o.target_owner_at_arrival == -1:
                # Still neutral — fleet didn't reach (sun, OOB, miss)
                o.failure_reason = "still-neutral-at-arrival"
            elif o.target_owner_at_arrival == o.target_owner_at_launch and o.target_owner_at_launch >= 1:
                # Same enemy still owns it — we under-sent OR fleet was destroyed
                if o.target_ships_at_arrival > o.ships:
                    o.failure_reason = "enemy-defended"
                else:
                    o.failure_reason = "fleet-destroyed-in-transit"
            elif o.target_owner_at_arrival != 0:
                # A different player captured before us
                o.failure_reason = "lost-race-to-different-player"
            else:
                o.failure_reason = "unknown"

    final = env.steps[-1]
    return outcomes, final[0].reward, final[1].reward


def summarize(outcomes: list[LaunchOutcome]) -> dict[str, object]:
    """Aggregate launch outcomes by static/orbiting/comet × failure reason."""
    total = len(outcomes)
    captures = sum(1 for o in outcomes if o.captured)
    misses = total - captures

    by_target_type: dict[str, dict[str, int]] = {
        "static": {"total": 0, "captures": 0, "misses": 0},
        "orbiting": {"total": 0, "captures": 0, "misses": 0},
        "comet": {"total": 0, "captures": 0, "misses": 0},
    }
    for o in outcomes:
        if o.target_is_comet:
            kind = "comet"
        elif o.target_is_static:
            kind = "static"
        else:
            kind = "orbiting"
        by_target_type[kind]["total"] += 1
        if o.captured:
            by_target_type[kind]["captures"] += 1
        else:
            by_target_type[kind]["misses"] += 1

    failure_reasons = Counter(o.failure_reason for o in outcomes if not o.captured)

    # Failures by target type
    failures_by_type_reason: dict[str, dict[str, int]] = {}
    for o in outcomes:
        if o.captured:
            continue
        if o.target_is_comet:
            kind = "comet"
        elif o.target_is_static:
            kind = "static"
        else:
            kind = "orbiting"
        failures_by_type_reason.setdefault(kind, {})
        failures_by_type_reason[kind][o.failure_reason or "unknown"] = (
            failures_by_type_reason[kind].get(o.failure_reason or "unknown", 0) + 1
        )

    return {
        "total_launches": total,
        "captures": captures,
        "misses": misses,
        "capture_rate": (captures / total) if total else 0.0,
        "by_target_type": by_target_type,
        "failure_reasons": dict(failure_reasons),
        "failures_by_type_reason": failures_by_type_reason,
    }


@app.command()
def run(
    seeds: str = typer.Option("0,1,2,3,4", "--seeds", help="Comma-separated env seeds."),
    out: str = typer.Option(
        "docs/iteration_logs/v1.1/diagnostic_seeds_0-4.json",
        "--out",
        help="Output JSON path for raw outcomes.",
    ),
    summary_out: str = typer.Option(
        "docs/iteration_logs/v1.1/diagnostic_summary.md",
        "--summary-out",
        help="Output Markdown path for aggregated summary.",
    ),
    py_seed: int = typer.Option(42, "--py-seed", help="Global random.seed for opponent determinism."),
) -> None:
    """Run the diagnostic and write per-launch JSON + summary Markdown."""
    seed_list = [int(s.strip()) for s in seeds.split(",")]
    random.seed(py_seed)

    out_path = Path(out)
    summary_path = Path(summary_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cfg = HeuristicConfig.default()
    all_outcomes: list[LaunchOutcome] = []
    win_results: list[tuple[int, float, float]] = []

    for s in seed_list:
        outcomes, r0, r1 = diagnose_seed(s, cfg)
        all_outcomes.extend(outcomes)
        win_results.append((s, r0, r1))
        console.print(
            f"  seed {s}: launches={len(outcomes)} "
            f"captures={sum(1 for o in outcomes if o.captured)} "
            f"reward=({r0}, {r1})"
        )

    # Persist raw JSON
    out_path.write_text(json.dumps([asdict(o) for o in all_outcomes], indent=2, default=str))
    console.print(f"[green]Wrote raw outcomes:[/green] {out_path} ({len(all_outcomes)} records)")

    # Aggregate and write summary
    summary = summarize(all_outcomes)
    md_lines = ["# Diagnostic summary — heuristic v1.1 Phase 2", ""]
    md_lines.append(f"**Seeds:** {seed_list}")
    md_lines.append(f"**Global random.seed:** {py_seed}")
    md_lines.append("")
    md_lines.append("## Win/loss")
    wins = sum(1 for _, r0, r1 in win_results if r0 > r1)
    losses = sum(1 for _, r0, r1 in win_results if r0 < r1)
    md_lines.append(f"Heuristic vs random: **{wins}W-{losses}L** over {len(seed_list)} seeds")
    for s, r0, r1 in win_results:
        md_lines.append(f"- seed {s}: heuristic={r0}, random={r1}")
    md_lines.append("")
    md_lines.append("## Launch outcomes")
    md_lines.append(f"- Total launches: **{summary['total_launches']}**")
    md_lines.append(f"- Captures: **{summary['captures']}**")
    md_lines.append(f"- Misses: **{summary['misses']}**")
    md_lines.append(f"- Overall capture rate: **{summary['capture_rate']:.1%}**")
    md_lines.append("")
    md_lines.append("## By target type")
    md_lines.append("| Type | Total | Captures | Misses | Capture rate |")
    md_lines.append("|------|------:|---------:|-------:|-------------:|")
    for kind, stats in summary["by_target_type"].items():
        n = stats["total"]
        c = stats["captures"]
        m = stats["misses"]
        rate = (c / n) if n else 0.0
        md_lines.append(f"| {kind} | {n} | {c} | {m} | {rate:.1%} |")
    md_lines.append("")
    md_lines.append("## Failure reasons (across all misses)")
    for reason, count in sorted(summary["failure_reasons"].items(), key=lambda kv: -kv[1]):
        md_lines.append(f"- `{reason}`: **{count}**")
    md_lines.append("")
    md_lines.append("## Failures by target type x reason")
    for kind, reasons in summary["failures_by_type_reason"].items():
        md_lines.append(f"### {kind}")
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            md_lines.append(f"- `{reason}`: {count}")
        md_lines.append("")

    summary_path.write_text("\n".join(md_lines))
    console.print(f"[green]Wrote summary:[/green] {summary_path}")


if __name__ == "__main__":
    app()
