"""What each device did with an event, and how an attack moved through the environment.

Everything here is derived from fields that are present in the log record. Nothing is
inferred that the log does not say: an IDS "alert" is reported as detection only, an HTTP
200 to an attack payload is reported as "request served - exploitation possible, verify",
never as a confirmed compromise.
"""
import re
from urllib.parse import unquote_plus

# result classes (used for colour in the UI / PDF)
ALLOWED, BLOCKED, SUCCESS, FAILED, DETECTED, EXECUTED, CHANGED, ERROR, INFO = (
    "allowed", "blocked", "success", "failed", "detected", "executed", "changed", "error", "info")

DEVICE = {"firewall": "Firewall", "ids": "IDS/IPS", "vpn": "VPN gateway", "windows": "Windows host",
          "linux_auth": "Linux host", "linux": "Linux host", "web": "Web server", "dns": "DNS server",
          "proxy": "Web proxy", "edr": "EDR agent", "database": "Database", "generic": "Log source"}

WIN = {  # event id -> (what the machine recorded, result)
    "4624": ("Logon succeeded", SUCCESS), "4625": ("Logon failed", FAILED), "4648": ("Logon with explicit credentials", SUCCESS),
    "4634": ("Logged off", INFO), "4672": ("Admin privileges assigned to logon", SUCCESS),
    "4740": ("Account locked out", BLOCKED), "4767": ("Account unlocked", CHANGED),
    "4771": ("Kerberos pre-authentication failed", FAILED), "4776": ("Credential validation", INFO),
    "4768": ("Kerberos TGT issued", SUCCESS), "4769": ("Kerberos service ticket issued", SUCCESS),
    "4688": ("Process executed", EXECUTED), "4104": ("PowerShell script block executed", EXECUTED),
    "4720": ("User account created", CHANGED), "4722": ("User account enabled", CHANGED),
    "4724": ("Password reset", CHANGED), "4726": ("User account deleted", CHANGED),
    "4728": ("Added to global security group", CHANGED), "4732": ("Added to local security group", CHANGED),
    "4756": ("Added to universal security group", CHANGED), "4698": ("Scheduled task created", CHANGED),
    "7045": ("Service installed", CHANGED), "4697": ("Service installed", CHANGED),
    "4719": ("Audit policy changed", CHANGED), "1102": ("Security audit log cleared", CHANGED),
    "104": ("Event log cleared", CHANGED), "5140": ("Network share accessed", SUCCESS),
    "4663": ("Object access", SUCCESS), "1": ("Process executed (Sysmon)", EXECUTED),
    "3": ("Network connection (Sysmon)", ALLOWED), "11": ("File created (Sysmon)", CHANGED),
    "22": ("DNS query (Sysmon)", INFO),
}
LOGON_TYPE = {2: "interactive", 3: "network", 4: "batch", 5: "service", 7: "unlock", 8: "network cleartext",
              9: "new credentials", 10: "RDP", 11: "cached"}
FW_ALLOW = {"allow", "allowed", "accept", "accepted", "permit", "permitted", "pass", "passed", "built", "teardown", "close"}
FW_BLOCK = {"deny", "denied", "drop", "dropped", "reject", "rejected", "block", "blocked", "reset", "discard"}
SYSLOG_HOST = re.compile(r"^(?:<\d+>)?(?:\w{3} +\d+ [\d:]{8}|\d{4}-\d\d-\d\dT\S+) +([\w.-]+) ")
RAW_EVENT = re.compile(r"\bevent=([\w.-]+)")
RAW_REASON = re.compile(r"\breason=([\w.-]+)")
WEB_PORTS = (80, 443, 8000, 8080, 8443)
EXPLOIT_HINT = re.compile(r"union\s+select|select.+from|'\s*or\s*'?1|\.\./|%2e%2e|<script|\$\{jndi:|cmd=|exec=|"
                          r"/etc/passwd|wp-config|\.env\b|shell\.php|c99|r57|eval\(|base64_decode|;\s*(?:id|whoami|uname)",
                          re.I)


def _host(ev):
    return str(ev.get("host") or "").split(".")[0]


def device(ev):
    """Name of the system that reported the event, e.g. 'Firewall fw01', 'Windows host DC01'."""
    st = ev.get("source_type") or "generic"
    if st == "generic" and str(ev.get("event_id") or "") in WIN and len(str(ev.get("event_id"))) == 4:
        st = "windows"
    name = DEVICE.get(st, st)
    h = str(ev.get("device") or "") or _host(ev)
    if not h and st in ("ids", "firewall", "vpn", "proxy", "dns"):
        m = SYSLOG_HOST.match(str(ev.get("raw") or ""))
        h = m.group(1) if m else (str(ev["vendor"]).split()[-1] if ev.get("vendor") else "")
    return f"{name} {h}".strip()


def action(ev):
    """{'by': device, 'action': what it did, 'result': class}. Uses only fields in the record."""
    st = ev.get("source_type") or "generic"
    act = str(ev.get("action") or "").strip().lower()
    out = str(ev.get("outcome") or "").strip().lower()
    raw = str(ev.get("raw") or "")[:600]
    by = device(ev)
    eid = str(ev.get("event_id") or "")

    def r(text, res):
        return {"by": by, "action": text, "result": res}

    if st == "firewall" or (act in FW_ALLOW | FW_BLOCK and ev.get("dst_port")):
        port = f" to port {ev['dst_port']}" if ev.get("dst_port") else ""
        if act in FW_BLOCK:
            return r(f"Blocked ({act}){port}", BLOCKED)
        if act in FW_ALLOW:
            sent = ev.get("bytes_out")
            vol = f", {_size(sent)} sent" if isinstance(sent, int) and sent >= 1024 else ""
            return r(f"Allowed{port}{vol}", ALLOWED)
        if "config" in act or "change" in act:
            return r("Firewall policy changed", CHANGED)
    if st in ("ids", "edr"):
        if act in FW_BLOCK or act in ("prevented", "quarantined", "killed", "cleaned"):
            return r(f"Blocked by sensor ({act})", BLOCKED)
        return r("Alert raised - detection only, traffic not blocked" if st == "ids"
                 else "Alert raised - no prevention action logged", DETECTED)
    if st == "vpn":
        m = RAW_EVENT.search(raw)
        e = (m.group(1) if m else act or out).lower()
        if "fail" in e or "reject" in e or "denied" in e:
            why = RAW_REASON.search(raw)
            return r("Login rejected" + (f" ({why.group(1)})" if why else ""), FAILED)
        if "success" in e or "accept" in e or "connect" in e:
            extra = ", tunnel IP " + ev["assigned_ip"] if ev.get("assigned_ip") else ""
            return r(f"Login accepted, VPN session opened{extra}", SUCCESS)
        if "disconnect" in e or "logout" in e:
            return r("Session closed", INFO)
    if st == "web" or (ev.get("url") and ev.get("status")):
        return r(*_http(ev))
    if st == "dns" and ev.get("rcode"):
        rc = str(ev["rcode"]).upper()
        if rc == "NXDOMAIN":
            return r("Name does not exist (NXDOMAIN)", FAILED)
        if rc in ("REFUSED", "BLOCKED", "SINKHOLE"):
            return r(f"Query refused ({rc})", BLOCKED)
        return r(f"Resolved ({rc})" + (f", {ev['query_type']} record" if ev.get("query_type") else ""), SUCCESS)
    if eid in WIN and st in ("windows", "edr", "generic"):
        text, res = WIN[eid]
        lt = ev.get("logon_type")
        if eid in ("4624", "4625") and lt in LOGON_TYPE:
            text += f" ({LOGON_TYPE[lt]})"
        if eid == "4625" and out and out not in ("failure", "audit failure"):
            text += f": {out[:60]}"
        return r(text, res)
    if out or act:
        t = f"{act} {out}"
        if re.search(r"\b(fail|failure|failed|denied|invalid|rejected)\b", t):
            return r(("SSH login rejected" if ev.get("protocol") == "ssh" else "Login failed") if "logon" in t
                     else f"Failed ({out or act})", FAILED)
        if re.search(r"\b(success|succeeded|accepted|ok)\b", t):
            return r("SSH login accepted" if ev.get("protocol") == "ssh" else "Login succeeded" if "logon" in t
                     else f"Succeeded ({act or out})", SUCCESS)
    if ev.get("command"):
        how = "Command run with sudo" if str(ev.get("process", "")).startswith("sudo") else "Command executed"
        return r(how, EXECUTED)
    if ev.get("process"):
        return r("Process activity recorded", EXECUTED)
    if act:
        return r(act[:60], INFO)
    return r("Recorded (no action field in log)", INFO)


def _http(ev):
    s = ev.get("status")
    try:
        s = int(s)
    except (TypeError, ValueError):
        return ("Request logged (no status)", INFO)
    attack = bool(EXPLOIT_HINT.search(unquote_plus(str(ev.get("url") or ""))))
    if 200 <= s < 300:
        return ((f"Served HTTP {s} to attack payload - exploitation possible, verify", SUCCESS) if attack
                else (f"Served HTTP {s}", SUCCESS))
    if 300 <= s < 400:
        return (f"Redirected (HTTP {s})", INFO)
    if s in (401, 403, 405, 406, 429):
        return (f"Denied (HTTP {s})", BLOCKED)
    if 400 <= s < 500:
        return (f"Not found / rejected (HTTP {s})", FAILED)
    return ((f"Server error HTTP {s} - payload reached the application", ERROR) if attack
            else (f"Server error (HTTP {s})", ERROR))


def _size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _name(ip, names):
    n = names(ip) if names and ip else None
    return f"{ip} ({n})" if n else ip


def hops(ev, names=None):
    """Ordered path of one event: source -> reporting device -> target -> object (the action is separate)."""
    src = _name(ev.get("src_ip"), names) if ev.get("src_ip") else (ev.get("src_host") or "")
    if ev.get("user") and ev.get("source_type") in ("vpn", "windows", "linux_auth", "linux"):
        src = f"{src} as {ev['user']}" if src else ev["user"]
    a = action(ev)
    st = ev.get("source_type")
    path = []
    if src:
        path.append(src)
    if st in ("firewall", "ids", "vpn", "proxy"):
        path.append(a["by"])
        if st == "vpn" and ev.get("assigned_ip"):
            path.append(f"tunnel IP {ev['assigned_ip']}")
        if ev.get("dst_ip"):
            path.append(_name(ev["dst_ip"], names) + (f":{ev['dst_port']}" if ev.get("dst_port") else ""))
    else:
        target = _host(ev) or (_name(ev["dst_ip"], names) if ev.get("dst_ip") else "")
        if ev.get("dst_ip") and _host(ev):
            target = f"{_host(ev)} ({ev['dst_ip']})"
        if ev.get("dst_port") and target:
            target += f":{ev['dst_port']}"
        if target:
            path.append(target)
        obj = _object(ev)
        if obj:
            path.append(obj)
    if st in ("firewall", "ids", "proxy") and _object(ev, network=True):
        path.append(_object(ev, network=True))
    return [p for p in path if p]


def _object(ev, network=False):
    if ev.get("url"):
        return f"{ev.get('method') or 'GET'} {str(ev['url'])[:120]}"
    if network:
        return str(ev["signature"])[:100] if ev.get("source_type") == "ids" and ev.get("signature") else ""
    if ev.get("command"):
        return f"cmd: {str(ev['command'])[:120]}"
    if ev.get("process") and ev.get("action") != "logon" and ev.get("source_type") not in ("vpn", "linux_auth"):
        return f"process: {str(ev['process']).split(chr(92))[-1][:80]}"
    if ev.get("file_path"):
        return f"file: {str(ev['file_path'])[:100]}"
    if ev.get("domain"):
        return f"query: {str(ev['domain'])[:90]}"
    if ev.get("target_user"):
        return f"account: {ev['target_user']}" + (f" -> {ev['group']}" if ev.get("group") else "")
    return ""


def describe(ev, names=None):
    """Fields added to every timeline / evidence entry."""
    a = action(ev)
    return {"action": a["action"], "action_by": a["by"], "result": a["result"],
            "path": " → ".join(hops(ev, names))}


def _node(ip, host, names):
    if host:
        return host
    return _name(ip, names) if ip else ""


def incident_flow(timeline, evidence_by_id, names=None, limit=40):
    """Group an incident's ordered timeline into attack-flow steps:
    step = {from, via, to, object, action, result, stage, first, last, count, evidence}.
    Consecutive events with the same stage, source, target and result are merged."""
    steps = []
    web_host = {}   # attacker IP -> the server the firewall let it reach on a web port (names the web log's host)
    for t in timeline:
        ev = evidence_by_id.get(t.get("evidence")) or {}
        if ev.get("source_type") in ("firewall", "ids") and ev.get("dst_port") in WEB_PORTS and ev.get("src_ip") \
                and action(ev)["result"] in (ALLOWED, DETECTED):
            web_host.setdefault(ev["src_ip"], _name(ev.get("dst_ip"), names))
    for t in timeline:
        ev = evidence_by_id.get(t.get("evidence"))
        if not ev:
            continue
        a = action(ev)
        st = ev.get("source_type")
        src = _node(ev.get("src_ip"), "", names) or (ev.get("src_host") if ev.get("src_host") not in ("UNKNOWN", "-") else "") or ""
        dst = _host(ev) if st not in ("firewall", "ids", "proxy", "vpn") else ""
        if not dst and st == "web":
            dst = web_host.get(ev.get("src_ip")) or "Web server"
            if ev.get("file"):
                dst += f" [{ev['file']}]"
        port = None
        if not dst and ev.get("dst_ip"):
            dst = _name(ev["dst_ip"], names)
            if st == "firewall" and ev.get("dst_port"):
                port = ev["dst_port"]          # firewall steps to one host are merged; ports are listed
            elif ev.get("dst_port"):
                dst += f":{ev['dst_port']}"
        if st == "vpn":
            dst = (_host(ev) or "VPN") + (f" → {ev['assigned_ip']}" if ev.get("assigned_ip") and a["result"] == SUCCESS else "")
        if st == "dns" and not dst:
            dst = "DNS"
        via = a["by"] if st in ("firewall", "ids", "proxy") else ""
        obj = "" if st == "vpn" else _object(ev, network=st in ("firewall", "ids", "proxy")) or ""
        if st == "dns" and ev.get("domain"):
            d = str(ev["domain"]).split(".")
            obj = "query: *." + ".".join(d[-3:]) if len(d) > 3 else f"query: {ev['domain']}"
        who = ev.get("user") if st in ("windows", "linux_auth", "linux", "vpn", "edr") else ""
        noise = st == "web" and a["result"] in (FAILED, BLOCKED, INFO)   # probing: merge, list the paths
        key = (t.get("tactic"), src, dst, via, "probe" if noise else a["result"],
               st if noise or not obj.startswith(("GET", "POST", "PUT", "DELETE", "cmd")) else obj)
        last = steps[-1] if steps else None
        if noise and last and last["_key"] == key and obj and obj not in last["object"] and len(last["object"]) < 200:
            last["object"] += ", " + obj.split(" ", 1)[-1]
        # one source logging on to several machines in a row = one lateral-movement step
        fan = (last and src and not obj and last["_key"][1] == src and last["_key"][0] == key[0]
               and last["_key"][3:] == key[3:] and last["action_base"] == a["action"] and dst
               and not last["object"] and st in ("windows", "linux_auth", "linux", "edr"))
        if fan and dst not in last["to"].split(", "):
            last["to"] += f", {dst}"
            last["_key"] = key
        if last and (last["_key"] == key or fan):
            last["count"] += 1
            last["last"] = t.get("ts")
            if port is not None and port not in last["_ports"]:
                last["_ports"].append(port)
            if noise:
                last["_codes"][ev.get("status")] = last["_codes"].get(ev.get("status"), 0) + 1
            if t.get("evidence") and len(last["evidence"]) < 6:
                last["evidence"].append(t["evidence"])
            if who and who not in last["users"]:
                last["users"].append(who)
            continue
        steps.append({"_key": key, "action_base": a["action"], "stage": t.get("tactic") or "", "from": src, "via": via, "to": dst,
                      "object": obj, "action": a["action"], "action_by": a["by"], "result": a["result"],
                      "first": t.get("ts"), "last": t.get("ts"), "count": 1, "users": [who] if who else [],
                      "evidence": [t["evidence"]] if t.get("evidence") else [],
                      "_codes": {ev.get("status"): 1} if noise else {}, "_ports": [port] if port is not None else []})
    for n, s in enumerate(steps, 1):
        s.pop("_key")
        s.pop("action_base")
        codes, ports = s.pop("_codes"), s.pop("_ports")
        s["step"] = n
        if ports:
            s["to"] += f":{ports[0]}" if len(ports) == 1 else f" ports {', '.join(map(str, ports[:12]))}" + \
                ("..." if len(ports) > 12 else "")
            if len(ports) > 1:
                s["action"] = re.sub(r" to port \d+", f" to {len(ports)} ports", s["action"])
        if len(codes) > 1:
            s["action"] = "Rejected / not served: " + ", ".join(f"HTTP {c} x{k}" for c, k in sorted(codes.items(), key=str))
            s["result"] = BLOCKED if all(c in (401, 403, 405, 406, 429) for c in codes) else FAILED
        elif s["count"] > 1 and len(ports) < 2:
            s["action"] = f"{s['action']} (x{s['count']})"
    if len(steps) > limit:
        steps = steps[:limit - 1] + [{"step": limit, "stage": "", "from": "", "via": "", "to": "", "users": [],
                                      "object": f"{len(steps) - limit + 1} further steps - see timeline",
                                      "action": "", "action_by": "", "result": INFO, "first": steps[limit - 1]["first"],
                                      "last": steps[-1]["last"], "count": 0, "evidence": []}]
    return steps


def path_summary(steps, limit=14):
    """Ordered unique systems the attack touched, e.g. 203.0.113.77 → VPN01 → DC01 → WS-BOB → 203.0.113.99."""
    nodes, seen = [], set()
    for s in steps:
        for part in (s.get("from"), s.get("to")):
            part = re.sub(r" ports [\d, .]+$", "", str(part or ""))
            for n in re.split(r" → |, ", part):
                n = re.sub(r" \[.*?\]$", "", n.strip())
                ip_name = re.match(r"^([\d.:a-fA-F]+?)(?::\d+)? \((.+?)\)(?::\d+)?$", n)
                if ip_name:
                    n = ip_name.group(2)          # "192.0.2.22 (WS-BOB)" -> "WS-BOB"
                else:
                    n = re.sub(r"^(\d+\.\d+\.\d+\.\d+):\d+$", r"\1", n)
                if n and n.lower() not in seen and not n.startswith("DNS"):
                    seen.add(n.lower())
                    nodes.append(n)
    if len(nodes) > limit:
        nodes = nodes[:limit] + [f"+{len(nodes) - limit} more"]
    return " → ".join(nodes)
