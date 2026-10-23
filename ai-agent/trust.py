"""Trusted Networks & Assets: inventory, validation, IP classification and change history.

Trust is CONTEXT, never an exemption. Classification tells the analyst and the AI agent
what an address is; it never lowers severity or suppresses a detection.

Classification precedence (first match wins, documented in docs/TRUSTED-NETWORKS.md):
  1. invalid / unparseable address
  2. suspicious_indicators     - an explicitly suspicious/blocked entry always wins,
                                 even inside a trusted range
  3. trusted_assets            - exact IP of a known asset
  4. most specific prefix among isp_public_ips, approved_external_services and
     trusted_networks (longest prefix wins; equal prefixes: ISP > external service > network)
  5. loopback / link-local
  6. other private (RFC 1918, ULA, CGNAT) - private but NOT in your inventory
  7. public address not in the approved inventory
"""
import csv
import copy
import io
import ipaddress
import re
import uuid
from datetime import date, datetime
from functools import lru_cache

import config_store

FILE = "trusted_assets.json"
SECTIONS = ("trusted_networks", "isp_public_ips", "trusted_assets", "approved_external_services",
            "suspicious_indicators", "service_accounts")
SECTION_LABELS = {
    "trusted_networks": "Internal / trusted networks",
    "isp_public_ips": "ISP-assigned public IPs",
    "trusted_assets": "Servers, workstations & devices",
    "approved_external_services": "Known external services",
    "suspicious_indicators": "Suspicious / blocked indicators",
    "service_accounts": "Approved service accounts",
}
TRUST_CLASSES = {
    "internal_trusted": "Internal trusted network",
    "isp_public": "ISP-assigned public address",
    "public_server": "Approved public-facing server",
    "management_host": "Approved management host",
    "monitoring_scanner": "Approved monitoring or scanning system",
    "known_external_service": "Known external service",
    "unclassified": "Unclassified network or asset",
    "suspicious_blocked": "Explicitly suspicious or blocked indicator",
}
ASSET_TYPES = ("server", "workstation", "domain_controller", "dns_server", "dhcp_server", "firewall",
               "router", "switch", "vpn_gateway", "proxy", "web_server", "reverse_proxy", "database",
               "jump_host", "monitoring", "scanner", "network_device", "other")
CRITICALITY = ("low", "medium", "high", "critical")
DEFAULT_CLASS = {"trusted_networks": "internal_trusted", "isp_public_ips": "isp_public",
                 "trusted_assets": "internal_trusted", "approved_external_services": "known_external_service",
                 "suspicious_indicators": "suspicious_blocked", "service_accounts": "internal_trusted"}
# Result categories of classify()
CATEGORY_LABELS = {
    "configured_internal": "Configured internal network",
    "configured_isp": "Configured ISP address",
    "approved_asset": "Approved server or asset",
    "known_external_service": "Known external service",
    "suspicious_indicator": "Configured suspicious / blocked indicator",
    "other_private": "Other private network (not in inventory)",
    "public_unknown": "Public address not in approved inventory",
    "loopback_linklocal": "Loopback or link-local",
    "invalid": "Invalid or unparseable address",
    "unknown": "Unknown / unclassified",
}
# Explicit private ranges. Python's ip.is_private also counts documentation ranges
# (192.0.2.0/24, 203.0.113.0/24...) as private, which would hide real external traffic.
PRIVATE_NETS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                                                  "100.64.0.0/10", "fc00::/7")]


def is_private_ip(ip):
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    return any(a in n for n in PRIVATE_NETS if n.version == a.version)


MIN_PREFIX = {4: 8, 6: 32}   # never trust anything broader than a /8 (IPv4) or /32 (IPv6)
# IPv6 ranges that embed the whole IPv4 internet: trusting one would trust every IPv4 address
TRANSLATION_NETS = [ipaddress.ip_network(n) for n in ("::ffff:0:0/96", "64:ff9b::/96", "64:ff9b:1::/48", "2002::/16",
                                                      "::/96")]


def embedded_ipv4(addr):
    """IPv4 address carried inside an IPv6 one (mapped, NAT64, 6to4), else None."""
    if addr.version != 6:
        return None
    if addr.ipv4_mapped:
        return addr.ipv4_mapped
    if addr in TRANSLATION_NETS[1]:
        return ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    if addr.sixtofour:
        return addr.sixtofour
    return None
TEXT_FIELDS = ("id", "name", "asset_id", "hostname", "asset_type", "zone", "owner", "criticality",
               "environment", "description", "classification", "valid_from", "valid_until", "notes",
               "isp", "domain", "reason", "username")
EMPTY = {s: [] for s in SECTIONS}


# ------------------------------------------------------------------ load / validate

def _date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise ValueError(f"{field} must be a date like 2026-01-31")


def _network(value, section):
    """Parse an IP or CIDR strictly. '192.168.1.5/16' is rejected instead of silently widened."""
    s = str(value or "").strip()
    if not s:
        raise ValueError("an IP address or CIDR is required")
    try:
        net = ipaddress.ip_network(s, strict=True)
    except ValueError:
        try:
            loose = ipaddress.ip_network(s, strict=False)
        except ValueError:
            raise ValueError(f"'{s}' is not a valid IP address or CIDR")
        raise ValueError(f"'{s}' has host bits set; did you mean {loose}? (refused so a typo can't trust a wider range)")
    if section != "suspicious_indicators" and net.version == 6 and any(net.overlaps(t) for t in TRANSLATION_NETS):
        raise ValueError(f"'{s}' overlaps an IPv4-translation range (::ffff:0:0/96, 64:ff9b::/96, 2002::/16); "
                         "add the IPv4 network itself instead")
    if section != "suspicious_indicators" and net.prefixlen < MIN_PREFIX[net.version]:
        raise ValueError(f"'{s}' is too broad (/{net.prefixlen}); the widest allowed is "
                         f"/{MIN_PREFIX[net.version]} so an import can never trust an entire network")
    return net


def validate_entry(section, entry):
    """Return a clean copy of one entry or raise ValueError with a readable message."""
    if section not in SECTIONS:
        raise ValueError(f"unknown section '{section}'")
    if not isinstance(entry, dict):
        raise ValueError("entry must be an object")
    out = {}
    for f in TEXT_FIELDS:
        v = entry.get(f)
        if v not in (None, ""):
            v = str(v).strip()
            if len(v) > 300:
                raise ValueError(f"{f} is too long (max 300 characters)")
            out[f] = v
    out["id"] = out.get("id") or uuid.uuid4().hex[:10]
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", out["id"]):
        raise ValueError("id may only contain letters, digits, '.', '_' and '-'")
    if not out.get("name"):
        raise ValueError("name is required")
    enabled = entry.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("1", "true", "yes", "y", "enabled")
    out["enabled"] = bool(enabled)
    out["valid_from"] = _date(entry.get("valid_from"), "valid_from")
    out["valid_until"] = _date(entry.get("valid_until"), "valid_until")
    if out["valid_from"] and out["valid_until"] and out["valid_from"] > out["valid_until"]:
        raise ValueError("valid_from is after valid_until")
    cls = out.get("classification") or DEFAULT_CLASS[section]
    if cls not in TRUST_CLASSES:
        raise ValueError(f"classification must be one of: {', '.join(TRUST_CLASSES)}")
    if section == "suspicious_indicators":
        cls = "suspicious_blocked"
    elif cls == "suspicious_blocked":
        raise ValueError("use the suspicious_indicators section for blocked indicators")
    out["classification"] = cls
    if out.get("asset_type") and out["asset_type"] not in ASSET_TYPES:
        raise ValueError(f"asset_type must be one of: {', '.join(ASSET_TYPES)}")
    if out.get("criticality") and out["criticality"] not in CRITICALITY:
        raise ValueError(f"criticality must be one of: {', '.join(CRITICALITY)}")

    if section == "service_accounts":
        if not out.get("username"):
            raise ValueError("username is required for a service account")
        hosts = entry.get("allowed_hosts") or []
        if isinstance(hosts, str):
            hosts = [h for h in re.split(r"[;,\s]+", hosts) if h]
        out["allowed_hosts"] = [str(h)[:255] for h in hosts][:100]
        out["interactive_allowed"] = str(entry.get("interactive_allowed", False)).lower() in ("1", "true", "yes")
        return out
    if section == "approved_external_services" and out.get("domain") and not (entry.get("cidr") or entry.get("ip")):
        if not re.fullmatch(r"(\*\.)?[A-Za-z0-9.\-]{1,253}", out["domain"]):
            raise ValueError("domain is not valid")
        return out
    net = _network(entry.get("cidr") or entry.get("ip"), section)
    if section == "trusted_assets":
        if net.num_addresses != 1:
            raise ValueError("an asset must be a single IP address (use Trusted networks for ranges)")
        out["ip"] = str(net.network_address)
    else:
        out["cidr"] = str(net)
    ports = entry.get("allowed_services") or entry.get("allowed_ports") or []
    if isinstance(ports, str):
        ports = [p for p in re.split(r"[;,\s]+", ports) if p]
    clean_ports = []
    for p in ports[:64]:
        if not str(p).isdigit() or not 0 < int(p) < 65536:
            raise ValueError(f"allowed service port '{p}' is not a valid port number")
        clean_ports.append(int(p))
    if clean_ports:
        out["allowed_services"] = clean_ports
    return out


def validate_config(data):
    """Validate a whole configuration. Returns (clean_config, errors). Invalid entries are dropped."""
    clean, errors = copy.deepcopy(EMPTY), []
    if not isinstance(data, dict):
        return clean, ["configuration must be a JSON object"]
    seen = set()
    for section in SECTIONS:
        items = data.get(section) or []
        if not isinstance(items, list):
            errors.append(f"{section}: must be a list")
            continue
        for i, entry in enumerate(items, 1):
            try:
                e = validate_entry(section, entry)
            except ValueError as ex:
                name = entry.get("name", "") if isinstance(entry, dict) else ""
                errors.append(f"{section} #{i} {name}: {ex}".replace("  ", " "))
                continue
            if e["id"] in seen:
                e["id"] = uuid.uuid4().hex[:10]
            seen.add(e["id"])
            clean[section].append(e)
    return clean, errors


class Inventory:
    def __init__(self, data=None, errors=None):
        self.data, self.errors = validate_config(data or {})
        self.errors = (errors or []) + self.errors
        self._build()

    @classmethod
    def load(cls):
        raw, err = config_store.load_json(config_store.live_path(FILE), EMPTY)
        return cls(raw, [err] if err else [])

    def save(self, actor, action, target="", before=None, after=None):
        config_store.save_json(config_store.live_path(FILE), self.data)
        config_store.audit(actor, "trusted_assets", action, target, before, after)
        _cached.cache_clear()

    def _build(self):
        self.nets = []          # (network, rank, section, entry)
        self.assets = {}        # ip -> entry
        self.suspicious = []    # (network, entry)
        rank = {"isp_public_ips": 0, "approved_external_services": 1, "trusted_networks": 2}
        for section in ("isp_public_ips", "approved_external_services", "trusted_networks"):
            for e in self.data[section]:
                if e.get("enabled") and e.get("cidr"):
                    self.nets.append((ipaddress.ip_network(e["cidr"]), rank[section], section, e))
        for e in self.data["trusted_assets"]:
            if e.get("enabled"):
                self.assets.setdefault(e["ip"], e)
        for e in self.data["suspicious_indicators"]:
            if e.get("enabled") and e.get("cidr"):
                self.suspicious.append((ipaddress.ip_network(e["cidr"]), e))
        self.service_accounts = {e["username"].lower(): e for e in self.data["service_accounts"] if e.get("enabled")}
        self.hostnames = {e["hostname"].lower(): e for e in self.data["trusted_assets"]
                          if e.get("enabled") and e.get("hostname")}
        self.domains = [e for e in self.data["approved_external_services"] if e.get("enabled") and e.get("domain")]
        self.enabled_count = len(self.nets) + len(self.assets) + len(self.suspicious) + len(self.service_accounts)

    # ------------------------------------------------------------ classification
    def classify(self, ip, at=None):
        """Classify one address. `at` (date/datetime) checks valid_from/valid_until."""
        day = (at.date() if isinstance(at, datetime) else at) or date.today()
        return dict(_cached(self, str(ip).strip(), day.isoformat()))

    def _classify(self, ip, day):
        res = {"ip": ip, "category": "unknown", "label": CATEGORY_LABELS["unknown"],
               "trust_class": "unclassified", "trusted_context": False}
        try:
            addr = ipaddress.ip_address(ip.split("%")[0])
        except ValueError:
            res.update(category="invalid", label=CATEGORY_LABELS["invalid"])
            return res
        v4 = embedded_ipv4(addr)
        if v4 is not None:   # ::ffff:8.8.8.8 is 8.8.8.8 - classify the real address
            addr = v4

        def active(e):
            return (not e.get("valid_from") or e["valid_from"] <= day) and \
                   (not e.get("valid_until") or day <= e["valid_until"])

        sus = [(n, e) for n, e in self.suspicious if addr in n and active(e)]
        if sus:
            n, e = max(sus, key=lambda x: x[0].prefixlen)
            res.update(category="suspicious_indicator", label=CATEGORY_LABELS["suspicious_indicator"],
                       trust_class="suspicious_blocked", entry=_public(e), matched=str(n))
            return res
        a = self.assets.get(str(addr))
        if a and active(a):
            res.update(category="approved_asset", label=CATEGORY_LABELS["approved_asset"],
                       trust_class=a["classification"], entry=_public(a), matched=a["ip"],
                       asset_type=a.get("asset_type"), criticality=a.get("criticality"), zone=a.get("zone"),
                       trusted_context=True)
            # also record the network it sits in (for zone context)
            net = self._best_net(addr, active)
            if net:
                res["network"] = _public(net[3])
            return res
        net = self._best_net(addr, active)
        if net:
            n, _, section, e = net
            cat = {"isp_public_ips": "configured_isp", "approved_external_services": "known_external_service",
                   "trusted_networks": "configured_internal"}[section]
            res.update(category=cat, label=CATEGORY_LABELS[cat], trust_class=e["classification"],
                       entry=_public(e), matched=str(n), zone=e.get("zone"), criticality=e.get("criticality"),
                       trusted_context=True)
            return res
        if addr.is_loopback or addr.is_link_local:
            res.update(category="loopback_linklocal", label=CATEGORY_LABELS["loopback_linklocal"])
        elif any(addr in n for n in PRIVATE_NETS if n.version == addr.version):
            res.update(category="other_private", label=CATEGORY_LABELS["other_private"])
        else:
            res.update(category="public_unknown", label=CATEGORY_LABELS["public_unknown"])
        return res

    def _best_net(self, addr, active):
        hits = [x for x in self.nets if addr.version == x[0].version and addr in x[0] and active(x[3])]
        return max(hits, key=lambda x: (x[0].prefixlen, -x[1])) if hits else None

    def is_internal(self, cls):
        return cls["category"] in ("configured_internal", "approved_asset", "other_private", "loopback_linklocal") \
            and cls.get("trust_class") not in ("public_server", "isp_public", "known_external_service")

    def host_asset(self, hostname):
        return self.hostnames.get(str(hostname or "").lower())

    def service_account(self, user):
        return self.service_accounts.get(str(user or "").lower().split("\\")[-1].split("@")[0])

    # ------------------------------------------------------------ AI / report context
    def summary(self, limit=40):
        """Structured, compact description of the inventory for the AI agent and the report."""
        lines = []
        for section in SECTIONS:
            items = [e for e in self.data[section] if e.get("enabled")]
            if not items:
                continue
            lines.append(f"{SECTION_LABELS[section]} ({len(items)} enabled):")
            for e in items[:limit]:
                where = e.get("cidr") or e.get("ip") or e.get("domain") or e.get("username") or ""
                extra = ", ".join(x for x in (e.get("asset_type"), e.get("zone"), e.get("criticality") and
                                             f"criticality {e['criticality']}", e.get("allowed_services") and
                                             f"allowed ports {e['allowed_services']}") if x)
                lines.append(f"- {e['name']}: {where} [{TRUST_CLASSES.get(e['classification'], '')}]"
                             + (f" ({extra})" if extra else ""))
        if not lines:
            return "No trusted networks or assets are configured; every address is treated as unclassified."
        lines.append("Rule: trusted/ISP/internal classification is context only - it never makes activity safe.")
        return "\n".join(lines)


@lru_cache(maxsize=65536)
def _cached(inv, ip, day):
    return tuple(inv._classify(ip, day).items())


def _public(e):
    return {k: v for k, v in e.items() if k in ("id", "name", "cidr", "ip", "hostname", "asset_type", "zone",
                                                  "owner", "criticality", "environment", "classification",
                                                  "allowed_services", "domain")}


# ------------------------------------------------------------------ editing with audit trail

def upsert(inv, section, entry, actor):
    clean = validate_entry(section, entry)
    items = inv.data[section]
    before = next((copy.deepcopy(e) for e in items if e["id"] == clean["id"]), None)
    if before:
        items[:] = [clean if e["id"] == clean["id"] else e for e in items]
    else:
        items.append(clean)
    inv._build()
    inv.save(actor, "update" if before else "add", f"{section}/{clean['id']}", before, clean)
    return clean


def remove(inv, section, entry_id, actor):
    items = inv.data.get(section, [])
    before = next((e for e in items if e["id"] == entry_id), None)
    if not before:
        raise ValueError("entry not found")
    items[:] = [e for e in items if e["id"] != entry_id]
    inv._build()
    inv.save(actor, "delete", f"{section}/{entry_id}", before, None)


# ------------------------------------------------------------------ import / export

CSV_COLUMNS = ["section", "id", "name", "cidr", "ip", "hostname", "asset_type", "zone", "classification",
               "owner", "criticality", "environment", "description", "valid_from", "valid_until", "enabled",
               "allowed_services", "domain", "username", "allowed_hosts", "notes"]


def export_csv(inv):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for section in SECTIONS:
        for e in inv.data[section]:
            row = dict(e, section=section)
            for k in ("allowed_services", "allowed_hosts"):
                if isinstance(row.get(k), list):
                    row[k] = ";".join(map(str, row[k]))
            # neutralise spreadsheet formulas (CSV injection) in free-text cells
            for k, v in row.items():
                if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
                    row[k] = "'" + v
            w.writerow(row)
    return buf.getvalue()


def parse_import(text, fmt):
    """Turn an uploaded CSV/JSON file into {section: [raw entries]}; structural errors raise."""
    if fmt == "json":
        import json
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("JSON import must be an object with sections such as trusted_networks")
        unknown = set(data) - set(SECTIONS) - {"version", "_comment"}
        if unknown:
            raise ValueError(f"unknown sections: {', '.join(sorted(unknown))}")
        return {s: data.get(s) or [] for s in SECTIONS}
    rows = list(csv.DictReader(io.StringIO(text)))
    if rows and "section" not in rows[0]:
        raise ValueError("CSV import needs a 'section' column (see the exported CSV for the format)")
    out = {s: [] for s in SECTIONS}
    for r in rows:
        sec = (r.get("section") or "").strip()
        out.setdefault(sec, []).append({k: v for k, v in r.items() if k != "section" and v not in (None, "")})
    return out


def preview_import(inv, raw, mode="merge"):
    """Validate an import WITHOUT applying it. Returns what would change and every error."""
    errors, valid = [], {s: [] for s in SECTIONS}
    for section, items in raw.items():
        if section not in SECTIONS:
            errors.append(f"row(s) with unknown section '{section}' ignored")
            continue
        for i, e in enumerate(items, 1):
            try:
                valid[section].append(validate_entry(section, e))
            except ValueError as ex:
                errors.append(f"{section} row {i} ({(e or {}).get('name', '?')}): {ex}")
    changes = {"add": [], "update": [], "unchanged": [], "remove": []}
    for section in SECTIONS:
        existing = {e["id"]: e for e in inv.data[section]}
        for e in valid[section]:
            old = existing.get(e["id"])
            key = "add" if not old else "unchanged" if old == e else "update"
            changes[key].append({"section": section, "id": e["id"], "name": e["name"],
                                 "where": e.get("cidr") or e.get("ip") or e.get("domain") or e.get("username")})
        if mode == "replace":
            new_ids = {e["id"] for e in valid[section]}
            changes["remove"] += [{"section": section, "id": i, "name": e["name"]}
                                  for i, e in existing.items() if i not in new_ids]
    return {"valid": valid, "errors": errors, "changes": changes, "mode": mode,
            "counts": {k: len(v) for k, v in changes.items()}}


def apply_import(inv, raw, mode, actor):
    """Apply only validated rows. Invalid rows are never applied."""
    prev = preview_import(inv, raw, mode)
    before = copy.deepcopy(inv.data)
    for section in SECTIONS:
        if mode == "replace":
            inv.data[section] = []
        by_id = {e["id"]: i for i, e in enumerate(inv.data[section])}
        for e in prev["valid"][section]:
            if e["id"] in by_id:
                inv.data[section][by_id[e["id"]]] = e
            else:
                inv.data[section].append(e)
    inv._build()
    inv.save(actor, f"import ({mode})", "all", {s: len(before[s]) for s in SECTIONS},
             {"counts": prev["counts"], "errors": prev["errors"][:50]})
    return prev
