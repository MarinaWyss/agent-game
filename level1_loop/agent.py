"""Level 1: a coding agent in one file.

Three tools, one loop. The loop is left for you (well, for Claude Code) to fill in.

Run from the repo root:
    python level1_loop/agent.py "Run the tests and fix whatever fails."
"""
import subprocess
import sys
from pathlib import Path

import anthropic

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from harness import AGENT_MODEL as MODEL  # noqa: E402  (also loads .env so the API key is found)

WORKSPACE = REPO / "workspace"

SYSTEM = "You are a coding agent in a small Python project. Use your tools to complete the task, then summarize what you did."

# --- 1. The tools the model is allowed to ask for -------------------------------

TOOLS = [
    {"name": "read_file",
     "description": "Read a file. Path is relative to the project root.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file",
     "description": "Create or overwrite a file with the given content.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "run_shell",
     "description": "Run a shell command in the project root and return its output.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
]


def run_tool(name: str, args: dict) -> str:
    """Actually do the thing the model asked for. Returns text the model will read."""
    if name == "read_file":
        return (WORKSPACE / args["path"]).read_text()
    if name == "write_file":
        (WORKSPACE / args["path"]).write_text(args["content"])
        return f"wrote {args['path']}"
    if name == "run_shell":
        p = subprocess.run(args["command"], shell=True, cwd=WORKSPACE, capture_output=True, text=True)
        return f"exit {p.returncode}\n{p.stdout}{p.stderr}"
    return f"unknown tool {name}"


# --- 2. The loop -----------------------------------------------------------------

def run_agent(task: str) -> None:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": task}]

    # TODO: implement the agent loop.
    #
    # Repeat until the model stops asking for tools:
    #   1. call client.messages.create(model=MODEL, max_tokens=16000, system=SYSTEM,
    #      tools=TOOLS, messages=messages)
    #   2. append response.content to messages as the assistant's turn, EXACTLY as
    #      returned (it can contain thinking blocks the API needs back unmodified)
    #   3. print any text blocks so we can see what the agent is saying
    #   4. if response.stop_reason != "tool_use": the model is done (or hit a limit);
    #      print the final text and return
    #   5. for each block with block.type == "tool_use":
    #        - print the tool name and its input
    #        - call run_tool(block.name, block.input)
    #        - collect {"type": "tool_result", "tool_use_id": block.id, "content": <output>}
    #   6. append ALL the collected tool results to messages as ONE "user" turn
    #      (the model may call several tools at once; every tool_use needs its tool_result)
    #
    # That's it. That's the whole agent.
    raise NotImplementedError("fill in the loop")


if __name__ == "__main__":
    run_agent(sys.argv[1] if len(sys.argv) > 1 else "Run the tests and fix whatever fails.")
