# Runbook

Just the steps: what to run, what to open, and what to change. No explanations. For what's happening and why, see each level's `README.md`.

Run everything from the repo root (the `agent-game` folder) unless a step says otherwise.

---

## Setup

```
git clone https://github.com/MarinaWyss/agent-game.git && cd agent-game
./setup.sh
```

**Change:** open `.env` and put your Anthropic API key after `ANTHROPIC_API_KEY=`.

```
source .venv/bin/activate
python -m harness.workspace
(cd workspace && python -m pytest -q)
```

You should see `1 failed, 3 passed`.

---

## Level 0: Watch the loop

```
python -m harness.workspace
cd workspace
pwd
claude --verbose
```

`pwd` should end in `/agent-game/workspace`.

**Type into Claude Code:**

```
Run the tests and fix whatever fails.
```

If it asks permission, say yes.

**Open:** `workspace/CLAUDE.md`

When it's done, type `/exit`, then go back to the repo root:

```
cd ..
```

---

## Level 1: Build the loop

**Open:** `level1_loop/agent.py` (scroll to the `TODO`)

```
python -m harness.workspace
claude
```

**Type into Claude Code:**

```
Fill in the TODO in level1_loop/agent.py. Follow the numbered steps in the comment exactly. Don't change anything else in the file.
```

When it's done, type `/exit`, then run your agent:

```
python level1_loop/agent.py "Run the tests and fix whatever fails."
```

If the build stalls, run the finished version instead:

```
python level1_loop/solution/agent.py "Run the tests and fix whatever fails."
```

---

## Level 2: The harness

Run these in your own terminal, not inside Claude Code.

```
python level2_harness/run.py "Run the tests and fix whatever fails."
```

At the first `allow? [y/N]`, type `y`. At the second, type `n`.

```
python level2_harness/run.py --max-turns 2 "Run the tests and fix whatever fails."
```

At `allow? [y/N]`, type `y`.

**Open:** `harness/SYSTEM.md`

---

## Level 3: Evals, the easy kind

```
python level3_evals/run_evals.py --n 3 --quiet
```

Wait for the table. Then list any failures:

```
python -c "import json,sys; d=json.load(open(sys.argv[1])); [print(r['task'], r['run'], r['reason']) for r in d['runs'] if not r['passed']]" "$(ls -t level3_evals/results/*-baseline.json | head -1)"
```

(No output means nothing failed.)

**Open:**
- `level3_evals/tasks/fix_failing_test/check.py`
- `level3_evals/tasks/add_parse_date/check.py`

---

## Level 4: Evals, the hard kind

**Change:** in each of these files, replace the line that starts with `- TODO:` with your own criterion. Keep the `- ` at the start of the line.
- `level4_judge/tasks/commit_message/rubric.md`
- `level4_judge/tasks/explain_trace/rubric.md`
- `level4_judge/tasks/write_readme/rubric.md`

```
python level4_judge/judge.py generate --n 2 --quiet
python level4_judge/judge.py grade --twice
```

```
python level4_judge/judge.py grade --numeric --twice
```

```
python level4_judge/judge.py pairwise
```

**Open:** `level4_judge/JUDGE_PROMPT.md`

Now grade 5 questions yourself. Press Enter to start, then type `p` (pass) or `f` (fail) for each one:

```
python level4_judge/calibrate.py grade --demo
```

```
python level4_judge/calibrate.py compare
```

---

## Level 5: Change one thing, measure everything

```
cp harness/SYSTEM.md harness/SYSTEM_v2.md
```

**Change:** open `harness/SYSTEM_v2.md` and add one line at the end. Pick one of these, or write your own:

```
Always run the existing tests before changing any code, and again after.
```

```
Never modify test files. If a test looks wrong, say so instead of changing it.
```

```
Before writing any file, explain your plan in one sentence.
```

```
Be concise. Keep any prose you write under 100 words.
```

```
python level5_ab/run_all.py --n 2
```

This is the longest run. For a shorter one, add `--skip-level4`.

**Open:** `level0_watch/README.md` (the first diagram)

---

## If something goes wrong

Reset the toy project:

```
python -m harness.workspace
```

`pytest: command not found`: activate the venv.

```
source .venv/bin/activate
```

---

## Reset everything afterwards

Puts the repo back the way it started, so the next run begins fresh:

```
git checkout level1_loop/agent.py level4_judge/tasks
rm -f harness/SYSTEM_v2.md
python -m harness.workspace
```
