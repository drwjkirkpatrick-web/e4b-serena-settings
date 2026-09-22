# E4B + Serena Agent Bridge — Settings & Configuration

Optimized settings for running **Gemma 4 E4B QAT** (4.0GB GGUF) with **Serena MCP** tools on a **Jetson Orin Nano 8GB** for agentic HTML game generation.

## Hardware
- NVIDIA Jetson Orin Nano 8GB
- GUI off (`sudo systemctl stop gdm.service`) — frees ~1.8GB RAM
- Solar powered: 100W panel → Jackery → Jetson (net 11.30W)

## Model
- **Gemma 4 E4B QAT** — `gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf` (4.0GB)
- Quant: QAT UD-Q4_K_XL
- Context: 32K (`-c 32768`)
- KV cache: q4_0 (`-ctk q4_0 -ctv q4_0`)
- Function calling: confirmed working via llama.cpp OpenAI-compatible API

## E4B Server Launch

```bash
GGML_CUDA_ENABLE_UNIFIED_MEMORY=1 setsid ~/llama.cpp/build/bin/llama-server \
  -m ~/models/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf \
  --alias gemma-4-e4b-qat \
  --host 127.0.0.1 --port 8091 \
  -ngl 99 -c 32768 -ctk q4_0 -ctv q4_0 \
  -b 64 -ub 64 -fa on --jinja --fit off -np 1 \
  > /tmp/e4b_server.log 2>&1 &
```

Key flags:
- `GGML_CUDA_ENABLE_UNIFIED_MEMORY=1` — required for >4GB models on Jetson unified memory
- `--fit off` — required by new llama.cpp build (0b1bad1+)
- `--jinja` — proper chat template for function calling
- `-np 1` — single slot (all requests queue)

## Bridge Script Settings

| Setting | Value | Notes |
|---------|-------|-------|
| `LLM_BASE_URL` | `http://127.0.0.1:8091/v1` | E4B llama-server |
| `LLM_MODEL` | `gemma-4-e4b-qat` | Alias from `--alias` |
| `MAX_TOKENS` | 17000 | Per-turn generation + reasoning budget |
| `TEMPERATURE` | 0.6 | |
| `TOP_P` | 0.95 | |
| `MAX_TURNS` | 30 | Agent loop limit |
| `httpx timeout` | 4000.0s | Critical: default 600s kills E4B mid-generation |

### Why 4000s timeout?
E4B generates at ~30 tok/s. 17K tokens = ~567s generation. With reasoning overhead (E4B thinks before acting), turns take 600-1000s. Default httpx timeout (600s) kills the request mid-generation. 4000s gives 4x headroom.

### Why 17K max tokens?
- Prompt with 29 Serena tool definitions = ~13,688 tokens
- E4B reasoning_content = 500-2000 tokens
- Game code output = 8,000-12,000 tokens
- 17K gives enough room for reasoning + complete game in one turn

## Serena MCP Configuration

```yaml
# ~/.serena/serena_config.yml (relevant settings)
language_backend: LSP
gui_log_window: false
web_dashboard: true
tool_timeout: 240
```

### Context: Use DEFAULT (not `ide`)
- `--context ide` excludes: `create_text_file`, `read_file`, `list_dir`, `find_file`, `execute_shell_command`
- Default context exposes all 29 tools needed for agentic file editing

### MCP Server Connection (in bridge script)
```python
server_params = StdioServerParameters(
    command="/home/walker/.local/bin/serena",
    args=["start-mcp-server", "--project", PROJECT_DIR],  # NO --context ide
    env={"PATH": ..., "HOME": ..., "USER": ...},
)
```

## Gotchas

1. **MCP SDK snake_case**: `tool.input_schema`, NOT `tool.inputSchema`
2. **Serena `--context ide` excludes file tools** — use default context
3. **E4B function calling works** — produces structured `tool_calls` JSON, no text parsing
4. **E4B reasoning in `reasoning_content`** — separate from `content`, visible in API response
5. **httpx timeout 4000s** — default 600s kills long generations
6. **`setsid` for long runs** — terminal background wrapper times out at 420s
7. **Tool result truncation** — Serena `initial_instructions` returns ~15K chars; truncate >8K
8. **E4B may output code as text** — force `create_text_file` in prompt; add fallback extraction
9. **Single E4B slot (`-np 1`)** — concurrent requests queue; don't run multiple bridges at once
10. **GPU memory doesn't release** after killing llama-server on Jetson — reboot to restart

## System Prompt (for forcing tool use)

```
CRITICAL INSTRUCTIONS:
- You MUST use the create_text_file tool to write files. Do NOT output code as text.
- The create_text_file tool takes two arguments: relative_path (e.g. "index.html") and content (the full file text).
- When asked to create a game, call create_text_file with relative_path="index.html" and the complete HTML as content.
- After writing, use read_file to verify the file was created correctly.
```

## Verified Results

### Test 1: Counter App (simple, Sep 22 2026)
- 4 turns, 3 tool calls, 31,538 tokens, 217.4s
- 13/13 feature checks passed
- Tool sequence: list_dir → read_file → create_text_file → summary

### Test 2: Crypt of the Shadow King (dungeon crawler, Sep 22 2026)
- Prior Ornith 9B single-shot: **FAILED** (9,367 tok, 1013s, 5.52Wh)
- E4B + Serena 12K tokens: **PASSED 24/24** (18,040 tok, 950s, 995 lines, 38K chars)
- E4B + Serena 17K tokens: **PASSED** — used `create_text_file` directly (forced by prompt)
- Features: procedural dungeons, 3 enemy types, keys/doors, potions, chests, stairs, sword combat, Web Audio, CRT scanlines, localStorage, title/game-over/pause screens

## Files

- `serena_e4b_bridge.py` — the bridge script (connects E4B to Serena MCP)
- `start_agent.sh` — startup script (GUI stop, server check, dep verify, bridge launch)
- `game_prompt.txt` — the dungeon crawler prompt
- `system_prompt.txt` — the game-specific system prompt
- `agent_log.json` — structured per-event log of each agent run

## Quick Start

```bash
# 1. Stop GUI
sudo systemctl stop gdm.service

# 2. Start E4B server (if not already running)
GGML_CUDA_ENABLE_UNIFIED_MEMORY=1 setsid ~/llama.cpp/build/bin/llama-server \
  -m ~/models/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf \
  --alias gemma-4-e4b-qat --host 127.0.0.1 --port 8091 \
  -ngl 99 -c 32768 -ctk q4_0 -ctv q4_0 \
  -b 64 -ub 64 -fa on --jinja --fit off -np 1 \
  > /tmp/e4b_server.log 2>&1 &

# 3. Wait for server
for i in $(seq 1 60); do curl -s http://127.0.0.1:8091/health | grep -q ok && break; sleep 1; done

# 4. Run the agent bridge
cd ~/projects/crypt-shadowking-e4b
setsid python3 serena_e4b_bridge.py > /tmp/crypt_e4b_run.log 2>&1 &

# 5. Monitor
python3 -c "import json; [print(f'[{d.get(\"type\")}] turn={d.get(\"turn\",\"?\")} {d.get(\"summary\",\"\")[:200]}') for line in open('agent_log.json') for d in [json.loads(line)]]"
```