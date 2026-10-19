"""SIEM export parsers -> one normalised event model.

Supported: CSV/TSV (any SIEM export), JSON array/object, JSON Lines, Windows Event Viewer
CSV and XML exports, syslog (RFC 3164/5424), CEF, LEEF, key=value firewall/VPN/proxy logs,
Apache/Nginx access logs and plain text. `.gz` files are read transparently.

Everything is streamed: events are yielded one at a time, so a multi-GB export never has
to fit in memory. Vendor field names are mapped through an alias table which can be
extended without code changes in config/field_mappings.json.

Normalised event (keys only present when known):
  ts (datetime, UTC naive), ts_raw, src_ip, dst_ip, src_port, dst_port, protocol, user,
  target_user, host, src_host, event_id, action, outcome, process, parent_process, command,
  url, method, status, domain, query_type, rcode, bytes_out, bytes_in, logon_type, signature,
  severity, hash, file_path, service, group, user_agent, session_id, pid, message,
  source_type, file, line, ref ("file:line" evidence reference), raw (original record),
  text (searchable text used by signature rules)
"""
import csv
import gzip
import io
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config_store

csv.field_size_limit(16 * 1024 * 1024)
RAW_KEEP = 2000           # characters of the original record kept as evidence
SNIFF_BYTES = 64 * 1024

# canonical field -> aliases (compared after lower-casing and removing non-alphanumerics)
DEFAULT_ALIASES = {
    "ts": ["timestamp", "time", "datetime", "date", "eventtime", "@timestamp", "timegenerated", "timecreated",
           "systemtime", "_time", "devicetime", "logtime", "createdat", "eventtimestamp", "dateandtime",
           "starttime", "receivedtime", "rt", "start", "generatedtime", "ts"],
    "src_ip": ["srcip", "sourceip", "src", "sourceaddress", "srcaddr", "clientip", "cip", "callingstationid",
               "ipaddress", "sourcenetworkaddress", "remoteip", "remoteaddr", "remoteaddress", "srcipaddr",
               "clientaddress", "sourceipaddress", "sourceip4", "idorigh", "networksourceip", "ipsrc", "sip",
               "externalip", "publicip", "clientipaddress", "csip"],
    "dst_ip": ["dstip", "destip", "destinationip", "dst", "destinationaddress", "dstaddr", "serverip", "sip2",
               "destinationipaddress", "targetip", "idresph", "networkdestinationip", "ipdst", "dip", "localip",
               "serveraddress", "csip2", "destinationnetworkaddress"],
    "src_port": ["srcport", "sourceport", "spt", "sport", "clientport", "idorigp", "ipport", "sourceportnumber"],
    "dst_port": ["dstport", "destport", "destinationport", "dpt", "dport", "serverport", "port", "idrespp",
                 "targetport", "destinationportnumber", "service_port"],
    "protocol": ["protocol", "proto", "transport", "ipprotocol", "networkprotocol", "app", "application"],
    "user": ["user", "username", "usr", "suser", "targetusername", "accountname", "account", "userid", "login",
             "subjectusername", "uid", "principal", "userprincipalname", "loginname", "logonuser", "srcuser",
             "useridentity", "csusername", "identity", "actor"],
    "target_user": ["duser", "targetuser", "membername", "newusername", "samaccountname", "targetaccount",
                    "destinationuser"],
    "host": ["host", "hostname", "computer", "computername", "devicename", "dvchost", "dvc", "machine",
             "agenthostname", "hostnamename", "observerhostname", "sourcehost", "reportinghost", "server",
             "workstation", "endpoint", "assetname", "dhost"],
    "src_host": ["workstationname", "shost", "clienthostname", "sourcehostname", "srchost", "callingstation"],
    "event_id": ["eventid", "eventcode", "id", "eventtype", "signatureid", "sid", "ruleid", "winlogeventid",
                 "eventidentifier", "logid", "messageid", "eventname"],
    "action": ["action", "act", "disposition", "eventoutcome", "verdict", "decision", "policyaction", "result",
               "status_action", "fwaction", "deviceaction"],
    "outcome": ["outcome", "success", "auditresult", "keywords", "loginresult", "authresult", "level", "status2"],
    "process": ["process", "processname", "newprocessname", "image", "exe", "executable", "processpath",
                "filename", "program", "appname", "procname", "imagepath"],
    "parent_process": ["parentprocess", "parentprocessname", "parentimage", "parentexe", "creatorprocessname"],
    "command": ["commandline", "cmdline", "command", "cmd", "processcommandline", "scriptblocktext", "args",
                "arguments", "query"],
    "url": ["url", "uri", "request", "requesturl", "csuri", "csuristem", "path", "requestpath", "fullurl",
            "httpurl", "request_uri", "dest_url"],
    "method": ["method", "httpmethod", "requestmethod", "csmethod", "verb"],
    "status": ["status", "statuscode", "httpstatus", "responsecode", "scstatus", "response"],
    "domain": ["domain", "queryname", "qname", "dnsquestionname", "questionname", "dnsqueryname", "dnsquery", "fqdn", "hostheader", "cshost", "requestdomain",
               "destinationhostname", "dnsname", "dhostname", "sni", "servername"],
    "query_type": ["qtype", "querytype", "qtypename", "recordtype", "dnsrecordtype", "dnsquestiontype", "questiontype"],
    "assigned_ip": ["assignedip", "framedip", "framedipaddress", "clientvirtualip", "tunnelip", "virtualip",
                    "internalip", "vpnip", "assignedaddress", "privateip"],
    "rcode": ["rcode", "rcodename", "responsecodename", "dnsresponsecode", "replycode"],
    "bytes_out": ["bytesout", "sentbytes", "bytessent", "out", "csbytes", "origbytes", "txbytes", "sbytes",
                  "uploadbytes", "srcbytes", "bytes_sent", "outbytes"],
    "bytes_in": ["bytesin", "receivedbytes", "bytesreceived", "in", "scbytes", "respbytes", "rxbytes", "rbytes",
                 "downloadbytes", "dstbytes", "bytes", "inbytes", "size"],
    "logon_type": ["logontype", "logon_type", "authtype"],
    "signature": ["signature", "alert", "alertname", "rule", "rulename", "signaturename", "threatname",
                  "detectionname", "msg", "attackname", "category", "classification"],
    "severity": ["severity", "priority", "risk", "riskscore", "sev", "threatlevel", "alertseverity", "pri"],
    "hash": ["hash", "sha256", "sha1", "md5", "filehash", "filesha256", "hashes", "imphash"],
    "file_path": ["filepath", "targetfilename", "objectname", "file", "path2", "targetpath", "fname"],
    "service": ["servicename", "service", "taskname", "scheduledtask", "servicefilename"],
    "group": ["groupname", "group", "targetgroup"],
    "user_agent": ["useragent", "csuseragent", "httpuseragent", "ua", "requestclientapplication"],
    "session_id": ["sessionid", "session", "logonid", "targetlogonid", "uid2", "connectionid", "tunnelid"],
    "pid": ["pid", "processid", "newprocessid"],
    "message": ["message", "msg2", "description", "details", "log", "rawmessage", "eventmessage", "_raw",
                "summary", "text", "info"],
    "vendor": ["vendor", "devicevendor", "product", "deviceproduct", "logsource", "sourcetype", "channel",
               "providername", "provider", "source", "logname", "program2", "eventsource", "observerproduct"],
}
WIN_MESSAGE_FIELDS = [  # "Label:  value" pairs inside Windows event messages
    (r"Account Name:\s*([^\r\n\t]+)", "user"), (r"Source Network Address:\s*([^\s]+)", "src_ip"),
    (r"Client Address:\s*(?:::ffff:)?([^\s]+)", "src_ip"), (r"Workstation Name:\s*([^\r\n\t]+)", "src_host"),
    (r"Logon Type:\s*(\d+)", "logon_type"), (r"New Process Name:\s*([^\r\n\t]+)", "process"),
    (r"Process Command Line:\s*([^\r\n]+)", "command"), (r"Creator Process Name:\s*([^\r\n\t]+)", "parent_process"),
    (r"Service Name:\s*([^\r\n\t]+)", "service"), (r"Task Name:\s*([^\r\n\t]+)", "service"),
    (r"Group Name:\s*([^\r\n\t]+)", "group"), (r"Source Port:\s*(\d+)", "src_port"),
    (r"Destination Address:\s*([^\s]+)", "dst_ip"), (r"Destination Port:\s*(\d+)", "dst_port"),
    (r"Application Name:\s*([^\r\n\t]+)", "process"), (r"Failure Reason:\s*([^\r\n\t]+)", "outcome"),
]
WIN_MESSAGE_RES = [(re.compile(p, re.I), f) for p, f in WIN_MESSAGE_FIELDS]
IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
KV_RE = re.compile(r'([A-Za-z_][\w.\-]{0,40})=("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^\s,;]+)')
CEF_RE = re.compile(r"CEF:\s*\d+\|([^|]*)\|([^|]*)\|[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|(.*)")
LEEF_RE = re.compile(r"LEEF:\s*[\d.]+\|([^|]*)\|([^|]*)\|[^|]*\|([^|]*)\|(.*)")
WEB_RE = re.compile(r'^(\S+) \S+ (\S+) \[([^\]]+)\] "(\S+) (\S+)[^"]*" (\d{3}) (\d+|-)(?: "([^"]*)" "([^"]*)")?')
SYSLOG_RE = re.compile(r"^(?:<\d+>)?(?:\d\s+)?((?:[A-Z][a-z]{2}\s+\d{1,2} \d\d:\d\d:\d\d)|"
                       r"(?:\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?))\s+(\S+)\s+"
                       r"([\w./\-()]+?)(?:\[(\d+)\])?:?\s+(.*)$")
SSH_RE = re.compile(r"(Failed|Accepted) (\S+) for (?:invalid user )?(\S+) from (\S+)(?: port (\d+))?")
SSH_INVALID_RE = re.compile(r"Invalid user (\S+) from (\S+)")
SUDO_RE = re.compile(r"sudo:\s+(\S+)\s*:.*?(?:USER=(\S+))?.*?COMMAND=(.*)$")
FW_RE = re.compile(r"\b(SRC|DST|SPT|DPT|PROTO)=(\S+)")
WIN_TEXT_RE = re.compile(r"(?:EventID|Event ID|event_id)\D{0,3}(\d{3,5})", re.I)
UFW_ACTION_RE = re.compile(r"\[UFW (\w+)\]|\b(DROP|DENY|REJECT|BLOCK|ACCEPT|ALLOW)\b")

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"], 1)}
_norm = lambda k: re.sub(r"[^a-z0-9@_]", "", str(k).lower()).replace("_", "")


def load_aliases():
    aliases = {k: list(v) for k, v in DEFAULT_ALIASES.items()}
    raw, _ = config_store.load_json(config_store.CONFIG_DIR / "field_mappings.json", {})
    for field, extra in (raw.get("aliases") or {}).items() if isinstance(raw, dict) else []:
        if field in aliases and isinstance(extra, list):
            aliases[field] = [str(x) for x in extra] + aliases[field]  # user aliases win
    lookup = {}
    for field, names in aliases.items():
        for n in names:
            lookup.setdefault(_norm(n), field)
    return lookup


# ------------------------------------------------------------------ timestamps

class TimeParser:
    """Parses many timestamp styles; remembers which formats and timezones it saw."""
    PATTERNS = [
        ("iso8601", re.compile(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:[.,](\d{1,9}))?\s*(Z|[+-]\d\d:?\d\d)?")),
        ("apache", re.compile(r"(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d\d):(\d\d):(\d\d)\s*([+-]\d{4})?")),
        ("syslog", re.compile(r"\b([A-Z][a-z]{2})\s+(\d{1,2}) (\d\d):(\d\d):(\d\d)\b")),
        ("us_12h", re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d\d):(\d\d)\s*([AP]M)", re.I)),
        ("slash_24h", re.compile(r"(\d{4})/(\d\d)/(\d\d)\s+(\d\d):(\d\d):(\d\d)")),
        ("dmy_24h", re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\s+(\d{1,2}):(\d\d):(\d\d)\b")),
        ("epoch", re.compile(r"^\s*(\d{10}(?:\.\d+)?|\d{13})\s*$")),
    ]

    def __init__(self, default_tz_hours=0):
        self.formats, self.zones = Counter(), Counter()
        self.default_tz = timedelta(hours=default_tz_hours)
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)

    def parse(self, value):
        if value in (None, ""):
            return None
        s = str(value)
        for name, rx in self.PATTERNS:
            m = rx.search(s)
            if not m:
                continue
            try:
                ts, tz = self._build(name, m)
            except (ValueError, KeyError, OverflowError):
                continue
            self.formats[name] += 1
            if tz is None:
                self.zones["not stated (assumed UTC)" if not self.default_tz else "not stated (assumed local)"] += 1
                ts = ts - self.default_tz
            else:
                self.zones["UTC" if tz == timedelta(0) else f"UTC{'+' if tz >= timedelta(0) else '-'}"
                           f"{abs(tz).seconds // 3600:02d}:{abs(tz).seconds % 3600 // 60:02d}"] += 1
                ts = ts - tz
            return ts
        return None

    def _build(self, name, m):
        g = m.groups()
        if name == "iso8601":
            frac = int((g[6] or "0")[:6].ljust(6, "0"))
            ts = datetime(int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]), int(g[5]), frac)
            return ts, _tz(g[7])
        if name == "apache":
            return datetime(int(g[2]), MONTHS[g[1].lower()], int(g[0]), int(g[3]), int(g[4]), int(g[5])), _tz(g[6])
        if name == "syslog":
            ts = datetime(self.now.year, MONTHS[g[0].lower()], int(g[1]), int(g[2]), int(g[3]), int(g[4]))
            if ts > self.now + timedelta(days=2):  # no year in syslog: December logs read in January
                ts = ts.replace(year=ts.year - 1)
            return ts, None
        if name == "us_12h":
            h = int(g[3]) % 12 + (12 if g[6].upper() == "PM" else 0)
            return datetime(int(g[2]), int(g[0]), int(g[1]), h, int(g[4]), int(g[5])), None
        if name == "slash_24h":
            return datetime(int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]), int(g[5])), None
        if name == "dmy_24h":
            return datetime(int(g[2]), int(g[1]), int(g[0]), int(g[3]), int(g[4]), int(g[5])), None
        v = float(g[0])
        v = v / 1000 if len(g[0].split(".")[0]) == 13 else v
        return datetime.fromtimestamp(v, timezone.utc).replace(tzinfo=None), timedelta(0)


def _tz(s):
    if not s:
        return None
    if s == "Z":
        return timedelta(0)
    s = s.replace(":", "")
    sign = -1 if s[0] == "-" else 1
    return sign * timedelta(hours=int(s[1:3]), minutes=int(s[3:5]))


# ------------------------------------------------------------------ format detection

def open_text(path):
    path = Path(path)
    raw = gzip.open(path, "rb") if path.suffix == ".gz" else open(path, "rb")
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")


def sniff(path):
    """Return the container format: csv, json, jsonl, winxml, text (or unsupported)."""
    p = Path(path)
    name = p.name.lower().removesuffix(".gz")
    if name.endswith(".evtx"):
        return "unsupported:evtx"
    with open_text(p) as fh:
        head = fh.read(SNIFF_BYTES)
    s = head.lstrip("\ufeff \r\n\t")
    if not s:
        return "empty"
    if s.startswith("<?xml") or s.startswith("<Events") or s.startswith("<Event"):
        return "winxml"
    if s[0] in "{[":
        first = s.splitlines()[0].strip()
        try:
            if isinstance(json.loads(first), dict):
                return "jsonl"
        except ValueError:
            pass
        return "json"
    lines = [ln for ln in s.splitlines()[:20] if ln.strip()]
    if len(lines) >= 2 and not CEF_RE.search(lines[0]) and not SYSLOG_RE.match(lines[0]) and not WEB_RE.match(lines[0]):
        try:
            dialect = csv.Sniffer().sniff("\n".join(lines[:10]), delimiters=",\t;|")
            header = next(csv.reader([lines[0]], dialect))
            if len(header) >= 3 and all(h.strip() and len(h) < 80 for h in header) \
                    and not any(IP_RE.fullmatch(h.strip()) for h in header):
                return "csv"
        except (csv.Error, StopIteration):
            pass
    return "text"


# ------------------------------------------------------------------ record -> event

def _flatten(obj, prefix="", out=None, depth=0):
    """{"source": {"ip": 1}} -> {"source.ip": 1}; short lists of scalars become one string."""
    out = {} if out is None else out
    if isinstance(obj, dict) and depth < 6:
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                _flatten(v, f"{prefix}{k}.", out, depth + 1)
            else:
                out[f"{prefix}{k}"] = v
    elif isinstance(obj, list) and depth < 6:
        if all(not isinstance(x, (dict, list)) for x in obj):
            out[prefix.rstrip(".")] = ", ".join(map(str, obj[:20]))
        else:
            for i, v in enumerate(obj[:20]):
                _flatten(v, f"{prefix}{i}.", out, depth + 1)
    else:
        out[prefix.rstrip(".")] = obj
    return out


class Normaliser:
    def __init__(self, aliases, tparse):
        self.aliases, self.tp = aliases, tparse
        self._colmap = {}

    def map_key(self, key):
        """Column/field name -> canonical field. 'source.ip' matches 'sourceip'; for deeper paths
        (winlog.event_data.IpAddress) the last one or two parts are tried; vague last parts
        such as 'ip' or 'name' alone are never trusted."""
        k = self._colmap.get(key)
        if k is None:
            k = self.aliases.get(_norm(key))
            if k is None and "." in key:
                parts = key.split(".")
                k = self.aliases.get(_norm("".join(parts[-2:])))
                if k is None and parts[-1].lower() not in ("ip", "port", "name", "id", "address", "type", "value"):
                    k = self.aliases.get(_norm(parts[-1]))
            self._colmap[key] = k or ""
        return k or None

    def from_record(self, rec):
        ev, extra = {}, {}
        for key, val in rec.items():
            if val in (None, "", "-") or key is None:
                continue
            f = self.map_key(key)
            sval = val if isinstance(val, (int, float)) else str(val).strip()
            if f and f not in ev:
                ev[f] = sval
            else:
                extra[key] = sval
        return ev, extra

    def finish(self, ev, text, structured=False):
        """Fill derived fields, clean types and timestamps."""
        msg = str(ev.get("message") or "")
        if msg and ("Account Name" in msg or "Network Address" in msg or "Process Name" in msg):
            for rx, f in WIN_MESSAGE_RES:
                if f not in ev:
                    m = rx.search(msg)
                    if m and m.group(1).strip() not in ("-", "", "N/A"):
                        ev[f] = m.group(1).strip()
        if "event_id" not in ev and not structured:
            m = WIN_TEXT_RE.search(text)
            if m:
                ev["event_id"] = m.group(1)
        for f in ("src_port", "dst_port", "bytes_in", "bytes_out", "status", "logon_type", "pid"):
            if f in ev:
                try:
                    ev[f] = int(float(str(ev[f]).split()[0]))
                except (ValueError, IndexError):
                    ev.pop(f)
        for f in ("src_ip", "dst_ip"):
            if f in ev:
                v = str(ev[f]).strip("[]").removeprefix("::ffff:")
                if v.count(":") == 1 and "." in v:  # ip:port
                    v = v.split(":")[0]
                ev[f] = v
        if "event_id" in ev:
            ev["event_id"] = str(ev["event_id"]).strip()
        for f in ("user", "target_user"):
            if f in ev:
                u = str(ev[f]).strip()
                if u in ("-", "N/A", "SYSTEM$") or not u:
                    ev.pop(f)
        if "ts_raw" not in ev and "ts" in ev:
            ev["ts_raw"] = str(ev["ts"])
        ev["ts"] = self.tp.parse(ev.get("ts_raw"))
        if ev["ts"] is None:
            ev["ts"] = self.tp.parse(text[:120])
        ev["source_type"] = classify_source(ev, text)
        return ev


SOURCE_HINTS = [
    ("windows", re.compile(r"microsoft-windows|security-auditing|eventid=\d{4}|\bwinlog|sysmon", re.I)),
    ("edr", re.compile(r"crowdstrike|defender|sentinelone|carbon ?black|sophos|edr|falcon", re.I)),
    ("ids", re.compile(r"snort|suricata|\bids\b|\bips\b|zeek|bro_|alert|signature|cve-\d{4}", re.I)),
    ("vpn", re.compile(r"vpn|anyconnect|openvpn|globalprotect|ipsec|wireguard|\bike\b|ssl-?vpn", re.I)),
    ("dns", re.compile(r"\bdns\b|named\[|qname|query\[|nxdomain|dnsmasq|unbound|rcode", re.I)),
    ("proxy", re.compile(r"squid|proxy|bluecoat|zscaler|tcp_miss|tcp_hit|x-forwarded", re.I)),
    ("firewall", re.compile(r"ufw|iptables|firewall|fortigate|palo ?alto|pan-os|asa-|checkpoint|"
                            r"\b(?:deny|drop|accept|allow)\b.*\b(?:src|dst)|policyid|%asa|%ftd", re.I)),
    ("linux_auth", re.compile(r"sshd\[|sudo:|pam_unix|useradd|usermod|groupadd|passwd\[|systemd-logind|su\[", re.I)),
    ("web", re.compile(r'"(?:GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH) /|nginx|apache|httpd|iis', re.I)),
    ("database", re.compile(r"mysql|postgres|mssql|oracle|sqlserver|mongodb|select .* from", re.I)),
    ("linux", re.compile(r"kernel:|systemd\[|cron\[|auditd|audit\(|rsyslogd", re.I)),
]


def classify_source(ev, text):
    eid = ev.get("event_id", "")
    if str(eid).isdigit() and len(str(eid)) == 4 and (str(eid)[0] in "14567" or ev.get("logon_type")):
        if re.search(r"windows|security|microsoft|logon|account", text, re.I) or "logon_type" in ev:
            return "windows"
    if ev.get("domain") and (ev.get("query_type") or ev.get("rcode")):
        return "dns"
    if ev.get("signature") and ev.get("severity") and ev.get("src_ip"):
        return "ids" if not re.search(r"crowdstrike|defender|sentinelone|edr", text, re.I) else "edr"
    if ev.get("dst_port") and str(ev.get("action", "")).lower() in ("allow", "accept", "deny", "drop", "reject",
                                                                    "block", "permit", "denied", "blocked"):
        return "firewall"
    if ev.get("url") and ev.get("method") and (ev.get("user_agent") or ev.get("bytes_in")) and "proxy" in text.lower():
        return "proxy"
    for name, rx in SOURCE_HINTS:
        if rx.search(text[:1500]):
            return name
    if ev.get("dst_port") and ev.get("action"):
        return "firewall"
    if ev.get("url") and ev.get("status"):
        return "web"
    return "generic"


def parse_text_line(line, norm):
    """Extract fields from one line of syslog / CEF / LEEF / key=value / web / plain text."""
    ev = {}
    m = CEF_RE.search(line)
    if m:
        ev.update(vendor=f"{m.group(1)} {m.group(2)}", event_id=m.group(3), signature=m.group(4), severity=m.group(5))
        rec = {k: v.strip('"') for k, v in re.findall(r"(\w+)=((?:[^=](?!\w+=))*[^=]?)(?=\s+\w+=|$)", m.group(6))}
        f, _ = norm.from_record(rec)
        for k, v in f.items():
            ev.setdefault(k, v)
        return ev
    m = LEEF_RE.search(line)
    if m:
        ev.update(vendor=f"{m.group(1)} {m.group(2)}", event_id=m.group(3))
        rec = dict(p.split("=", 1) for p in re.split(r"\t|\^|\|", m.group(4)) if "=" in p)
        f, _ = norm.from_record(rec)
        for k, v in f.items():
            ev.setdefault(k, v)
        return ev
    m = WEB_RE.match(line)
    if m:
        ev.update(src_ip=m.group(1), ts_raw=m.group(3), method=m.group(4), url=m.group(5), status=m.group(6),
                  bytes_out=m.group(7) if m.group(7) != "-" else None, user_agent=m.group(9))
        if m.group(2) != "-":
            ev["user"] = m.group(2)
        return {k: v for k, v in ev.items() if v not in (None, "")}
    m = SYSLOG_RE.match(line)
    body = line
    if m:
        ev.update(ts_raw=m.group(1), host=m.group(2), process=m.group(3), message=m.group(5))
        if m.group(4):
            ev["pid"] = m.group(4)
        body = m.group(5)
    s = SSH_RE.search(body)
    if s:
        ev.update(outcome="failure" if s.group(1) == "Failed" else "success", action="logon", user=s.group(3),
                  src_ip=s.group(4), protocol="ssh", logon_type=s.group(2))
        if s.group(5):
            ev["src_port"] = s.group(5)
    elif (s := SSH_INVALID_RE.search(body)):
        ev.update(outcome="failure", action="logon", user=s.group(1), src_ip=s.group(2), protocol="ssh")
    elif (s := SUDO_RE.search(body)):
        ev.update(user=s.group(1), command=s.group(3).strip(), action="sudo")
        if s.group(2):
            ev["target_user"] = s.group(2).rstrip(";")
        if "NOT in sudoers" in body or "incorrect password" in body or "authentication failure" in body:
            ev["outcome"] = "failure"
    fw = dict(FW_RE.findall(body))
    if fw:
        ev.setdefault("src_ip", fw.get("SRC"))
        ev.setdefault("dst_ip", fw.get("DST"))
        for k, f in (("SPT", "src_port"), ("DPT", "dst_port"), ("PROTO", "protocol")):
            if k in fw:
                ev.setdefault(f, fw[k])
        a = UFW_ACTION_RE.search(body)
        if a:
            ev.setdefault("action", (a.group(1) or a.group(2)).lower())
    kv = KV_RE.findall(body)
    if len(kv) >= 2:
        f, _ = norm.from_record({k: v.strip("\"'") for k, v in kv})
        for k, v in f.items():
            ev.setdefault(k, v)
    if "src_ip" not in ev:
        ips = IP_RE.findall(body)
        if ips:
            ev["src_ip"] = ips[0]
            if len(ips) > 1:
                ev["dst_ip"] = ips[1]
    return {k: v for k, v in ev.items() if v not in (None, "")}


# ------------------------------------------------------------------ file readers (streaming)

def _json_array_items(fh):
    """Stream objects out of a (possibly huge) JSON array or {"events": [...]} wrapper."""
    dec = json.JSONDecoder()
    buf, pos, started = "", 0, False
    while True:
        chunk = fh.read(1 << 20)
        if chunk:
            buf = buf[pos:] + chunk
            pos = 0
        elif pos >= len(buf.rstrip()):
            return
        if not started:
            i = buf.find("[")
            if i < 0:
                if not chunk:
                    return
                continue
            pre = buf[:i].strip()
            if pre and not pre.startswith("{"):
                raise ValueError("unexpected JSON structure")
            pos, started = i + 1, True
        while True:
            while pos < len(buf) and buf[pos] in " \r\n\t,":
                pos += 1
            if pos >= len(buf) or buf[pos] == "]":
                if pos < len(buf) and buf[pos] == "]":
                    return
                break
            try:
                obj, end = dec.raw_decode(buf, pos)
            except ValueError:
                if not chunk:
                    raise
                break  # need more data
            pos = end
            yield obj
        if not chunk:
            return


def _iter_records(path, fmt, stats):
    """Yield (line_no, record_dict | None, raw_text) per record."""
    if fmt == "csv":
        with open_text(path) as fh:
            sample = fh.read(SNIFF_BYTES)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff("\n".join(sample.splitlines()[:10]), delimiters=",\t;|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(fh, dialect)
            header = [h.strip().lstrip("\ufeff") or f"col{i}" for i, h in enumerate(next(reader, []))]
            # Windows Event Viewer CSV: the 6th column (message) has no header
            if len(header) == 5 and [h.lower() for h in header[:2]] == ["level", "date and time"]:
                header.append("Message")
            stats["columns"] = header
            for n, row in enumerate(reader, 2):
                if not row or not any(c.strip() for c in row):
                    continue
                if len(row) > len(header):
                    row = row[:len(header) - 1] + [",".join(row[len(header) - 1:])]
                if len(row) < len(header) - 1:
                    stats["failures"].append((n, f"expected {len(header)} columns, got {len(row)}"))
                rec = dict(zip(header, row))
                yield n, rec, ",".join(row)
    elif fmt in ("json", "jsonl"):
        with open_text(path) as fh:
            if fmt == "jsonl":
                for n, line in enumerate(fh, 1):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError as e:
                        stats["failures"].append((n, f"invalid JSON ({e.msg})"))
                        yield n, None, line.rstrip("\r\n")
                        continue
                    yield n, obj if isinstance(obj, dict) else {"message": obj}, line.rstrip("\r\n")
            else:
                head = fh.read(SNIFF_BYTES)
                fh.seek(0)
                if head.lstrip().startswith("{") and "[" not in head.split(":", 3)[-1][:200] and len(head) < SNIFF_BYTES:
                    obj = json.load(fh)
                    items = next((v for v in obj.values() if isinstance(v, list)), [obj]) if isinstance(obj, dict) else [obj]
                else:
                    items = _json_array_items(fh)
                try:
                    for n, obj in enumerate(items, 1):
                        if isinstance(obj, dict) and "_source" in obj and isinstance(obj["_source"], dict):
                            obj = obj["_source"]  # Elasticsearch / OpenSearch export
                        yield n, obj if isinstance(obj, dict) else {"message": obj}, json.dumps(obj)[:RAW_KEEP]
                except ValueError as e:
                    stats["failures"].append((0, f"JSON structure error: {e}"))
    elif fmt == "winxml":
        with open_text(path) as fh:
            n = 0
            try:
                for _, el in ET.iterparse(fh, events=("end",)):
                    if el.tag.rsplit("}", 1)[-1] != "Event":
                        continue
                    n += 1
                    rec = {}
                    for child in el.iter():
                        tag = child.tag.rsplit("}", 1)[-1]
                        if tag == "Data" and child.get("Name"):
                            rec[child.get("Name")] = (child.text or "").strip()
                        elif tag == "TimeCreated":
                            rec["TimeCreated"] = child.get("SystemTime")
                        elif tag == "Provider":
                            rec["ProviderName"] = child.get("Name")
                        elif tag in ("EventID", "Computer", "Channel", "Level", "Keywords", "Message") and child.text:
                            rec[tag] = child.text.strip()
                        elif tag == "Execution":
                            rec["ProcessID"] = child.get("ProcessID")
                    raw = re.sub(r'\s?xmlns(:ns\d+)?="[^"]*"|ns\d+:', "", ET.tostring(el, encoding="unicode"))[:RAW_KEEP]
                    el.clear()
                    yield n, rec, raw
            except ET.ParseError as e:
                stats["failures"].append((n, f"XML error: {e}"))
    else:
        with open_text(path) as fh:
            for n, line in enumerate(fh, 1):
                line = line.rstrip("\r\n")
                if line.strip():
                    yield n, None, line


def iter_events(path, display_name=None, tz_hours=0, aliases=None, stats=None):
    """Stream normalised events from one file. Fills `stats` with the ingestion summary."""
    path = Path(path)
    name = display_name or path.name
    fmt = sniff(path)
    st = stats if stats is not None else {}
    st.update(file=name, size=path.stat().st_size, format=fmt, events=0, failures=[], columns=[],
              field_counts=Counter(), sources=Counter(), no_timestamp=0, first=None, last=None)
    if fmt.startswith("unsupported") or fmt == "empty":
        st["failures"].append((0, "Windows .evtx is binary - export it from Event Viewer as XML or CSV"
                               if fmt == "unsupported:evtx" else "file is empty"))
        return
    tp = TimeParser(tz_hours)
    st["_tp"] = tp
    norm = Normaliser(aliases or load_aliases(), tp)
    for n, rec, raw in _iter_records(path, fmt, st):
        if rec is not None:
            ev, extra = norm.from_record(_flatten(rec) if fmt in ("json", "jsonl") else rec)
            if fmt == "csv" and not st.get("mapped"):
                st["mapped"] = {c: norm.map_key(c) for c in st["columns"]}
            text = raw
        else:
            ev = parse_text_line(raw, norm)
            text = raw
        if "ts" in ev:
            ev["ts_raw"] = ev.pop("ts")
        ev = norm.finish(ev, text, structured=rec is not None)
        # signature rules read `text`; a structured EventID is made explicit for them
        eid = ev.get("event_id")
        ev["text"] = (f"EventID={eid} " if eid and "eventid" not in text[:300].lower().replace(" ", "") else "") + text
        ev.update(file=name, line=n, ref=f"{name}:{n}", raw=raw[:RAW_KEEP])
        st["events"] += 1
        st["sources"][ev["source_type"]] += 1
        for k in ev:
            st["field_counts"][k] += 1
        if ev["ts"] is None:
            st["no_timestamp"] += 1
        else:
            st["first"] = min(st["first"] or ev["ts"], ev["ts"])
            st["last"] = max(st["last"] or ev["ts"], ev["ts"])
        yield ev


REPORTED_FIELDS = ["ts", "src_ip", "dst_ip", "src_port", "dst_port", "protocol", "user", "host", "event_id",
                   "action", "outcome", "process", "command", "url", "domain", "bytes_out", "logon_type", "hash",
                   "assigned_ip", "session_id"]


def summarise(st):
    """JSON-safe ingestion summary for one file."""
    n = max(st.get("events", 0), 1)
    tp = st.get("_tp")
    fc = st.get("field_counts", Counter())
    have = {f: round(100 * fc.get(f, 0) / n, 1) for f in REPORTED_FIELDS if fc.get(f, 0)}
    if "ts" in have:
        have["ts"] = round(100 * (n - st.get("no_timestamp", 0)) / n, 1)
        if not have["ts"]:
            have.pop("ts")
    return {
        "file": st.get("file"), "size": st.get("size"), "format": st.get("format"),
        "events": st.get("events", 0),
        "probable_source": [s for s, _ in st.get("sources", Counter()).most_common(3)],
        "source_counts": dict(st.get("sources", Counter()).most_common(8)),
        "columns": st.get("columns", [])[:60],
        "column_mapping": {k: v for k, v in (st.get("mapped") or {}).items() if v},
        "unmapped_columns": [k for k, v in (st.get("mapped") or {}).items() if not v][:40],
        "fields_available": have,
        "fields_unavailable": [f for f in REPORTED_FIELDS if f not in have],
        "timestamp_formats": dict(tp.formats) if tp else {},
        "timezones": dict(tp.zones) if tp else {},
        "no_timestamp": st.get("no_timestamp", 0),
        "time_range": {"start": _fmt(st.get("first")), "end": _fmt(st.get("last"))},
        "parse_failures": len(st.get("failures", [])),
        "failure_samples": [{"line": ln, "error": err} for ln, err in st.get("failures", [])[:10]],
    }


def _fmt(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S") if ts else None


def iter_text(text, name="pasted log", tz_hours=0, stats=None):
    """Same as iter_events for text pasted in the UI (no file)."""
    import tempfile
    import os
    fd, tmp = tempfile.mkstemp(dir=config_store.UPLOAD_DIR if config_store.UPLOAD_DIR.exists() else None,
                               suffix=".log")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        yield from iter_events(tmp, name, tz_hours, stats=stats)
    finally:
        os.unlink(tmp)
