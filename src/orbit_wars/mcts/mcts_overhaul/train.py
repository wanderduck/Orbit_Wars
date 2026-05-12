"""Neural Network Training script on Modal GPUs. Loads the bootstrap datasets, trains the LightWeightMCTSNet, and exports the result to ONNX for CPU inference."""
from __future__ import annotations
import sys
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

import os
from pathlib import Path
import time
import modal

volume = modal.Volume.from_name("orbit-wars-vol", create_if_missing=True)
tuner_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install("torch>=2.6.0", "numpy>=2.0", "onnx", "onnxruntime", "kaggle_environments>=1.18.0")
    .add_local_dir(
        local_path=str(Path(__file__).parent.parent.parent.parent),
        remote_path="/app/src",
        copy=True,
    )
)
app = modal.App("orbit-wars-nn-trainer", image=tuner_image)

@app.function(
    image=tuner_image,
    gpu="A10G",
    timeout=46800, cpu=12.0, memory=344064,
    volumes={"/data": volume},
    retries=modal.Retries(max_retries=5, backoff_coefficient=1.0)
)
def remote_main(epochs: int = 23, batch_size: int = 4096, lr: float = 1e-3):
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, IterableDataset
    import torch.multiprocessing
    import numpy as np
    import random

    # 🚀 CRITICAL FIX 1: Bypass restrictive /dev/shm (shared memory) limits by routing
    # inter-process tensor sharing through the container's fast file system instead.
    try:
        torch.multiprocessing.set_sharing_strategy('file_system')
    except Exception as e:
        print(f"Warning: Could not set sharing strategy to file_system: {e}")

    from orbit_wars.mcts.mcts_overhaul.nn_model import LightWeightMCTSNet
    from orbit_wars.mcts.mcts_overhaul.features import STATE_DIM
    from orbit_wars.mcts.mcts_overhaul.dense_token import NUM_TOKENS

    data_dir = "/data/nn_bootstrap"
    files = sorted(list(Path(data_dir).glob("dataset_*.npz")))
    if not files:
        raise FileNotFoundError(f"No dataset found in {data_dir}")

    print(f"Found {len(files)} dataset files for lazy loading. Bypassing massive RAM allocations...")

    class FastBatchedIterableDataset(IterableDataset):
        """Lazily loads .npz files and yields pre-collated batches to prevent GPU starvation."""
        def __init__(self, file_paths, batch_size: int):
            self.files = file_paths
            self.batch_size = batch_size

        def __iter__(self):
            import torch
            import random
            import numpy as np

            worker_info = torch.utils.data.get_worker_info()
            if worker_info is None:
                files_to_process = list(self.files)
            else:
                # Partition files evenly across multiple DataLoader workers
                files_to_process = [
                    f for i, f in enumerate(self.files)
                    if i % worker_info.num_workers == worker_info.id
                ]

                # Reseed to ensure variation across epochs and workers
                seed = worker_info.seed % (2**32)
                random.seed(seed)
                torch.manual_seed(seed)

            random.shuffle(files_to_process)
            S_rem, P_rem, V_rem = None, None, None

            for filepath in files_to_process:
                try:
                    with np.load(filepath, allow_pickle=True) as data:
                        S = torch.tensor(data['states'], dtype=torch.float32)
                        P = torch.tensor(data['policies'], dtype=torch.float32)
                        V = torch.tensor(data['values'], dtype=torch.float32)
                except Exception as e:
                    print(f"Error loading {filepath}: {e}")
                    continue

                # Fast in-memory shuffle for the current file
                indices = torch.randperm(len(S))
                S, P, V = S[indices], P[indices], V[indices]

                # Stitch any remainder left over from the previous file
                if S_rem is not None:
                    S = torch.cat([S_rem, S], dim=0)
                    P = torch.cat([P_rem, P], dim=0)
                    V = torch.cat([V_rem, V], dim=0)
                    S_rem, P_rem, V_rem = None, None, None

                idx = 0
                total = len(S)

                # Yield pre-collated chunks native to the requested batch size.
                # 🚀 CRITICAL FIX 2: .clone() prevents PyTorch from dumping the entire gigabyte-sized
                # parent array into IPC for every single batch slice!
                while idx + self.batch_size <= total:
                    yield (
                        S[idx:idx+self.batch_size].clone(),
                        P[idx:idx+self.batch_size].clone(),
                        V[idx:idx+self.batch_size].clone()
                    )
                    idx += self.batch_size

                # Cache the leftover rows for the next file iteration
                if idx < total:
                    S_rem = S[idx:].clone()
                    P_rem = P[idx:].clone()
                    V_rem = V[idx:].clone()

            # Note: We intentionally discard the final remainder at the very end to mimic `drop_last=True`
            # This prevents shape-mismatches from crashing the BatchNorm1D layers on the GPU.

    dataset = FastBatchedIterableDataset(files, batch_size=batch_size)

    loader = DataLoader(
        dataset,
        batch_size=None, # Crucial: tells DataLoader we are already yielding full batches directly!
        num_workers=min(4, (os.cpu_count() or 4)), # Reduced to 4 to perfectly balance file_descriptor limits
        pin_memory=True,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on device: {device}")

    if torch.cuda.is_available():
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cuda.matmul.allow_tf32 = True

    model = LightWeightMCTSNet(state_dim=STATE_DIM, num_tokens=NUM_TOKENS).to(device)

    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    # Cosine scheduling bound to epochs (since IterableDataset lacks a distinct __len__)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    use_amp = torch.cuda.is_available()
    scaler = torch.amp.GradScaler('cuda', enabled=use_amp) if use_amp else None

    criterion_pol = nn.BCEWithLogitsLoss()
    criterion_val = nn.MSELoss()

    model.train()
    for epoch in range(epochs):
        epoch_loss = pol_loss_total = val_loss_total = 0.0
        num_batches = 0
        start_time = time.time()

        for s, p, v in loader:
            s, p, v = s.to(device, non_blocking=True), p.to(device, non_blocking=True), v.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)

            if use_amp:
                with torch.amp.autocast('cuda'):
                    pol_out, val_out = model(s)
                    loss_pol = criterion_pol(pol_out, p)
                    loss_val = criterion_val(val_out, v)
                    loss = loss_pol + loss_val

                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                pol_out, val_out = model(s)
                loss_pol = criterion_pol(pol_out, p)
                loss_val = criterion_val(val_out, v)
                loss = loss_pol + loss_val
                loss.backward()
                optimizer.step()

            epoch_loss += loss.item()
            pol_loss_total += loss_pol.item()
            val_loss_total += loss_val.item()
            num_batches += 1

        # Advance the LR Scheduler at the epoch frontier
        scheduler.step()

        elapsed = time.time() - start_time
        if num_batches > 0:
            print(f"Epoch {epoch+1}/{epochs} - Time: {elapsed:.2f}s - Batches: {num_batches} - Loss: {epoch_loss/num_batches:.4f} "
                  f"(Pol: {pol_loss_total/num_batches:.4f}, Val: {val_loss_total/num_batches:.4f})")
        else:
            print(f"Epoch {epoch+1}/{epochs} - Time: {elapsed:.2f}s - No batches processed")

    model.eval()
    dummy_input = torch.randn(1, STATE_DIM, device=device)
    out_dir = Path("/data/models")
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / "mcts_net.onnx"

    torch.onnx.export(
        model, dummy_input, str(onnx_path),
        export_params=True, opset_version=14, do_constant_folding=True,
        input_names=['input'], output_names=['policy', 'value'],
        dynamic_axes={'input': {0: 'batch_size'}, 'policy': {0: 'batch_size'}, 'value': {0: 'batch_size'}}
    )
    print(f"Exported ONNX model to volume at {onnx_path}")
    volume.commit()

@app.local_entrypoint()
def main(epochs: int = 23, batch_size: int = 4096, lr: float = 1e-3):
    remote_main.remote(epochs=epochs, batch_size=batch_size, lr=lr)