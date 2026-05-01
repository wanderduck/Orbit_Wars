# CUDA sanity check (Tier 1)

**Date:** 2026-04-30

## Result: PASS

```
torch: 2.9.1+cu130
CUDA available: True
Device: NVIDIA GeForce RTX 2080 Ti
Compute capability: (7, 5)   ← Turing / sm_75
CUDA version (runtime): 13.0
Tensor device: cuda:0
```

The cu130 wheels in `pyproject.toml` support sm_75 (Turing). No fallback to cu128 needed.

## Reproducer

```bash
uv run python -c "
import torch
print('torch:', torch.__version__)
print('CUDA available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('Device:', torch.cuda.get_device_name(0))
    print('Compute capability:', torch.cuda.get_device_capability(0))
    print('CUDA version (runtime):', torch.version.cuda)
    t = torch.zeros(1, device='cuda')
    print('Tensor device:', t.device)
"
```

## Fallback procedure (if cu130 ever drops sm_75)

Edit `pyproject.toml`:

```toml
[[tool.uv.index]]
name = "pytorch-cu128"   # was pytorch-cu130
url = "https://download.pytorch.org/whl/cu128"
explicit = true

[tool.uv.sources]
torch = { index = "pytorch-cu128" }
```

Then `uv sync`. Note that RAPIDS 26.2 (`*-cu12==26.2.*`) is on CUDA 12.x, so it stays compatible across cu128/cu130.
