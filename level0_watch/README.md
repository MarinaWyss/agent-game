# Level 0: Watch the loop

**Goal:** watch Claude Code do a task and name the four steps it repeats.

## Why start here

People call Claude Code "an agent," and that word gets used for a lot of things right now. So here's what I mean by it in this repo.

A **model** on its own is a text-in, text-out function. You send it a conversation, and it sends back the next message. It can't run your tests, open a file, or check whether its answer worked. A chatbot is a model plus a chat window: it answers, and then it waits for you.

An **agent** is a model plus a program that lets it act and see what happened. The program gives the model a list of tools ("you can run a shell command," "you can read a file"). When the model replies with "run `pytest`," the program runs `pytest` and sends the output back as the next message. Then it asks the model again, and keeps going until the model replies without asking for anything. The model does the deciding. The program does the doing, and it also decides what the model is allowed to do.

That program is a loop, and the loop is surprisingly small. Claude Code is that loop plus a _lot_ of careful engineering around it: well-designed tools, permission prompts, CLAUDE.md files, context management. Underneath all of that, it's the same four steps over and over.

So in this level you just watch. The task is small enough that you can follow every step and match it to the diagram below. In level 1 you build the same loop yourself in about 70 lines. Everything after that is about the box around the loop, and how to tell whether it's any good.

## What this is

Claude Code is a loop. It asks the model what to do, the model asks for a tool, Claude Code runs the tool and sends back the result, and the model decides again. It stops when the model answers without asking for a tool. Everything else (permissions, the CLAUDE.md file, context management) is scaffolding around that loop.

```mermaid
flowchart LR
    A[Your task +<br/>conversation so far] --> B[Model]
    B -->|"I want to call read_file(...)"| C[Run the tool]
    C -->|tool result| A
    B -->|"plain text, no tool call"| D[Done]
```

## Type this

**Start Claude Code from inside `workspace/`, not from the repo root.** This one matters. Claude Code reads `CLAUDE.md` from the folder it starts in and from that folder's parents, never from subfolders. If you start it in the repo root, it won't see `workspace/CLAUDE.md`. It'll see the whole workshop instead (READMEs, `_pristine/`, the level folders) and spend its first few turns figuring out what this repo is.

From the repo root:

```
source .venv/bin/activate
python -m harness.workspace
cd workspace
pwd          # should end in /agent-game/workspace
claude --verbose
```

Activating the venv first puts `pytest` on the path for Claude Code's shell. Resetting the workspace brings the failing test back, in case you already fixed it.

Then give it one task:

```
Run the tests and fix whatever fails.
```

`--verbose` shows the full tool calls and results instead of collapsing them. (Inside a session, **Ctrl+O** toggles the same view.) Claude Code may ask permission before it runs a shell command or edits a file; say yes. If you've set it to auto-approve, it won't ask, and that's fine too.

## What you should see

I set the task up so there's really only one sensible path. Expect something like this sequence of tool calls:

1. `Bash: python -m pytest -q` (one failure: `test_slugify_lowercases`)
2. `Read: test_utils.py`
3. `Read: utils.py`
4. `Edit: utils.py` (adds `.lower()`)
5. `Bash: python -m pytest -q` (all pass)
6. Final message, no tool call. The loop ends.

The details will vary. It might read both files at once, or make the edit with `sed` through `Bash` instead of `Edit`. The shape stays the same, though: run the tests, look, change, run the tests again, stop. Each numbered step is one trip around the diagram.

**If its first move is `ls` on a folder full of `level*` directories, or it reads the top-level `README.md`,** you started it in the repo root. Quit (`/exit`), `cd workspace`, and start again. (It's also a nice little preview of level 2: same model, same task, different context, different behavior.)

## How to read the transcript

The output mixes three kinds of lines. Once you can tell them apart, you can see the loop.

```
I'll run the test suite first to see what's failing.      <- the model talking

⏺ Bash(python -m pytest -q 2>&1 | tail -40)               <- the model ASKING for a tool
  .F..                                       [100%]       <- what Claude Code ran and sent back
  FAILED test_utils.py::test_slugify_lowercases ...
  1 failed, 3 passed in 0.02s

One failure: slugify doesn't lowercase. I'll look at       <- the model again, having read the result
the source and the tests.

⏺ Bash(ls && cat utils.py test_utils.py)                   <- next request: one more trip around the loop
```

- **A `⏺` line is a request, not an action.** The model can't run anything. Its reply contains a structured message that basically says "please call the `Bash` tool with this command." The `⏺` line is Claude Code showing you that request: the tool name, with the arguments in parentheses.
- **The indented text under a `⏺` line is the tool result.** Claude Code ran the command itself, captured the output, and added it to the conversation as the next message. That's the arrow from "Run the tool" back to the start of the diagram.
- **Plain sentences are the model's own text.** It writes one before each request because `workspace/CLAUDE.md` tells it to. Notice how each sentence reacts to the result just above it. It only decides what to do next after it has seen what happened.
- **The last message has no `⏺` line after it.** That's the "plain text, no tool call" exit. The model stopped asking, so the loop stopped.

So each `⏺` line plus its result is one trip around the diagram. Count them and you've counted the loop.

Between the request and the result, Claude Code decides whether to run the command at all. With default settings you see that as a permission prompt. With auto-approve on, it happens silently, because your settings already said yes before the model asked. Either way, the model only asked. Level 2 makes this gap visible on purpose: the harness stops and asks `allow? [y/N]` before every shell command.

## What to notice

- Every tool call is the model _asking_. Claude Code decides whether to run it, and that gap is where permissions live.
- `workspace/CLAUDE.md` told it to run the tests first and to say what it's doing before each step. Claude Code loads that file into the context at startup. It's the part of the system prompt you get to control, so open it and have a look. (Your own mini agent in level 1 won't load it automatically. Only Claude Code does that; the mini agent only sees it if it happens to `read_file` it. Keep that in mind when the mini agent edits a test in level 3.)
- What does the model need to know to make that second `pytest` call? The result of the edit. That's why results get fed back into the conversation: the conversation _is_ the agent's memory.

## If the run goes sideways

Reset with `python -m harness.workspace` from the repo root and try once more. If it does something weird, that's worth a look too. The loop is the same; the model just made a different choice. Then move on to level 1, where you build the loop yourself and it's fully under your control.

## Questions you might have

**So the model never actually executes anything?**
Right. The API returns a `tool_use` block, which is just a name and a JSON object of arguments. Your code (here, Claude Code) decides whether to run it and what to send back. Everything you'd call "safety" in a coding agent lives in that gap. The model only ever sees text going in and text coming out. [How tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)

**Is CLAUDE.md a system prompt?**
Functionally, yes. It's project-level instructions that Claude Code loads into the context at the start of a session, from the working directory and its parents. The real system prompt belongs to Claude Code and is much longer; CLAUDE.md is the part you control. [Memory](https://code.claude.com/docs/en/memory)

**Why did it edit the file with `sed` instead of the `Edit` tool?**
Because the model picks the tool, and `Bash` can do almost anything. Claude Code offers both, and the model usually reaches for `Edit`, but not always. It's the same loop either way: a request, a result, a decision about what to do next.

**Why did it run `git diff` and get confused when the output was empty?**
`workspace/` is gitignored, so git doesn't track it and the diff is always empty. The model noticed, checked the file directly, and moved on. That's the loop doing its job: it reacts to whatever the result actually says, including results it didn't expect.

**I have auto-approve on. How do I see the "asking" part?**
You won't see a prompt, because your settings already said yes. The request and the decision still happen; they just happen instantly. The `⏺` lines are your best view of the asking, and level 2 shows the decision step on purpose.
