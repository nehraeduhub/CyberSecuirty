"""Threat-intel sources (mocked: OTX, URLhaus, ThreatFox, MalwareBazaar, PhishTank, CIRCL) and live SIEM analysis."""
import json
import socket
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent  # noqa: E402
import config_store  # noqa: E402
import history  # noqa: E402
import live  # noqa: E402
import pipeline  # noqa: E402
import reputation  # noqa: E402
from test_siem_platform import SIEM, Isolated  # noqa: E402

BAD_URL = "http://203.0.113.61/x.sh"
BAD_HASH = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


class FakeSources(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode() if n else ""
        if "json" in (self.headers.get("Content-Type") or ""):
            return json.loads(raw or "{}")
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        FakeSources.calls.append(("GET", self.path, dict(self.headers), None))
        if self.path.startswith("/otx/"):
            if self.headers.get("X-OTX-API-KEY") != "O" * 64:
                return self._json(403, {})
            n = 7 if ("203.0.113.50" in self.path or "x.sh" in self.path) else 0
            return self._json(200, {"pulse_info": {"count": n, "pulses": [
                {"name": "Web shell campaign", "tags": ["webshell"], "malware_families": [{"display_name": "China Chopper"}]}] * min(n, 2)}})
        if self.path.startswith("/circl/cve/"):
            cve = self.path.rsplit("/", 1)[-1]
            if cve != "CVE-2021-44228":
                return self._json(404, {})
            return self._json(200, {"cveMetadata": {"datePublished": "2021-12-10T00:00:00"}, "containers": {"cna": {
                "descriptions": [{"lang": "en", "value": "Apache Log4j2 JNDI features do not protect against attacker controlled LDAP."}],
                "affected": [{"vendor": "Apache Software Foundation", "product": "Apache Log4j2"}],
                "metrics": [{"cvssV3_1": {"baseScore": 10.0, "baseSeverity": "CRITICAL", "vectorString": "CVSS:3.1/AV:N"}}],
                "references": [{"url": "https://logging.apache.org/log4j/2.x/security.html"}]}}})
        self._json(404, {})

    def do_POST(self):
        body = self._body()
        FakeSources.calls.append(("POST", self.path, dict(self.headers), body))
        if self.path.startswith(("/urlhaus/", "/threatfox/", "/mb/")) and self.headers.get("Auth-Key") != "K" * 48:
            return self._json(401, {})
        if self.path == "/urlhaus/url/":
            if body.get("url") == BAD_URL:
                return self._json(200, {"query_status": "ok", "threat": "malware_download", "url_status": "online",
                                        "tags": ["elf", "mirai"], "urlhaus_reference": "https://urlhaus.abuse.ch/url/1/"})
            return self._json(200, {"query_status": "no_results"})
        if self.path == "/urlhaus/host/":
            return self._json(200, {"query_status": "no_results"})
        if self.path == "/urlhaus/payload/":
            return self._json(200, {"query_status": "no_results"})
        if self.path == "/threatfox/":
            term = body.get("search_term") or body.get("hash")
            if term in ("203.0.113.50", BAD_HASH):
                return self._json(200, {"query_status": "ok", "data": [{"malware_printable": "Cobalt Strike",
                                        "threat_type": "botnet_cc", "threat_type_desc": "Botnet C2", "confidence_level": 90}]})
            return self._json(200, {"query_status": "no_result"})
        if self.path == "/mb/":
            if body.get("hash") == BAD_HASH:
                return self._json(200, {"query_status": "ok", "data": [{"sha256_hash": BAD_HASH, "signature": "AgentTesla",
                                        "file_type": "exe", "first_seen": "2026-10-01 10:00:00"}]})
            return self._json(200, {"query_status": "hash_not_found"})
        if self.path == "/phish/":
            if not self.headers.get("User-Agent", "").startswith("phishtank/"):
                return self._json(403, {})
            hit = "login-verify" in body.get("url", "")
            return self._json(200, {"results": {"in_database": hit, "verified": hit, "valid": hit,
                                                "phish_detail_page": "https://phishtank.org/phish_detail.php?phish_id=1"}})
        self._json(404, {})


class IntelSourceTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeSources)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        b = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.cfg = {"otx_key": "O" * 64, "abusech_key": "K" * 48, "phishtank_enabled": True, "circl_enabled": True,
                   "otx_url": b + "/otx", "urlhaus_url": b + "/urlhaus", "threatfox_url": b + "/threatfox",
                   "malwarebazaar_url": b + "/mb", "phishtank_url": b + "/phish/", "circl_url": b + "/circl",
                   "reputation_allow_documentation": True}
        for p in reputation.SOURCES:
            cls.cfg[f"{p}_per_min"] = 6000

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        super().tearDownClass()

    def test_providers_in_order(self):
        self.assertEqual(reputation.providers(self.cfg), ["otx", "urlhaus", "threatfox", "malwarebazaar", "phishtank", "circl"])
        self.assertEqual(reputation.providers({}), [])

    def test_url_sources(self):
        r = reputation.lookup(self.cfg, BAD_URL)
        self.assertEqual(r["verdict"], "malicious")
        names = [s["name"] for s in r["sources"]]
        self.assertEqual(names[0], "otx")                       # OTX first
        self.assertTrue({"otx", "urlhaus", "threatfox", "phishtank"} <= set(names))
        self.assertIn("malware_download", r["urlhaus"]["text"])
        self.assertEqual(r["otx"]["level"], "malicious")
        self.assertIn("China Chopper", r["otx"]["text"])
        phish = reputation.lookup(self.cfg, "http://203.0.113.80/login-verify")
        self.assertEqual(phish["phishtank"]["level"], "malicious")
        self.assertIn("verified phishing", phish["summary"])

    def test_hash_and_ip_sources(self):
        h = reputation.lookup(self.cfg, BAD_HASH.upper())
        self.assertEqual(h["type"], "hash")
        self.assertEqual(h["malwarebazaar"]["signature"], "AgentTesla")
        self.assertIn("Cobalt Strike", h["threatfox"]["text"])
        self.assertEqual(h["verdict"], "malicious")
        ip = reputation.lookup(self.cfg, "203.0.113.50")
        self.assertEqual(ip["verdict"], "malicious")
        self.assertNotIn("malwarebazaar", ip)                    # hash-only source not asked
        clean = reputation.lookup(self.cfg, "203.0.113.7")
        self.assertEqual(clean["verdict"], "no known abuse")

    def test_cve(self):
        r = reputation.lookup(self.cfg, "cve-2021-44228")
        self.assertEqual(r["type"], "cve")
        self.assertEqual(r["circl"]["cvss"], 10.0)
        self.assertEqual(r["verdict"], "vulnerability (critical)")
        self.assertIn("Log4j2", r["summary"])
        self.assertEqual(reputation.lookup(self.cfg, "CVE-2099-0001")["verdict"], "unknown")

    def test_only_lookups_and_refusals(self):
        FakeSources.calls.clear()
        reputation.lookup(self.cfg, "http://203.0.113.90/a", force=True)
        posts = [c[1] for c in FakeSources.calls if c[0] == "POST"]
        self.assertTrue(set(posts) <= {"/urlhaus/url/", "/threatfox/", "/phish/"}, posts)   # query endpoints only
        with self.assertRaises(reputation.RefusedError):
            reputation.lookup(self.cfg, "http://10.0.0.5/admin")
        with self.assertRaises(ValueError):                      # no source configured for hashes
            reputation.lookup({"circl_enabled": True}, BAD_HASH)

    def test_bad_key(self):
        cfg = dict(self.cfg, abusech_key="Z" * 48)
        r = reputation.lookup(cfg, "http://203.0.113.91/b", force=True)
        self.assertIn("rejected the API key", r["urlhaus"]["error"])

    def test_candidates_find_hashes_and_cves(self):
        res = {"iocs": {"hashes": [BAD_HASH], "urls": [], "domains": []}, "ip_profiles": [],
               "findings": [{"title": "Log4Shell (JNDI) exploit attempt", "references": ["CVE-2021-44228"], "samples": []}],
               "evidence": [{"raw": "ET EXPLOIT Apache Struts CVE-2017-5638 attempt"}]}
        c = {x["value"]: x["type"] for x in reputation.candidates(res)}
        self.assertEqual(c, {BAD_HASH: "hash", "CVE-2021-44228": "cve", "CVE-2017-5638": "cve"})


def _window_lines():
    vpn = (SIEM / "vpn.log").read_text().splitlines()
    web = (SIEM / "web_access.log").read_text().splitlines()
    return [ln for ln in vpn if "Oct 18" in ln] + [ln for ln in web if "18/Oct/2026:02" in ln]


class LiveEngineTests(Isolated):
    def engine(self, **cfg):
        c = dict({"live_enabled": True, "live_window_minutes": 60, "live_interval_s": 3600}, **cfg)
        return live.LiveEngine(c, lambda files: pipeline.to_json(pipeline.analyze_files(files, learn_baseline=False)))

    def test_ingest_formats(self):
        e = self.engine()
        self.assertEqual(e.ingest_http(b"line one\nline two\n", "text/plain", "1.2.3.4"), 2)
        self.assertEqual(e.ingest_http(json.dumps([{"src_ip": "203.0.113.9"}, {"src_ip": "203.0.113.10"}]),
                                       "application/json", "1.2.3.4"), 2)
        self.assertEqual(e.ingest_http(json.dumps({"search_name": "x", "result": {"_raw": "Oct 18 02:55:07 vpn01 test"}}),
                                       "application/json", "1.2.3.4"), 1)      # Splunk webhook
        self.assertEqual(e.ingest_http(b'{"a":1}\n{"b":2}\n', "application/x-ndjson", "1.2.3.4"), 2)
        self.assertEqual(e.ingest_http(json.dumps({"events": [{"a": 1}, {"a": 2}, {"a": 3}]}), "application/json", "x"), 3)
        with self.assertRaises(ValueError):
            e.ingest_http(b"{not json", "application/json", "x")
        kinds = [r[3] for r in e.events]
        self.assertEqual(kinds[:2], ["text", "text"])
        self.assertEqual(kinds[4], "text")                                   # Splunk _raw kept as a log line
        self.assertEqual(e.received["http"], 10)
        self.assertTrue(list((config_store.DATA_DIR / "live").glob("*.jsonl")), "spooled to disk")

    def test_analysis_alerts_and_flags(self):
        e = self.engine()
        e.ingest_http("\n".join(_window_lines()).encode(), "text/plain", "10.0.0.5")
        e.analyse()
        st = e.state()
        titles = [a["title"] for a in st["alerts"]]
        self.assertTrue(any("Web shell" in t for t in titles), titles)
        self.assertTrue(any("spraying" in t.lower() for t in titles), titles)
        self.assertTrue(all(a["status"] == "new" for a in st["alerts"]))
        self.assertTrue(any(l["rules"] for l in st["stream"]), "evidence lines flagged in the stream")
        # the same alert again only updates it; ack keeps it acknowledged
        k = st["alerts"][0]["key"]
        e.ack(k)
        e.ingest_http(_window_lines()[-1].encode(), "text/plain", "10.0.0.5")
        e.analyse()
        a = next(x for x in e.state()["alerts"] if x["key"] == k)
        self.assertEqual(a["status"], "acknowledged")
        self.assertGreaterEqual(a["times_seen"], 2)
        # restart: the window is reloaded from the spool
        e2 = self.engine()
        e2._reload_spool()
        self.assertEqual(len(e2.window()), len(e.window()))

    def test_syslog_udp_tcp_and_allow_list(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        e = self.engine(live_syslog_port=port, live_syslog_host="127.0.0.1")
        e.start_syslog()
        try:
            self.assertIn("listening", e.syslog_status)
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.sendto(b"<34>Oct 18 02:55:07 vpn01 vpnd[331]: event=auth_failure user=alice src_ip=203.0.113.77", ("127.0.0.1", port))
            u.close()
            t = socket.create_connection(("127.0.0.1", port))
            msg = b"<34>Oct 18 02:55:14 vpn01 vpnd[331]: event=auth_failure user=bob src_ip=203.0.113.77"
            t.sendall(str(len(msg)).encode() + b" " + msg + b"line two from tcp\n")   # octet-counted + newline frame
            t.close()
            for _ in range(50):
                if e.received["syslog"] >= 3:
                    break
                time.sleep(0.05)
            self.assertEqual(e.received["syslog"], 3)
            e.cfg["live_allowed_sources"] = ["10.0.0.0/8"]
            self.assertEqual(e.ingest_syslog(b"x", "127.0.0.1"), 0)
            self.assertEqual(e.received["dropped"], 1)
        finally:
            e.stop()


class LiveApiTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cfg = agent.load_config()
        cfg.update(base_url="http://127.0.0.1:9", access_token="", password_hash="", host="127.0.0.1",
                   live_enabled=False, live_token="", live_interval_s=3600, history_enabled=True)
        agent.Handler.cfg = cfg
        agent._LIVE.clear()
        cls.cfg_path = agent.CONFIG_FILE
        agent.CONFIG_FILE = cls.tmp / "config.json"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        agent.CONFIG_FILE = cls.cfg_path
        agent._LIVE.clear()
        super().tearDownClass()

    def call(self, path, body=None, raw=None, headers=None, ctype="application/json"):
        from urllib.error import HTTPError
        from urllib.request import Request
        h = dict({"Content-Type": ctype}, **(headers or {}))
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        try:
            with agent._OPENER.open(Request(self.base + path, data=data, headers=h), timeout=60) as r:
                return r.status, json.loads(r.read() or b"{}")
        except HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_live_flow(self):
        code, _ = self.call("/api/live/ingest", raw=b"x", ctype="text/plain")
        self.assertEqual(code, 403)                                       # off by default
        code, st = self.call("/api/live/control", {"action": "enable"})
        self.assertEqual(code, 200)
        token = st["setup"]["token"]
        self.assertTrue(len(token) >= 24)
        self.assertEqual(self.call("/api/live/ingest", raw=b"x", ctype="text/plain")[0], 401)
        self.assertEqual(self.call("/api/live/ingest", raw=b"x", ctype="text/plain",
                                   headers={"X-Ingest-Token": "wrong"})[0], 401)
        agent._FAILS.clear()
        code, r = self.call("/api/live/ingest", raw="\n".join(_window_lines()).encode(), ctype="text/plain",
                            headers={"X-Ingest-Token": token})
        self.assertEqual((code, r["accepted"]), (200, len(_window_lines())))
        code, r = self.call(f"/api/live/ingest?token={token}", {"result": {"src_ip": "203.0.113.50", "action": "deny",
                                                                           "dst_port": 22}, "search_name": "fw"})
        self.assertEqual(r["accepted"], 1)                                # Splunk webhook, token in the URL
        code, st = self.call("/api/live/control", {"action": "analyse"})
        self.assertEqual(code, 200)
        self.assertTrue(st["alerts"])
        self.assertGreater(st["new_alerts"], 0)
        code, snap = self.call("/api/live/control", {"action": "snapshot"})
        self.assertEqual(code, 200, snap)
        m = history.meta(snap["analysis_id"])
        self.assertEqual(m["kind"], "live")
        self.assertEqual({f["name"] for f in m["files"]}, {"live.log", "live.jsonl"})
        code, page = 200, (ROOT / "static" / "live.html").read_text()
        self.assertIn("Live SIEM analysis", page)
        self.assertEqual(self.call("/api/live/control", {"action": "nope"})[0], 400)
        self.call("/api/live/control", {"action": "disable"})
        self.assertEqual(self.call("/api/live/ingest", raw=b"x", ctype="text/plain",
                                   headers={"X-Ingest-Token": token})[0], 403)


if __name__ == "__main__":
    unittest.main()
