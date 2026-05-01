# R3: heur2.pdf

## Source
/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/docs/research_documents/heur2.pdf

## Document type
M.S. thesis (Cal Poly San Luis Obispo, 2018), 87 pages. Primarily a CNN/computer-vision thesis on training a custom object-detector ("SmashNet") for Super Smash Bros. Melee, with one short chapter (Ch. 6, ~5 pages) on a hard-coded reactive bot ("KirbyBot") driven by the detector. The bot chapter is the only part with material relevant to Orbit Wars. Despite being the largest PDF in the research folder by file size, the relevant content density is very low.

## Title and authors
"Object Tracking in Games using Convolutional Neural Networks" - Anirudh Venkatesh, June 2018. Committee: Alexander Dekhtyar (chair), John Seng, Franz Kurfess.

## Pages read
1-10 (front matter / TOC), 11-20 (Intro + Ch. 2 background up to optimization), 35-45 (Ch. 3 related work + Ch. 4 system pipeline + SmashNet architecture, skimmed for irrelevance), 65-80 (end of Ch. 5 results, **all of Ch. 6 KirbyBot**, Ch. 7 future work, Ch. 8 conclusion, bibliography). The CNN training chapters (2.1-2.3, 4.3-4.4, 5.1-5.2) and YOLO/object-detection background were skipped or skimmed because Orbit Wars gives us a structured `obs` namespace, not pixels — there is no detection problem to solve.

## Goal
Stated thesis goal (p. 2): "implement a real-time detection model to classify and track video game characters from the popular fighting game Super Smash Brothers Melee. With this, we constructed a simplistic bot, capable of movement based on tracked locations of a secondary character on screen." The bot was deliberately a *proof of concept*, not an attempt at a competitive agent.

For our purposes, the only useful goal is the bot chapter's: build a reactive heuristic agent that acts purely from the (x, y) positions of two units on a 2D playfield.

## Methods
- **CNN pipeline** (Ch. 4, p. 38-50): two-stage training — pretrain SmashNet on Caltech-101 (8,677 images, 101 classes), then fine-tune on 2,296 hand-annotated SSBM frames using YOLO-style detection. Not relevant to us.
- **KirbyBot reactive heuristic** (Ch. 6, p. 67-72): hard-coded rule-based controller with no game knowledge other than the bounding boxes of two characters. Two-thread architecture: thread 1 sends commands to the Dolphin emulator via libmelee; thread 2 captures frames and runs the detector remotely. Decision logic is the pseudocode on p. 70 (reproduced below).
- **Latency mitigation** (p. 67-68): client laptop's GPU could only run the detector at 2 fps, so frames are pushed over TCP to a Xeon + GTX 980 server. Capture is fragmented into 4096-byte packets with a 1-byte header (`'0'` start / `'1'` middle / `'2'` end) and a 4-byte length prefix. Round-trip cost: bot operates at 6-10 fps with the visualization window open, 12-14 fps without. Game itself stays at 60 fps because the controller thread is decoupled from the perception thread.
- **Evaluation methodology** (Ch. 6.4, p. 71-72): instrument the bot to count "close combat frames" (both bounding boxes within 15 px of each other) versus "detected frames" (both characters visible) versus total frames over ~1 minute on each of two stages. Used to characterize player habits and bot/opponent interaction rates.

## Numerical params / hyperparams
Numbers from the bot chapter only (CNN hyperparams ignored as irrelevant):

- **Reactive distance threshold: 15 pixels** (p. 70). Hard-coded gap on every comparison axis. Justification: "we decided to leave an extra 15 pixel distance so that when KirbyBot moves, it avoids running past Ness in a majority of cases."
- **Confidence threshold: 0.45**, **NMS threshold: 0.4** (p. 68; tuned in 5.2 p. 65). Increased above the validation-time 0.3 specifically to suppress false positives during live play, accepting a small recall loss (Ness AP 0.79, Kirby AP 0.74).
- **Operating frame rate: 6-10 fps with detection visualization, 12-14 fps without** (p. 67, p. 69, p. 73).
- **Game window: 639x507 px** (p. 67). 180-200 fps capture without display, 24-26 fps with display via the `mss` Python library.
- **Two test stages, ~1 minute each** (p. 71). Final Destination: 412 total frames, 163 with both characters detected, 44 close-combat. Yoshi's Story: 425 total, 256 detected, 36 close-combat.

## Reusable patterns for our heuristic
Most of this thesis does not translate. The five things that do:

1. **Decision-tree-of-position-deltas as a baseline pattern.** KirbyBot's entire algorithm (p. 70) is a pure if/elif on signed coordinate differences with a deadband. For our nearest-planet baseline we already do something similar; the explicit lesson is that *naming the deadband as a hyperparameter* (their "+15 pixels") is worth doing. In our codebase the analogue is "how many ships of slack do we want above `garrison + 1` before launching" and "how many turns of orbital lead do we want." Those should be named constants in `src/orbit_wars/heuristic/`, not magic numbers buried in the action selector.
2. **Decouple perception from action.** Their two-thread split (p. 69) keeps the game at 60 fps even while perception runs at 6-10 fps. For us, the analogue is: keep the per-turn `agent(obs)` work bounded, and push expensive predictions (predicting orbital positions N turns ahead, simulating fleet collisions) into a module-level cache that survives across turns. We already note this caching pattern in `/home/wanderduck/000_Duckspace/WanderduckDevelopment/Ducks/Kaggle/Orbit_Wars/CLAUDE.md`. The thesis is one more data point that "dumb-but-fast reaction" beats "smart-but-blocking" when there is a wall-clock budget.
3. **Tune detection/decision thresholds for live play, not for validation.** Section 5.2 (p. 65) raises confidence from 0.3 (validation-tuned) to 0.45 specifically because false positives hurt the live bot more than missed detections. Translate: when we set thresholds for "is this opponent fleet a threat," we should tune them in self-play, not on a static dataset, because the agent's response loop magnifies certain error modes. This is a concrete argument for a self-play harness over an offline scoring dataset.
4. **Instrument the bot to log per-frame interaction statistics.** The "close combat frames vs detected frames vs total frames" table (Table 6.1, p. 72) is the entire empirical contribution and it took ~2 minutes of footage. The cheap analogue for us: log each turn's `(my_ships, enemy_ships, owned_planets, comet_present, sun_distance_min)` and dump per-episode CSVs. With 500 turns x 4 players, even 10 episodes gives us enough signal to identify which heuristic rules fire and which never do.
5. **Explicitly accept being a "black-box" agent with no game model — but as a *negative* lesson.** The thesis (Ch. 8, p. 76) calls KirbyBot "a black-box implementation as it inherently knows nothing about the game and relies entirely on the tracked locations." This is a negative example for us: we have rich structured observation, deterministic planet rotation, and an open-source game engine. Choosing to be black-box would leave huge value on the table. The current `nearest-planet sniper` baseline in `src/main.py` is already partway down the black-box path (it ignores sun, comets, rotation). The thesis illustrates how thin a purely-reactive agent ends up — KirbyBot literally cannot recover, attack offensively, or move independently (p. 70). We should not stop there.

## Direct quotes / code snippets to preserve

KirbyBot pseudocode (p. 70, verbatim, lightly reformatted):

```
while SSBM is running do
    if both Ness and Kirby boxes exist then
        if Ness xmax + 15 pixels < Kirby xmin then
            Kirby moves left;
        else if Kirby xmax + 15 pixels < Ness xmin then
            Kirby moves right;
        else if Ness ymax + 15 pixels < Kirby ymin then
            Kirby jumps;
        else if Kirby ymax + 15 pixels < Ness ymin then
            Kirby comes down;
        else
            Kirby attacks;
    else
        Kirby doesn't move;
end
```

Honest self-assessment of the bot, p. 70: "KirbyBot has no concept of recovery, offensive or defensive maneuvers, or even independent movement. It relies purely on the location of the enemy Ness for instructions."

Latency / threading note, p. 69: "the bot was set up as a two-thread system where the first thread controls the character within the game, and the second runs the frame capture and tracks the characters. So while the frame display may run at approximately 6-10 fps, the game is not hindered by this process and will always run at the full 60 fps."

Threshold-tuning note, p. 65: "For the purposes of the bot, we increase the confidence and NMS thresholds to 0.45 which appears to make a visual difference of less false positive detections."

## Anything novel worth replicating
- **Per-stage interaction-rate logging** (Table 6.1, p. 72) is genuinely cheap and gives a sanity-check on whether the agent is doing what we *think* it is doing. It also doubles as a player-modeling primitive: if our agent logs "fraction of turns the opponent's largest fleet was within 15 squares of one of my planets" across episodes, it can cluster opponents into archetypes (rusher / turtler / sniper). The thesis treats this as a side-experiment but it is a clean recipe.
- The deadband-on-every-axis idiom (p. 70) is a small but worthwhile pattern: when comparing positions, never test for strict equality or zero-difference, always test against a named tolerance. Direct application: when checking "am I close enough to commit a fleet" or "is the sun close enough to abort," use a named tolerance, not raw distance comparison.

Nothing else in the thesis (CNN architecture, Caltech-101 pretraining, YOLO loss, IOU evaluation) generalizes to Orbit Wars.

## Open questions / things I couldn't determine
- The thesis never reports a win-rate of KirbyBot vs. the human player or vs. the built-in CPU. The "evaluation" of the bot is purely the interaction-rate experiment; there is no "did KirbyBot win?" metric. So we cannot tell from this document whether even a 5-rule reactive heuristic is *competitive* in SSBM, only that it follows and attacks. By analogy, the document gives no evidence about whether our nearest-planet baseline is sufficient or insufficient for the Kaggle leaderboard.
- The thesis does not address multi-opponent dynamics. It explicitly punted to 1v1 ("Having the maximum possible of 4 characters introduces multiple variables and options for the bot which we did not want to explore," p. 67). Orbit Wars is 4-player, and the most interesting heuristic questions (target prioritization, kingmaking, alliance-of-convenience against the leader) are exactly what was punted on.
- No discussion of stateful behavior: KirbyBot is purely Markov on the current frame. Compatible with our `agent(obs)` stateless contract but means the thesis offers nothing on memory / belief tracking / planning horizons.

## Relevance to Orbit Wars (1-5)
**2/5.** This is mostly a CNN thesis; the bot chapter is short, single-opponent, purely reactive, and contains no domain-transferable algorithms — only a few engineering patterns (deadband thresholds, decoupled perception/action threading, live-tuned thresholds, per-episode interaction logging) that we could have arrived at independently. The relevant content fits in roughly 6 pages out of 87. If R3 is reading other heuristic-agent papers, deprioritize this one against anything that covers multi-agent target selection, planning under wall-clock budgets, or RTS-style production/consumption tradeoffs.
