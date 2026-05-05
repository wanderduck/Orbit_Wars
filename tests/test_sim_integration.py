"""End-to-end Day 3-5 gate: ≥80% match rate on filtered static-2P scenarios."""
from __future__ import annotations

import pytest


GATE_CATEGORIES = {
    "ownership-flip",
    "ship-count-off",
    "step-mismatch",
    "planet-count-mismatch",
    "comet-related",
}
# NOT in gate (Day 3-5 — fleet handling is stub):
#   "fleet-position-drift" — Phase 4 stub doesn't move fleets
#   "fleet-count-mismatch" — env consumes fleets via arrival/sweep, our sim doesn't
#   "fleet-id-set-mismatch" — same root cause
# Filter requires no-fleets-in-flight in state_t, but actions can spawn new ones
# this turn that we'd then carry mismatched.


@pytest.mark.slow
def test_day_3_5_gate_match_rate_at_least_80_percent():
    """Day 3-5 gate per kickoff brief Section 3.4 + master design doc Section 4."""
    from orbit_wars.sim.simulator import Simulator
    from orbit_wars.sim.validator import (
        ForwardModelValidator,
        filter_day_3_5_scenarios,
    )

    seeds = list(range(10))
    opponent_pool = ["random", "starter"]
    opponent_combos = [
        (opp_a, opp_b)
        for opp_a in opponent_pool
        for opp_b in opponent_pool
    ]

    v = ForwardModelValidator(simulator=Simulator())
    raw_triples = v.collect_scenarios(
        seeds=seeds,
        opponent_pool=opponent_pool,
        opponent_combos=opponent_combos,
    )
    filtered = filter_day_3_5_scenarios(raw_triples)
    print(f"\nFiltered {len(filtered)} triples from {len(raw_triples)} raw")
    # Empirical: the all-static-planet filter passes ~0.22% of triples
    # (most random games have at least one rotating planet). 40 triples
    # gives stderr ~6% — enough for a coarse pass/fail. Plan recommended
    # >=500 (10×3-opponent×~17 expected); reality requires expanded seeds.
    # See iteration log for decision on whether to expand if borderline.
    assert len(filtered) >= 30, (
        f"Day 3-5 filter too aggressive: only {len(filtered)} triples from "
        f"{len(raw_triples)} raw. Even coarse measurement infeasible — "
        f"expand seeds or loosen filter."
    )

    report = v.validate(filtered, gate_categories=GATE_CATEGORIES)
    print(f"\nDay 3-5 gate: n_total={report.n_total}  n_match={report.n_match}  "
          f"match_rate={report.match_rate:.3f}")
    print(f"Mismatch categories: {report.mismatch_categories}")

    assert report.match_rate >= 0.80, (
        f"Day 3-5 gate FAILED: match_rate={report.match_rate:.3f} < 0.80. "
        f"Top mismatch categories: {sorted(report.mismatch_categories.items(), key=lambda kv: -kv[1])[:5]}"
    )
