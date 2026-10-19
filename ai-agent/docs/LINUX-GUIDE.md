# Linux Guide: 64 GB RAM, no GPU, 1 TB HDD

This guide sets up CyberSec AI Agent for the fastest possible answers on a CPU-only Linux
machine with 64 GB RAM and a hard disk (HDD). It covers Ubuntu/Debian; Fedora/RHEL notes are
included where they differ.

---

## 1. How it stays fast without a GPU

| Layer | What it does | Speed |
|---|---|---|
| Rule engine | Finds attacks in logs (brute force, SQLi, reverse shells…) | ~30,000 lines/s |
| Host audit | Checks this machine's security settings | ~0.3 s |
| ⚡ Instant answers | Response plan, firewall block commands, IOCs, explanations, fixes | a few milliseconds |
| Answer cache | The same question with the same data is answered again instantly | instant |
| 🤖 Local AI | Reasoning, attack story, detection rules, free-form chat | depends on model (below) |

The AI only receives a **short summary** (about 1–2 KB) of what the engine found, never the
whole log. On a CPU, reading the prompt is often slower than writing the answer, so a short
prompt means the reply starts sooner.

### What decides AI speed on your machine

- **No GPU:** the CPU and **RAM bandwidth** do all the work. Speed depends on how many
  parameters the model uses *per word*. Smaller models, and "Mixture-of-Experts" (MoE) models
  that only use a small part of themselves per word, are fast.
- **64 GB RAM:** plenty. Any model up to about 40 GB fits, and stays loaded so it is never
  read from disk again.
- **HDD:** only slows the **first load** of a model (about 100–150 MB/s, so a 5 GB model takes
  roughly 40 s and a 19 GB model takes 2–3 minutes). After that the model lives in RAM. The
  setup below keeps it loaded permanently and pre-loads it at start-up, so you only wait once
  per boot.

---

## 2. Choose the model

The speeds below are **rough estimates** for a modern 8–16 core desktop CPU with dual-channel
DDR4/DDR5. Measure your own machine with `scripts/benchmark.py` (section 5).

| Goal | Model (`ollama pull …`) | Size in RAM | Est. reply speed | Uncensored |
|---|---|---|---|---|
| **Very fast + uncensored (recommended start)** | `dolphin3` (8B, Llama 3.1) | ~5 GB | ~8–15 tok/s | ✅ |
| **Fastest possible** | `dolphin-phi` (2.7B) | ~2 GB | ~20–35 tok/s | ✅ (weaker reasoning) |
| Fast, strong analysis | `qwen2.5:3b` or `llama3.2:3b` | ~2–3 GB | ~15–30 tok/s | ❌ (but answers security questions with our prompt) |
| **Best quality at high speed on 64 GB** | `qwen3:30b-a3b` (MoE, 3B active) | ~19 GB | ~10–20 tok/s | ❌ standard; community "abliterated" builds exist* |
| Uncensored, more knowledge | `dolphin-mistral` (7B) | ~4.5 GB | ~8–14 tok/s | ✅ |
| Avoid on CPU | 70B dense models | 40+ GB | ~1–2 tok/s | — |

\* Uncensored ("abliterated") community versions of Qwen3 MoE are published on ollama.com
by community accounts. Search the library for "qwen3 abliterated 30b-a3b", check the exact tag
on the model page, then `ollama pull <that-name>`. Community builds aren't reviewed by Ollama,
so download them only from accounts you trust.

**Suggested setup for this machine:** install **`dolphin3`** as the everyday uncensored model,
and **`qwen3:30b-a3b`** for harder investigations. With 64 GB you can keep both downloaded
and switch from the model drop-down in the sidebar. The agent automatically turns off Qwen3's
slow "thinking" mode so it answers straight away.

> **tok/s** = words (tokens) per second the AI writes. Above about 15 tok/s feels instant,
> 8–15 is comfortable, and below 5 feels slow.

---

## 3. Install (one command)

```bash
sudo apt update && sudo apt install -y git python3 curl      # Fedora: sudo dnf install -y git python3 curl
git clone https://github.com/nehraeduhub/CyberSecuirty.git
cd CyberSecuirty/ai-agent
./scripts/setup-linux.sh --model dolphin3 --service
```

The script is safe to run again. It:

1. Installs the PDF library (`python3-reportlab`).
2. Installs **Ollama** (the local AI server).
3. **Tunes Ollama for CPU speed.** It keeps the model in RAM forever, gives one request all
   the cores, turns on flash attention and a smaller attention cache, and allows only local
   access.
4. Lowers swappiness so the model is never pushed out to the slow HDD, and sets the CPU
   governor to `performance` if `cpupower` is installed.
5. Downloads the model and writes `config.json` with **threads = your physical core count**.
6. Pre-loads the model into RAM. With `--service`, it also starts the agent at boot.

Add the second model at any time:

```bash
ollama pull qwen3:30b-a3b
```

Open **http://127.0.0.1:8787**.

---

## 4. Daily use

| Task | How |
|---|---|
| Analyse logs | **Threat Analysis → Log files**: drop `auth.log`, `access.log`, firewall or Windows exports |
| Analyse SIEM exports | Drop several CSV / JSON / JSONL / XML / CEF exports at once. They are correlated together (see [SIEM-ANALYSIS-GUIDE.md](SIEM-ANALYSIS-GUIDE.md)) |
| Describe your network | **Trusted Networks** page: LAN ranges, ISP IPs, servers, firewalls, jump hosts, scanners. This is context for the engine and the AI |
| Your logo and name on reports | **Branding** page |
| Audit this machine | **Threat Analysis → This machine → Run host audit** |
| Full audit with PDF from the terminal | `sudo python3 agent.py audit --pdf audit.pdf --client "ACME" --assessor "SOC"` |
| Scan a log from the terminal | `python3 agent.py scan /var/log/auth.log --ai --pdf incident.pdf` |
| Instant answers (no AI) | ⚡ **Response plan**, ⚡ **Block attackers**, ⚡ **IOCs** |
| AI investigation | 🤖 **AI Investigate**. The result is added to the PDF report automatically |
| PDF report | **Reports → Download PDF report** (Tech Guardians format: cover, document control, executive summary, findings, timeline, IOCs, roadmap, MITRE mapping, AI assessment) |

**Root and the host audit:** the web UI runs as your normal user, which is safer. Some checks
can only read their data as root: `/etc/shadow`, sudoers, every user's crontab and the
firewall rules. For a complete audit, use the terminal command with `sudo` shown above.

### Open the agent from other computers (host IP)

By default the agent only answers on `127.0.0.1`, which means this machine only. To use the
server's IP address instead:

```bash
cd ~/CyberSecuirty/ai-agent
hostname -I                     # shows the server's IP, e.g. 192.168.1.50
nano config.json                # add or change:  "host": "0.0.0.0",
sudo systemctl restart cybersec-agent      # or: python3 agent.py
journalctl -u cybersec-agent -n 20         # shows the URL and the access token
```

- `"host": "0.0.0.0"` listens on every network card. To listen on one network only, put
  that card's IP instead (e.g. `"192.168.1.50"`). The port is set with `"port": 8787`.
- On the other computer, open `http://192.168.1.50:8787` and sign in with the **access
  token**. It is generated automatically the first time the agent listens on the network,
  printed in the terminal/log, and stored in `config.json` (readable only by its owner). To
  change it, edit `"access_token"` and restart. All signed-in browsers then have to sign in
  again.
- **Prefer a username and password?** Run this on the server, then restart the agent:
  ```bash
  python3 agent.py set-password            # asks for a username (default admin) and the password twice
  sudo systemctl restart cybersec-agent    # or stop and start python3 agent.py
  ```
  The sign-in page then asks for the username and password, and the access token stops working.
  - The password must be at least 10 characters. Only a salted PBKDF2-SHA256 hash is stored in `config.json`, never the password itself.
  - A sign-in lasts 12 hours (`"session_hours"` in `config.json`). **Sign out** is at the bottom of the sidebar.
  - After 10 wrong passwords from one address, that address is blocked for 15 minutes.
  - Run `set-password` again to change the password; everyone has to sign in again.
  - `python3 agent.py remove-password` goes back to the access token.
  - Once a password is set, it is required on `127.0.0.1` too.
- If the firewall is on, allow only your LAN:
  `sudo ufw allow from 192.168.1.0/24 to any port 8787 proto tcp`
- **Ollama stays on 127.0.0.1.** Only the agent talks to it, so the AI is never exposed to
  the network directly.
- The connection is plain HTTP, so use this only on a trusted LAN or VPN. For access across
  untrusted networks, keep `127.0.0.1` and use an SSH tunnel instead:
  `ssh -L 8787:127.0.0.1:8787 user@server`, then open `http://127.0.0.1:8787`.
- The host audit will now list port 8787 as exposed. That is expected, because you opened it
  on purpose.

---

## 5. Measure and tune speed

```bash
python3 scripts/benchmark.py                 # every installed model
python3 scripts/benchmark.py dolphin3 qwen3:30b-a3b
```

Run it twice; the first run includes loading from the HDD. The *reply tok/s* column is what
you feel in the chat.

Tuning knobs (**Settings** page or `config.json`):

| Setting | Fastest value | Why |
|---|---|---|
| CPU threads (`num_thread`) | number of **physical** cores (`lscpu -p=Core \| grep -v '#' \| sort -u \| wc -l`) | Hyper-threads slow inference down |
| Context window (`num_ctx`) | `4096` | Larger contexts are slower to process; 4096 is plenty because the agent sends summaries |
| Max reply tokens (`num_predict`) | `800`–`1200` | Caps very long answers |
| Temperature | `0.1`–`0.3` | Focused, factual answers |

Other speed tips:

- **Keep only one big model loaded.** This is already set (`OLLAMA_MAX_LOADED_MODELS=1`).
- **Close RAM-hungry programs** (browsers with many tabs) while analysing. Memory bandwidth
  is shared.
- **Check the RAM runs in dual-channel mode** (two or four sticks, not one). This alone can
  double AI speed on a CPU. `sudo dmidecode -t memory | grep -E "Size|Speed|Locator"`
- **Optional: an SSD.** A small SATA/NVMe SSD for `~/.ollama` or `/usr/share/ollama` makes the
  first load 5–20× faster. Answers *after* loading are the same speed, because the model is
  in RAM.
- Follow-up questions in the same chat start faster than the first one, because Ollama
  reuses its cache for the unchanged system prompt and analysis.

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| Sidebar says "AI offline" | `systemctl status ollama`, then `sudo systemctl restart ollama` |
| First answer takes a minute | The model is loading from the HDD (once per boot). Use **Settings → Pre-load model now** or wait for the boot-time pre-load |
| Answers are slow every time | Run the benchmark; use a smaller model or `qwen3:30b-a3b`; set threads = physical cores |
| "PDF reports need reportlab" | `sudo apt install python3-reportlab`, then restart the agent |
| Host audit shows limited results | Run it as root: `sudo python3 agent.py audit --pdf audit.pdf` |
| Want to use it from another PC | Set `"host": "0.0.0.0"` in `config.json` and sign in with the access token (section 4), or use an SSH tunnel |
| Can't open `http://SERVER-IP:8787` | Check `"host"` in `config.json`, restart the agent, and open the port: `sudo ufw allow from 192.168.1.0/24 to any port 8787 proto tcp` |
| Lost the access token | `python3 agent.py info` on the server |
| Forgot the password | On the server: `python3 agent.py set-password` (sets a new one), then restart the agent |
| "Too many failed sign-ins" | Wait 15 minutes, or restart the agent |
| Network IP not printed at start | `git pull` to get the latest version, then `python3 agent.py info`. It shows the config file in use, the host, every URL and the token. As a service, the start-up output goes to `journalctl -u cybersec-agent -n 30`, not your terminal |

---

## 7. Security of the setup

- Ollama and the agent both listen on **127.0.0.1 only** by default. If you open the agent on
  the host IP, it requires the access token, and Ollama stays local.
  The host audit flags an exposed Ollama port (11434) as a finding.
- The web UI blocks requests from other websites (CSRF / DNS-rebinding protection), and all
  log content is HTML-escaped.
- Nothing is sent to the internet. After setup you can run the machine fully offline.
