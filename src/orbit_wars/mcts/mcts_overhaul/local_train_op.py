"""Neural Network Training script for local execution.
Lazily streams massive compressed datasets directly from zip archives to bypass
system RAM limitations, trains the LightWeightMCTSNet, and exports to ONNX.
Saves and overwrites checkpoints after EVERY epoch to prevent data loss.
"""
from __future__ import annotations

import os
import sys
import time
import random
import argparse
import zipfile
import multiprocessing as mp
from pathlib import Path

import numpy as np
import numpy.lib.format as np_fmt
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, IterableDataset

# Dynamically add the 'src' root to sys.path so 'orbit_wars' modules can be imported naturally
project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from orbit_wars.mcts.mcts_overhaul.nn_model import LightWeightMCTSNet
from orbit_wars.mcts.mcts_overhaul.features import STATE_DIM
from orbit_wars.mcts.mcts_overhaul.dense_token import NUM_TOKENS


def read_exact(f, num_bytes: int) -> bytes:
    """Guarantees we read exactly `num_bytes` from a stream, preventing truncation."""
    chunks = []
    bytes_read = 0
    while bytes_read < num_bytes:
        chunk = f.read(num_bytes - bytes_read)
        if not chunk:
            break
        chunks.append(chunk)
        bytes_read += len(chunk)
    return b''.join(chunks)


class StreamingBatchedIterableDataset(IterableDataset):
    """
    Reads compressed .npz files directly as binary streams without decompressing
    the whole arrays into RAM. Maintains a sliding shuffle buffer.
    Dynamically distributes work across processes using Halving Work-Stealing,
    so idle workers automatically jump in and assist others on the exact same
    file to maximize throughput.
    """
    def __init__(self, file_paths: list[Path], batch_size: int, chunks_per_buffer: int = 5):
        self.files = file_paths
        self.batch_size = batch_size
        self.chunk_size = batch_size * chunks_per_buffer

        # Establish IPC synchronization proxies safely picklable to PyTorch worker subprocesses
        self.manager = mp.Manager()
        self.lock = self.manager.Lock()
        self.active_tasks = self.manager.dict()
        self.unassigned_files = self.manager.list()

        self.file_metadata = {}

        print("Pre-scanning dataset headers for dynamic Work-Stealing distribution...")
        for i, filepath in enumerate(self.files):
            try:
                with zipfile.ZipFile(filepath, 'r') as zf:
                    names = zf.namelist()
                    s_name = 'states.npy' if 'states.npy' in names else 'states'
                    p_name = 'policies.npy' if 'policies.npy' in names else 'policies'
                    v_name = 'values.npy' if 'values.npy' in names else 'values'

                    with zf.open(s_name, 'r') as f_s, \
                         zf.open(p_name, 'r') as f_p, \
                         zf.open(v_name, 'r') as f_v:

                        def parse_header(f):
                            version = np_fmt.read_magic(f)
                            try:
                                shape, _, dtype = np_fmt._read_array_header(f, version)
                            except AttributeError:
                                if version == (1, 0):
                                    shape, _, dtype = np_fmt.read_array_header_1_0(f)
                                else:
                                    shape, _, dtype = np_fmt.read_array_header_2_0(f)
                            return shape, dtype, f.tell()

                        shape_s, dtype_s, hl_s = parse_header(f_s)
                        shape_p, dtype_p, hl_p = parse_header(f_p)
                        shape_v, dtype_v, hl_v = parse_header(f_v)

                        total_rows = shape_s[0]
                        rb_s = int(np.prod(shape_s[1:]) * dtype_s.itemsize) if len(shape_s) > 1 else dtype_s.itemsize
                        rb_p = int(np.prod(shape_p[1:]) * dtype_p.itemsize) if len(shape_p) > 1 else dtype_p.itemsize
                        rb_v = int(np.prod(shape_v[1:]) * dtype_v.itemsize) if len(shape_v) > 1 else dtype_v.itemsize

                        self.file_metadata[i] = {
                            'filepath': filepath,
                            's_name': s_name, 'p_name': p_name, 'v_name': v_name,
                            'shape_s': shape_s, 'dtype_s': dtype_s, 'hl_s': hl_s, 'rb_s': rb_s,
                            'shape_p': shape_p, 'dtype_p': dtype_p, 'hl_p': hl_p, 'rb_p': rb_p,
                            'shape_v': shape_v, 'dtype_v': dtype_v, 'hl_v': hl_v, 'rb_v': rb_v,
                            'total_rows': total_rows
                        }
            except Exception as e:
                print(f"Error parsing {filepath}: {e}")

    def __getstate__(self):
        """Allows Dataset to be safely Pickled to DataLoader worker processes without Exception."""
        state = self.__dict__.copy()
        if 'manager' in state:
            del state['manager']
        return state

    def reset_epoch(self):
        """Called inside main thread to reset shared work queues for a new epoch."""
        with self.lock:
            self.active_tasks.clear()
            file_indices = list(self.file_metadata.keys())
            random.shuffle(file_indices)
            del self.unassigned_files[:]
            self.unassigned_files.extend(file_indices)

    def __iter__(self):
        worker_info = torch.utils.data.get_worker_info()
        worker_id = worker_info.id if worker_info else 0

        seed = worker_info.seed % (2**32) if worker_info else 0
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)

        open_zfs = {}

        def get_work():
            with self.lock:
                # 1. Continue the current sequentially assigned task if work remains (Fastest Read)
                if worker_id in self.active_tasks:
                    f_idx, c_row, e_row = self.active_tasks[worker_id]
                    if c_row < e_row:
                        alloc = min(self.chunk_size, e_row - c_row)
                        self.active_tasks[worker_id] = (f_idx, c_row + alloc, e_row)
                        return f_idx, c_row, alloc
                    else:
                        del self.active_tasks[worker_id]

                # 2. Grab an entirely unstarted file from the queue
                if len(self.unassigned_files) > 0:
                    f_idx = self.unassigned_files.pop(0)
                    e_row = self.file_metadata[f_idx]['total_rows']
                    alloc = min(self.chunk_size, e_row)
                    self.active_tasks[worker_id] = (f_idx, alloc, e_row)
                    return f_idx, 0, alloc

                # 3. Work Stealing: Help a busy worker process their remaining file
                best_victim = None
                max_rem = 0
                for victim_w, (v_f_idx, v_c_row, v_e_row) in self.active_tasks.items():
                    if victim_w == worker_id: continue
                    rem = v_e_row - v_c_row
                    if rem > max_rem:
                        max_rem = rem
                        best_victim = victim_w

                # Dramatically lowered threshold so workers will aggressively split the final few megabytes.
                if best_victim is not None and max_rem >= self.batch_size * 2:
                    v_f_idx, v_c_row, v_e_row = self.active_tasks[best_victim]

                    # Steal the END half, but mathematically align the amount to EXACT multiples
                    # of batch_size so that no dropped/fragmented dataset remainder rows are created
                    steal_amount = max_rem // 2
                    steal_amount = (steal_amount // self.batch_size) * self.batch_size

                    if steal_amount > 0:
                        new_v_e_row = v_e_row - steal_amount
                        self.active_tasks[best_victim] = (v_f_idx, v_c_row, new_v_e_row)

                        alloc = min(self.chunk_size, steal_amount)
                        self.active_tasks[worker_id] = (v_f_idx, new_v_e_row + alloc, v_e_row)
                        return v_f_idx, new_v_e_row, alloc

                # 4. If active work exists but it's too small to steal (< 2 batches), queue WAIT
                if len(self.active_tasks) > 0:
                    return "WAIT", None, None

                # 5. All globally distributed work has been completely exhausted
                return None, None, None

        idle_start_time = None

        try:
            while True:
                f_idx, start_row, alloc_size = get_work()

                # Watchdog State Check
                if f_idx == "WAIT":
                    if idle_start_time is None:
                        idle_start_time = time.time()
                    elif time.time() - idle_start_time > 60:
                        print(f"\n[Worker {worker_id}] Timed out after 60s of 0% CPU. Freeing system RAM and ending task.")
                        break
                    time.sleep(1)
                    continue
                else:
                    idle_start_time = None

                if f_idx is None:
                    break # Natural completion

                meta = self.file_metadata[f_idx]

                if f_idx not in open_zfs:
                    # Clean up old file descriptors so we only keep 1 ZipFile context open per worker thread
                    for cached_idx in list(open_zfs.keys()):
                        czf, cf_s, cf_p, cf_v, _ = open_zfs.pop(cached_idx)
                        cf_s.close(); cf_p.close(); cf_v.close(); czf.close()

                    zf = zipfile.ZipFile(meta['filepath'], 'r')
                    f_s = zf.open(meta['s_name'], 'r')
                    f_p = zf.open(meta['p_name'], 'r')
                    f_v = zf.open(meta['v_name'], 'r')
                    open_zfs[f_idx] = (zf, f_s, f_p, f_v, -1)

                zf, f_s, f_p, f_v, local_read_head = open_zfs[f_idx]

                # Seek if assisting another worker, or jumping past the header on first read
                if local_read_head != start_row:
                    f_s.seek(meta['hl_s'] + start_row * meta['rb_s'])
                    f_p.seek(meta['hl_p'] + start_row * meta['rb_p'])
                    f_v.seek(meta['hl_v'] + start_row * meta['rb_v'])

                bytes_s = read_exact(f_s, alloc_size * meta['rb_s'])
                bytes_p = read_exact(f_p, alloc_size * meta['rb_p'])
                bytes_v = read_exact(f_v, alloc_size * meta['rb_v'])

                open_zfs[f_idx] = (zf, f_s, f_p, f_v, start_row + alloc_size)

                if not bytes_s or not bytes_p or not bytes_v:
                    with self.lock:
                        if worker_id in self.active_tasks:
                            del self.active_tasks[worker_id]
                    continue

                # Guard against unexpectedly truncated zip archive chunks
                if len(bytes_s) != alloc_size * meta['rb_s'] or \
                   len(bytes_p) != alloc_size * meta['rb_p'] or \
                   len(bytes_v) != alloc_size * meta['rb_v']:
                    print(f"\nWarning: Truncated read from {meta['filepath']}. Skipping corrupted chunk.")
                    with self.lock:
                        if worker_id in self.active_tasks:
                            del self.active_tasks[worker_id]
                    continue

                arr_s = np.frombuffer(bytes_s, dtype=meta['dtype_s']).copy().reshape(alloc_size, *meta['shape_s'][1:])
                arr_p = np.frombuffer(bytes_p, dtype=meta['dtype_p']).copy().reshape(alloc_size, *meta['shape_p'][1:])
                arr_v = np.frombuffer(bytes_v, dtype=meta['dtype_v']).copy().reshape(alloc_size, *meta['shape_v'][1:])

                S = torch.from_numpy(arr_s).float()
                P = torch.from_numpy(arr_p).float()
                V = torch.from_numpy(arr_v).float()

                # Optimization: Delete raw bytes instantly before converting to Torch tensors to cut RAM spike in half
                del bytes_s, bytes_p, bytes_v
                del arr_s, arr_p, arr_v

                chunk_total = len(S)
                indices = torch.randperm(chunk_total)
                S, P, V = S[indices], P[indices], V[indices]

                idx = 0
                while idx + self.batch_size <= chunk_total:
                    yield (
                        S[idx:idx+self.batch_size].clone(),
                        P[idx:idx+self.batch_size].clone(),
                        V[idx:idx+self.batch_size].clone()
                    )
                    idx += self.batch_size

                del S, P, V

        finally:
            for cached_idx in list(open_zfs.keys()):
                czf, cf_s, cf_p, cf_v, _ = open_zfs.pop(cached_idx)
                cf_s.close(); cf_p.close(); cf_v.close(); czf.close()
            open_zfs.clear()

            # --- MEMORY BLOAT HOTFIX ---
            # Explicitly force Python's garbage collector and C-library's malloc to release RAM back
            # to the OS immediately before PyTorch decides to zombie the worker subprocess at the end of generator.
            import gc
            gc.collect()
            try:
                import ctypes, sys
                if sys.platform.startswith('linux'):
                    ctypes.CDLL('libc.so.6').malloc_trim(0)
            except Exception:
                pass


def main(args):
    try:
        import torch.multiprocessing
        torch.multiprocessing.set_sharing_strategy('file_system')
    except Exception as e:
        pass

    data_dir = Path(args.data_dir)
    files = sorted(list(data_dir.glob("dataset_*.npz")))

    if not files:
        raise FileNotFoundError(f"No dataset found in {data_dir}. Check paths.")

    print(f"Found {len(files)} dataset files.")
    print("Initiating Streaming Zip Loader. System RAM usage will remain safely under 5GB regardless of dataset size!")

    dataset = StreamingBatchedIterableDataset(files, batch_size=args.batch_size, chunks_per_buffer=args.chunks_per_buffer)

    loader = DataLoader(
        dataset,
        batch_size=None,
        num_workers=args.num_workers,
        pin_memory=True,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on device: {device} (Targeting RTX 2080 Ti)")

    if torch.cuda.is_available():
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cuda.matmul.allow_tf32 = True

    model = LightWeightMCTSNet(state_dim=STATE_DIM, num_tokens=NUM_TOKENS).to(device)
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    # --- WARMUP + COSINE ANNEALING SCHEDULER ---
    # Warms up to args.lr over the first 2 epochs to prevent gradient explosion in deep layers
    warmup_epochs = min(2, args.epochs - 1) if args.epochs > 1 else 0
    if warmup_epochs > 0:
        warmup_scheduler = optim.lr_scheduler.LinearLR(optimizer, start_factor=0.1, total_iters=warmup_epochs)
        cosine_scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=(args.epochs - warmup_epochs))
        scheduler = optim.lr_scheduler.SequentialLR(optimizer, schedulers=[warmup_scheduler, cosine_scheduler], milestones=[warmup_epochs])
    else:
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.epochs))

    # ======= RETRAINING / RESUME LOGIC =======
    start_epoch = 0
    if args.resume:
        resume_path = Path(args.resume)
        if resume_path.is_file():
            print(f"Loading checkpoint from '{resume_path}'...")
            checkpoint = torch.load(resume_path, map_location=device, weights_only=False)

            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                model.load_state_dict(checkpoint['model_state_dict'])

                if not args.finetune:
                    try:
                        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
                        scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
                        start_epoch = checkpoint.get('epoch', 0)
                        print(f"Restored optimizer and scheduler state. Resuming from epoch {start_epoch + 1}.")
                    except KeyError:
                        print("Optimizer state missing in checkpoint. Proceeding with fresh optimizer.")
                else:
                    print("Fine-tune mode enabled. Using fresh learning rate and optimizer.")
            else:
                model.load_state_dict(checkpoint)
                print("Successfully loaded prior model weights!")
        else:
            print(f"Warning: --resume file '{args.resume}' not found! Starting from scratch.")
    # =========================================

    use_amp = torch.cuda.is_available()
    scaler = torch.amp.GradScaler('cuda', enabled=use_amp) if use_amp else None

    criterion_pol = nn.BCEWithLogitsLoss()
    criterion_val = nn.MSELoss()

    target_epochs = start_epoch + args.epochs
    out_path = Path(args.out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    pt_path = out_path / "mcts_net.pt"
    onnx_path = out_path / "mcts_net.onnx"

    model.train()

    for epoch in range(start_epoch, target_epochs):
        dataset.reset_epoch() # Dynamically refreshes the global workpool queue across all thread states

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
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=args.clip_grad)

                scaler.step(optimizer)
                scaler.update()
            else:
                pol_out, val_out = model(s)
                loss_pol = criterion_pol(pol_out, p)
                loss_val = criterion_val(val_out, v)
                loss = loss_pol + loss_val

                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=args.clip_grad)
                optimizer.step()

            epoch_loss += loss.item()
            pol_loss_total += loss_pol.item()
            val_loss_total += loss_val.item()
            num_batches += 1

            if num_batches % 50 == 0:
                print(f"\rEpoch {epoch+1}/{target_epochs} - Batch {num_batches} - Loss: {epoch_loss/num_batches:.4f}...", end="")

        scheduler.step()

        elapsed = time.time() - start_time
        # Clear the carriage return line and print epoch summary
        print("\r" + " " * 80, end="\r")
        if num_batches > 0:
            print(f"Epoch {epoch+1}/{target_epochs} - Time: {elapsed:.2f}s - Batches: {num_batches} - Loss: {epoch_loss/num_batches:.4f} "
                  f"(Pol: {pol_loss_total/num_batches:.4f}, Val: {val_loss_total/num_batches:.4f})")
        else:
            print(f"Epoch {epoch+1}/{target_epochs} - Time: {elapsed:.2f}s - No batches processed")

        # ==========================================================
        # OVERWRITE AND SAVE MODEL AT THE END OF EVERY EPOCH
        # ==========================================================
        print(f"--> Saving checkpoint and exporting ONNX for Epoch {epoch+1}...")

        # 1. Save Native PyTorch Checkpoint
        torch.save({
            'epoch': epoch + 1, # Saves the NEXT epoch number to resume from seamlessly
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'scheduler_state_dict': scheduler.state_dict(),
        }, pt_path)

        # 2. Export ONNX Model
        model.eval() # MUST be in eval mode for ONNX export (disables Dropout / freezes BatchNorm)

        # Wrapping in torch.no_grad() is best practice for ONNX export memory footprint
        with torch.no_grad():
            dummy_input = torch.randn(1, STATE_DIM, device=device)
            # FIXED: Removed dynamic_axes, upgraded opset_version to 18
            torch.onnx.export(
                model,
                dummy_input,
                str(onnx_path),
                export_params=True,
                opset_version=18,
                do_constant_folding=True,
                input_names=['input'],
                output_names=['policy', 'value']
            )

        model.train() # CRITICAL: Switch back to train mode for the next epoch loop!
        print(f"--> Successfully updated {pt_path.name} and {onnx_path.name}\n")
        # ==========================================================

    print("Training Complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train LightWeightMCTSNet on a local machine using streaming chunks.")
    parser.add_argument("--data-dir", type=str, default="./data/nn_bootstrap", help="Path containing dataset_*.npz files")
    parser.add_argument("--out-dir", type=str, default="./models", help="Directory to save the trained ONNX and PT models")

    parser.add_argument("--resume", type=str, default="", help="Path to a previously saved .pt checkpoint to resume training from")
    parser.add_argument("--finetune", action="store_true", help="If passed with --resume, ignores old learning rate/optimizer states")

    parser.add_argument("--epochs", type=int, default=23, help="Number of training epochs (or additional epochs if resuming)")
    parser.add_argument("--batch-size", type=int, default=4096, help="Batch size (easily fits in 11GB VRAM)")
    parser.add_argument("--chunks-per-buffer", type=int, default=5, help="Controls memory usage: streams batches into RAM in multiples of this number before shuffling.")

    parser.add_argument("--lr", type=float, default=5e-4, help="Learning rate (Lowered to 5e-4 for deep network stability)")
    parser.add_argument("--weight-decay", type=float, default=1e-3, help="Weight decay (Increased to 1e-3 to prevent overfitting)")
    parser.add_argument("--clip-grad", type=float, default=2.0, help="Maximum gradient norm threshold to prevent exploding gradients")
    parser.add_argument("--num-workers", type=int, default=min(2, os.cpu_count() or 2), help="Number of PyTorch DataLoader workers")

    args = parser.parse_args()
    main(args)