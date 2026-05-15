"""Application to build and submit the MCTS overhaul to Kaggle."""

import argparse
import tarfile
import tempfile
from pathlib import Path
import shutil
import subprocess
import sys
import os

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

def build_tarball(out_path="submission.tar.gz", smol="no"):
    out_path = Path(out_path).resolve()

    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir) / "staging"
        staging.mkdir()

        # 1. Write custom main.py
        main_py = staging / "main.py"
        main_py.write_text('''"""Kaggle Submission Entry Point for MCTS Overhaul."""
from orbit_wars.mcts.mcts_overhaul.agent import agent as mcts_agent

def agent(obs, config=None):
    return mcts_agent(obs, config)
''')

        # 2. Copy orbit_wars source
        shutil.copytree(
            REPO_ROOT / "src" / "orbit_wars",
            staging / "orbit_wars",
            ignore=shutil.ignore_patterns("__pycache__", "*opponents", "*rl")
        )

        # 3. Copy models directory
        # Exclude PyTorch checkpoints like mcts_net.pt to save space (retaining .onnx)
        model_ignore = shutil.ignore_patterns("__pycache__", "*.pt", "*.pth", "*opponents", "*rl")

        match smol:
            case "no":
                models_dir = REPO_ROOT / "models"
                if models_dir.exists():
                    shutil.copytree(models_dir, staging / "models", ignore=model_ignore)
            case "yes":
                models_dir = REPO_ROOT / "models_smol"
                if models_dir.exists():
                    shutil.copytree(models_dir, staging / "models_smol", ignore=model_ignore)
            case _:
                raise ValueError(f"Invalid value for --smol: {smol}")

        # 4. Pack
        if out_path.exists():
            out_path.unlink()

        with tarfile.open(out_path, mode="w:gz") as tf:
            for entry in sorted(staging.iterdir()):
                tf.add(entry, arcname=entry.name)

    return out_path

def smoke_test(tarball: Path):
    with tempfile.TemporaryDirectory() as tmpdir:
        with tarfile.open(tarball, mode="r:gz") as tf:
            # We use filter='data' for safety if supported, but older python versions don't have it
            if sys.version_info >= (3, 12):
                tf.extractall(tmpdir, filter="data")
            else:
                tf.extractall(tmpdir)

        smoke_script = (
            f"import sys, os; sys.path.insert(0, {tmpdir!r}); os.chdir({tmpdir!r}); "
            "import main; "
            "assert callable(main.agent), 'agent not callable'; "
            "result = main.agent({'player': 0, 'planets': [], 'fleets': [], "
            "'angular_velocity': 0.05, 'initial_planets': [], 'comets': [], "
            "'comet_planet_ids': [], 'remainingOverageTime': 60.0}); "
            "assert isinstance(result, list), f'expected list, got {type(result)}'; "
            "print(f'smoke ok: {len(result)} moves')"
        )

        result = subprocess.run([sys.executable, "-c", smoke_script], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Smoke test failed:\n{result.stdout}\n{result.stderr}")

def submit(tarball: Path, message: str):
    print(f"Submitting {tarball} to Kaggle with message: '{message}'")
    cmd = ["kaggle", "competitions", "submit", "orbit-wars", "-f", str(tarball), "-m", message]
    try:
        subprocess.run(cmd, check=True)
        print("Submission complete.")
    except subprocess.CalledProcessError as e:
        print(f"Submission failed with exit code {e.returncode}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Build and submit MCTS Overhaul to Orbit Wars Kaggle competition")
    parser.add_argument("-m", "--message", default="MCTS Overhaul via Neural Net Prior", help="Submission message")
    parser.add_argument("--dry-run", action="store_true", help="Build and smoke test without submitting")
    parser.add_argument("--smol", choices=["no", "yes"], default="no", help="Determine if the smol models directory should be used")
    args = parser.parse_args()

    print("Building submission tarball...")
    tarball = build_tarball(smol=args.smol)
    print(f"Tarball built at {tarball}")

    # Check tarball size to adhere to Kaggle's limits
    size_mb = tarball.stat().st_size / (1024 * 1024)
    print(f"Tarball size: {size_mb:.2f} MB")
    if size_mb > 100.0:
        print(f"\n[WARNING] Tarball is {size_mb:.2f} MB, which exceeds the 100 MB Kaggle limit!")
        print("Interrupting submission. Please ensure large files like PyTorch checkpoints are properly excluded.")
        sys.exit(1)

    print("Running smoke test on tarball...")
    smoke_test(tarball)
    print("Smoke test passed.")

    if args.dry_run:
        print("Dry run complete. Skipping submission.")
    else:
        submit(tarball, args.message)

if __name__ == "__main__":
    main()