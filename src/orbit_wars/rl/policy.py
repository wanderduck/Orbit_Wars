"""Actor-critic policy for the RL agent.
Architecture optimized for PPO training speed and sample efficiency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import nn

__all__ = ["PolicyConfig", "PolicyOutput", "PlanetPolicy", "build_policy"]

@dataclass(frozen=True, slots=True)
class PolicyConfig:
    self_dim: int = 16          # E7  self_features dimension (incl. one-hots)
    candidate_dim: int = 18     # E7  candidate_features dimension (incl. relative pos, masks)
    global_dim: int = 12        # E7  global_features dimension
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
                nn.Linear(in_dim, out_dim), nn.LayerNorm(out_dim), nn.ReLU(),
                nn.Linear(out_dim, out_dim), nn.LayerNorm(out_dim), nn.ReLU(),
            )

        self.self_encoder = _mlp(cfg.self_dim, cfg.hidden_size)
        self.global_encoder = _mlp(cfg.global_dim, cfg.hidden_size)
        self.candidate_encoder = _mlp(cfg.candidate_dim, cfg.hidden_size)

        # PERFORMANCE: Additive Late-Fusion vs Concatenation
        # Eliminates O(B * K * 3H^2) memory scaling by projecting BEFORE broadcasting
        self.target_proj_self = nn.Linear(cfg.hidden_size, cfg.hidden_size)
        self.target_proj_global = nn.Linear(cfg.hidden_size, cfg.hidden_size, bias=False)
        self.target_proj_candidate = nn.Linear(cfg.hidden_size, cfg.hidden_size, bias=False)

        self.target_out = nn.Sequential(
            nn.ReLU(),
            nn.Linear(cfg.hidden_size, 1),
        )

        self.value_head = nn.Sequential(
            nn.Linear(cfg.hidden_size * 3, cfg.hidden_size), nn.LayerNorm(cfg.hidden_size), nn.ReLU(),
            nn.Linear(cfg.hidden_size, 1),
        )

        self._apply_orthogonal_init()

    def _apply_orthogonal_init(self) -> None:
        """PPO models require orthogonal initialization for convergence and high initial entropy."""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=math.sqrt(2))
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0.0)

        # Policy logits should be near 0 initially to maximize exploratory entropy (gain=0.01)
        nn.init.orthogonal_(self.target_out[-1].weight, gain=0.01)
        # Value head mirrors the initial standardized return expectations (gain=1.0)
        nn.init.orthogonal_(self.value_head[-1].weight, gain=1.0)

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

        # 1. Target Logit Head (Optimized Additive Fusion)
        t_self = self.target_proj_self(self_h).unsqueeze(1)
        t_global = self.target_proj_global(global_h).unsqueeze(1)
        t_cand = self.target_proj_candidate(candidate_h)

        joint_h = t_self + t_global + t_cand
        target_logits = self.target_out(joint_h).squeeze(-1)

        # PPO stability fix: use -1e8 instead of finfo(min) to prevent NaN softmax gradients
        target_logits = target_logits.masked_fill(~candidate_mask, -1e8)

        # 2. PPO BUG FIX: Masked Mean Pooling
        # Replaces `pooled = candidate_h.mean(dim=1)` which poisoned the critic baseline
        # by averaging valid targets with zero-padded "dummy" targets.
        valid_mask = candidate_mask.unsqueeze(-1).float()
        pooled = (candidate_h * valid_mask).sum(dim=1) / valid_mask.sum(dim=1).clamp(min=1.0)

        # 3. Value Head
        value = self.value_head(torch.cat([self_h, global_h, pooled], dim=-1)).squeeze(-1)

        return PolicyOutput(target_logits=target_logits, value=value)

def build_policy(cfg: PolicyConfig | None = None) -> nn.Module:
    """Factory used by the orchestrator (and the submission verifier) for the policy."""
    policy = PlanetPolicy(cfg)

    # PyTorch 2 compilation for massive batch rollout acceleration
    if hasattr(torch, "compile"):
        return torch.compile(policy)
    return policy