# 🛡️ CyberSec AI Agent

A **portable, lightweight, fully offline** AI cybersecurity agent with a web UI.
It analyzes security logs, detects suspicious activity, and writes incident
reports using an **uncensored open-source AI model running on your own machine**.
Your logs are never sent to the cloud.

| ✅ | Feature |
|---|---|
| 🖥️ | Runs a local, uncensored AI (Ollama, LM Studio, llama.cpp, KoboldCpp, Jan…) |
| 🦙 | Works with any open-source model: Dolphin, Llama, Qwen, Mistral, Phi… |
| ⚙️ | Talks to the local AI's API server (Ollama or OpenAI-compatible) |
| 🐍 | **Pure Python, zero dependencies**: no `pip install`, nothing to build |
| 📄 | Analyzes Linux auth/syslog, Apache/Nginx, UFW/iptables, Windows events, shell history |
| 🛡️ | Detects ~30 attack patterns instantly (brute force, SQLi, Log4Shell, reverse shells, mimikatz…) mapped to MITRE ATT&CK |
| 💡 | AI investigation + one-click Markdown incident reports |
| 💬 | Chat with the agent: exploits, hardening, Sigma/Splunk rules, firewall commands, CTFs |

**Why it's fast:** a built-in rule engine scans about 30,000 log lines per second with
no AI at all. The AI only receives a compact summary of the findings, not the
whole log, so even small models on a laptop CPU reply quickly.

---

## 🚀 Quick start (3 steps)

**1. Install a local AI server**: [Ollama](https://ollama.com/download) (recommended)

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh
# macOS / Windows: download the installer from https://ollama.com/download
```

**2. Download an uncensored model** (one time)

```bash
ollama pull dolphin-phi        # 1.6 GB, fastest, runs on any laptop CPU
```

**3. Start the agent**

```bash
git clone https://github.com/nehraeduhub/CyberSecuirty.git
cd CyberSecuirty/ai-agent
./start.sh          # Linux / macOS
start.bat           # Windows (double-click)
# or simply:  python agent.py
```

Your browser opens **http://127.0.0.1:8787**. Click a sample log (for example `auth.log`),
press **⚡ Analyze**, then **🤖 AI Investigate**.

> The start scripts launch Ollama for you and download `dolphin-phi` on first run if
> you have no models. Use a different model with `AGENT_MODEL=dolphin3 ./start.sh`.

Only **Python 3.8+** is required. It's preinstalled on Linux and macOS; on Windows get it
from [python.org](https://www.python.org/downloads/) and tick "Add to PATH".

---

## 🦙 Recommended models

| Model | Size | RAM | Notes |
|---|---|---|---|
| `dolphin-phi` | 2.7B | ~3 GB | Uncensored, **fastest**, good on CPU-only machines |
| `dolphin-mistral` | 7B | ~6 GB | Uncensored, better reasoning |
| `dolphin3` | 8B | ~6 GB | Uncensored (Llama 3.1 based), **best quality/speed balance** |
| `llama2-uncensored` | 7B | ~6 GB | Classic uncensored model |
| `qwen2.5:3b` / `llama3.2:3b` | 3B | ~3 GB | Not uncensored, but fast and strong at analysis |

Switch models any time from the drop-down in the top bar. Everything you've pulled
with `ollama pull` appears there automatically.

## 🔌 Using LM Studio, llama.cpp, KoboldCpp, Jan, vLLM…

Any OpenAI-compatible server works. Open **⚙️ Settings** in the UI → Provider
**OpenAI-compatible**, then set the URL:

| Server | URL |
|---|---|
| LM Studio | `http://127.0.0.1:1234/v1` (enable "Local Server") |
| llama.cpp `llama-server` | `http://127.0.0.1:8080/v1` |
| KoboldCpp | `http://127.0.0.1:5001/v1` |
| Jan | `http://127.0.0.1:1337/v1` |

Settings are saved to `config.json`. You can also use environment variables:
`AGENT_PROVIDER`, `AGENT_BASE_URL`, `AGENT_MODEL`, `AGENT_API_KEY`, `AGENT_HOST`, `AGENT_PORT`.

---

## 💻 Command-line mode

```bash
python agent.py scan /var/log/auth.log          # instant rule-based scan
python agent.py scan access.log --ai            # + AI-written assessment
python agent.py scan access.log --json > out.json
python agent.py --port 9000 --model dolphin3 --no-browser
```

## 🔍 What it detects

| Category | Examples |
|---|---|
| Brute force | SSH/Windows password guessing, **successful login after brute force** (likely compromise), invalid users |
| Web attacks | SQL injection, XSS, path traversal, command injection, Log4Shell, scanners (sqlmap, nikto, gobuster…), `.env`/`.git` probes, directory enumeration |
| Network | Port scans from firewall logs |
| Post-exploitation | `curl \| bash`, reverse shells, encoded PowerShell, mimikatz/LSASS dumping, crypto miners, binaries in `/tmp` |
| Persistence & privilege | New accounts, admin group changes, cron/scheduled tasks, `authorized_keys`, unauthorized sudo |
| Anti-forensics | Log deletion, `history -c`, Windows audit log cleared (1102) |

Rules live in [`detector.py`](detector.py) as plain regexes, so it's easy to add your own.

## 🎒 Make it fully portable (USB stick)

1. Copy the `ai-agent` folder to the USB drive.
2. Store the models on the drive too: set `OLLAMA_MODELS=/path/to/usb/models`
   (Windows: `set OLLAMA_MODELS=E:\models`) before `ollama serve` / `ollama pull`.
3. On any machine with Python and Ollama, run `start.sh` / `start.bat` from the drive.

## 🔒 Security notes

- The agent listens on `127.0.0.1` only, so other machines on the network can't reach it.
  To expose it on purpose: `AGENT_HOST=0.0.0.0 python agent.py` (anyone on your network
  can then use it).
- Requests from other websites are blocked (Host header + JSON content-type checks), so a
  malicious page can't drive your agent or change its settings.
- Log content is always HTML-escaped in the UI, so attacker-controlled log lines can't
  run scripts in your browser.
- Use the agent only on systems you own or are authorised to assess.

## 🧪 Tests

```bash
python -m unittest discover -s tests -v
```

## 📁 Files

```
ai-agent/
├── agent.py          # web server, local AI client, CLI (stdlib only)
├── detector.py       # rule engine + correlation (brute force, scans, enumeration)
├── static/index.html # the web UI (single file, no build step)
├── samples/          # example attack logs: auth, web, firewall, Windows
├── tests/            # unit tests
├── start.sh          # Linux/macOS launcher
└── start.bat         # Windows launcher
```
