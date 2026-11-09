"""Level 4: calibrate the judge against humans.

Two people grade the same outputs against the same rubric, independently. Then compare
them to each other and to the judge.

    python level4_judge/calibrate.py grade --name alice
    python level4_judge/calibrate.py grade --name bob
    python level4_judge/calibrate.py compare

grade shows you each output and asks p/f per criterion. No API needed.
compare reads results/human-*.json and results/grades-<label>.json.

Human grades only make sense against the exact outputs and rubric they were given, so
each human file records both, and compare leaves out any file that no longer matches.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from judge import RESULTS_DIR, describe, load_tasks, outputs_path  # noqa: E402


def outputs_fingerprint(label: str) -> str:
    """Short hash of the outputs file, so grades can be matched to the outputs they graded."""
    return hashlib.sha256(outputs_path(label).read_bytes()).hexdigest()[:12]


def cmd_grade(args) -> None:
    data = json.loads(outputs_path(args.label).read_text())
    tasks = {t["name"]: t for t in load_tasks()}
    verdicts = []
    for o in data["outputs"]:
        task = tasks[o["task"]]
        print(f"\n{'=' * 70}\n{o['task']}  run {o['run']}\n{'=' * 70}")
        print(f"TASK: {task['prompt']}\n")
        print(o["output"])
        print("\n" + "-" * 70)
        marks = []
        for crit in task["criteria"]:
            while True:
                ans = input(f"  {describe(crit)}\n    pass or fail? [p/f] ").strip().lower()
                if ans in ("p", "f"):
                    marks.append(ans == "p")
                    break
        verdicts.append({"task": o["task"], "run": o["run"], "passes": marks})
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"human-{args.name}.json"
    path.write_text(json.dumps({
        "name": args.name,
        "label": args.label,
        "outputs_fingerprint": outputs_fingerprint(args.label),
        "criteria": {name: t["criteria"] for name, t in tasks.items()},
        "verdicts": verdicts,
    }, indent=2))
    print(f"\nsaved to {path}")


def cmd_compare(args) -> None:
    tasks = {t["name"]: t for t in load_tasks()}
    current = outputs_fingerprint(args.label)
    current_criteria = {name: t["criteria"] for name, t in tasks.items()}
    humans = {}
    for p in sorted(RESULTS_DIR.glob("human-*.json")):
        d = json.loads(p.read_text())
        if d.get("label") != args.label:
            continue
        if d.get("outputs_fingerprint") != current:
            print(f"skipping {d['name']}: they graded an older set of outputs. "
                  f"Re-run: calibrate.py grade --name {d['name']}")
            continue
        if d.get("criteria") != current_criteria:
            print(f"skipping {d['name']}: the rubric changed since they graded. "
                  f"Re-run: calibrate.py grade --name {d['name']}")
            continue
        humans[d["name"]] = {(v["task"], v["run"]): v["passes"] for v in d["verdicts"]}
    if not humans:
        sys.exit("no up-to-date human grades yet; run: calibrate.py grade --name <you>")

    judge = {}
    jpath = RESULTS_DIR / f"grades-{args.label}.json"
    if jpath.exists() and jpath.stat().st_mtime < outputs_path(args.label).stat().st_mtime:
        print("skipping the judge: its grades are older than the outputs. Re-run: judge.py grade")
    elif jpath.exists():
        for g in json.loads(jpath.read_text()):
            first = g["grades"][0].get("grades") or []
            judge[(g["task"], g["run"])] = [x.get("pass") for x in first]
        stale = [t for (t, _), marks in judge.items() if marks and len(marks) != len(current_criteria[t])]
        if stale:
            print("skipping the judge: the rubric changed since it graded. Re-run: judge.py grade")
            judge = {}
    graders = dict(humans)
    if judge:
        graders["judge"] = judge

    names = list(graders)
    keys = sorted(set().union(*[set(v) for v in graders.values()]))

    # per-criterion rows
    print(f"\n{'task / criterion':<60} " + " ".join(f"{n[:8]:>8}" for n in names))
    print("-" * (62 + 9 * len(names)))
    for key in keys:
        task, run = key
        for ci, crit in enumerate(tasks[task]["criteria"]):
            row = []
            for n in names:
                marks = graders[n].get(key)
                v = marks[ci] if marks and ci < len(marks) else None
                row.append("pass" if v is True else "fail" if v is False else "-")
            label = f"{task} r{run}: {describe(crit)}"
            disagree = len(set(x for x in row if x != "-")) > 1
            print(f"{label[:60]:<60} " + " ".join(f"{x:>8}" for x in row) + ("  <--" if disagree else ""))

    # pairwise agreement
    print("\nagreement (share of criteria where both graders gave the same verdict):")
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            same = total = 0
            for key in keys:
                ma, mb = graders[a].get(key), graders[b].get(key)
                if not ma or not mb:
                    continue
                for x, y in zip(ma, mb):
                    if x is None or y is None:
                        continue
                    total += 1
                    same += x == y
            if total:
                print(f"  {a} vs {b}: {same}/{total} ({100 * same / total:.0f}%)")

    print("\nhow to read it:")
    print("  humans disagree with each other  -> the rubric is ambiguous; tighten the criterion")
    print("  humans agree, judge disagrees    -> the judge prompt or model needs work")
    print("  everyone agrees                  -> you can trust the judge on this criterion")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade")
    g.add_argument("--name", required=True)
    g.add_argument("--label", default="baseline")
    g.set_defaults(fn=cmd_grade)
    c = sub.add_parser("compare")
    c.add_argument("--label", default="baseline")
    c.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
