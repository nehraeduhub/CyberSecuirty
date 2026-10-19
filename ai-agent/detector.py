"""Fast rule-based threat detection for common log formats.

Runs in milliseconds with no AI, so results show instantly. The AI model is
only given the compact summary from here, which keeps its replies fast.

Supported out of the box: Linux auth/syslog (SSH, sudo), web access logs
(Apache/Nginx), firewall logs (UFW/iptables), Windows event exports, and
shell/command history.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from urllib.parse import unquote_plus, urlparse

import knowledge

SEVERITIES = ["critical", "high", "medium", "low", "info"]
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
SEV_WEIGHT = {"critical": 40, "high": 20, "medium": 8, "low": 2, "info": 0}

MAX_SAMPLES = 5
MAX_SAMPLE_LEN = 300

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
WEB_RE = re.compile(r'^(\S+) \S+ \S+ \[[^\]]+\] "(?:\S+) (\S+)[^"]*" (\d{3})')
SSH_FAIL_RE = re.compile(r"Failed (?:password|publickey) for (?:invalid user )?(\S+) from (\S+)")
SSH_OK_RE = re.compile(r"Accepted \S+ for (\S+) from (\S+)")
FW_RE = re.compile(r"SRC=(\S+).*?DPT=(\d+)")
WIN_FAIL_RE = re.compile(r"(?:eventid|event id|event_id)\D{0,3}4625")  # matched on lowercased lines
WIN_OK_RE = re.compile(r"(?:eventid|event id|event_id)\D{0,3}4624")

# (id, title, severity, MITRE ATT&CK technique, pattern)
LINE_RULES = [
    # --- Web attacks ---
    ("web_sqli", "SQL injection attempt", "high", "T1190",
     r"union(?:\s|\+|/\*.*?\*/)+(?:all\s+)?select|'\s*or\s*'?1'?\s*=\s*'?1|\bor\s+1=1\b"
     r"|sleep\(\d+\)|benchmark\(|information_schema|xp_cmdshell"),
    ("web_xss", "Cross-site scripting (XSS) attempt", "medium", "T1059.007",
     r"<script|javascript:|onerror\s*=|onload\s*=|alert\("),
    ("web_traversal", "Path traversal / sensitive file read", "high", "T1083",
     r"\.\./\.\./|\.\.\\\.\.\\|/etc/passwd|/etc/shadow|win\.ini|boot\.ini"),
    ("web_log4shell", "Log4Shell (JNDI) exploit attempt", "critical", "T1190",
     r"\$\{jndi:"),
    ("web_cmdi", "Command injection attempt", "critical", "T1059",
     r"(?:;|\||`|\$\()\s*(?:id|whoami|uname|cat\s|wget\s|curl\s)|cmd\.exe\s*/c"),
    ("web_shell", "Web shell command execution", "critical", "T1505.003",
     r"/(?:uploads?|images?|img|tmp|files|media|static|assets|wp-content)/[^\s?\"]+\.(?:php\d?|phtml|jspx?|aspx?|ashx|cgi)\?"
     r"[^\s\"]*\b(?:cmd|exec|command|execute|shell)="
     r"|/(?:c99|r57|wso|b374k|alfa|shell|cmd)\.(?:php|jsp|aspx?)\?[^\s\"]*="),
    ("web_scanner", "Attack tool / scanner detected", "medium", "T1595",
     r"sqlmap|nikto|nmap|masscan|zgrab|gobuster|dirbuster|feroxbuster|wpscan|nuclei|acunetix|hydra"),
    ("web_sensitive", "Probe for sensitive files", "medium", "T1595.003",
     r"/\.env\b|/\.git/|/\.aws/|wp-config\.php|/phpmyadmin|\.htpasswd|/server-status"),
    # --- Authentication ---
    ("ssh_fail", "Failed SSH login", "low", "T1110", SSH_FAIL_RE.pattern),
    ("ssh_invalid", "SSH login with invalid username", "low", "T1110.001",
     r"\]: invalid user \S+ from"),
    ("ssh_root_ok", "Successful root login over SSH", "high", "T1078.003",
     r"Accepted \S+ for root from"),
    ("sudo_fail", "Failed / unauthorized sudo", "medium", "T1548.003",
     r"sudo:.*(?:authentication failure|incorrect password attempts|NOT in sudoers)"),
    ("account_create", "User account created / privileged group change", "medium", "T1136",
     r"\buseradd\b|new user: name=|usermod\s.*-a?G\s*\S*(?:sudo|wheel|admin)"
     r"|(?:EventID|Event ID)\D{0,3}4720"),
    ("win_admin_group", "User added to privileged group (Windows)", "high", "T1098",
     r"(?:EventID|Event ID|event_id)\D{0,3}(?:4728|4732|4756)"),
    ("win_log_cleared", "Security log cleared (Windows)", "critical", "T1070.001",
     r"(?:EventID|Event ID|event_id)\D{0,3}1102|audit log was cleared"),
    ("win_logon_fail", "Failed Windows logon", "low", "T1110", WIN_FAIL_RE.pattern),
    # --- Malicious commands / malware ---
    ("download_exec", "Download piped to shell", "critical", "T1105",
     r"(?:wget|curl)\s[^|;\n]*\|\s*(?:sudo\s+)?(?:ba)?sh"),
    ("reverse_shell", "Reverse shell", "critical", "T1059.004",
     r"\bnc(?:at)?\s+(?:-\S+\s+)*-e\s|/dev/tcp/|bash\s+-i\s*>&|socat\s.*exec"
     r"|python[23]?\s+-c\s+['\"]import\s+socket"),
    ("encoded_powershell", "Encoded PowerShell command", "high", "T1059.001",
     r"powershell(?:\.exe)?\s.*-(?:e|enc|encodedcommand)\s"),
    ("cred_dump", "Credential dumping tool", "critical", "T1003",
     r"mimikatz|sekurlsa|lsass\.dmp|procdump.*lsass|hashdump"),
    ("persistence", "Persistence mechanism (cron/service/run key)", "medium", "T1053",
     r"crontab\s+-[er]\b|\|\s*crontab|>>?\s*/etc/cron|authorized_keys|systemctl\s+enable|schtasks\s+/create"
     r"|CurrentVersion\\Run"),
    ("tmp_exec", "Executable dropped in temp directory", "high", "T1059",
     r"chmod\s+\+?[0-7]*x\s+/(?:tmp|dev/shm|var/tmp)|[\s(]/(?:tmp|dev/shm)/\.\w+"),
    ("log_tamper", "Log tampering / anti-forensics", "high", "T1070",
     r"rm\s+(?:-\S+\s+)*/var/log|history\s+-c|unset\s+HISTFILE|shred\s.*log|wevtutil\s+cl"),
    ("crypto_miner", "Cryptocurrency miner", "high", "T1496",
     r"xmrig|stratum\+tcp|minerd|cryptonight"),
]


def _lower_pattern(p):
    # Lines are lowercased once before matching, which is much faster than re.I.
    # Lowercase the pattern's literals but keep escapes like \S and \D intact.
    return re.sub(r"(\\.)|([A-Z])", lambda m: m.group(1) or m.group(2).lower(), p)


COMPILED = [(rid, title, sev, mitre, re.compile(_lower_pattern(p))) for rid, title, sev, mitre, p in LINE_RULES]

# Thresholds for correlation rules
BRUTE_FORCE_MIN = 5
BRUTE_FORCE_WINDOW = timedelta(minutes=10)   # failures must form a burst, not be spread over days
SUCCESS_AFTER = timedelta(hours=1)
WEB_ENUM_MIN_404 = 20
PORT_SCAN_MIN_PORTS = 10


def _clip(text):
    return text if len(text) <= MAX_SAMPLE_LEN else text[:MAX_SAMPLE_LEN] + "..."


# Timestamps are only parsed for suspicious lines, so they cost nothing on clean logs
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
TS_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})")
TS_WEB = re.compile(r"\[(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})")
TS_SYSLOG = re.compile(r"^(\w{3})\s+(\d{1,2}) (\d{2}):(\d{2}):(\d{2})")
URL_RE = re.compile(r"\b(?:https?|ldap|ldaps|rmi|ftp)://[^\s\"'|;)<>]+", re.I)
FILE_RE = re.compile(r"(?<![\w/])/(?:tmp|dev/shm|var/tmp)/[\w.\-]+|[A-Za-z]:\\(?:Users\\Public|Windows\\Temp|ProgramData)\\[\w.\-]+")
ACCOUNT_RE = re.compile(r"(?:New Account|Account|Member|new user: name)=([\w.$-]+)")


def parse_ts(line):
    try:
        if m := TS_ISO.search(line):
            return datetime(*map(int, m.groups()))
        if m := TS_WEB.search(line):
            d, mon, y, hh, mm, ss = m.groups()
            return datetime(int(y), _MONTHS[mon.lower()], int(d), int(hh), int(mm), int(ss))
        if m := TS_SYSLOG.match(line):
            mon, d, hh, mm, ss = m.groups()
            return datetime(datetime.now().year, _MONTHS[mon.lower()], int(d), int(hh), int(mm), int(ss))
    except (KeyError, ValueError):
        pass
    return None


def _fmt(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S") if ts else None


class _Finding:
    def __init__(self, rid, title, severity, mitre):
        self.id, self.title, self.severity, self.mitre = rid, title, severity, mitre
        self.count = 0
        self.ips = Counter()
        self.samples = []
        self.refs = []
        self.first = self.last = None

    def add(self, lineno, text, ips=(), ts=None, ref=None):
        self.count += 1
        self.ips.update(ips)
        if ts:
            self.first = min(self.first or ts, ts)
            self.last = max(self.last or ts, ts)
        if len(self.samples) < MAX_SAMPLES:
            self.samples.append({"line": lineno, "text": _clip(text), "ref": ref or f"line {lineno}"})
        if len(self.refs) < MAX_REFS:
            self.refs.append(ref or f"line {lineno}")

    def to_dict(self):
        return knowledge.enrich({
            "id": self.id, "title": self.title, "severity": self.severity,
            "mitre": self.mitre, "count": self.count,
            "ips": [ip for ip, _ in self.ips.most_common(10)],
            "first_seen": _fmt(self.first), "last_seen": _fmt(self.last),
            "samples": self.samples, "evidence_refs": self.refs, "method": "signature",
        })


MAX_REFS = 200        # evidence references kept per finding
MAX_KEEP = 200        # lines kept per correlation key (counts stay exact)


class _Capped:
    """List that keeps the first MAX_KEEP items but counts all of them."""
    __slots__ = ("items", "n")

    def __init__(self):
        self.items, self.n = [], 0

    def append(self, x):
        self.n += 1
        if len(self.items) < MAX_KEEP:
            self.items.append(x)


class LogAnalyzer:
    """Streaming signature + correlation engine. feed() one line at a time, then result()."""

    def __init__(self):
        self.findings = {}
        self.ip_counter = Counter()
        self.log_types = set()
        self.ssh_fail_by_ip = defaultdict(_Capped)      # ip -> [(lineno, text, ref)]
        self.ssh_ok_by_ip = defaultdict(_Capped)
        self.web_404_by_ip = defaultdict(_Capped)
        self.fw_ports_by_ip = defaultdict(set)
        self.fw_first_line = {}
        self.win_fail_by_ip = defaultdict(_Capped)
        self.win_ok_by_ip = defaultdict(_Capped)
        self.targeted_users = Counter()
        self.ts_cache = {}                           # lineno -> datetime (suspicious lines only)
        self.suspicious = {}                         # lineno -> line
        self.profiles = defaultdict(lambda: {"lines": set(), "rules": set(), "sev": 9, "first": None, "last": None})
        self.lines = 0
        self.first_ts = self.last_ts = None
        self._cur = (None, None)   # (lineno, ts) of the line being fed - avoids storing every timestamp

    def _ts_of(self, lineno, line):
        if lineno not in self.ts_cache:
            given = self._cur[1] if self._cur[0] == lineno else None
            self.ts_cache[lineno] = given or parse_ts(line)
        return self.ts_cache[lineno]

    def _record(self, f, lineno, line, ips, ref=None):
        ts = self._ts_of(lineno, line)
        f.add(lineno, line, ips, ts, ref)
        if len(self.suspicious) < 500000:
            self.suspicious[lineno] = line
        for ip in set(ips):
            p = self.profiles[ip]
            if len(p["lines"]) < 100000:
                p["lines"].add(lineno)
            p["rules"].add(f.title)
            p["sev"] = min(p["sev"], SEV_RANK[f.severity])
            if ts:
                p["first"] = min(p["first"] or ts, ts)
                p["last"] = max(p["last"] or ts, ts)

    def _hit(self, rule, lineno, line, ips, ref):
        rid, title, sev, mitre = rule
        f = self.findings.get(rid)
        if f is None:
            f = self.findings[rid] = _Finding(rid, title, sev, mitre)
        self._record(f, lineno, line, ips, ref)

    def feed(self, line, lineno=None, ref=None, ts=None):
        self.lines += 1
        lineno = lineno or self.lines
        if not line.strip():
            return
        self._cur = (lineno, ts)
        if ts is not None:
            self.first_ts = min(self.first_ts or ts, ts)
            self.last_ts = max(self.last_ts or ts, ts)
        ips = IP_RE.findall(line)
        self.ip_counter.update(ips)
        # Match against the URL-decoded line too, so %2e%2e%2f etc. is caught
        # " +0" is the timezone in web logs; don't let it trigger decoding of every line
        if "%" in line or "+" in line.replace(" +0", ""):
            haystack = (line + " " + unquote_plus(line)).lower()
        else:
            haystack = line.lower()

        for rid, title, sev, mitre, rx in COMPILED:
            if rx.search(haystack):
                self._hit((rid, title, sev, mitre), lineno, line, ips, ref)

        entry = (lineno, line, ref, ts or parse_ts(line))
        if m := WEB_RE.match(line):
            self.log_types.add("web")
            if m.group(3) == "404":
                self.web_404_by_ip[m.group(1)].append(entry)
        if m := SSH_FAIL_RE.search(line):
            self.log_types.add("auth")
            self.ssh_fail_by_ip[m.group(2)].append(entry)
            self.targeted_users[m.group(1)] += 1
        if m := SSH_OK_RE.search(line):
            self.log_types.add("auth")
            self.ssh_ok_by_ip[m.group(2)].append(entry)
        if m := FW_RE.search(line):
            self.log_types.add("firewall")
            ip = m.group(1)
            self.fw_ports_by_ip[ip].add(m.group(2))
            self.fw_first_line.setdefault(ip, entry)
        if WIN_FAIL_RE.search(haystack):
            self.log_types.add("windows")
            for ip in ips or ["unknown"]:
                self.win_fail_by_ip[ip].append(entry)
        if WIN_OK_RE.search(haystack):
            for ip in ips or ["unknown"]:
                self.win_ok_by_ip[ip].append(entry)

    def _corr(self, rid, title, sev, mitre, ip, entries):
        f = self.findings.get(rid)
        if f is None:
            f = self.findings[rid] = _Finding(rid, title, sev, mitre)
        items = entries.items if isinstance(entries, _Capped) else entries
        for lineno, line, ref, _ in items:
            self._record(f, lineno, line, [ip], ref)
        if isinstance(entries, _Capped):
            f.count += entries.n - len(items)

    def result(self):
        # --- Correlation rules (patterns across many lines) ---
        for fail_map, ok_map, rid, title, mitre in (
                (self.ssh_fail_by_ip, self.ssh_ok_by_ip, "ssh_bruteforce", "SSH brute-force attack", "T1110.001"),
                (self.win_fail_by_ip, self.win_ok_by_ip, "win_bruteforce",
                 "Windows logon brute force / password spray", "T1110.003")):
            for ip, fails in fail_map.items():
                burst = _burst(fails)
                if burst is None:
                    continue
                self._corr(rid, title, "high", mitre, ip, fails)
                # Success from the same IP soon after the burst = likely compromise
                end = burst[-1][3]
                later_ok = [e for e in ok_map[ip].items if e[0] > burst[0][0] and
                            (end is None or e[3] is None or timedelta(0) <= e[3] - end <= SUCCESS_AFTER)] \
                    if ip in ok_map else []
                if later_ok:
                    self._corr("bruteforce_success", "Successful login after brute force (likely compromise)",
                               "critical", "T1078", ip, later_ok)
        for ip, hits in self.web_404_by_ip.items():
            if hits.n >= WEB_ENUM_MIN_404:
                self._corr("web_enum", "Web directory enumeration (many 404s)", "medium", "T1595.003", ip, hits)
        for ip, ports in self.fw_ports_by_ip.items():
            if len(ports) >= PORT_SCAN_MIN_PORTS:
                f = self.findings.setdefault("port_scan", _Finding("port_scan", "Port scan", "medium", "T1046"))
                lineno, line, ref, _ = self.fw_first_line[ip]
                self._record(f, lineno, f"{ip} probed {len(ports)} ports, e.g. {line}", [ip], ref)
                f.count += len(ports) - 1

        if any(r in self.findings for r in ("download_exec", "reverse_shell", "persistence", "tmp_exec")):
            self.log_types.add("commands")

        result = sorted((f.to_dict() for f in self.findings.values()),
                        key=lambda f: (SEV_RANK[f["severity"]], -f["count"]))
        out = score(result)
        out.update({
            "kind": "logs",
            "lines": self.lines,
            "log_types": sorted(self.log_types) or ["generic"],
            "top_ips": [(ip, n) for ip, n in self.ip_counter.most_common(30) if knowledge.valid_ip(ip)][:10],
            "suspicious_lines": len(self.suspicious),
        })
        out.update(_enrichment(self.suspicious, self.ts_cache, self.profiles, self.targeted_users,
                               self.first_ts, self.last_ts))
        return out


def _burst(fails):
    """The first window of >= BRUTE_FORCE_MIN failures within BRUTE_FORCE_WINDOW, else None.
    Lines without timestamps fall back to a plain count."""
    items = fails.items
    if fails.n < BRUTE_FORCE_MIN:
        return None
    timed = sorted((e for e in items if e[3]), key=lambda e: e[3])
    if len(timed) < len(items) * 0.5:
        return items
    j = 0
    for i in range(len(timed)):
        while timed[i][3] - timed[j][3] > BRUTE_FORCE_WINDOW:
            j += 1
        if i - j + 1 >= BRUTE_FORCE_MIN:
            return timed[j:i + 1]
    return None


def analyze(text):
    """Scan log text and return findings, stats and a 0-100 risk score."""
    a = LogAnalyzer()
    lines = text.splitlines()
    for lineno, line in enumerate(lines, 1):
        a.feed(line, lineno)
    first = next((t for t in (parse_ts(x) for x in lines[:50]) if t), None)
    last = next((t for t in (parse_ts(x) for x in reversed(lines[-50:])) if t), None)
    a.first_ts, a.last_ts = a.first_ts or first, a.last_ts or last
    return a.result()


def score(findings):
    """Severity counts, 0-100 risk score, risk level and A-F grade for a list of findings."""
    summary = {s: 0 for s in SEVERITIES}
    for f in findings:
        summary[f["severity"]] += 1
    risk = min(100, sum(SEV_WEIGHT[f["severity"]] for f in findings))
    level = ("critical" if risk >= 70 else "high" if risk >= 40
             else "medium" if risk >= 8 else "low" if risk > 0 else "clean")
    grade = "A" if risk == 0 else "B" if risk < 8 else "C" if risk < 25 else "D" if risk < 40 \
        else "E" if risk < 70 else "F"
    return {"findings": findings, "summary": summary, "risk_score": risk,
            "risk_level": level, "grade": grade}


def _enrichment(suspicious, ts_cache, profiles, targeted_users, first_ts=None, last_ts=None):
    # Attacker profiles
    ip_profiles = []
    for ip, p in profiles.items():
        if not knowledge.valid_ip(ip):
            continue
        sev = SEVERITIES[p["sev"]] if p["sev"] < len(SEVERITIES) else "info"
        verdict = ("Malicious" if sev in ("critical", "high") else
                   "Suspicious" if sev == "medium" else "Noisy")
        ip_profiles.append({
            "ip": ip, "public": knowledge.is_public_ip(ip), "events": len(p["lines"]),
            "severity": sev, "verdict": verdict, "activity": sorted(p["rules"]),
            "first_seen": _fmt(p["first"]), "last_seen": _fmt(p["last"]),
        })
    ip_profiles.sort(key=lambda x: (SEV_RANK[x["severity"]], -x["events"]))

    # Timeline of suspicious events (hourly, or daily for long ranges)
    stamps = [t for ln, t in ts_cache.items() if t and ln in suspicious]
    timeline, bucket = [], "hour"
    if stamps:
        span_h = (max(stamps) - min(stamps)).total_seconds() / 3600
        if span_h <= 3:
            bucket = "5 min"
            keys = (t.replace(minute=t.minute - t.minute % 5).strftime("%Y-%m-%d %H:%M") for t in stamps)
        elif span_h <= 72:
            bucket, keys = "hour", (t.strftime("%Y-%m-%d %H:00") for t in stamps)
        else:
            bucket, keys = "day", (t.strftime("%Y-%m-%d") for t in stamps)
        timeline = sorted(Counter(keys).items())

    # Indicators of compromise from suspicious lines only
    urls, files, users = set(), set(), Counter(targeted_users)
    for line in suspicious.values():
        urls.update(u.rstrip(".,}") for u in URL_RE.findall(line))
        files.update(FILE_RE.findall(line))
        users.update(ACCOUNT_RE.findall(line))
    domains = sorted({urlparse(u).hostname for u in urls if urlparse(u).hostname
                      and not knowledge.valid_ip(urlparse(u).hostname)})
    bad_ips = [p["ip"] for p in ip_profiles if p["verdict"] in ("Malicious", "Suspicious")]
    return {
        "time_range": {"start": _fmt(first_ts), "end": _fmt(last_ts)},
        "timeline": timeline, "timeline_bucket": bucket,
        "ip_profiles": ip_profiles[:50],
        "targeted_users": users.most_common(15),
        "iocs": {"ips": bad_ips, "urls": sorted(urls)[:50], "domains": domains[:50],
                 "files": sorted(files)[:50], "users": [u for u, _ in users.most_common(15)]},
    }


def ai_context(result, max_findings=12):
    """Compact text version of the analysis for the AI prompt (keeps replies fast).

    Explanations and fixes are already computed locally, so only facts are sent;
    fewer prompt tokens means the model starts answering sooner.
    """
    kind = result.get("kind", "logs")
    out = []
    if kind == "host":
        h = result.get("host", {})
        out.append(f"Live host audit of {h.get('hostname')} ({h.get('os')}, kernel {h.get('kernel')})")
    else:
        tr = result.get("time_range") or {}
        out.append(f"Log scan: {result.get('lines')} lines, types: {', '.join(result.get('log_types', []))}, "
                   f"time {tr.get('start') or '?'} to {tr.get('end') or '?'}")
    out.append(f"Risk {result['risk_score']}/100 ({result['risk_level']}), grade {result.get('grade', '-')}")
    out.append("Findings:")
    for f in result["findings"][:max_findings]:
        where = f", IPs {', '.join(f['ips'][:4])}" if f.get("ips") else ""
        when = ""
        if f.get("first_seen"):
            when = f", at {f['first_seen']}" if f["first_seen"] == f["last_seen"] \
                else f", {f['first_seen']}..{f['last_seen']}"
        out.append(f"- [{f['severity'].upper()}] {f['title']} ({f.get('mitre', '-')}) x{f.get('count', 1)}{where}{when}")
        if f.get("samples"):
            out.append(f"    e.g. {f['samples'][0]['text'][:160]}")
    if not result["findings"]:
        out.append("- No rule matched. Look for anything unusual the rules may have missed.")
    profiles = result.get("ip_profiles") or []
    if profiles:
        out.append("Attacker IPs:")
        for p in profiles[:5]:
            out.append(f"- {p['ip']} {p['verdict']} ({p['events']} events): {'; '.join(p['activity'][:4])}")
    if result.get("targeted_users"):
        out.append("Accounts involved: " + ", ".join(u for u, _ in result["targeted_users"][:8]))
    return "\n".join(out)
