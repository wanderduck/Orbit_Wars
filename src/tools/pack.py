"""Submission packager.

Builds ``submission.tar.gz`` with ``main.py`` at the bundle root, per Kaggle's
requirement (E4 §Submission). Ships the heuristic agent by default;
``--include-rl`` adds the RL module + a checkpoint for v2+ submissions.

After packing, runs a smoke test that:
1. Extracts the tarball into a fresh tempdir.
2. Imports the extracted ``main.py``.
3. Calls ``main.agent({...})`` with a minimal observation.
4. Asserts no exception, ``agent`` is callable, returns a list.

If the smoke test fails, the tarball is rejected (the file is not deleted but
its path is reported with a FAILED prefix and the Kaggle submission MUST NOT
be issued).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

__all__ = ["pack_submission"]


REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # /Orbit_Wars/
SRC = REPO_ROOT / "src"


def pack_submission(
    out: Path | str = "submission.tar.gz",
    *,
    include_rl: Path | str | None = None,
) -> tuple[Path, str]:
    """Build the submission tarball.

    Returns ``(out_path, sha256_hex)`` on success.
    Raises ``RuntimeError`` if the smoke test fails.
    """
    out_path = Path(out).resolve()
    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir) / "staging"
        staging.mkdir()

        # Copy main.py to bundle root
        shutil.copy2(SRC / "main.py", staging / "main.py")

        # Copy orbit_wars/ but exclude rl/ and tools/ subpackages by default
        ow_src = SRC / "orbit_wars"
        ow_dst = staging / "orbit_wars"

        def _ignore(_root: str, names: list[str]) -> set[str]:
            ignored: set[str] = set()
            # Skip RL by default; opt-in via --include-rl
            if include_rl is None and "rl" in names:
                ignored.add("rl")
            # Skip __pycache__ always
            if "__pycache__" in names:
                ignored.add("__pycache__")
            return ignored

        shutil.copytree(ow_src, ow_dst, ignore=_ignore)

        # If include_rl supplied, also bundle the checkpoint
        if include_rl is not None:
            checkpoint_src = Path(include_rl).resolve()
            if not checkpoint_src.exists():
                raise FileNotFoundError(f"checkpoint not found: {checkpoint_src}")
            (ow_dst / "rl" / "checkpoints").mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkpoint_src, ow_dst / "rl" / "checkpoints" / "best.pt")

        # Build tarball with main.py at archive root
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            out_path.unlink()
        with tarfile.open(out_path, mode="w:gz") as tf:
            for entry in sorted(staging.iterdir()):
                tf.add(entry, arcname=entry.name)  # recursive by default

        # Compute SHA-256
        sha = hashlib.sha256()
        with out_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        sha256_hex = sha.hexdigest()

    # Smoke test: extract elsewhere and run a minimal agent invocation
    _smoke_test(out_path)

    return out_path, sha256_hex


def _smoke_test(tarball: Path) -> None:
    """Extract the tarball into a fresh tempdir and run a minimal `agent({})` call."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with tarfile.open(tarball, mode="r:gz") as tf:
            tf.extractall(tmpdir, filter="data")  # type: ignore[arg-type]
        # Execute the smoke test in a subprocess so we don't pollute orchestrator imports
        smoke_script = (
            f"import sys; sys.path.insert(0, {tmpdir!r}); "
            "import main; "
            "assert callable(main.agent), 'agent not callable'; "
            "result = main.agent({'player': 0, 'planets': [], 'fleets': [], "
            "'angular_velocity': 0.05, 'initial_planets': [], 'comets': [], "
            "'comet_planet_ids': [], 'remainingOverageTime': 60.0}); "
            "assert isinstance(result, list), f'expected list, got {type(result)}'; "
            "print(f'smoke ok: {len(result)} moves')"
        )
        result = subprocess.run(
            [sys.executable, "-c", smoke_script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"smoke test FAILED for {tarball}:\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
