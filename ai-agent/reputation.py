"""Threat intelligence for public IPs, domains, URLs, file hashes and CVEs.

Sources (each optional, used only when configured in Settings):
  AlienVault OTX (IPs, domains, URLs, hashes - shown first), AbuseIPDB (IPs), VirusTotal (all),
  abuse.ch URLhaus (malware URLs / hosts / payloads), abuse.ch ThreatFox (malware IOCs),
  abuse.ch MalwareBazaar (file hashes), PhishTank (phishing URLs), CIRCL cve.circl.lu (CVE details).

This is the only part of the tool that contacts an internet service, so it is deliberately narrow:
  * off until you add an API key in Settings, and it runs only when you ask (or when you switch
    on automatic look-ups); log analysis itself stays fully offline
  * only the indicator value is sent (an IP, domain or URL), never log lines
  * private, reserved and documentation addresses, internal names and anything listed as your own
    in Trusted Networks & Assets are refused, so your own infrastructure is never disclosed
  * URLs and files are only *looked up*; nothing is ever submitted for scanning (a submission makes it
    public). The abuse.ch and PhishTank APIs use POST for their *query* endpoints - still look-ups only.
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
from urllib.parse import quote, urlencode, urlparse
from urllib.request import (HTTPDefaultErrorHandler, HTTPErrorProcessor, HTTPHandler, HTTPRedirectHandler,
                            HTTPSHandler, OpenerDirector, ProxyHandler, Request, UnknownHandler)

import config_store
import trust

ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2"
VIRUSTOTAL_URL = "https://www.virustotal.com/api/v3"
OTX_URL = "https://otx.alienvault.com/api/v1"
URLHAUS_URL = "https://urlhaus-api.abuse.ch/v1"
THREATFOX_URL = "https://threatfox-api.abuse.ch/api/v1"
MALWAREBAZAAR_URL = "https://mb-api.abuse.ch/api/v1"
PHISHTANK_URL = "https://checkurl.phishtank.com/checkurl/"
CIRCL_URL = "https://cve.circl.lu/api"
HASH_RE = re.compile(r"[A-Fa-f0-9]{32}|[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64}")
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.I)
CACHE_FILE = "reputation_cache.json"
INTERNAL_SUFFIXES = (".local", ".lan", ".internal", ".intranet", ".corp", ".home", ".localdomain", ".home.arpa",
                     ".example", ".test", ".invalid", ".localhost")
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")]

_lock = threading.Lock()
_last_call = {}


class RefusedError(ValueError):
    """The indicator must not be sent to an external service."""


# name: (label, config switch that enables it, indicator types, requests per minute, daily limit key)
SOURCES = {
    "otx": ("AlienVault OTX", "otx_key", ("ip", "domain", "url", "hash"), 60, "otx_daily_limit"),
    "abuseipdb": ("AbuseIPDB", "abuseipdb_key", ("ip",), 30, "abuseipdb_daily_limit"),
    "virustotal": ("VirusTotal", "virustotal_key", ("ip", "domain", "url", "hash"), 4, "virustotal_daily_limit"),
    "urlhaus": ("URLhaus", "abusech_key", ("ip", "domain", "url", "hash"), 30, "abusech_daily_limit"),
    "threatfox": ("ThreatFox", "abusech_key", ("ip", "domain", "url", "hash"), 30, "abusech_daily_limit"),
    "malwarebazaar": ("MalwareBazaar", "abusech_key", ("hash",), 30, "abusech_daily_limit"),
    "phishtank": ("PhishTank", "phishtank_enabled", ("url",), 6, "phishtank_daily_limit"),
    "circl": ("CVE (CIRCL)", "circl_enabled", ("cve",), 30, "circl_daily_limit"),
}
DAILY_DEFAULTS = {"virustotal_daily_limit": 500, "abuseipdb_daily_limit": 1000, "otx_daily_limit": 5000,
                  "abusech_daily_limit": 5000, "phishtank_daily_limit": 500, "circl_daily_limit": 2000}


def providers(cfg):
    """Configured sources, in display order (OTX first)."""
    return [p for p, s in SOURCES.items() if cfg.get(s[1]) not in (None, "", False, 0, "0", "false")]


def classify(value, inv=None, allow_documentation=False):
    """('ip'|'domain'|'url'|'hash'|'cve', normalised value). Raises RefusedError for anything that must stay local."""
    v = str(value or "").strip()
    if not v or len(v) > 2048 or any(c in v for c in "\r\n\t "):
        raise RefusedError("not a valid IP address, domain, URL, file hash or CVE")
    if HASH_RE.fullmatch(v):
        return "hash", v.lower()
    if CVE_RE.fullmatch(v):
        return "cve", v.upper()
    if "://" in v:
        u = urlparse(v)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise RefusedError("only http(s) URLs can be looked up")
        _check_host(u.hostname, inv, allow_documentation)
        if u.username or u.password:   # never send credentials embedded in a URL to a third party
            v = u._replace(netloc=u.netloc.rsplit("@", 1)[-1]).geturl()
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
    inner = trust.embedded_ipv4(ip)
    if inner is not None:          # ::ffff:10.0.0.1, 64:ff9b::a00:1, 2002:a00:1:: carry an internal IPv4 inside
        _check_ip(inner, inv, allow_documentation)
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

MAX_RESPONSE = 2 * 1024 * 1024   # threat-intel answers are small; a bigger body is refused


class _NoRedirect(HTTPRedirectHandler):
    """Never follow redirects: urllib would copy the API-key headers to the new host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, f"redirect to {newurl} refused", headers, fp)


def _opener(url):
    host = urlparse(url).hostname or ""
    proxy = ProxyHandler({}) if host in ("127.0.0.1", "localhost", "::1") else ProxyHandler()
    op = OpenerDirector()   # http(s) only; no file:, ftp:, data:
    for h in (proxy, HTTPHandler(), HTTPSHandler(), HTTPDefaultErrorHandler(), _NoRedirect(), HTTPErrorProcessor(),
              UnknownHandler()):
        op.add_handler(h)
    return op


def _read_capped(resp):
    data = resp.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise ValueError("response too large")
    return data


def _request(url, headers, data=None, timeout=20):
    """GET (data None) or POST (dict -> form, or bytes). Returns (status, parsed JSON or {})."""
    h = dict({"Accept": "application/json", "User-Agent": "CyberSecAIAgent"}, **headers)
    if isinstance(data, dict):
        data = urlencode(data).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = Request(url, data=data, headers=h)
    try:
        with _opener(url).open(req, timeout=timeout) as r:
            raw = _read_capped(r).decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw or "{}")
            except (ValueError, RecursionError):
                return r.status, {"_raw": raw[:500]}
    except HTTPError as e:
        try:
            body = json.loads(_read_capped(e).decode("utf-8") or "{}") if e.fp else {}
        except (ValueError, OSError, AttributeError):
            body = {}
        return e.code, body
    except (URLError, OSError, ValueError) as e:
        raise ConnectionError(f"cannot reach the service ({getattr(e, 'reason', e)}). Check internet access "
                              "or the proxy settings of this server.") from None


def _get(url, headers, timeout=20):
    return _request(url, headers, None, timeout)


def _err(code, provider):
    return {401: f"{provider} rejected the API key", 403: f"{provider} rejected the API key or the request",
            429: f"{provider} rate limit or daily quota reached - try later"}.get(code, f"{provider} answered HTTP {code}")


def _gate(cfg, name):
    """Daily quota + throttle for one source. Returns an error dict, or None to go ahead."""
    label, _, _, per_min, limit_key = SOURCES[name]
    limit = cfg.get(limit_key, DAILY_DEFAULTS.get(limit_key))
    if not _quota(name, limit):
        return {"error": f"daily {label} quota used up ({limit_key})", "level": "error"}
    _throttle(name, cfg.get(f"{name}_per_min", per_min))
    return None


def abuseipdb(cfg, ip):
    g = _gate(cfg, "abuseipdb")
    if g:
        return g
    code, body = _get(f"{cfg.get('abuseipdb_url') or ABUSEIPDB_URL}/check?ipAddress={quote(ip)}&maxAgeInDays=90",
                      {"Key": cfg["abuseipdb_key"]})
    if code != 200:
        return {"error": _err(code, "AbuseIPDB"), "level": "error"}
    d = body.get("data") or {}
    score = d.get("abuseConfidenceScore")
    return {"score": score, "reports": d.get("totalReports"),
            "distinct_users": d.get("numDistinctUsers"), "country": d.get("countryCode"), "isp": d.get("isp"),
            "usage": d.get("usageType"), "domain": d.get("domain"), "tor": d.get("isTor"),
            "whitelisted": d.get("isWhitelisted"), "last_reported": d.get("lastReportedAt"),
            "level": "malicious" if (score or 0) >= 75 else "suspicious" if (score or 0) >= 25 else "clean",
            "text": f"{score}% confidence, {d.get('totalReports') or 0} reports"
                    + (f" · {d.get('countryCode')}" if d.get("countryCode") else "") + (" · Tor" if d.get("isTor") else ""),
            "link": f"https://www.abuseipdb.com/check/{ip}"}


def virustotal(cfg, typ, value):
    g = _gate(cfg, "virustotal")
    if g:
        return g
    base = cfg.get("virustotal_url") or VIRUSTOTAL_URL
    if typ == "ip":
        path, link = f"ip_addresses/{quote(value)}", f"https://www.virustotal.com/gui/ip-address/{value}"
    elif typ == "domain":
        path, link = f"domains/{quote(value)}", f"https://www.virustotal.com/gui/domain/{value}"
    elif typ == "hash":
        path, link = f"files/{value}", f"https://www.virustotal.com/gui/file/{value}"
    else:  # look-up only: the id is the unpadded url-safe base64 of the URL; never POSTed for scanning
        vid = base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")
        path, link = f"urls/{vid}", f"https://www.virustotal.com/gui/url/{vid}"
    code, body = _get(f"{base}/{path}", {"x-apikey": cfg["virustotal_key"]})
    if code == 404:
        return {"found": False, "link": link, "level": "unknown", "text": "not known (not submitted)",
                "note": "not known to VirusTotal (not submitted)"}
    if code != 200:
        return {"error": _err(code, "VirusTotal"), "level": "error"}
    a = (body.get("data") or {}).get("attributes") or {}
    st = a.get("last_analysis_stats") or {}
    flagged = sorted(k for k, v in (a.get("last_analysis_results") or {}).items()
                     if (v or {}).get("category") in ("malicious", "suspicious"))
    when = a.get("last_analysis_date")
    mal, sus, eng = st.get("malicious", 0), st.get("suspicious", 0), sum(int(v or 0) for v in st.values())
    return {"found": True, "malicious": mal, "suspicious": sus,
            "harmless": st.get("harmless", 0), "undetected": st.get("undetected", 0),
            "engines": eng, "reputation": a.get("reputation"),
            "country": a.get("country"), "owner": a.get("as_owner") or a.get("registrar"),
            "categories": sorted(set((a.get("categories") or {}).values()))[:5], "flagged_by": flagged[:8],
            "names": (a.get("names") or [])[:3], "type": a.get("type_description"),
            "last_analysis": datetime.fromtimestamp(when, timezone.utc).strftime("%Y-%m-%d") if when else None,
            "level": "malicious" if mal >= 3 else "suspicious" if mal >= 1 or sus >= 2 else "clean",
            "text": f"{mal}/{eng} engines malicious" + (f", {sus} suspicious" if sus else "")
                    + (f" · {a.get('type_description')}" if a.get("type_description") else ""),
            "link": link}


def otx(cfg, typ, value):
    g = _gate(cfg, "otx")
    if g:
        return g
    section = {"domain": "domain", "url": "url", "hash": "file"}.get(typ) or ("IPv6" if ":" in value else "IPv4")
    base = cfg.get("otx_url") or OTX_URL
    code, body = _get(f"{base}/indicators/{section}/{quote(value, safe='')}/general", {"X-OTX-API-KEY": cfg["otx_key"]})
    link = f"https://otx.alienvault.com/indicator/{section.lower() if section != 'IPv4' else 'ip'}/{quote(value, safe='')}"
    if code == 404:
        return {"pulses": 0, "level": "unknown", "text": "not known", "link": link}
    if code != 200:
        return {"error": _err(code, "AlienVault OTX"), "level": "error"}
    pi = body.get("pulse_info") or {}
    n = int(pi.get("count") or 0)
    pulses = [p.get("name") for p in (pi.get("pulses") or [])[:5] if p.get("name")]
    fams = sorted({m.get("display_name") for p in (pi.get("pulses") or []) for m in (p.get("malware_families") or [])
                   if isinstance(m, dict) and m.get("display_name")})[:5]
    tags = sorted({t for p in (pi.get("pulses") or [])[:20] for t in (p.get("tags") or [])})[:8]
    return {"pulses": n, "pulse_names": pulses, "malware_families": fams, "tags": tags,
            "reputation": body.get("reputation"), "country": body.get("country_name"),
            "level": "malicious" if n >= 3 else "suspicious" if n >= 1 else "clean",
            "text": f"{n} pulse(s)" + (f" · {', '.join(fams[:3])}" if fams else "") +
                    (f" · e.g. {pulses[0][:60]}" if pulses else ""),
            "link": link}


def _abusech(cfg, name, label, url, data):
    g = _gate(cfg, name)
    if g:
        return None, g
    hdr = {"Auth-Key": cfg["abusech_key"]}
    if isinstance(data, dict) and data.get("_json"):
        body = json.dumps({k: v for k, v in data.items() if k != "_json"}).encode()
        code, res = _request(url, dict(hdr, **{"Content-Type": "application/json"}), body)
    else:
        code, res = _request(url, hdr, data)
    if code != 200:
        return None, {"error": _err(code, label), "level": "error"}
    return res, None


def urlhaus(cfg, typ, value):
    base = cfg.get("urlhaus_url") or URLHAUS_URL
    if typ == "url":
        res, err = _abusech(cfg, "urlhaus", "URLhaus", f"{base}/url/", {"url": value})
    elif typ == "hash":
        res, err = _abusech(cfg, "urlhaus", "URLhaus", f"{base}/payload/",
                            {("sha256_hash" if len(value) == 64 else "md5_hash"): value})
        if res is not None and len(value) == 40:
            return {"level": "unknown", "text": "SHA-1 not supported by URLhaus"}
    else:
        res, err = _abusech(cfg, "urlhaus", "URLhaus", f"{base}/host/", {"host": value})
    if err:
        return err
    st = res.get("query_status")
    if st in ("no_results", "invalid_url", "invalid_host"):
        return {"level": "clean", "text": "not listed", "found": False}
    if st != "ok":
        return {"error": f"URLhaus: {st}", "level": "error"}
    if typ == "url":
        tags = res.get("tags") or []
        return {"found": True, "threat": res.get("threat"), "url_status": res.get("url_status"), "tags": tags,
                "date_added": res.get("date_added"), "link": res.get("urlhaus_reference"), "level": "malicious",
                "text": f"listed: {res.get('threat') or 'malware'} ({res.get('url_status') or '?'})"
                        + (f" · {', '.join(tags[:3])}" if tags else "")}
    if typ == "hash":
        return {"found": True, "signature": res.get("signature"), "file_type": res.get("file_type"),
                "url_count": res.get("url_count"), "level": "malicious",
                "text": f"payload seen on {res.get('url_count') or 0} URL(s)" + (f" · {res['signature']}" if res.get("signature") else ""),
                "link": f"https://urlhaus.abuse.ch/browse.php?search={value}"}
    urls = res.get("urls") or []
    online = sum(1 for u in urls if u.get("url_status") == "online")
    return {"found": True, "url_count": res.get("url_count") or len(urls), "online": online,
            "link": res.get("urlhaus_reference"), "level": "malicious" if urls else "suspicious",
            "text": f"hosted {res.get('url_count') or len(urls)} malware URL(s), {online} online"}


def threatfox(cfg, typ, value):
    base = cfg.get("threatfox_url") or THREATFOX_URL
    q = {"_json": True, "query": "search_hash", "hash": value} if typ == "hash" else \
        {"_json": True, "query": "search_ioc", "search_term": value, "exact_match": True}
    res, err = _abusech(cfg, "threatfox", "ThreatFox", f"{base}/", q)
    if err:
        return err
    st = res.get("query_status")
    if st in ("no_result", "no_results", "illegal_search_term", "illegal_hash"):
        return {"level": "clean", "text": "not listed", "found": False}
    if st != "ok":
        return {"error": f"ThreatFox: {st}", "level": "error"}
    data = res.get("data") or []
    d = data[0] if data and isinstance(data[0], dict) else {}
    fams = sorted({x.get("malware_printable") for x in data if isinstance(x, dict) and x.get("malware_printable")})[:4]
    return {"found": True, "iocs": len(data), "malware": fams, "threat_type": d.get("threat_type_desc") or d.get("threat_type"),
            "confidence": d.get("confidence_level"), "first_seen": d.get("first_seen"),
            "level": "malicious", "link": f"https://threatfox.abuse.ch/browse.php?search=ioc%3A{quote(value, safe='')}",
            "text": f"{', '.join(fams) or 'malware'} · {d.get('threat_type_desc') or d.get('threat_type') or 'IOC'}"
                    + (f" · confidence {d['confidence_level']}%" if d.get("confidence_level") is not None else "")}


def malwarebazaar(cfg, value):
    base = cfg.get("malwarebazaar_url") or MALWAREBAZAAR_URL
    res, err = _abusech(cfg, "malwarebazaar", "MalwareBazaar", f"{base}/", {"query": "get_info", "hash": value})
    if err:
        return err
    st = res.get("query_status")
    if st in ("hash_not_found", "no_results"):
        return {"level": "unknown", "text": "not known", "found": False}
    if st != "ok":
        return {"error": f"MalwareBazaar: {st}", "level": "error"}
    d = (res.get("data") or [{}])[0]
    return {"found": True, "signature": d.get("signature"), "file_type": d.get("file_type"), "file_name": d.get("file_name"),
            "first_seen": d.get("first_seen"), "tags": (d.get("tags") or [])[:6], "level": "malicious",
            "text": f"{d.get('signature') or 'malware sample'} · {d.get('file_type') or '?'}"
                    + (f" · first seen {str(d.get('first_seen'))[:10]}" if d.get("first_seen") else ""),
            "link": f"https://bazaar.abuse.ch/sample/{d.get('sha256_hash') or value}/"}


def phishtank(cfg, url):
    g = _gate(cfg, "phishtank")
    if g:
        return g
    data = {"url": url, "format": "json"}
    if cfg.get("phishtank_key"):
        data["app_key"] = cfg["phishtank_key"]
    user = re.sub(r"[^A-Za-z0-9_.-]", "", str(cfg.get("phishtank_user") or "cybersec-agent"))
    code, res = _request(cfg.get("phishtank_url") or PHISHTANK_URL, {"User-Agent": f"phishtank/{user}"}, data)
    if code != 200:
        return {"error": _err(code, "PhishTank"), "level": "error"}
    r = res.get("results") or {}
    if not r.get("in_database"):
        return {"level": "unknown", "text": "not in database", "found": False}
    valid = bool(r.get("valid")) and bool(r.get("verified"))
    return {"found": True, "verified": r.get("verified"), "valid": r.get("valid"), "phish_id": r.get("phish_id"),
            "level": "malicious" if valid else "suspicious" if r.get("valid") else "clean",
            "text": "verified phishing site" if valid else "reported phishing (unverified)" if r.get("valid") else "in database, not a phish",
            "link": r.get("phish_detail_page") or "https://phishtank.org/"}


def circl_cve(cfg, cve):
    g = _gate(cfg, "circl")
    if g:
        return g
    code, d = _get(f"{cfg.get('circl_url') or CIRCL_URL}/cve/{cve}", {})
    if code == 404 or not d:
        return {"level": "unknown", "text": "CVE not found", "found": False}
    if code != 200:
        return {"error": _err(code, "CIRCL CVE"), "level": "error"}
    # CVE JSON 5 (vulnerability-lookup) or the legacy cve-search format
    cna = ((d.get("containers") or {}).get("cna") or {})
    summary = d.get("summary") or next((x.get("value") for x in cna.get("descriptions") or [] if x.get("lang", "en").startswith("en")), "")
    score, sev, vector = d.get("cvss3") or d.get("cvss"), None, None
    for m in cna.get("metrics") or []:
        for k in ("cvssV4_0", "cvssV3_1", "cvssV3_0", "cvssV2_0"):
            if m.get(k):
                score, sev, vector = m[k].get("baseScore"), m[k].get("baseSeverity"), m[k].get("vectorString")
                break
        if score is not None:
            break
    for adp in (d.get("containers") or {}).get("adp") or []:
        for m in adp.get("metrics") or []:
            for k in ("cvssV3_1", "cvssV3_0"):
                if score is None and m.get(k):
                    score, sev, vector = m[k].get("baseScore"), m[k].get("baseSeverity"), m[k].get("vectorString")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    sev = (sev or ("CRITICAL" if (score or 0) >= 9 else "HIGH" if (score or 0) >= 7 else "MEDIUM" if (score or 0) >= 4
                   else "LOW" if score else "UNKNOWN")).upper()
    meta = d.get("cveMetadata") or {}
    refs = [r.get("url") for r in cna.get("references") or [] if r.get("url")][:5] or (d.get("references") or [])[:5]
    affected = [f"{a.get('vendor', '')} {a.get('product', '')}".strip() for a in cna.get("affected") or []][:4]
    return {"found": True, "cvss": score, "severity": sev, "vector": vector, "summary": str(summary)[:600],
            "published": (meta.get("datePublished") or d.get("Published") or "")[:10], "affected": affected,
            "references": refs, "level": "vulnerability",
            "text": f"CVSS {score if score is not None else '?'} {sev}" + (f" · {', '.join(affected[:2])}" if affected else "")
                    + (f" · {str(summary)[:90]}" if summary else ""),
            "link": f"https://cve.circl.lu/vuln/{cve.lower()}"}


LEVEL_RANK = {"malicious": 0, "suspicious": 1, "clean": 2, "unknown": 3, "error": 4}


def verdict(res):
    levels = [(p, (res.get(p) or {}).get("level")) for p in SOURCES if res.get(p)]
    if res.get("type") == "cve":
        c = res.get("circl") or {}
        if c.get("found"):
            return f"vulnerability ({c.get('severity', '').lower() or 'unknown'})", f"CVE (CIRCL): {c.get('text', '')}"
        return "unknown", "; ".join(f"{SOURCES[p][0]}: {(res.get(p) or {}).get('error') or (res.get(p) or {}).get('text', '')}" for p, _ in levels)
    lv = [lvl for _, lvl in levels if lvl in LEVEL_RANK and lvl != "error"]
    best = min(lv, key=lambda x: LEVEL_RANK[x]) if lv else "unknown"
    v = {"malicious": "malicious", "suspicious": "suspicious", "clean": "no known abuse"}.get(best, "unknown")
    # one malicious source among clean ones is still "malicious": these lists are curated
    parts = []
    for p, lvl in levels:
        r = res[p]
        txt = r.get("error") or r.get("text") or ""
        if p == "abuseipdb" and r.get("score") is not None:
            txt = f"{r['score']}% confidence, {r.get('reports') or 0} reports"
        parts.append(f"{SOURCES[p][0]} {txt}" if p != "virustotal" or not r.get("found") else
                     f"VirusTotal {r.get('malicious', 0)}/{r.get('engines') or 0} engines malicious"
                     + (f", {r['suspicious']} suspicious" if r.get("suspicious") else ""))
    return v, "; ".join(parts)


def lookup(cfg, value, inv=None, force=False):
    """Reputation of one indicator from every configured source that supports its type."""
    have = providers(cfg)
    if not have:
        raise ValueError("No threat-intelligence source configured. Add API keys (OTX, AbuseIPDB, VirusTotal, "
                         "abuse.ch) or enable PhishTank / CVE look-ups in Settings.")
    typ, v = classify(value, inv, allow_documentation=bool(cfg.get("reputation_allow_documentation")))
    usable = [p for p in have if typ in SOURCES[p][2]]
    if not usable:
        need = ", ".join(SOURCES[p][0] for p in SOURCES if typ in SOURCES[p][2])
        raise ValueError(f"No configured source can look up a {typ}. Sources for this type: {need}.")
    if not force:
        c = cached(v, cfg.get("reputation_cache_hours", 24))
        if c:
            return c
    res = {"value": v, "type": typ, "checked": config_store.now_iso(), "cached": False}
    calls = {"otx": lambda: otx(cfg, typ, v), "abuseipdb": lambda: abuseipdb(cfg, v),
             "virustotal": lambda: virustotal(cfg, typ, v), "urlhaus": lambda: urlhaus(cfg, typ, v),
             "threatfox": lambda: threatfox(cfg, typ, v), "malwarebazaar": lambda: malwarebazaar(cfg, v),
             "phishtank": lambda: phishtank(cfg, v), "circl": lambda: circl_cve(cfg, v)}
    reachable = False
    for p in usable:
        try:
            res[p] = calls[p]()
            reachable = True
        except ConnectionError as e:
            res[p] = {"error": f"{SOURCES[p][0]}: {e}", "level": "error"}
    if not reachable:
        raise ValueError(next(iter(r["error"] for r in (res[p] for p in usable))))
    for p in usable:   # links come from remote JSON: only http(s) links are kept
        if res[p].get("link") and urlparse(str(res[p]["link"])).scheme not in ("http", "https"):
            res[p]["link"] = None
    res["sources"] = [{"name": p, "label": SOURCES[p][0], "level": res[p].get("level") or "unknown",
                       "text": res[p].get("error") or res[p].get("text") or "", "link": res[p].get("link")}
                      for p in usable]
    res["verdict"], res["summary"] = verdict(res)
    if not any((res.get(p) or {}).get("error") for p in usable):
        _store(v, res)
    return res


def candidates(result, inv=None, limit=80, allow_documentation=False):
    """Indicators from an analysis that may be looked up, most relevant first."""
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
        if p.get("trusted"):
            continue
        add(p.get("ip"), f"{p.get('verdict', '')}: " + "; ".join((p.get("activity") or [])[:2]))
    i = result.get("iocs") or {}
    for u in i.get("urls") or []:
        add(u, "URL seen in the logs")
    for d in i.get("domains") or []:
        add(d, "domain seen in the logs")
    for h in i.get("hashes") or []:
        add(h, "file hash seen in the logs")
    cves = {}
    for f in result.get("findings") or []:
        blob = " ".join([str(f.get("title", "")), " ".join(map(str, f.get("references") or [])),
                         " ".join(str(s.get("text", "")) for s in f.get("samples") or [])])
        for c in CVE_RE.findall(blob):
            cves.setdefault(c.upper(), f.get("title", ""))
    for e in result.get("evidence") or []:
        for c in CVE_RE.findall(str(e.get("raw", ""))):
            cves.setdefault(c.upper(), "CVE named in the logs")
    for c, ctx in cves.items():
        add(c, f"CVE: {ctx}"[:120])
    return out[:limit]
