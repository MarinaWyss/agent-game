"""Level 4: evals for outputs you can't assert on.

Three commands, run from the repo root:

    python level4_judge/judge.py generate            # run the agent on each text task, save outputs
    python level4_judge/judge.py grade               # judge each output against its rubric, pass/fail per criterion
    python level4_judge/judge.py grade --twice       # judge twice, show which criteria flipped
    python level4_judge/judge.py grade --numeric     # ask for a 1-10 score instead; run with --twice to see it drift
    python level4_judge/judge.py pairwise            # compare two outputs per task, both orders, catch position bias

generate needs the API for the agent; grade and pairwise need it for the judge.
Outputs and grades are saved under results/ so you can re-grade without re-generating.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402

from harness import JUDGE_MODEL, REPO, WORKSPACE  # noqa: E402
from harness.agent import run_agent  # noqa: E402
from harness.tools import always_allow  # noqa: E402
from harness.workspace import reset_workspace  # noqa: E402

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "tasks"
RESULTS_DIR = HERE / "results"
JUDGE_PROMPT = (HERE / "JUDGE_PROMPT.md").read_text()


# ----------------------------------------------------------------- task loading

def load_tasks() -> list[dict]:
    tasks = []
    for d in sorted(p for p in TASKS_DIR.iterdir() if p.is_dir()):
        meta = json.loads((d / "task.json").read_text())
        tasks.append({
            "name": d.name,
            "prompt": (d / "prompt.txt").read_text().strip(),
            "output": meta["output"],
            "criteria": load_rubric(d / "rubric.md"),
        })
    return tasks


def load_rubric(path: Path) -> list[str]:
    criteria = []
    for line in path.read_text().splitlines():
        if line.startswith("- ") and "TODO" not in line:
            criteria.append(line[2:].strip())
    return criteria


# Criteria a model shouldn't be trusted with. Anything that is a count or a measurement
# gets checked by code; the judge only sees the criteria that need judgment.
CODE_CRITERIA = {
    "max_words": lambda output, n: (len(output.split()) <= int(n), f"{len(output.split())} words"),
    "max_lines": lambda output, n: (len(output.strip().splitlines()) <= int(n), f"{len(output.strip().splitlines())} lines"),
}


def split_criteria(criteria: list[str]) -> tuple[list[tuple[int, str, str]], list[tuple[int, str]]]:
    """Return (code criteria as (index, name, arg), judge criteria as (index, text))."""
    code, judged = [], []
    for i, c in enumerate(criteria):
        m = re.fullmatch(r"(\w+):\s*(\S+)", c)
        if m and m.group(1) in CODE_CRITERIA:
            code.append((i, m.group(1), m.group(2)))
        else:
            judged.append((i, c))
    return code, judged


def describe(criterion: str) -> str:
    m = re.fullmatch(r"(\w+):\s*(\S+)", criterion)
    if m and m.group(1) in CODE_CRITERIA:
        return f"{m.group(1).replace('_', ' ')} {m.group(2)}  [checked by code]"
    return criterion


def outputs_path(label: str) -> Path:
    return RESULTS_DIR / f"outputs-{label}.json"


# ----------------------------------------------------------------- generate

def cmd_generate(args) -> None:
    system = Path(args.system)
    tasks = load_tasks()
    if args.task:
        tasks = [t for t in tasks if t["name"] == args.task]
    outputs = []
    for t in tasks:
        for i in range(1, args.n + 1):
            print(f"\n{'=' * 70}\n{t['name']}  run {i}/{args.n}\n{'=' * 70}")
            reset_workspace()
            result = run_agent(t["prompt"], system=system, confirm=always_allow, verbose=not args.quiet)
            text = extract_output(t["output"], result.final_text)
            outputs.append({"task": t["name"], "run": i, "output": text, "stop_reason": result.stop_reason,
                            "turns": result.turns, "tokens": result.total_input_tokens + result.output_tokens,
                            "cost_usd": result.cost_usd, "model": result.model})
            print(f"\n--- output ({len(text.split())} words) ---\n{text[:1200]}{'...' if len(text) > 1200 else ''}")
    RESULTS_DIR.mkdir(exist_ok=True)
    path = outputs_path(args.label)
    path.write_text(json.dumps({"label": args.label, "system_prompt": str(system),
                                "system_prompt_text": system.read_text(), "outputs": outputs}, indent=2))
    print(f"\nsaved {len(outputs)} outputs to {path}")


def extract_output(spec: str, final_text: str) -> str:
    if spec == "final_message":
        return final_text.strip()
    if spec.startswith("file:"):
        f = WORKSPACE / spec[5:]
        return f.read_text().strip() if f.exists() else f"<{spec[5:]} was not created>"
    raise ValueError(f"unknown output spec {spec}")


# ----------------------------------------------------------------- grade

NUMERIC_INSTRUCTIONS = (
    "Give ONE overall score from 1 to 10 for how well the output meets the rubric as a whole. "
    'Reply with JSON only: {"score": <int 1-10>, "reason": "<one sentence>"}'
)


def build_judge_prompt(task: dict, judged: list[tuple[int, str]], output: str, numeric: bool) -> str:
    rubric = "\n".join(f"- {c}" for _, c in judged)
    prompt = JUDGE_PROMPT.replace("{task}", task["prompt"]).replace("{rubric}", rubric).replace("{output}", output)
    if numeric:
        # swap the pass/fail instructions (from "Reply with JSON" to "in the order given.") for a 1-10 score
        prompt = re.sub(r"Reply with JSON only.*?in the order given\.", NUMERIC_INSTRUCTIONS, prompt, flags=re.S)
    return prompt


def judge_one(client, task: dict, output: str, numeric: bool) -> dict:
    """Grade one output. Code criteria are checked here; the rest go to the judge model.

    Returns {"grades": [...one per criterion, in rubric order...]} or {"score", "reason"} when numeric.
    """
    code, judged = split_criteria(task["criteria"])
    prompt = build_judge_prompt(task, judged, output, numeric)
    # Thinking is on by default for the judge too and counts against max_tokens.
    resp = client.messages.create(model=JUDGE_MODEL, max_tokens=8000, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in resp.content if b.type == "text")
    parsed = parse_json(text)
    if numeric or "error" in parsed:
        return parsed

    # Merge model grades and code grades back into rubric order.
    model_grades = parsed.get("grades") or []
    merged: list = [None] * len(task["criteria"])
    for (i, _), g in zip(judged, model_grades):
        merged[i] = g
    for i, name, arg in code:
        ok, detail = CODE_CRITERIA[name](output, arg)
        merged[i] = {"criterion": task["criteria"][i], "pass": ok, "reason": f"{detail} (checked by code)"}
    return {"grades": [g if g else {"criterion": task["criteria"][i], "pass": None, "reason": "judge returned no grade"}
                       for i, g in enumerate(merged)]}


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"error": f"judge did not return JSON: {text[:200]}"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"error": f"bad JSON from judge: {e}"}


def cmd_grade(args) -> None:
    data = json.loads(outputs_path(args.label).read_text())
    tasks = {t["name"]: t for t in load_tasks()}
    client = anthropic.Anthropic()
    rounds = 2 if args.twice else 1
    all_grades = []

    for o in data["outputs"]:
        task = tasks[o["task"]]
        print(f"\n{'=' * 70}\n{o['task']}  run {o['run']}\n{'=' * 70}")
        results = [judge_one(client, task, o["output"], args.numeric) for _ in range(rounds)]
        all_grades.append({"task": o["task"], "run": o["run"], "grades": results})

        if args.numeric:
            scores = [r.get("score") for r in results]
            print(f"  score{'s' if rounds > 1 else ''}: {scores}" + ("   <-- drifted" if len(set(scores)) > 1 else ""))
            for r in results:
                print(f"    {r.get('reason', r.get('error'))}")
            continue

        if any("error" in r for r in results):
            for r in results:
                if "error" in r:
                    print(f"  judge error: {r['error']}")
            continue

        for ci, crit in enumerate(task["criteria"]):
            verdicts = [r["grades"][ci]["pass"] for r in results]
            known = [v for v in verdicts if v is not None]
            if not known:
                mark = "N/A"
            elif all(known):
                mark = "PASS"
            elif not any(known):
                mark = "FAIL"
            else:
                mark = "SPLIT"
            flag = "   <-- judge disagreed with itself" if len(set(known)) > 1 else ""
            print(f"  [{mark}] {describe(crit)}{flag}")
            for r in results:
                g = r["grades"][ci]
                verdict = "pass" if g["pass"] else "fail" if g["pass"] is False else "n/a"
                print(f"         {verdict}: {g['reason']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"grades-{args.label}{'-numeric' if args.numeric else ''}.json"
    path.write_text(json.dumps(all_grades, indent=2))
    print(f"\nsaved grades to {path}")
    if not args.numeric:
        print_pass_rate(all_grades, tasks)


def print_pass_rate(all_grades: list[dict], tasks: dict) -> None:
    print(f"\n{'task':<18} {'criteria passed':>16}")
    print("-" * 36)
    total = passed = 0
    for g in all_grades:
        first = (g["grades"][0].get("grades") or [])
        n = len(tasks[g["task"]]["criteria"])
        p = sum(1 for x in first if x.get("pass") is True)
        total += n
        passed += p
        print(f"{g['task'] + ' r' + str(g['run']):<18} {p:>7}/{n:<7}")
    print("-" * 36)
    if total:
        print(f"{'overall':<18} {passed:>7}/{total:<7} ({100 * passed / total:.0f}%)")


# ----------------------------------------------------------------- pairwise

PAIRWISE_PROMPT = """You are comparing two outputs from a coding agent for the same task.

Task: {task}

Rubric:
{rubric}

Output A:
<a>
{a}
</a>

Output B:
<b>
{b}
</b>

Which output better satisfies the rubric overall? Reply with JSON only: {{"winner": "A" or "B", "reason": "<one sentence>"}}
"""


def cmd_pairwise(args) -> None:
    data = json.loads(outputs_path(args.label).read_text())
    tasks = {t["name"]: t for t in load_tasks()}
    client = anthropic.Anthropic()
    by_task: dict[str, list] = {}
    for o in data["outputs"]:
        by_task.setdefault(o["task"], []).append(o)

    flips = 0
    for name, outs in by_task.items():
        if len(outs) < 2:
            print(f"{name}: need at least 2 outputs (run generate --n 2)")
            continue
        task = tasks[name]
        rubric = "\n".join(f"- {c}" for c in task["criteria"])
        a, b = outs[0]["output"], outs[1]["output"]

        ab = ask(client, PAIRWISE_PROMPT.format(task=task["prompt"], rubric=rubric, a=a, b=b))
        ba = ask(client, PAIRWISE_PROMPT.format(task=task["prompt"], rubric=rubric, a=b, b=a))
        # In the second call, "A" is really run 2. Translate back to run numbers.
        first = "run 1" if ab.get("winner") == "A" else "run 2"
        second = "run 2" if ba.get("winner") == "A" else "run 1"
        consistent = first == second
        flips += not consistent
        print(f"\n{name}")
        print(f"  order (1,2): prefers {first:<6} {ab.get('reason', ab.get('error', ''))}")
        print(f"  order (2,1): prefers {second:<6} {ba.get('reason', ba.get('error', ''))}")
        print(f"  {'consistent' if consistent else 'FLIPPED: the judge preferred whichever came ' + ('first' if ab.get('winner') == 'A' else 'second')}")
    print(f"\n{flips} of {len(by_task)} comparisons flipped when the order was swapped")


def ask(client, prompt: str) -> dict:
    resp = client.messages.create(model=JUDGE_MODEL, max_tokens=8000, messages=[{"role": "user", "content": prompt}])
    return parse_json("".join(b.text for b in resp.content if b.type == "text"))


# ----------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--n", type=int, default=1)
    g.add_argument("--task")
    g.add_argument("--system", default=str(REPO / "harness" / "SYSTEM.md"))
    g.add_argument("--label", default="baseline")
    g.add_argument("--quiet", action="store_true")
    g.set_defaults(fn=cmd_generate)

    r = sub.add_parser("grade")
    r.add_argument("--label", default="baseline")
    r.add_argument("--twice", action="store_true")
    r.add_argument("--numeric", action="store_true")
    r.set_defaults(fn=cmd_grade)

    p = sub.add_parser("pairwise")
    p.add_argument("--label", default="baseline")
    p.set_defaults(fn=cmd_pairwise)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
