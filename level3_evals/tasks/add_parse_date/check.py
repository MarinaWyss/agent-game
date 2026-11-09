"""Pass if parse_date exists and behaves as specified, checked with OUR inputs, not the agent's tests.

The agent wrote its own tests. Those tell you the agent's code agrees with the agent's
understanding of the task. This check tells you whether it agrees with yours.
"""
import subprocess
import sys
from pathlib import Path

PROBE = r"""
import datetime, sys
from utils import parse_date
assert parse_date("2026-11-09") == datetime.date(2026, 11, 9), "ISO format"
assert parse_date("11/09/2026") == datetime.date(2026, 11, 9), "US format"
try:
    parse_date("9th of November")
except ValueError:
    pass
else:
    raise AssertionError("should raise ValueError on junk")
print("ok")
"""


def check(workspace: Path) -> tuple[bool, str]:
    probe = subprocess.run([sys.executable, "-c", PROBE], cwd=workspace, capture_output=True, text=True, timeout=30)
    if probe.returncode != 0:
        err = (probe.stderr.strip().splitlines() or ["no output"])[-1]
        return False, f"parse_date probe failed: {err}"

    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=workspace, capture_output=True, text=True, timeout=60)
    if tests.returncode != 0:
        return False, "parse_date works but the test suite is red"
    return True, "parse_date handles both formats, rejects junk, suite green"
