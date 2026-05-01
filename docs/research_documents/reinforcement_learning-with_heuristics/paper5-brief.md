# Paper 5 — Atari Tetris: Heuristic vs RL (Comparative Study)

**Source PDF:** `paper5.pdf` in this directory.

## Executive summary

A comparative empirical study showing a hand-coded heuristic agent crushes from-scratch DQN/C51/PPO at ALE/Tetris-v5 (heuristic ~138 avg score; RL agents fail to clear lines after 10M steps). It is **NOT a hybrid RL+heuristic method paper** — the two approaches are strictly head-to-head — but its diagnostic findings about why pure RL fails in sparse-reward, high-state-space games are directly relevant to Orbit Wars strategy.

## 1. Title, authors, venue/year
"Outsmarting algorithms: A comparative battle between Reinforcement Learning and heuristics in Atari Tetris." Julius A. Bairaktaris (U. Hamburg) and Arne Johannssen (Harz UAS). *Expert Systems With Applications* 277 (2025), Article 127251. Open access (CC BY-NC-ND).

## 2. Problem setting / domain
Single-agent ALE/Tetris-v5 inside the Arcade Learning Environment (Gymnasium API). State space ~1.68×10^66 cells, branching factor up to 162, sparse delayed rewards (only line clears score; Tetris awards 10 lines, single 1 line — eq. 11, p.8). The ALE variant is *harder* than guideline Tetris: no 7-bag RNG (LFSR pseudo-RNG, p.8), no piece preview, no hold, no hard drop, no wall kicks, no lock delay (Table 3, p.8).

## 3. Method
Three RL baselines plus one heuristic, all evaluated as standalone agents.

**RL:** DQN (Algorithm 1, p.4), Categorical DQN/C51 with 51 atoms over [V_min=-10, V_max=10] using cross-entropy KL loss (eqs. 4-6, Algorithm 2, p.4), and PPO with clipped surrogate (eq. 7, Algorithm 3, p.4). All use the CleanRL JAX/Flax CNN: 4×84×84 → Conv(32,8,4) → Conv(64,4,2) → Conv(64,3,1) → Dense(512) → action head (Fig. 5, p.11).

**Heuristic agent (Section 4.2, p.12):** re-implementation of "SuperStacker" (hexhowells, 2022) — extracts board features by cropping/thresholding/downsampling the grayscale frame to a 10×22 binary grid (no CNN), enumerates all placements per Tetrimino, and scores with `score = lines_cleared² − (holes×4) − wells − added_height` (eq. 12, p.14). Picks the top-scoring placement, then emits the keypress sequence to achieve it.

## 4. Key results
**Heuristic agent over 2000 episodes:** mean 137.50, std 40.30, median 157, 99th pctile 190 (Table 8, p.14). Generated in ~8h 21m on a single i7-6700K (~15.1 s/episode, p.15).

**RL agents trained for 10M steps each on Xeon E5-2630 v3 (no GPU):** DQN/C51/PPO **never developed line-clearing strategies** — episodic returns hovered near 0 across the full training run (Fig. 11, p.16); PPO took 17.45h, C51 39.24h, DQN 37.70h. C51 cleared 2 lines once at step 5,465,768 (p.16), described as "more likely by chance than by strategy."

On the Atari-57 *general* benchmark (Table 2, p.5) C51 reaches 701% mean human score — the failure here is Tetris-specific.

## 5. Heuristic-RL integration
**None.** The agents do not interact. The paper explicitly contrasts them as alternatives. Section 6.3 "Future outlook" (p.22) gestures at hybrid possibilities — *"dynamic or adaptive heuristic approaches that could combine the computational efficiency of traditional heuristics with some of the adaptability of RL methods… dynamically adjusting the weights of different heuristic components based on the current game state"* — and mentions curriculum learning (Narvekar et al. 2020) as a way to address sparse rewards, but no implementation is given.

## 6. Strengths / limitations (per authors)
**Strengths claimed:** rigorous comparison on identical environment; demonstrates heuristics' computational and score advantages on sparse-reward problems; identifies CAP (Credit Assignment Problem), high state space, image-based observation parsing as the RL bottlenecks (Section 3.3.1, p.9). **Limitations** (Section 6.2, p.21): only 10M training steps (acknowledged as possibly insufficient — guidelines used 50M frames historically); no hyperparameter tuning; ALE/Tetris-v5 differs from guideline Tetris (limits external comparability); single CNN architecture; heuristic is static and "unable to adapt to or discover novel strategies."

## 7. Applicability to Orbit Wars
**Low-to-moderate, indirect.** Orbit Wars shares the painful properties highlighted here — sparse terminal-only rewards (win/loss), 1s per-turn budget, large state space, partially observable opponents — and v1.5G is already a hand-coded heuristic that exploits domain structure. The paper's findings *reinforce* current strategy: pure-RL-from-scratch in 7 weeks is a bad bet, and well-engineered heuristics dominate when reward shaping is hard.

**There is no transferable hybrid technique to prototype** — the paper offers no policy prior, action mask, reward shaper, or self-play scheme. The single 1-2 week prototype-able idea is **adaptive heuristic weights** (Section 6.3, p.22): tune feature-weight constants based on game phase or board state. This is heuristic tuning (e.g., CMA-ES or genetic-algorithm sweep over `HeuristicConfig`), not RL — but it directly addresses v1.5G's documented static-rules limitation.

## 8. What couldn't be determined
Whether RL can succeed at ALE/Tetris-v5 with longer training, hyperparameter search, or richer state representations (authors note this as future work, p.21). Whether feature-extraction layers (rather than raw pixels) would let RL match the heuristic. Whether SuperStacker's NES score (4.24M) would be reachable in ALE if the missing mechanics were added. The paper has no information on multi-agent RTS, search trees, opponent modeling, or self-play — none of which it covers.
