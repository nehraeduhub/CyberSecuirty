# Pilot plan: CPU-only server

**Server:** 64 CPU cores, 64 GB RAM, 2 TB HDD, no GPU.
**Organisation:** about 3 lakh (300,000) employees.

## 1. Can this server run the pilot? Yes, with limits

The model does **not** get bigger or slower because the database is large.
It only writes a short SQL query, and PostgreSQL does the heavy work. So
3 lakh employees is a database question, not an AI question, and
PostgreSQL handles this easily.

What a CPU limits is **how many people can ask at the same time**, and how
long each answer takes.

| | Pilot on this server | Full rollout (3 lakh staff) |
|---|---|---|
| Users | 20-100 named pilot users (HR cell, 1-2 departments) | Thousands |
| Questions at the same time | 1-2 (others wait in a queue) | Tens to hundreds |
| Time per answer | about 15-60 s (estimate, measure it) | 2-5 s |
| Hardware | this server | GPU server(s), see section 6 |

## 2. Memory plan (64 GB)

| Use | RAM |
|---|---|
| Operating system, Docker, monitoring | ~4 GB |
| PostgreSQL `shared_buffers` (set in docker-compose.yml) | 8 GB |
| PostgreSQL query memory + OS file cache for the database | ~16-20 GB |
| LLM, 14B model, 4-bit (`qwen2.5-coder:14b`, ~9 GB) + working memory | ~12 GB |
| Free headroom | ~20 GB |

A 32B 4-bit model (~20 GB) also fits in RAM, but on CPU it is roughly twice
as slow as 14B. Start with 7B and 14B, and try 32B only if accuracy is too low.

## 3. Which model on CPU

On a CPU, speed depends mostly on **memory bandwidth** and model size. Use
4-bit quantised models (`Q4_K_M`, the Ollama default):

| Model (Ollama tag) | Disk/RAM | Rough speed on 64 cores* | Use |
|---|---|---|---|
| `qwen2.5-coder:7b` | ~4.7 GB | 10-20 words/s | fastest; start here |
| `qwen2.5-coder:14b` | ~9 GB | 5-10 words/s | **recommended for the pilot** |
| `qwen2.5-coder:32b` | ~20 GB | 2-5 words/s | most accurate, slow |

\*Estimates only. Real numbers depend on the CPU model and how many memory
channels are populated. `agent/evaluate.py` measures speed and accuracy on
your server; let those results decide.

Qwen2.5-Coder is a well-tested baseline for SQL. Newer open-weight models
appear often. Any model in the Ollama library can be compared the same way:
```bash
docker compose run --rm agent python evaluate.py --model qwen2.5-coder:7b --model qwen2.5-coder:14b
```
Check that the model's licence allows use inside your organisation.

### Making the CPU faster
- The system prompt (schema + examples) is identical for every question, so
  Ollama can reuse it instead of re-reading it each time. Keep it short:
  expose only the views the pilot needs.
- `--no-summary` skips the second LLM call (the plain-English answer) and
  roughly halves the time. The table of results is shown either way.
- `OLLAMA_KEEP_ALIVE=-1` keeps the model in RAM. Loading it from an HDD takes
  30-60 s, so it should happen only once, at startup.

## 4. The HDD

- **Fine for the pilot.** The model is read once into RAM. The database's
  frequently used parts stay in RAM (8 GB buffers + OS cache).
- Large reports (for example "total pay for all 3 lakh staff over 12 months")
  will be slower on an HDD than on an SSD.
- If you can add even one 500 GB-1 TB SSD, put the PostgreSQL data directory
  on it. That is the cheapest big speed-up.

## 5. Test with full-size dummy data (3 lakh employees)

```bash
# Without Docker (PostgreSQL 15+ installed on the server)
sudo -u postgres DB_NAME=org_hr EMP_COUNT=300000 ./scripts/setup_db.sh

# With Docker: the first start creates 500 employees; then regenerate at full size
docker compose up -d hr-db
for f in 01_schema 02_seed_dummy_data 03_security_roles; do
  docker compose exec -T hr-db psql -q -v ON_ERROR_STOP=1 -v emp_count=300000 \
    -U hr_owner -d org_hr -f /docker-entrypoint-initdb.d/$f.sql
done
docker compose exec -T hr-db psql -U hr_owner -d org_hr -c "VACUUM ANALYZE"
```
See section 8 for size and time measured on a test machine.

## 6. Later: production for 3 lakh employees (rough sizing)

Assume 10% of staff use it on a given day, 3 questions each, and the busiest
hour carries 20% of the day:
`300,000 × 10% × 3 × 20% ≈ 18,000 questions/hour ≈ 5 per second`.

- One CPU server answers roughly 60-200 questions per hour.
- A GPU server with **vLLM** serving a 14B-32B model handles many requests at
  once. Plan for **2-4 data-centre GPUs** (L40S 48 GB or A100/H100 80 GB
  class) across two servers for redundancy, plus an SSD-based PostgreSQL
  **read replica** dedicated to the assistant.
- The agent code does not change: it talks to any OpenAI-compatible server.
  Point `LLM_BASE_URL` at vLLM instead of Ollama.

Use the pilot to measure real usage (the audit log records every question)
before buying hardware.

## 7. Pilot steps

| Week | Work | Done when |
|---|---|---|
| 1 | Build the offline bundle (`scripts/offline_bundle.sh`) on an internet machine, scan it, move it in, run `scripts/import_bundle.sh` | `ollama list` shows the models on the server |
| 1 | Load 3 lakh dummy employees; run `evaluate.py` with 7B and 14B | Accuracy and seconds per question recorded for each model |
| 2 | Collect 50-100 real questions from the pilot HR users; add them with correct SQL to `database/04_sample_questions.sql` | Test set covers postings, leave, training and pay |
| 2-3 | Improve view and column comments and the examples until accuracy ≥ 85-90% | `evaluate.py` result |
| 3 | Web chat screen with login (next build step) | Pilot users can log in from their desks |
| 4 | Connect a **copy** of the real database (only the views the pilot needs) | Same tests pass on real data |
| 4+ | Pilot runs; review the audit log weekly | Decision on GPU purchase and rollout |

## 8. Measured on the test machine

Measured in a 4-core cloud test machine, **not** your server:

- Generating 3 lakh dummy employees: _see below_
- Database size: _see below_
- Sample questions on 3 lakh data: _see below_
