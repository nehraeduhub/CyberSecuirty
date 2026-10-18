# Connect the HR assistant to the model already on your server

Your server already runs a model that answers general questions. This guide
connects the HR assistant to it. You do **not** need `offline_bundle.sh` or
the `ollama` service in `docker-compose.yml`.

Commands assume Ollama is installed directly on the server (the usual
`curl … | sh` install, running as the `ollama` systemd service). Notes for
Docker installs are given where they differ.

---

## Step 0: Note what you have

Run on the server and keep the output:

```bash
ollama --version
ollama list                     # the exact model names, e.g. qwen2.5-coder:14b
python3 --version               # needed for Step 2
psql --version                  # PostgreSQL 15 or newer needed
systemctl status ollama | head -3
```

Use the **exact** name from `ollama list` as `LLM_MODEL` below.

## Step 1: Create the dummy database on the server

```bash
cd org-ai-assistant
sudo -u postgres ./scripts/setup_db.sh                          # 500 employees, ~10 s
# later, full size:
sudo -u postgres EMP_COUNT=300000 ./scripts/setup_db.sh         # 3 lakh, ~10-20 min on HDD
```

## Step 2: Install the assistant's Python packages (offline)

On an **internet-connected** machine, with the project folder:
```bash
PY_VERSION=3.10 ./scripts/download_python_packages.sh   # use the server's version from Step 0
```
Copy `offline-bundle/python-packages/` to the server, then on the server:
```bash
cd python-packages && sha256sum -c SHA256SUMS && cd ..
python3 -m venv ~/hr-agent-venv
source ~/hr-agent-venv/bin/activate
pip install --no-index --find-links ./python-packages -r org-ai-assistant/agent/requirements.txt
```
(On Ubuntu/Debian, `python3 -m venv` may need the `python3-venv` package,
which you can copy in as a `.deb` the same way.)

## Step 3: Give Ollama a bigger context window (important)

The assistant sends the model a description of the database plus example
questions: about 1,700 tokens now, more as you add examples. Some Ollama
versions default to a 2,048-token window and **silently drop** the start
of a longer prompt, which makes answers wrong. Set 8,192:

```bash
sudo systemctl edit ollama
```
Add these lines, then save:
```ini
[Service]
Environment="OLLAMA_CONTEXT_LENGTH=8192"
Environment="OLLAMA_KEEP_ALIVE=-1"
Environment="OLLAMA_NUM_PARALLEL=2"
```
```bash
sudo systemctl daemon-reload && sudo systemctl restart ollama
```
- `OLLAMA_KEEP_ALIVE=-1` keeps the model in RAM, so it isn't reloaded from the HDD.
- `OLLAMA_NUM_PARALLEL=2` answers two people at once (uses more RAM).
- Ollama in Docker: pass the same variables with `-e`, then recreate the container.

**Older Ollama without `OLLAMA_CONTEXT_LENGTH`:** make a copy of the model
with a bigger window and use that name as `LLM_MODEL`:
```bash
printf 'FROM qwen2.5-coder:14b\nPARAMETER num_ctx 8192\n' > Modelfile
ollama create qwen2.5-coder-14b-8k -f Modelfile
```

## Step 4: Point the assistant at your model and database

```bash
source ~/hr-agent-venv/bin/activate
cd org-ai-assistant/agent
export LLM_BASE_URL=http://localhost:11434/v1     # Ollama's OpenAI-compatible address
export LLM_MODEL=qwen2.5-coder:14b                # exact name from "ollama list"
# Only if your database or passwords differ from the dummy defaults:
# export AI_DB_DSN="host=localhost dbname=org_hr user=ai_readonly password=..."
# export AI_AUDIT_DSN="host=localhost dbname=org_hr user=ai_audit_writer password=..."
```
If Ollama runs on another machine, use its IP in `LLM_BASE_URL`, and on that
machine set `Environment="OLLAMA_HOST=0.0.0.0"` and allow port 11434 only from
the assistant's server in the firewall.

## Step 5: Run the checks

```bash
python check_setup.py
```
It checks, in order:
1. the read-only database login works and cannot write;
2. Ollama is reachable and the model name is right;
3. the whole prompt fits in the context window;
4. reading and writing speed on your CPU;
5. one real question from start to finish.

Fix anything marked `[FAIL]`; the message says how.

## Step 6: Ask questions and measure accuracy

```bash
python ask.py --role hr_admin "How many employees are posted in each region?"
python ask.py --role employee --employee-id 2 "Show my net pay for the last 3 months"
python ask.py --role hr_admin --no-summary          # interactive; faster without the summary

python evaluate.py                                  # accuracy + seconds per question
python evaluate.py --model qwen2.5-coder:7b --model qwen2.5-coder:14b   # compare models
```

**Please send back:** the output of `check_setup.py` and `evaluate.py`. They
show how accurate and how fast your model is on your hardware, and decide
the next step.

---

### If your model is a general chat model, not a coder model

General models (Llama, Mistral, Gemma, and others) can write SQL too, but
usually less accurately than coder models. `evaluate.py` will show the
difference. If accuracy is low, add a coder model (`qwen2.5-coder:7b` or
`:14b`, 5-9 GB) next to it. Both can be installed; Ollama loads the one asked for.

### Keep your existing chat screen

If staff already use a chat screen (for example Open WebUI) for general
questions, keep it. A later step can add the HR assistant to the same screen
as a separate "HR" option, with the logged-in user's access rules applied.
