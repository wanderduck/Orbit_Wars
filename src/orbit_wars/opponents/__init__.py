"""Local-only sparring partners.

Each module exposes a single ``agent(obs)`` function compatible with
``kaggle_environments.env.run``. They are intentionally weaker than our
production agent and intentionally diverse — competent_sniper attacks
correctly, aggressive_swarm tests volume, defensive_turtle tests breakthrough.
None of them ship to Kaggle; they exist so we can measure failure modes.
"""
