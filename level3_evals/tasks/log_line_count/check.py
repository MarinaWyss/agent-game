"""Pass if error_count.txt exists and contains the right number.

The simplest possible grader: exact match against a known answer. The answer is
computed from the pristine log so nobody has to remember it.
"""
from pathlib import Path

from harness import PRISTINE


def check(workspace: Path) -> tuple[bool, str]:
    expected = sum(1 for line in (PRISTINE / "app.log").read_text().splitlines() if " ERROR " in line)
    out = workspace / "error_count.txt"
    if not out.exists():
        return False, "error_count.txt was not created"
    content = out.read_text().strip()
    if content != str(expected):
        return False, f"expected {expected}, file says {content!r}"
    return True, f"error_count.txt == {expected}"
