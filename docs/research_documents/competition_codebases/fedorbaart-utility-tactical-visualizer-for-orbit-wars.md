---
source_url: https://www.kaggle.com/code/fedorbaart/utility-tactical-visualizer-for-orbit-wars
author: fedorbaart
slug: utility-tactical-visualizer-for-orbit-wars
title_claim: "Orbit Wars: Visualizing Your Agent"
ladder_verified: rank 318, score 850.9
pulled_on: 2026-05-01
pull_command: uv run kaggle kernels pull fedorbaart/utility-tactical-visualizer-for-orbit-wars
---

# fedorbaart/utility-tactical-visualizer-for-orbit-wars

## Architecture in one sentence
This is **not an agent** — it's a 7-cell demo notebook that pip-installs `kaggle-environments`, runs a `random` vs `random` episode, and calls a `render()` function imported from an external Kaggle dataset (`fedorbaart/orbit-wars-visualizer`) that the author distributes separately.

## Notable techniques
The notebook itself contains **no visualization code** — the entire rendering implementation lives in the un-attached dataset under `orbit_wars.core.viz.embed.render`. The author markets the dataset as offering "improved aesthetics, APM sparklines, and combat impact effects" (cell 1), and the API supports two input modes: a live `env` object (cell 4) and a recorded replay loaded from JSON (cell 6). The dataset path is hard-coded to `/kaggle/input/datasets/fedorbaart/orbit-wars-visualizer` (cell 2), implying it must be attached at notebook-runtime.

## Visible evidence
There are no rendered outputs in the .ipynb JSON — all cells show empty execution results. The marketing claims (APM sparklines, combat impact effects) cannot be inspected without pulling the separate dataset. From cell 2:

```python
# cell 2
viz_path = Path('/kaggle/input/datasets/fedorbaart/orbit-wars-visualizer')
if viz_path.exists():
    sys.path.append(str(viz_path))
else:
    print("Dataset not found! Make sure fedorbaart/orbit-wars-visualizer is attached.")
from orbit_wars.core.viz.embed import render
```

The `render()` function accepts both an `env` object and a deserialized replay dict (cells 4, 6) — a dual-input pattern.

## Relevance to v1.5G
**Low to none from this notebook alone.** The actual rendering library is in a separate dataset that would have to be pulled and inspected independently — this notebook is just a thin loader/demo. The dual-input `render(env_or_replay)` API pattern is mildly interesting (could match how `tools/diagnostic.py` walks `env.steps` post-hoc), but the design is obvious and we already do post-hoc replay analysis. Note: the author's ladder score of 850.9 (rank 318) is from a separate submission entirely — this notebook is unrelated tooling and gives **no insight into how that 850.9-scoring agent works**. APM (actions-per-minute) sparklines, if they truly exist in the dataset, could conceivably surface tempo asymmetries we don't currently track in `tools/diagnostic.py`, but that's speculative without seeing the code.

## What couldn't be determined
- The actual rendering implementation (lives in unfetched `fedorbaart/orbit-wars-visualizer` dataset).
- What "APM sparklines" and "combat impact effects" actually compute or look like.
- Whether the renderer extracts any tactical metrics (fleet flux, frontier pressure, capture-attempt success rate) that would be novel diagnostic angles for us.
- Whether `example_episode.json` in the dataset is a high-skill replay worth studying.
- Anything about the author's actual 850.9-scoring agent — this notebook is orthogonal to it.
