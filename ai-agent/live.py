"""Live analysis of logs forwarded by a SIEM (or any log shipper).

Receivers
  * HTTP  POST /api/live/ingest  with header  X-Ingest-Token: <token>
          body: JSON object, JSON array, {"events": [...]}, Splunk webhook ({"result": {...}}),
          NDJSON (one JSON object per line) or plain text (one log line per line)
  * Syslog  UDP and TCP on live_syslog_port (off by default), RFC 3164 / 5424, newline or
          octet-counted framing; optionally only from live_allowed_sources

Engine
  Events are kept in memory (rolling window) and appended to a daily spool file in data/live/
  (owner-only), so a restart does not lose the window. Every live_interval_s seconds, if new events
  arrived, the window is analysed with the same pipeline as uploaded files (rules, correlation,
  UEBA, trusted inventory, learned indicators). Each finding becomes a live alert keyed by rule and
  entity: new alerts are flagged, repeats update the count. Nothing is executed or blocked.
  A snapshot stores the window in the History (where "Learn from stored logs" can use it).
"""
import json
import os
import re
import socket
import socketserver
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import config_store

MAX_LINE = 64 * 1024
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _now():
    return time.time()


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class LiveEngine:
    def __init__(self, cfg, analyse_files, annotate=None):
        """analyse_files(files) -> analysis dict (JSON-ready); annotate(result) applies the learning memory."""
        self.cfg = cfg
        self.analyse_files = analyse_files
        self.annotate = annotate
        self.lock = threading.RLock()
        self.events = deque(maxlen=int(cfg.get("live_max_events") or 50000))   # (seq, t, source, kind, text)
        self.seq = 0
        self.flags = {}            # seq -> [rule ids] for events used as evidence
        self.alerts = {}
        self.result = None
        self.last_run = None
        self.last_run_seq = 0
        self.run_ms = 0
        self.paused = False
        self.received = {"http": 0, "syslog": 0, "dropped": 0}
        self.last_event = None
        self.errors = deque(maxlen=20)
        self._stop = threading.Event()
        self._servers = []
        self._thread = None
        self.syslog_status = "off"

    # ------------------------------------------------------------------ setup
    @property
    def enabled(self):
        return bool(self.cfg.get("live_enabled"))

    def start(self):
        self._reload_spool()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="live-analysis")
        self._thread.start()
        self.start_syslog()

    def stop(self):
        self._stop.set()
        for s in self._servers:
            try:
                s.shutdown()
                s.server_close()
            except OSError:
                pass
        self._servers = []

    def start_syslog(self):
        port = int(self.cfg.get("live_syslog_port") or 0)
        if not (self.enabled and port):
            self.syslog_status = "off (set live_syslog_port)" if self.enabled else "off"
            return
        host = str(self.cfg.get("live_syslog_host") or "0.0.0.0")
        eng = self

        class UDP(socketserver.BaseRequestHandler):
            def handle(self):
                data = self.request[0]
                eng.ingest_syslog(data, self.client_address[0])

        class TCP(socketserver.StreamRequestHandler):
            def handle(self):
                buf = b""
                while True:
                    chunk = self.request.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    buf = eng._tcp_frames(buf, self.client_address[0])
                    if len(buf) > MAX_LINE * 4:   # unframed garbage
                        buf = b""
                if buf.strip():
                    eng.ingest_syslog(buf, self.client_address[0])

        try:
            fam = socket.AF_INET6 if ":" in host else socket.AF_INET
            udp = type("U", (socketserver.ThreadingUDPServer,), {"address_family": fam, "allow_reuse_address": True})((host, port), UDP)
            tcp = type("T", (socketserver.ThreadingTCPServer,), {"address_family": fam, "allow_reuse_address": True,
                                                                  "daemon_threads": True})((host, port), TCP)
        except OSError as e:
            self.syslog_status = f"error: cannot listen on {host}:{port} ({e.strerror or e})"
            return
        for srv in (udp, tcp):
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self._servers.append(srv)
        self.syslog_status = f"listening on {host}:{port} (UDP + TCP)"

    def _tcp_frames(self, buf, src):
        """RFC 6587: octet counting ("123 <34>...") or newline-delimited frames. Returns the unconsumed rest."""
        while buf:
            m = re.match(rb"(\d{1,6}) ", buf)
            if m and buf[m.end():m.end() + 1] == b"<":
                n = int(m.group(1))
                if len(buf) < m.end() + n:
                    return buf
                self.ingest_syslog(buf[m.end():m.end() + n], src)
                buf = buf[m.end() + n:]
                continue
            i = buf.find(b"\n")
            if i < 0:
                return buf
            self.ingest_syslog(buf[:i], src)
            buf = buf[i + 1:]
        return buf

    def allowed_source(self, ip):
        allow = self.cfg.get("live_allowed_sources") or []
        if not allow:
            return True
        import ipaddress
        try:
            a = ipaddress.ip_address(ip)
            return any(a in ipaddress.ip_network(str(n), strict=False) for n in allow)
        except ValueError:
            return False

    # ------------------------------------------------------------------ ingest
    def ingest_syslog(self, data, src):
        if not self.enabled:
            return 0
        if not self.allowed_source(src):
            with self.lock:
                self.received["dropped"] += 1
            return 0
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
        return self._add([("text", ln) for ln in text.splitlines() if ln.strip()], f"syslog:{src}", "syslog")

    def ingest_http(self, body, content_type, src):
        """Returns the number of events accepted. Raises ValueError for a body that can't be read."""
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
        items = []
        ct = (content_type or "").lower()
        stripped = text.lstrip()
        if "json" in ct or stripped[:1] in ("{", "["):
            try:
                items = self._json_items(json.loads(text))
            except ValueError:
                lines = [ln for ln in text.splitlines() if ln.strip()]
                try:   # NDJSON
                    for ln in lines:
                        items += self._json_items(json.loads(ln))
                except ValueError:
                    if "json" in ct:
                        raise ValueError("body is not valid JSON / NDJSON") from None
                    items = [("text", ln) for ln in lines]
        else:
            items = [("text", ln) for ln in text.splitlines() if ln.strip()]
        return self._add(items, f"http:{src}", "http")

    @staticmethod
    def _json_items(obj):
        if isinstance(obj, list):
            out = []
            for o in obj:
                out += LiveEngine._json_items(o)
            return out
        if not isinstance(obj, dict):
            return [("text", str(obj))]
        if isinstance(obj.get("events"), list):
            return LiveEngine._json_items(obj["events"])
        if isinstance(obj.get("result"), dict) and ("search_name" in obj or "sid" in obj or len(obj) <= 4):
            obj = obj["result"]                      # Splunk alert webhook
        raw = obj.get("_raw") or obj.get("raw") or obj.get("full_log")
        if isinstance(raw, str) and raw.strip() and len(obj) <= 3:
            return [("text", raw)]
        return [("json", json.dumps(obj, ensure_ascii=False, default=str))]

    def _add(self, items, source, channel):
        if not items:
            return 0
        t = _now()
        rows = []
        with self.lock:
            for kind, txt in items:
                txt = str(txt)[:MAX_LINE].replace("\r", " ").replace("\n", " ")
                self.seq += 1
                row = (self.seq, t, source, kind, txt)
                self.events.append(row)
                rows.append(row)
            self.received[channel] += len(rows)
            self.last_event = t
        self._spool(rows)
        return len(rows)

    # ------------------------------------------------------------------ spool (survives restarts, feeds snapshots)
    def _spool_dir(self):
        return config_store.DATA_DIR / "live"

    def _spool(self, rows):
        try:
            d = self._spool_dir()
            d.mkdir(parents=True, exist_ok=True)
            os.chmod(d, 0o700)
            p = d / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
            new = not p.exists()
            with open(p, "a", encoding="utf-8") as fh:
                for seq, t, src, kind, txt in rows:
                    fh.write(json.dumps({"t": round(t, 3), "s": src, "k": kind, "d": txt}, ensure_ascii=False) + "\n")
            if new:
                os.chmod(p, 0o600)
                self._prune_spool()
        except OSError as e:
            self.errors.append(f"spool: {e}")

    def _prune_spool(self):
        keep = float(self.cfg.get("live_keep_days") or 7)
        cutoff = _now() - keep * 86400
        for p in self._spool_dir().glob("*.jsonl"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass

    def _reload_spool(self):
        """Put the last window back in memory after a restart."""
        horizon = _now() - self._window_s()
        rows = []
        for p in sorted(self._spool_dir().glob("*.jsonl"))[-2:] if self._spool_dir().exists() else []:
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for ln in fh:
                        try:
                            r = json.loads(ln)
                        except ValueError:
                            continue
                        if r.get("t", 0) >= horizon:
                            rows.append(r)
            except OSError:
                continue
        with self.lock:
            for r in rows[-self.events.maxlen:]:
                self.seq += 1
                self.events.append((self.seq, r["t"], r.get("s", "spool"), r.get("k", "text"), r.get("d", "")))
            if rows:
                self.last_event = rows[-1]["t"]

    # ------------------------------------------------------------------ analysis
    def _window_s(self):
        return float(self.cfg.get("live_window_minutes") or 60) * 60

    def window(self):
        horizon = _now() - self._window_s()
        limit = int(self.cfg.get("live_max_analyse") or 20000)
        with self.lock:
            rows = [r for r in self.events if r[1] >= horizon]
        return rows[-limit:]

    def _loop(self):
        while not self._stop.wait(1.0):
            interval = float(self.cfg.get("live_interval_s") or 20)
            if (self.enabled and not self.paused and self.seq != self.last_run_seq
                    and (self.last_run is None or _now() - self.last_run >= interval)):
                try:
                    self.analyse()
                except Exception as e:  # noqa: BLE001 - keep the live loop alive
                    self.errors.append(f"{_iso(_now())} analysis failed: {e}")
                    self.last_run = _now()

    def write_window(self, folder, rows=None):
        """Window -> live.jsonl (JSON events) and live.log (text lines). Returns ([(path, name)], {ref: seq})."""
        rows = self.window() if rows is None else rows
        folder.mkdir(parents=True, exist_ok=True)
        files, refmap = [], {}
        for kind, name in (("json", "live.jsonl"), ("text", "live.log")):
            sel = [r for r in rows if r[3] == kind]
            if not sel:
                continue
            p = folder / name
            with open(p, "w", encoding="utf-8") as fh:
                for i, r in enumerate(sel, 1):
                    fh.write(r[4] + "\n")
                    refmap[f"{name}:{i}"] = r[0]
            os.chmod(p, 0o600)
            files.append((p, name))
        return files, refmap

    def analyse(self):
        rows = self.window()
        seq_at = self.seq
        if not rows:
            with self.lock:
                self.result, self.last_run, self.last_run_seq = None, _now(), seq_at
            return None
        t0 = _now()
        tmp = config_store.UPLOAD_DIR / f"live-{os.getpid()}"
        try:
            files, refmap = self.write_window(tmp, rows)
            res = self.analyse_files(files)
        finally:
            for p in tmp.glob("*") if tmp.exists() else []:
                p.unlink(missing_ok=True)
            try:
                tmp.rmdir()
            except OSError:
                pass
        res["analysis_id"] = res.get("analysis_id") or "live"
        if self.annotate:
            try:
                self.annotate(res)
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"learning memory: {e}")
        flags = {}
        for f in res.get("findings") or []:
            for ref in f.get("evidence_refs") or []:
                s = refmap.get(ref)
                if s:
                    flags.setdefault(s, []).append(f.get("rule_id"))
        with self.lock:
            self.result, self.flags = res, flags
            self._update_alerts(res)
            self.last_run, self.last_run_seq, self.run_ms = _now(), seq_at, int((_now() - t0) * 1000)
        return res

    def _update_alerts(self, res):
        import memory
        now = _now()
        active = set()
        for f in res.get("findings") or []:
            k = memory.key(f)
            active.add(k)
            a = self.alerts.get(k)
            if a is None:
                self.alerts[k] = a = {"key": k, "first": now, "status": "new", "rule_id": f.get("rule_id"),
                                      "times_seen": 0}
            elif a["status"] == "inactive":
                a["status"] = "new" if SEV_RANK.get(f["severity"], 4) < SEV_RANK.get(a.get("severity"), 4) else a.get("prev", "new")
            a.update(last=now, title=f.get("title"), severity=f.get("severity"), count=f.get("count", 1),
                     risk=(f.get("risk") or {}).get("score"), confidence=f.get("confidence"), fid=f.get("fid"),
                     ips=(f.get("ips") or [])[:6], users=(f.get("users") or [])[:6], hosts=(f.get("hosts") or [])[:6],
                     incident=f.get("incident"), mitre=f.get("mitre"), recommendation=f.get("recommendation"),
                     sample=((f.get("samples") or [{}])[0].get("text") or "")[:300],
                     actions=(f.get("actions_taken") or [])[:3], first_seen=f.get("first_seen"),
                     last_seen=f.get("last_seen"), verdict=(f.get("analyst_verdict") or {}).get("label"))
            a["times_seen"] += 1
        for k, a in self.alerts.items():
            if k not in active and a["status"] != "inactive":
                a["prev"], a["status"] = a["status"], "inactive"   # dropped out of the window
        if len(self.alerts) > 2000:
            for k in sorted(self.alerts, key=lambda k: self.alerts[k]["last"])[:len(self.alerts) - 2000]:
                self.alerts.pop(k)

    # ------------------------------------------------------------------ control & state
    def ack(self, key):
        with self.lock:
            a = self.alerts.get(key)
            if a and a["status"] == "new":
                a["status"] = "acknowledged"
            return bool(a)

    def ack_all(self):
        with self.lock:
            for a in self.alerts.values():
                if a["status"] == "new":
                    a["status"] = "acknowledged"

    def clear(self):
        with self.lock:
            self.events.clear()
            self.alerts.clear()
            self.flags.clear()
            self.result = None
            self.last_run_seq = self.seq

    def rate(self, minutes=60):
        now = _now()
        buckets = [0] * minutes
        with self.lock:
            for _, t, *_ in reversed(self.events):
                age = int((now - t) // 60)
                if age >= minutes:
                    break
                buckets[minutes - 1 - age] += 1
        return buckets

    def state(self, since=0, limit=200):
        with self.lock:
            new_rows = [r for r in self.events if r[0] > since][-limit:]
            stream = [{"seq": s, "time": _iso(t), "source": src, "kind": k, "text": txt[:2000],
                       "rules": self.flags.get(s, [])} for s, t, src, k, txt in new_rows]
            alerts = sorted(self.alerts.values(), key=lambda a: ({"new": 0, "acknowledged": 1, "inactive": 2}[a["status"]],
                                                                  SEV_RANK.get(a.get("severity"), 4), -a["last"]))
            res = self.result or {}
            win = self.window()
            return {
                "enabled": self.enabled, "paused": self.paused, "seq": self.seq,
                "received": dict(self.received), "window_events": len(win),
                "window_minutes": float(self.cfg.get("live_window_minutes") or 60),
                "interval_s": float(self.cfg.get("live_interval_s") or 20),
                "last_event": _iso(self.last_event) if self.last_event else None,
                "last_run": _iso(self.last_run) if self.last_run else None, "run_ms": self.run_ms,
                "pending": self.seq != self.last_run_seq, "syslog": self.syslog_status,
                "errors": list(self.errors)[-5:], "rate": self.rate(60),
                "alerts": [dict(a, first=_iso(a["first"]), last=_iso(a["last"])) for a in alerts[:300]],
                "new_alerts": sum(1 for a in self.alerts.values() if a["status"] == "new"),
                "summary": {"risk_score": res.get("risk_score", 0), "risk_level": res.get("risk_level", "clean"),
                            "findings": len(res.get("findings") or []), "summary": res.get("summary"),
                            "incidents": [{"id": i["id"], "title": i["title"], "severity": i["severity"],
                                           "status": i.get("status"), "attack_path": i.get("attack_path"),
                                           "diagram": i.get("diagram")} for i in res.get("incidents") or []][:10],
                            "ip_profiles": [p for p in res.get("ip_profiles") or [] if p.get("verdict") in
                                            ("Malicious", "Suspicious")][:15]},
                "stream": stream,
            }
