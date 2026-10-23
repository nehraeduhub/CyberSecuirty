"""What the agent learns from your data (stored in data/, removable at any time from the History page).

The local AI model itself is not re-trained: fine-tuning on a CPU-only server is impractical, and
weights trained on attacker-controlled log text could be poisoned. Instead the tool keeps an
explicit, reviewable memory that every new analysis and every AI investigation uses:

1. Analyst verdicts - you mark a finding true positive / false positive / benign (expected). The
   same rule on the same entity in later analyses shows your verdict and note, and its confidence
   and risk move accordingly. Severity is never changed and nothing is ever hidden.
2. Learned indicators - public IPs, domains, URLs and hashes from findings you confirmed as true
   positives, and indicators that AbuseIPDB / VirusTotal rated malicious, become a local IoC feed
   (data/learned_iocs.csv). Later logs that contain them raise a threat-intel finding, offline.
3. Sightings - indicators seen in earlier analyses ("203.0.113.50 was seen in 2 earlier analyses,
   last on ...") are shown in the attacker profiles and given to the AI.
4. UEBA baselines - per-account behaviour (already learned by pipeline.py).

All of it is added to the AI case file as ORGANISATION MEMORY, so the local model answers with
what your team already knows.
"""
import csv
import io
import ipaddress
import threading

import config_store
import trust

FEEDBACK = "feedback.json"
SIGHTINGS = "sightings.json"
LEARNED = "learned_iocs.csv"
VERDICTS = {"true_positive": "True positive", "false_positive": "False positive", "benign": "Benign / expected"}
_lock = threading.RLock()


def _path(name):
    return config_store.DATA_DIR / name


def _load(name, default):
    d, _ = config_store.load_json(_path(name), default)
    return d if isinstance(d, type(default)) else default


def _save(name, data):
    config_store.ensure_dirs()
    config_store.save_json(_path(name), data)


def _public(v):
    try:
        ip = ipaddress.ip_address(str(v))
    except ValueError:
        return False
    return not (trust.is_private_ip(str(v)) or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_unspecified)


def entity(f):
    """The entity a verdict is about: the main external IP, else the account, else the host."""
    ips = f.get("ips") or []
    pub = [i for i in ips if _public(i)]
    for group in (pub, ips, f.get("users") or [], f.get("hosts") or []):
        if group:
            return str(group[0]).lower()
    return ""


def key(f):
    return f"{f.get('rule_id') or f.get('id')}|{entity(f)}"


# ------------------------------------------------------------------ analyst verdicts

def record_verdict(f, verdict, note, actor, analysis_id=None, result=None):
    if verdict not in VERDICTS and verdict != "clear":
        raise ValueError("verdict must be true_positive, false_positive, benign or clear")
    k = key(f)
    with _lock:
        fb = _load(FEEDBACK, {})
        before = fb.get(k)
        if verdict == "clear":
            fb.pop(k, None)
        else:
            fb[k] = {"key": k, "rule_id": f.get("rule_id"), "entity": entity(f), "title": str(f.get("title", ""))[:160],
                     "verdict": verdict, "note": str(note or "")[:500], "actor": actor, "time": config_store.now_iso(),
                     "analysis_id": analysis_id,
                     "indicators": _indicators(f, result) if verdict == "true_positive" else []}
        _save(FEEDBACK, fb)
        _write_learned()
    config_store.audit(actor, "learning", "verdict" if verdict != "clear" else "verdict_clear", k,
                       {"verdict": before.get("verdict")} if before else None,
                       {"verdict": verdict, "note": str(note or "")[:200]} if verdict != "clear" else None)
    return fb.get(k)


def _indicators(f, result=None):
    """Public IPs of the finding, plus the URLs / domains / hashes of the analysis that occur in its evidence."""
    out = [("ip", ip) for ip in f.get("ips") or [] if _public(ip)]
    text = " ".join(str(s.get("text", "")) for s in f.get("samples") or [])
    if result:
        refs = set(f.get("evidence") or [])
        text += " " + " ".join(str(e.get("raw", "")) for e in result.get("evidence") or [] if e.get("id") in refs)
        i = result.get("iocs") or {}
        for k, t in (("urls", "url"), ("domains", "domain"), ("hashes", "hash")):
            out += [(t, v) for v in (i.get(k) or []) if v and v in text]
    seen, uniq = set(), []
    for t, v in out:
        if v.lower() not in seen:
            seen.add(v.lower())
            uniq.append({"type": t, "value": v})
    return uniq[:20]


def verdicts():
    return sorted(_load(FEEDBACK, {}).values(), key=lambda v: v.get("time", ""), reverse=True)


def forget(k, actor):
    with _lock:
        fb = _load(FEEDBACK, {})
        if fb.pop(k, None) is None:
            return False
        _save(FEEDBACK, fb)
        _write_learned()
    config_store.audit(actor, "learning", "forget", k, None, None)
    return True


# ------------------------------------------------------------------ reputation-learned indicators

def learn_reputation(res, actor):
    """Indicators rated malicious by AbuseIPDB / VirusTotal join the local IoC feed."""
    if res.get("verdict") != "malicious":
        return False
    with _lock:
        rep = _load("learned_reputation.json", {})
        rep[res["value"]] = {"type": res["type"], "value": res["value"], "summary": res.get("summary", ""),
                             "time": config_store.now_iso(), "actor": actor}
        _save("learned_reputation.json", rep)
        _write_learned()
    return True


def learned_indicators():
    rows = {}
    for fbk in _load(FEEDBACK, {}).values():
        if fbk.get("verdict") != "true_positive":
            continue
        for i in fbk.get("indicators") or []:
            rows[(i["type"], i["value"].lower())] = {"type": i["type"], "value": i["value"], "source": "LOCAL-VERDICT",
                                                     "description": f"Confirmed by {fbk.get('actor')} on "
                                                                    f"{fbk.get('time', '')[:10]}: {fbk.get('title', '')}"[:200]}
    for r in _load("learned_reputation.json", {}).values():
        rows.setdefault((r["type"], r["value"].lower()), {"type": r["type"], "value": r["value"],
                                                          "source": "LOCAL-REPUTATION",
                                                          "description": r.get("summary", "")[:200]})
    # the analyst's most recent verdict on an entity decides: a newer false-positive / benign verdict on an IP
    # removes it from the feed, a newer true-positive verdict puts it back
    latest = {}
    for fb in sorted(_load(FEEDBACK, {}).values(), key=lambda v: v.get("time", "")):
        latest[(fb.get("entity") or "").lower()] = fb.get("verdict")
    return [r for k, r in rows.items() if latest.get(k[1]) in (None, "true_positive")]


def _write_learned():
    rows = learned_indicators()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["type", "value", "source", "description"])
    w.writeheader()
    for r in rows:
        # neutralise spreadsheet formulas if someone opens the feed in Excel
        w.writerow({k: ("'" + v if isinstance(v, str) and v[:1] in "=+-@" else v) for k, v in r.items()})
    config_store.ensure_dirs()
    p = _path(LEARNED)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(p)


def learned_feed_paths():
    p = _path(LEARNED)
    return [p] if p.exists() else []


def forget_reputation(value, actor):
    with _lock:
        rep = _load("learned_reputation.json", {})
        if rep.pop(value, None) is None:
            return False
        _save("learned_reputation.json", rep)
        _write_learned()
    config_store.audit(actor, "learning", "forget_indicator", value, None, None)
    return True


# ------------------------------------------------------------------ sightings across analyses

RULE_STATS = "rule_stats.json"
BASELINED = "baseline_learned.json"


def record_sightings(result, name, when=None):
    """Remember the suspicious public indicators and the rules that fired in this analysis, for later ones."""
    aid = result.get("analysis_id")
    if not aid:
        return
    when = when or config_store.now_iso()
    with _lock:
        rs = _load(RULE_STATS, {})
        for rid in {f.get("rule_id") for f in result.get("findings") or [] if f.get("rule_id")}:
            rs.setdefault(rid, {})[aid] = when
        rs.setdefault("_analyses", {})[aid] = when
        _save(RULE_STATS, rs)
    inc_of = {}
    for f in result.get("findings") or []:
        for ip in f.get("ips") or []:
            if f.get("incident"):
                inc_of.setdefault(ip, f["incident"])
    entries = []
    for p in result.get("ip_profiles") or []:
        if p.get("public") and p.get("verdict") in ("Malicious", "Suspicious"):
            entries.append((p["ip"], p["verdict"]))
    i = result.get("iocs") or {}
    for t in ("domains", "urls", "hashes"):
        for v in (i.get(t) or [])[:50]:
            entries.append((v, "indicator"))
    with _lock:
        s = _load(SIGHTINGS, {})
        for v, verdict in entries[:300]:
            lst = [x for x in s.get(v.lower(), []) if x.get("analysis_id") != aid]
            lst.append({"analysis_id": aid, "time": when, "name": str(name)[:80],
                        "verdict": verdict, "incident": inc_of.get(v)})
            s[v.lower()] = lst[-10:]
        if len(s) > 20000:
            for k in sorted(s, key=lambda k: s[k][-1]["time"])[:len(s) - 20000]:
                s.pop(k)
        _save(SIGHTINGS, s)


def forget_analysis(aid):
    """Remove the sightings and rule statistics of a deleted analysis."""
    with _lock:
        rs = _load(RULE_STATS, {})
        if any(aid in v for v in rs.values()):
            for k in list(rs):
                rs[k].pop(aid, None)
                if not rs[k]:
                    rs.pop(k)
            _save(RULE_STATS, rs)
        s = _load(SIGHTINGS, {})
        changed = False
        for k in list(s):
            keep = [x for x in s[k] if x.get("analysis_id") != aid]
            if len(keep) != len(s[k]):
                changed = True
                if keep:
                    s[k] = keep
                else:
                    s.pop(k)
        if changed:
            _save(SIGHTINGS, s)


def forget_all(actor):
    with _lock:
        for name in (FEEDBACK, SIGHTINGS, "learned_reputation.json", LEARNED, RULE_STATS, BASELINED):
            _path(name).unlink(missing_ok=True)
    config_store.audit(actor, "learning", "forget_all", "", None, None)


# ------------------------------------------------------------------ applying the memory to a new analysis

def annotate(result):
    """Attach verdicts and earlier sightings to a fresh analysis (before it is stored)."""
    fb = _load(FEEDBACK, {})
    sightings = _load(SIGHTINGS, {})
    aid = result.get("analysis_id")
    mem = {"verdicts": [], "seen_before": [], "learned_iocs": len(learned_indicators())}
    for f in result.get("findings") or []:
        v = fb.get(key(f))
        if not v:
            continue
        f["analyst_verdict"] = {k: v.get(k) for k in ("verdict", "note", "actor", "time", "analysis_id")}
        f["analyst_verdict"]["label"] = VERDICTS.get(v["verdict"], v["verdict"])
        risk = f.setdefault("risk", {"score": 0, "factors": []})
        if v["verdict"] == "true_positive":
            f["confidence"] = min(99, int(f.get("confidence", 50)) + 10)
            delta = 5
        else:
            f["confidence"] = max(10, int(f.get("confidence", 50)) - 25)
            delta = -15
        risk["score"] = max(0, min(100, int(risk.get("score", 0)) + delta))
        risk.setdefault("factors", []).append(
            {"factor": f"Analyst marked this rule on {entity(f) or 'this entity'} as {VERDICTS[v['verdict']].lower()} "
                       f"on {v.get('time', '')[:10]}", "points": delta})
        note = f"Earlier analyst verdict: {VERDICTS[v['verdict']]} by {v.get('actor')} on {v.get('time', '')[:10]}" + \
               (f" - {v['note']}" if v.get("note") else "") + ". Severity unchanged; verify it still applies."
        f.setdefault("notes", []).append(note)
        mem["verdicts"].append({"finding": f.get("fid"), "rule_id": f.get("rule_id"), "entity": entity(f),
                                "verdict": v["verdict"], "note": v.get("note", ""), "time": v.get("time")})
    rs = _load(RULE_STATS, {})
    total = len([k for k in rs.get("_analyses", {}) if k != aid])
    fp_by_rule = {}
    for v in fb.values():
        if v.get("verdict") in ("false_positive", "benign"):
            fp_by_rule[v.get("rule_id")] = fp_by_rule.get(v.get("rule_id"), 0) + 1
    for f in result.get("findings") or []:
        seen = len([k for k in rs.get(f.get("rule_id"), {}) if k != aid])
        if total >= 3:
            f["prevalence"] = {"seen_in": seen, "of": total,
                               "text": (f"New: this rule never fired in the {total} earlier analyses" if not seen else
                                        f"This rule fired in {seen} of {total} earlier analyses")}
        if fp_by_rule.get(f.get("rule_id")) and not f.get("analyst_verdict"):
            f.setdefault("notes", []).append(f"Analysts marked this rule false positive / benign {fp_by_rule[f['rule_id']]} "
                                              "time(s) on other entities - review it with that in mind.")
    if total:
        mem["history"] = {"analyses": total, "new_rules": sorted({f["rule_id"] for f in result.get("findings") or []
                                                                  if (f.get("prevalence") or {}).get("seen_in") == 0})}
    for p in result.get("ip_profiles") or []:
        prev = [x for x in sightings.get(str(p.get("ip", "")).lower(), []) if x.get("analysis_id") != aid]
        if prev:
            p["seen_before"] = prev[-5:]
            mem["seen_before"].append({"value": p["ip"], "count": len(prev), "last": prev[-1]["time"],
                                       "last_name": prev[-1].get("name"), "verdicts": sorted({x["verdict"] for x in prev})})
    i = result.get("iocs") or {}
    for t in ("domains", "urls", "hashes"):
        for v in (i.get(t) or [])[:50]:
            prev = [x for x in sightings.get(v.lower(), []) if x.get("analysis_id") != aid]
            if prev:
                mem["seen_before"].append({"value": v, "count": len(prev), "last": prev[-1]["time"],
                                           "last_name": prev[-1].get("name"), "verdicts": []})
    if any(v for k, v in mem.items() if k != "learned_iocs"):
        result["memory"] = mem
    return result


def summary():
    fb = verdicts()
    return {"verdicts": fb, "learned": learned_indicators(),
            "learned_reputation": sorted(_load("learned_reputation.json", {}).values(),
                                         key=lambda r: r.get("time", ""), reverse=True),
            "sightings": len(_load(SIGHTINGS, {})),
            "analyses_learned": len(_load(RULE_STATS, {}).get("_analyses", {})),
            "baselined": len(_load(BASELINED, {})),
            "job": dict(JOB),
            "counts": {k: sum(1 for v in fb if v["verdict"] == k) for k in VERDICTS}}


# ------------------------------------------------------------------ learning from the stored logs

JOB = {"running": False, "done": 0, "total": 0, "current": "", "baselines": 0, "errors": [], "finished": None}


def mark_baselined(aid):
    """This analysis already taught the UEBA baselines (so learning from history won't count it twice)."""
    with _lock:
        b = _load(BASELINED, {})
        b[aid] = config_store.now_iso()
        _save(BASELINED, b)


def learn_from_history(analyse_logs=None, actor=""):
    """Replay the History: sightings and rule statistics from every stored analysis, and UEBA baselines from
    stored logs that have not taught them yet. analyse_logs(files) runs the pipeline with baseline learning on.
    Runs in a background thread; progress is in JOB."""
    import history
    if JOB["running"]:
        return False
    items = sorted(history.list_all(), key=lambda m: (m.get("time", ""), m.get("ts", 0)))
    JOB.update(running=True, done=0, total=len(items), current="", baselines=0, errors=[], finished=None)
    try:
        for m in items:
            JOB["current"] = m.get("name", "")
            try:
                r = history.load(m["id"])
                if r and r.get("findings") is not None:
                    record_sightings(r, m.get("name", ""), m.get("time"))
                if analyse_logs and m["id"] not in _load(BASELINED, {}) and m.get("kind") in ("upload", "paste"):
                    files = history.log_files(m["id"])
                    if files and not history.verify(m["id"]):
                        analyse_logs(files)
                        mark_baselined(m["id"])
                        JOB["baselines"] += 1
            except Exception as e:  # noqa: BLE001 - one bad entry must not stop the rest
                JOB["errors"].append(f"{m.get('name', m['id'])}: {e}"[:200])
            JOB["done"] += 1
        config_store.audit(actor, "learning", "learn_from_history", "",
                           None, {"analyses": JOB["done"], "baselines": JOB["baselines"], "errors": len(JOB["errors"])})
    finally:
        JOB.update(running=False, current="", finished=config_store.now_iso())
    return True
