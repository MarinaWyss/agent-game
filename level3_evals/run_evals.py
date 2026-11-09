"""Level 3: deterministic evals.

For each task in tasks/: reset the workspace, run the agent, run the task's check().
Do it N times per task because the agent is not deterministic. Print a table.

Run from the repo root:
    python level3_evals/run_evals.py                 # every task, 3 runs each
    python level3_evals/run_evals.py --n 1           # quick smoke run
    python level3_evals/run_evals.py --task fix_failing_test
    python level3_evals/run_evals.py --system harness/SYSTEM_v2.md --label v2
"""
import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import REPO, WORKSPACE  # noqa: E402
from harness.agent import run_agent  # noqa: E402
from harness.tools import always_allow  # noqa: E402
from harness.workspace import reset_workspace  # noqa: E402

TASKS_DIR = Path(__file__).resolve().parent / "tasks"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_check(task_dir: Path):
    spec = importlib.util.spec_from_file_location(f"check_{task_dir.name}", task_dir / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check


def run_one(task_dir: Path, system: Path, max_turns: int, verbose: bool) -> dict:
    prompt = (task_dir / "prompt.txt").read_text().strip()
    check = load_check(task_dir)

    reset_workspace()
    result = run_agent(prompt, system=system, max_turns=max_turns, confirm=always_allow, verbose=verbose)

    try:
        passed, reason = check(WORKSPACE)
    except Exception as e:  # a crashing grader is a failing grade, with the crash as the reason
        passed, reason = False, f"check crashed: {type(e).__name__}: {e}"

    return {
        "task": task_dir.name,
        "passed": passed,
        "reason": reason,
        "stop_reason": result.stop_reason,
        "turns": result.turns,
        "tool_calls": result.tool_calls,
        "input_tokens": result.total_input_tokens,
        "cache_read_tokens": result.cache_read_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "seconds": round(result.seconds, 1),
        "model": result.model,
        "final_text": result.final_text,
        "transcript": result.transcript,
    }


def wilson(passed: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a pass rate. Small n gives a wide interval, which is the point."""
    if n == 0:
        return 0.0, 0.0
    p = passed / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, center - half), min(1.0, center + half)


def run_suite(system: Path, n: int, max_turns: int, only: str | None, verbose: bool, label: str) -> dict:
    task_dirs = sorted(d for d in TASKS_DIR.iterdir() if d.is_dir() and not d.name.startswith("_"))
    if only:
        task_dirs = [d for d in task_dirs if d.name == only]
        if not task_dirs:
            sys.exit(f"no task named {only!r} in {TASKS_DIR}")

    runs = []
    for task_dir in task_dirs:
        for i in range(1, n + 1):
            print(f"\n{'=' * 70}\n{task_dir.name}  run {i}/{n}\n{'=' * 70}")
            r = run_one(task_dir, system, max_turns, verbose)
            r["run"] = i
            runs.append(r)
            mark = "PASS" if r["passed"] else "FAIL"
            print(f"\n>> {mark}: {r['reason']}")

    suite = {
        "label": label,
        "system_prompt": str(system),
        "system_prompt_text": system.read_text(),   # what was actually tested, not just the path
        "model": runs[0]["model"] if runs else None,
        "n": n,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "runs": runs,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{label}.json"
    out.write_text(json.dumps(suite, indent=2))
    suite["path"] = str(out)
    return suite


def print_table(suite: dict) -> None:
    runs = suite["runs"]
    tasks = sorted({r["task"] for r in runs})
    def cost(rs):
        cs = [r["cost_usd"] for r in rs if r.get("cost_usd") is not None]
        return f"${sum(cs) / len(cs):.3f}" if cs else "n/a"

    print(f"\n\n{'task':<20} {'pass':>7} {'95% CI':>12} {'avg turns':>10} {'avg tokens':>11} {'avg cost':>9} {'avg sec':>8}")
    print("-" * 84)
    for t in tasks:
        rs = [r for r in runs if r["task"] == t]
        passed = sum(r["passed"] for r in rs)
        lo, hi = wilson(passed, len(rs))
        avg_turns = sum(r["turns"] for r in rs) / len(rs)
        avg_tok = sum(r["input_tokens"] + r["output_tokens"] for r in rs) / len(rs)
        avg_sec = sum(r["seconds"] for r in rs) / len(rs)
        print(f"{t:<20} {passed:>3}/{len(rs):<3} {100 * lo:>5.0f}-{100 * hi:<3.0f}% {avg_turns:>10.1f} "
              f"{avg_tok:>11,.0f} {cost(rs):>9} {avg_sec:>8.0f}")
    total = sum(r["passed"] for r in runs)
    lo, hi = wilson(total, len(runs))
    print("-" * 84)
    print(f"{'overall':<20} {total:>3}/{len(runs):<3} {100 * lo:>5.0f}-{100 * hi:<3.0f}%   "
          f"({100 * total / len(runs):.0f}% observed; the interval is how sure you can be of that)")

    failures = [r for r in runs if not r["passed"]]
    if failures:
        print("\nfailures:")
        for r in failures:
            print(f"  {r['task']} run {r['run']}: {r['reason']}")
    print(f"\nfull transcripts saved to {suite['path']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="runs per task")
    ap.add_argument("--task", help="run only this task")
    ap.add_argument("--system", default=str(REPO / "harness" / "SYSTEM.md"))
    ap.add_argument("--max-turns", type=int, default=15)
    ap.add_argument("--label", default="baseline", help="name for this results file")
    ap.add_argument("--quiet", action="store_true", help="hide the live transcript")
    args = ap.parse_args()

    started = time.time()
    suite = run_suite(Path(args.system), args.n, args.max_turns, args.task, not args.quiet, args.label)
    print_table(suite)
    print(f"total wall time {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
