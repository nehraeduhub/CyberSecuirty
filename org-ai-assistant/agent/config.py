"""Settings, read from environment variables (defaults match the dummy setup)."""
import os

# Read-only login used to run AI-generated SQL
DB_DSN = os.getenv("AI_DB_DSN", "host=localhost dbname=org_hr user=ai_readonly password=change_me_ai_readonly")
# Insert-only login used to write the audit log (empty = no audit)
AUDIT_DSN = os.getenv("AI_AUDIT_DSN", "host=localhost dbname=org_hr user=ai_audit_writer password=change_me_audit_writer")

# Any OpenAI-compatible server: Ollama (pilot, CPU) or vLLM (later, GPU)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-coder:7b")
LLM_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT_S", "300"))  # CPU inference is slow

MAX_ROWS = int(os.getenv("AI_MAX_ROWS", "200"))
