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
import shutil
import socket
import sys
import threading
import time
import webbrowser
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import ProxyHandler, Request, build_opener

import branding
import config_store
import detector
import history
import host_audit
import investigator
import knowledge
import memory
import pipeline
import report_pdf
import reputation
import trust

VERSION = "3.0.0"
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
    "report": {},             # legacy PDF branding overrides (Branding settings take precedence)
    "max_upload_mb": 512,     # per uploaded file
    "keep_uploads": False,    # delete uploaded logs after analysis (evidence is kept in the result)
    "learn_baseline": True,   # update UEBA baselines from accounts not involved in incidents
    "tz_hours": 0,            # time zone of logs that carry no zone information (0 = UTC)
    "host": "127.0.0.1",      # "0.0.0.0" or this machine's IP to open the UI from other computers
    "access_token": "",       # required to log in when listening on the network (auto-generated)
    "username": "",           # password login (set with: python3 agent.py set-password); replaces the token
    "password_hash": "",      # salted PBKDF2-SHA256 hash, never the password itself
    "session_secret": "",     # signs login cookies (auto-generated)
    "session_hours": 12,      # how long a password login stays valid
    "history_enabled": True,  # keep every analysis (History page) until you delete it
    "store_logs": True,       # keep the original uploaded / pasted log files with the analysis
    "history_max_days": 0,    # delete analyses older than this (0 = keep until deleted)
    "history_max_gb": 20,     # delete the oldest analyses when history exceeds this size (0 = no limit)
    "learn_from_data": True,  # use analyst verdicts, learned indicators and earlier sightings
    "abuseipdb_key": "",      # reputation look-ups (optional, sent only when you ask): abuseipdb.com
    "virustotal_key": "",     # virustotal.com (free key: 4 look-ups/minute, 500/day)
    "reputation_auto": False,  # look up public IPs/URLs automatically after each analysis
    "reputation_cache_hours": 24,
    "virustotal_per_min": 4,
    "virustotal_daily_limit": 500,
    "abuseipdb_daily_limit": 1000,
    "ui_show_branding": True,       # false = hide logo, organisation name and credit line in the web UI
    "ui_hide_branding_page": False,  # true = remove the Branding page and lock branding changes from the web UI
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
            raw = CONFIG_FILE.read_text(encoding="utf-8", errors="replace") if CONFIG_FILE.exists() else ""
            m = re.search(r'"(\w+)"\s*:\s*([0-9]+(?:\.[0-9]+){2,}|[A-Za-z][\w.\-]*)\s*[,}\n]', raw)
            if m and m.group(2) not in ("true", "false", "null"):
                print(f'\n  [!] In {CONFIG_FILE.name} the value of "{m.group(1)}" needs double quotes:\n'
                      f'        "{m.group(1)}": "{m.group(2)}"', file=sys.stderr)
            print(f"\n  [!] {CONFIG_FILE} has a mistake ({e}).\n"
                  "      ALL its settings are ignored (host falls back to 127.0.0.1). Check commas and quotes,\n"
                  "      or test it with:  python3 -m json.tool config.json\n", file=sys.stderr)
    env = {"provider": "AGENT_PROVIDER", "base_url": "AGENT_BASE_URL", "model": "AGENT_MODEL",
           "api_key": "AGENT_API_KEY", "host": "AGENT_HOST", "port": "AGENT_PORT",
           "access_token": "AGENT_TOKEN"}
    env.update(ui_show_branding="AGENT_SHOW_BRANDING", ui_hide_branding_page="AGENT_HIDE_BRANDING_PAGE",
               abuseipdb_key="AGENT_ABUSEIPDB_KEY", virustotal_key="AGENT_VIRUSTOTAL_KEY")
    for key, var in env.items():
        if os.environ.get(var):
            cfg[key] = os.environ[var]
    cfg["port"] = int(cfg["port"])
    for key in ("ui_show_branding", "ui_hide_branding_page", "history_enabled", "store_logs", "learn_from_data",
                "reputation_auto"):
        cfg[key] = _flag(cfg[key])
    return cfg


def _flag(v):
    """true/false from config.json, also accepting "yes"/"no", "1"/"0", "on"/"off"."""
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on", "show")
    return bool(v)


SAVED_KEYS = ("provider", "base_url", "model", "api_key", "temperature", "num_ctx", "num_predict",
              "num_thread", "keep_alive", "report", "learn_baseline", "tz_hours", "ui_show_branding",
              "history_enabled", "store_logs", "history_max_days", "learn_from_data", "abuseipdb_key",
              "virustotal_key", "reputation_auto")


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
BRANDING_LOCKED = ('Branding settings are disabled in the web interface ("ui_hide_branding_page": true in '
                   'config.json). Edit config/branding.json on the server, or set it to false and restart.')

# ---------------------------------------------------------------- password login
PBKDF2_ROUNDS = 600_000
MIN_PASSWORD = 10


def hash_password(password, rounds=PBKDF2_ROUNDS):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${dk.hex()}"


def check_password(password, stored):
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), bytes.fromhex(salt), int(rounds))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), digest)


def password_mode(cfg):
    return bool(cfg.get("password_hash"))


def _session_key(cfg):
    # bound to the password hash: changing or removing the password signs everyone out
    return (str(cfg.get("session_secret")) + "|" + str(cfg.get("password_hash"))).encode()


def make_session(cfg, user):
    exp = int(time.time() + float(cfg.get("session_hours") or 12) * 3600)
    msg = f"{user}|{exp}"
    sig = hmac.new(_session_key(cfg), msg.encode(), hashlib.sha256).hexdigest()
    return f"{user}|{exp}|{sig}"


def check_session(cfg, value):
    """Returns the user name for a valid, unexpired session cookie, else None."""
    try:
        user, exp, sig = value.rsplit("|", 2)
        if int(exp) < time.time():
            return None
    except ValueError:
        return None
    good = hmac.new(_session_key(cfg), f"{user}|{exp}".encode(), hashlib.sha256).hexdigest()
    return user if hmac.compare_digest(sig, good) and user == cfg.get("username") else None


_FAILS = {}            # client ip -> [failure times]; slows down password guessing
_FAILS_LOCK = threading.Lock()
LOCKOUT = (10, 900)    # 10 failures within 15 minutes locks that address out for the rest of the window


def _locked_out(ip):
    with _FAILS_LOCK:
        recent = [t for t in _FAILS.get(ip, []) if t > time.time() - LOCKOUT[1]]
        _FAILS[ip] = recent
        return len(recent) >= LOCKOUT[0]


def _record_fail(ip):
    with _FAILS_LOCK:
        _FAILS.setdefault(ip, []).append(time.time())


def agent_urls(cfg):
    port = cfg["port"]
    if cfg["host"] in ("0.0.0.0", "", "::"):
        return [f"http://127.0.0.1:{port}"] + [f"http://{ip}:{port}" for ip in lan_addresses()]
    return [f"http://{cfg['host']}:{port}"]


def is_local_only(cfg):
    return cfg["host"] in LOOPBACK


def _interface_addresses():
    """IPv4 address of every network interface, read from the kernel (works with no internet/route)."""
    ips = set()
    try:
        import fcntl
        import struct
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            for _, name in socket.if_nameindex():
                try:
                    req = struct.pack("256s", name[:15].encode())
                    ips.add(socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, req)[20:24]))  # SIOCGIFADDR
                except OSError:
                    pass  # interface without an IPv4 address
    except (ImportError, OSError, AttributeError):
        pass
    if not ips:
        try:  # fallback for systems without the ioctl (e.g. some containers)
            import subprocess
            out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=3).stdout
            ips.update(x for x in out.split() if "." in x)
        except (OSError, subprocess.SubprocessError):
            pass
    return ips


def lan_addresses():
    """This machine's IP addresses, for printing the URLs other computers can use."""
    ips = _interface_addresses()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; picks the default-route address
            ips.add(s.getsockname()[0])
    except OSError:
        pass  # offline server without a default route - the interface list above covers it
    bad = ("127.", "169.254.", "0.")
    return sorted((ip for ip in ips if not ip.startswith(bad)),
                  key=lambda ip: (ip.startswith("172.17."), ip))  # list Docker's bridge last


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


def build_messages(history, analysis=None, num_ctx=4096):
    # System prompt first and unchanged, then the analysis: Ollama reuses its cache for this
    # identical prefix, so follow-up questions only process the new tokens.
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if analysis and analysis.get("incidents") is not None:
        budget = max(3000, int(num_ctx) * 3 - 5000)  # leave room for the question and the answer
        msgs.append({"role": "system", "content": investigator.AGENT_RULES + "\n\nFACTS:\n" +
                     investigator.case_file(analysis, budget)})
    elif analysis:
        msgs.append({"role": "system",
                     "content": "Current analysis results:\n" + detector.ai_context(analysis)})
    for m in history[-MAX_HISTORY:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"]})
    return msgs


DEFAULT_LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="40 50 170 230"><path d="M120,58 L200,74 L200,150 C200,208 168,244 120,270 C72,244 40,208 40,150 L40,74 Z" fill="#123E6B" stroke="#2f6db0" stroke-width="4"/><circle cx="122" cy="196" r="48" fill="#1E9E4F"/><circle cx="122" cy="196" r="27" fill="#123E6B"/><rect x="122" y="184" width="68" height="24" fill="#123E6B"/><rect x="148" y="193" width="32" height="13" fill="#1E9E4F"/><rect x="167" y="193" width="13" height="23" fill="#1E9E4F"/><rect x="74" y="92" width="96" height="22" fill="#F59E1E"/><rect x="112" y="112" width="20" height="66" fill="#F59E1E"/></svg>"""

LOGIN_TOKEN = """<p>Enter the access token shown in the agent's terminal (or run <code>python3 agent.py info</code>
on the server).</p><input id="t" type="password" placeholder="Access token" autofocus autocomplete="current-password">"""
LOGIN_PASSWORD = """<input id="u" placeholder="Username" autofocus autocomplete="username" autocapitalize="none"
style="margin-bottom:10px"><input id="pw" type="password" placeholder="Password" autocomplete="current-password">"""
LOGIN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>CyberSec AI Agent - Sign in</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0a111c;color:#e4ebf3;
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}form{background:#111a27;border:1px solid #24344a;
border-radius:14px;padding:28px;width:min(360px,90vw);box-shadow:0 6px 18px rgba(0,0,0,.3)}h1{font-size:18px;margin:0 0 4px}
p{color:#7d8da1;font-size:13px;margin:0 0 18px}input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;
border:1px solid #24344a;background:#162232;color:#e4ebf3;font:inherit}button{margin-top:14px;width:100%;padding:10px;
border:0;border-radius:8px;background:#1E9E4F;color:#fff;font:inherit;font-weight:600;cursor:pointer}
#e{color:#ff4d6a;font-size:13px;min-height:18px;margin-top:10px}</style></head><body>
<form id="f">{LOGO}
<h1 style="text-align:center">{APP}</h1>{ORG}{FIELDS}
<button>Sign in</button><div id="e"></div></form>
<script>document.getElementById("f").onsubmit=async(ev)=>{ev.preventDefault();
const v=(id)=>{const el=document.getElementById(id);return el?el.value:"";};
const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({token:v("t"),username:v("u"),password:v("pw")})});
if(r.ok){location.reload();return;}
const j=await r.json().catch(()=>({}));document.getElementById("e").textContent=j.error||"Sign-in failed.";};</script>
</body></html>"""


INVESTIGATE_PROMPT = ("Investigate these findings. Start with a 2-3 sentence executive summary paragraph "
                      "(no heading). Then: ## Attack story (what happened, step by step, with times), "
                      "## Confidence & false positives, ## Top 5 actions now (with commands).")


def _html(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


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
    if kind == "investigation":
        return investigation_markdown(analysis)
    raise ValueError("unknown instant answer")


def investigation_markdown(analysis):
    """Deterministic investigation (no AI) rendered for the chat."""
    if analysis.get("incidents") is None:
        return knowledge.playbook_markdown(analysis)
    inv = investigator.investigate(analysis)
    out = [inv["summary"]]
    for i in inv["incidents"][:3]:
        out.append(f"\n### {i['id']} - {i['status']} (risk {i['risk']}/100)")
        src = next((x for x in analysis.get("incidents", []) if x.get("id") == i["id"]), {})
        if src.get("attack_path"):
            out.append(f"**Attack path:** {src['attack_path']}")
        out += [f"- **{s['ts'][11:16] if s['ts'] else '?'} {s['stage']}**: {s['text']}"
                + (f" → _{s['action']}_ ({s['action_by']})" if s.get("action") else "") + f" [{', '.join(s['evidence'])}]"
                for s in i["story"][:14]]
        out.append("\n**Hypotheses**")
        out += [f"- ({h['status']}) {h['statement']} [{', '.join(h['evidence'][:3])}]" for h in i["hypotheses"]]
        if i["gaps"]:
            out.append("\n**Evidence gaps**")
            out += [f"- {g}" for g in i["gaps"][:4]]
        if i["queries"]:
            out.append("\n**Suggested read-only query (Splunk)**\n```\n" + i["queries"][0]["splunk"] + "\n```")
    if not inv["incidents"]:
        out.append("No correlated incidents. See the findings list for individual detections.")
    return "\n".join(out)


# ---------------------------------------------------------------- analysis store
_ANALYSES = OrderedDict()
_ANALYSES_MAX = 4


def remember(result):
    aid = secrets.token_hex(8)
    result["analysis_id"] = aid
    _ANALYSES[aid] = result
    while len(_ANALYSES) > _ANALYSES_MAX:
        _ANALYSES.popitem(last=False)
    return result


def recall(body):
    aid = str(body.get("analysis_id") or "")
    a = _ANALYSES.get(aid)
    if a is None and history.exists(aid):  # older analysis: load it back from the history
        a = history.load(aid)
        if a is not None:
            _ANALYSES[aid] = a
            while len(_ANALYSES) > _ANALYSES_MAX:
                _ANALYSES.popitem(last=False)
    return a if a is not None else body.get("analysis")


def persist(analysis):
    """Save later additions (AI text, reputation, verdicts) to the stored analysis, if it is stored."""
    if isinstance(analysis, dict) and history.exists(analysis.get("analysis_id")):
        try:
            history.update_result(analysis)
        except OSError:
            pass


def finish(cfg, result, kind, name, files=(), move=False, actor="", samples=()):
    """Every new analysis: give it an id, apply what was learned, store it in the history."""
    remember(result)
    if cfg.get("learn_from_data", True) and result.get("findings") is not None:
        try:
            memory.annotate(result)
        except (OSError, ValueError, KeyError) as e:
            result.setdefault("warnings", []).append(f"Learning memory not applied: {e}")
    if cfg.get("history_enabled", True):
        try:
            history.save(result, kind, name, files if cfg.get("store_logs", True) else (), move=move,
                         actor=actor, samples=samples)
            history.enforce_retention(cfg.get("history_max_days") or 0, cfg.get("history_max_gb") or 0)
            if cfg.get("learn_from_data", True):
                memory.record_sightings(result, name)
        except OSError as e:
            result.setdefault("warnings", []).append(f"Could not store this analysis in the history: {e}")
    result["stored"] = history.exists(result.get("analysis_id"))
    return result


def learned_feeds(cfg):
    return memory.learned_feed_paths() if cfg.get("learn_from_data", True) else None


SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-]+")


def safe_filename(name):
    name = SAFE_NAME.sub("_", Path(str(name or "upload.log")).name).strip("._") or "upload.log"
    return name[:120]


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

    # ---- access control
    # Password set (python3 agent.py set-password): username + password, on every address, token not accepted.
    # Otherwise the access token, which is generated automatically when listening on the network.
    def _cookie(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return ""

    def _user(self):
        """Signed-in user name, or None. 'local' when no login is configured."""
        if password_mode(self.cfg):
            return check_session(self.cfg, self._cookie("tg_session"))
        token = self.cfg.get("access_token")
        if not token:
            return "local"
        sent = self.headers.get("X-Agent-Token", "") or self._cookie("tg_token")
        return "token-user" if hmac.compare_digest(sent.encode(), token.encode()) else None

    def _authorized(self):
        return self._user() is not None

    def _login(self, body):
        ip = self.client_address[0]
        if _locked_out(ip):
            return self._send(429, {"error": "Too many failed sign-ins. Wait 15 minutes and try again."})
        if password_mode(self.cfg):
            ok = (hmac.compare_digest(str(body.get("username", "")).strip().encode(), str(self.cfg.get("username")).encode())
                  & check_password(str(body.get("password", "")), self.cfg["password_hash"]))
            if not ok:
                _record_fail(ip)
                time.sleep(1.5)  # slow down guessing
                return self._send(401, {"error": "Wrong username or password."})
            config_store.audit(f"{self.cfg['username']}@{ip}", "login", "sign_in", "", {}, {})
            cookie = (f"tg_session={make_session(self.cfg, self.cfg['username'])}; HttpOnly; SameSite=Strict; Path=/; "
                      f"Max-Age={int(float(self.cfg.get('session_hours') or 12) * 3600)}")
            return self._send(200, {"ok": True}, headers={"Set-Cookie": cookie})
        token = self.cfg.get("access_token") or ""
        if not token or not hmac.compare_digest(str(body.get("token", "")).encode(), token.encode()):
            _record_fail(ip)
            time.sleep(1.5)  # slow down guessing
            return self._send(401, {"error": "Wrong token - try again."})
        cookie = f"tg_token={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000"
        return self._send(200, {"ok": True}, headers={"Set-Cookie": cookie})

    def _logout(self):
        expired = "; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
        return self._send(200, {"ok": True}, headers={"Set-Cookie": "tg_session=" + expired})

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/branding/logo":
            data, ctype = branding.logo_bytes(branding.load())
            return self._send(200, data, ctype) if data else self._send(200, DEFAULT_LOGO_SVG, "image/svg+xml")
        if not self._authorized():
            if path in ("/", "/index.html"):
                b = branding.load()
                show = self.cfg.get("ui_show_branding", True)
                page = LOGIN_PAGE.replace("{APP}", _html(b["application_name"])) \
                    .replace("{LOGO}", '<img src="/branding/logo" alt="" style="height:54px;display:block;margin:0 auto 10px">'
                             if show else "") \
                    .replace("{ORG}", f'<p style="text-align:center">{_html(b["organisation_name"])}</p>' if show else "") \
                    .replace("{FIELDS}", LOGIN_PASSWORD if password_mode(self.cfg) else LOGIN_TOKEN)
                return self._send(200, page, "text/html; charset=utf-8")
            return self._send(401, {"error": "login required"})
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/status":
            return self._send(200, self._status())
        if path == "/api/trust":
            inv = trust.Inventory.load()
            return self._send(200, {"data": inv.data, "errors": inv.errors, "sections": trust.SECTION_LABELS,
                                    "classes": trust.TRUST_CLASSES, "asset_types": trust.ASSET_TYPES,
                                    "criticality": trust.CRITICALITY, "summary": inv.summary(),
                                    "precedence": trust.__doc__})
        if path == "/api/trust/export":
            inv = trust.Inventory.load()
            fmt = (parse_qs(urlparse(self.path).query).get("format") or ["json"])[0]
            if fmt == "csv":
                return self._send(200, trust.export_csv(inv), "text/csv; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="trusted_assets.csv"'})
            return self._send(200, json.dumps(inv.data, indent=2), "application/json",
                              {"Content-Disposition": 'attachment; filename="trusted_assets.json"'})
        if path == "/api/branding":
            if self.cfg.get("ui_hide_branding_page"):
                return self._send(403, {"error": BRANDING_LOCKED})
            return self._send(200, branding.load())
        if path == "/api/history":
            return self._send(200, {"items": history.list_all(), "usage": history.usage(),
                                    "enabled": bool(self.cfg.get("history_enabled", True)),
                                    "store_logs": bool(self.cfg.get("store_logs", True))})
        if path == "/api/history/file":
            q = parse_qs(urlparse(self.path).query)
            aid, name = (q.get("id") or [""])[0], (q.get("name") or [""])[0]
            fp = history.file_path(aid, name) if history.valid_id(aid) else None
            if not fp:
                return self._send(404, {"error": "file not found"})
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(fp.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{safe_filename(name)}"')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with open(fp, "rb") as fh:
                shutil.copyfileobj(fh, self.wfile, 1 << 20)
            return None
        if path == "/api/memory":
            return self._send(200, memory.summary())
        if path == "/api/audit-log":
            return self._send(200, {"entries": config_store.read_audit(200)})
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
                "platform": sys.platform, "branding": _public_branding(),
                "login": "password" if password_mode(cfg) else "token" if cfg.get("access_token") else "none",
                "user": self._user() if password_mode(cfg) else None,
                "ui_show_branding": bool(cfg.get("ui_show_branding", True)),
                "history_enabled": bool(cfg.get("history_enabled", True)), "store_logs": bool(cfg.get("store_logs", True)),
                "history_max_days": cfg.get("history_max_days") or 0, "learn_from_data": bool(cfg.get("learn_from_data", True)),
                "reputation_providers": reputation.providers(cfg), "reputation_auto": bool(cfg.get("reputation_auto")),
                "has_abuseipdb_key": bool(cfg.get("abuseipdb_key")), "has_virustotal_key": bool(cfg.get("virustotal_key")),
                "reputation_quota": reputation.quota_used(),
                "ui_hide_branding_page": bool(cfg.get("ui_hide_branding_page")),
                "trust_entries": trust.Inventory.load().enabled_count,
                "learn_baseline": bool(cfg.get("learn_baseline", True)), "tz_hours": cfg.get("tz_hours", 0),
                "max_upload_mb": cfg.get("max_upload_mb", 512),
                "samples": sorted(p.name for p in SAMPLES.glob("*.log")),
                "siem_samples": sorted(p.name for p in (SAMPLES / "siem").glob("*")
                                       if p.suffix in (".csv", ".jsonl", ".json", ".cef", ".log", ".xml")
                                       and "demo" not in p.name and "ioc" not in p.name)}
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
        ctype = (self.headers.get("Content-Type") or "")
        return ctype.startswith("application/json") or (
            ctype.startswith("application/octet-stream") and self.path.startswith("/api/upload"))

    def _actor(self):
        who = self._user() or "anonymous"
        return f"{'local-user' if who == 'local' else who}@{self.client_address[0]}"

    def do_POST(self):
        if not self._trusted():
            return self._send(403, {"error": "forbidden"})
        if self.path.startswith("/api/upload"):
            if not self._authorized():
                return self._send(401, {"error": "login required"})
            return self._upload()
        try:
            body = self._json_body()
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        if not isinstance(body, dict):
            return self._send(400, {"error": "expected a JSON object"})
        path = self.path.split("?", 1)[0]
        if path == "/api/login":
            return self._login(body)
        if path == "/api/logout":
            return self._logout()
        if not self._authorized():
            return self._send(401, {"error": "login required"})
        if path == "/api/analyze":
            text = body.get("text") or ""
            if not text.strip():
                return self._send(400, {"error": "No log text supplied"})
            display = str(body.get("name") or "pasted log")[:80]
            config_store.ensure_dirs()
            tmp = config_store.UPLOAD_DIR / f"paste-{secrets.token_hex(8)}.log"
            tmp.write_text(text, encoding="utf-8")
            os.chmod(tmp, 0o600)
            try:
                res = pipeline.analyze_files([(tmp, display)], tz_hours=float(self.cfg.get("tz_hours") or 0),
                                             learn_baseline=bool(self.cfg.get("learn_baseline", True)),
                                             extra_ioc_paths=learned_feeds(self.cfg))
                name = safe_filename(display)
                out = finish(self.cfg, pipeline.to_json(res), "paste", display,
                             [(tmp, name if Path(name).suffix else name + ".log")], move=True, actor=self._actor())
            finally:
                tmp.unlink(missing_ok=True)
            return self._send(200, out)
        if path == "/api/analyze-batch":
            return self._analyze_batch(body)
        if path == "/api/analyze-sample":
            files = sorted(p for p in (SAMPLES / "siem").glob("*") if p.suffix in (".csv", ".jsonl", ".json", ".cef",
                           ".log", ".xml") and "demo" not in p.name and "ioc" not in p.name)
            res = pipeline.analyze_files([(p, p.name) for p in files], learn_baseline=False,
                                         extra_ioc_paths=[SAMPLES / "siem" / "ioc_feed.csv"])
            return self._send(200, finish(self.cfg, pipeline.to_json(res), "sample", "SIEM sample dataset",
                                          actor=self._actor(), samples=[p.name for p in files]))
        if path.startswith("/api/trust/"):
            return self._trust(path, body)
        if path.startswith("/api/history/"):
            return self._history(path, body)
        if path == "/api/reputation/check":
            return self._reputation(body)
        if path == "/api/reputation/candidates":
            a = recall(body)
            if not isinstance(a, dict):
                return self._send(400, {"error": "run an analysis first"})
            return self._send(200, {"candidates": reputation.candidates(
                a, trust.Inventory.load(), allow_documentation=bool(self.cfg.get("reputation_allow_documentation"))),
                "providers": reputation.providers(self.cfg), "done": a.get("reputation") or {}})
        if path == "/api/feedback":
            return self._feedback(body)
        if path == "/api/memory/forget":
            if body.get("all"):
                memory.forget_all(self._actor())
                return self._send(200, memory.summary())
            ok = memory.forget(str(body.get("key")), self._actor()) if body.get("key") else \
                memory.forget_reputation(str(body.get("value")), self._actor())
            return self._send(200 if ok else 404, memory.summary())
        if path in ("/api/branding", "/api/branding/logo") and self.cfg.get("ui_hide_branding_page"):
            return self._send(403, {"error": BRANDING_LOCKED})
        if path == "/api/branding":
            try:
                return self._send(200, branding.save(body.get("branding") or {}, self._actor(),
                                                     bool(body.get("confirm_replace"))))
            except PermissionError as e:
                return self._send(409, {"error": str(e), "needs_confirmation": True})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
        if path == "/api/branding/logo":
            try:
                return self._send(200, branding.store_logo(body.get("data_b64") or "", self._actor()))
            except ValueError as e:
                return self._send(400, {"error": str(e)})
        if path == "/api/config":
            return self._update_config(body)
        if path == "/api/chat":
            return self._chat(body)
        if path == "/api/audit":
            return self._send(200, finish(self.cfg, host_audit.run_audit(include_logs=body.get("include_logs", True)),
                                          "host", f"Host audit of {socket.gethostname()}", actor=self._actor()))
        if path == "/api/instant":
            try:
                md = instant_answer(body.get("kind"), recall(body) or {}, body.get("index"))
            except (ValueError, KeyError, IndexError, TypeError) as e:
                return self._send(400, {"error": f"cannot answer: {e}"})
            return self._send(200, {"markdown": md})
        if path == "/api/report/pdf":
            return self._pdf(body)
        if path == "/api/warmup":
            threading.Thread(target=warmup, args=(self.cfg,), daemon=True).start()
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    # ------------------------------------------------------------ uploads & analysis
    def _upload(self):
        q = parse_qs(urlparse(self.path).query)
        batch = (q.get("batch") or [""])[0] or secrets.token_hex(8)
        if not re.fullmatch(r"[a-f0-9]{16}", batch):
            return self._send(400, {"error": "bad batch id"})
        name = safe_filename(self.headers.get("X-Filename") or (q.get("name") or ["upload.log"])[0])
        length = int(self.headers.get("Content-Length") or 0)
        limit = int(self.cfg.get("max_upload_mb", 512)) * 1024 * 1024
        if length <= 0:
            return self._send(400, {"error": "empty upload"})
        if length > limit:
            return self._send(413, {"error": f"file larger than {limit // 1024 // 1024} MB"})
        config_store.ensure_dirs()
        d = config_store.UPLOAD_DIR / batch
        d.mkdir(mode=0o700, exist_ok=True)
        dest = d / name
        n = 1
        while dest.exists():
            dest = d / f"{Path(name).stem}-{n}{Path(name).suffix}"
            n += 1
        left = length
        with open(dest, "wb") as fh:  # stream to disk; never hold the whole file in memory
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                fh.write(chunk)
                left -= len(chunk)
        os.chmod(dest, 0o600)
        return self._send(200, {"batch": batch, "file": dest.name, "bytes": length - left})

    def _analyze_batch(self, body):
        batch = str(body.get("batch") or "")
        if not re.fullmatch(r"[a-f0-9]{16}", batch):
            return self._send(400, {"error": "bad batch id"})
        d = config_store.UPLOAD_DIR / batch
        files = sorted(p for p in d.glob("*") if p.is_file()) if d.exists() else []
        if not files:
            return self._send(400, {"error": "no uploaded files in this batch"})
        stored = None
        try:
            res = pipeline.analyze_files([(p, p.name) for p in files],
                                         tz_hours=float(body.get("tz_hours", self.cfg.get("tz_hours") or 0)),
                                         learn_baseline=bool(body.get("learn_baseline", self.cfg.get("learn_baseline", True))),
                                         extra_ioc_paths=learned_feeds(self.cfg))
            name = str(body.get("name") or "") or (files[0].name if len(files) == 1 else f"{len(files)} files: " +
                                                   ", ".join(p.name for p in files[:3]) + (" ..." if len(files) > 3 else ""))
            stored = finish(self.cfg, pipeline.to_json(res), "upload", name[:160], [(p, p.name) for p in files],
                            move=True, actor=self._actor())
        finally:
            if not self.cfg.get("keep_uploads"):
                for p in files:
                    p.unlink(missing_ok=True)
                try:
                    d.rmdir()
                except OSError:
                    pass
        return self._send(200, stored)

    # ------------------------------------------------------------ history, reputation, learning
    def _history(self, path, body):
        actor = self._actor()
        aid = str(body.get("id") or "")
        if path == "/api/history/delete":
            if body.get("all"):
                for m in history.list_all():
                    memory.forget_analysis(m["id"])
                return self._send(200, {"deleted": history.delete_all(actor)})
            ids = body.get("ids") or [aid]
            n = 0
            for i in ids:
                if history.valid_id(i) and history.delete(i, actor):
                    memory.forget_analysis(i)
                    _ANALYSES.pop(i, None)
                    n += 1
            return self._send(200 if n else 404, {"deleted": n} if n else {"error": "not found"})
        if not history.exists(aid):
            return self._send(404, {"error": "This analysis is no longer in the history."})
        if path == "/api/history/open":
            a = recall({"analysis_id": aid})
            bad = history.verify(aid)
            if bad:
                a.setdefault("warnings", []).append("Stored log file(s) changed since they were stored "
                                                    f"(SHA-256 mismatch): {', '.join(bad)}")
            return self._send(200, a)
        if path == "/api/history/reanalyse":
            m = history.meta(aid)
            if m.get("kind") == "sample":
                files = [(SAMPLES / "siem" / n, n) for n in m.get("samples", []) if (SAMPLES / "siem" / n).is_file()]
                extra = [SAMPLES / "siem" / "ioc_feed.csv"]
            else:
                files, extra = history.log_files(aid), []
            if not files:
                return self._send(400, {"error": "No stored log files for this analysis (store_logs was off, "
                                                 "or it was a host audit)."})
            bad = history.verify(aid)
            if bad:
                return self._send(409, {"error": f"Stored log file(s) changed since they were stored: {', '.join(bad)}"})
            res = pipeline.analyze_files(files, tz_hours=float(self.cfg.get("tz_hours") or 0), learn_baseline=False,
                                         extra_ioc_paths=extra + (learned_feeds(self.cfg) or []))
            name = f"{m.get('name', 'analysis')} (re-analysed)"[:160]
            out = finish(self.cfg, pipeline.to_json(res), m.get("kind", "upload"), name,
                         files if m.get("kind") != "sample" else (), actor=actor, samples=m.get("samples", []))
            return self._send(200, out)
        return self._send(404, {"error": "not found"})

    def _reputation(self, body):
        analysis = recall(body) if body.get("analysis_id") else None
        try:
            res = reputation.lookup(self.cfg, body.get("value"), trust.Inventory.load(), force=bool(body.get("force")))
        except reputation.RefusedError as e:
            return self._send(422, {"error": str(e), "refused": True})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        if not res.get("cached"):
            config_store.audit(self._actor(), "reputation", "lookup", res["value"], None,
                               {"verdict": res["verdict"], "providers": reputation.providers(self.cfg)})
        if self.cfg.get("learn_from_data", True):
            memory.learn_reputation(res, self._actor())
        if isinstance(analysis, dict):
            analysis.setdefault("reputation", {})[res["value"]] = res
            persist(analysis)
        return self._send(200, res)

    def _feedback(self, body):
        analysis = recall(body)
        if not isinstance(analysis, dict):
            return self._send(400, {"error": "analysis not found"})
        f = next((x for x in analysis.get("findings") or [] if x.get("fid") == body.get("fid")), None)
        if not f:
            return self._send(404, {"error": "finding not found"})
        try:
            v = memory.record_verdict(f, str(body.get("verdict")), body.get("note"), self._actor(),
                                      analysis.get("analysis_id"), analysis)
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        if v:
            f["analyst_verdict"] = {k: v.get(k) for k in ("verdict", "note", "actor", "time", "analysis_id")}
            f["analyst_verdict"]["label"] = memory.VERDICTS[v["verdict"]]
        else:
            f.pop("analyst_verdict", None)
        persist(analysis)
        return self._send(200, {"finding": f, "learned": len(memory.learned_indicators())})

    # ------------------------------------------------------------ trusted networks & assets
    def _trust(self, path, body):
        inv = trust.Inventory.load()
        actor = self._actor()
        try:
            if path == "/api/trust/entry":
                e = trust.upsert(inv, body.get("section"), body.get("entry") or {}, actor)
                return self._send(200, {"entry": e, "summary": inv.summary()})
            if path == "/api/trust/delete":
                trust.remove(inv, body.get("section"), body.get("id"), actor)
                return self._send(200, {"ok": True})
            if path in ("/api/trust/import/preview", "/api/trust/import/apply"):
                fmt = "csv" if str(body.get("format", "")).lower() == "csv" else "json"
                raw = trust.parse_import(str(body.get("text") or ""), fmt)
                mode = "replace" if body.get("mode") == "replace" else "merge"
                if path.endswith("preview"):
                    p = trust.preview_import(inv, raw, mode)
                    p.pop("valid")
                    return self._send(200, p)
                p = trust.apply_import(inv, raw, mode, actor)
                p.pop("valid")
                return self._send(200, p)
            if path == "/api/trust/classify":
                return self._send(200, inv.classify(str(body.get("ip") or "")))
        except (ValueError, KeyError, TypeError) as e:
            return self._send(400, {"error": str(e)})
        return self._send(404, {"error": "not found"})

    def _pdf(self, body):
        if not report_pdf.AVAILABLE:
            return self._send(501, {"error": "PDF reports need reportlab. Install it with:  pip install reportlab"})
        analysis = recall(body)
        if not isinstance(analysis, dict) or "findings" not in analysis:
            return self._send(400, {"error": "run an analysis first"})
        meta = {k: str(v)[:200] for k, v in (body.get("meta") or {}).items()
                if k in ("client", "assessor", "ref", "source", "scope_note")}
        ai = analysis.get("ai_investigation") or {}
        ai_text = str(body.get("ai_text") or ai.get("text") or "")
        meta["model"] = (ai.get("model") or self.cfg.get("model")) if ai_text else ""
        b = branding.load()
        brand = dict(self.cfg.get("report") or {}, **branding.report_brand(b))
        try:
            pdf = report_pdf.build_pdf(analysis, meta, ai_text, brand)
        except Exception as e:  # report must never take the server down
            return self._send(500, {"error": f"PDF generation failed: {e}"})
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(pdf)))
        self.send_header("Content-Disposition", f'attachment; filename="{b["filename_prefix"]}-{datetime.now():%Y%m%d-%H%M}.pdf"')
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
        for key in ("history_enabled", "store_logs", "learn_from_data", "reputation_auto"):
            if key in body:
                cfg[key] = bool(body[key])
        if "history_max_days" in body:
            try:
                cfg["history_max_days"] = max(0, int(body["history_max_days"] or 0))
            except (TypeError, ValueError):
                return self._send(400, {"error": "history_max_days must be a number"})
        for key in ("abuseipdb_key", "virustotal_key"):
            if isinstance(body.get(key), str) and body[key] != "********":
                if body[key].strip() and not re.fullmatch(r"[A-Za-z0-9_\-]{16,128}", body[key].strip()):
                    return self._send(400, {"error": f"{key} does not look like an API key"})
                cfg[key] = body[key].strip()
        if "ui_show_branding" in body and not cfg.get("ui_hide_branding_page"):  # locked with the page
            cfg["ui_show_branding"] = bool(body["ui_show_branding"])
        if "learn_baseline" in body:
            cfg["learn_baseline"] = bool(body["learn_baseline"])
        if "tz_hours" in body:
            try:
                cfg["tz_hours"] = max(-14.0, min(14.0, float(body["tz_hours"])))
            except (TypeError, ValueError):
                return self._send(400, {"error": "tz_hours must be a number"})
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
        analysis = recall(body) if (body.get("investigate") or body.get("use_context", True)) else None
        new_pipeline = bool(analysis and analysis.get("incidents") is not None)
        if body.get("investigate"):
            prompt = investigator.INVESTIGATE_PROMPT if new_pipeline else INVESTIGATE_PROMPT
            history = history + [{"role": "user", "content": prompt}]
        messages = build_messages(history, analysis, self.cfg.get("num_ctx", 4096))
        parts = []
        # Plain streaming response; the connection closes when the reply is done.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            for chunk in stream_chat(self.cfg, messages):
                parts.append(chunk)
                self.wfile.write(chunk.encode())
                self.wfile.flush()
            reply = "".join(parts)
            if new_pipeline and reply.strip():
                v = investigator.validate(reply, analysis)
                self.wfile.write(investigator.validation_footer(v).encode())
                if body.get("investigate"):
                    analysis["ai_investigation"] = {"text": reply, "validation": v, "model": self.cfg.get("model"),
                                                    "time": datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")}
                    persist(analysis)
        except (BrokenPipeError, ConnectionResetError):
            pass  # user pressed Stop
        except (LLMError, ValueError) as e:
            self.wfile.write(f"\n\n[error] {e}".encode())


def serve(cfg, open_browser=True):
    Handler.cfg = cfg
    on_network = not is_local_only(cfg)
    if password_mode(cfg) and not cfg.get("session_secret"):
        cfg["session_secret"] = secrets.token_hex(32)
        save_config(cfg, ("session_secret",))
    if on_network and not password_mode(cfg) and not cfg.get("access_token"):
        cfg["access_token"] = secrets.token_urlsafe(18)
        save_config(cfg, ("access_token",))
    server_cls = ThreadingHTTPServer
    if ":" in cfg["host"]:  # IPv6 address such as "::"
        server_cls = type("V6Server", (ThreadingHTTPServer,), {"address_family": socket.AF_INET6})
    try:
        httpd = server_cls((cfg["host"], cfg["port"]), Handler)
    except OSError as e:
        if e.errno == 98:  # EADDRINUSE
            sys.exit(f"\n  [!] Port {cfg['port']} is already in use - the agent is probably already running"
                     " (e.g. as the cybersec-agent service).\n"
                     "      Restart it with:  sudo systemctl restart cybersec-agent\n"
                     "      Show its address and token:  python3 agent.py info\n")
        if e.errno == 99:  # EADDRNOTAVAIL
            sys.exit(f"\n  [!] {cfg['host']} is not an IP address of this machine. Its IPs are: "
                     f"{', '.join(lan_addresses()) or 'none'}\n      Or use \"host\": \"0.0.0.0\" for all of them.\n")
        raise
    urls = agent_urls(cfg)
    print(f"\n  CyberSec AI Agent v{VERSION}")
    print(f"  Config : {CONFIG_FILE}  (host {cfg['host']}, port {cfg['port']})")
    for u in urls:
        print(f"  Web UI : {u}")
    if not on_network:
        print(f'  [i] Only this computer can open it. To use the server IP, set "host": "0.0.0.0" in {CONFIG_FILE}')
    elif cfg["host"] in ("0.0.0.0", "", "::") and len(urls) == 1:
        print("  [!] No network IP found on this machine - check with:  ip -4 addr")
    print(f"  AI     : {cfg['provider']} @ {cfg['base_url']} (model: {cfg['model'] or 'auto'})")
    if password_mode(cfg):
        print(f"  Login  : username '{cfg['username']}' + password  (change: python3 agent.py set-password)")
    elif on_network:
        print(f"  Access token: {cfg['access_token']}   (stored in {CONFIG_FILE.name})")
        print("  [i] Prefer a password? Run:  python3 agent.py set-password")
    if on_network:
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
    for inc in result.get("incidents") or []:
        print(f"{inc['id']} [{inc['severity'].upper()}] risk {inc['risk']['score']}/100 - {inc['status']}")
        print(f"   {inc['title'][:150]}")
    if result.get("incidents"):
        print()
    for f in result["findings"]:
        c = COLORS[f["severity"]] if color else ""
        risk = f" risk {f['risk']['score']}" if f.get("risk") else ""
        print(f"{c}[{f['severity'].upper():8}]{reset} {f.get('fid', '')} {f.get('rule_id', '')} {f['title']}  "
              f"x{f['count']}{risk}  ({f['mitre']})  {', '.join(f['ips'][:3])}")
        for s in f["samples"][:2]:
            where = f"{s['ref']}: " if s.get("ref") else f"L{s['line']}: " if s.get("line") else ""
            print(f"           {where}{s['text'][:140]}")
    if not result["findings"]:
        print("No issues found.")


def cli_report(cfg, args, result, source):
    ai_text = ""
    new_pipeline = result.get("incidents") is not None
    if new_pipeline:
        print("\n--- Investigation (deterministic, no AI) ---\n")
        print(investigation_markdown(result))
    if args.ai:
        print("\n--- AI investigation ---\n")
        try:
            prompt = investigator.INVESTIGATE_PROMPT if new_pipeline else INVESTIGATE_PROMPT
            msgs = build_messages([{"role": "user", "content": prompt}], result, cfg.get("num_ctx", 4096))
            parts = []
            for chunk in stream_chat(cfg, msgs):
                parts.append(chunk)
                print(chunk, end="", flush=True)
            ai_text = "".join(parts)
            if new_pipeline:
                print(investigator.validation_footer(investigator.validate(ai_text, result)))
            print()
        except LLMError as e:
            print(f"[AI unavailable - deterministic analysis above is complete] {e}", file=sys.stderr)
    if args.pdf:
        if not report_pdf.AVAILABLE:
            sys.exit("PDF reports need reportlab:  pip install reportlab")
        meta = {"source": source, "client": args.client or "", "assessor": args.assessor or "",
                "model": cfg.get("model") if ai_text else ""}
        brand = dict(cfg.get("report") or {}, **branding.report_brand(branding.load()))
        Path(args.pdf).write_bytes(report_pdf.build_pdf(result, meta, ai_text, brand))
        print(f"\nPDF report saved: {args.pdf}")


def _public_branding():
    b = branding.load()
    return {k: b[k] for k in ("application_name", "organisation_name", "report_title", "primary_colour",
                              "accent_colour", "highlight_colour", "footer_text", "logo_url", "classification")}


def cli_info(cfg):
    print(f"Config file : {CONFIG_FILE} ({'found' if CONFIG_FILE.exists() else 'NOT FOUND - using defaults'})")
    print(f"Listening on: {cfg['host']}:{cfg['port']}")
    for u in agent_urls(cfg):
        print(f"Web UI      : {u}")
    if password_mode(cfg):
        print(f"Login       : username '{cfg.get('username')}' + password (python3 agent.py set-password to change)")
    if is_local_only(cfg):
        print(f'Only this computer can open it. To use the server IP add  "host": "0.0.0.0",  to {CONFIG_FILE.name}')
    elif not password_mode(cfg):
        print(f"Access token: {cfg.get('access_token') or '(created on next start)'}")
    print(f"Network IPs : {', '.join(lan_addresses()) or 'none found'}")


def cli_set_password(cfg, args):
    """Set or change the web login. Run on the server; the password is stored only as a salted hash."""
    import getpass
    user = (args.user or cfg.get("username") or "").strip()
    if not user:
        user = input("Username [admin]: ").strip() or "admin"
    if not re.fullmatch(r"[A-Za-z0-9._@-]{1,40}", user):
        sys.exit("Username may only contain letters, digits and . _ @ - (max 40 characters).")
    pw = getpass.getpass(f"New password for '{user}' (min {MIN_PASSWORD} characters): ")
    if len(pw) < MIN_PASSWORD:
        sys.exit(f"Password too short - use at least {MIN_PASSWORD} characters.")
    if pw.lower() in (user.lower(), "password12", "password123", "1234567890", "qwertyuiop") or len(set(pw)) < 4:
        sys.exit("That password is too easy to guess - choose another.")
    if getpass.getpass("Repeat the password: ") != pw:
        sys.exit("The passwords don't match - nothing changed.")
    cfg.update(username=user, password_hash=hash_password(pw), session_secret=secrets.token_hex(32))
    save_config(cfg, ("username", "password_hash", "session_secret"))
    config_store.audit(f"cli@{socket.gethostname()}", "login", "set_password", CONFIG_FILE.name, {}, {"username": user})
    print(f"Password login enabled for '{user}'. The access token is no longer accepted and everyone signed in\n"
          "must sign in again. Restart the agent to apply it:  sudo systemctl restart cybersec-agent  "
          "(or stop and start python3 agent.py)")


def cli_remove_password(cfg):
    if not password_mode(cfg):
        return print("No password is set.")
    cfg.update(username="", password_hash="", session_secret="")
    save_config(cfg, ("username", "password_hash", "session_secret"))
    config_store.audit(f"cli@{socket.gethostname()}", "login", "remove_password", CONFIG_FILE.name, {}, {})
    print("Password removed. After a restart the agent uses the access token again on the network\n"
          "(shown by: python3 agent.py info).")


def cli_scan(cfg, args):
    files = [(Path(f), Path(f).name) for f in args.files]
    for p, _ in files:
        if not p.is_file():
            sys.exit(f"File not found: {p}")
    inv = trust.Inventory(json.loads(Path(args.trust).read_text())) if args.trust else None
    result = pipeline.to_json(pipeline.analyze_files(
        files, tz_hours=float(cfg.get("tz_hours") or 0), inventory=inv,
        learn_baseline=bool(cfg.get("learn_baseline", True)) and not args.no_learn,
        extra_ioc_paths=[Path(x) for x in args.ioc or []] + (learned_feeds(cfg) or [])))
    if cfg.get("learn_from_data", True):
        memory.annotate(result)
    if args.json:
        return print(json.dumps(result, indent=2))
    print_result(result)
    cli_report(cfg, args, result, ", ".join(n for _, n in files))


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
    sub.add_parser("info", help="show the web address, access token and config in use")
    sp_pw = sub.add_parser("set-password", help="use a username + password for the web login instead of the token")
    sp_pw.add_argument("--user", help="login name (default: current one, or admin)")
    sub.add_parser("remove-password", help="remove the password login and go back to the access token")
    s = sub.add_parser("scan", help="analyse SIEM exports / log files from the terminal")
    s.add_argument("files", nargs="+", help="CSV, JSON, JSONL, XML, CEF, syslog or text logs (.gz ok)")
    s.add_argument("--trust", metavar="JSON", help="use this trusted-assets file instead of config/trusted_assets.json")
    s.add_argument("--ioc", metavar="FILE", action="append", help="extra IoC feed (CSV/TXT); repeatable")
    s.add_argument("--no-learn", action="store_true", help="don't update UEBA baselines from this run")
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
    if args.cmd == "info":
        return cli_info(cfg)
    if args.cmd == "set-password":
        return cli_set_password(cfg, args)
    if args.cmd == "remove-password":
        return cli_remove_password(cfg)
    if args.cmd == "scan":
        cli_scan(cfg, args)
    elif args.cmd == "audit":
        cli_audit(cfg, args)
    else:
        serve(cfg, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
