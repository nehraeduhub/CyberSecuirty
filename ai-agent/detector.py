"""Fast rule-based threat detection for common log formats.

Runs in milliseconds with no AI, so results show instantly. The AI model is
only given the compact summary from here, which keeps its replies fast.

Supported out of the box: Linux auth/syslog (SSH, sudo), web access logs
(Apache/Nginx), firewall logs (UFW/iptables), Windows event exports, and
shell/command history.
"""
import re
from collections import Counter, defaultdict
from urllib.parse import unquote_plus

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
WEB_ENUM_MIN_404 = 20
PORT_SCAN_MIN_PORTS = 10


def _clip(text):
    return text if len(text) <= MAX_SAMPLE_LEN else text[:MAX_SAMPLE_LEN] + "..."


class _Finding:
    def __init__(self, rid, title, severity, mitre):
        self.id, self.title, self.severity, self.mitre = rid, title, severity, mitre
        self.count = 0
        self.ips = Counter()
        self.samples = []

    def add(self, lineno, text, ips=()):
        self.count += 1
        self.ips.update(ips)
        if len(self.samples) < MAX_SAMPLES:
            self.samples.append({"line": lineno, "text": _clip(text)})

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "severity": self.severity,
            "mitre": self.mitre, "count": self.count,
            "ips": [ip for ip, _ in self.ips.most_common(10)],
            "samples": self.samples,
        }


def analyze(text):
    """Scan log text and return findings, stats and a 0-100 risk score."""
    findings = {}
    ip_counter = Counter()
    log_types = set()
    ssh_fail_by_ip = defaultdict(list)       # ip -> [(lineno, text)]
    ssh_ok_by_ip = defaultdict(list)
    web_404_by_ip = defaultdict(list)
    fw_ports_by_ip = defaultdict(set)
    fw_first_line = {}
    win_fail_by_ip = defaultdict(list)
    win_ok_by_ip = defaultdict(list)

    def hit(rule, lineno, line, ips):
        rid, title, sev, mitre = rule
        f = findings.get(rid)
        if f is None:
            f = findings[rid] = _Finding(rid, title, sev, mitre)
        f.add(lineno, line, ips)

    lines = text.splitlines()
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        ips = IP_RE.findall(line)
        ip_counter.update(ips)
        # Match against the URL-decoded line too, so %2e%2e%2f etc. is caught
        # " +0" is the timezone in web logs; don't let it trigger decoding of every line
        if "%" in line or "+" in line.replace(" +0", ""):
            haystack = (line + " " + unquote_plus(line)).lower()
        else:
            haystack = line.lower()

        for rid, title, sev, mitre, rx in COMPILED:
            if rx.search(haystack):
                hit((rid, title, sev, mitre), lineno, line, ips)

        if m := WEB_RE.match(line):
            log_types.add("web")
            if m.group(3) == "404":
                web_404_by_ip[m.group(1)].append((lineno, line))
        if m := SSH_FAIL_RE.search(line):
            log_types.add("auth")
            ssh_fail_by_ip[m.group(2)].append((lineno, line))
        if m := SSH_OK_RE.search(line):
            log_types.add("auth")
            ssh_ok_by_ip[m.group(2)].append((lineno, line))
        if m := FW_RE.search(line):
            log_types.add("firewall")
            ip = m.group(1)
            fw_ports_by_ip[ip].add(m.group(2))
            fw_first_line.setdefault(ip, (lineno, line))
        if WIN_FAIL_RE.search(haystack):
            log_types.add("windows")
            for ip in ips or ["unknown"]:
                win_fail_by_ip[ip].append((lineno, line))
        if WIN_OK_RE.search(haystack):
            for ip in ips or ["unknown"]:
                win_ok_by_ip[ip].append((lineno, line))

    # --- Correlation rules (patterns across many lines) ---
    def corr(rid, title, sev, mitre, ip, entries):
        f = findings.get(rid)
        if f is None:
            f = findings[rid] = _Finding(rid, title, sev, mitre)
        for lineno, line in entries:
            f.add(lineno, line, [ip])

    for ip, fails in ssh_fail_by_ip.items():
        if len(fails) >= BRUTE_FORCE_MIN:
            corr("ssh_bruteforce", "SSH brute-force attack", "high", "T1110.001", ip, fails)
            # Success after many failures from the same IP = likely compromise
            later_ok = [e for e in ssh_ok_by_ip.get(ip, []) if e[0] > fails[0][0]]
            if later_ok:
                corr("bruteforce_success", "Successful login after brute force (likely compromise)",
                     "critical", "T1078", ip, later_ok)
    for ip, fails in win_fail_by_ip.items():
        if len(fails) >= BRUTE_FORCE_MIN:
            corr("win_bruteforce", "Windows logon brute force / password spray", "high", "T1110.003",
                 ip, fails)
            later_ok = [e for e in win_ok_by_ip.get(ip, []) if e[0] > fails[0][0]]
            if later_ok:
                corr("bruteforce_success", "Successful login after brute force (likely compromise)",
                     "critical", "T1078", ip, later_ok)
    for ip, hits in web_404_by_ip.items():
        if len(hits) >= WEB_ENUM_MIN_404:
            corr("web_enum", "Web directory enumeration (many 404s)", "medium", "T1595.003", ip, hits)
    for ip, ports in fw_ports_by_ip.items():
        if len(ports) >= PORT_SCAN_MIN_PORTS:
            f = findings.setdefault("port_scan", _Finding("port_scan", "Port scan", "medium", "T1046"))
            lineno, line = fw_first_line[ip]
            f.add(lineno, f"{ip} probed {len(ports)} ports, e.g. {line}", [ip])
            f.count += len(ports) - 1

    if any(r in findings for r in ("download_exec", "reverse_shell", "persistence", "tmp_exec")):
        log_types.add("commands")

    result = sorted((f.to_dict() for f in findings.values()),
                    key=lambda f: (SEV_RANK[f["severity"]], -f["count"]))
    summary = {s: 0 for s in SEVERITIES}
    for f in result:
        summary[f["severity"]] += 1
    risk = min(100, sum(SEV_WEIGHT[f["severity"]] for f in result))

    return {
        "lines": len(lines),
        "log_types": sorted(log_types) or ["generic"],
        "risk_score": risk,
        "risk_level": ("critical" if risk >= 70 else "high" if risk >= 40
                       else "medium" if risk >= 8 else "low" if risk > 0 else "clean"),
        "summary": summary,
        "findings": result,
        "top_ips": ip_counter.most_common(10),
    }


def ai_context(result, max_findings=15):
    """Compact text version of the analysis for the AI prompt (keeps replies fast)."""
    out = [
        f"Lines scanned: {result['lines']} | Log types: {', '.join(result['log_types'])}",
        f"Risk score: {result['risk_score']}/100 ({result['risk_level']})",
        "Top IPs: " + ", ".join(f"{ip} ({n})" for ip, n in result["top_ips"][:5]),
        "Findings:",
    ]
    for f in result["findings"][:max_findings]:
        out.append(f"- [{f['severity'].upper()}] {f['title']} (MITRE {f['mitre']}) "
                   f"x{f['count']}; IPs: {', '.join(f['ips'][:5]) or 'n/a'}")
        for s in f["samples"][:2]:
            out.append(f"    line {s['line']}: {s['text'][:200]}")
    if not result["findings"]:
        out.append("- No rule matched. Look for anything unusual the rules may have missed.")
    return "\n".join(out)
