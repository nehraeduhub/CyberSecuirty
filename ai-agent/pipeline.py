"""Upload-to-report analysis pipeline.

  files -> parsers (normalise, stream) -> detector (regex signatures) + engine (structured rules,
  UEBA, statistics, TI, forensics) -> evidence pass (re-read exact records by reference)
  -> de-duplication -> trust context -> correlation into incidents -> explainable risk
  -> evidence register (E-IDs) -> SOAR checklists -> limitations / missing telemetry.

Trust context is attached to findings but NEVER lowers severity or removes a finding.
Severity, confidence, UEBA score, incident risk and asset trust are separate fields.
"""
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import config_store
import detector
import engine
import knowledge
import parsers
import rules as rulebook
import trust

SEV = ["critical", "high", "medium", "low", "info"]
SEV_RANK = {s: i for i, s in enumerate(SEV)}
SEV_BASE = {"critical": 70, "high": 50, "medium": 30, "low": 15, "info": 5}
CORRELATION_IDS = {"ssh_bruteforce", "bruteforce_success", "win_bruteforce", "web_enum", "port_scan"}
BASELINE_FILE = config_store.DATA_DIR / "baselines.json"
MAX_EVIDENCE = 1500
LINK_WINDOW = timedelta(hours=2)


def _fmt(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else ts


def _parse(ts):
    if isinstance(ts, datetime) or not ts:
        return ts or None
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def norm_host(h):
    h = str(h or "").strip()
    if not h or h.lower() in ("-", "unknown", "localhost"):
        return ""
    return h.split(".")[0].upper() if not re.fullmatch(r"[\d.]+", h) else h


# ------------------------------------------------------------------ main entry points

def analyze_text(text, name="pasted log", **kw):
    config_store.ensure_dirs()
    tmp = config_store.UPLOAD_DIR / f"paste-{int(time.time() * 1000)}.log"
    tmp.write_text(text, encoding="utf-8")
    try:
        return analyze_files([(tmp, name)], **kw)
    finally:
        tmp.unlink(missing_ok=True)


def analyze_files(files, tz_hours=0, learn_baseline=True, inventory=None, iocs=None, extra_ioc_paths=None):
    """files: [(path, display_name)]. Returns the full, JSON-serialisable analysis."""
    t0 = time.time()
    inv = inventory or trust.Inventory.load()
    rules, rule_errors = rulebook.load()
    if iocs is None:
        iocs, ioc_errors = engine.load_iocs()
        if extra_ioc_paths:
            more, e2 = engine.load_iocs(extra_ioc_paths)
            for k in iocs:
                iocs[k].update(more[k])
            ioc_errors += e2
    else:
        ioc_errors = []
    baselines, _ = config_store.load_json(BASELINE_FILE, {})
    det = detector.LogAnalyzer()
    eng = engine.Engine(rules, inv, iocs)
    aliases = parsers.load_aliases()
    ingestion, n = [], 0
    for path, name in files:
        st = {}
        for ev in parsers.iter_events(path, name, tz_hours, aliases, st):
            n += 1
            det.feed(ev["text"], n, ev["ref"], ev["ts"])
            eng.observe(ev)
        ingestion.append(parsers.summarise(st))
    d = det.result()
    e = eng.finish(baselines if isinstance(baselines, dict) else {})

    findings = [_from_detector(f) for f in d["findings"]] + e["findings"]
    evidence = _evidence_pass(files, findings, e, aliases, tz_hours)
    for f in findings:
        _entities(f, evidence)
        for s in f.get("samples", []):  # samples captured from compact events get their original text here
            if not s.get("text") and s.get("ref") in evidence:
                s["text"] = str(evidence[s["ref"]].get("raw", ""))[:300]
    findings = _dedupe(findings)
    _trust_context(findings, inv)
    aliases_map = _alias_map(e, inv, evidence)
    incidents = _correlate(findings, aliases_map)
    ueba_by_user = {u["entity"]: u for u in e["ueba"]["entities"]}
    ti_values = {m["value"].lower() for m in e["ti_matches"]}
    for f in findings:
        _score(f, ueba_by_user, ti_values)
    for inc in incidents:
        _incident_score(inc, findings)
    register = _register(findings, incidents, evidence)
    for inc in incidents:
        inc["checklist"], inc["actions"] = _soar(inc, findings)
    findings.sort(key=lambda f: (-f["risk"]["score"], SEV_RANK[f["severity"]]))
    for i, f in enumerate(findings, 1):
        f["fid"] = f"F-{i:02d}"
    fid = {f["id"]: f["fid"] for f in findings}
    for inc in incidents:
        inc["finding_ids"] = [fid[x] for x in inc["findings"] if x in fid]

    out = detector.score([{"severity": f["severity"]} for f in findings])
    top = max([i["risk"]["score"] for i in incidents] + [f["risk"]["score"] for f in findings] + [0])
    out.update(
        kind="logs", findings=findings, risk_score=top,
        risk_level="critical" if top >= 75 else "high" if top >= 50 else "medium" if top >= 25 else "low" if top else "clean",
        lines=n, log_types=sorted({s for i in ingestion for s in i["probable_source"]}) or ["generic"],
        top_ips=d["top_ips"], targeted_users=d["targeted_users"],
        time_range=_time_range(ingestion), suspicious_lines=d["suspicious_lines"],
        ingestion=ingestion, incidents=incidents, evidence=register,
        ueba={"entities": e["ueba"]["entities"][:60]}, statistics=e["statistics"], forensics=e["forensics"],
        ti={"matches": e["ti_matches"], "feeds_loaded": sum(len(v) for v in iocs.values()),
            "errors": ioc_errors}, telemetry=e["telemetry"],
        trust={"configured": inv.enabled_count > 0, "summary": inv.summary(), "errors": inv.errors,
               "entries": inv.enabled_count},
        rule_errors=rule_errors, duration_s=round(time.time() - t0, 2),
    )
    out["grade"] = "A" if top == 0 else "B" if top < 15 else "C" if top < 30 else "D" if top < 50 else "E" if top < 75 else "F"
    out["ip_profiles"] = _ip_profiles(findings, inv)
    out["iocs"] = _iocs(d, findings, e, inv)
    out["timeline"], out["timeline_bucket"] = _timeline(evidence, findings)
    out["attack_mapping"] = _attack_map(findings)
    out["limitations"] = _limitations(out, e, ingestion, inv, iocs)
    out["coverage"] = _coverage(e["telemetry"])
    if learn_baseline:
        _update_baselines(baselines if isinstance(baselines, dict) else {}, e["ueba"]["history"], incidents, findings)
    return out


# ------------------------------------------------------------------ stages

def _from_detector(f):
    cat = rulebook.catalogue_entry(f["id"])
    f.update(rule_id=cat["rule_id"], confidence=cat["confidence"], fp=cat["fp"], telemetry=cat["telemetry"],
             method="correlation" if f["id"] in CORRELATION_IDS else "signature",
             mitre_list=[f["mitre"]] if f.get("mitre") and f["mitre"] != "-" else [], users=[], hosts=[],
             limitation="Attempt detected from log text; success or impact must be confirmed from responses "
                        "or host telemetry." if f["id"].startswith("web_") else "",
             details={}, notes=[])
    return f


def _evidence_pass(files, findings, e, aliases, tz_hours):
    """Re-read only the referenced records so evidence is exact without keeping everything in memory."""
    need = set()
    for f in findings:
        need.update(f.get("evidence_refs", [])[:60])
        need.update(s.get("ref") for s in f.get("samples", []) if s.get("ref"))
    for u in e["ueba"]["entities"]:
        need.update(r["ref"] for r in u["reasons"] if r.get("ref"))
    got = {}
    if not need:
        return got
    for path, name in files:
        for ev in parsers.iter_events(path, name, tz_hours, aliases):
            if ev["ref"] in need:
                got[ev["ref"]] = {k: ev[k] for k in ("ts", "ref", "file", "line", "user", "target_user", "host",
                                                     "src_host", "src_ip", "dst_ip", "src_port", "dst_port",
                                                     "assigned_ip", "event_id", "logon_type", "process", "command",
                                                     "domain", "url", "action", "bytes_out", "signature",
                                                     "source_type", "raw") if ev.get(k) not in (None, "")}
                if len(got) >= len(need):
                    break
    return got


def _entities(f, evidence):
    users, hosts, ips, ts, srcs = Counter(f.get("users") and {u: 1 for u in f["users"]} or {}), Counter(), Counter(), [], set()
    for h in f.get("hosts", []):
        hosts[norm_host(h)] += 1
    for ip in f.get("ips", []):
        ips[ip] += 1
    for ref in f.get("evidence_refs", [])[:60]:
        ev = evidence.get(ref)
        if not ev:
            continue
        srcs.add(ev.get("source_type"))
        if ev.get("ts"):
            ts.append(ev["ts"])
        for k in ("user", "target_user"):
            if ev.get(k):
                users[str(ev[k]).lower()] += 1
        for k in ("host", "src_host"):
            h = norm_host(ev.get(k))
            if h:
                hosts[h] += 1
        for k in ("src_ip", "dst_ip", "assigned_ip"):
            if ev.get(k):
                ips[ev[k]] += 1
    f["users"] = [u for u, _ in users.most_common(10) if u]
    f["hosts"] = [h for h, _ in hosts.most_common(10) if h]
    f["ips"] = [i for i, _ in ips.most_common(15) if knowledge.valid_ip(i)]
    f["source_types"] = sorted(s for s in srcs if s)
    if ts and not f.get("first_seen"):
        f["first_seen"], f["last_seen"] = _fmt(min(ts)), _fmt(max(ts))


INDEPENDENT = ("TG-TI-", "TG-IDS-", "TG-UEBA-", "TG-STAT-", "TG-FOR-003", "TG-FOR-004")


def _same_conclusion(a, b):
    """Two detections describe the same thing: same category or overlapping ATT&CK techniques.
    Threat intel, sensor alerts and UEBA are independent corroboration and are never folded."""
    if a["rule_id"].startswith(INDEPENDENT) or b["rule_id"].startswith(INDEPENDENT):
        return False
    return a.get("category") == b.get("category") or bool(set(a.get("mitre_list", [])) & set(b.get("mitre_list", [])))


def _dedupe(findings):
    """A finding whose evidence is a subset of an equivalent, at least as severe finding is folded into it."""
    keep = []
    order = sorted(findings, key=lambda f: (SEV_RANK[f["severity"]], -len(f.get("evidence_refs", []))))
    for f in order:
        refs = set(f.get("evidence_refs", []))
        host = next((k for k in keep if refs and refs <= set(k.get("evidence_refs", []))
                     and SEV_RANK[k["severity"]] <= SEV_RANK[f["severity"]] and k["rule_id"] != f["rule_id"]
                     and _same_conclusion(k, f)), None)
        if host:
            host.setdefault("also_matched", []).append(f"{f['rule_id']} {f['title']}")
            for t in f.get("mitre_list", []):
                if t not in host.setdefault("mitre_list", []):
                    host["mitre_list"].append(t)
        else:
            keep.append(f)
    return keep


def _trust_context(findings, inv):
    for f in findings:
        ctx = []
        ts = _parse(f.get("first_seen"))
        for ip in f.get("ips", [])[:10]:
            c = inv.classify(ip, ts)
            ctx.append({"ip": ip, "category": c["category"], "label": c["label"], "trust_class": c["trust_class"],
                        "name": (c.get("entry") or {}).get("name"), "asset_type": c.get("asset_type"),
                        "criticality": c.get("criticality"), "zone": c.get("zone")})
        for h in f.get("hosts", [])[:10]:
            a = inv.host_asset(h)
            if a:
                ctx.append({"host": h, "category": "approved_asset", "label": "Approved server or asset",
                            "trust_class": a["classification"], "name": a["name"], "asset_type": a.get("asset_type"),
                            "criticality": a.get("criticality"), "zone": a.get("zone")})
        f["trust_context"] = ctx
        trusted = [c for c in ctx if c["category"] in ("configured_internal", "approved_asset", "configured_isp")]
        if trusted and SEV_RANK[f["severity"]] <= 1:
            names = ", ".join(sorted({c.get("name") or c.get("ip") or c.get("host") for c in trusted}))[:200]
            note = (f"Involves configured/trusted assets ({names}). Trust is context only - this activity is "
                    f"reported at full severity because the behaviour itself is suspicious.")
            if note not in f["notes"]:
                f["notes"].append(note)


def _alias_map(e, inv, evidence):
    """Entity aliases that genuinely belong together: VPN assigned IP <-> user <-> public IP,
    host name <-> its IP (inventory or observed logons)."""
    pairs = []
    for ip, (user, src, _, _) in e["vpn_assign"].items():
        pairs += [(f"ip:{ip}", f"user:{str(user).lower()}")]
        if src:
            pairs.append((f"ip:{ip}", f"ip:{src}"))
    for host, ips in e["host_ips"].items():
        if len(ips) == 1:
            pairs.append((f"host:{norm_host(host)}", f"ip:{next(iter(ips))}"))
    for a in inv.data["trusted_assets"]:
        if a.get("enabled") and a.get("hostname"):
            pairs.append((f"host:{norm_host(a['hostname'])}", f"ip:{a['ip']}"))
    return pairs


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


# Rules whose user/host entities are the TARGETS of an attack (victims), not the actor.
# They correlate only through the acting source, so e.g. every sprayed account does not
# become part of one incident.
TARGET_RULES = {"TG-AUTH-001", "TG-AUTH-002", "TG-AUTH-003", "TG-AUTH-005", "TG-LNX-002", "TG-LNX-003",
                "TG-LNX-004", "TG-WIN-001", "TG-WIN-002", "TG-NET-001", "TG-NET-007", "TG-WEB-006", "TG-WEB-008"}


def _link_tokens(f):
    d = f.get("details") or {}
    if f["rule_id"] in TARGET_RULES:
        src = d.get("src")
        toks = {f"ip:{src}"} if src else {f"ip:{i}" for i in f.get("ips", [])[:1]}
        return toks
    toks = {f"user:{u}" for u in f.get("users", [])} | {f"host:{h}" for h in f.get("hosts", [])} | \
           {f"ip:{i}" for i in f.get("ips", [])}
    if f["rule_id"] == "TG-AUTH-004" and d.get("account"):
        toks = {f"user:{d['account']}"} | {f"ip:{d['src']}"} if d.get("src") else {f"user:{d['account']}"}
    return toks


def _correlate(findings, alias_pairs):
    """Group findings into incidents through shared actor entities (never by time alone)."""
    # low/info findings (single failed logons etc.) never drive correlation; they stay standalone
    ents = {f["id"]: (_link_tokens(f) if SEV_RANK[f["severity"]] <= 2 else set()) for f in findings}
    freq = Counter(t for toks in ents.values() for t in toks)
    hubs = {t for t, c in freq.items() if c > max(6, 0.5 * len(findings))}
    uf_e = _UF()
    for a, b in alias_pairs:
        if a not in hubs and b not in hubs:
            uf_e.union(a, b)
    clusters = {f["id"]: {uf_e.find(t) for t in toks - hubs} for f in findings for toks in [ents[f["id"]]]}
    uf = _UF()
    by_id = {f["id"]: f for f in findings}
    ids = list(by_id)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if not clusters[a] & clusters[b]:
                continue
            fa, fb = by_id[a], by_id[b]
            sa, sb = _parse(fa.get("first_seen")), _parse(fb.get("first_seen"))
            ea, eb = _parse(fa.get("last_seen")) or sa, _parse(fb.get("last_seen")) or sb
            if sa and sb and (sb - ea > LINK_WINDOW or sa - eb > LINK_WINDOW):
                continue
            uf.union(a, b)
    groups = defaultdict(list)
    for f in findings:
        groups[uf.find(f["id"])].append(f)
    incidents = []
    for members in groups.values():
        if len(members) < 2 and members[0]["severity"] != "critical":
            continue
        members.sort(key=lambda f: _parse(f.get("first_seen")) or datetime.max)
        tactics = []
        for f in members:
            for t in f.get("mitre_list", []):
                tac = rulebook.technique(t)["tactic"]
                if tac and tac not in tactics:
                    tactics.append(tac)
        tactics.sort(key=lambda t: rulebook.TACTIC_ORDER.index(t) if t in rulebook.TACTIC_ORDER else 99)
        # actor accounts only (victims of spraying etc. are listed separately)
        users = Counter(t[5:] for f in members for t in _link_tokens(f) if t.startswith("user:"))
        targeted = sorted({u for f in members if f["rule_id"] in TARGET_RULES for u in f.get("users", [])} - set(users))
        hosts = Counter(t[5:] for f in members for t in _link_tokens(f) if t.startswith("host:"))
        ips = Counter(i for f in members for i in f.get("ips", []))
        starts = [_parse(f.get("first_seen")) for f in members if f.get("first_seen")]
        ends = [_parse(f.get("last_seen")) for f in members if f.get("last_seen")]
        sev = min((f["severity"] for f in members), key=lambda s: SEV_RANK[s])
        sources = sorted({s for f in members for s in f.get("source_types", [])})
        for f in members:
            f["incident_size"] = len(members)
            f["incident_sources"] = sources
        incidents.append({
            "findings": [f["id"] for f in members], "severity": sev, "tactics": tactics,
            "users": [u for u, _ in users.most_common(8)], "hosts": [h for h, _ in hosts.most_common(8)],
            "ips": [i for i, _ in ips.most_common(12)], "first_seen": _fmt(min(starts)) if starts else None,
            "last_seen": _fmt(max(ends)) if ends else None, "source_types": sources,
            "title": _incident_title(members, users, hosts, tactics), "targeted_accounts": targeted[:30],
        })
    incidents.sort(key=lambda i: (SEV_RANK[i["severity"]], -len(i["findings"])))
    for n, inc in enumerate(incidents, 1):
        inc["id"] = f"INC-{n:03d}"
        for f in findings:
            if f["id"] in inc["findings"]:
                f["incident"] = inc["id"]
    return incidents


def _incident_title(members, users, hosts, tactics):
    who = ", ".join(f"'{u}'" for u, _ in users.most_common(2)) or ", ".join(h for h, _ in hosts.most_common(2)) or "multiple entities"
    stages = " → ".join(t for t in tactics if t)[:140]
    return f"Correlated activity involving {who}: {stages or members[0]['title']}"


def _score(f, ueba_by_user, ti_values):
    """Explainable 0-100 incident risk for one finding. Trust never lowers it below the severity base."""
    sev = f["severity"]
    base = SEV_BASE[sev]
    parts = [(f"Severity {sev}", base)]
    conf = int(f.get("confidence", 50))
    if f.get("count", 0) >= 10:
        conf += 5
    if len(f.get("incident_sources", [])) >= 2:
        conf += 10
    conf = max(5, min(99, conf))
    f["confidence"] = conf
    f["confidence_label"] = "High" if conf >= 80 else "Medium" if conf >= 60 else "Low"
    adj = round((conf - 60) / 4)
    if adj:
        parts.append((f"Evidence confidence {conf}%", adj))
    size = f.get("incident_size", 1)
    if size >= 3:
        parts.append((f"Part of an incident with {size} correlated findings", 10))
    elif size == 2:
        parts.append(("Correlated with another finding", 5))
    late = {"Credential Access", "Lateral Movement", "Command and Control", "Exfiltration", "Impact"}
    if any(rulebook.technique(t)["tactic"] in late for t in f.get("mitre_list", [])):
        parts.append(("Late attack stage (credential access, lateral movement, C2, exfiltration or impact)", 5))
    crit = [c for c in f.get("trust_context", []) if c.get("criticality") in ("critical", "high")]
    if crit:
        top = "critical" if any(c["criticality"] == "critical" for c in crit) else "high"
        parts.append((f"Affects a {top}-criticality asset ({crit[0].get('name') or crit[0].get('ip')})",
                       10 if top == "critical" else 5))
    if f["rule_id"].startswith("TG-TI") or any(i.lower() in ti_values for i in f.get("ips", [])):
        parts.append(("Involves a threat-intelligence indicator", 10))
    ueba = max([ueba_by_user.get(u, {}).get("score", 0) for u in f.get("users", [])] + [0])
    f["ueba_score"] = ueba
    if ueba >= 70:
        parts.append((f"Involved account has a high UEBA anomaly score ({ueba})", 5))
    if any(c["category"] in ("public_unknown", "suspicious_indicator") for c in f.get("trust_context", [])):
        parts.append(("Involves an address outside the approved inventory", 5))
    if f.get("details", {}).get("approved_scanner"):
        parts.append(("Source is an approved scanner (contextual adjustment; severity unchanged)", -15))
    score = sum(p for _, p in parts)
    score = max(round(base * 0.6), min(100, score))  # context can never push risk far below the severity base
    f["risk"] = {"score": score, "factors": [{"factor": t, "points": p} for t, p in parts]}
    f["asset_trust"] = sorted({c["label"] for c in f.get("trust_context", [])})


def _incident_score(inc, findings):
    members = [f for f in findings if f["id"] in inc["findings"]]
    top = max(f["risk"]["score"] for f in members)
    n_tac = len(inc["tactics"])
    bonus = 15 if n_tac >= 5 else 10 if n_tac >= 3 else 0
    parts = [("Highest finding risk", top)]
    if bonus:
        parts.append((f"Attack progression across {n_tac} ATT&CK tactics", bonus))
    if len(inc["source_types"]) >= 2:
        parts.append((f"Corroborated by {len(inc['source_types'])} log sources", 5))
    score = min(100, sum(p for _, p in parts))
    inc["risk"] = {"score": score, "factors": [{"factor": t, "points": p} for t, p in parts]}
    high_conf = [f for f in members if f["confidence"] >= 75 and SEV_RANK[f["severity"]] <= 1]
    inc["status"] = "Probable compromise - validate" if n_tac >= 3 and len(high_conf) >= 2 else "Suspected - investigate"
    inc["confidence"] = round(sum(f["confidence"] for f in members) / len(members))


def _register(findings, incidents, evidence):
    """Assign stable evidence IDs (E-0001...) and attach them to findings and incident timelines."""
    reg, ids = [], {}

    def eid(ref):
        if ref not in evidence or ref in ids or len(reg) >= MAX_EVIDENCE:
            return ids.get(ref)
        ev = evidence[ref]
        ids[ref] = f"E-{len(reg) + 1:04d}"
        summary = " ".join(str(x) for x in (
            ev.get("event_id") and f"EventID {ev['event_id']}", ev.get("user") and f"user={ev['user']}",
            ev.get("host") and f"host={ev['host']}", ev.get("src_ip") and f"src={ev['src_ip']}",
            ev.get("dst_ip") and f"dst={ev['dst_ip']}" + (f":{ev['dst_port']}" if ev.get("dst_port") else ""),
            ev.get("command") and f"cmd={str(ev['command'])[:140]}", ev.get("domain") and f"domain={ev['domain']}",
            ev.get("signature") and f"alert={ev['signature']}") if x)
        reg.append({"id": ids[ref], "ref": ref, "ts": _fmt(ev.get("ts")), "source_type": ev.get("source_type"),
                    "summary": summary or str(ev.get("raw", ""))[:160], "raw": str(ev.get("raw", ""))[:700]})
        return ids[ref]

    by_id = {f["id"]: f for f in findings}
    for inc in incidents:
        tl = []
        for fidx in inc["findings"]:
            f = by_id.get(fidx)
            if not f:
                continue
            for ref in f.get("evidence_refs", [])[:4]:
                ev = evidence.get(ref)
                if not ev:
                    continue
                tl.append({"ts": _fmt(ev.get("ts")), "finding": f["title"], "rule_id": f["rule_id"],
                           "tactic": next((rulebook.technique(t)["tactic"] for t in f.get("mitre_list", [])), ""),
                           "summary": _event_line(ev), "evidence": eid(ref)})
        merged = {}
        for t in sorted(tl, key=lambda x: x["ts"] or "9999"):
            m = merged.get(t["evidence"])
            if m is None:
                merged[t["evidence"]] = dict(t, findings=[t["finding"]], rules=[t["rule_id"]])
            elif t["finding"] not in m["findings"]:
                m["findings"].append(t["finding"])
                m["rules"].append(t["rule_id"])
                m["tactic"] = m["tactic"] or t["tactic"]
        for m in merged.values():
            m["finding"] = " + ".join(m["findings"][:3])
        inc["timeline"] = sorted(merged.values(), key=lambda x: x["ts"] or "9999")[:80]
    for f in findings:
        f["evidence"] = [x for x in (eid(r) for r in f.get("evidence_refs", [])[:25]) if x]
        for s in f.get("samples", []):
            s["evidence"] = ids.get(s.get("ref"))
    return reg


def _event_line(ev):
    who = ev.get("user") or ""
    where = norm_host(ev.get("host")) or ""
    net = f"{ev.get('src_ip', '')} -> {ev.get('dst_ip', '')}{':' + str(ev['dst_port']) if ev.get('dst_port') else ''}" \
        if ev.get("dst_ip") else (f"from {ev['src_ip']}" if ev.get("src_ip") else "")
    what = ev.get("command") or ev.get("signature") or ev.get("domain") or (f"EventID {ev['event_id']}" if ev.get("event_id") else "")
    return " ".join(x for x in (who and f"{who}@{where}" if where else who, net, str(what)[:160]) if x).strip()


def _soar(inc, findings):
    """Read-only response checklist. Nothing here is executed by the platform."""
    members = [f for f in findings if f["id"] in inc["findings"]]
    tac = set(inc["tactics"])
    rules_present = {f["rule_id"] for f in members}
    ev = lambda pred: list(dict.fromkeys(x for f in members if pred(f) for x in f.get("evidence", [])[:2]))[:8]
    check = [
        {"step": "Preserve evidence: export the original logs for the incident window and record SHA-256 hashes "
                 "before any cleanup.", "phase": "Investigation", "evidence": []},
        {"step": f"Confirm the timeline {inc.get('first_seen')} - {inc.get('last_seen')} with the system owners of "
                 f"{', '.join(inc['hosts'][:4]) or 'the affected hosts'}.", "phase": "Investigation", "evidence": []},
    ]
    act = []
    if {"Credential Access", "Initial Access"} & tac or rules_present & {"TG-AUTH-004", "TG-AUTH-008", "TG-AUTH-002"}:
        act.append({"action": f"Reset credentials and revoke sessions/tokens for: {', '.join(inc['users'][:6]) or 'affected accounts'}; enforce MFA.",
                    "phase": "Containment", "requires_authorisation": True,
                    "evidence": ev(lambda f: f["category"] in ("Authentication", "Credential Access"))})
    if {"Execution", "Persistence", "Command and Control", "Impact"} & tac:
        act.append({"action": f"Isolate hosts {', '.join(inc['hosts'][:6]) or ''} from the network (EDR/network "
                              "quarantine) after capturing volatile evidence (memory, running processes).",
                    "phase": "Containment", "requires_authorisation": True,
                    "evidence": ev(lambda f: f["category"] in ("Execution", "Impact", "Command and Control"))})
    ext = [c["ip"] for f in members for c in f.get("trust_context", []) if c.get("ip") and
           c["category"] in ("public_unknown", "suspicious_indicator")]
    if ext:
        act.append({"action": f"Block at the perimeter (firewall/proxy/DNS): {', '.join(sorted(set(ext))[:10])}.",
                    "phase": "Containment", "requires_authorisation": True,
                    "evidence": ev(lambda f: any(c.get("ip") in ext for c in f.get("trust_context", [])))})
    if "Persistence" in tac:
        act.append({"action": "Remove persistence created during the incident (new services, scheduled tasks, "
                              "accounts, group memberships) after documenting them.", "phase": "Eradication",
                    "requires_authorisation": True, "evidence": ev(lambda f: f["category"] == "Persistence")})
    if "Lateral Movement" in tac:
        act.append({"action": "Review every host the involved accounts reached; reset local admin passwords (LAPS).",
                    "phase": "Eradication", "requires_authorisation": True,
                    "evidence": ev(lambda f: f["category"] == "Lateral Movement")})
    if {"Exfiltration", "Collection"} & tac:
        act.append({"action": "Identify what data was staged/sent; assess legal and regulatory notification duties "
                              "(e.g. CERT-In requires reporting of notified incidents within 6 hours).",
                    "phase": "Recovery", "requires_authorisation": False,
                    "evidence": ev(lambda f: f["category"] in ("Exfiltration", "Collection"))})
    if "Defense Evasion" in tac:
        check.append({"step": "Logs were cleared or logging was changed: collect copies from the SIEM/central "
                              "collector and restore the audit policy.", "phase": "Investigation",
                      "evidence": ev(lambda f: f["category"] in ("Defense Evasion", "Forensics"))})
    check.append({"step": "Search all log sources for the incident indicators beyond this dataset (see suggested "
                          "queries in the investigation section).", "phase": "Investigation", "evidence": []})
    act.append({"action": "Recover affected systems from known-good images/backups and monitor them closely for "
                          "30 days.", "phase": "Recovery", "requires_authorisation": True, "evidence": []})
    return check, act


def _ip_profiles(findings, inv):
    prof = {}
    for f in findings:
        for ip in f.get("ips", []):
            p = prof.setdefault(ip, {"ip": ip, "events": 0, "activity": set(), "sev": 9, "first": None, "last": None})
            p["events"] += f.get("count", 1)
            p["activity"].add(f["title"][:80])
            p["sev"] = min(p["sev"], SEV_RANK[f["severity"]])
            for k, v in (("first", f.get("first_seen")), ("last", f.get("last_seen"))):
                if v:
                    p[k] = min(p[k] or v, v) if k == "first" else max(p[k] or v, v)
    out = []
    for ip, p in prof.items():
        c = inv.classify(ip)
        sev = SEV[min(p["sev"], 4)]
        internal = c["category"] in ("configured_internal", "approved_asset", "other_private", "loopback_linklocal")
        verdict = ("Affected internal asset" if internal and sev in ("critical", "high") else
                   "Malicious" if sev in ("critical", "high") else "Suspicious" if sev == "medium" else "Noisy")
        out.append({"ip": ip, "public": not internal, "events": p["events"], "severity": sev, "verdict": verdict,
                    "activity": sorted(p["activity"])[:8], "first_seen": p["first"], "last_seen": p["last"],
                    "classification": c["label"], "trust_class": trust.TRUST_CLASSES.get(c["trust_class"], ""),
                    "asset": (c.get("entry") or {}).get("name")})
    out.sort(key=lambda x: (SEV_RANK[x["severity"]], -x["events"]))
    return out[:60]


def _iocs(d, findings, e, inv):
    i = d["iocs"]
    ext = set()
    for f in findings:
        if SEV_RANK[f["severity"]] > 2:
            continue
        for c in f.get("trust_context", []):
            if c.get("ip") and c["category"] in ("public_unknown", "suspicious_indicator"):
                ext.add(c["ip"])
    doms = set(i.get("domains", []))
    for f in findings:
        if f["rule_id"] in ("TG-DNS-001", "TG-DNS-002") and f.get("details", {}).get("domain"):
            doms.add(f["details"]["domain"])
    for m in e["ti_matches"]:
        (ext if m["type"] == "ip" else doms).add(m["value"]) if m["type"] in ("ip", "domain") else None
    return {"ips": sorted(ext), "urls": i.get("urls", []), "domains": sorted(doms)[:50], "files": i.get("files", []),
            "users": sorted({u for f in findings if SEV_RANK[f["severity"]] <= 1 for u in f.get("users", [])})[:20],
            "hashes": sorted(m["value"] for m in e["ti_matches"] if m["type"] == "hash")}


def _timeline(evidence, findings):
    stamps = [ev["ts"] for ev in evidence.values() if ev.get("ts")]
    for f in findings:
        if not f.get("evidence_refs") and f.get("first_seen"):
            stamps.append(_parse(f["first_seen"]))
    stamps = [s for s in stamps if s]
    if not stamps:
        return [], "hour"
    span_h = (max(stamps) - min(stamps)).total_seconds() / 3600
    if span_h <= 3:
        bucket, keys = "5 min", [s.replace(minute=s.minute - s.minute % 5).strftime("%Y-%m-%d %H:%M") for s in stamps]
    elif span_h <= 72:
        bucket, keys = "hour", [s.strftime("%Y-%m-%d %H:00") for s in stamps]
    else:
        bucket, keys = "day", [s.strftime("%Y-%m-%d") for s in stamps]
    return sorted(Counter(keys).items()), bucket


def _attack_map(findings):
    agg = {}
    for f in findings:
        for t in f.get("mitre_list", []):
            meta = rulebook.technique(t)
            a = agg.setdefault(t, {"technique": t, "name": meta["name"], "tactic": meta["tactic"], "url": meta["url"],
                                   "findings": [], "events": 0})
            a["findings"].append(f.get("fid") or f["id"])
            a["events"] += f.get("count", 1)
    return sorted(agg.values(), key=lambda a: (rulebook.TACTIC_ORDER.index(a["tactic"])
                                               if a["tactic"] in rulebook.TACTIC_ORDER else 99, a["technique"]))


def _time_range(ingestion):
    s = [i["time_range"]["start"] for i in ingestion if i["time_range"]["start"]]
    e = [i["time_range"]["end"] for i in ingestion if i["time_range"]["end"]]
    return {"start": min(s) if s else None, "end": max(e) if e else None}


TELEMETRY_NEEDS = [
    ("process", "Process creation with command lines (Windows 4688 + command-line auditing, Sysmon 1, auditd execve)",
     "Malware execution, credential dumping, LOLBin and ransomware-preparation findings cannot be validated."),
    ("auth", "Authentication logs (Windows 4624/4625, Linux auth.log, VPN)",
     "Brute force, spraying, account takeover and UEBA cannot be assessed."),
    ("network", "Firewall / flow logs with bytes and ports",
     "Port scans, beaconing (C2) and exfiltration volume cannot be assessed."),
    ("dns", "DNS query logs", "DNS tunnelling and DGA/C2 domain lookups cannot be assessed."),
    ("edr", "EDR telemetry (file, registry, process tree)",
     "File encryption, persistence artefacts and exact malware behaviour cannot be confirmed."),
    ("web", "Web server / proxy logs with status codes", "Web exploitation success and API abuse cannot be assessed."),
]


def _limitations(out, e, ingestion, inv, iocs):
    lim = []
    tel = e["telemetry"]
    for key, need, impact in TELEMETRY_NEEDS:
        if not tel.get(key):
            lim.append({"area": "Missing telemetry", "detail": f"No {need} in the uploaded data.", "impact": impact})
    for i in ingestion:
        if i["parse_failures"]:
            lim.append({"area": "Parsing", "detail": f"{i['file']}: {i['parse_failures']} record(s) could not be parsed.",
                        "impact": "Events in those records were not analysed."})
        if i["no_timestamp"]:
            lim.append({"area": "Timestamps", "detail": f"{i['file']}: {i['no_timestamp']} event(s) without a usable timestamp.",
                        "impact": "They are excluded from time-window correlation and timelines."})
        if any(z.startswith("not stated") for z in i["timezones"]):
            lim.append({"area": "Time zone", "detail": f"{i['file']}: timestamps have no time zone; UTC was assumed.",
                        "impact": "Cross-source timelines may be offset if the source used local time."})
    if not inv.enabled_count:
        lim.append({"area": "Trust context", "detail": "No trusted networks or assets are configured.",
                    "impact": "Internal/external context, asset criticality and policy checks are limited."})
    if not sum(len(v) for v in iocs.values()):
        lim.append({"area": "Threat intelligence", "detail": "No IoC feeds were loaded (config/ioc/).",
                    "impact": "Known-bad indicators cannot be matched."})
    thin = [u["entity"] for u in out["ueba"]["entities"] if u.get("insufficient_history")]
    if thin:
        lim.append({"area": "UEBA baseline", "detail": f"{len(thin)} account(s) have little history "
                    f"({', '.join(thin[:8])}).", "impact": "Behavioural scores for these accounts are less reliable."})
    lim.append({"area": "Scope", "detail": "Analysis is limited to the uploaded records; activity on systems or "
                "time ranges not included cannot be assessed.", "impact": "Absence of evidence is not evidence of absence."})
    return lim


def _coverage(tel):
    cats = [("Authentication & UEBA", "auth"), ("Process / endpoint", "process"), ("Network / firewall", "network"),
            ("DNS", "dns"), ("IDS / EDR alerts", "ids"), ("Web / API", "web"), ("VPN", "vpn"), ("Windows", "windows")]
    return [{"area": name, "events": tel.get(k, 0), "available": bool(tel.get(k))} for name, k in cats]


def _update_baselines(baselines, history, incidents, findings):
    """Learn baselines only from accounts that are not part of an incident or high finding."""
    tainted = {t[5:] for f in findings if SEV_RANK[f["severity"]] <= 1 for t in _link_tokens(f) if t.startswith("user:")}
    tainted |= {u for i in incidents for u in i["users"]}
    changed = False
    for user, h in history.items():
        if user in tainted:
            continue
        b = baselines.setdefault(user, {"logons": 0, "hours": {}, "ips": [], "hosts": [], "first_seen": h["first_seen"]})
        b["logons"] = max(b.get("logons", 0), h["logons"])
        for k, v in h["hours"].items():
            b["hours"][k] = max(b["hours"].get(k, 0), v)
        b["ips"] = sorted(set(b.get("ips", [])) | set(h["ips"]))[:50]
        b["hosts"] = sorted(set(b.get("hosts", [])) | set(h["hosts"]))[:100]
        changed = True
    if changed:
        config_store.save_json(BASELINE_FILE, baselines)


def to_json(result):
    return json.loads(json.dumps(result, default=lambda o: _fmt(o) if isinstance(o, datetime) else list(o)
                                 if isinstance(o, (set, tuple)) else str(o)))
