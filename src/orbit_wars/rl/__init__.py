"""RL training scaffold for Orbit Wars (PPO + self-play).

Per Path A (synthesis §5.A): full RL scaffold is built in v1 codebase but ships
in v2+ when a trained policy beats the heuristic in self-play eval (≥60% win rate
over 100 episodes per spec §8.7).

The current state of this package is **scaffold only** — file structure, dataclass
configs, and stub class signatures. Real training infrastructure (PPO updates,
self-play league, set-transformer encoder) lands when v2 work begins. The
scaffolding is here so:
- C2 part-2 has a concrete starting point (no greenfield decision)
- The submission packager's ``--include-rl`` path has files to bundle
- Anyone reading the codebase sees the v2 plan in code form

See E7 (kashiwaba RL tutorial) reusable patterns for the recommended starting
point: per-planet decision factoring, 3-encoder MLP, candidate-count gating.
"""

from .policy import PolicyConfig, PolicyOutput, build_policy

__all__ = ["PolicyConfig", "PolicyOutput", "build_policy"]
