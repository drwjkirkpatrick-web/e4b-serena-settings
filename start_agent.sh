#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Serena + E4B Agent Bridge — Startup Script
# For running HTML game generation with local LLM + Serena MCP tools
# on Jetson 8GB with GUI off.
# ═══════════════════════════════════════════════════════════════════
set -e

PROJECT_DIR="${1:-$HOME/projects/crypt-shadowking-e4b}"
LOG_DIR="/tmp"

echo "=== Serena + E4B Agent Bridge Startup ==="
echo "Project: $PROJECT_DIR"
echo ""

# ─── 1. Stop GUI (frees ~1.8GB RAM) ──────────────────────────────
echo "[1/4] Stopping GUI..."
sudo systemctl stop gdm.service 2>/dev/null && echo "  GDM stopped" || echo "  GDM already stopped or not running"
free -h | head -2

# ─── 2. Verify / Start E4B llama-server ──────────────────────────
echo ""
echo "[2/4] Checking E4B llama-server on port 8091..."
if curl -s --max-time 5 http://127.0.0.1:8091/health | grep -q "ok"; then
    MODEL=$(curl -s http://127.0.0.1:8091/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)['models'][0]['model'])" 2>/dev/null)
    echo "  E4B already running: $MODEL"
else
    echo "  Starting E4B llama-server..."
    GGML_CUDA_ENABLE_UNIFIED_MEMORY=1 setsid $HOME/llama.cpp/build/bin/llama-server \
        -m $HOME/models/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf \
        --alias gemma-4-e4b-qat \
        --host 127.0.0.1 --port 8091 \
        -ngl 99 -c 32768 -ctk q4_0 -ctv q4_0 \
        -b 64 -ub 64 -fa on --jinja --fit off -np 1 \
        > /tmp/e4b_server.log 2>&1 &
    echo "  Waiting for server to load..."
    for i in $(seq 1 60); do
        if curl -s --max-time 5 http://127.0.0.1:8091/health | grep -q "ok"; then
            echo "  E4B server ready after ${i}s"
            break
        fi
        sleep 1
    done
fi

# ─── 3. Verify Python deps ───────────────────────────────────────
echo ""
echo "[3/4] Checking Python dependencies..."
python3 -c "import mcp; print('  mcp OK')" 2>/dev/null || { echo "  mcp MISSING — pip install mcp"; exit 1; }
python3 -c "import httpx; print('  httpx OK')" 2>/dev/null || { echo "  httpx MISSING — pip install httpx"; exit 1; }
which serena >/dev/null 2>&1 && echo "  serena OK ($(serena --version 2>&1))" || { echo "  serena MISSING — pip install serena-agent"; exit 1; }

# ─── 4. Launch Agent Bridge ──────────────────────────────────────
echo ""
echo "[4/4] Launching Serena + E4B agent bridge..."
echo "  Config:"
echo "    Model:      gemma-4-e4b-qat (4.0GB QAT)"
echo "    Port:       8091"
echo "    Max tokens: 12000 per turn"
echo "    Timeout:    4000s per LLM call"
echo "    Max turns:  30"
echo "    Temp:       0.6, top_p: 0.95"
echo ""
echo "  Log: $PROJECT_DIR/agent_log.json"
echo "  Stdout: /tmp/crypt_e4b_run.log"
echo ""

cd "$PROJECT_DIR"
setsid python3 serena_e4b_bridge.py > "$LOG_DIR/crypt_e4b_run.log" 2>&1 &
BRIDGE_PID=$!
echo "  Bridge PID: $BRIDGE_PID"
echo ""
echo "=== Agent running in background. Monitor with: ==="
echo "  tail -f $PROJECT_DIR/agent_log.json"
echo "  python3 -c \"import json; [print(f'[{d.get(\\\"type\\\")}] turn={d.get(\\\"turn\\\",\\\"?\\\")} {d.get(\\\"summary\\\",\\\"\\\")[:200]}') for line in open('$PROJECT_DIR/agent_log.json') for d in [json.loads(line)]]\""
echo ""
echo "  Kill with: kill $BRIDGE_PID"