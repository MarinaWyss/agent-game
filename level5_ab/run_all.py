"""Level 5: change the harness, re-run every eval, compare.

    python level5_ab/run_all.py --a harness/SYSTEM.md --b harness/SYSTEM_v2.md --n 2

Runs level 3 (deterministic) and level 4 (generate + judge) against both system prompts
and prints the two columns side by side. Everything else about the harness is held fixed,
so any difference in the numbers is the prompt.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "level3_evals"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "level4_judge"))

import anthropic  # noqa: E402
from run_evals import run_suite  # noqa: E402
from judge import extract_output, judge_one, load_tasks  # noqa: E402

from harness import REPO  # noqa: E402
from harness.agent import run_agent  # noqa: E402
from harness.tools import always_allow  # noqa: E402
from harness.workspace import reset_workspace  # noqa: E402


def level3(system: Path, n: int, label: str) -> dict:
    suite = run_suite(system, n=n, max_turns=15, only=None, verbose=False, label=label)
    by_task = {}
    for r in suite["runs"]:
        d = by_task.setdefault(r["task"], {"pass": 0, "n": 0, "tokens": 0, "turns": 0})
        d["pass"] += r["passed"]
        d["n"] += 1
        d["tokens"] += r["input_tokens"] + r["output_tokens"]  # input_tokens here already includes cache reads
        d["turns"] += r["turns"]
    return by_task


def level4(system: Path, n: int) -> dict:
    client = anthropic.Anthropic()
    by_task = {}
    for t in load_tasks():
        d = by_task.setdefault(t["name"], {"pass": 0, "criteria": 0, "tokens": 0, "turns": 0, "n": 0})
        for _ in range(n):
            reset_workspace()
            result = run_agent(t["prompt"], system=system, confirm=always_allow, verbose=False)
            output = extract_output(t["output"], result.final_text)
            grades = (judge_one(client, t, output, numeric=False).get("grades") or [])
            d["pass"] += sum(1 for g in grades if g.get("pass") is True)
            d["criteria"] += len(t["criteria"])
            d["tokens"] += result.total_input_tokens + result.output_tokens
            d["turns"] += result.turns
            d["n"] += 1
    return by_task


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=str(REPO / "harness" / "SYSTEM.md"))
    ap.add_argument("--b", default=str(REPO / "harness" / "SYSTEM_v2.md"))
    ap.add_argument("--n", type=int, default=2, help="runs per task per variant")
    ap.add_argument("--skip-level4", action="store_true", help="deterministic tasks only (faster)")
    args = ap.parse_args()

    a, b = Path(args.a), Path(args.b)
    if not b.exists():
        sys.exit(f"{b} does not exist. Copy harness/SYSTEM.md to it and change one line first.")

    print(f"A = {a}\nB = {b}\n")
    results = {}
    for name, system in (("A", a), ("B", b)):
        print(f"\n######## variant {name}: level 3 ########")
        results[name] = {"l3": level3(system, args.n, f"ab-{name}")}
        if not args.skip_level4:
            print(f"\n######## variant {name}: level 4 ########")
            results[name]["l4"] = level4(system, args.n)

    print(f"\n\n{'':<22} {'A pass':>8} {'B pass':>8}   {'A tokens':>9} {'B tokens':>9}   {'A turns':>7} {'B turns':>7}")
    print("-" * 82)
    for task in results["A"]["l3"]:
        ra, rb = results["A"]["l3"][task], results["B"]["l3"][task]
        print(f"{task:<22} {ra['pass']:>4}/{ra['n']:<3} {rb['pass']:>4}/{rb['n']:<3}   "
              f"{ra['tokens'] // ra['n']:>9,} {rb['tokens'] // rb['n']:>9,}   "
              f"{ra['turns'] / ra['n']:>7.1f} {rb['turns'] / rb['n']:>7.1f}")
    if not args.skip_level4:
        print("-" * 82)
        for task in results["A"]["l4"]:
            ra, rb = results["A"]["l4"][task], results["B"]["l4"][task]
            print(f"{task + ' (judge)':<22} {ra['pass']:>4}/{ra['criteria']:<3} {rb['pass']:>4}/{rb['criteria']:<3}   "
                  f"{ra['tokens'] // ra['n']:>9,} {rb['tokens'] // rb['n']:>9,}   "
                  f"{ra['turns'] / ra['n']:>7.1f} {rb['turns'] / rb['n']:>7.1f}")

    (REPO / "level5_ab" / "last_run.json").write_text(json.dumps(results, indent=2))
    print("\nsaved to level5_ab/last_run.json")


if __name__ == "__main__":
    main()
