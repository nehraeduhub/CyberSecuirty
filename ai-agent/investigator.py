"""AI investigation agent: case file, deterministic investigation, prompt and answer validation.

Hybrid design:
  - The Python engine produces facts (findings, incidents, evidence IDs, trust context).
  - investigate() turns those facts into an investigation WITHOUT any AI: attack narrative,
    hypotheses, benign explanations, evidence gaps, read-only follow-up queries. This is what
    the report uses when no local model is available.
  - case_file() gives the local model a compact, structured view of the same facts, and
    validate() checks the model's answer: every evidence ID it cites must exist, and it must
    not upgrade a suspected incident to "confirmed".

The agent never executes commands, never changes infrastructure and never sends data out.
Suggested queries are text for an analyst to review and run.
"""
import re
from datetime import datetime, timedelta, timezone

import rules as rulebook

AGENT_RULES = """You are the investigation agent of an offline SOC platform. You receive FACTS produced by a
deterministic detection engine. Rules you must follow:
1. Use only the facts below. Never invent events, hosts, users, IPs, times or evidence.
2. Support every substantive statement with evidence IDs in square brackets, e.g. [E-0012].
   Only cite IDs that appear in the facts.
3. Status words: "suspected" or "probable". Do not call an incident "confirmed" - only a human
   analyst can confirm after validation.
4. Trusted / internal / ISP addresses are context, not proof of safety. A trusted asset that
   behaves suspiciously is still suspicious.
5. Say what is missing: when telemetry needed to prove something is absent, state it.
6. You cannot run tools. Do not claim you ran queries or checked systems; you may SUGGEST
   read-only queries for the analyst.
7. Be concise and technical."""

INVESTIGATE_PROMPT = ("Investigate the case. Answer with these sections:\n"
                      "Start with a 2-4 sentence executive summary paragraph (no heading).\n"
                      "## Attack narrative - chronological bullets, each with evidence IDs\n"
                      "## Attack flow - the path (source > firewall/VPN > server/machine > URL/path or command) and "
                      "what each device did (allowed, blocked, served, executed), only as logged in the attack flow\n"
                      "## Assessment - per incident: status (suspected/probable), confidence and why\n"
                      "## Benign explanations to rule out\n"
                      "## Evidence gaps and suggested read-only queries\n"
                      "## Priority actions (recommendations only)")


def _ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def case_file(result, budget_chars=7000):
    """Compact, structured facts for the local model (sized for a 4K-8K context window)."""
    out = []
    ing = result.get("ingestion") or []
    if ing:
        out.append("DATA: " + "; ".join(f"{i['file']} ({i['format']}, {i['events']} events, "
                                         f"{'/'.join(i['probable_source'][:2])})" for i in ing[:8]))
        missing = sorted({f for i in ing for f in i.get("fields_unavailable", [])} -
                         {f for i in ing for f in i.get("fields_available", {})})
        if missing:
            out.append("Fields not present in any source: " + ", ".join(missing[:12]))
    tr = result.get("time_range") or {}
    out.append(f"TIME RANGE: {tr.get('start')} to {tr.get('end')} (UTC). Overall risk {result.get('risk_score')}/100.")
    trust = result.get("trust") or {}
    out.append("TRUSTED INVENTORY:\n" + (trust.get("summary") or "not configured")[:900])
    rep = result.get("reputation") or {}
    if rep:
        out.append("\nEXTERNAL REPUTATION (looked up by the analyst; context only):")
        order = {"malicious": 0, "suspicious": 1}
        for r in sorted(rep.values(), key=lambda r: order.get(r.get("verdict"), 5))[:12]:
            out.append(f"- {r['value']}: {r.get('verdict')} ({r.get('summary', '')[:120]})")
    mem = result.get("memory") or {}
    if mem.get("verdicts") or mem.get("seen_before"):
        out.append("\nORGANISATION MEMORY (earlier analyst verdicts and sightings - use them, but verify they still apply):")
        for v in mem.get("verdicts", [])[:10]:
            out.append(f"- {v['finding']} {v['rule_id']} on {v['entity']}: analyst said {v['verdict'].replace('_', ' ')}"
                       f" on {str(v.get('time', ''))[:10]}" + (f" - {v['note'][:120]}" if v.get("note") else ""))
        for x in mem.get("seen_before", [])[:10]:
            out.append(f"- {x['value']} seen in {x['count']} earlier analysis(es), last {str(x['last'])[:10]}"
                       + (f" ({x['last_name'][:50]})" if x.get("last_name") else ""))
    by_fid = {f.get("fid"): f for f in result.get("findings", [])}
    for inc in (result.get("incidents") or [])[:4]:
        out.append(f"\n{inc['id']} [{inc['severity']}] risk {inc['risk']['score']} status '{inc['status']}' "
                   f"tactics: {' > '.join(inc['tactics'])}\n  actors: {', '.join(inc['users'][:6])}; hosts: "
                   f"{', '.join(inc['hosts'][:6])}; findings: {', '.join(inc.get('finding_ids', [])[:20])}")
        if inc.get("targeted_accounts"):
            out.append(f"  accounts targeted (not necessarily compromised): {', '.join(inc['targeted_accounts'][:10])}")
        if inc.get("attack_path"):
            out.append(f"  attack path (systems in evidence order): {inc['attack_path'][:300]}")
        steps = inc.get("flow") or []
        if steps:
            out.append("  attack flow (source > device > target | object | ACTION the device logged | evidence):")
            for x in steps[:16]:
                hop = " > ".join(v for v in (x.get("from") or ",".join(x.get("users") or []), x.get("via"), x.get("to")) if v)
                out.append(f"   {x['step']}. {(x.get('first') or '?')[11:]} {x.get('stage') or 'Alert'}: {hop[:110]}"
                           f" | {x.get('object', '')[:80]} | {x.get('action', '')[:80]} | {','.join(x.get('evidence', [])[:3])}")
        out.append("  timeline (repeated rows collapsed):")
        for t in _collapse(inc.get("timeline", []))[:8 if steps else 24]:
            out.append(f"   {t['when']} [{t['evidence']}] {t['tactic'] or 'Alert'}: {t['finding'][:70]} | "
                       f"{t['summary'][:90]}" + (f" | {t['action'][:50]}" if t.get("action") else "")
                       + (f" (x{t['n']})" if t["n"] > 1 else ""))
    out.append("\nFINDINGS (id rule severity/confidence/risk: title | trust context | evidence):")
    for f in result.get("findings", [])[:30]:
        ctx = "; ".join(sorted({(c.get("name") or c.get("ip") or c.get("host") or "") + " = " + c["label"]
                                for c in f.get("trust_context", [])[:3]}))
        out.append(f"- {f.get('fid')} {f['rule_id']} {f['severity']}/{f['confidence']}%/{f['risk']['score']}: "
                   f"{f['title'][:80]} | {ctx[:140] or 'no inventory match'} | {', '.join(f.get('evidence', [])[:3])}"
                   + (f" | note: {f['notes'][0][:120]}" if f.get("notes") else ""))
    ueba = (result.get("ueba") or {}).get("entities", [])
    if ueba:
        out.append("\nUEBA (score: reasons):")
        for u in ueba[:5]:
            if u["score"]:
                out.append(f"- {u['entity']} {u['score']}{' (thin baseline)' if u.get('insufficient_history') else ''}: "
                           + "; ".join(r["text"][:100] for r in u["reasons"][:4]))
    lim = result.get("limitations") or []
    if lim:
        out.append("\nLIMITATIONS: " + " | ".join(l["detail"][:110] for l in lim[:6]))
    text = "\n".join(out)
    return text if len(text) <= budget_chars else text[:budget_chars] + "\n[case file truncated]"


def _collapse(timeline):
    """Consecutive rows of the same finding become one row with a time range and count."""
    out = []
    for t in timeline:
        if out and out[-1]["finding"] == t["finding"]:
            o = out[-1]
            o["n"] += 1
            o["last"] = t["ts"]
            o["when"] = f"{o['first'][11:] if o['first'] else '?'}-{t['ts'][11:] if t.get('ts') else '?'}"
            if t["evidence"] not in o["evidence"]:
                o["evidence"] = o["evidence"].split(",")[0] + f",..,{t['evidence']}"
            continue
        out.append(dict(t, n=1, first=t["ts"], when=t["ts"][11:] if t.get("ts") else "?"))
    return out


def investigate(result):
    """Deterministic investigation of the engine output (works with no AI available)."""
    findings = result.get("findings", [])
    by_id = {f["id"]: f for f in findings}
    incidents = result.get("incidents") or []
    inv = {"incidents": [], "uncorrelated": [], "generated": datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S"),
           "method": "deterministic"}
    for inc in incidents:
        members = [by_id[x] for x in inc["findings"] if x in by_id]
        story, seen = [], {}
        for t in inc.get("timeline", []):
            key = t["tactic"] or "Alert"
            k = (key, t["finding"][:40])
            if k in seen:  # same step again: only add what the device did differently
                st = seen[k]
                if t.get("action"):
                    st["_acts"][t["action"]] = st["_acts"].get(t["action"], 0) + 1
                continue
            seen[k] = {"ts": t["ts"], "stage": key, "text": t["finding"], "detail": t["summary"],
                       "action_by": t.get("action_by", ""), "evidence": [t["evidence"]],
                       "_acts": {t["action"]: 1} if t.get("action") else {}}
            story.append(seen[k])
        for st in story:
            acts = st.pop("_acts")
            st["action"] = "; ".join(a + (f" x{n}" if n > 1 else "") for a, n in acts.items())
        story = story[:25]
        hyps = _hypotheses(inc, members)
        benign = []
        for f in sorted(members, key=lambda f: -f["risk"]["score"])[:6]:
            if f.get("fp"):
                benign.append({"finding": f.get("fid"), "explanation": f["fp"],
                               "how_to_rule_out": _rule_out(f)})
        gaps = _gaps(members, result)
        inv["incidents"].append({
            "id": inc["id"], "title": inc["title"], "status": inc["status"], "risk": inc["risk"]["score"],
            "confidence": inc["confidence"], "story": story, "hypotheses": hyps, "benign": benign,
            "gaps": gaps, "queries": _queries(inc), "validation_steps": _validation(inc, members),
        })
    inv["uncorrelated"] = [{"finding": f.get("fid"), "title": f["title"], "severity": f["severity"],
                            "risk": f["risk"]["score"], "evidence": f.get("evidence", [])[:3]}
                           for f in findings if not f.get("incident")][:20]
    inv["summary"] = executive_summary(result, inv)
    return inv


def _hypotheses(inc, members):
    rules_present = {f["rule_id"] for f in members}
    ev = lambda *rids: [e for f in members if f["rule_id"] in rids for e in f.get("evidence", [])[:2]][:4]
    hyps = []
    acct = [f for f in members if f["rule_id"] in ("TG-AUTH-004", "TG-AUTH-008")]
    if acct:
        a = acct[0]
        hyps.append({"statement": f"Account takeover: {a['title']}.", "status": "probable",
                     "evidence": ev("TG-AUTH-004", "TG-AUTH-008", "TG-AUTH-002")})
    if rules_present & {"TG-EXE-001", "TG-EXE-007", "TG-CRED-001", "TG-CRED-002"}:
        hyps.append({"statement": "Hands-on-keyboard post-exploitation on "
                                  f"{', '.join(sorted({h for f in members if f['category'] in ('Execution', 'Credential Access') for h in f.get('hosts', [])})) or 'the affected host'}"
                                  " (download cradle and/or credential theft).", "status": "probable",
                     "evidence": ev("TG-EXE-001", "TG-EXE-007", "TG-CRED-001", "TG-CRED-002")})
    if rules_present & {"TG-C2-001", "TG-DNS-001", "TG-DNS-002"}:
        hyps.append({"statement": "Active command-and-control channel from the compromised host.",
                     "status": "suspected", "evidence": ev("TG-C2-001", "TG-DNS-001", "TG-DNS-002", "TG-IDS-001")})
    if "TG-LAT-001" in rules_present:
        hyps.append({"statement": "Stolen privileged credentials used for lateral movement.", "status": "probable",
                     "evidence": ev("TG-LAT-001", "TG-UEBA-001")})
    if rules_present & {"TG-EXF-001", "TG-DB-001", "TG-EXF-002"}:
        hyps.append({"statement": "Data staged and transferred out of the network. Volume and timing are "
                                  "consistent with exfiltration; content is not visible in these logs.",
                     "status": "suspected", "evidence": ev("TG-DB-001", "TG-EXF-002", "TG-EXF-001")})
    if rules_present & {"TG-MAL-001"}:
        hyps.append({"statement": "Preparation for ransomware (recovery inhibition). No file-encryption "
                                  "telemetry is present to show whether encryption happened.",
                     "status": "suspected", "evidence": ev("TG-MAL-001")})
    if rules_present & {"TG-FOR-001", "TG-FOR-005", "TG-FOR-006"}:
        hyps.append({"statement": "Anti-forensics: audit policy changed and/or logs cleared; later activity may "
                                  "be missing from the logs.", "status": "probable",
                     "evidence": ev("TG-FOR-001", "TG-FOR-005", "TG-FOR-006")})
    if not hyps:
        top = max(members, key=lambda f: f["risk"]["score"])
        hyps.append({"statement": f"Related suspicious activity centred on: {top['title']}.", "status": "suspected",
                     "evidence": top.get("evidence", [])[:3]})
    return hyps


def _rule_out(f):
    m = {
        "Authentication": "Ask the account owner whether they logged on at that time and from that address.",
        "Execution": "Check the process tree and file hash in EDR; confirm whether an admin ran the command.",
        "Command and Control": "Identify the process behind the connections on the source host; check the destination's reputation and ownership.",
        "Exfiltration": "Confirm with the system owner whether a backup or sync job was scheduled at that time.",
        "Reconnaissance": "Check whether the scan matches an approved scan window and scope.",
        "Lateral Movement": "Ask the account owner/administrator whether these logons were planned work.",
        "Persistence": "Compare the new service/task/account with change-management records.",
        "Threat Intelligence": "Check the feed entry's date and confidence; shared hosting can cause false matches.",
    }
    return m.get(f.get("category"), "Validate the activity with the system owner and change records.")


def _gaps(members, result):
    gaps = []
    tel = result.get("telemetry", {})
    cats = {f["category"] for f in members}
    if {"Command and Control", "Exfiltration"} & cats and not tel.get("edr"):
        gaps.append("No EDR/process-network telemetry: the process that opened the C2/exfiltration connections "
                    "is not identified.")
    if {"Exfiltration", "Collection"} & cats:
        gaps.append("Logs show volumes and commands, not file contents: what data left the network must be "
                    "established from the archive/export itself.")
    if "Impact" in cats and not tel.get("edr"):
        gaps.append("No file-system telemetry: whether files were encrypted cannot be determined.")
    if any(f["rule_id"] in ("TG-FOR-001", "TG-FOR-005") for f in members):
        gaps.append("Logs were cleared or audit policy changed on at least one host: events after that point may "
                    "be missing; use the SIEM's copy.")
    for l in result.get("limitations", []):
        if l["area"] == "Missing telemetry" and len(gaps) < 6:
            gaps.append(l["detail"] + " " + l["impact"])
    return gaps


def _window(inc, before=60, after=60):
    s, e = _ts(inc.get("first_seen")), _ts(inc.get("last_seen"))
    if not s:
        return None, None
    return s - timedelta(minutes=before), (e or s) + timedelta(minutes=after)


def _queries(inc):
    """Read-only follow-up searches for the analyst to run in their SIEM (never executed here)."""
    s, e = _window(inc)
    q = []
    ips = [i for i in inc.get("ips", [])[:5]]
    users = inc.get("users", [])[:4]
    hosts = inc.get("hosts", [])[:4]
    if ips:
        ip_or = " OR ".join(f'"{i}"' for i in ips)
        q.append({"purpose": "All activity of the incident IP addresses beyond the uploaded files",
                  "splunk": f'index=* ({ip_or}) earliest="{s:%m/%d/%Y:%H:%M:%S}" latest="{e:%m/%d/%Y:%H:%M:%S}" '
                            f'| stats count min(_time) max(_time) by sourcetype, src_ip, dest_ip' if s else
                            f'index=* ({ip_or}) | stats count by sourcetype, src_ip, dest_ip',
                  "kql": "union * | where " + (f"TimeGenerated between (datetime({s:%Y-%m-%dT%H:%M:%SZ}) .. "
                                               f"datetime({e:%Y-%m-%dT%H:%M:%SZ})) and " if s else "")
                         + "(" + " or ".join(f'* has "{i}"' for i in ips) + ")",
                  "grep": "grep -rnE '" + "|".join(re.escape(i) for i in ips) + "' /var/log/"})
    if users:
        u_or = " OR ".join(f'user="{u}"' for u in users)
        q.append({"purpose": "Every logon, privilege use and process started by the involved accounts",
                  "splunk": f"index=wineventlog ({u_or}) EventCode IN (4624,4625,4648,4672,4688,4720,4732) "
                            f"| table _time host EventCode user src_ip Logon_Type CommandLine",
                  "kql": "SecurityEvent | where Account has_any (" + ", ".join(f'"{u}"' for u in users) +
                         ") | where EventID in (4624,4625,4648,4672,4688,4720,4732) | project TimeGenerated, Computer, "
                         "EventID, Account, IpAddress, LogonType, CommandLine"})
    if hosts:
        q.append({"purpose": "Process creation and service/task changes on the affected hosts",
                  "splunk": "index=* (" + " OR ".join(f'host="{h}"' for h in hosts) + ") (EventCode=4688 OR "
                            "EventCode=7045 OR EventCode=4698 OR EventCode=1) | table _time host user "
                            "ParentProcessName NewProcessName CommandLine",
                  "kql": "DeviceProcessEvents | where DeviceName has_any (" + ", ".join(f'"{h}"' for h in hosts) +
                         ") | project Timestamp, DeviceName, AccountName, InitiatingProcessFileName, FileName, "
                         "ProcessCommandLine"})
    return q


def _validation(inc, members):
    steps = []
    hosts = ", ".join(inc.get("hosts", [])[:4])
    if any(f["category"] in ("Execution", "Credential Access", "Impact") for f in members):
        steps.append(f"Collect EDR process trees / memory from {hosts or 'affected hosts'} for the incident window "
                     "(read-only collection).")
    if any(f["category"] in ("Command and Control", "Exfiltration") for f in members):
        steps.append("Pull full flow/proxy records for the external destinations to establish total data volume "
                     "and first contact time.")
    steps.append("Interview the owners of the actor accounts to separate authorised activity from the attacker's.")
    steps.append("Check change-management records for the account, group, service and firewall changes.")
    return steps


def executive_summary(result, inv=None):
    incs = result.get("incidents") or []
    f = result.get("findings") or []
    crit = sum(1 for x in f if x["severity"] == "critical")
    high = sum(1 for x in f if x["severity"] == "high")
    tr = result.get("time_range") or {}
    parts = [f"Analysis of {result.get('lines', 0):,} events from {len(result.get('ingestion') or [])} log source(s) "
             f"covering {tr.get('start') or '?'} to {tr.get('end') or '?'} (UTC) produced {len(f)} findings "
             f"({crit} critical, {high} high), grouped into {len(incs)} incident(s)."]
    if incs:
        i = incs[0]
        parts.append(f"The most significant, {i['id']} ({i['status'].lower()}, risk {i['risk']['score']}/100), "
                     f"involves {', '.join(i['users'][:3]) or ', '.join(i['hosts'][:3]) or 'several entities'} and "
                     f"spans {len(i['tactics'])} ATT&CK tactics: {', '.join(i['tactics'][:6])}.")
    if not (result.get("trust") or {}).get("configured"):
        parts.append("No trusted network inventory was configured, so internal/external context is limited.")
    parts.append("All conclusions are based on log evidence referenced by evidence IDs and require analyst "
                 "validation before containment decisions.")
    return " ".join(parts)


EVIDENCE_RE = re.compile(r"\bE-\d{4}\b")


def validate(text, result):
    """Check an AI answer against the facts. Returns the answer plus warnings (never silently edits it)."""
    known = {e["id"] for e in result.get("evidence", [])}
    cited = set(EVIDENCE_RE.findall(text or ""))
    unknown = sorted(cited - known)
    warnings = []
    if unknown:
        warnings.append(f"The AI cited evidence IDs that do not exist: {', '.join(unknown[:10])}. Treat those "
                        "statements as unverified.")
    if not cited and result.get("evidence"):
        warnings.append("The AI answer cites no evidence IDs; verify its statements against the findings.")
    if re.search(r"\bconfirmed (compromise|breach|incident|exfiltration|ransomware)|\bis confirmed\b", text or "", re.I):
        warnings.append("The AI used the word 'confirmed'. The engine's status is 'suspected/probable' until an "
                        "analyst validates it.")
    if re.search(r"\bI (ran|executed|checked|queried|blocked|disabled)\b", text or "", re.I):
        warnings.append("The AI claims to have performed an action. It cannot execute tools; no action was taken.")
    return {"cited": sorted(cited & known), "unknown": unknown, "warnings": warnings}


def validation_footer(v):
    if not v["warnings"]:
        return f"\n\n---\n_Evidence check: {len(v['cited'])} evidence reference(s) cited, all verified against the engine output._"
    return "\n\n---\n**Evidence check:** " + " ".join(v["warnings"])
