"""History (stored analyses + logs), reputation look-ups (mocked services) and the learning memory."""
import copy
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent  # noqa: E402
import config_store  # noqa: E402
import engine  # noqa: E402
import history  # noqa: E402
import memory  # noqa: E402
import pipeline  # noqa: E402
import reputation  # noqa: E402
import trust  # noqa: E402
from test_siem_platform import DEMO_TRUST, SAMPLE_FILES, SIEM, Isolated  # noqa: E402

WEB = (ROOT / "samples" / "siem" / "web_access.log").read_text()


class FakeIntel(BaseHTTPRequestHandler):
    """Stands in for api.abuseipdb.com and www.virustotal.com."""
    calls = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        FakeIntel.calls.append((self.command, self.path, dict(self.headers)))
        if self.path.startswith("/abuse/check"):
            if self.headers.get("Key") != "A" * 32:
                return self._json(401, {"errors": [{"detail": "bad key"}]})
            ip = self.path.split("ipAddress=")[1].split("&")[0]
            bad = ip == "203.0.113.50"
            return self._json(200, {"data": {"ipAddress": ip, "abuseConfidenceScore": 100 if bad else 0,
                                             "totalReports": 57 if bad else 0, "countryCode": "XX", "isp": "Example ISP",
                                             "usageType": "Data Center/Web Hosting/Transit", "isTor": False}})
        if self.path.startswith("/vt/"):
            if "urls/" in self.path:
                return self._json(404, {"error": {"code": "NotFoundError"}})
            mal = 9 if "203.0.113.50" in self.path else 0
            return self._json(200, {"data": {"attributes": {
                "last_analysis_stats": {"malicious": mal, "suspicious": 0, "harmless": 60, "undetected": 20},
                "country": "XX", "as_owner": "Example AS", "last_analysis_date": 1760000000}}})
        self._json(404, {})

    def do_POST(self):  # a URL must never be submitted for scanning
        FakeIntel.calls.append((self.command, self.path, dict(self.headers)))
        self._json(405, {})

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class HistoryTests(Isolated):
    def test_save_list_load_verify_delete(self):
        src = self.tmp / "fw.log"
        src.write_text("Oct 18 02:00:00 fw01 kernel: [UFW BLOCK] SRC=203.0.113.9 DST=192.0.2.1 PROTO=TCP DPT=22\n")
        r = {"analysis_id": "a" * 16, "findings": [{"x": 1}], "incidents": [], "lines": 1, "risk_score": 10}
        m = history.save(r, "upload", "fw test", [(src, "fw.log")], actor="t")
        self.assertEqual(m["files"][0]["name"], "fw.log")
        self.assertEqual(len(m["files"][0]["sha256"]), 64)
        self.assertTrue(src.exists(), "copy mode keeps the source")
        self.assertIn("a" * 16, [m["id"] for m in history.list_all()])
        self.assertEqual(history.load("a" * 16)["risk_score"], 10)
        self.assertEqual(history.verify("a" * 16), [])
        (history.root() / ("a" * 16) / "logs" / "fw.log").write_text("tampered")
        self.assertEqual(history.verify("a" * 16), ["fw.log"])
        self.assertIsNone(history.file_path("a" * 16, "../meta.json"))     # no path traversal
        self.assertIsNone(history.file_path("a" * 16, "other.log"))
        with self.assertRaises(ValueError):
            history.load("../../etc")
        self.assertTrue(history.delete("a" * 16, "t"))
        self.assertFalse(history.exists("a" * 16))
        self.assertIn("delete", [e["action"] for e in config_store.read_audit(20) if e["area"] == "history"])

    def test_retention(self):
        for n, t in ((1, "2020-01-01T00:00:00Z"), (2, config_store.now_iso())):
            r = {"analysis_id": f"{n:016x}", "findings": []}
            history.save(r, "paste", f"n{n}")
            meta = history.meta(r["analysis_id"])
            meta["time"] = t
            config_store.save_json(history.root() / r["analysis_id"] / "meta.json", meta)
        self.assertEqual(history.enforce_retention(max_days=30), [f"{1:016x}"])
        self.assertEqual([m["id"] for m in history.list_all()], [f"{2:016x}"])


class ReputationTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeIntel)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.cfg = {"abuseipdb_key": "A" * 32, "virustotal_key": "V" * 64, "abuseipdb_url": base + "/abuse",
                   "virustotal_url": base + "/vt", "virustotal_per_min": 6000, "abuseipdb_per_min": 6000,
                   "reputation_allow_documentation": True}

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        super().tearDownClass()

    def test_refuses_internal_and_own(self):
        inv = trust.Inventory(copy.deepcopy(DEMO_TRUST))
        for v in ("10.1.2.3", "192.168.1.5", "127.0.0.1", "fe80::1", "dc01.corp", "intranet.example.local",
                  "http://10.0.0.5/x", "ftp://203.0.113.5/", "hello world", "100.64.1.1"):
            with self.assertRaises(reputation.RefusedError, msg=v):
                reputation.classify(v, inv, allow_documentation=True)
        with self.assertRaises(reputation.RefusedError):            # documentation ranges only on request
            reputation.classify("203.0.113.50", inv)
        with self.assertRaises(reputation.RefusedError):            # own public web server is never sent
            reputation.classify("198.51.100.2", inv, allow_documentation=True)
        self.assertEqual(reputation.classify("8.8.8.8"), ("ip", "8.8.8.8"))
        self.assertEqual(reputation.classify("Evil.COM."), ("domain", "evil.com"))

    def test_lookup_cache_and_verdicts(self):
        FakeIntel.calls.clear()
        r = reputation.lookup(self.cfg, "203.0.113.50")
        self.assertEqual(r["verdict"], "malicious")
        self.assertEqual(r["abuseipdb"]["score"], 100)
        self.assertEqual(r["virustotal"]["malicious"], 9)
        self.assertIn("AbuseIPDB 100%", r["summary"])
        n = len(FakeIntel.calls)
        self.assertTrue(reputation.lookup(self.cfg, "203.0.113.50")["cached"])
        self.assertEqual(len(FakeIntel.calls), n, "cached result: no second request")
        self.assertEqual(reputation.lookup(self.cfg, "203.0.113.7")["verdict"], "no known abuse")
        u = reputation.lookup(self.cfg, "http://203.0.113.61/x.sh")
        self.assertFalse(u["virustotal"]["found"])
        self.assertNotIn("abuseipdb", u)
        self.assertTrue(all(c[0] == "GET" for c in FakeIntel.calls), "URLs are looked up, never submitted")
        self.assertTrue(all("Key" not in c[2] or "/abuse/" in c[1] for c in FakeIntel.calls))
        self.assertEqual(reputation.quota_used()["virustotal"], 3)

    def test_bad_key_and_no_key(self):
        bad = dict(self.cfg, abuseipdb_key="B" * 32, virustotal_key="")
        r = reputation.lookup(bad, "203.0.113.8")
        self.assertIn("rejected the API key", r["abuseipdb"]["error"])
        self.assertEqual(r["verdict"], "unknown")
        with self.assertRaises(ValueError):
            reputation.lookup({}, "8.8.8.8")


class LearningTests(Isolated):
    def analyse(self, files=None, learned=True):
        inv = trust.Inventory(copy.deepcopy(DEMO_TRUST))
        iocs = engine.load_iocs([SIEM / "ioc_feed.csv"] + (memory.learned_feed_paths() if learned else []))[0]
        r = pipeline.to_json(pipeline.analyze_files(files or SAMPLE_FILES, inventory=inv, iocs=iocs, learn_baseline=False))
        return r

    def test_verdicts_learned_indicators_and_sightings(self):
        r1 = self.analyse()
        r1["analysis_id"] = "1" * 16
        memory.annotate(r1)
        memory.record_sightings(r1, "first")
        shell = next(f for f in r1["findings"] if f["rule_id"] == "TG-WEB-009")
        scan = next(f for f in r1["findings"] if f["rule_id"] == "TG-NET-001" and "192.0.2.250" in f["title"])
        memory.record_verdict(shell, "true_positive", "web shell confirmed on WEB01", "analyst@test", r1["analysis_id"], r1)
        memory.record_verdict(scan, "benign", "approved weekly scan", "analyst@test", r1["analysis_id"], r1)
        learned = {x["value"] for x in memory.learned_indicators()}
        self.assertTrue({"203.0.113.50", "203.0.113.61"} <= learned)   # attacker + second-stage server
        self.assertTrue(memory.learned_feed_paths())

        # a later analysis of the web log alone
        p = self.tmp / "web2.log"
        p.write_text(WEB)
        r2 = self.analyse([(p, "web2.log")])
        r2["analysis_id"] = "2" * 16
        memory.annotate(r2)
        shell2 = next(f for f in r2["findings"] if f["rule_id"] == "TG-WEB-009")
        self.assertEqual(shell2["analyst_verdict"]["verdict"], "true_positive")
        self.assertGreaterEqual(shell2["confidence"], shell["confidence"])
        self.assertEqual(shell2["severity"], "critical")
        ti = [f for f in r2["findings"] if f["rule_id"].startswith("TG-TI") and "203.0.113.50" in f["title"]]
        self.assertTrue(ti, "confirmed attacker IP is matched offline in later logs")
        prof = next(x for x in r2["ip_profiles"] if x["ip"] == "203.0.113.50")
        self.assertEqual(prof["seen_before"][0]["analysis_id"], "1" * 16)
        self.assertTrue(r2["memory"]["seen_before"])

        # false-positive / benign verdicts lower confidence but never hide or downgrade
        r3 = self.analyse()
        r3["analysis_id"] = "3" * 16
        before = {f["fid"]: f for f in copy.deepcopy(r3["findings"])}
        memory.annotate(r3)
        self.assertEqual(len(r3["findings"]), len(before))
        scan3 = next(f for f in r3["findings"] if f["rule_id"] == "TG-NET-001" and "192.0.2.250" in f["title"])
        self.assertEqual(scan3["analyst_verdict"]["verdict"], "benign")
        self.assertLess(scan3["confidence"], before[scan3["fid"]]["confidence"])
        self.assertEqual(scan3["severity"], before[scan3["fid"]]["severity"])

        import investigator
        cf = investigator.case_file(r3)
        self.assertIn("ORGANISATION MEMORY", cf)
        self.assertIn("approved weekly scan", cf)

        memory.forget_all("t")
        self.assertEqual(memory.learned_indicators(), [])

    def test_reputation_malicious_is_learned(self):
        memory.learn_reputation({"value": "198.51.100.77", "type": "ip", "verdict": "malicious", "summary": "x"}, "t")
        memory.learn_reputation({"value": "198.51.100.78", "type": "ip", "verdict": "no known abuse"}, "t")
        self.assertEqual([x["value"] for x in memory.learned_indicators()], ["198.51.100.77"])
        text = memory.learned_feed_paths()[0].read_text()
        self.assertIn("LOCAL-REPUTATION", text)
        memory.forget_reputation("198.51.100.77", "t")
        self.assertEqual(memory.learned_indicators(), [])


class ApiHistoryTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.intel = ThreadingHTTPServer(("127.0.0.1", 0), FakeIntel)
        threading.Thread(target=cls.intel.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.intel.server_address[1]}"
        cfg = agent.load_config()
        cfg.update(base_url="http://127.0.0.1:9", access_token="", password_hash="", host="127.0.0.1",
                   keep_uploads=False, history_enabled=True, store_logs=True, learn_from_data=True,
                   abuseipdb_key="A" * 32, virustotal_key="V" * 64, abuseipdb_url=base + "/abuse",
                   virustotal_url=base + "/vt", virustotal_per_min=6000, reputation_allow_documentation=True)
        agent.Handler.cfg = cfg
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.intel.shutdown()
        super().tearDownClass()

    def call(self, path, body=None, raw=None, headers=None):
        from urllib.error import HTTPError
        from urllib.request import Request
        h = {"Content-Type": "application/octet-stream" if raw is not None else "application/json"}
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        try:
            with agent._OPENER.open(Request(self.base + path, data=data, headers=h), timeout=60) as r:
                return r.status, r.read()
        except HTTPError as e:
            return e.code, e.read()

    def test_upload_store_open_reanalyse_download_delete(self):
        batch = "fedcba9876543210"
        self.call(f"/api/upload?batch={batch}", raw=WEB.encode(), headers={"X-Filename": "web_access.log"})
        code, body = self.call("/api/analyze-batch", {"batch": batch, "name": "WEB01 access log"})
        self.assertEqual(code, 200, body)
        r = json.loads(body)
        aid = r["analysis_id"]
        self.assertTrue(r["stored"])
        items = json.loads(self.call("/api/history")[1])["items"]
        self.assertEqual(items[0]["id"], aid)
        self.assertEqual(items[0]["name"], "WEB01 access log")
        self.assertEqual(items[0]["files"][0]["name"], "web_access.log")
        self.assertFalse((config_store.UPLOAD_DIR / batch).exists(), "upload moved into the history")
        code, data = self.call(f"/api/history/file?id={aid}&name=web_access.log")
        self.assertEqual((code, data.decode()), (200, WEB))
        self.assertEqual(self.call(f"/api/history/file?id={aid}&name=..%2Fmeta.json")[0], 404)

        # verdict via the UI endpoint is stored with the analysis and in the memory
        fid = next(f["fid"] for f in r["findings"] if f["rule_id"] == "TG-WEB-009")
        code, body = self.call("/api/feedback", {"analysis_id": aid, "fid": fid, "verdict": "true_positive", "note": "confirmed"})
        self.assertEqual(code, 200, body)
        self.assertGreaterEqual(json.loads(body)["learned"], 1)

        # reputation through the API (mock services), saved with the analysis
        cands = json.loads(self.call("/api/reputation/candidates", {"analysis_id": aid})[1])
        self.assertIn("203.0.113.50", [c["value"] for c in cands["candidates"]])
        code, body = self.call("/api/reputation/check", {"analysis_id": aid, "value": "203.0.113.50"})
        self.assertEqual(json.loads(body)["verdict"], "malicious")
        self.assertEqual(self.call("/api/reputation/check", {"value": "10.0.0.1"})[0], 422)

        # open after the in-memory cache is gone: comes back from disk with the additions
        agent._ANALYSES.clear()
        opened = json.loads(self.call("/api/history/open", {"id": aid})[1])
        self.assertIn("203.0.113.50", opened["reputation"])
        self.assertEqual(next(f for f in opened["findings"] if f["fid"] == fid)["analyst_verdict"]["verdict"], "true_positive")

        code, body = self.call("/api/history/reanalyse", {"id": aid})
        self.assertEqual(code, 200, body)
        r2 = json.loads(body)
        self.assertNotEqual(r2["analysis_id"], aid)
        shell = next(f for f in r2["findings"] if f["rule_id"] == "TG-WEB-009")
        self.assertEqual(shell["analyst_verdict"]["verdict"], "true_positive")   # learned from the first run
        self.assertTrue(any(x["ip"] == "203.0.113.50" and x.get("seen_before") for x in r2["ip_profiles"]))

        self.assertEqual(json.loads(self.call("/api/history/delete", {"ids": [aid, r2["analysis_id"]]})[1])["deleted"], 2)
        self.assertEqual(self.call("/api/history/open", {"id": aid})[0], 404)
        self.assertFalse(any(x["analysis_id"] == aid for v in memory._load(memory.SIGHTINGS, {}).values() for x in v))

    def test_paste_is_stored_and_history_can_be_disabled(self):
        r = json.loads(self.call("/api/analyze", {"text": WEB, "name": "pasted web"})[1])
        self.assertEqual(history.meta(r["analysis_id"])["files"][0]["name"], "pasted_web.log")
        agent.Handler.cfg["history_enabled"] = False
        try:
            r2 = json.loads(self.call("/api/analyze", {"text": WEB})[1])
            self.assertFalse(r2["stored"])
        finally:
            agent.Handler.cfg["history_enabled"] = True
        self.assertFalse(list(config_store.UPLOAD_DIR.glob("paste-*")), "temporary paste files are removed")


if __name__ == "__main__":
    unittest.main()
