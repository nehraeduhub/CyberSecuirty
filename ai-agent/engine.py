"""Structured analytics on normalised events: rules, UEBA, statistics, threat intel, forensics.

Complements detector.py (regex signatures on raw text). Every finding carries the rule
catalogue id, evidence references (file:line) and the numbers that triggered it, so each
conclusion can be traced back to original records. All state is bounded: per-key lists
keep a capped number of references while counts stay exact.
"""
import csv
import ipaddress
from array import array
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config_store
import rules as rulebook
import trust

ADMIN_PORTS = {22, 135, 139, 445, 3389, 5985, 5986}
SAMPLES, REFS = 5, 200
RX = {
    "TG-EXE-001": re.compile(r"downloadstring|downloadfile|invoke-webrequest|\biwr\b.+\|\s*iex|\biex\b|"
                             r"invoke-expression|net\.webclient|start-bitstransfer|\s-e(nc|ncodedcommand)?\s+[a-z0-9+/=]{20,}|"
                             r"frombase64string", re.I),
    "TG-EXE-002": re.compile(r"certutil(\.exe)?\s.*-urlcache|mshta(\.exe)?\s+(https?|javascript|vbscript):|"
                             r"regsvr32(\.exe)?\s.*/i:https?|rundll32(\.exe)?\s.*javascript:|bitsadmin(\.exe)?\s.*/transfer|"
                             r"installutil(\.exe)?\s.*/u|msbuild(\.exe)?\s+\S+\.(xml|csproj)", re.I),
    "TG-EXE-003": re.compile(r"\\users\\public\\|\\appdata\\local\\temp\\|\\windows\\temp\\|\\programdata\\[^\\]+\.exe|"
                             r"\\\$recycle\.bin\\|(^|\s)/(tmp|dev/shm|var/tmp)/", re.I),
    "TG-MAL-001": re.compile(r"vssadmin(\.exe)?\s+delete\s+shadows|wmic(\.exe)?\s+shadowcopy\s+delete|"
                             r"wbadmin(\.exe)?\s+delete\s+(catalog|systemstatebackup)|bcdedit(\.exe)?\s.*recoveryenabled\s+no|"
                             r"bcdedit(\.exe)?\s.*bootstatuspolicy\s+ignoreallfailures|cipher(\.exe)?\s+/w|"
                             r"\.(locked|encrypted|crypt|ryk)\b.*rename|readme[-_]?(to[-_]?)?decrypt", re.I),
    "TG-DEF-001": re.compile(r"set-mppreference\s.*-disable(realtimemonitoring|behaviormonitoring|ioavprotection)|"
                             r"sc(\.exe)?\s+(stop|config)\s+(windefend|sense|wdnissvc)|net\s+stop\s+(windefend|\"?windows defender)|"
                             r"auditctl\s+-e\s*0|auditctl\s+-D|systemctl\s+(stop|disable|mask)\s+(auditd|rsyslog|systemd-journald|"
                             r"firewalld|ufw|falcon|wazuh|osquery)|ufw\s+disable|iptables\s+-F|setenforce\s+0|"
                             r"netsh\s+(advfirewall|firewall)\s+set\s+\S*\s*state\s+off|"
                             r"add-mppreference\s+-exclusionpath", re.I),
    "TG-CRED-001": re.compile(r"sekurlsa|lsadump|mimikatz|procdump(64)?(\.exe)?\s.*lsass|comsvcs(\.dll)?,?\s*minidump|"
                              r"ntdsutil.*ifm|reg(\.exe)?\s+save\s+hklm\\(sam|system|security)|hashdump|secretsdump|"
                              r"rubeus|kerberoast", re.I),
    "TG-DB-001": re.compile(r"\bbcp\b.*\bqueryout\b|mysqldump\b|pg_dump\b|pg_dumpall\b|\bexpdp\b|\bexp\s+\w+/|"
                            r"into\s+outfile|copy\s+\(?select.*\)?\s+to\s+'|sqlcmd.*-o\s|mongoexport|mongodump", re.I),
    "TG-EXF-002": re.compile(r"7z(a|\.exe)?\s+a\s+.*-p|\brar(\.exe)?\s+a\s+.*-hp|\bzip\s+.*-(P|e)\s|"
                             r"compress-archive.*-destinationpath|\btar\s+-?c\w*z\w*f\s+\S+\s+(/etc|/home|/var/lib|/srv)", re.I),
    "TG-LNX-001": re.compile(r"(visudo|vi|vim|nano|tee|sed\s+-i|echo).*(/etc/sudoers|/etc/ssh/sshd_config|/etc/passwd|"
                             r"/etc/shadow|/etc/pam\.d/)|chmod\s+[0-7]*[2367]\s+/etc/(passwd|shadow|sudoers)", re.I),
    "TG-NET-006": re.compile(r"firewall (policy|rule)s? (modified|added|changed|deleted)|policy (modified|changed)|"
                             r"%(asa|ftd)-\d-1110(08|10)|configured from|config(uration)? change|"
                             r"netsh\s+advfirewall\s+firewall\s+(add|delete|set)|iptables\s+-[AID]\s|new-netfirewallrule", re.I),
}
WEB_PARENTS = re.compile(r"w3wp|httpd|apache2?|nginx|php-?fpm|tomcat|java(w)?\.exe|winword|excel|powerpnt|outlook|"
                         r"mshta|wscript", re.I)
SHELLS = re.compile(r"\\(cmd|powershell|pwsh|wscript|cscript|bash|sh)(\.exe)?$|^/bin/(ba)?sh$|^(cmd|powershell|sh|bash)(\.exe)?$", re.I)
HEX_RE = re.compile(r"\b[a-f0-9]{64}\b|\b[a-f0-9]{40}\b|\b[a-f0-9]{32}\b", re.I)


def _fmt(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S") if ts else None


def _clip(s, n=300):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def robust_z(values):
    """Median/MAD z-scores - not fooled by the very outliers we are looking for."""
    if len(values) < 5:
        return [0.0] * len(values)
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values) * 1.4826
    if mad == 0:
        mean = sum(values) / len(values)
        sd = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 or 1
        return [(v - med) / sd for v in values]
    return [(v - med) / mad for v in values]


def entropy(s):
    if not s:
        return 0.0
    c = Counter(s)
    return -sum(n / len(s) * math.log2(n / len(s)) for n in c.values())


def _utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)


def _usual_hours(hours):
    """Smallest contiguous (circular) hour window holding 80% of the logons."""
    total = sum(hours.values()) or 1
    best = (0, 23)
    for width in range(1, 25):
        for start in range(24):
            if sum(hours.get((start + i) % 24, 0) for i in range(width)) >= 0.8 * total:
                return start, (start + width - 1) % 24
    return best


def base_domain(name):
    parts = str(name).lower().rstrip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else name


# ------------------------------------------------------------------ threat intelligence feeds

def load_iocs(paths=None):
    """Offline IoC feeds from config/ioc/*.csv|*.txt (type,value,source,description)."""
    paths = paths if paths is not None else sorted((config_store.CONFIG_DIR / "ioc").glob("*"))
    iocs = {"ip": {}, "domain": {}, "url": {}, "hash": {}}
    errors = []
    for p in paths:
        p = Path(p)
        if p.suffix.lower() not in (".csv", ".txt"):
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                if p.suffix.lower() == ".csv":
                    for row in csv.DictReader(fh):
                        _add_ioc(iocs, row.get("type"), row.get("value"), row.get("source") or p.name,
                                 row.get("description") or "")
                else:
                    for line in fh:
                        v = line.split("#")[0].strip()
                        if v:
                            _add_ioc(iocs, None, v, p.name, "")
        except OSError as e:
            errors.append(f"{p.name}: {e}")
    return iocs, errors


def _add_ioc(iocs, typ, value, source, desc):
    v = str(value or "").strip()
    if not v:
        return
    t = (typ or "").strip().lower()
    if not t:
        try:
            ipaddress.ip_address(v)
            t = "ip"
        except ValueError:
            t = "url" if "://" in v else "hash" if re.fullmatch(r"[A-Fa-f0-9]{32,64}", v) else "domain"
    t = {"ipv4": "ip", "ipv6": "ip", "md5": "hash", "sha1": "hash", "sha256": "hash", "fqdn": "domain",
         "hostname": "domain"}.get(t, t)
    if t in iocs:
        iocs[t][v.lower()] = {"value": v, "type": t, "source": source, "description": desc}


# ------------------------------------------------------------------ finding accumulator

class EF:
    """One structured finding being accumulated."""
    __slots__ = ("rule", "title", "key", "count", "samples", "refs", "ips", "users", "hosts", "first", "last",
                 "details", "severity", "notes")

    def __init__(self, rule, title, key):
        self.rule, self.title, self.key = rule, title, key
        self.count, self.samples, self.refs = 0, [], []
        self.ips, self.users, self.hosts = Counter(), Counter(), Counter()
        self.first = self.last = None
        self.details, self.notes = {}, []
        self.severity = rule["severity"]

    def add(self, ev, text=None):
        self.count += 1
        ts = ev.get("ts")
        if ts:
            self.first = min(self.first or ts, ts)
            self.last = max(self.last or ts, ts)
        for f in ("src_ip", "dst_ip", "assigned_ip"):
            if ev.get(f):
                self.ips[ev[f]] += 1
        if ev.get("user"):
            self.users[ev["user"]] += 1
        if ev.get("host"):
            self.hosts[ev["host"]] += 1
        if len(self.samples) < SAMPLES:
            self.samples.append({"ref": ev.get("ref"), "line": ev.get("line"),
                                 "text": _clip(text or ev.get("raw") or ev.get("text", ""))})
        if len(self.refs) < REFS and ev.get("ref"):
            self.refs.append(ev["ref"])

    def to_dict(self):
        r = self.rule
        mitre = r["mitre"]
        return {
            "id": r["id"].lower().replace("-", "_") + (f"__{self.key}" if self.key else ""), "rule_id": r["id"],
            "title": self.title, "severity": self.severity, "confidence": r["confidence"], "method": r["method"],
            "category": r["category"], "mitre": mitre[0] if mitre else "-", "mitre_list": mitre,
            "count": self.count, "ips": [i for i, _ in self.ips.most_common(10)],
            "users": [u for u, _ in self.users.most_common(10)], "hosts": [h for h, _ in self.hosts.most_common(10)],
            "first_seen": _fmt(self.first), "last_seen": _fmt(self.last), "samples": self.samples,
            "evidence_refs": self.refs, "description": r["description"], "impact": r["impact"],
            "recommendation": r["recommendation"], "fp": r["fp"], "telemetry": r["telemetry"],
            "limitation": r["limitation"], "details": self.details, "notes": self.notes,
        }


class _Discard:
    """Sink for hits of a disabled rule: accepts everything, stores nothing."""
    def __init__(self):
        self.details, self.notes, self.refs, self.count, self.severity = {}, [], [], 0, "info"
        self.first = self.last = None

    def add(self, *a, **k):
        pass


class Engine:
    def __init__(self, rules=None, inventory=None, iocs=None):
        self.rules = rules or rulebook.load()[0]
        self.inv = inventory
        self.iocs = iocs or {"ip": {}, "domain": {}, "url": {}, "hash": {}}
        self.found = {}
        self.auth = []                   # (ts, user, src, host, outcome, logon_type, source, ref, event_id, ev-lite)
        self.vpn_assign = {}             # assigned ip -> (user, public src, session)
        self.priv = defaultdict(list)    # user -> [(ts, ref)]
        self.scan = defaultdict(lambda: defaultdict(set))
        self.scan_ev = {}
        self.scan_open = defaultdict(dict)    # (src, dst) -> {port: lite event} for ports the device let through
        self.scan_denied = Counter()
        self.denies = defaultdict(list)
        self.deny_n = Counter()
        self.beacons = {}                # (src, dst, port) -> [array of epoch seconds, first lites, refs]
        self.bytes = defaultdict(lambda: [0, None])
        self.per_min = {}                # dst -> [minute, count, peak, peak_minute] (streaming, bounded)
        self.dns = defaultdict(lambda: {"n": 0, "long": 0, "txt": 0, "evs": [], "labels": []})
        self.nx = defaultdict(list)
        self.web = defaultdict(lambda: {"n": 0, "paths": set(), "err_paths": set(), "evs": [], "times": []})
        self.ids = {}
        self.vol = defaultdict(Counter)  # file -> 5-min bucket counts
        self.forensic = defaultdict(lambda: {"prev": None, "backwards": [], "future": [], "intervals": [],
                                             "n": 0, "gaps": [], "first": None, "last": None})
        self.ti_hits = {}
        self.host_ips = defaultdict(set)  # hostname -> ips observed
        self.ip_hosts = defaultdict(set)
        self.events = 0
        self.has = Counter()             # telemetry types seen (for the limitations section)
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)

    # ------------------------------------------------------------ helpers
    def rule(self, rid):
        r = self.rules.get(rid)
        return r if r and r.get("enabled", True) else None

    def _f(self, rid, key):
        return self.found.get((rid, key)) or _Discard()

    def hit(self, rid, key, ev, title=None, text=None):
        r = self.rule(rid)
        if not r:
            return _Discard()
        f = self.found.get((rid, key))
        if f is None:
            f = self.found[(rid, key)] = EF(r, title or r["name"], key)
        f.add(ev, text)
        return f

    def cls(self, ip, ts=None):
        if not self.inv or not ip:
            return None
        return self.inv.classify(ip, ts)

    def external(self, ip, ts=None):
        try:
            a = ipaddress.ip_address(str(ip))
        except ValueError:
            return False
        c = self.cls(ip, ts)
        if c:
            return c["category"] in ("public_unknown", "suspicious_indicator", "known_external_service")
        return not (a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified or trust.is_private_ip(ip))

    # ------------------------------------------------------------ per event
    def observe(self, ev):
        self.events += 1
        ts = ev.get("ts")
        st = ev.get("source_type", "generic")
        self.has[st] += 1
        eid = str(ev.get("event_id") or "")
        text_l = None
        self._forensics(ev, ts)
        if ts:
            self.vol[ev.get("file")][ts.replace(minute=ts.minute - ts.minute % 5, second=0, microsecond=0)] += 1
        if ev.get("host") and ev.get("src_ip") and eid in ("4624", "4625") and ev.get("src_host"):
            self.host_ips[ev["src_host"].upper()].add(ev["src_ip"])
            self.ip_hosts[ev["src_ip"]].add(ev["src_host"].upper())
        if ev.get("assigned_ip") and ev.get("user"):
            self.vpn_assign[ev["assigned_ip"]] = (ev["user"], ev.get("src_ip"), ev.get("session_id"), ev.get("ref"))

        # ---- authentication
        outcome = self._auth_outcome(ev, eid)
        if outcome:
            self.has["auth"] += 1
            lt = ev.get("logon_type")
            self.auth.append((ts, (ev.get("user") or "").lower(), ev.get("src_ip"), (ev.get("host") or "").upper(),
                              outcome, lt, st, ev.get("ref"), eid, self._lite(ev)))
        if eid == "4740":
            self.hit("TG-AUTH-005", "", ev, f"Account lockout: {ev.get('user') or 'account'}")
        if eid in ("4672",) and ev.get("user"):
            self.priv[ev["user"].lower()].append((ts, ev.get("ref"), self._lite(ev)))
        if ev.get("action") == "sudo" or (ev.get("process") == "sudo" and ev.get("user")):
            self.priv[(ev.get("user") or "").lower()].append((ts, ev.get("ref"), self._lite(ev)))

        # ---- process / command based signatures
        cmd = " ".join(str(ev.get(k, "")) for k in ("command", "process") if ev.get(k))
        if cmd:
            self.has["process"] += 1
            for rid, rx in RX.items():
                if rid == "TG-NET-006":
                    continue
                if rx.search(cmd):
                    title = None
                    if rid == "TG-EXE-003":
                        if not ev.get("process") or not RX[rid].search(str(ev.get("process"))):
                            continue
                    self.hit(rid, (ev.get("host") or "").upper(), ev, title, text=f"{ev.get('host', '')} "
                             f"{ev.get('user', '')}: {cmd}")
            parent = str(ev.get("parent_process") or "")
            if parent and WEB_PARENTS.search(parent) and SHELLS.search(str(ev.get("process") or "").strip()):
                self.hit("TG-EXE-004", (ev.get("host") or "").upper(), ev,
                         text=f"{parent} -> {ev.get('process')} {ev.get('command', '')}")
        if eid in ("7045", "4697"):
            self.hit("TG-PER-001", (ev.get("host") or "").upper(), ev,
                     f"New service installed on {ev.get('host') or 'host'}: {ev.get('service') or ''}".strip())
        if eid in ("4698", "4702") and not ev.get("command"):
            self.hit("TG-PER-002", (ev.get("host") or "").upper(), ev)
        if eid in ("4719", "4907"):
            self.hit("TG-FOR-001", (ev.get("host") or "").upper(), ev)
        if eid in ("1100", "104") or re.search(r"(rsyslogd|auditd|journald).{0,40}(exiting|stopped|shutdown)|"
                                               r"event logging service has shut down", ev.get("text", "")[:400], re.I):
            self.hit("TG-FOR-002", (ev.get("host") or "").upper(), ev)

        # ---- network flows (firewall / proxy / netflow)
        src, dst, dport = ev.get("src_ip"), ev.get("dst_ip"), ev.get("dst_port")
        action = str(ev.get("action") or "").lower()
        if action in ("config_change",) or (st in ("firewall", "vpn", "generic", "linux") and
                                            RX["TG-NET-006"].search(ev.get("text", "")[:600])):
            f = self.hit("TG-NET-006", (ev.get("host") or ev.get("dst_ip") or "").lower(), ev)
            if f and src and self.inv:
                c = self.cls(src, ts)
                if c and c.get("trust_class") != "management_host":
                    f.severity = "high"
                    note = f"Change made from {src} ({c['label']}), not from an approved management/jump host."
                    if note not in f.notes:
                        f.notes.append(note)
        if src and dst and dport is not None and st in ("firewall", "proxy", "generic", "ids") and action != "alert":
            self.has["network"] += 1
            denied = action in ("deny", "drop", "reject", "block", "denied", "blocked")
            sc = self.scan[src][dst]
            if len(sc) < 5000:
                sc.add(dport)
            self.scan_ev.setdefault((src, dst), ev)
            if denied:
                self.scan_denied[(src, dst)] += 1
            elif action and len(self.scan_open[(src, dst)]) < 10 and dport not in self.scan_open[(src, dst)]:
                self.scan_open[(src, dst)][dport] = self._lite(ev)
            if denied:
                k = (src, dst, dport)
                self.deny_n[k] += 1
                if len(self.denies[k]) < 20:
                    self.denies[k].append(self._lite(ev))
            elif ts and self.external(dst, ts):
                b = self.beacons.get((src, dst, dport))
                if b is None:
                    b = self.beacons[(src, dst, dport)] = [array("d"), [], []]
                if len(b[0]) < 5000:
                    b[0].append(ts.timestamp())
                    if len(b[1]) < 5:
                        b[1].append(self._lite(ev))
                    if len(b[2]) < REFS:
                        b[2].append(ev.get("ref"))
            if not denied and ev.get("bytes_out"):
                bb = self.bytes[(src, dst)]
                bb[0] += int(ev["bytes_out"])
                if bb[1] is None or int(ev["bytes_out"]) > bb[1].get("bytes_out", 0):
                    bb[1] = self._lite(ev)
            if ts:
                minute = ts.replace(second=0, microsecond=0)
                pm = self.per_min.get(dst)
                if pm is None:
                    self.per_min[dst] = [minute, 1, 0, None]
                elif pm[0] == minute:
                    pm[1] += 1
                else:
                    if pm[1] > pm[2]:
                        pm[2], pm[3] = pm[1], pm[0]
                    pm[0], pm[1] = minute, 1
            if self.inv and not denied:
                self._segment(ev, src, dst, dport, ts)
        # ---- DNS
        if ev.get("domain") and (st == "dns" or ev.get("query_type") or ev.get("rcode")):
            self.has["dns"] += 1
            client = src or "unknown"
            name = str(ev["domain"]).lower().rstrip(".")
            labels = name.split(".")
            bd = base_domain(name)
            d = self.dns[(client, bd)]
            d["n"] += 1
            if max(len(x) for x in labels) >= self.rules["TG-DNS-001"]["threshold"]["long_label"] or \
                    (len(labels[0]) >= 25 and entropy(labels[0]) > 3.8):
                d["long"] += 1
                if len(d["evs"]) < 5:
                    d["evs"].append(self._lite(ev))
            if str(ev.get("query_type", "")).upper() == "TXT":
                d["txt"] += 1
            if "NXDOMAIN" in str(ev.get("rcode", "")).upper() and ts:
                if len(self.nx[client]) < 5000:
                    self.nx[client].append((ts, name, self._lite(ev)))
        # ---- web / API
        if ev.get("url") and src and st in ("web", "proxy", "generic"):
            self.has["web"] += 1
            w = self.web[src]
            w["n"] += 1
            path = str(ev["url"]).split("?")[0][:200]
            if len(w["paths"]) < 5000:
                w["paths"].add(path)
            if str(ev.get("status", "")).startswith(("401", "403", "404")) and len(w["err_paths"]) < 5000:
                w["err_paths"].add(path)
            if ts and len(w["times"]) < 20000 and "/api" in path.lower():
                w["times"].append(ts)
            if len(w["evs"]) < 5:
                w["evs"].append(self._lite(ev))
        # ---- IDS / EDR alerts
        if st in ("ids", "edr") and ev.get("signature"):
            self.has["ids"] += 1
            sig = str(ev["signature"])[:160]
            sev = self._sensor_severity(ev.get("severity"))
            f = self.hit("TG-IDS-001", sig, ev, f"{'EDR' if st == 'edr' else 'IDS'} alert: {sig}")
            if f and SEV_RANK.get(sev, 9) < SEV_RANK.get(f.severity, 9):
                f.severity = sev
        # ---- threat intelligence + configured suspicious indicators
        self._ti(ev, ts)

    def _lite(self, ev):
        """Small copy of an event kept for later rules. The raw record is NOT kept: the pipeline's
        evidence pass re-reads exact records by reference, so memory stays bounded on huge files."""
        return {k: ev[k] for k in ("ts", "ref", "user", "host", "src_ip", "dst_ip", "dst_port", "assigned_ip",
                                   "event_id", "logon_type", "process", "command", "domain", "bytes_out",
                                   "source_type", "line") if ev.get(k) not in (None, "")}

    def _auth_outcome(self, ev, eid):
        if not eid and not ev.get("user") and ev.get("source_type") in ("firewall", "dns", "ids", "proxy"):
            return None  # pure flow / DNS / sensor records carry no authentication outcome
        if eid in ("4624", "4648"):
            return "success"
        if eid in ("4625", "4771", "4776") and ("fail" in ev.get("text", "").lower() or eid == "4625"):
            return "failure"
        t = (str(ev.get("outcome", "")) + " " + str(ev.get("action", ""))).lower()
        raw = ev.get("text", "")[:300].lower()
        if not ev.get("user") and not ev.get("src_ip"):
            return None
        if "auth_failure" in raw or "login failed" in raw or "authentication failure" in raw or \
                re.search(r"\b(failure|failed|fail|denied|rejected|invalid)\b", t):
            return "failure" if (ev.get("user") or "logon" in t or "auth" in raw or "login" in raw) else None
        if "auth_success" in raw or "login succeeded" in raw or "logged in" in raw or \
                (re.search(r"\b(success|succeeded|accepted)\b", t) and ("logon" in t or "auth" in raw or "login" in raw)):
            return "success"
        return None

    @staticmethod
    def _sensor_severity(v):
        try:
            n = float(v)
        except (TypeError, ValueError):
            s = str(v or "").lower()
            return next((x for x in ("critical", "high", "medium", "low") if x in s), "medium")
        n = n * 10 if n <= 1 else n
        return "critical" if n >= 9 else "high" if n >= 7 else "medium" if n >= 4 else "low"

    def _segment(self, ev, src, dst, dport, ts):
        cs, cd = self.cls(src, ts), self.cls(dst, ts)
        if not cs or not cd:
            return
        if dport in ADMIN_PORTS and cs.get("asset_type") == "workstation" and cd.get("asset_type") == "workstation":
            self.hit("TG-NET-004", f"{src}>{dst}", ev, f"Workstation-to-workstation admin traffic ({src} -> {dst}:{dport})")
        elif dport in ADMIN_PORTS and cd.get("zone") == "management" and cs.get("trust_class") != "management_host":
            self.hit("TG-NET-004", f"{src}>mgmt", ev, f"Admin protocol into the management zone from {src}")
        allowed = (cd.get("entry") or {}).get("allowed_services")
        if allowed and cd.get("trust_class") == "public_server" and dport not in allowed and self.external(src, ts):
            self.hit("TG-NET-005", f"{dst}:{dport}", ev,
                     f"Public server {cd['entry'].get('name')} accepted port {dport} (approved: {allowed})")

    def _ti(self, ev, ts):
        cands = []
        for f in ("src_ip", "dst_ip", "assigned_ip"):
            if ev.get(f):
                cands.append(("ip", str(ev[f]).lower()))
        if ev.get("domain"):
            name = str(ev["domain"]).lower().rstrip(".")
            parts = name.split(".")
            cands += [("domain", ".".join(parts[i:])) for i in range(len(parts) - 1)]
        if ev.get("url"):
            cands.append(("url", str(ev["url"]).lower()))
            m = re.match(r"\w+://([^/:]+)", str(ev["url"]))
            if m:
                cands.append(("domain", m.group(1).lower()))
        if ev.get("hash"):
            cands += [("hash", h.lower()) for h in HEX_RE.findall(str(ev["hash"]))]
        elif self.iocs["hash"] and ev.get("command"):
            cands += [("hash", h.lower()) for h in HEX_RE.findall(str(ev["command"]))]
        for typ, v in cands:
            hit = self.iocs[typ].get(v)
            if hit:
                f = self.hit("TG-TI-001", f"{typ}:{v}", ev, f"Threat-intel match: {hit['value']} ({hit['source']})")
                if f:
                    f.details.update(indicator=hit["value"], type=typ, feed=hit["source"],
                                     description=hit["description"])
                    self.ti_hits[v] = hit
        if self.inv:
            for f in ("src_ip", "dst_ip"):
                if ev.get(f):
                    c = self.cls(ev[f], ts)
                    if c and c["category"] == "suspicious_indicator":
                        h = self.hit("TG-TI-002", ev[f], ev, f"Configured suspicious indicator observed: {ev[f]}")
                        if h:
                            h.details.update(indicator=ev[f], reason=(c.get("entry") or {}).get("name"))

    def _forensics(self, ev, ts):
        if ts is None:
            return
        fo = self.forensic[ev.get("file")]
        fo["n"] += 1
        fo["first"] = min(fo["first"] or ts, ts)
        fo["last"] = max(fo["last"] or ts, ts)
        if ts > self.now + timedelta(days=1) and len(fo["future"]) < 20:
            fo["future"].append(self._lite(ev))
        p = fo["prev"]
        if p is not None:
            delta = (ts - p[0]).total_seconds()
            if delta < -self.rules["TG-FOR-004"]["threshold"]["backwards_s"] and len(fo["backwards"]) < 20:
                fo["backwards"].append(self._lite(ev))
            elif delta >= 0:
                if len(fo["intervals"]) < 20000:
                    fo["intervals"].append(delta)
                if delta >= self.rules["TG-FOR-003"]["threshold"]["min_gap_min"] * 60 and len(fo["gaps"]) < 200:
                    fo["gaps"].append((p[0], ts, delta, p[1], ev.get("ref")))
        fo["prev"] = (ts, ev.get("ref"))

    # ------------------------------------------------------------ finish
    def finish(self, baselines=None):
        self._auth_rules()
        self._network_rules()
        self._dns_rules()
        self._web_rules()
        ueba = self._ueba(baselines or {})
        stats = self._statistics()
        forensics = self._forensic_rules()
        findings = [f.to_dict() for f in self.found.values()]
        for f in findings:
            for k, v in list(f["details"].items()):
                if isinstance(v, datetime):
                    f["details"][k] = _fmt(v)
        return {"findings": findings, "ueba": ueba, "statistics": stats, "forensics": forensics,
                "vpn_assign": {k: list(v) for k, v in self.vpn_assign.items()},
                "host_ips": {h: sorted(ips) for h, ips in self.host_ips.items()},
                "telemetry": dict(self.has), "ti_matches": list(self.ti_hits.values())}

    def _auth_rules(self):
        auth = sorted((a for a in self.auth if a[0]), key=lambda a: a[0])
        by_src = defaultdict(list)
        for a in auth:
            if a[2]:
                by_src[a[2]].append(a)
        R = self.rules
        for src, items in by_src.items():
            fails = [a for a in items if a[4] == "failure"]
            if not fails:
                continue
            # password spraying: many users, few tries each, inside the window
            th = R["TG-AUTH-002"]["threshold"]
            win = timedelta(minutes=th["window_min"])
            j = 0
            for i in range(len(fails)):
                while fails[i][0] - fails[j][0] > win:
                    j += 1
                window = fails[j:i + 1]
                users = Counter(a[1] for a in window if a[1])
                if len(users) >= th["distinct_users"] and max(users.values()) <= th["max_per_user"] * 2 and \
                        sum(users.values()) / len(users) <= th["max_per_user"]:
                    if ("TG-AUTH-002", src) not in self.found:
                        for a in window:
                            self.hit("TG-AUTH-002", src, a[9], f"Password spraying from {src} ({len(users)} accounts)")
                        self._f("TG-AUTH-002", src).details.update(distinct_users=len(users),
                                                                         attempts=len(window), src=src)
                    break
            # brute force (sources the regex detector doesn't cover)
            th = R["TG-AUTH-001"]["threshold"]
            nonstd = [a for a in fails if a[6] not in ("windows", "linux_auth")]
            if len(nonstd) >= th["failures"] and ("TG-AUTH-002", src) not in self.found:
                users = Counter(a[1] for a in nonstd)
                for a in nonstd[:REFS]:
                    self.hit("TG-AUTH-001", src, a[9], f"Brute force from {src} against {', '.join(list(users)[:3])}")
            # enumeration: many invalid user names
            invalid = {a[1] for a in fails if a[1] and re.search(r"invalid user|unknown user|0xc0000064|no such user",
                                                                   (a[9].get("raw") or "").lower())}
            if len(invalid) >= R["TG-AUTH-003"]["threshold"]["distinct_invalid_users"]:
                for a in fails:
                    if a[1] in invalid:
                        self.hit("TG-AUTH-003", src, a[9], f"Account enumeration from {src} ({len(invalid)} unknown users)")
            # success after failures
            th = R["TG-AUTH-004"]["threshold"]
            for a in items:
                if a[4] != "success":
                    continue
                prior = [f for f in fails if timedelta(0) <= a[0] - f[0] <= timedelta(minutes=th["window_min"])]
                if len(prior) >= th["failures_before"]:
                    f = self.hit("TG-AUTH-004", src, a[9], f"Logon succeeded for '{a[1]}' from {src} after "
                                                           f"{len(prior)} failures")
                    for p in prior[-5:]:
                        f.add(p[9])
                    f.details.update(account=a[1], failures_before=len(prior), src=src)
        # lateral movement and RDP / service accounts / VPN use
        th = R["TG-LAT-001"]["threshold"]
        by_user = defaultdict(list)
        for a in auth:
            if a[4] == "success" and a[1]:
                by_user[a[1]].append(a)
        for user, items in by_user.items():
            net = [a for a in items if str(a[5]) in ("3", "10") and a[3]]
            j = 0
            for i in range(len(net)):
                while net[i][0] - net[j][0] > timedelta(minutes=th["window_min"]):
                    j += 1
                hosts = {a[3] for a in net[j:i + 1]}
                if len(hosts) >= th["distinct_hosts"]:
                    key = user
                    if ("TG-LAT-001", key) not in self.found:
                        for a in net[j:i + 1]:
                            self.hit("TG-LAT-001", key, a[9], f"Lateral movement: '{user}' logged on to "
                                                              f"{len(hosts)} hosts in {th['window_min']} min")
                        self._f("TG-LAT-001", key).details.update(hosts=sorted(hosts))
                    break
            for a in items:
                lt = str(a[5])
                if lt == "10" and a[2]:
                    c = self.cls(a[2], a[0])
                    approved = c and c.get("trust_class") == "management_host"
                    if not approved:
                        f = self.hit("TG-AUTH-006", f"{user}@{a[3]}", a[9],
                                     f"RDP logon by '{user}' on {a[3] or 'host'} from {a[2]}")
                        if f and c and c["category"] != "public_unknown":
                            note = f"Source {a[2]} is {c['label']}" + (f" ({c['entry']['name']})" if c.get("entry") else "") + \
                                   " - internal context, still not an approved management host."
                            if note not in f.notes:
                                f.notes.append(note)
                sa = self.inv.service_account(user) if self.inv else None
                looks_svc = re.match(r"(svc|srv|service)[_\-.]", user) is not None
                if (sa or looks_svc) and lt in ("2", "10", "11"):
                    allowed = sa and sa.get("interactive_allowed")
                    if not allowed:
                        f = self.hit("TG-AUTH-007", user, a[9], f"Service account '{user}' used interactively "
                                                                f"(logon type {lt}) on {a[3] or 'host'}")
                        if f and not sa:
                            f.notes.append("Identified by naming convention only; add it under Approved service "
                                           "accounts to confirm policy.")
        th = R["TG-VPN-001"]["threshold"]
        for user, items in by_user.items():
            vpn = [a for a in items if a[6] == "vpn" and a[2] and self.external(a[2], a[0])]
            for i, a in enumerate(vpn):
                near = {b[2] for b in vpn if abs((b[0] - a[0]).total_seconds()) <= th["window_min"] * 60}
                if len(near) >= 2:
                    for b in vpn:
                        if b[2] in near:
                            self.hit("TG-VPN-001", user, b[9], f"VPN account '{user}' used from {len(near)} public IPs")
                    break

    def _network_rules(self):
        R = self.rules
        th = R["TG-NET-001"]["threshold"]
        for src, dsts in self.scan.items():
            for dst, ports in dsts.items():
                if len(ports) >= th["distinct_ports"]:
                    ev = self.scan_ev[(src, dst)]
                    f = self.hit("TG-NET-001", f"{src}>{dst}", ev, f"Port scan: {src} probed {len(ports)} ports on {dst}",
                                 text=f"{src} -> {dst}: {len(ports)} distinct ports e.g. {sorted(ports)[:12]}")
                    for lite in self.scan_open.get((src, dst), {}).values():  # ports that got through
                        self.hit("TG-NET-001", f"{src}>{dst}", lite, f"Port scan: {src} probed {len(ports)} ports on {dst}")
                    f.count = len(ports)
                    f.details.update(distinct_ports=len(ports), sample_ports=sorted(ports)[:30], src=src, target=dst,
                                     ports_allowed=sorted(self.scan_open.get((src, dst), {}))[:10],
                                     connections_denied=self.scan_denied.get((src, dst), 0))
                    c = self.cls(src, ev.get("ts"))
                    if c and c.get("trust_class") == "monitoring_scanner":
                        f.notes.append(f"Source is an approved scanner ({c['entry']['name']}). Severity is unchanged; "
                                       "verify the scan matched its approved schedule and scope.")
                        f.details["approved_scanner"] = True
        th = R["TG-NET-002"]["threshold"]
        for k, n in self.deny_n.items():
            if n >= th["denies"]:
                for ev in self.denies[k]:
                    self.hit("TG-NET-002", f"{k[0]}>{k[1]}:{k[2]}", ev,
                             f"{n} denied connections {k[0]} -> {k[1]}:{k[2]}")
                self._f("TG-NET-002", f"{k[0]}>{k[1]}:{k[2]}").count = n
        th = R["TG-C2-001"]["threshold"]
        for (src, dst, port), (times, lites, refs) in self.beacons.items():
            if len(times) < th["min_connections"]:
                continue
            t = sorted(times)
            iv = [t[i + 1] - t[i] for i in range(len(t) - 1)]
            iv = [x for x in iv if x > 0]
            if len(iv) < th["min_connections"] - 1:
                continue
            med = statistics.median(iv)
            jitter = statistics.pstdev(iv) / statistics.mean(iv) if statistics.mean(iv) else 9
            if th["min_interval_s"] <= med <= th["max_interval_s"] and jitter <= th["max_jitter"]:
                key = f"{src}>{dst}:{port}"
                for lite in lites:
                    self.hit("TG-C2-001", key, lite, f"Beaconing: {src} -> {dst}:{port} every ~{int(med)} s")
                f = self._f("TG-C2-001", key)
                f.count = len(t)
                f.refs += [r for r in refs[len(lites):] if r]
                f.first, f.last = _utc(t[0]), _utc(t[-1])
                f.details.update(connections=len(t), median_interval_s=round(med, 1), jitter=round(jitter, 3))
        th = R["TG-EXF-001"]["threshold"]
        vols = [v[0] for v in self.bytes.values() if v[0] > 0]
        med = statistics.median(vols) if vols else 0
        for (src, dst), (total, lite) in self.bytes.items():
            ext = self.external(dst, lite.get("ts") if lite else None)
            if ext and (total >= th["bytes_out"] or (med and total >= med * th["outlier_factor"] and total >= 100_000_000)):
                f = self.hit("TG-EXF-001", f"{src}>{dst}", lite, f"Large outbound transfer: {src} -> {dst} "
                                                                f"({total / 1e9:.2f} GB)")
                f.details.update(bytes_out=total, median_flow_bytes=med)
                c = self.cls(dst)
                if c and c["category"] == "known_external_service":
                    f.notes.append(f"Destination is an approved external service ({c['entry']['name']}); "
                                   "verify the transfer was expected.")
        th = R["TG-NET-003"]["threshold"]
        for dst, (minute_now, count_now, peak, peak_minute) in self.per_min.items():
            n, minute = (count_now, minute_now) if count_now > peak else (peak, peak_minute)
            if n >= th["per_minute"]:
                f = self.hit("TG-NET-003", dst, {"ts": minute, "dst_ip": dst, "ref": f"{n} connections in {minute:%H:%M}"},
                             f"Possible DoS: {n} connections/min to {dst}")
                f.details["peak_per_minute"] = max(f.details.get("peak_per_minute", 0), n)

    def _dns_rules(self):
        R = self.rules
        th = R["TG-DNS-001"]["threshold"]
        for (client, bd), d in self.dns.items():
            if d["long"] >= th["min_queries"] or (d["txt"] >= th["min_queries"] and d["long"] >= 5):
                for lite in d["evs"]:
                    self.hit("TG-DNS-001", f"{client}>{bd}", lite, f"DNS tunnelling indicators: {client} -> *.{bd}")
                f = self._f("TG-DNS-001", f"{client}>{bd}")
                f.count = d["long"]
                f.details.update(queries=d["n"], long_queries=d["long"], txt_queries=d["txt"], domain=bd)
        th = R["TG-DNS-002"]["threshold"]
        for client, items in self.nx.items():
            items.sort(key=lambda x: x[0])
            j = 0
            for i in range(len(items)):
                while items[i][0] - items[j][0] > timedelta(minutes=th["window_min"]):
                    j += 1
                win = items[j:i + 1]
                random_like = [x for x in win if entropy(x[1].split(".")[0]) >= 3.2]
                if len(win) >= th["nxdomain"] and len(random_like) >= len(win) * 0.6:
                    for x in win[:REFS]:
                        self.hit("TG-DNS-002", client, x[2], f"NXDOMAIN burst / DGA-like lookups from {client}")
                    self._f("TG-DNS-002", client).details["nxdomain"] = len(win)
                    break

    def _web_rules(self):
        th = self.rules["TG-API-001"]["threshold"]
        for src, w in self.web.items():
            burst = 0
            t = sorted(w["times"])
            j = 0
            for i in range(len(t)):
                while t[i] - t[j] > timedelta(minutes=th["window_min"]):
                    j += 1
                burst = max(burst, i - j + 1)
            if burst >= th["requests"] or len(w["err_paths"]) >= th["distinct_paths"]:
                for lite in w["evs"]:
                    self.hit("TG-API-001", src, lite, f"API abuse / enumeration from {src}")
                self._f("TG-API-001", src).details.update(peak_requests=burst, error_paths=len(w["err_paths"]),
                                                              distinct_paths=len(w["paths"]))

    # ------------------------------------------------------------ UEBA
    def _ueba(self, baselines):
        """Per-user behaviour vs. the user's own history (persisted + earlier in this dataset) and peers."""
        auth = sorted((a for a in self.auth if a[0] and a[1]), key=lambda a: a[0])
        hist = {}
        users = {}
        fails_by_user = defaultdict(list)
        for a in auth:
            if a[4] == "failure":
                fails_by_user[a[1]].append(a[0])
        priv_users_hist = {u for u, b in baselines.items() if b.get("privileged")}
        data_start = auth[0][0] if auth else None
        for a in auth:
            ts, user, src, host, outcome, lt, st, ref, eid, lite = a
            if outcome != "success":
                continue
            b = hist.get(user)
            if b is None:
                pb = baselines.get(user, {})
                b = hist[user] = {"n": pb.get("logons", 0), "hours": Counter({int(k): v for k, v in (pb.get("hours") or {}).items()}),
                                  "ips": set(pb.get("ips") or []), "hosts": set(pb.get("hosts") or []),
                                  "first": pb.get("first_seen"), "days": set()}
            u = users.get(user)
            if u is None:
                u = users[user] = {"entity": user, "type": "user", "reasons": [], "score": 0, "events": 0,
                                   "hosts": set(), "ips": set(), "first": ts, "last": ts}
                if b["n"] == 0 and data_start and ts - data_start >= timedelta(days=2):
                    self._reason(u, "new_entity", 15, f"Account first seen {ts:%Y-%m-%d %H:%M} although the logs start "
                                 f"{data_start:%Y-%m-%d} - no baseline exists for it", ref)
            u["events"] += 1
            u["hosts"].add(host)
            if src:
                u["ips"].add(src)
            u["last"] = ts
            enough = b["n"] >= 10 and len(b["days"]) >= 3
            if enough:
                near = sum(v for h, v in b["hours"].items() if min(abs(h - ts.hour), 24 - abs(h - ts.hour)) <= 1)
                if near / b["n"] < 0.05:
                    lo, hi = _usual_hours(b["hours"])
                    self._reason(u, "unusual_hour", 30, f"Logon at {ts:%H:%M} UTC; 80% of this account's "
                                 f"{b['n']} earlier logons were between {lo:02d}:00 and {hi:02d}:59", ref)
                if src and src not in b["ips"]:
                    c = self.cls(src, ts)
                    w, ctx = 25, ""
                    if c and c["category"] in ("configured_internal", "approved_asset"):
                        w, ctx = 12, f" - inside {c.get('entry', {}).get('name') or c['label']}, so weighted lower"
                    elif c and c["category"] == "public_unknown" or (not c and self.external(src)):
                        w = 35
                    self._reason(u, "new_source", w, f"First logon from {src} (known sources: "
                                 f"{', '.join(sorted(b['ips'])[:4]) or 'none'}){ctx}", ref)
                if host and host not in b["hosts"]:
                    asset = self.inv.host_asset(host) if self.inv else None
                    crit = asset and asset.get("criticality") in ("critical", "high")
                    self._reason(u, "new_host", 25 if crit else 12,
                                 f"First access to {host}" + (f" ({asset.get('name')}, criticality "
                                                               f"{asset.get('criticality')})" if crit else ""), ref)
            prior_fail = [t for t in fails_by_user.get(user, []) if timedelta(0) < ts - t <= timedelta(hours=1)]
            if len(prior_fail) >= 3:
                self._reason(u, "fail_then_success", 25, f"{len(prior_fail)} failed logons in the hour before this "
                             f"successful logon", ref)
            # learn (online) - the event becomes part of the history for later events
            b["n"] += 1
            b["hours"][ts.hour] += 1
            if src:
                b["ips"].add(src)
            if host:
                b["hosts"].add(host)
            b["days"].add(ts.date())
        for user, evs in self.priv.items():
            u = users.get(user)
            if u is None:
                continue
            b = hist.get(user, {})
            if user not in priv_users_hist and b.get("n", 0) >= 3:
                first_priv = min((e for e in evs if e[0]), key=lambda e: e[0], default=None)
                if first_priv:
                    self._reason(u, "new_privilege", 20, "Privileged activity (special privileges / sudo) with no "
                                 "history of it in the baseline", first_priv[1])
        for (rid, key), f in self.found.items():
            if rid == "TG-LAT-001" and key in users:
                self._reason(users[key], "lateral", 35, f"Logged on to {len(f.details.get('hosts', []))} hosts within "
                             f"{self.rules['TG-LAT-001']['threshold']['window_min']} minutes", f.refs[0] if f.refs else None)
            if rid == "TG-AUTH-007" and key in users:
                self._reason(users[key], "service_interactive", 40, "Service account used interactively", f.refs[0] if f.refs else None)
        # peer group: distinct hosts accessed compared with other users
        counts = {u: len(v["hosts"]) for u, v in users.items()}
        if len(counts) >= 4:
            med = statistics.median(counts.values()) or 1
            for user, n in counts.items():
                if n >= 4 and n >= 3 * med:
                    self._reason(users[user], "peer_deviation", 20, f"Accessed {n} hosts; peer median is {med:g}", None)
        out = []
        for user, u in users.items():
            b = hist.get(user, {})
            u["score"] = min(100, sum(r["weight"] for r in u["reasons"]))
            u["baseline"] = {"logons": b.get("n", 0), "history_days": len(b.get("days", ())) or 0,
                             "usual_hours": sorted(h for h, v in b.get("hours", {}).items() if v)[:24],
                             "known_sources": len(b.get("ips", ())), "known_hosts": len(b.get("hosts", ()))}
            u["insufficient_history"] = u["baseline"]["logons"] < 10 or u["baseline"]["history_days"] < 3
            u["hosts"], u["ips"] = sorted(u["hosts"])[:20], sorted(u["ips"])[:20]
            u["first"], u["last"] = _fmt(u["first"]), _fmt(u["last"])
            out.append(u)
            th = self.rules["TG-UEBA-001"]["threshold"]["score"]
            if u["score"] >= th and self.rule("TG-UEBA-001"):
                f = self.found[("TG-UEBA-001", user)] = EF(self.rules["TG-UEBA-001"],
                                                         f"Anomalous behaviour for '{user}' (UEBA score {u['score']})", user)
                f.severity = "high" if u["score"] >= 70 else "medium"
                for r in u["reasons"]:
                    f.add({"ref": r["ref"], "user": user, "ts": None}, text=r["text"])
                f.users[user] += 1
                f.details.update(ueba_score=u["score"], reasons=[r["text"] for r in u["reasons"]])
        hist_out = {u: {"logons": b["n"], "hours": {str(h): v for h, v in b["hours"].items()},
                        "ips": sorted(b["ips"])[:50], "hosts": sorted(b["hosts"])[:100],
                        "first_seen": b["first"] or _fmt(min((a[0] for a in auth if a[1] == u), default=None)),
                        "privileged": u in priv_users_hist} for u, b in hist.items()}
        out.sort(key=lambda x: -x["score"])
        return {"entities": out, "history": hist_out}

    @staticmethod
    def _reason(u, kind, weight, text, ref):
        """Keep the strongest occurrence of each kind of anomaly (latest wins on ties)."""
        for r in u["reasons"]:
            if r["kind"] == kind:
                if weight >= r["weight"]:
                    r.update(weight=weight, text=text, ref=ref)
                return
        u["reasons"].append({"kind": kind, "weight": weight, "text": text, "ref": ref})

    # ------------------------------------------------------------ statistics & forensics
    def _statistics(self):
        th = self.rules["TG-STAT-001"]["threshold"]
        spikes = []
        for file, buckets in self.vol.items():
            keys = sorted(buckets)
            vals = [buckets[k] for k in keys]
            for k, v, z in zip(keys, vals, robust_z(vals)):
                if z >= th["robust_z"] and v >= th["min_events"]:
                    spikes.append({"file": file, "bucket": _fmt(k), "events": v, "robust_z": round(z, 1)})
        for s in spikes[:20]:
            f = self.hit("TG-STAT-001", s["file"], {"ts": datetime.strptime(s["bucket"], "%Y-%m-%d %H:%M:%S"),
                                                    "ref": f"{s['file']} @ {s['bucket']}"},
                         f"Unusual event volume in {s['file']}", text=f"{s['events']} events in 5 min "
                         f"(robust z={s['robust_z']}) at {s['bucket']}")
        talkers = Counter()
        for (src, dst), (total, _) in self.bytes.items():
            talkers[src] += total
        return {"volume_spikes": spikes[:50], "top_talkers_bytes": talkers.most_common(10),
                "events": self.events}

    def _forensic_rules(self):
        out = []
        th = self.rules["TG-FOR-003"]["threshold"]
        for file, fo in self.forensic.items():
            iv = fo["intervals"]
            med = statistics.median(iv) if len(iv) >= 50 else None
            buckets = self.vol.get(file) or {}
            span = ((fo["last"] - fo["first"]).total_seconds() / 300 + 1) if fo["first"] else 1
            continuous = len(buckets) / span >= 0.8  # events in >=80% of 5-minute buckets
            entry = {"file": file, "events": fo["n"], "first": _fmt(fo["first"]), "last": _fmt(fo["last"]),
                     "out_of_order": len(fo["backwards"]), "future": len(fo["future"]), "gaps": []}
            entry["continuous"] = continuous
            if med is not None and continuous:  # gap detection only for continuously logging sources
                limit = max(th["min_gap_min"] * 60, th["gap_factor"] * max(med, 1))
                for start, end, delta, r1, r2 in fo["gaps"]:
                    if delta >= limit:
                        entry["gaps"].append({"from": _fmt(start), "to": _fmt(end), "minutes": round(delta / 60),
                                              "refs": [r1, r2]})
                        self.hit("TG-FOR-003", file, {"ts": start, "ref": r1}, f"Log collection gap in {file}",
                                 text=f"No events from {_fmt(start)} to {_fmt(end)} ({round(delta / 60)} min; "
                                      f"normal interval {med:.0f}s)")
            for lite in fo["backwards"][:5]:
                self.hit("TG-FOR-004", file, lite, f"Out-of-order timestamps in {file}")
            for lite in fo["future"][:5]:
                self.hit("TG-FOR-004", file, lite, f"Future timestamps in {file}")
            out.append(entry)
        return out


SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
