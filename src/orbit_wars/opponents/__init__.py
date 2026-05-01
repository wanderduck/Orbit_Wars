"""Local-only sparring partners.

Each module exposes a single ``agent(obs)`` function compatible with
``kaggle_environments.env.run``. They are intentionally weaker than our
production agent and intentionally diverse — competent_sniper attacks
correctly, aggressive_swarm tests volume, defensive_turtle tests breakthrough.
``peer_mdmahfuzsumon`` is a vendored snapshot of a real peer submission
(rank 498, score 796.8 at time of port) and exists specifically as the
non-regression discriminator for Phase 2 A/B gating — it is NOT necessarily
weaker than our production agent. None of them ship to Kaggle; they exist
so we can measure failure modes and gate technique experiments.
"""
