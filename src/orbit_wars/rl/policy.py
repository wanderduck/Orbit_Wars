"""Actor-critic policy for the RL agent.

Stub for v1 — real network architecture lands in v2 when training begins.

Architecture (per E7 cell 14, synthesis §4 / 5):
- 3-encoder MLP (self_features + global_features + per-candidate features).
- Per-candidate target logit head; pooled value head.
- Param budget ≤ 1M for CPU inference at 1s/turn (per spec §10 risk #5).

The ``build_policy`` factory is the orchestrator's entry point for param-count
verification (Task 3.8 Step 2 of the plan).
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

__all__ = ["PolicyConfig", "PolicyOutput", "PlanetPolicy", "build_policy"]


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    self_dim: int = 16          # E7 §self_features dimension (incl. one-hots)
    candidate_dim: int = 18     # E7 §candidate_features dimension (incl. relative pos, masks)
    global_dim: int = 12        # E7 §global_features dimension
    candidate_count: int = 8    # K-nearest target candidates
    hidden_size: int = 128      # E7 default


@dataclass(slots=True)
class PolicyOutput:
    target_logits: torch.Tensor
    value: torch.Tensor


class PlanetPolicy(nn.Module):
    """Per-planet actor-critic policy. Adapted from E7's ``PlanetPolicy``.

    Each owned planet calls this network independently and gets a categorical
    distribution over (no-op, K-1 nearest target candidates).
    """

    def __init__(self, cfg: PolicyConfig | None = None) -> None:
        super().__init__()
        cfg = cfg or PolicyConfig()
        self.cfg = cfg

        def _mlp(in_dim: int, out_dim: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Linear(in_dim, out_dim), nn.ReLU(),
                nn.Linear(out_dim, out_dim), nn.ReLU(),
            )

        self.self_encoder = _mlp(cfg.self_dim, cfg.hidden_size)
        self.global_encoder = _mlp(cfg.global_dim, cfg.hidden_size)
        self.candidate_encoder = _mlp(cfg.candidate_dim, cfg.hidden_size)
        self.target_head = nn.Sequential(
            nn.Linear(cfg.hidden_size * 3, cfg.hidden_size), nn.ReLU(),
            nn.Linear(cfg.hidden_size, 1),
        )
        self.value_head = nn.Sequential(
            nn.Linear(cfg.hidden_size * 3, cfg.hidden_size), nn.ReLU(),
            nn.Linear(cfg.hidden_size, 1),
        )

    def forward(
        self,
        self_features: torch.Tensor,
        candidate_features: torch.Tensor,
        global_features: torch.Tensor,
        candidate_mask: torch.Tensor,
    ) -> PolicyOutput:
        self_h = self.self_encoder(self_features)
        global_h = self.global_encoder(global_features)
        candidate_h = self.candidate_encoder(candidate_features)
        K = self.cfg.candidate_count
        expanded_self = self_h.unsqueeze(1).expand(-1, K, -1)
        expanded_global = global_h.unsqueeze(1).expand(-1, K, -1)
        joint = torch.cat([expanded_self, expanded_global, candidate_h], dim=-1)
        target_logits = self.target_head(joint).squeeze(-1)
        target_logits = target_logits.masked_fill(~candidate_mask, torch.finfo(target_logits.dtype).min)
        pooled = candidate_h.mean(dim=1)
        value = self.value_head(torch.cat([self_h, global_h, pooled], dim=-1)).squeeze(-1)
        return PolicyOutput(target_logits=target_logits, value=value)


def build_policy(cfg: PolicyConfig | None = None) -> PlanetPolicy:
    """Factory used by the orchestrator (and the submission verifier) for the policy."""
    return PlanetPolicy(cfg)
