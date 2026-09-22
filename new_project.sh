#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Scaffold a new E4B + Serena agent project from the settings repo.
# Usage: ./new_project.sh /path/to/new/project "Optional task prompt"
# ═══════════════════════════════════════════════════════════════════
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
NEW_DIR="${1:-$HOME/projects/new-serena-project}"
TASK_PROMPT="${2:-}"

echo "=== Scaffolding E4B + Serena Agent Project ==="
echo "  Target: $NEW_DIR"
echo ""

mkdir -p "$NEW_DIR"

# Copy template files
cp "$REPO_DIR/agent_bridge.py" "$NEW_DIR/"
cp "$REPO_DIR/agent_config.yaml" "$NEW_DIR/"
cp "$REPO_DIR/start_agent.sh" "$NEW_DIR/"

# Copy system_prompt.txt if it exists, or create a default one
if [ -f "$REPO_DIR/system_prompt.txt" ]; then
    cp "$REPO_DIR/system_prompt.txt" "$NEW_DIR/"
else
    cat > "$NEW_DIR/system_prompt.txt" << 'PROMPT'
You are an expert HTML5 game developer. You create complete, polished, single-file HTML5 games using only vanilla JavaScript and the Canvas API — no external libraries, no CDN links, no image files, no audio files. All graphics are drawn with canvas code. All sounds use the Web Audio API.

CRITICAL OUTPUT RULES:
- Output the COMPLETE HTML file from <!DOCTYPE html> to </html>
- Do NOT truncate. Do NOT use "..." or "// rest unchanged". Every line must be present.
- All code in ONE <script> block.
- Desktop: arrow keys/WASD to move, spacebar to attack. Mobile: touch.
PROMPT
fi

# Create game_prompt.txt if task provided, otherwise create placeholder
if [ -n "$TASK_PROMPT" ]; then
    echo "$TASK_PROMPT" > "$NEW_DIR/game_prompt.txt"
    echo "  Task prompt saved to game_prompt.txt"
else
    cat > "$NEW_DIR/game_prompt.txt" << 'PROMPT'
Create a complete HTML5 game. Output the full HTML file.
PROMPT
    echo "  Placeholder game_prompt.txt created (edit with your task)"
fi

# Create .gitignore
cat > "$NEW_DIR/.gitignore" << 'GITIGNORE'
agent_log.json
__pycache__/
*.pyc
.serena/
index.html
*.html
GITIGNORE

# Initialize git
cd "$NEW_DIR"
git init -b main 2>/dev/null || git init
git add -A
git commit -m "Initial scaffold from e4b-serena-settings" --allow-empty

echo ""
echo "=== Project scaffolded at: $NEW_DIR ==="
echo ""
echo "Files:"
ls -la "$NEW_DIR"
echo ""
echo "Next steps:"
echo "  1. Edit agent_config.yaml — adjust model, tokens, timeout as needed"
echo "  2. Edit game_prompt.txt — paste your game/task prompt"
echo "  3. Edit system_prompt.txt — customize for your task type"
echo "  4. Run: cd $NEW_DIR && setsid python3 agent_bridge.py > /tmp/run.log 2>&1 &"
echo "  5. Monitor: python3 -c \"import json;[print(f'[{d.get(\\\"type\\\")}] turn={d.get(\\\"turn\\\",\\\"?\\\")} {d.get(\\\"summary\\\",\\\"\\\")[:200]}') for l in open('agent_log.json') for d in [json.loads(l)]]\""
echo ""
echo "Or use the startup script:"
echo "  cd $NEW_DIR && ./start_agent.sh"