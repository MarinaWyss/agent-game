"""The three tools. This is all a coding agent needs to be dangerous.

Each tool is two things:
  1. A JSON schema the model sees (so it knows the tool exists and how to call it).
  2. A Python function that actually runs when the model calls it.

The model never runs anything. It emits a request; the harness decides whether to
honor it. That gap is where every safety feature of Claude Code lives.
"""
import subprocess
from pathlib import Path
from typing import Callable

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file in the project. Path is relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file in the project with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": "Run a shell command in the project root and return its output. Use for running tests, listing files, etc.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
]

# A confirm function takes the command string and returns True to allow it.
ConfirmFn = Callable[[str], bool]


def ask_in_terminal(command: str) -> bool:
    answer = input(f"\n  run_shell wants to run: {command}\n  allow? [y/N] ").strip().lower()
    return answer == "y"


def always_allow(command: str) -> bool:
    return True


def _safe_path(workspace: Path, relative: str) -> Path:
    """Refuse paths that escape the workspace. A tiny sandbox."""
    target = (workspace / relative).resolve()
    if workspace.resolve() not in target.parents and target != workspace.resolve():
        raise ValueError(f"path escapes workspace: {relative}")
    return target


def execute_tool(name: str, args: dict, workspace: Path, confirm: ConfirmFn) -> str:
    """Run one tool call and return its result as a string for the model."""
    try:
        if name == "read_file":
            return _safe_path(workspace, args["path"]).read_text()

        if name == "write_file":
            target = _safe_path(workspace, args["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args["content"])
            return f"wrote {len(args['content'])} bytes to {args['path']}"

        if name == "run_shell":
            if not confirm(args["command"]):
                return ("DENIED: the user did not allow this command. Do not retry it. "
                        "Either find another way or stop and explain what you needed it for.")
            proc = subprocess.run(
                args["command"], shell=True, cwd=workspace,
                capture_output=True, text=True, timeout=60,
            )
            out = (proc.stdout + proc.stderr).strip()
            return f"exit code {proc.returncode}\n{out[-4000:]}"

        return f"ERROR: unknown tool {name}"
    except Exception as e:  # the model should see errors, not crash the loop
        return f"ERROR: {type(e).__name__}: {e}"
