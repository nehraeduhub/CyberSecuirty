#!/usr/bin/env python3
"""CyberSec AI Agent - portable local AI security analyst.

Zero dependencies: only the Python 3.8+ standard library. Talks to a local LLM
server (Ollama, LM Studio, llama.cpp server, KoboldCpp, Jan, vLLM...) so your
logs never leave your machine.

    python agent.py                         # start web UI on http://127.0.0.1:8787
    python agent.py scan auth.log           # scan a log from the terminal
    python agent.py scan auth.log --ai      # ...and let the AI write an assessment
    sudo python agent.py audit --pdf r.pdf  # audit this Linux machine, save a PDF report
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import webbrowser
from collections import OrderedDict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import detector
import host_audit
import knowledge
import report_pdf

VERSION = "2.0.0"
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
    "num_ctx": 4096,          # context window; smaller = faster prompt processing on CPU
    "num_predict": 1200,      # max reply length in tokens
    "num_thread": 0,          # CPU threads for the model; 0 = let Ollama decide (physical cores)
    "keep_alive": "-1",       # keep the model loaded in RAM forever (no reload delay)
    "report": {},             # PDF branding overrides, see report_pdf.BRAND
    "host": "127.0.0.1",      # "0.0.0.0" or this machine's IP to open the UI from other computers
    "access_token": "",       # required to log in when listening on the network (auto-generated)
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
- Explanations, fixes and IOCs for each finding are already computed by the local rule \
engine and shown to the user. Do not repeat them: add correlation, reasoning, attacker \
intent and priorities instead.
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
           "api_key": "AGENT_API_KEY", "host": "AGENT_HOST", "port": "AGENT_PORT",
           "access_token": "AGENT_TOKEN"}
    for key, var in env.items():
        if os.environ.get(var):
            cfg[key] = os.environ[var]
    cfg["port"] = int(cfg["port"])
    return cfg


SAVED_KEYS = ("provider", "base_url", "model", "api_key", "temperature", "num_ctx", "num_predict",
              "num_thread", "keep_alive", "report")


def save_config(cfg, keys=SAVED_KEYS):
    """Update only these keys in config.json; anything else in the file (host, port...) is kept."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.update({k: cfg[k] for k in keys})
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)  # holds the access token / API key
    except OSError:
        pass


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def is_local_only(cfg):
    return cfg["host"] in LOOPBACK


def lan_addresses():
    """This machine's IP addresses, for printing the URLs other computers can use."""
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; picks the default-route address
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        ips.update(a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


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


THINKING_MODELS = re.compile(r"qwen3|deepseek-r1|qwq|magistral", re.I)


def _keep_alive(cfg):
    k = str(cfg.get("keep_alive", "-1")).strip()
    return int(k) if k.lstrip("-").isdigit() else k


def _ollama_options(cfg):
    opts = {"temperature": float(cfg["temperature"]), "num_ctx": int(cfg["num_ctx"]),
            "num_predict": int(cfg["num_predict"])}
    if int(cfg.get("num_thread") or 0) > 0:
        opts["num_thread"] = int(cfg["num_thread"])
    return opts


def warmup(cfg):
    """Load the model into RAM ahead of the first question (the slow part on an HDD)."""
    if cfg["provider"] != "ollama":
        return
    try:
        body = {"model": resolve_model(cfg), "keep_alive": _keep_alive(cfg), "options": _ollama_options(cfg)}
        with _request(cfg["base_url"].rstrip("/") + "/api/generate", cfg, body, timeout=600) as r:
            r.read()
    except LLMError:
        pass


def _strip_thinking(chunks):
    """Hide <think>...</think> reasoning blocks some models emit, so answers appear immediately."""
    inside, buf = False, ""
    for c in chunks:
        buf += c
        while True:
            if inside:
                end = buf.find("</think>")
                if end < 0:
                    buf = buf[-8:]
                    break
                buf, inside = buf[end + 8:].lstrip(), False
            else:
                start = buf.find("<think>")
                if start < 0:
                    keep = len(buf) - 7 if len(buf) > 7 else 0  # a tag may be split across chunks
                    if keep:
                        yield buf[:keep]
                        buf = buf[keep:]
                    break
                if start:
                    yield buf[:start]
                buf, inside = buf[start + 7:], True
    if buf and not inside:
        yield buf


_CACHE = OrderedDict()
_CACHE_MAX = 128


def _cache_key(cfg, messages):
    raw = json.dumps([cfg["provider"], cfg["model"], cfg["temperature"], messages], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def stream_chat(cfg, messages, use_cache=True):
    """Yield the reply token-by-token. Identical questions are answered instantly from cache."""
    resolve_model(cfg)
    key = _cache_key(cfg, messages)
    if use_cache and key in _CACHE:
        _CACHE.move_to_end(key)
        yield _CACHE[key]
        return
    parts = []
    for chunk in _strip_thinking(_raw_stream(cfg, messages)):
        parts.append(chunk)
        yield chunk
    reply = "".join(parts)
    if reply.strip():
        _CACHE[key] = reply
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def _raw_stream(cfg, messages):
    model = cfg["model"]
    if cfg["provider"] == "ollama":
        body = {"model": model, "messages": messages, "stream": True, "keep_alive": _keep_alive(cfg),
                "options": _ollama_options(cfg)}
        if THINKING_MODELS.search(model):
            body["think"] = False  # skip slow hidden reasoning for fast answers
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
                "temperature": float(cfg["temperature"]), "max_tokens": int(cfg["num_predict"])}
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
    # System prompt first and unchanged, then the analysis: Ollama reuses its cache for this
    # identical prefix, so follow-up questions only process the new tokens.
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if analysis:
        msgs.append({"role": "system",
                     "content": "Current analysis results:\n" + detector.ai_context(analysis)})
    for m in history[-MAX_HISTORY:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"]})
    return msgs


LOGIN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>CyberSec AI Agent - Sign in</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0a111c;color:#e4ebf3;
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}form{background:#111a27;border:1px solid #24344a;
border-radius:14px;padding:28px;width:min(360px,90vw);box-shadow:0 6px 18px rgba(0,0,0,.3)}h1{font-size:18px;margin:0 0 4px}
p{color:#7d8da1;font-size:13px;margin:0 0 18px}input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;
border:1px solid #24344a;background:#162232;color:#e4ebf3;font:inherit}button{margin-top:14px;width:100%;padding:10px;
border:0;border-radius:8px;background:#1E9E4F;color:#fff;font:inherit;font-weight:600;cursor:pointer}
#e{color:#ff4d6a;font-size:13px;min-height:18px;margin-top:10px}</style></head><body>
<form id="f"><h1>&#128737; CyberSec AI Agent</h1><p>Enter the access token shown in the agent's terminal
(or in config.json on the server).</p><input id="t" type="password" placeholder="Access token" autofocus
autocomplete="current-password"><button>Sign in</button><div id="e"></div></form>
<script>document.getElementById("f").onsubmit=async(ev)=>{ev.preventDefault();
const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({token:document.getElementById("t").value})});
if(r.ok)location.reload();else document.getElementById("e").textContent="Wrong token - try again.";};</script>
</body></html>"""


INVESTIGATE_PROMPT = ("Investigate these findings. Start with a 2-3 sentence executive summary paragraph "
                      "(no heading). Then: ## Attack story (what happened, step by step, with times), "
                      "## Confidence & false positives, ## Top 5 actions now (with commands).")


def instant_answer(kind, analysis, index=None):
    """Answers computed locally in milliseconds - no AI needed."""
    if kind == "block":
        ips = [p["ip"] for p in analysis.get("ip_profiles", []) if p["verdict"] in ("Malicious", "Suspicious")]
        return knowledge.block_commands(ips)
    if kind == "iocs":
        return knowledge.iocs_markdown(analysis)
    if kind == "playbook":
        return knowledge.playbook_markdown(analysis)
    if kind == "explain":
        return knowledge.explain_markdown(dict(analysis["findings"][int(index)]))
    raise ValueError("unknown instant answer")


# ---------------------------------------------------------------- web server

class Handler(BaseHTTPRequestHandler):
    server_version = f"CyberSecAIAgent/{VERSION}"
    cfg = None  # set in serve()

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError(f"Upload too large (max {MAX_BODY // 1024 // 1024} MB)")
        return json.loads(self.rfile.read(length) or b"{}")

    # ---- access control (only active when a token is set, which is automatic on the network)
    def _authorized(self):
        token = self.cfg.get("access_token")
        if not token:
            return True
        sent = self.headers.get("X-Agent-Token", "")
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "tg_token":
                sent = sent or v
        return hmac.compare_digest(sent.encode(), token.encode())

    def _login(self, body):
        token = self.cfg.get("access_token") or ""
        if not hmac.compare_digest(str(body.get("token", "")).encode(), token.encode()):
            time.sleep(1.5)  # slow down guessing
            return self._send(401, {"error": "wrong access token"})
        cookie = f"tg_token={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000"
        return self._send(200, {"ok": True}, headers={"Set-Cookie": cookie})

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if not self._authorized():
            if path in ("/", "/index.html"):
                return self._send(200, LOGIN_PAGE, "text/html; charset=utf-8")
            return self._send(401, {"error": "login required"})
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
                "has_api_key": bool(cfg.get("api_key")), "pdf": report_pdf.AVAILABLE,
                "num_ctx": cfg["num_ctx"], "num_predict": cfg["num_predict"], "num_thread": cfg["num_thread"],
                "is_root": hasattr(os, "geteuid") and os.geteuid() == 0,
                "platform": sys.platform, "brand": dict(report_pdf.BRAND, **(cfg.get("report") or {})),
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
        """Block other websites from driving the agent (CSRF / DNS rebinding).

        On the network the access token does this job: a rebinding site never has the cookie."""
        if is_local_only(self.cfg):
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
        if path == "/api/login":
            return self._login(body)
        if not self._authorized():
            return self._send(401, {"error": "login required"})
        if path == "/api/analyze":
            text = body.get("text") or ""
            if not text.strip():
                return self._send(400, {"error": "No log text supplied"})
            return self._send(200, detector.analyze(text))
        if path == "/api/config":
            return self._update_config(body)
        if path == "/api/chat":
            return self._chat(body)
        if path == "/api/audit":
            return self._send(200, host_audit.run_audit(include_logs=body.get("include_logs", True)))
        if path == "/api/instant":
            try:
                md = instant_answer(body.get("kind"), body.get("analysis") or {}, body.get("index"))
            except (ValueError, KeyError, IndexError, TypeError) as e:
                return self._send(400, {"error": f"cannot answer: {e}"})
            return self._send(200, {"markdown": md})
        if path == "/api/report/pdf":
            return self._pdf(body)
        if path == "/api/warmup":
            threading.Thread(target=warmup, args=(self.cfg,), daemon=True).start()
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def _pdf(self, body):
        if not report_pdf.AVAILABLE:
            return self._send(501, {"error": "PDF reports need reportlab. Install it with:  pip install reportlab"})
        analysis = body.get("analysis")
        if not isinstance(analysis, dict) or "findings" not in analysis:
            return self._send(400, {"error": "run an analysis first"})
        meta = {k: str(v)[:200] for k, v in (body.get("meta") or {}).items()
                if k in ("client", "assessor", "ref", "source", "scope_note")}
        meta["model"] = self.cfg.get("model") if body.get("ai_text") else ""
        try:
            pdf = report_pdf.build_pdf(analysis, meta, str(body.get("ai_text") or ""), self.cfg.get("report"))
        except Exception as e:  # report must never take the server down
            return self._send(500, {"error": f"PDF generation failed: {e}"})
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(pdf)))
        self.send_header("Content-Disposition", f'attachment; filename="security-report-{datetime.now():%Y%m%d-%H%M}.pdf"')
        self.end_headers()
        self.wfile.write(pdf)

    def _update_config(self, body):
        cfg = self.cfg
        old_model = cfg["model"]
        for key in ("provider", "base_url", "model"):
            if isinstance(body.get(key), str):
                cfg[key] = body[key].strip()
        for key in ("num_ctx", "num_predict", "num_thread"):
            if key in body:
                try:
                    cfg[key] = max(0, int(body[key]))
                except (TypeError, ValueError):
                    return self._send(400, {"error": f"{key} must be a number"})
        if isinstance(body.get("api_key"), str) and body["api_key"] != "********":
            cfg["api_key"] = body["api_key"].strip()
        try:
            cfg["temperature"] = max(0.0, min(2.0, float(body.get("temperature", cfg["temperature"]))))
        except (TypeError, ValueError):
            return self._send(400, {"error": "temperature must be a number"})
        if cfg["provider"] not in ("ollama", "openai"):
            cfg["provider"] = "ollama"
        save_config(cfg)
        if cfg["model"] != old_model:
            threading.Thread(target=warmup, args=(cfg,), daemon=True).start()
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
    on_network = not is_local_only(cfg)
    if on_network and not cfg.get("access_token"):
        cfg["access_token"] = secrets.token_urlsafe(18)
        save_config(cfg, ("access_token",))
    server_cls = ThreadingHTTPServer
    if ":" in cfg["host"]:  # IPv6 address such as "::"
        server_cls = type("V6Server", (ThreadingHTTPServer,), {"address_family": socket.AF_INET6})
    httpd = server_cls((cfg["host"], cfg["port"]), Handler)
    local = f"http://127.0.0.1:{cfg['port']}"
    if cfg["host"] in ("0.0.0.0", "", "::"):
        urls = [local] + [f"http://{ip}:{cfg['port']}" for ip in lan_addresses()]
    else:
        urls = [f"http://{cfg['host']}:{cfg['port']}"]
    print(f"\n  CyberSec AI Agent v{VERSION}")
    for u in urls:
        print(f"  Web UI : {u}")
    print(f"  AI     : {cfg['provider']} @ {cfg['base_url']} (model: {cfg['model'] or 'auto'})")
    if on_network:
        print(f"  Access token: {cfg['access_token']}   (stored in {CONFIG_FILE.name})")
        print("  [!] Reachable from your network over plain HTTP - use it only on a trusted LAN or VPN.")
    print("  Press Ctrl+C to stop.\n")
    url = urls[0]
    threading.Thread(target=warmup, args=(cfg,), daemon=True).start()
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


# ---------------------------------------------------------------- CLI

COLORS = {"critical": "\033[1;91m", "high": "\033[91m", "medium": "\033[93m",
          "low": "\033[96m", "info": "\033[37m"}


def print_result(result):
    color = sys.stdout.isatty()
    reset = "\033[0m" if color else ""
    if result.get("kind") == "host":
        h = result["host"]
        print(f"\nHost audit: {h.get('hostname')} - {h.get('os')} (as {h.get('audited_as')}, "
              f"{result.get('duration_s')} s)")
    else:
        print(f"\nScanned {result['lines']} lines ({', '.join(result['log_types'])})")
    print(f"Risk score: {result['risk_score']}/100 [{result['risk_level'].upper()}]  Grade: {result['grade']}\n")
    for f in result["findings"]:
        c = COLORS[f["severity"]] if color else ""
        print(f"{c}[{f['severity'].upper():8}]{reset} {f['title']}  x{f['count']}  "
              f"({f['mitre']})  {', '.join(f['ips'][:3])}")
        for s in f["samples"][:2]:
            where = f"L{s['line']}: " if s.get("line") else ""
            print(f"           {where}{s['text'][:140]}")
    if not result["findings"]:
        print("No issues found.")


def cli_report(cfg, args, result, source):
    ai_text = ""
    if args.ai:
        print("\n--- AI assessment ---\n")
        try:
            msgs = build_messages([{"role": "user", "content": INVESTIGATE_PROMPT}], result)
            parts = []
            for chunk in stream_chat(cfg, msgs):
                parts.append(chunk)
                print(chunk, end="", flush=True)
            print()
            ai_text = "".join(parts)
        except LLMError as e:
            print(f"[error] {e}", file=sys.stderr)
    if args.pdf:
        if not report_pdf.AVAILABLE:
            sys.exit("PDF reports need reportlab:  pip install reportlab")
        meta = {"source": source, "client": args.client or "", "assessor": args.assessor or "",
                "model": cfg.get("model") if ai_text else ""}
        Path(args.pdf).write_bytes(report_pdf.build_pdf(result, meta, ai_text, cfg.get("report")))
        print(f"\nPDF report saved: {args.pdf}")


def cli_scan(cfg, args):
    result = detector.analyze(Path(args.file).read_text(encoding="utf-8", errors="replace"))
    if args.json:
        return print(json.dumps(result, indent=2))
    print_result(result)
    cli_report(cfg, args, result, Path(args.file).name)


def cli_audit(cfg, args):
    result = host_audit.run_audit(include_logs=not args.no_logs)
    if args.json:
        return print(json.dumps(result, indent=2))
    print_result(result)
    if not result["host"].get("audited_as") == "root":
        print("\nTip: run with sudo for a complete audit (shadow, sudoers, firewall, all crontabs).")
    cli_report(cfg, args, result, "Live host audit")


def main():
    p = argparse.ArgumentParser(description="CyberSec AI Agent - local AI security analyst")
    p.add_argument("--host", help="bind address (default 127.0.0.1)")
    p.add_argument("--port", type=int, help="port (default 8787)")
    p.add_argument("--model", help="model name, e.g. dolphin-phi")
    p.add_argument("--no-browser", action="store_true", help="don't open the browser")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="scan a log file from the terminal")
    s.add_argument("file")
    a = sub.add_parser("audit", help="security audit of this Linux machine (use sudo for full results)")
    a.add_argument("--no-logs", action="store_true", help="skip scanning the system logs")
    for sp in (s, a):
        sp.add_argument("--ai", action="store_true", help="add an AI-written assessment")
        sp.add_argument("--json", action="store_true", help="print raw JSON results")
        sp.add_argument("--pdf", metavar="FILE", help="save a branded PDF report")
        sp.add_argument("--client", help="client / organisation name for the report")
        sp.add_argument("--assessor", help="analyst name for the report")
    args = p.parse_args()

    cfg = load_config()
    for key in ("host", "port", "model"):
        if getattr(args, key):
            cfg[key] = getattr(args, key)
    if args.cmd == "scan":
        cli_scan(cfg, args)
    elif args.cmd == "audit":
        cli_audit(cfg, args)
    else:
        serve(cfg, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
