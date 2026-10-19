#!/usr/bin/env python3
"""CyberSec AI Agent - portable local AI security analyst.

Zero dependencies: only the Python 3.8+ standard library. Talks to a local LLM
server (Ollama, LM Studio, llama.cpp server, KoboldCpp, Jan, vLLM...) so your
logs never leave your machine.

    python agent.py                    # start web UI on http://127.0.0.1:8787
    python agent.py scan auth.log      # scan a log from the terminal
    python agent.py scan auth.log --ai # ...and let the AI write an assessment
"""
import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import detector

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SAMPLES = ROOT / "samples"
CONFIG_FILE = ROOT / "config.json"
MAX_BODY = 25 * 1024 * 1024   # 25 MB upload limit
MAX_HISTORY = 12              # chat turns sent to the model (shorter = faster)

DEFAULTS = {
    "provider": "ollama",                 # "ollama" or "openai" (any OpenAI-compatible server)
    "base_url": "http://127.0.0.1:11434", # LM Studio: http://127.0.0.1:1234/v1, llama.cpp: http://127.0.0.1:8080/v1
    "model": "",                          # empty = first model the server reports
    "api_key": "",
    "temperature": 0.2,
    "num_ctx": 4096,
    "host": "127.0.0.1",
    "port": 8787,
}

SYSTEM_PROMPT = """You are CyberSec AI Agent, an expert SOC analyst, incident responder and \
penetration tester running fully offline on the user's own machine.
- Answer directly and technically. The user is a security professional working on systems \
they own or are authorised to test, so explain attacker techniques, payloads and tooling \
openly when it helps them understand or defend.
- When given log analysis results: state what happened, how confident you are, which \
findings are false positives, the attacker's likely goal, and concrete next steps \
(commands, firewall rules, IOCs to block).
- Map activity to MITRE ATT&CK where relevant.
- Be concise. Use short headings, bullet points and code blocks."""

_OPENER = build_opener(ProxyHandler({}))  # local AI: never route through a system proxy


class LLMError(Exception):
    pass


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            print(f"[!] Ignoring unreadable {CONFIG_FILE.name}: {e}", file=sys.stderr)
    env = {"provider": "AGENT_PROVIDER", "base_url": "AGENT_BASE_URL", "model": "AGENT_MODEL",
           "api_key": "AGENT_API_KEY", "host": "AGENT_HOST", "port": "AGENT_PORT"}
    for key, var in env.items():
        if os.environ.get(var):
            cfg[key] = os.environ[var]
    cfg["port"] = int(cfg["port"])
    return cfg


def save_config(cfg):
    keep = {k: cfg[k] for k in ("provider", "base_url", "model", "api_key", "temperature", "num_ctx")}
    CONFIG_FILE.write_text(json.dumps(keep, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- LLM client

def _openai_url(base, path):
    base = base.rstrip("/")
    return base + path if base.endswith("/v1") else base + "/v1" + path


def _request(url, cfg, body=None, timeout=10):
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    data = json.dumps(body).encode() if body is not None else None
    try:
        return _OPENER.open(Request(url, data=data, headers=headers), timeout=timeout)
    except HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise LLMError(f"AI server returned HTTP {e.code}: {detail}") from e
    except (URLError, OSError) as e:
        raise LLMError(f"Cannot reach AI server at {cfg['base_url']} ({e}). "
                       "Is Ollama / LM Studio running?") from e


def list_models(cfg):
    if cfg["provider"] == "ollama":
        with _request(cfg["base_url"].rstrip("/") + "/api/tags", cfg, timeout=4) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    with _request(_openai_url(cfg["base_url"], "/models"), cfg, timeout=4) as r:
        return [m["id"] for m in json.load(r).get("data", [])]


def resolve_model(cfg):
    if cfg.get("model"):
        return cfg["model"]
    models = list_models(cfg)
    if not models:
        raise LLMError("The AI server has no models. Run e.g.:  ollama pull dolphin-phi")
    cfg["model"] = models[0]
    return cfg["model"]


def stream_chat(cfg, messages):
    """Yield the model's reply token-by-token."""
    model = resolve_model(cfg)
    if cfg["provider"] == "ollama":
        body = {"model": model, "messages": messages, "stream": True, "keep_alive": "30m",
                "options": {"temperature": float(cfg["temperature"]), "num_ctx": int(cfg["num_ctx"])}}
        with _request(cfg["base_url"].rstrip("/") + "/api/chat", cfg, body, timeout=600) as r:
            for raw in r:
                if not raw.strip():
                    continue
                obj = json.loads(raw)
                if obj.get("error"):
                    raise LLMError(obj["error"])
                if chunk := obj.get("message", {}).get("content"):
                    yield chunk
                if obj.get("done"):
                    return
    else:
        body = {"model": model, "messages": messages, "stream": True,
                "temperature": float(cfg["temperature"])}
        with _request(_openai_url(cfg["base_url"], "/chat/completions"), cfg, body, timeout=600) as r:
            for raw in r:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                choices = json.loads(data).get("choices") or [{}]
                if chunk := (choices[0].get("delta") or {}).get("content"):
                    yield chunk


def build_messages(history, analysis=None):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if analysis:
        msgs.append({"role": "system",
                     "content": "Current log analysis results:\n" + detector.ai_context(analysis)})
    for m in history[-MAX_HISTORY:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"]})
    return msgs


INVESTIGATE_PROMPT = ("Investigate these findings. Give: 1) Executive summary (2-3 sentences), "
                      "2) What the attacker did, step by step, 3) Likely false positives, "
                      "4) Indicators of compromise, 5) Prioritised response actions with commands.")


# ---------------------------------------------------------------- web server

class Handler(BaseHTTPRequestHandler):
    server_version = f"CyberSecAIAgent/{VERSION}"
    cfg = None  # set in serve()

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError(f"Upload too large (max {MAX_BODY // 1024 // 1024} MB)")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/status":
            return self._send(200, self._status())
        if path.startswith("/samples/"):
            name = path.rsplit("/", 1)[-1]
            allowed = {p.name: p for p in SAMPLES.glob("*.log")}
            if name in allowed:
                return self._send(200, allowed[name].read_bytes(), "text/plain; charset=utf-8")
        self._send(404, {"error": "not found"})

    def _status(self):
        cfg = self.cfg
        info = {"version": VERSION, "provider": cfg["provider"], "base_url": cfg["base_url"],
                "model": cfg["model"], "temperature": cfg["temperature"],
                "has_api_key": bool(cfg.get("api_key")),
                "samples": sorted(p.name for p in SAMPLES.glob("*.log"))}
        try:
            info["models"] = list_models(cfg)
            info["online"] = True
            if not cfg["model"] and info["models"]:
                cfg["model"] = info["model"] = info["models"][0]
        except (LLMError, ValueError, KeyError) as e:
            info.update(online=False, models=[], error=str(e))
        return info

    def _trusted(self):
        """Block other websites from driving the agent (CSRF / DNS rebinding)."""
        if self.cfg["host"] in ("127.0.0.1", "localhost"):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):
                return False
        # Forces a CORS preflight for cross-origin requests, which we never approve.
        return (self.headers.get("Content-Type") or "").startswith("application/json")

    def do_POST(self):
        if not self._trusted():
            return self._send(403, {"error": "forbidden"})
        try:
            body = self._json_body()
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        if not isinstance(body, dict):
            return self._send(400, {"error": "expected a JSON object"})
        path = self.path.split("?", 1)[0]
        if path == "/api/analyze":
            text = body.get("text") or ""
            if not text.strip():
                return self._send(400, {"error": "No log text supplied"})
            return self._send(200, detector.analyze(text))
        if path == "/api/config":
            return self._update_config(body)
        if path == "/api/chat":
            return self._chat(body)
        self._send(404, {"error": "not found"})

    def _update_config(self, body):
        cfg = self.cfg
        for key in ("provider", "base_url", "model"):
            if isinstance(body.get(key), str):
                cfg[key] = body[key].strip()
        if isinstance(body.get("api_key"), str) and body["api_key"] != "********":
            cfg["api_key"] = body["api_key"].strip()
        try:
            cfg["temperature"] = max(0.0, min(2.0, float(body.get("temperature", cfg["temperature"]))))
        except (TypeError, ValueError):
            return self._send(400, {"error": "temperature must be a number"})
        if cfg["provider"] not in ("ollama", "openai"):
            cfg["provider"] = "ollama"
        save_config(cfg)
        self._send(200, self._status())

    def _chat(self, body):
        history = body.get("messages") or []
        if body.get("investigate"):
            history = history + [{"role": "user", "content": INVESTIGATE_PROMPT}]
        messages = build_messages(history, body.get("analysis"))
        # Plain streaming response; the connection closes when the reply is done.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            for chunk in stream_chat(self.cfg, messages):
                self.wfile.write(chunk.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # user pressed Stop
        except (LLMError, ValueError) as e:
            self.wfile.write(f"\n\n[error] {e}".encode())


def serve(cfg, open_browser=True):
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer((cfg["host"], cfg["port"]), Handler)
    url = f"http://{'127.0.0.1' if cfg['host'] in ('0.0.0.0', '') else cfg['host']}:{cfg['port']}"
    print(f"\n  CyberSec AI Agent v{VERSION}")
    print(f"  Web UI : {url}")
    print(f"  AI     : {cfg['provider']} @ {cfg['base_url']} (model: {cfg['model'] or 'auto'})")
    if cfg["host"] not in ("127.0.0.1", "localhost"):
        print("  [!] Listening on all interfaces - anyone on your network can use this agent.")
    print("  Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


# ---------------------------------------------------------------- CLI

COLORS = {"critical": "\033[1;91m", "high": "\033[91m", "medium": "\033[93m",
          "low": "\033[96m", "info": "\033[37m"}


def cli_scan(cfg, args):
    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    result = detector.analyze(text)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    color = sys.stdout.isatty()
    reset = "\033[0m" if color else ""
    print(f"\nScanned {result['lines']} lines ({', '.join(result['log_types'])})")
    print(f"Risk score: {result['risk_score']}/100 [{result['risk_level'].upper()}]\n")
    for f in result["findings"]:
        c = COLORS[f["severity"]] if color else ""
        print(f"{c}[{f['severity'].upper():8}]{reset} {f['title']}  x{f['count']}  "
              f"({f['mitre']})  {', '.join(f['ips'][:3])}")
        for s in f["samples"][:2]:
            print(f"           L{s['line']}: {s['text'][:140]}")
    if not result["findings"]:
        print("No threats matched the built-in rules.")
    if args.ai:
        print("\n--- AI assessment ---\n")
        try:
            msgs = build_messages([{"role": "user", "content": INVESTIGATE_PROMPT}], result)
            for chunk in stream_chat(cfg, msgs):
                print(chunk, end="", flush=True)
            print()
        except LLMError as e:
            print(f"[error] {e}", file=sys.stderr)
            sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="CyberSec AI Agent - local AI security analyst")
    p.add_argument("--host", help="bind address (default 127.0.0.1)")
    p.add_argument("--port", type=int, help="port (default 8787)")
    p.add_argument("--model", help="model name, e.g. dolphin-phi")
    p.add_argument("--no-browser", action="store_true", help="don't open the browser")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="scan a log file from the terminal")
    s.add_argument("file")
    s.add_argument("--ai", action="store_true", help="add an AI-written assessment")
    s.add_argument("--json", action="store_true", help="print raw JSON results")
    args = p.parse_args()

    cfg = load_config()
    for key in ("host", "port", "model"):
        if getattr(args, key):
            cfg[key] = getattr(args, key)
    if args.cmd == "scan":
        cli_scan(cfg, args)
    else:
        serve(cfg, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
