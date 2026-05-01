# Competition Codebases Research — Design Spec

**Date:** 2026-05-01
**Phase:** 1 (research + synthesis only)
**Status:** Awaiting user review before execution

## Goal

Extract small directional hints from 6 publicly-shared Orbit Wars notebooks that could improve our bespoke v1.5G platform. The intent is **not** to copy any architecture — we're looking for techniques, edge-case handling, opponent-modelling tricks, or sparring-partner candidates that we can selectively absorb into our own design.

Phase 2 (deciding what to actually try, parallel codebases, A/B plans) is explicitly out of scope here. It will get its own brainstorm gated on the synthesis content — we don't pre-commit to direction before we've read what's in the notebooks.

## Inputs

Six unique Kaggle notebook URLs from the "More Codebases" section of `docs/competition_documentation/Orbit_Wars-important_links.md`. Link 7 in that section is dropped because it is identical to the kashiwaba RL tutorial already present in the upper "Code for Idea Generation and Iteration" section.

| # | Author | Slug |
|---|---|---|
| 1 | beraterolelk | omega-v5-orbit-wars-supreme-domination-engine |
| 2 | johnjanson | lb-max-score-1000-agi-is-here |
| 3 | rahulchauhan016 | orbit-wars-target-score-2000-4 |
| 4 | rauffauzanrambe | orbit-wars-neural-space-combat |
| 5 | mdmahfuzsumon | how-my-ai-wins-space-wars |
| 6 | fedorbaart | utility-tactical-visualizer-for-orbit-wars |

Pull verified working: `uv run kaggle kernels pull beraterolelk/omega-v5-orbit-wars-supreme-domination-engine` succeeded against a public notebook in a smoke test.

## Deliverables

1. **Six per-codebase briefs** at `docs/research_documents/competition_codebases/<author>-<slug>.md` (one per notebook above).
2. **One synthesis doc** at `docs/research_documents/competition_codebases/synthesis.md`.
3. **One git commit** containing all 7 markdown files. Commit message scoped as research-only (no code changes to `src/`).
4. **(Optional, opt-in only)** A "Red-team review" section appended to `synthesis.md` in a separate follow-up commit, IF the user opts into the B-pass after reading the synthesis.

The pulled `.ipynb` files themselves land in `/tmp/orbit_wars_kaggle_pulls/` and are **not committed** — they are third-party IP, and each brief already cites cell numbers for traceability. The pull command is recorded in each brief's frontmatter for reproducibility.

## Per-codebase brief template

Path: `docs/research_documents/competition_codebases/<author>-<slug>.md`
Length: ≤400 words
Code excerpts: ≤15 lines each, must cite cell number

### Frontmatter

```yaml
---
source_url: <full Kaggle URL>
author: <kaggle handle>
slug: <kernel slug>
title_claim: <e.g. "LB MAX 1224">
ladder_verified: <if author username appears anywhere in /tmp/orbit_wars_lb/*.csv, record "rank N, score X.X"; else "not on leaderboard">
pulled_on: 2026-05-01
pull_command: uv run kaggle kernels pull <author>/<slug>
---
```

### Sections

1. **Architecture in one sentence** — heuristic / search / RL / hybrid; key data structures.
2. **Notable techniques** — bulleted, ≤8 items. Each: cell number + 5-15 line code excerpt + one-sentence "what it does" + one-sentence "why we'd care."
3. **Visible evidence** — anything *in the notebook itself* that demonstrates the technique works (in-notebook self-play results, opponent comparison tables, score history, comments like "this fixed X"). Distinguished explicitly from the author's title/marketing claims.
4. **Relevance to v1.5G** — direct comparison with our agent: techniques we already do, techniques that contradict our approach, techniques that would slot in cleanly, techniques requiring significant rework. Agent reads `CLAUDE.md` to ground this section.
5. **What couldn't be determined** — missing context, unclear cells, hidden dependencies (e.g., references to a saved model file not in the notebook).
6. **Sparring-partner flag** *(optional, omit unless obvious win)* — one short paragraph IF the agent looks cleanly extractable as a self-contained `agent(obs)` function AND meaningfully stronger or different from our current local opponents (`competent_sniper`, `aggressive_swarm`, `defensive_turtle`). If the candidate doesn't jump out, this section is omitted entirely.

## Synthesis doc structure

Path: `docs/research_documents/competition_codebases/synthesis.md`

1. **TL;DR** — ≤5 bullets, top hints with cross-references to source briefs.
2. **Cross-codebase patterns** — techniques appearing in 2+ notebooks (stronger signal than one-offs). Each: short description, which briefs reference it, evidence of effectiveness.
3. **Per-technique deep dives** — actionable hints, ranked by `(evidence × fit-with-v1.5G × low-cost-to-try)`. Each: idea, source(s), why it might help us, fit notes against v1.5G architecture (per CLAUDE.md), rough cost estimate ("a few hours" / "multi-day rewrite"), regression risk.
4. **Things explicitly NOT worth pursuing** — and why. (Discipline against shiny-but-bad ideas.)
5. **Sparring-partner notes** — informal recap of any flagged candidates from individual briefs.
6. **Open questions / follow-ups** — things needing more research or an experiment to resolve.
7. **Overall summary + thoughts** — qualitative read on what the public Kaggle scene looks like, where median/strong public submissions sit relative to v1.5G, anything surprising, and which directions feel most promising for our bespoke platform's continued development. This is the "here's what I actually think after reading all 6" section.

## Execution plan

1. Download the full public leaderboard once: `mkdir -p /tmp/orbit_wars_lb && uv run kaggle competitions leaderboard orbit-wars --download -p /tmp/orbit_wars_lb && cd /tmp/orbit_wars_lb && unzip -o orbit-wars.zip`. Produces a single CSV (columns: `Rank,TeamId,TeamName,LastSubmissionDate,Score,SubmissionCount,TeamMemberUserNames`) covering the entire leaderboard. Cached for the duration of this task.
2. `mkdir -p /tmp/orbit_wars_kaggle_pulls && mkdir -p docs/research_documents/competition_codebases`.
3. Pull 6 `.ipynb` files sequentially with ~2s spacing (~15-30s wall-clock). Verify each is non-empty / not a redirect HTML.
4. Drop any failed-pull links from the dispatch list; note them for the synthesis "Open questions" section.
5. Dispatch 6 parallel agents in **one message** for concurrent execution.
   - Subagent type: `python3-development:codebase-analyzer` (purpose-built for "read code, write structured analysis directly to disk"). Falls back to `general-purpose` if it has trouble.
   - Each agent receives: absolute path to its `.ipynb`, source URL, author, slug, the brief template inline, the leaderboard CSV path, and the path to `CLAUDE.md` for the relevance section.
   - Hard limits enforced in prompt: brief ≤400 words; code excerpts ≤15 lines with cell number; no marketing-claim regurgitation; if no working `agent(` function exists, say so and describe what *is* there.
   - Tools allowed: Read, Write, Bash (for `jupyter nbconvert` if useful), Grep, Glob.
6. Wait for all 6 agents. Verify each brief file was written; one retry on any missing.
7. Lead reads all 6 briefs and writes `synthesis.md`.
8. Lead self-reviews synthesis (placeholder/contradiction/sourcing-gap scan).
9. Single commit: all 6 briefs + synthesis. Message scoped as research-only.
10. Report path to user. Offer optional B-pass red-team.

Wall-clock estimate: 5-10 minutes total, dominated by the parallel agent step.

## Failure handling

- **Pull failures (before any agent fires):** sequential pulls upfront. One retry on failure. If still failing, drop that link and note `couldn't fetch <slug>: <reason>` in the synthesis Open questions section. Doesn't block the rest.
- **Notebook has no code:** agent still writes a brief saying "no working agent found, only commentary" and describes what is actually in the notebook (e.g., visualizer-only, training scaffolding, broken stub). Brief is still committed.
- **Agent returns without writing the file:** treat as extraction failure, single retry with same prompt; if still failed, note in synthesis and move on.
- **Kaggle CLI rate-limiting:** ≤1 pull every 2s; one CSV leaderboard call total, cached.

## Optional B-pass red-team (opt-in, post-synthesis)

After the synthesis lands and the user has read it, the lead explicitly asks: "want a red-team pass or are you good?" If yes:

- Dispatch one fresh-context Python+ML expert agent (`pensive:code-reviewer` or `axiom-python-engineering:python-code-reviewer`, picked based on the specific gaps the user flags).
- Inputs: `synthesis.md`, all 6 briefs, `CLAUDE.md`.
- Mission: red-team only — where is the analysis weakest, what is over-weighted, what's been missed entirely, what should be re-ranked.
- Output: short critique **appended** to `synthesis.md` as a "Red-team review" section. Not a rewrite.
- Separate follow-up commit.

## Constraints

- No edits to `src/` or any other code in Phase 1.
- Briefs ≤400 words each.
- Code excerpts ≤15 lines, must cite cell number.
- No marketing-claim regurgitation. `ladder_verified` field uses the cached LB CSV — agent greps `TeamMemberUserNames` column for the author handle; if present, records `rank N, score X.X`; if absent, records `not on leaderboard`.
- Pulled `.ipynb` files NOT committed.
- Lead does the synthesis pass directly (per Q4 answer A); B-pass is opt-in only.

## Out of scope

- Any modification of `src/main.py` or `src/orbit_wars/`.
- Implementing any technique found in research (deferred to Phase 2 brainstorm).
- Local A/B testing of any extracted ideas (deferred; CLAUDE.md flags local opponent pool as non-discriminating).
- Kaggle ladder submissions.
- Cloning or forking entire architectures from any notebook.
- Phase 2 planning of any kind.

## Done state

Synthesis committed at `docs/research_documents/competition_codebases/synthesis.md` with all 6 briefs alongside it. User has read the synthesis and decided either to (a) opt into the B-pass red-team, (b) proceed to a Phase 2 brainstorm, or (c) shelve the findings as-is.
