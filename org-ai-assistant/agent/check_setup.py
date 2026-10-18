"""Checks that the assistant can use your database and your existing LLM.

    python check_setup.py
    LLM_MODEL=qwen2.5-coder:14b python check_setup.py

Checks, in order:
  1. database: the read-only login works, sees the views, cannot write
  2. LLM server: reachable, and the configured model is installed
  3. context window: the whole instruction prompt fits (Ollama only)
  4. speed: prompt reading and answer writing speed on this server
  5. one real question from start to finish
"""
import sys
import time

import psycopg
import requests

import config
from agent import HRAgent, UserContext
from examples import load_examples

OK, WARN, FAIL = "  [OK]  ", "  [WARN]", "  [FAIL]"
problems = 0


def report(status, msg):
    global problems
    problems += status == FAIL
    print(f"{status} {msg}")


def check_database():
    print("1. Database")
    try:
        with psycopg.connect(config.DB_DSN, connect_timeout=5) as conn:
            views = conn.execute("SELECT count(*) FROM information_schema.views"
                                 " WHERE table_schema = 'ai_views'").fetchone()[0]
            read_only = conn.execute("SHOW default_transaction_read_only").fetchone()[0]
    except psycopg.Error as e:
        report(FAIL, f"cannot connect with AI_DB_DSN: {e}")
        return False
    report(OK if views else FAIL, f"{views} views visible in ai_views")
    report(OK if read_only == "on" else FAIL, f"read-only login: {read_only}")
    return views > 0


def check_llm():
    print("2. LLM server")
    try:
        r = requests.get(f"{config.LLM_BASE_URL}/models", timeout=10)
        r.raise_for_status()
        models = [m["id"] for m in r.json().get("data", [])]
    except (requests.RequestException, ValueError) as e:
        report(FAIL, f"cannot reach {config.LLM_BASE_URL}: {e}")
        print("         Set LLM_BASE_URL, e.g. http://localhost:11434/v1 (Ollama)")
        return False
    report(OK, f"reachable at {config.LLM_BASE_URL}")
    if config.LLM_MODEL in models:
        report(OK, f"model {config.LLM_MODEL} is installed")
        return True
    report(FAIL, f"model {config.LLM_MODEL} not found. Installed: {', '.join(models) or 'none'}")
    print("         Set LLM_MODEL to one of these names.")
    return False


def check_context_and_speed(bot):
    print("3. Context window and 4. speed (Ollama native API)")
    root = config.LLM_BASE_URL.rstrip("/").removesuffix("/v1")
    question = load_examples()[0]["question"]
    # A unique first line stops Ollama reusing a cached copy of the prompt,
    # so prompt_eval_count really is the number of tokens the model read.
    system = f"(setup check {time.time_ns()})\n{bot.system_prompt}"
    try:
        r = requests.post(f"{root}/api/chat", timeout=config.LLM_TIMEOUT_S, json={
            "model": config.LLM_MODEL, "stream": False,
            "options": {"temperature": 0, "num_predict": 120},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": f"Question: {question}"}]})
        r.raise_for_status()
        d = r.json()
    except (requests.RequestException, ValueError):
        report(WARN, "not an Ollama server (or old version): skipped. Check its context length is >= 8192")
        return
    expected = len(system) // 4  # rough lower bound on tokens
    got = d.get("prompt_eval_count", 0)
    if got and got < expected:
        report(FAIL, f"prompt cut short: model read {got} tokens, prompt is ~{expected}+ tokens")
        print("         Increase Ollama's context: set OLLAMA_CONTEXT_LENGTH=8192 for the Ollama")
        print("         service (see docs/CONNECT_EXISTING_MODEL.md) and restart it.")
    else:
        report(OK, f"whole prompt read ({got} tokens)")
    if d.get("prompt_eval_duration"):
        report(OK, f"reading speed: {got / (d['prompt_eval_duration'] / 1e9):.0f} tokens/s"
                   " (a repeat question is faster: Ollama reuses the cached prompt)")
    if d.get("eval_duration"):
        report(OK, f"writing speed: {d['eval_count'] / (d['eval_duration'] / 1e9):.1f} tokens/s")


def check_one_question(bot):
    print("5. One question, start to finish (as hr_admin)")
    ex = load_examples()[0]
    t = time.time()
    ans = bot.ask(ex["question"], UserContext("check-setup", "hr_admin"))
    if ans.error:
        report(FAIL, f"{ex['question']} -> {ans.error}")
        if ans.sql:
            print(f"         SQL was: {ans.sql}")
        return
    report(OK, f"{ex['question']} -> {len(ans.rows)} rows in {time.time() - t:.1f}s")
    print(f"         SQL: {' '.join(ans.sql.split())}")
    if ans.summary:
        print(f"         Answer: {ans.summary.strip()}")


def main():
    print(f"Database: {config.DB_DSN.split('password')[0].strip()}")
    print(f"LLM:      {config.LLM_BASE_URL}  model={config.LLM_MODEL}\n")
    db_ok = check_database()
    llm_ok = check_llm()
    if db_ok and llm_ok:
        bot = HRAgent()
        check_context_and_speed(bot)
        check_one_question(bot)
    print("\nAll checks passed. Next: python evaluate.py" if problems == 0
          else f"\n{problems} problem(s) found; fix them and run again.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
