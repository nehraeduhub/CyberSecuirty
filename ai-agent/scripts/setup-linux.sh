#!/usr/bin/env bash
# One-shot setup of CyberSec AI Agent on a CPU-only Linux machine, tuned for speed.
#
#   ./scripts/setup-linux.sh                     # install + tune + download default model
#   ./scripts/setup-linux.sh --model qwen3:30b-a3b
#   ./scripts/setup-linux.sh --service           # also start the agent at boot
#   ./scripts/setup-linux.sh --host 0.0.0.0      # open the web UI to other computers (token login)
#
# Safe to run again: every step checks before it changes anything.
set -euo pipefail

MODEL="dolphin3"
INSTALL_SERVICE=0
AGENT_HOST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    --service) INSTALL_SERVICE=1; shift ;;
    --host) AGENT_HOST="$2"; shift 2 ;;
    -h|--help) sed -n 2,10p "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
RUN_USER="${SUDO_USER:-$(id -un)}"
say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

# Physical cores (not hyper-threads) give the best llama.cpp speed
CORES=$( (lscpu -p=Core,Socket 2>/dev/null || true) | grep -v "^#" | sort -u | wc -l || true)
[ "${CORES:-0}" -lt 1 ] && CORES=$(nproc)
RAM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
echo "CPU: $(nproc) threads / ${CORES} physical cores   RAM: ${RAM_GB} GB   Model: ${MODEL}"

say "1/6 Python and PDF library"
command -v python3 >/dev/null || { echo "Install python3 first"; exit 1; }
if ! python3 -c "import reportlab" 2>/dev/null; then
  if command -v apt-get >/dev/null; then $SUDO apt-get update -qq && $SUDO apt-get install -y -qq python3-reportlab
  elif command -v dnf >/dev/null; then $SUDO dnf install -y -q python3-reportlab
  else python3 -m pip install --user reportlab || python3 -m pip install --user --break-system-packages reportlab
  fi
fi
python3 -c "import reportlab; print('reportlab', reportlab.Version)"

say "2/6 Ollama"
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
ollama --version || true

say "3/6 Tune Ollama for CPU speed (systemd override)"
if [ -d /etc/systemd/system ] && systemctl list-unit-files ollama.service >/dev/null 2>&1; then
  $SUDO mkdir -p /etc/systemd/system/ollama.service.d
  $SUDO tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<EOF
[Service]
# Keep the model in RAM forever: loading from an HDD is the slowest step
Environment="OLLAMA_KEEP_ALIVE=-1"
# One request at a time gets all CPU cores (fastest single answer)
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
# Smaller, faster attention cache
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
# Only this machine may use the AI API
Environment="OLLAMA_HOST=127.0.0.1:11434"
EOF
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now ollama >/dev/null 2>&1 || true
  $SUDO systemctl restart ollama
else
  echo "systemd not found - start Ollama manually with: OLLAMA_KEEP_ALIVE=-1 OLLAMA_FLASH_ATTENTION=1 ollama serve &"
  (OLLAMA_KEEP_ALIVE=-1 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 nohup ollama serve >/dev/null 2>&1 &)
fi
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 1; done

# Keep the model out of swap; prefer RAM
if [ "$(cat /proc/sys/vm/swappiness)" -gt 10 ]; then
  echo "vm.swappiness = 10" | $SUDO tee /etc/sysctl.d/90-ai-agent.conf >/dev/null
  $SUDO sysctl -q -p /etc/sysctl.d/90-ai-agent.conf || true
fi
# Full CPU clock speed for inference (if the tool is installed)
if command -v cpupower >/dev/null; then $SUDO cpupower -q frequency-set -g performance >/dev/null 2>&1 || true; fi

say "4/6 Download model: ${MODEL} (one time; large download)"
ollama pull "$MODEL"

say "5/6 Agent settings (threads = ${CORES} physical cores)"
python3 - "$AGENT_DIR/config.json" "$MODEL" "$CORES" "$AGENT_HOST" <<'EOF'
import json, sys, os
path, model, cores, host = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
cfg = json.load(open(path)) if os.path.exists(path) else {}
cfg.update({"provider": "ollama", "base_url": "http://127.0.0.1:11434", "model": model,
            "num_thread": cores, "num_ctx": 4096, "num_predict": 1000, "keep_alive": "-1"})
cfg.setdefault("temperature", 0.2)
if host:
    cfg["host"] = host
json.dump(cfg, open(path, "w"), indent=2)
print("wrote", path)
EOF
[ -n "${SUDO_USER:-}" ] && chown "$SUDO_USER" "$AGENT_DIR/config.json" || true

echo "Pre-loading the model into RAM (first load from HDD can take a minute)..."
curl -s http://127.0.0.1:11434/api/generate \
  -d "{\"model\":\"$MODEL\",\"keep_alive\":-1,\"options\":{\"num_thread\":$CORES,\"num_ctx\":4096}}" >/dev/null || true

if [ "$INSTALL_SERVICE" = 1 ]; then
  say "6/6 Agent service (starts at boot, runs as ${RUN_USER})"
  $SUDO tee /etc/systemd/system/cybersec-agent.service >/dev/null <<EOF
[Unit]
Description=CyberSec AI Agent (web UI, see: python3 agent.py info)
After=network.target ollama.service
Wants=ollama.service

[Service]
User=${RUN_USER}
WorkingDirectory=${AGENT_DIR}
ExecStart=$(command -v python3) ${AGENT_DIR}/agent.py --no-browser
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now cybersec-agent
  echo "Agent running: http://127.0.0.1:8787"
else
  say "6/6 Done"
  echo "Start the agent:   cd ${AGENT_DIR} && python3 agent.py"
fi
echo "Measure speed:     python3 ${AGENT_DIR}/scripts/benchmark.py"
echo "Full host audit:   sudo python3 ${AGENT_DIR}/agent.py audit --pdf audit.pdf"
