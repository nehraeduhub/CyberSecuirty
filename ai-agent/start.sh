#!/usr/bin/env sh
# CyberSec AI Agent launcher (Linux / macOS)
cd "$(dirname "$0")" || exit 1
MODEL="${AGENT_MODEL:-dolphin-phi}"

PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "Python 3.8+ is required: https://www.python.org/downloads/"; exit 1; }

if command -v ollama >/dev/null 2>&1; then
  # Start the Ollama server if it isn't running yet
  if ! curl -s -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
    echo "[*] Starting Ollama..."; (ollama serve >/dev/null 2>&1 &); sleep 2
  fi
  # First run: download a small uncensored model
  if [ -z "$(ollama list 2>/dev/null | sed 1d)" ]; then
    echo "[*] No models found - downloading $MODEL (one-time)..."
    ollama pull "$MODEL"
  fi
else
  echo "[!] Ollama not found. Install it from https://ollama.com (or use LM Studio)."
  echo "    The log analyzer still works without AI."
fi

"$PY" -c "import reportlab" 2>/dev/null || \
  echo "[i] PDF reports need reportlab: sudo apt install python3-reportlab  (or: pip install reportlab)"

exec "$PY" agent.py "$@"
