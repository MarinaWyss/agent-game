"""Level 4: calibrate the judge against a human.

You grade the same outputs the judge graded, against the same rubric, then compare.

    python level4_judge/calibrate.py grade              # you grade each output, p/f per criterion
    python level4_judge/calibrate.py compare            # you vs the judge, row by row

grade needs no API. compare reads results/human-*.json and results/grades-<label>.json.
Pass --name to grade as someone else on the same machine; compare shows every grader.

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


INTRO = """
You're about to grade {n} outputs, the same ones the judge graded.

For each one you'll see three things:
  1. what the agent was asked to do
  2. what the agent produced
  3. the rubric: a short list of criteria

Then you'll answer each criterion one at a time: p if the output passes it, f if it fails.
Go by what each criterion actually says, not what you think it was meant to say.
If you can't decide, that's worth noticing: it usually means the criterion is vague.
"""


def _ask(prompt: str) -> bool:
    while True:
        ans = input(prompt).strip().lower()
        if ans in ("p", "pass"):
            return True
        if ans in ("f", "fail"):
            return False
        print("    please type p (pass) or f (fail)")


def cmd_grade(args) -> None:
    data = json.loads(outputs_path(args.label).read_text())
    tasks = {t["name"]: t for t in load_tasks()}
    outputs = data["outputs"]
    print(INTRO.format(n=len(outputs)))
    input("Press Enter to start. ")
    verdicts = []
    for i, o in enumerate(outputs, 1):
        task = tasks[o["task"]]
        produced = "the README.md file it wrote" if task["output"].startswith("file:") else "its final reply"
        print(f"\n{'=' * 70}\nOUTPUT {i} OF {len(outputs)}: {o['task']} (run {o['run']})\n{'=' * 70}")
        print(f"\nWHAT THE AGENT WAS ASKED:\n  {task['prompt']}")
        print(f"\nWHAT IT PRODUCED ({produced}):")
        for line in o["output"].splitlines() or [""]:
            print(f"  | {line}")
        print(f"\nTHE RUBRIC ({len(task['criteria'])} criteria):")
        for ci, crit in enumerate(task["criteria"], 1):
            print(f"  {ci}. {describe(crit)}")
        print("\nNow grade the output against each criterion.")
        marks = []
        for ci, crit in enumerate(task["criteria"], 1):
            note = "\n    (code checks this one automatically; answer what you think)" if "[checked by code]" in describe(crit) else ""
            marks.append(_ask(f"\n  Criterion {ci} of {len(task['criteria'])}: {describe(crit)}{note}\n    pass or fail? [p/f] "))
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


def _regrade(name: str) -> str:
    return "calibrate.py grade" if name == "me" else f"calibrate.py grade --name {name}"


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
            print(f"skipping {d['name']}: they graded an older set of outputs. Re-run: {_regrade(d['name'])}")
            continue
        if d.get("criteria") != current_criteria:
            print(f"skipping {d['name']}: the rubric changed since they graded. Re-run: {_regrade(d['name'])}")
            continue
        humans[d["name"]] = {(v["task"], v["run"]): v["passes"] for v in d["verdicts"]}
    if not humans:
        sys.exit("no up-to-date human grades yet; run: calibrate.py grade")

    judge, judge_reasons = {}, {}
    jpath = RESULTS_DIR / f"grades-{args.label}.json"
    if jpath.exists() and jpath.stat().st_mtime < outputs_path(args.label).stat().st_mtime:
        print("skipping the judge: its grades are older than the outputs. Re-run: judge.py grade")
    elif jpath.exists():
        for g in json.loads(jpath.read_text()):
            first = g["grades"][0].get("grades") or []
            judge[(g["task"], g["run"])] = [x.get("pass") for x in first]
            judge_reasons[(g["task"], g["run"])] = [x.get("reason", "") for x in first]
        stale = [t for (t, _), marks in judge.items() if marks and len(marks) != len(current_criteria[t])]
        if stale:
            print("skipping the judge: the rubric changed since it graded. Re-run: judge.py grade")
            judge = {}
    graders = dict(humans)
    if judge:
        graders["judge"] = judge

    names = list(graders)
    keys = sorted(set().union(*[set(v) for v in graders.values()]))

    disagreements = []

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
            if disagree:
                disagreements.append((task, run, ci, crit, dict(zip(names, row))))

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

    if disagreements:
        print("\nwhere the graders disagreed:")
        for task, run, ci, crit, verdicts in disagreements:
            print(f"\n  {task} run {run}, criterion {ci + 1}: {describe(crit)}")
            print("    " + ", ".join(f"{n}: {v}" for n, v in verdicts.items()))
            reasons = judge_reasons.get((task, run))
            if "judge" in verdicts and reasons and ci < len(reasons):
                print(f"    judge's reason: {reasons[ci]}")
    else:
        print("\nno disagreements: every grader gave the same verdict on every criterion")

    print("\nhow to read it:")
    if len(humans) == 1:
        print("  you and the judge agree     -> the judge reads this criterion the way you do")
        print("  you and the judge disagree  -> read the judge's reason:")
        print("      it's a fair reading of the words  -> the criterion is ambiguous; rewrite it")
        print("      it misread or missed something    -> make the criterion more explicit, or fix the judge")
    else:
        print("  humans disagree with each other  -> the rubric is ambiguous; tighten the criterion")
        print("  humans agree, judge disagrees    -> the judge prompt or model needs work")
        print("  everyone agrees                  -> you can trust the judge on this criterion")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade")
    g.add_argument("--name", default="me", help="who is grading (default: me)")
    g.add_argument("--label", default="baseline")
    g.set_defaults(fn=cmd_grade)
    c = sub.add_parser("compare")
    c.add_argument("--label", default="baseline")
    c.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
