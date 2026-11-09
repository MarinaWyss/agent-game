"""The agent loop, plus the harness around it.

The loop itself is ~20 lines (look for LOOP below). Everything else in this file is
harness: the things that make the loop safe, bounded, and observable.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from . import AGENT_MODEL, REPO, WORKSPACE, estimate_cost
from .tools import TOOLS, ConfirmFn, always_allow, execute_tool

DEFAULT_SYSTEM = REPO / "harness" / "SYSTEM.md"

# Thinking is on by default for current models and its tokens count against max_tokens,
# so this has to be a lot bigger than the visible reply you expect.
MAX_TOKENS = 16000


@dataclass
class Result:
    final_text: str = ""
    stop_reason: str = ""           # end_turn, max_turns, max_tokens, refusal, ...
    turns: int = 0
    tool_calls: int = 0
    input_tokens: int = 0           # uncached input
    cache_read_tokens: int = 0      # input served from the prompt cache (cheap)
    cache_write_tokens: int = 0     # input written to the cache this run
    output_tokens: int = 0          # includes thinking tokens
    seconds: float = 0.0
    model: str = ""
    transcript: list = field(default_factory=list)  # what happened, in order

    @property
    def hit_max_turns(self) -> bool:
        return self.stop_reason == "max_turns"

    @property
    def total_input_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def cost_usd(self) -> float | None:
        return estimate_cost(self.model, self.input_tokens, self.output_tokens,
                             self.cache_read_tokens, self.cache_write_tokens)

    def summary(self) -> str:
        cost = f", ~${self.cost_usd:.3f}" if self.cost_usd is not None else ""
        cached = f" ({self.cache_read_tokens:,} from cache)" if self.cache_read_tokens else ""
        flag = "" if self.stop_reason == "end_turn" else f" [stopped: {self.stop_reason}]"
        return (f"{self.turns} turns, {self.tool_calls} tool calls, "
                f"{self.total_input_tokens:,} in{cached} / {self.output_tokens:,} out tokens, "
                f"{self.seconds:.0f}s{cost}{flag}")


def run_agent(
    task: str,
    system: str | Path = DEFAULT_SYSTEM,
    workspace: Path = WORKSPACE,
    max_turns: int = 15,
    confirm: ConfirmFn = always_allow,
    model: str = AGENT_MODEL,
    verbose: bool = True,
) -> Result:
    """Run the agent on one task until it stops calling tools or hits max_turns."""
    if isinstance(system, Path):
        system = system.read_text()

    # The SDK retries rate limits (429), overloads (529) and connection errors on its own.
    # 5 is generous so a live demo survives a busy API.
    client = anthropic.Anthropic(max_retries=5)
    messages = [{"role": "user", "content": task}]
    result = Result(model=model)
    log = _Logger(verbose, result.transcript)
    started = time.time()
    max_tokens = MAX_TOKENS

    # ---------------------------------------------------------------- LOOP
    for turn in range(1, max_turns + 1):                       # harness: turn cap
        result.turns = turn
        response = client.messages.create(                     # 1. ask the model
            model=model,
            max_tokens=max_tokens,
            system=system,                                     # harness: system prompt
            tools=TOOLS,                                       # harness: tool schemas
            messages=messages,
            cache_control={"type": "ephemeral"},               # harness: cache the growing prefix
        )
        _count_usage(result, response.usage)

        # Hit the output cap in the middle of a tool call? The call is incomplete.
        # Don't run it; ask again with more room. (Documented remedy.)
        if response.stop_reason == "max_tokens" and response.content and response.content[-1].type == "tool_use":
            if max_tokens < 64000:
                max_tokens *= 2
                log.note(turn, f"max_tokens hit mid tool call, retrying with {max_tokens}")
                continue

        # Append the response exactly as returned. It may contain thinking blocks with
        # signatures that the API requires back, unmodified, on the next request.
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text" and block.text.strip():
                log.text(turn, block.text)

        if response.stop_reason != "tool_use":                 # 2. no tool call -> done
            result.stop_reason = response.stop_reason          #    (end_turn, max_tokens, refusal)
            result.final_text = "".join(b.text for b in response.content if b.type == "text")
            break

        tool_results = []                                      # 3. run each tool (may be several)
        for block in response.content:
            if block.type == "tool_use":
                log.tool_call(turn, block.name, block.input)
                output = execute_tool(block.name, block.input, workspace, confirm)  # harness: permission gate inside
                result.tool_calls += 1
                log.tool_result(turn, output)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": output.startswith(("ERROR", "DENIED")),
                })

        messages.append({"role": "user", "content": tool_results})  # 4. feed results back, repeat
    else:
        result.stop_reason = "max_turns"
    # ---------------------------------------------------------------- END LOOP

    result.seconds = time.time() - started
    if verbose:
        print(f"\n== done: {result.summary()}")
    return result


def _count_usage(result: Result, usage) -> None:
    result.input_tokens += usage.input_tokens
    result.output_tokens += usage.output_tokens
    result.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
    result.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0


class _Logger:
    """Prints the transcript as it happens and keeps a copy on the Result."""

    def __init__(self, verbose: bool, sink: list):
        self.verbose, self.sink = verbose, sink

    def text(self, turn, text):
        self.sink.append({"turn": turn, "type": "text", "text": text})
        if self.verbose:
            print(f"\n[turn {turn}] agent: {text.strip()}")

    def tool_call(self, turn, name, args):
        self.sink.append({"turn": turn, "type": "tool_call", "name": name, "args": args})
        if self.verbose:
            shown = json.dumps(args)
            print(f"[turn {turn}] -> {name}({shown[:200]}{'...' if len(shown) > 200 else ''})")

    def tool_result(self, turn, output):
        self.sink.append({"turn": turn, "type": "tool_result", "output": output})
        if self.verbose:
            first = output.strip().splitlines()[0] if output.strip() else ""
            print(f"[turn {turn}] <- {first[:120]}")

    def note(self, turn, text):
        self.sink.append({"turn": turn, "type": "note", "text": text})
        if self.verbose:
            print(f"[turn {turn}] !! {text}")
