"""Analysis history: every analysis is kept with its original log files until you delete it.

Layout (data/ is 0700, files 0600):
  data/history/<analysis id>/meta.json        name, time, who, files (size + SHA-256), counts, risk
  data/history/<analysis id>/result.json.gz   the full analysis (findings, incidents, evidence, AI text...)
  data/history/<analysis id>/logs/...         the uploaded / pasted logs, exactly as received

The original files are evidence: they are never modified, and their SHA-256 is recorded when
they are stored so later tampering can be detected.
"""
import gzip
import hashlib
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

import config_store

ID_RE = re.compile(r"[a-f0-9]{16}")
_lock = threading.RLock()


def root():
    return config_store.DATA_DIR / "history"


def valid_id(aid):
    return bool(ID_RE.fullmatch(str(aid or "")))


def _dir(aid):
    if not valid_id(aid):
        raise ValueError("bad analysis id")
    return root() / aid


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _private(path, mode=0o600):
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def save(result, kind, name, files=(), move=False, actor="", samples=()):
    """Store an analysis. files: [(path, display name)] copied (or moved) into logs/.
    samples: names of built-in sample files used (not copied; re-analysis reads them from samples/)."""
    aid = result.get("analysis_id")
    d = _dir(aid)
    with _lock:
        config_store.ensure_dirs()
        root().mkdir(mode=0o700, exist_ok=True)
        _private(root(), 0o700)
        (d / "logs").mkdir(mode=0o700, parents=True, exist_ok=True)
        stored = []
        for path, display in files:
            path = Path(path)
            dest = d / "logs" / Path(display).name
            n = 1
            while dest.exists():
                dest = d / "logs" / f"{Path(display).stem}-{n}{Path(display).suffix}"
                n += 1
            if move:
                shutil.move(str(path), dest)
            else:
                shutil.copyfile(path, dest)
            _private(dest)
            stored.append({"name": dest.name, "bytes": dest.stat().st_size, "sha256": _sha256(dest)})
        meta = {"id": aid, "time": config_store.now_iso(), "ts": time.time(), "name": str(name or "analysis")[:160], "kind": kind,
                "actor": actor, "files": stored, "samples": list(samples),
                "events": result.get("lines") or result.get("events") or 0,
                "findings": len(result.get("findings") or []), "incidents": len(result.get("incidents") or []),
                "risk_score": result.get("risk_score", 0), "risk_level": result.get("risk_level", ""),
                "grade": result.get("grade", "")}
        _write_result(d, result)
        config_store.save_json(d / "meta.json", meta)
        return meta


def _write_result(d, result):
    tmp = d / "result.json.gz.tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, default=str)
    _private(tmp)
    os.replace(tmp, d / "result.json.gz")


def update_result(result):
    """Persist changes made after the analysis (AI investigation, reputation, analyst verdicts)."""
    aid = result.get("analysis_id")
    if not valid_id(aid):
        return False
    d = _dir(aid)
    with _lock:
        if not (d / "meta.json").exists():
            return False
        _write_result(d, result)
        meta, _ = config_store.load_json(d / "meta.json", {})
        meta.update(findings=len(result.get("findings") or []), risk_score=result.get("risk_score", 0),
                    has_ai=bool(result.get("ai_investigation")), reputation=len(result.get("reputation") or {}))
        config_store.save_json(d / "meta.json", meta)
    return True


def exists(aid):
    return valid_id(aid) and (root() / aid / "meta.json").exists()


def load(aid):
    d = _dir(aid)
    try:
        with gzip.open(d / "result.json.gz", "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def meta(aid):
    m, _ = config_store.load_json(_dir(aid) / "meta.json", None)
    return m


def list_all():
    out = []
    if not root().exists():
        return out
    for d in root().iterdir():
        if not (d.is_dir() and valid_id(d.name)):
            continue
        m, err = config_store.load_json(d / "meta.json", None)
        if not m:
            continue
        m["stored_bytes"] = sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
        out.append(m)
    out.sort(key=lambda m: (m.get("time", ""), m.get("ts", 0)), reverse=True)
    return out


def log_files(aid):
    """[(path, name)] of the stored original logs, verifying they are still the files that were stored."""
    d = _dir(aid) / "logs"
    m = meta(aid) or {}
    known = {f["name"]: f for f in m.get("files", [])}
    out = []
    for p in sorted(d.glob("*")) if d.exists() else []:
        if p.is_file() and p.name in known:
            out.append((p, p.name))
    return out


def verify(aid):
    """Names of stored log files whose SHA-256 no longer matches (tampered / damaged)."""
    m = meta(aid) or {}
    bad = []
    for f in m.get("files", []):
        p = _dir(aid) / "logs" / f["name"]
        if not p.exists() or _sha256(p) != f["sha256"]:
            bad.append(f["name"])
    return bad


def file_path(aid, name):
    """Path of one stored log, or None. The name must be one recorded in meta.json (no traversal)."""
    m = meta(aid) or {}
    if name not in {f["name"] for f in m.get("files", [])}:
        return None
    p = _dir(aid) / "logs" / name
    return p if p.is_file() else None


def delete(aid, actor=""):
    d = _dir(aid)
    with _lock:
        m = meta(aid)
        if not m:
            return False
        shutil.rmtree(d, ignore_errors=True)
    config_store.audit(actor, "history", "delete", aid, {"name": m.get("name"), "files": [f["name"] for f in m.get("files", [])]}, None)
    return True


def delete_all(actor=""):
    n = 0
    for m in list_all():
        n += delete(m["id"], actor)
    return n


def enforce_retention(max_days=0, max_gb=0, actor="retention"):
    """Delete analyses older than max_days, then the oldest ones while the total exceeds max_gb (0 = no limit)."""
    removed = []
    items = list_all()
    if max_days and float(max_days) > 0:
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - float(max_days) * 86400))
        for m in items:
            if m.get("time", "") < cutoff and delete(m["id"], actor):
                removed.append(m["id"])
        items = [m for m in items if m["id"] not in removed]
    if max_gb and float(max_gb) > 0:
        limit = float(max_gb) * 1024 ** 3
        total = sum(m["stored_bytes"] for m in items)
        for m in reversed(items):                 # oldest first
            if total <= limit:
                break
            if delete(m["id"], actor):
                removed.append(m["id"])
                total -= m["stored_bytes"]
    return removed


def usage():
    items = list_all()
    return {"analyses": len(items), "bytes": sum(m["stored_bytes"] for m in items),
            "log_files": sum(len(m.get("files", [])) for m in items)}
