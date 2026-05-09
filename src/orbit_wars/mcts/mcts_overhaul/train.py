"""Neural Network Training script on Modal GPUs.

Loads the bootstrap datasets, trains the LightWeightMCTSNet,
and exports the result to ONNX for CPU inference.
"""

from __future__ import annotations

import sys
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

import os
from pathlib import Path
import time
import numpy as np

import modal

# Setup Modal environment
volume = modal.Volume.from_name("orbit-wars-vol", create_if_missing=True)

tuner_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install("torch>=2.6.0", "numpy>=2.0", "onnx", "onnxruntime", "kaggle_environments>=1.18.0")
    .add_local_dir(
        local_path=str(Path(__file__).parent.parent.parent.parent), # src/
        remote_path="/app/src",
        copy=True,
    )
)

app = modal.App("orbit-wars-nn-trainer", image=tuner_image)

import numpy as np
from torch.utils.data import DataLoader, IterableDataset

class OrbitWarsIterableDataset(IterableDataset):
    """Loads .npz files on the fly to prevent massive RAM OOMs."""
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.files = sorted(list(self.data_dir.glob("dataset_*.npz")))
        if not self.files:
            raise ValueError(f"No dataset found in {data_dir}")
        print(f"Found {len(self.files)} dataset files for lazy loading.")

    def __iter__(self):
        import torch
        import random
        import numpy as np

        worker_info = torch.utils.data.get_worker_info()
        if worker_info is None:
            files_to_process = self.files
        else:
            # Partition the files across multiple DataLoader workers
            files_to_process = [
                f for i, f in enumerate(self.files)
                if i % worker_info.num_workers == worker_info.id
            ]

        random.shuffle(files_to_process) # Shuffle files for better randomness across epochs

        for filepath in files_to_process:
            # Lazily load one file at a time per worker, and ensure it's a Path object
            data = np.load(filepath, allow_pickle=True)
            S = data['states']
            P = data['policies']
            V = data['values']

            # Shuffle the arrays within the file
            indices = np.arange(len(S))
            np.random.shuffle(indices)

            for i in indices:
                yield (
                    torch.tensor(S[i], dtype=torch.float32),
                    torch.tensor(P[i], dtype=torch.float32),
                    torch.tensor(V[i], dtype=torch.float32)
                )


def _load_npz_file(filepath: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Helper function to load an NPZ file. Must be at module level for pickling."""
    import numpy as np # Ensure numpy is imported for this function
    data = np.load(filepath, allow_pickle=True)
    return data['states'], data['policies'], data['values']

class OrbitWarsDataset:
    """Loads and concatenates .npz dataset files in parallel."""
    def __init__(self, data_dir: str):
        import torch
        import concurrent.futures
        import os

        files = list(Path(data_dir).glob("dataset_*.npz"))
        if not files:
            raise ValueError(f"No dataset found in {data_dir}")

        print(f"Loading {len(files)} dataset files in parallel bypassing GIL...")

        self.states = []
        self.policies = []
        self.values = []

        # Use ProcessPoolExecutor to bypass the GIL and load numpy arrays in parallel
        max_workers = min(32, (os.cpu_count() or 4))
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            for s, p, v in executor.map(_load_npz_file, files):
                self.states.append(s)
                self.policies.append(p)
                self.values.append(v)

        S = np.concatenate(self.states, axis=0)
        P = np.concatenate(self.policies, axis=0)
        V = np.concatenate(self.values, axis=0)

        self.S = torch.tensor(S, dtype=torch.float32)
        self.P = torch.tensor(P, dtype=torch.float32)
        self.V = torch.tensor(V, dtype=torch.float32)

        print(f"Total samples: {len(self.S)}")

    def __len__(self):
        return len(self.S)

    def __getitem__(self, idx):
        return self.S[idx], self.P[idx], self.V[idx]


@app.function(
    image=tuner_image,
    gpu="A10G",
    timeout=14400,
	cpu=8.0,
	memory=344064,
    volumes={"/data": volume},
    retries=modal.Retries(max_retries=5, backoff_coefficient=1.0)
)
def remote_main(epochs: int = 42, batch_size: int = 4096, lr: float = 1e-3):
    """Trains the model using GPU and saves the ONNX directly to the Volume."""
    import torch
    import torch.nn as nn
    import torch.optim as optim
    import os
    import numpy as np
    from torch.utils.data import DataLoader, IterableDataset
    from orbit_wars.mcts.mcts_overhaul.nn_model import LightWeightMCTSNet
    from orbit_wars.mcts.mcts_overhaul.features import STATE_DIM
    from orbit_wars.mcts.mcts_overhaul.dense_token import NUM_TOKENS
    import tempfile

    class OrbitWarsIterableDataset(IterableDataset):
        """Loads .npz files on the fly to prevent massive RAM OOMs."""
        def __init__(self, data_dir: str):
            self.data_dir = Path(data_dir)
            self.files = sorted(list(self.data_dir.glob("dataset_*.npz")))
            if not self.files:
                raise ValueError(f"No dataset found in {data_dir}")
            print(f"Found {len(self.files)} dataset files for lazy loading.")

        def __iter__(self):
            import torch
            import random
            import numpy as np

            worker_info = torch.utils.data.get_worker_info()
            if worker_info is None:
                files_to_process = self.files
            else:
                # Partition the files across multiple DataLoader workers
                files_to_process = [
                    f for i, f in enumerate(self.files)
                    if i % worker_info.num_workers == worker_info.id
                ]

            random.shuffle(files_to_process) # Shuffle files for better randomness across epochs

            for filepath in files_to_process:
                # Lazily load one file at a time per worker, and ensure it's a Path object
                data = np.load(filepath, allow_pickle=True)
                S = data['states']
                P = data['policies']
                V = data['values']

                # Shuffle the arrays within the file
                indices = np.arange(len(S))
                np.random.shuffle(indices)

                for i in indices:
                    yield (
                        torch.tensor(S[i], dtype=torch.float32),
                        torch.tensor(P[i], dtype=torch.float32),
                        torch.tensor(V[i], dtype=torch.float32)
                    )

    # Check if data exists
    if not list(Path("/data/nn_bootstrap").glob("dataset_*.npz")):
        raise FileNotFoundError("No dataset files found on volume. Please run bootstrap.py first.")

    dataset = OrbitWarsIterableDataset("/data/nn_bootstrap")

    # Use multiple workers for the DataLoader to ensure data is fed to GPU as fast as possible
    num_workers = min(8, (os.cpu_count() or 4))
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        # shuffle=True cannot be used with IterableDataset
        drop_last=True,
        num_workers=num_workers,
        pin_memory=True,          # Speeds up CPU to GPU tensor transfers
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on device: {device}")

    model = LightWeightMCTSNet(state_dim=STATE_DIM, num_tokens=NUM_TOKENS).to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)

    # Loss functions
    # Policy is multi-hot, so we use BCEWithLogitsLoss
    criterion_pol = nn.BCEWithLogitsLoss()
    # Value is [-1, 1], output is tanh, so MSELoss
    criterion_val = nn.MSELoss()

    model.train()

    for epoch in range(epochs):
        epoch_loss = 0.0
        pol_loss_total = 0.0
        val_loss_total = 0.0

        num_batches = 0 # Track the number of batches manually
        start_time = time.time()

        for s, p, v in loader:
            s, p, v = s.to(device), p.to(device), v.to(device)

            optimizer.zero_grad()
            pol_out, val_out = model(s)

            loss_pol = criterion_pol(pol_out, p)
            loss_val = criterion_val(val_out, v)
            loss = loss_pol + loss_val

            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            pol_loss_total += loss_pol.item()
            val_loss_total += loss_val.item()

            num_batches += 1 # Increment batch count

        elapsed = time.time() - start_time

        # Output logic relies on the manually tracked variable to avoid ZeroDivisionError
        if num_batches > 0:
            print(f"Epoch {epoch+1}/{epochs} - Time: {elapsed:.2f}s - Loss: {epoch_loss/num_batches:.4f} "
                  f"(Pol: {pol_loss_total/num_batches:.4f}, Val: {val_loss_total/num_batches:.4f})")
        else:
            print(f"Epoch {epoch+1}/{epochs} - Time: {elapsed:.2f}s - No batches processed")

    # Export to ONNX
    model.eval()
    dummy_input = torch.randn(1, STATE_DIM, device=device)

    out_dir = Path("/data/models")
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / "mcts_net.onnx"

    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['policy', 'value'],
        dynamic_axes={'input': {0: 'batch_size'}, 'policy': {0: 'batch_size'}, 'value': {0: 'batch_size'}}
    )

    print(f"Exported ONNX model to volume at {onnx_path}")
    volume.commit()


@app.local_entrypoint()
def main(epochs: int = 42, batch_size: int = 4096, lr: float = 1e-3):
    """Entrypoint to run GPU training on Modal."""
    remote_main.remote(epochs=epochs, batch_size=batch_size, lr=lr)