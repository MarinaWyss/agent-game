"""Reset the workspace to its pristine state.

Every eval run starts from the same files. Without this, run 2 would be graded on
run 1's leftovers and the numbers would mean nothing.
"""
import hashlib
import shutil
from pathlib import Path

from . import PRISTINE, WORKSPACE


def reset_workspace(target: Path = WORKSPACE) -> Path:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(PRISTINE, target)
    return target


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unchanged_since_pristine(relative_path: str, workspace: Path = WORKSPACE) -> bool:
    """True if the agent left this file exactly as it found it."""
    pristine = PRISTINE / relative_path
    current = workspace / relative_path
    if not current.exists():
        return False
    return file_hash(pristine) == file_hash(current)


if __name__ == "__main__":
    reset_workspace()
    print(f"workspace reset -> {WORKSPACE}")
