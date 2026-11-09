"""Level 4: calibrate the judge against a human.

You grade the same outputs the judge graded, against the same rubric, then compare.

    python level4_judge/calibrate.py grade --demo       # 5 questions, picked to be interesting
    python level4_judge/calibrate.py grade              # every criterion on every output
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
You're about to answer {n} questions about the same outputs the judge graded.

Each question shows you three things:
  1. what the agent was asked to do
  2. what the agent produced
  3. one criterion from the rubric

You answer p if the output passes that criterion, or f if it fails it.
Go by what the criterion actually says, not what you think it was meant to say.
If you can't decide, that's worth noticing: it usually means the criterion is vague.
"""

DEMO_NOTE = """
This is the short demo version: {n} questions out of {total}, picked to be the
interesting ones (anything the judge disagreed with itself on comes first). A real
calibration grades everything, ideally with several people grading independently,
so you can also measure how much the humans agree with each other.
"""


def _ask(prompt: str) -> bool:
    while True:
        ans = input(prompt).strip().lower()
        if ans in ("p", "pass"):
            return True
        if ans in ("f", "fail"):
            return False
        print("    please type p (pass) or f (fail)")


def _interesting(label: str) -> list[tuple[str, int, int]]:
    """(task, run, criterion index) worth a human look, most interesting first.

    1. the judge's two rounds disagreed (needs grade --twice)
    2. the judge gave different verdicts on different runs of the same task
    3. the judge failed it
    Returns nothing if there are no up-to-date judge grades.
    """
    path = RESULTS_DIR / f"grades-{label}.json"
    if not path.exists() or path.stat().st_mtime < outputs_path(label).stat().st_mtime:
        return []
    grades = json.loads(path.read_text())
    splits, varies, fails = [], [], []
    first: dict[tuple[str, int], list] = {}
    for g in grades:
        rounds = [[x.get("pass") for x in (r.get("grades") or [])] for r in g["grades"]]
        first[(g["task"], g["run"])] = rounds[0] if rounds else []
        if len(rounds) >= 2:
            for ci, (a, b) in enumerate(zip(rounds[0], rounds[1])):
                if a is not None and b is not None and a != b:
                    splits.append((g["task"], g["run"], ci))
    by_task: dict[str, list] = {}
    for (task, run), marks in first.items():
        by_task.setdefault(task, []).append((run, marks))
    for task, runs in by_task.items():
        for ci in range(max((len(m) for _, m in runs), default=0)):
            seen = {m[ci] for _, m in runs if ci < len(m) and m[ci] is not None}
            if len(seen) > 1:
                varies += [(task, run, ci) for run, m in sorted(runs) if ci < len(m)]
    for (task, run), marks in sorted(first.items()):
        fails += [(task, run, ci) for ci, v in enumerate(marks) if v is False]
    return splits + varies + fails


def pick_questions(outputs: list[dict], tasks: dict, label: str, demo: bool, k: int = 5) -> list[tuple[int, int]]:
    """(output index, criterion index) pairs to ask about.

    Full mode asks everything. Demo mode asks k questions: first the ones where the
    judge's verdicts look shaky or interesting (see _interesting), then one judgment
    criterion per task in turn. Code-checked criteria are skipped in demo mode, since
    there's nothing to calibrate about counting words.
    """
    index = {(o["task"], o["run"]): i for i, o in enumerate(outputs)}
    if not demo:
        return [(i, ci) for i, o in enumerate(outputs) for ci in range(len(tasks[o["task"]]["criteria"]))]

    def judged(task, ci):
        return "[checked by code]" not in describe(tasks[task]["criteria"][ci])

    chosen: list[tuple[int, int]] = []
    for task, run, ci in _interesting(label):
        if (task, run) in index and judged(task, ci):
            chosen.append((index[(task, run)], ci))
    first_run = min(o["run"] for o in outputs)
    longest = max(len(t["criteria"]) for t in tasks.values())
    for ci in range(longest):
        for name in tasks:
            if (name, first_run) in index and ci < len(tasks[name]["criteria"]) and judged(name, ci):
                chosen.append((index[(name, first_run)], ci))
    unique = list(dict.fromkeys(chosen))[:k]
    return sorted(unique)


def cmd_grade(args) -> None:
    data = json.loads(outputs_path(args.label).read_text())
    tasks = {t["name"]: t for t in load_tasks()}
    outputs = data["outputs"]
    questions = pick_questions(outputs, tasks, args.label, args.demo)
    total = sum(len(tasks[o["task"]]["criteria"]) for o in outputs)

    print(INTRO.format(n=len(questions)))
    if args.demo:
        print(DEMO_NOTE.format(n=len(questions), total=total))
    input("Press Enter to start. ")

    answers: dict[int, list] = {}
    shown = None
    for q, (i, ci) in enumerate(questions, 1):
        o = outputs[i]
        task = tasks[o["task"]]
        if shown != i:
            shown = i
            produced = "the README.md file it wrote" if task["output"].startswith("file:") else "its final reply"
            print(f"\n{'=' * 70}\n{o['task']} (run {o['run']})\n{'=' * 70}")
            print(f"\nWHAT THE AGENT WAS ASKED:\n  {task['prompt']}")
            print(f"\nWHAT IT PRODUCED ({produced}):")
            for line in o["output"].splitlines() or [""]:
                print(f"  | {line}")
        crit = describe(task["criteria"][ci])
        note = "\n    (code checks this one automatically; answer what you think)" if "[checked by code]" in crit else ""
        marks = answers.setdefault(i, [None] * len(task["criteria"]))
        marks[ci] = _ask(f"\n  QUESTION {q} OF {len(questions)}. Does the output above pass this criterion?\n"
                         f"    {crit}{note}\n    pass or fail? [p/f] ")

    verdicts = [{"task": outputs[i]["task"], "run": outputs[i]["run"], "passes": marks}
                for i, marks in sorted(answers.items())]
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"human-{args.name}.json"
    path.write_text(json.dumps({
        "name": args.name,
        "label": args.label,
        "demo": args.demo,
        "outputs_fingerprint": outputs_fingerprint(args.label),
        "criteria": {name: t["criteria"] for name, t in tasks.items()},
        "verdicts": verdicts,
    }, indent=2))
    print(f"\nsaved to {path}")
    print("next: python level4_judge/calibrate.py compare")


def _regrade(name: str) -> str:
    return "calibrate.py grade" if name == "me" else f"calibrate.py grade --name {name}"


def cmd_compare(args) -> None:
    tasks = {t["name"]: t for t in load_tasks()}
    current = outputs_fingerprint(args.label)
    current_criteria = {name: t["criteria"] for name, t in tasks.items()}
    humans, demo_graders = {}, []
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
        if d.get("demo"):
            demo_graders.append(d["name"])
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
            if all(row[names.index(h)] == "-" for h in humans):
                continue  # no human answered this one (demo mode), so there's nothing to compare
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

    if demo_graders:
        print(f"\nnote: {', '.join(demo_graders)} used --demo, so only those questions are compared. "
              "A real calibration grades everything, with several people if you can.")

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
    g.add_argument("--demo", action="store_true", help="answer 5 interesting questions instead of all of them")
    g.set_defaults(fn=cmd_grade)
    c = sub.add_parser("compare")
    c.add_argument("--label", default="baseline")
    c.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
