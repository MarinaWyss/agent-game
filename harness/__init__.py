"""Shared harness used by levels 2 to 5.

Level 1 has its own self-contained agent.py so the loop can be read in one screen.
From level 2 on, everything imports from here so the harness is in one place and
can be changed in one place (which is the whole point of level 5).
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKSPACE = REPO / "workspace"
PRISTINE = REPO / "_pristine" / "workspace"


def _load_dotenv() -> None:
    """Read KEY=VALUE lines from .env at the repo root, if present. No dependency needed."""
    env_file = REPO / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# The model doing the work and the model grading the work.
# They are different on purpose. See level4_judge/README.md.
# Every Claude model ID is a pinned snapshot: the weights behind an ID never change,
# so eval results stay comparable until you change this string.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-haiku-5-5")

# USD per million tokens: (input, output, cache-read multiplier on input price).
# From https://platform.claude.com/docs/en/about-claude/pricing as of Nov 2026.
# Cache writes are billed at 1.25x input. Edit if prices change; the numbers in the
# eval tables are estimates for comparing variants, not an invoice.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.025),
    "claude-opus-5-5": (4.0, 20.0, 0.05),
    "claude-sonnet-5-5": (2.0, 10.0, 0.05),
    "claude-haiku-5-5": (0.10, 0.50, 0.10),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  cache_read: int = 0, cache_write: int = 0) -> float | None:
    """Rough USD cost of one run. None if the model isn't in PRICES."""
    if model not in PRICES:
        return None
    inp, out, read_mult = PRICES[model]
    return (input_tokens * inp + cache_write * inp * 1.25 + cache_read * inp * read_mult
            + output_tokens * out) / 1_000_000
