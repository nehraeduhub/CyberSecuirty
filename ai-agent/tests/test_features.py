import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent  # noqa: E402
import detector  # noqa: E402
import host_audit  # noqa: E402
import knowledge  # noqa: E402
import report_pdf  # noqa: E402

AUTH = (ROOT / "samples" / "auth.log").read_text()


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.r = detector.analyze(AUTH)

    def test_every_finding_has_advice(self):
        for f in self.r["findings"]:
            self.assertTrue(f["description"] and f["recommendation"], f["id"])
            self.assertTrue(any("attack.mitre.org" in x for x in f["references"]), f["id"])

    def test_attacker_profile_and_iocs(self):
        top = self.r["ip_profiles"][0]
        self.assertEqual(top["ip"], "203.0.113.45")
        self.assertEqual(top["verdict"], "Malicious")
        self.assertIn("http://203.0.113.45/x.sh", self.r["iocs"]["urls"])
        self.assertIn("/tmp/.kworker", self.r["iocs"]["files"])
        self.assertIn("root", self.r["iocs"]["users"])

    def test_timeline_and_grade(self):
        self.assertTrue(self.r["timeline"])
        self.assertEqual(self.r["grade"], "F")
        self.assertEqual(detector.analyze("hello")["grade"], "A")

    def test_lan_addresses_are_internal(self):
        self.assertFalse(knowledge.is_public_ip("192.168.1.20"))
        self.assertTrue(knowledge.is_public_ip("203.0.113.45"))
        self.assertFalse(knowledge.valid_ip("999.1.1.1"))


class InstantAnswerTests(unittest.TestCase):
    def test_block_commands_cover_platforms(self):
        md = agent.instant_answer("block", detector.analyze(AUTH))
        for needle in ("ufw insert 1 deny from 203.0.113.45", "iptables -I INPUT -s 203.0.113.45",
                       "New-NetFirewallRule"):
            self.assertIn(needle, md)

    def test_playbook_and_explain(self):
        r = detector.analyze(AUTH)
        self.assertIn("Immediate", agent.instant_answer("playbook", r))
        self.assertIn("What to do", agent.instant_answer("explain", r, 0))

    def test_block_rejects_non_ips(self):
        self.assertNotIn("1.8.2.0.1", knowledge.block_commands(["1.8.2.0.1", "x"]))


class AgentTests(unittest.TestCase):
    def test_strip_thinking_across_chunks(self):
        chunks = ["Hi <thi", "nk>hidden</th", "ink>answer"]
        self.assertEqual("".join(agent._strip_thinking(iter(chunks))), "Hi answer")
        self.assertEqual("".join(agent._strip_thinking(iter(["a < b > c"]))), "a < b > c")

    def test_context_is_compact(self):
        big = detector.analyze((ROOT / "samples" / "access.log").read_text() * 300)
        self.assertLess(len(detector.ai_context(big)), 5000)


class HostAuditTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux only")
    def test_audit_runs_and_scores(self):
        r = host_audit.run_audit(include_logs=False)
        self.assertEqual(r["kind"], "host")
        self.assertGreaterEqual(len(r["checks_run"]), 10)
        self.assertIn(r["grade"], "ABCDEF")
        for f in r["findings"]:
            self.assertIn(f["severity"], detector.SEVERITIES)

    def test_sysctl_check_reports_bad_value(self):
        a = host_audit.Audit()
        orig = host_audit._read
        host_audit._read = lambda p, limit=None: "0\n" if "randomize_va_space" in p else None
        try:
            host_audit.check_sysctl(a)
        finally:
            host_audit._read = orig
        self.assertEqual([f["id"] for f in a.findings], ["sysctl_kernel_randomize_va_space"])


class OptionalDependencyTests(unittest.TestCase):
    def test_agent_imports_without_reportlab(self):
        import subprocess
        code = "import sys; sys.modules['reportlab'] = None; import agent; print(agent.report_pdf.AVAILABLE)"
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "False", out.stderr)


@unittest.skipUnless(report_pdf.AVAILABLE, "reportlab not installed")
class PdfTests(unittest.TestCase):
    def test_pdf_for_logs_host_and_empty(self):
        ai = "## Summary\nThe host was **compromised** via SSH brute force from 203.0.113.45 and a miner installed. 🚨\n```bash\nufw deny from 203.0.113.45\n```"
        for result in (detector.analyze(AUTH), detector.analyze("nothing"), host_audit.run_audit(include_logs=False)):
            pdf = report_pdf.build_pdf(result, {"client": "<ACME & Co>"}, ai)
            self.assertTrue(pdf.startswith(b"%PDF"))
            self.assertGreater(len(pdf), 5000)


class LanAddressTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux only")
    def test_ip_found_on_offline_server(self):
        """No default route + hostname mapped to 127.0.1.1 must still list the interface IPs."""
        import socket
        normal = agent.lan_addresses()

        class NoRoute(socket.socket):
            def connect(self, *a):
                raise OSError(101, "Network is unreachable")

        orig = socket.socket
        socket.socket = NoRoute
        try:
            offline = agent.lan_addresses()
        finally:
            socket.socket = orig
        self.assertEqual(offline, normal)
        self.assertFalse(any(ip.startswith("127.") for ip in offline))


class NetworkAccessTests(unittest.TestCase):
    """Running on the host IP: token login required, settings file keeps host/port."""

    def setUp(self):
        import json
        import tempfile
        import threading
        from http.server import ThreadingHTTPServer
        self.json = json
        self.tmp = Path(tempfile.mkdtemp()) / "config.json"
        self.tmp.write_text(json.dumps({"host": "0.0.0.0", "port": 0, "access_token": "s3cret"}))
        self._orig = agent.CONFIG_FILE
        agent.CONFIG_FILE = self.tmp
        cfg = agent.load_config()
        cfg["base_url"] = "http://127.0.0.1:9"  # no AI needed for these tests
        agent.Handler.cfg = cfg
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        agent.CONFIG_FILE = self._orig

    def req(self, path, body=None, cookie=None):
        from urllib.error import HTTPError
        from urllib.request import Request
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        data = self.json.dumps(body).encode() if body is not None else None
        try:
            with agent._OPENER.open(Request(self.base + path, data=data, headers=headers), timeout=10) as r:
                return r.status, r.read(), r.headers
        except HTTPError as e:
            return e.code, e.read(), e.headers

    def test_login_required(self):
        code, body, _ = self.req("/")
        self.assertIn(b"Sign in", body)
        self.assertEqual(self.req("/api/status")[0], 401)
        self.assertEqual(self.req("/api/analyze", {"text": "x"})[0], 401)

    def test_login_sets_cookie_and_unlocks(self):
        code, _, headers = self.req("/api/login", {"token": "s3cret"})
        self.assertEqual(code, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        code, body, _ = self.req("/api/analyze", {"text": AUTH}, cookie="tg_token=s3cret")
        self.assertEqual(code, 200)
        self.assertNotIn(b"s3cret", self.req("/api/status", cookie="tg_token=s3cret")[1])

    def test_saving_settings_keeps_host_and_port(self):
        self.req("/api/config", {"temperature": 0.4}, cookie="tg_token=s3cret")
        saved = self.json.loads(self.tmp.read_text())
        self.assertEqual((saved["host"], saved["access_token"], saved["temperature"]), ("0.0.0.0", "s3cret", 0.4))


if __name__ == "__main__":
    unittest.main()
