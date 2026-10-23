"""Security regression tests (VAPT findings). Each test reproduces an attack and checks it now fails."""
import copy
import http.client
import json
import os
import socket
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent  # noqa: E402
import branding  # noqa: E402
import config_store  # noqa: E402
import history  # noqa: E402
import live  # noqa: E402
import memory  # noqa: E402
import reputation  # noqa: E402
import rules  # noqa: E402
import trust  # noqa: E402
from test_siem_platform import DEMO_TRUST, Isolated  # noqa: E402


class ServerCase(Isolated):
    """Agent on a random port; cfg overrides per class."""
    CFG = {}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._cfgfile = agent.CONFIG_FILE
        agent.CONFIG_FILE = cls.tmp / "config.json"
        cfg = agent.load_config()
        cfg.update(base_url="http://127.0.0.1:9", host="127.0.0.1", access_token="", password_hash="",
                   live_enabled=False, history_enabled=True)
        cfg.update(cls.CFG)
        agent.Handler.cfg = cfg
        agent._LIVE.clear()
        agent._FAILS.clear()
        cls.cfg = cfg
        srv = type("S", (agent._BoundedThreads, ThreadingHTTPServer), {})
        cls.httpd = srv(("127.0.0.1", 0), agent.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        agent.CONFIG_FILE = cls._cfgfile
        agent._LIVE.clear()
        super().tearDownClass()

    def raw(self, method, path, body=b"", headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        h = {"Host": f"127.0.0.1:{self.port}"}
        if body:
            h["Content-Length"] = str(len(body))
        h.update(headers or {})
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in h.items():
            c.putheader(k, v)
        c.endheaders()
        if body:
            c.send(body)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data, r


class LocalModeTests(ServerCase):
    def test_dns_rebinding_get_refused(self):
        for path in ("/api/history", "/api/status", "/api/live/state", "/api/audit-log", "/", "/live"):
            code, _, _ = self.raw("GET", path, headers={"Host": "evil.example.com"})
            self.assertEqual(code, 403, path)
        self.assertEqual(self.raw("GET", "/api/status")[0], 200)
        self.assertEqual(self.raw("GET", "/api/status", headers={"Host": f"[::1]:{self.port}"})[0], 200)
        self.assertEqual(self.raw("POST", "/api/live/ingest", b"x", {"Host": "evil.example.com",
                                                                   "Content-Type": "text/plain"})[0], 403)

    def test_bad_content_length(self):
        for cl in ("-1", "abc", str(10 ** 12)):
            code, body, _ = self.raw("POST", "/api/config", b"{}", {"Content-Type": "application/json", "Content-Length": cl})
            self.assertEqual(code, 400, cl)

    def test_security_headers_and_csp_nonce(self):
        code, body, r = self.raw("GET", "/")
        csp = r.getheader("Content-Security-Policy")
        nonce = csp.split("'nonce-")[1].split("'")[0]
        self.assertIn(f'<script nonce="{nonce}">'.encode(), body)
        self.assertNotIn(b"<script>", body)
        self.assertNotIn("unsafe-inline' 'unsafe-eval", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        for h in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Cross-Origin-Opener-Policy"):
            self.assertTrue(r.getheader(h), h)
        self.assertNotIn("Python", r.getheader("Server"))
        _, _, r2 = self.raw("GET", "/api/status")
        self.assertIn("default-src 'none'", r2.getheader("Content-Security-Policy"))
        _, page2, r3 = self.raw("GET", "/")
        self.assertNotEqual(r3.getheader("Content-Security-Policy"), csp)     # fresh nonce per page

    def test_ssrf_base_url(self):
        for bad in ("file:///etc/passwd", "http://169.254.169.254/latest/meta-data/", "ftp://x/",
                    "http://user:pw@127.0.0.1:11434", "http://127.0.0.1:11434/#x", "gopher://127.0.0.1:70/",
                    "http://metadata.google.internal/"):
            code, body, _ = self.raw("POST", "/api/config", json.dumps({"base_url": bad}).encode(),
                                     {"Content-Type": "application/json"})
            self.assertEqual(code, 400, bad)
        self.cfg["api_key"] = "secret-key"
        self.raw("POST", "/api/config", json.dumps({"base_url": "http://10.9.9.9:1234/v1"}).encode(),
                 {"Content-Type": "application/json"})
        self.assertEqual(self.cfg["api_key"], "", "the stored key is never sent to a new host")
        with self.assertRaises(Exception):
            agent._OPENER.open("file:///etc/passwd")

    def test_client_supplied_analysis_never_persisted(self):
        fake = {"analysis_id": "ab" * 8, "findings": [{"fid": "F-01", "rule_id": "TG-X", "title": "forged"}]}
        code, _, _ = self.raw("POST", "/api/feedback", json.dumps({"analysis": fake, "fid": "F-01",
                                                                    "verdict": "true_positive"}).encode(),
                              {"Content-Type": "application/json"})
        self.assertEqual(code, 400)
        self.assertEqual(memory.verdicts(), [])

    def test_atomic_private_config(self):
        agent.save_config(dict(self.cfg, temperature=0.33), ("temperature",))
        self.assertEqual(os.stat(agent.CONFIG_FILE).st_mode & 0o777, 0o600)
        agent.CONFIG_FILE.write_text("{broken")
        agent.save_config(dict(self.cfg, temperature=0.2), ("temperature",))
        self.assertTrue(list(agent.CONFIG_FILE.parent.glob("config.json.broken-*")), "unreadable file kept, not overwritten")


class AuthTests(ServerCase):
    CFG = {"host": "0.0.0.0", "access_token": "tok-abc-123456"}

    def test_unauthenticated_body_not_read(self):
        code, _, _ = self.raw("POST", "/api/analyze", b"x" * 1000, {"Content-Type": "application/json",
                                                                     "Content-Length": str(20 * 1024 * 1024)})
        self.assertEqual(code, 401)
        code, body, _ = self.raw("POST", "/api/login", b"{}", {"Content-Type": "application/json",
                                                              "Content-Length": str(1024 * 1024)})
        self.assertEqual(code, 400)        # pre-login bodies capped at 64 KB

    def test_parallel_login_burst_cannot_exceed_limit(self):
        agent._FAILS.clear()
        body = json.dumps({"token": "wrong"}).encode()

        def attempt(_):
            return self.raw("POST", "/api/login", body, {"Content-Type": "application/json"})[0]
        with ThreadPoolExecutor(30) as ex:
            codes = list(ex.map(attempt, range(30)))
        self.assertEqual(codes.count(401), agent.LOCKOUT[0])
        self.assertEqual(codes.count(429), 30 - agent.LOCKOUT[0])
        ok = self.raw("POST", "/api/login", json.dumps({"token": "tok-abc-123456"}).encode(),
                      {"Content-Type": "application/json"})[0]
        self.assertEqual(ok, 429)          # locked even with the right token
        agent._FAILS.clear()

    def test_session_cookie_and_sign_out_everywhere(self):
        agent._FAILS.clear()
        code, _, r = self.raw("POST", "/api/login", json.dumps({"token": "tok-abc-123456"}).encode(),
                              {"Content-Type": "application/json"})
        cookie = r.getheader("Set-Cookie").split(";")[0]
        self.assertNotIn("tok-abc-123456", cookie)
        self.assertEqual(self.raw("GET", "/api/status", headers={"Cookie": cookie})[0], 200)
        self.assertEqual(self.raw("GET", "/api/status", headers={"Cookie": "tg_token=tok-abc-123456"})[0], 401)
        self.assertEqual(self.raw("GET", "/api/status", headers={"X-Agent-Token": "tok-abc-123456"})[0], 200)
        _, _, r = self.raw("POST", "/api/logout", json.dumps({"everywhere": True}).encode(),
                           {"Content-Type": "application/json", "Cookie": cookie})
        self.assertEqual(len(r.headers.get_all("Set-Cookie")), 2)
        self.assertEqual(self.raw("GET", "/api/status", headers={"Cookie": cookie})[0], 401)   # revoked
        forged = cookie.split("=", 1)[0] + "=token-user|9999999999|" + "0" * 64
        self.assertEqual(self.raw("GET", "/api/status", headers={"Cookie": forged})[0], 401)

    def test_slow_client_does_not_hold_the_server(self):
        self.assertLessEqual(agent.Handler.timeout, 60)
        s = socket.create_connection(("127.0.0.1", self.port))
        s.sendall(b"GET /api/status HTTP/1.1\r\nHost: x\r\n")      # never finishes the request
        self.assertEqual(self.raw("GET", "/api/status", headers={"X-Agent-Token": "tok-abc-123456"})[0], 200)
        s.close()


class FakeBadIntel(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if "redirect" in self.path or "203.0.113.11" in self.path:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/steal")
            self.end_headers()
            return
        if "203.0.113.12" in self.path:
            body = b'{"pulse_info": {"count": 0}, "x": "' + b"A" * (3 * 1024 * 1024) + b'"}'
        else:
            body = json.dumps({"pulse_info": {"count": 5, "pulses": []}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        body = json.dumps({"query_status": "ok", "threat": "malware_download", "url_status": "online",
                           "urlhaus_reference": "javascript:alert(document.domain)"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class IntelHardeningTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeBadIntel)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        b = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.cfg = {"otx_key": "O" * 64, "abusech_key": "K" * 48, "otx_url": b + "/otx", "urlhaus_url": b + "/uh",
                   "threatfox_url": b + "/tf", "reputation_allow_documentation": True, "otx_per_min": 6000,
                   "urlhaus_per_min": 6000, "threatfox_per_min": 6000}

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        super().tearDownClass()

    def test_redirects_refused_and_big_bodies_rejected(self):
        r = reputation.lookup(self.cfg, "203.0.113.11", force=True)          # OTX answers with a redirect
        self.assertEqual(r["otx"]["level"], "error")
        r = reputation.lookup(self.cfg, "203.0.113.12", force=True)          # 3 MB answer
        self.assertEqual(r["otx"]["level"], "error")

    def test_javascript_links_dropped(self):
        r = reputation.lookup(self.cfg, "http://203.0.113.13/x", force=True)
        self.assertIsNone(r["urlhaus"]["link"])
        self.assertTrue(all((s["link"] or "").startswith(("http", "")) and not (s["link"] or "").startswith("javascript")
                            for s in r["sources"]))

    def test_embedded_internal_addresses_and_credentials(self):
        for v in ("::ffff:10.0.0.1", "64:ff9b::a00:1", "2002:a00:1::", "http://[::ffff:192.168.1.1]/x"):
            with self.assertRaises(reputation.RefusedError, msg=v):
                reputation.classify(v)
        self.assertEqual(reputation.classify("http://admin:secret@8.8.8.8/x?y=1"), ("url", "http://8.8.8.8/x?y=1"))


class TrustHardeningTests(Isolated):
    def test_translation_ranges_refused(self):
        for cidr in ("::ffff:0:0/96", "64:ff9b::/96", "2002::/16", "2001:db8::/20"):
            with self.assertRaises(ValueError, msg=cidr):
                trust.validate_entry("trusted_networks", {"name": "x", "cidr": cidr})

    def test_mapped_address_classified_as_ipv4(self):
        inv = trust.Inventory(copy.deepcopy(DEMO_TRUST))
        self.assertEqual(inv.classify("::ffff:203.0.113.50")["category"], "public_unknown")
        self.assertEqual(inv.classify("::ffff:192.0.2.22")["category"], inv.classify("192.0.2.22")["category"])

    def test_rule_override_values_validated(self):
        p = config_store.CONFIG_DIR / "detection_rules.json"
        p.write_text(json.dumps({"rules": {"TG-AUTH-001": {"severity": 'x" onmouseover="alert(1)', "confidence": "zz",
                                                          "threshold": {"failures": "1; rm -rf /", "nope": 3}}}}))
        try:
            rs, errs = rules.load()
            self.assertIn(rs["TG-AUTH-001"]["severity"], ("critical", "high", "medium", "low", "info"))
            self.assertEqual(len(errs), 2)
            self.assertNotIn("nope", rs["TG-AUTH-001"]["threshold"])
        finally:
            p.unlink()


class LiveHardeningTests(Isolated):
    def engine(self, **cfg):
        return live.LiveEngine(dict({"live_enabled": True}, **cfg), lambda files: {"findings": []})

    def test_allow_list_applies_to_http(self):
        e = self.engine(live_allowed_sources=["10.0.0.0/8"])
        with self.assertRaises(PermissionError):
            e.ingest_http(b"x", "text/plain", "203.0.113.9")
        self.assertEqual(e.ingest_http(b"x", "text/plain", "10.1.2.3"), 1)

    def test_nested_json_and_long_lines(self):
        e = self.engine()
        with self.assertRaises(ValueError):
            e.ingest_http(b"[" * 100000 + b"]" * 100000, "application/json", "x")
        e.ingest_http(b"A" * 500000, "text/plain", "x")
        self.assertLessEqual(len(e.events[-1][4]), live.MAX_LINE)

    def test_memory_budget(self):
        e = self.engine(live_max_mb=1)
        for _ in range(200):
            e.ingest_http(b"B" * 15000, "text/plain", "x")
        self.assertLessEqual(e.bytes, 1024 * 1024)
        self.assertEqual(e.bytes, sum(len(r[4]) for r in e.events))

    def test_tcp_framing_is_linear(self):
        e = self.engine()
        t = time.time()
        rest = e._tcp_frames(b"a\n" * 200000, "x")
        self.assertLess(time.time() - t, 2.0)
        self.assertEqual(rest, b"")
        self.assertEqual(e.received["syslog"], 200000)

    def test_spool_budget(self):
        import shutil
        shutil.rmtree(config_store.DATA_DIR / "live", ignore_errors=True)
        e = self.engine(live_spool_max_mb=0.05)
        for _ in range(120):
            e.ingest_http(b"C" * 2000, "text/plain", "x")
        total = sum(p.stat().st_size for p in (config_store.DATA_DIR / "live").glob("*.jsonl"))
        self.assertLess(total, 0.05 * 1024 * 1024 + 50 * 2100)
        self.assertTrue(any("budget" in x for x in e.errors))

    def test_syslog_tcp_idle_and_connection_cap(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        e = self.engine(live_syslog_port=port, live_syslog_host="127.0.0.1")
        e.start_syslog()
        try:
            self.assertIn("listening", e.syslog_status)
            socks = [socket.create_connection(("127.0.0.1", port)) for _ in range(live.MAX_TCP_CLIENTS + 10)]
            time.sleep(0.3)
            self.assertLessEqual(threading.active_count(), 30 + live.MAX_TCP_CLIENTS + 10)
            for x in socks:
                x.close()
        finally:
            e.stop()


class LearningHardeningTests(Isolated):
    def test_planted_domains_and_trusted_ips_not_learned(self):
        trust_file = config_store.CONFIG_DIR / "trusted_assets.json"
        trust_file.write_text(json.dumps(DEMO_TRUST))
        try:
            f = {"rule_id": "TG-WEB-009", "title": "x", "ips": ["203.0.113.50", "198.51.100.2"],
                 "samples": [{"text": "GET /?q=office365.com http://203.0.113.61/x.sh"}], "evidence": []}
            result = {"iocs": {"domains": ["office365.com"], "urls": ["http://203.0.113.61/x.sh"], "hashes": []},
                      "evidence": []}
            memory.record_verdict(f, "true_positive", "", "t", "a" * 16, result)
            learned = {x["value"] for x in memory.learned_indicators()}
            self.assertIn("203.0.113.50", learned)
            self.assertIn("http://203.0.113.61/x.sh", learned)
            self.assertNotIn("office365.com", learned)              # bare domains are not learned
            self.assertNotIn("198.51.100.2", learned)               # own public web server never learned
            # a false-positive verdict on a user named like an indicator can't clear the indicator
            memory.record_verdict({"rule_id": "TG-X", "users": ["http://203.0.113.61/x.sh"], "title": "y"},
                                  "false_positive", "", "t", "b" * 16, None)
            self.assertIn("http://203.0.113.61/x.sh", {x["value"] for x in memory.learned_indicators()})
        finally:
            memory.forget_all("t")
            trust_file.unlink()


class FileHardeningTests(Isolated):
    def test_truncated_png_is_a_clean_error(self):
        with self.assertRaises(ValueError):
            branding.check_logo(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x01")

    def test_delete_forgets_derived_data(self):
        r = {"analysis_id": "c" * 16, "findings": [{"rule_id": "TG-WEB-009"}],
             "ip_profiles": [{"ip": "203.0.113.50", "public": True, "verdict": "Malicious"}], "iocs": {}}
        history.save(r, "paste", "x")
        memory.record_sightings(r, "x")
        self.assertIn("203.0.113.50", memory._load(memory.SIGHTINGS, {}))
        history.delete("c" * 16, "t")
        self.assertNotIn("203.0.113.50", memory._load(memory.SIGHTINGS, {}))
        self.assertNotIn("c" * 16, memory._load(memory.RULE_STATS, {}).get("_analyses", {}))

    def test_private_directories(self):
        config_store.ensure_dirs()
        for d in (config_store.CONFIG_DIR, config_store.DATA_DIR, config_store.UPLOAD_DIR):
            self.assertEqual(os.stat(d).st_mode & 0o777, 0o700, d)


if __name__ == "__main__":
    unittest.main()
