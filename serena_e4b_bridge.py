#!/usr/bin/env python3
"""
Serena + E4B Agent Bridge
Connects a local Gemma 4 E4B LLM (via llama.cpp OpenAI-compatible API)
to Serena's MCP tools, running an agentic loop on an HTML coding task.
"""
import asyncio
import json
import os
import sys
import time
import subprocess
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ─── Config ──────────────────────────────────────────────────────
LLM_BASE_URL = "http://127.0.0.1:8091/v1"
LLM_MODEL = "gemma-4-e4b-qat"
MAX_TOKENS = 17000          # 17K per turn — per user request, large budget for full game gen
TEMPERATURE = 0.6
TOP_P = 0.95
MAX_TURNS = 30              # more turns for complex game generation
SERENA_BIN = "/home/walker/.local/bin/serena"
PROJECT_DIR = "/home/walker/projects/crypt-shadowking-e4b"
LOG_FILE = "/home/walker/projects/crypt-shadowking-e4b/agent_log.json"

# Load the game-specific system prompt
with open(os.path.join(os.path.dirname(__file__), "system_prompt.txt")) as f:
    GAME_SYSTEM_PROMPT = f.read()

SYSTEM_PROMPT = GAME_SYSTEM_PROMPT + "\n\n" + """\
You are a coding agent with access to Serena MCP tools for semantic code analysis and editing.

You are working on an HTML/JS project at: {project}

CRITICAL INSTRUCTIONS:
- You MUST use the create_text_file tool to write files. Do NOT output code as text.
- The create_text_file tool takes two arguments: relative_path (e.g. "index.html") and content (the full file text).
- When asked to create a game, call create_text_file with relative_path="index.html" and the complete HTML as content.
- After writing, use read_file to verify the file was created correctly.
- Think step by step about what tools to call.

Available Serena tools will be provided as function definitions. Call them by name.
""".format(project=PROJECT_DIR)


def log_event(event: dict):
    """Append to structured log file"""
    event["timestamp"] = time.time()
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")
    # Also print to stdout for live monitoring
    print(f"[{event.get('type','?')}] {event.get('summary','')}", flush=True)


async def get_serena_tools(session: ClientSession) -> list:
    """Discover Serena tools via MCP and convert to OpenAI function format"""
    result = await session.list_tools()
    tools = []
    for tool in result.tools:
        # Skip JetBrains tools (no IDE running) and dashboard tools
        if "jet_brains" in tool.name or tool.name == "open_dashboard":
            continue
        # Build JSON schema from input_schema (snake_case in MCP Python SDK)
        schema = tool.input_schema if tool.input_schema else {"type": "object", "properties": {}}
        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": (tool.description or "")[:800],  # truncate long descriptions
                "parameters": schema,
            }
        })
    return tools


async def call_serena_tool(session: ClientSession, tool_name: str, arguments: dict) -> str:
    """Call a Serena tool and return the text result"""
    result = await session.call_tool(tool_name, arguments=arguments)
    # Extract text content from result
    parts = []
    for content in result.content:
        if hasattr(content, "text"):
            parts.append(content.text)
        elif isinstance(content, str):
            parts.append(content)
    return "\n".join(parts) if parts else "(no output)"


def call_llm(messages: list, tools: list, turn: int) -> dict:
    """Call E4B via OpenAI-compatible API"""
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    with httpx.Client(timeout=4000.0) as client:  # 4000s timeout per user request
        resp = client.post(
            f"{LLM_BASE_URL}/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def run_agent(task_prompt: str):
    """Main agentic loop: E4B decides which Serena tools to call"""

    # Start Serena MCP server as subprocess via stdio
    server_params = StdioServerParameters(
        command=SERENA_BIN,
        args=["start-mcp-server", "--project", PROJECT_DIR],
        env={
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ["HOME"],
            "USER": os.environ.get("USER", "walker"),
        },
    )

    log_event({"type": "start", "summary": f"Agent starting with task: {task_prompt[:80]}..."})

    # Connect to Serena MCP server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write, sampling_callback=None) as session:
            await session.initialize()

            # Discover available tools
            tools = await get_serena_tools(session)
            tool_names = [t["function"]["name"] for t in tools]
            log_event({"type": "tools", "summary": f"Discovered {len(tools)} Serena tools", "tools": tool_names})

            # Build conversation
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task_prompt},
            ]

            total_tokens = 0
            total_tool_calls = 0
            start_time = time.time()

            for turn in range(1, MAX_TURNS + 1):
                log_event({"type": "llm_call", "summary": f"Turn {turn}: calling E4B ({len(messages)} messages)", "turn": turn})

                try:
                    response = call_llm(messages, tools, turn)
                except Exception as e:
                    log_event({"type": "error", "summary": f"LLM call failed: {e}", "turn": turn})
                    break

                choice = response["choices"][0]
                msg = choice["message"]
                usage = response.get("usage", {})
                turn_tokens = usage.get("total_tokens", 0)
                total_tokens += turn_tokens
                finish_reason = choice["finish_reason"]

                # Extract reasoning if present (Gemma 4 thinking mode)
                reasoning = msg.get("reasoning_content", "")
                if reasoning:
                    log_event({"type": "reasoning", "summary": f"Turn {turn} reasoning: {reasoning[:200]}...", "turn": turn, "reasoning_len": len(reasoning)})

                # Check for tool calls
                tool_calls = msg.get("tool_calls", [])
                content = msg.get("content", "")

                if content:
                    log_event({"type": "response", "summary": f"Turn {turn}: {content[:200]}", "turn": turn, "content": content})

                if tool_calls:
                    # Add assistant message with tool calls to conversation
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["function"]["name"],
                                    "arguments": tc["function"]["arguments"],
                                }
                            }
                            for tc in tool_calls
                        ],
                    })

                    # Execute each tool call via Serena MCP
                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError as e:
                            args = {}
                            log_event({"type": "tool_error", "summary": f"Bad JSON args: {e}", "tool": tool_name})

                        log_event({"type": "tool_call", "summary": f"Turn {turn}: calling {tool_name}({json.dumps(args)[:150]})", "turn": turn, "tool": tool_name, "args": args})
                        total_tool_calls += 1

                        try:
                            result_text = await call_serena_tool(session, tool_name, args)
                            # Truncate very long results to keep context manageable
                            if len(result_text) > 8000:
                                result_text = result_text[:4000] + "\n\n... [truncated, " + str(len(result_text)) + " chars total] ...\n\n" + result_text[-2000:]
                            log_event({"type": "tool_result", "summary": f"Turn {turn}: {tool_name} returned {len(result_text)} chars", "turn": turn, "tool": tool_name, "result_len": len(result_text), "result_preview": result_text[:300]})

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result_text,
                            })
                        except Exception as e:
                            log_event({"type": "tool_error", "summary": f"Turn {turn}: {tool_name} failed: {e}", "turn": turn, "tool": tool_name, "error": str(e)})
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": f"Error: {e}",
                            })

                elif finish_reason == "stop":
                    # No tool calls and model stopped — task complete
                    # Fallback: if content contains HTML, save it to index.html
                    if content and ("<!DOCTYPE" in content or "```html" in content):
                        # Extract HTML from markdown code block or raw
                        if "```html" in content:
                            html_start = content.index("```html") + 7
                            html_end = content.rindex("```")
                            html_content = content[html_start:html_end].strip()
                        elif "<!DOCTYPE" in content:
                            html_start = content.index("<!DOCTYPE")
                            html_content = content[html_start:].strip()
                        else:
                            html_content = content

                        # Save via Serena create_text_file
                        try:
                            result_text = await call_serena_tool(session, "create_text_file", {
                                "relative_path": "index.html",
                                "content": html_content
                            })
                            log_event({"type": "fallback_save", "summary": f"Saved HTML from content via create_text_file: {len(html_content)} chars", "turn": turn, "result": result_text})
                        except Exception as e:
                            # Direct file write as last resort
                            with open(os.path.join(PROJECT_DIR, "index.html"), "w") as f:
                                f.write(html_content)
                            log_event({"type": "fallback_save", "summary": f"Saved HTML from content directly: {len(html_content)} chars", "turn": turn})

                    log_event({"type": "complete", "summary": f"Agent finished at turn {turn}. Final answer: {content[:300]}", "turn": turn, "content": content})
                    break

                elif finish_reason == "length":
                    log_event({"type": "warning", "summary": f"Turn {turn}: hit max_tokens ({MAX_TOKENS}), continuing", "turn": turn})
                    # Add the partial response and continue
                    messages.append({"role": "assistant", "content": content or "(continued)"})

                else:
                    log_event({"type": "warning", "summary": f"Turn {turn}: unexpected finish_reason={finish_reason}", "turn": turn})
                    if content:
                        messages.append({"role": "assistant", "content": content})
                    else:
                        break

            elapsed = time.time() - start_time
            log_event({
                "type": "final",
                "summary": f"Done: {total_tool_calls} tool calls, {total_tokens} tokens, {elapsed:.1f}s",
                "total_turns": turn,
                "total_tool_calls": total_tool_calls,
                "total_tokens": total_tokens,
                "elapsed_seconds": elapsed,
                "tokens_per_second": total_tokens / elapsed if elapsed > 0 else 0,
            })
            return total_tool_calls, total_tokens, elapsed


if __name__ == "__main__":
    # Load the dungeon crawler game prompt
    prompt_file = os.path.join(os.path.dirname(__file__), "game_prompt.txt")
    if len(sys.argv) > 1:
        task = sys.argv[1]
    elif os.path.exists(prompt_file):
        with open(prompt_file) as f:
            task = f.read()
    else:
        task = "Create a complete HTML5 game. Output the full HTML file."

    print(f"=== Serena + E4B Agent — Crypt of the Shadow King ===")
    print(f"LLM: {LLM_MODEL} at {LLM_BASE_URL}")
    print(f"Project: {PROJECT_DIR}")
    print(f"Max tokens per turn: {MAX_TOKENS}")
    print(f"Max turns: {MAX_TURNS}")
    print(f"Task: {task[:100]}...")
    print(f"Log: {LOG_FILE}")
    print("=" * 60)

    # Clear previous log
    with open(LOG_FILE, "w") as f:
        pass

    result = asyncio.run(run_agent(task))
    print(f"\n=== RESULT: {result[0]} tool calls, {result[1]} tokens, {result[2]:.1f}s ===")