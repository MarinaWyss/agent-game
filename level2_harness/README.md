# Level 2: The harness

**Goal:** name everything around the loop, and feel why each piece exists.

## What this is

The loop from level 1 moved into `harness/agent.py` and grew four things: a system prompt in a file, a turn cap, a permission gate on `run_shell`, and a transcript with token counts. Nothing about the loop changed. The harness is the box around it.

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

When it asks to run `pytest`, say **y**. When it asks a second time, say **n** and watch what the agent does with a denial.

Then show the cap:

```
python level2_harness/run.py --max-turns 2 "Run the tests and fix whatever fails."
```

Then open `harness/SYSTEM.md` and read it aloud. It's six lines. This file is your A/B lever in level 5.

## Talk about this while it runs

- **Permission gate.** The model asked, the harness said no, the model got a `DENIED` tool result (with `is_error: true`) and had to cope. That's how Claude Code's permission prompts work, and why `--dangerously-skip-permissions` is a harness flag: it's an alias for `--permission-mode bypassPermissions`, nothing to do with the model.
- **Turn cap.** Agents loop forever on tasks they can't finish. The cap is the cheapest safety feature there is. Claude Code has `--max-turns` and `--max-budget-usd` in print mode (`claude -p`); interactive sessions rely on you plus context limits.
- **System prompt.** The model's "personality" as a coding agent lives here, in the CLAUDE.md from level 0, and in the tool descriptions. Change the words, change the agent. There's no code path for "be careful."
- **Path sandbox** (`_safe_path` in `tools.py`). The model can't `read_file("../../.env")`. Ask your guest how they'd break out anyway. (Answer: `run_shell` with `cat ../../.env`. The sandbox is only as good as the weakest tool. Real harnesses sandbox the shell too.)
- **Transcript and tokens.** You can't evaluate what you don't record. Every eval in levels 3 to 5 reads the `Result` object this harness produces. The summary line shows input tokens, how many came from the prompt cache, output tokens (which include the model's thinking), and an estimated cost.
- **Prompt caching.** `cache_control={"type": "ephemeral"}` on the request caches the growing conversation prefix, so each turn re-reads the history at a fraction of the price. Point at the `from cache` number on turn 3 or 4. This is the answer to "doesn't resending everything get expensive."

## Keep in your pocket

If he asks "so what does Claude Code add on top of this?": subagents (the same loop, spawned by a tool call, with its own context), context compaction (summarize old turns when `messages` gets long), hooks (shell commands that run before or after a tool call), MCP (tool schemas loaded from other programs), permission rules per tool and per command pattern, and a lot of tool design. All of it is harness. The loop is the loop.

If he asks "why not just use the SDK's loop?": the SDK has one (Tool Runner), and the Agent SDK exposes Claude Code's whole harness as a library. Use those for real work. We wrote the loop once so nobody has to take it on faith. More in `FAQ.md`.
