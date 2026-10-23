"""Local, validated JSON configuration with an append-only audit trail.

Live configuration lives in config/ (git-ignored, created from config/examples/ on first
use) so `git pull` never overwrites an organisation's networks or branding. Runtime data
(uploads, baselines, audit log, generated reports) lives in data/ with owner-only
permissions because it can contain sensitive evidence.
"""
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
EXAMPLES_DIR = CONFIG_DIR / "examples"
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
AUDIT_LOG = DATA_DIR / "audit.log"
_lock = threading.Lock()


def ensure_dirs():
    for d in (CONFIG_DIR, DATA_DIR, UPLOAD_DIR, CONFIG_DIR / "ioc"):
        d.mkdir(parents=True, exist_ok=True)
    for d in (CONFIG_DIR, DATA_DIR, UPLOAD_DIR, CONFIG_DIR / "ioc"):   # secrets / evidence: owner only
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass


def live_path(name):
    """config/<name>; created from config/examples/<stem>.example.json if missing."""
    ensure_dirs()
    path = CONFIG_DIR / name
    example = EXAMPLES_DIR / (Path(name).stem + ".example" + Path(name).suffix)
    if not path.exists() and example.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # created 0600, never briefly readable
        with os.fdopen(fd, "wb") as fh:
            fh.write(example.read_bytes())
    return path


def _restrict(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_json(path, default):
    """Return (data, error). A malformed file never crashes the caller."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return default, None
    except (OSError, ValueError) as e:
        return default, f"{Path(path).name}: {e}"


def save_json(path, data):
    """Atomic write (temp file + rename) so a crash can't leave half a config file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            _restrict(tmp)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit(actor, area, action, target="", before=None, after=None, detail=""):
    """Append one change record: who, what, when, previous and new value."""
    ensure_dirs()
    rec = {"time": now_iso(), "actor": actor or "unknown", "area": area, "action": action,
           "target": target, "before": before, "after": after, "detail": detail}
    with _lock:
        new = not AUDIT_LOG.exists()
        with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if new:
            _restrict(AUDIT_LOG)
    return rec


def read_audit(limit=200, area=None):
    if not AUDIT_LOG.exists():
        return []
    out = []
    with open(AUDIT_LOG, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if area is None or rec.get("area") == area:
                out.append(rec)
    return out[-limit:][::-1]
