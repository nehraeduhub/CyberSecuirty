"""Reputation of public IPs, domains and URLs from AbuseIPDB and VirusTotal.

This is the only part of the tool that contacts an internet service, so it is deliberately narrow:
  * off until you add an API key in Settings, and it runs only when you ask (or when you switch
    on automatic look-ups); log analysis itself stays fully offline
  * only the indicator value is sent (an IP, domain or URL), never log lines
  * private, reserved and documentation addresses, internal names and anything listed as your own
    in Trusted Networks & Assets are refused, so your own infrastructure is never disclosed
  * URLs are only *looked up*; they are never submitted for scanning (a submission makes the URL
    public on VirusTotal)
  * results are cached (default 24 h) and requests are rate-limited to the free-tier quotas
Reputation is context for the analyst: it never changes a finding's severity and a clean result
never hides a finding.
"""
import base64
import ipaddress
import json
import re
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import ProxyHandler, Request, build_opener

import config_store
import trust

ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2"
VIRUSTOTAL_URL = "https://www.virustotal.com/api/v3"
CACHE_FILE = "reputation_cache.json"
INTERNAL_SUFFIXES = (".local", ".lan", ".internal", ".intranet", ".corp", ".home", ".localdomain", ".home.arpa",
                     ".example", ".test", ".invalid", ".localhost")
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")]

_lock = threading.Lock()
_last_call = {}


class RefusedError(ValueError):
    """The indicator must not be sent to an external service."""


def providers(cfg):
    return [p for p, k in (("abuseipdb", "abuseipdb_key"), ("virustotal", "virustotal_key")) if cfg.get(k)]


def classify(value, inv=None, allow_documentation=False):
    """('ip'|'domain'|'url', normalised value). Raises RefusedError for anything that must stay local."""
    v = str(value or "").strip()
    if not v or len(v) > 2048 or any(c in v for c in "\r\n\t "):
        raise RefusedError("not a valid IP address, domain or URL")
    if "://" in v:
        u = urlparse(v)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise RefusedError("only http(s) URLs can be looked up")
        _check_host(u.hostname, inv, allow_documentation)
        return "url", v
    try:
        ip = ipaddress.ip_address(v.strip("[]"))
    except ValueError:
        if not re.fullmatch(r"(?=.{4,253}$)([A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63}\.?", v):
            raise RefusedError("not a valid IP address, domain or URL") from None
        _check_host(v.rstrip(".").lower(), inv, allow_documentation)
        return "domain", v.rstrip(".").lower()
    _check_ip(ip, inv, allow_documentation)
    return "ip", str(ip)


def _check_host(host, inv, allow_documentation):
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None:  # checked outside the try: RefusedError is a ValueError too
        _check_ip(ip, inv, allow_documentation)
        return
    h = host.lower().rstrip(".")
    if "." not in h or h.endswith(INTERNAL_SUFFIXES) or (h.endswith((".example.com", ".example.net", ".example.org"))
                                                         and not allow_documentation):
        raise RefusedError(f"{host} is an internal or reserved name - not sent")
    if inv is not None:
        for sec in ("trusted_assets",):
            for e in inv.data.get(sec, []):
                if e.get("enabled") and str(e.get("hostname", "")).lower() in (h, h.split(".")[0]):
                    raise RefusedError(f"{host} is one of your configured assets - not sent")


def _check_ip(ip, inv, allow_documentation):
    if any(ip in n for n in DOC_NETS):
        if not allow_documentation:
            raise RefusedError(f"{ip} is a documentation (example) address - not sent")
    elif not ip.is_global or trust.is_private_ip(str(ip)):
        raise RefusedError(f"{ip} is a private, internal or reserved address - not sent")
    if inv is not None:
        c = inv.classify(str(ip))
        if c and c.get("category") not in ("public_unknown", "suspicious_indicator", "known_external_service", None):
            raise RefusedError(f"{ip} is listed in Trusted Networks & Assets ({c.get('label')}) - not sent")


# ------------------------------------------------------------------ cache

def _cache_path():
    return config_store.DATA_DIR / CACHE_FILE


def _cache():
    data, _ = config_store.load_json(_cache_path(), {})
    return data if isinstance(data, dict) else {}


def cached(value, max_age_h):
    e = _cache().get(value)
    if e and time.time() - e.get("_t", 0) < float(max_age_h) * 3600:
        return dict(e["result"], cached=True)
    return None


def _store(value, result):
    with _lock:
        c = _cache()
        c[value] = {"_t": time.time(), "result": result}
        if len(c) > 5000:
            for k in sorted(c, key=lambda k: c[k].get("_t", 0))[:len(c) - 5000]:
                c.pop(k)
        config_store.ensure_dirs()
        config_store.save_json(_cache_path(), c)


def _quota(provider, limit):
    """Daily request counter per provider (resets at 00:00 UTC). Returns False when the quota is used up."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = config_store.DATA_DIR / "reputation_quota.json"
    with _lock:
        q, _ = config_store.load_json(path, {})
        if q.get("day") != day:
            q = {"day": day}
        if limit and q.get(provider, 0) >= int(limit):
            return False
        q[provider] = q.get(provider, 0) + 1
        config_store.ensure_dirs()
        config_store.save_json(path, q)
    return True


def quota_used():
    q, _ = config_store.load_json(config_store.DATA_DIR / "reputation_quota.json", {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {k: v for k, v in q.items() if k != "day"} if q.get("day") == today else {}


def _throttle(provider, per_min):
    """Space requests so a free-tier key is never rate-limited (VirusTotal: 4/min)."""
    gap = 60.0 / max(float(per_min or 60), 0.1)
    with _lock:
        wait = _last_call.get(provider, 0) + gap - time.time()
        _last_call[provider] = max(time.time(), _last_call.get(provider, 0) + gap)
    if wait > 0:
        time.sleep(min(wait, 60))


# ------------------------------------------------------------------ providers

def _get(url, headers, timeout=20):
    host = urlparse(url).hostname or ""
    opener = build_opener(ProxyHandler({})) if host in ("127.0.0.1", "localhost", "::1") else build_opener()
    req = Request(url, headers=dict(headers, **{"Accept": "application/json", "User-Agent": "CyberSecAIAgent"}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            body = {}
        return e.code, body
    except (URLError, OSError, ValueError) as e:
        raise ConnectionError(f"cannot reach the service ({getattr(e, 'reason', e)}). Check internet access "
                              "or the proxy settings of this server.") from None


def _err(code, provider):
    return {401: f"{provider} rejected the API key", 403: f"{provider} rejected the API key or the request",
            429: f"{provider} rate limit or daily quota reached - try later"}.get(code, f"{provider} answered HTTP {code}")


def abuseipdb(cfg, ip):
    if not _quota("abuseipdb", cfg.get("abuseipdb_daily_limit", 1000)):
        return {"error": "daily AbuseIPDB quota used up (abuseipdb_daily_limit)"}
    _throttle("abuseipdb", cfg.get("abuseipdb_per_min", 30))
    code, body = _get(f"{cfg.get('abuseipdb_url') or ABUSEIPDB_URL}/check?ipAddress={quote(ip)}&maxAgeInDays=90",
                      {"Key": cfg["abuseipdb_key"]})
    if code != 200:
        return {"error": _err(code, "AbuseIPDB")}
    d = body.get("data") or {}
    return {"score": d.get("abuseConfidenceScore"), "reports": d.get("totalReports"),
            "distinct_users": d.get("numDistinctUsers"), "country": d.get("countryCode"), "isp": d.get("isp"),
            "usage": d.get("usageType"), "domain": d.get("domain"), "tor": d.get("isTor"),
            "whitelisted": d.get("isWhitelisted"), "last_reported": d.get("lastReportedAt"),
            "link": f"https://www.abuseipdb.com/check/{ip}"}


def virustotal(cfg, typ, value):
    if not _quota("virustotal", cfg.get("virustotal_daily_limit", 500)):
        return {"error": "daily VirusTotal quota used up (virustotal_daily_limit)"}
    _throttle("virustotal", cfg.get("virustotal_per_min", 4))
    base = cfg.get("virustotal_url") or VIRUSTOTAL_URL
    if typ == "ip":
        path, link = f"ip_addresses/{quote(value)}", f"https://www.virustotal.com/gui/ip-address/{value}"
    elif typ == "domain":
        path, link = f"domains/{quote(value)}", f"https://www.virustotal.com/gui/domain/{value}"
    else:  # look-up only: the id is the unpadded url-safe base64 of the URL; never POSTed for scanning
        vid = base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")
        path, link = f"urls/{vid}", f"https://www.virustotal.com/gui/url/{vid}"
    code, body = _get(f"{base}/{path}", {"x-apikey": cfg["virustotal_key"]})
    if code == 404:
        return {"found": False, "link": link, "note": "not known to VirusTotal (not submitted)"}
    if code != 200:
        return {"error": _err(code, "VirusTotal")}
    a = (body.get("data") or {}).get("attributes") or {}
    st = a.get("last_analysis_stats") or {}
    flagged = sorted(k for k, v in (a.get("last_analysis_results") or {}).items()
                     if (v or {}).get("category") in ("malicious", "suspicious"))
    when = a.get("last_analysis_date")
    return {"found": True, "malicious": st.get("malicious", 0), "suspicious": st.get("suspicious", 0),
            "harmless": st.get("harmless", 0), "undetected": st.get("undetected", 0),
            "engines": sum(int(v or 0) for v in st.values()), "reputation": a.get("reputation"),
            "country": a.get("country"), "owner": a.get("as_owner") or a.get("registrar"),
            "categories": sorted(set((a.get("categories") or {}).values()))[:5], "flagged_by": flagged[:8],
            "last_analysis": datetime.fromtimestamp(when, timezone.utc).strftime("%Y-%m-%d") if when else None,
            "link": link}


def verdict(res):
    ab, vt = res.get("abuseipdb") or {}, res.get("virustotal") or {}
    score, mal, sus = ab.get("score"), vt.get("malicious") or 0, vt.get("suspicious") or 0
    if (score is not None and score >= 75) or mal >= 3:
        v = "malicious"
    elif (score is not None and score >= 25) or mal >= 1 or sus >= 2:
        v = "suspicious"
    elif score is not None or vt.get("found"):
        v = "no known abuse"
    else:
        v = "unknown"
    parts = []
    if score is not None:
        parts.append(f"AbuseIPDB {score}% confidence, {ab.get('reports') or 0} reports")
    if vt.get("found"):
        parts.append(f"VirusTotal {mal}/{vt.get('engines') or 0} engines malicious" + (f", {sus} suspicious" if sus else ""))
    elif vt.get("found") is False:
        parts.append("VirusTotal: not known")
    for p in ("abuseipdb", "virustotal"):
        if (res.get(p) or {}).get("error"):
            parts.append(res[p]["error"])
    return v, "; ".join(parts)


def lookup(cfg, value, inv=None, force=False):
    """Reputation of one indicator from every configured provider. Raises RefusedError / ValueError."""
    have = providers(cfg)
    if not have:
        raise ValueError("No reputation service configured. Add an AbuseIPDB and/or VirusTotal API key in Settings.")
    typ, v = classify(value, inv, allow_documentation=bool(cfg.get("reputation_allow_documentation")))
    if not force:
        c = cached(v, cfg.get("reputation_cache_hours", 24))
        if c:
            return c
    res = {"value": v, "type": typ, "checked": config_store.now_iso(), "cached": False}
    try:
        if "abuseipdb" in have and typ == "ip":
            res["abuseipdb"] = abuseipdb(cfg, v)
        if "virustotal" in have:
            res["virustotal"] = virustotal(cfg, typ, v)
    except ConnectionError as e:
        raise ValueError(str(e)) from None
    if typ != "ip" and have == ["abuseipdb"]:
        res["note"] = "AbuseIPDB only rates IP addresses; add a VirusTotal key for domains and URLs."
    res["verdict"], res["summary"] = verdict(res)
    if not any((res.get(p) or {}).get("error") for p in ("abuseipdb", "virustotal")):
        _store(v, res)
    return res


def candidates(result, inv=None, limit=60, allow_documentation=False):
    """Public indicators from an analysis that may be looked up, most relevant first."""
    out, seen = [], set()

    def add(value, ctx):
        try:
            typ, v = classify(value, inv, allow_documentation)
        except RefusedError:
            return
        if v not in seen:
            seen.add(v)
            out.append({"value": v, "type": typ, "context": ctx})

    order = {"Malicious": 0, "Suspicious": 1, "Affected internal asset": 3}
    for p in sorted(result.get("ip_profiles") or [], key=lambda p: order.get(p.get("verdict"), 2)):
        add(p.get("ip"), f"{p.get('verdict', '')}: " + "; ".join((p.get("activity") or [])[:2]))
    i = result.get("iocs") or {}
    for u in i.get("urls") or []:
        add(u, "URL seen in the logs")
    for d in i.get("domains") or []:
        add(d, "domain seen in the logs")
    return out[:limit]
