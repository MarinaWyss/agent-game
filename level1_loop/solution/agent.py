"""Level 1 solution. Same file as ../agent.py with the loop filled in.

Use this if the live build stalls:
    python level1_loop/solution/agent.py "Run the tests and fix whatever fails."
"""
import subprocess
import sys
from pathlib import Path

import anthropic

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
from harness import AGENT_MODEL as MODEL  # noqa: E402  (also loads .env so the API key is found)

WORKSPACE = REPO / "workspace"

SYSTEM = "You are a coding agent in a small Python project. Use your tools to complete the task, then summarize what you did."

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
    if name == "read_file":
        return (WORKSPACE / args["path"]).read_text()
    if name == "write_file":
        (WORKSPACE / args["path"]).write_text(args["content"])
        return f"wrote {args['path']}"
    if name == "run_shell":
        p = subprocess.run(args["command"], shell=True, cwd=WORKSPACE, capture_output=True, text=True)
        return f"exit {p.returncode}\n{p.stdout}{p.stderr}"
    return f"unknown tool {name}"


def run_agent(task: str) -> None:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": task}]

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
        )
        # Append exactly what came back. Current models think before answering, and the
        # thinking blocks carry signatures the API needs to see again on the next request.
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text":
                print(f"\nagent: {block.text}")

        if response.stop_reason != "tool_use":
            return  # the model answered without asking for a tool: we're done

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  -> {block.name}({block.input})")
                output = run_tool(block.name, block.input)
                print(f"  <- {output[:200]}")
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})

        messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    run_agent(sys.argv[1] if len(sys.argv) > 1 else "Run the tests and fix whatever fails.")
