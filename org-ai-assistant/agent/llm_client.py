"""Minimal client for an OpenAI-compatible chat API (Ollama, vLLM, llama.cpp server)."""
import re

import requests

import config


def chat(messages, model=None, max_tokens=400):
    resp = requests.post(
        f"{config.LLM_BASE_URL}/chat/completions",
        json={"model": model or config.LLM_MODEL, "messages": messages,
              "temperature": 0, "max_tokens": max_tokens},
        timeout=config.LLM_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def extract_sql(text):
    """Pulls the SQL out of a reply; returns None if the model declined."""
    if "CANNOT_ANSWER" in text:
        return None
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    sql = (m.group(1) if m else text).strip()
    return sql.rstrip(";").strip() or None
