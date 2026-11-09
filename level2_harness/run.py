"""Level 2: the same agent, wrapped in a harness.

Run from the repo root:
    python level2_harness/run.py "Run the tests and fix whatever fails."
    python level2_harness/run.py --max-turns 3 "..."         # watch it hit the cap
    python level2_harness/run.py --yolo "..."                # skip the permission prompt
    python level2_harness/run.py --system harness/SYSTEM_v2.md "..."
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import REPO  # noqa: E402
from harness.agent import run_agent  # noqa: E402
from harness.tools import always_allow, ask_in_terminal  # noqa: E402
from harness.workspace import reset_workspace  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default="Run the tests and fix whatever fails.")
    ap.add_argument("--max-turns", type=int, default=15, help="hard cap on loop iterations")
    ap.add_argument("--yolo", action="store_true", help="auto-approve shell commands")
    ap.add_argument("--system", default=str(REPO / "harness" / "SYSTEM.md"), help="path to a system prompt file")
    ap.add_argument("--no-reset", action="store_true", help="keep the workspace as it is")
    args = ap.parse_args()

    if not args.no_reset:
        reset_workspace()

    print(f"system prompt: {args.system}")
    print(f"max turns:     {args.max_turns}")
    print(f"shell gate:    {'off (--yolo)' if args.yolo else 'ask before every run_shell'}")
    print(f"task:          {args.task}\n")

    run_agent(
        task=args.task,
        system=Path(args.system),
        max_turns=args.max_turns,
        confirm=always_allow if args.yolo else ask_in_terminal,
    )


if __name__ == "__main__":
    main()
