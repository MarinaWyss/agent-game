# Level 2: The harness

**Goal:** name everything around the loop, and feel why each piece is there.

## Why this level

The loop from level 1 works, but I wouldn't let it anywhere near a real codebase. It runs any command it's asked to, keeps going as long as the model keeps asking, and leaves no record of what happened. A **harness** is everything you put around the loop to fix that: what the model is told, what it's allowed to do, when it has to stop, and what gets written down.

Most of what makes Claude Code good is harness, not model. The same model in a worse harness is a worse agent.

**What to expect.** You run the agent twice. The first time, the harness stops before every shell command and asks `allow? [y/N]`. Say yes once, then say no, and watch what happens. The model gets a `DENIED` result and has to deal with it like any other result. Usually it explains that it couldn't check its fix and tells you how to check it yourself.

The second time, the turn limit is 2. The agent gets as far as reading the files and gets cut off before it changes anything, with `[stopped: max_turns]`.

Each run ends with a summary line: turns, tool calls, tokens (including how many came from the cache), seconds, and an estimated cost.

**Why it matters.** That summary line is what makes level 3 possible. A harness that records what happened is a harness you can measure.

## What this is

The loop from level 1 moved into `harness/agent.py` and picked up four things: a system prompt in a file, a turn cap, a permission gate on `run_shell`, and a transcript with token counts. The loop itself didn't change at all. The harness is the box around it.

```mermaid
flowchart TB
    subgraph H["Harness"]
        direction TB
        S["System prompt<br/>harness/SYSTEM.md"]
        TS["Tool schemas<br/>harness/tools.py"]
        subgraph LOOP["The loop (unchanged from level 1)"]
            direction LR
            M[Model] -->|tool_use| X[execute_tool]
            X -->|tool_result| M
        end
        G["Permission gate<br/>ask before run_shell"]
        C["Turn cap<br/>max_turns=15"]
        W["Workspace reset<br/>+ path sandbox"]
        O["Transcript + tokens<br/>Result object"]
    end
    S --> LOOP
    TS --> LOOP
    G -.-> X
    C -.-> LOOP
    W -.-> X
    LOOP --> O
```

## Type this

```
python level2_harness/run.py "Run the tests and fix whatever fails."
```

When it asks to run `pytest`, say **y**. When it asks a second time, say **n** and see what the agent does with a denial.

Then try the cap:

```
python level2_harness/run.py --max-turns 2 "Run the tests and fix whatever fails."
```

Then open `harness/SYSTEM.md` and read it. It's six lines. This file is the thing you'll change in level 5.

## What to notice

- **Permission gate.** The model asked, the harness said no, and the model got a `DENIED` tool result (with `is_error: true`) and had to cope. That's how Claude Code's permission prompts work too. It's also why `--dangerously-skip-permissions` is a harness flag: it's an alias for `--permission-mode bypassPermissions`, and it has nothing to do with the model.
- **Turn cap.** Agents will happily loop forever on a task they can't finish. The cap is the cheapest safety feature there is. Claude Code has `--max-turns` and `--max-budget-usd` in print mode (`claude -p`); interactive sessions rely on you plus context limits.
- **System prompt.** The model's "personality" as a coding agent lives here, in the CLAUDE.md from level 0, and in the tool descriptions. Change the words and you change the agent. There's no code path for "be careful."
- **Path sandbox** (`_safe_path` in `tools.py`). The model can't `read_file("../../.env")`. So how would you get around it anyway? `run_shell` with `cat ../../.env`. A sandbox is only as good as its weakest tool, which is why real harnesses sandbox the shell too.
- **Transcript and tokens.** You can't evaluate what you didn't record. Every eval in levels 3 to 5 reads the `Result` object this harness produces. The summary line shows input tokens, how many of those came from the prompt cache, output tokens (which include the model's thinking), and an estimated cost.
- **Prompt caching.** `cache_control={"type": "ephemeral"}` on the request caches the growing conversation, so each turn re-reads the history at a fraction of the price. Look at the `from cache` number on turn 3 or 4. That's the answer to "doesn't resending everything every turn get expensive?"

## Two questions that come up here

**"So what does Claude Code add on top of this?"** Subagents (the same loop, started by a tool call, with its own context), context compaction (summarizing old turns when `messages` gets long), hooks (shell commands that run before or after a tool call), MCP (tool schemas loaded from other programs), permission rules per tool and per command pattern, and a lot of tool design. All of it is harness. The loop is still the loop.

**"Why not just use the SDK's loop?"** You should, for real work. The SDK has one (Tool Runner), and the Agent SDK gives you Claude Code's whole harness as a library. We wrote the loop once here so nobody has to take it on faith. There's more on this in `FAQ.md`.
