---
source_url: https://www.kaggle.com/code/rauffauzanrambe/orbit-wars-neural-space-combat
author: rauffauzanrambe
slug: orbit-wars-neural-space-combat
title_claim: Import Library & Setup
ladder_verified: not on leaderboard
pulled_on: 2026-05-01
pull_command: uv run kaggle kernels pull rauffauzanrambe/orbit-wars-neural-space-combat
---

# rauffauzanrambe/orbit-wars-neural-space-combat

## Architecture in one sentence
A textbook DQN training loop on a fabricated 2D HP-and-movement combat toy environment that is unrelated to the real Orbit Wars game — the "neural" framing IS implemented (PyTorch DQN, replay buffer, target network) but the environment it learns is invented from scratch and has no fleets, planets, comets, or kaggle_environments integration.

## Notable techniques
- Standard DQN scaffolding: 2x128 ReLU MLP, replay buffer (deque, capacity 5000), target network synced every 10 episodes, epsilon-greedy with 0.995 decay floored at 0.05, MSE loss, Adam @ lr 1e-3, gamma=0.99 (cells 9, 13).
- Synthetic dataset export to CSV after training, presumably for downstream supervised use (cells 11, 15).
- 6-D state vector (player_xy, enemy_xy, player_hp, enemy_hp) and 6 discrete actions (stay/up/down/left/right/attack) — completely fabricated, not derived from the Orbit Wars observation schema (cell 3).

## Visible evidence
The custom env in cell 3 makes the disconnect explicit:

```python
# cell 3
self.player = np.array([0.0, 0.0])
self.enemy = np.array([random.uniform(-10, 10), random.uniform(-10, 10)])
self.player_hp = 100
self.enemy_hp = 100
# Actions: 0=stay, 1=up, 2=down, 3=left, 4=right, 5=attack
```

No `import kaggle_environments`, no `make("orbit_wars")`, no `def agent(obs)`, no Planet/Fleet handling, no submission packaging. The DQN never sees the real game.

## Relevance to v1.5G
Effectively zero direct relevance. The notebook does not interact with the real Orbit Wars observation (obs.planets, obs.fleets, comet aliasing, rotation, fleet-size to speed log scaling) and never produces an agent(obs) callable. The DQN scaffolding (replay buffer, target net cadence, epsilon decay schedule) is generic and already covered in stronger detail in src/orbit_wars/rl/ stubs and any standard DQN tutorial — nothing here informs v1.5G's heuristic offense/defense, Hungarian-vs-greedy A/B, path-clearance, or late-game launch filter. Confirms that "neural" titles in this competition's notebook pool can be aspirational/portfolio framing rather than working RL on the actual env.

## What couldn't be determined
- Whether the author intended this as a portfolio piece or a stepping stone toward a real submission (no narrative cells beyond emoji headers).
- Training outcome quality — only `print(f"Episode ..., Reward: ...")` per 10 episodes, no plot, no eval, no convergence claim.
- Whether the exported CSV was ever consumed by another notebook.
