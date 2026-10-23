import sys
import time
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
        import config_store
        self._data = config_store.DATA_DIR, config_store.UPLOAD_DIR, config_store.AUDIT_LOG
        config_store.DATA_DIR = self.tmp.parent / "data"           # history, learning and audit stay in the temp dir
        config_store.UPLOAD_DIR = config_store.DATA_DIR / "uploads"
        config_store.AUDIT_LOG = config_store.DATA_DIR / "audit.log"
        self._orig = agent.CONFIG_FILE
        agent.CONFIG_FILE = self.tmp
        cfg = agent.load_config()
        cfg["base_url"] = "http://127.0.0.1:9"  # no AI needed for these tests
        agent.Handler.cfg = cfg
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        import config_store
        self.httpd.shutdown()
        agent.CONFIG_FILE = self._orig
        config_store.DATA_DIR, config_store.UPLOAD_DIR, config_store.AUDIT_LOG = self._data

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

    def token_session(self):
        agent._FAILS.clear()
        code, _, headers = self.req("/api/login", {"token": "s3cret"})
        self.assertEqual(code, 200)
        return headers["Set-Cookie"].split(";")[0]

    def test_login_sets_cookie_and_unlocks(self):
        code, _, headers = self.req("/api/login", {"token": "s3cret"})
        self.assertEqual(code, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertTrue(headers["Set-Cookie"].startswith("tg_session="))
        self.assertNotIn("s3cret", headers["Set-Cookie"])           # the cookie never carries the raw token
        self.assertEqual(self.req("/api/status", cookie="tg_token=s3cret")[0], 401)   # raw-token cookies refused
        cookie = headers["Set-Cookie"].split(";")[0]
        code, body, _ = self.req("/api/analyze", {"text": AUTH}, cookie=cookie)
        self.assertEqual(code, 200)
        self.assertNotIn(b"s3cret", self.req("/api/status", cookie=cookie)[1])

    def test_saving_settings_keeps_host_and_port(self):
        self.req("/api/config", {"temperature": 0.4}, cookie=self.token_session())
        saved = self.json.loads(self.tmp.read_text())
        self.assertEqual((saved["host"], saved["access_token"], saved["temperature"]), ("0.0.0.0", "s3cret", 0.4))



class PasswordLoginTests(NetworkAccessTests):
    """Username + password replaces the token; only a salted hash is stored."""

    def setUp(self):
        super().setUp()
        cfg = agent.Handler.cfg
        cfg.update(username="admin", password_hash=agent.hash_password("correct horse 9", rounds=1000),
                   session_secret="x" * 64)
        agent._FAILS.clear()

    def login(self, user="admin", pw="correct horse 9"):
        return self.req("/api/login", {"username": user, "password": pw})

    def session(self):
        code, _, headers = self.login()
        self.assertEqual(code, 200)
        cookie = headers["Set-Cookie"].split(";")[0]
        self.assertTrue(cookie.startswith("tg_session="))
        self.assertNotIn("correct horse", cookie)
        return cookie

    def test_login_required(self):
        code, body, _ = self.req("/")
        self.assertIn(b"Password", body)
        self.assertNotIn(b"Access token", body)
        self.assertEqual(self.req("/api/status")[0], 401)

    def test_login_sets_cookie_and_unlocks(self):
        cookie = self.session()
        self.assertEqual(self.req("/api/analyze", {"text": AUTH}, cookie=cookie)[0], 200)
        st = self.json.loads(self.req("/api/status", cookie=cookie)[1])
        self.assertEqual((st["login"], st["user"]), ("password", "admin"))

    def test_saving_settings_keeps_host_and_port(self):
        self.req("/api/config", {"temperature": 0.4}, cookie=self.session())
        saved = self.json.loads(self.tmp.read_text())
        self.assertEqual((saved["host"], saved["temperature"]), ("0.0.0.0", 0.4))

    def test_token_and_wrong_password_rejected(self):
        self.assertEqual(self.req("/api/login", {"token": "s3cret"})[0], 401)
        self.assertEqual(self.req("/api/status", cookie="tg_token=s3cret")[0], 401)
        self.assertEqual(self.login(pw="wrong password")[0], 401)
        self.assertEqual(self.login(user="root")[0], 401)

    def test_forged_expired_and_stale_sessions_rejected(self):
        cfg = agent.Handler.cfg
        good = agent.make_session(cfg, "admin")
        user, exp, sig = good.split("|")
        self.assertEqual(self.req("/api/status", cookie=f"tg_session=admin|{int(exp) + 999}|{sig}")[0], 401)
        self.assertIsNone(agent.check_session(cfg, f"admin|{int(time.time()) - 5}|{sig}"))
        cookie = self.session()
        cfg["password_hash"] = agent.hash_password("another pass 7", rounds=1000)  # password changed
        self.assertEqual(self.req("/api/status", cookie=cookie)[0], 401)

    def test_logout_and_lockout(self):
        code, _, headers = self.req("/api/logout", {})
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        agent._FAILS["login:127.0.0.1"] = [time.time()] * agent.LOCKOUT[0]
        self.assertEqual(self.login()[0], 429)        # locked even with the right password

    def test_hash_format(self):
        h = agent.hash_password("correct horse 9", rounds=1000)
        self.assertTrue(h.startswith("pbkdf2_sha256$1000$"))
        self.assertTrue(agent.check_password("correct horse 9", h))
        self.assertFalse(agent.check_password("correct horse 8", h))
        self.assertFalse(agent.check_password("x", "garbage"))



class BrandingVisibilityTests(NetworkAccessTests):
    """config.json switches: hide branding in the web UI, and hide/lock the Branding page."""
    def setUp(self):
        super().setUp()
        self.TOKEN = self.token_session()

    def test_defaults_show_everything(self):
        st = self.json.loads(self.req("/api/status", cookie=self.TOKEN)[1])
        self.assertEqual((st["ui_show_branding"], st["ui_hide_branding_page"]), (True, False))
        self.assertIn(b"/branding/logo", self.req("/")[1])
        self.assertEqual(self.req("/api/branding", cookie=self.TOKEN)[0], 200)

    def test_hide_branding_in_ui(self):
        agent.Handler.cfg["ui_show_branding"] = False
        page = self.req("/")[1]
        self.assertNotIn(b"/branding/logo", page)                 # sign-in page without logo / organisation
        self.assertIn(b"Sign in", page)
        st = self.json.loads(self.req("/api/status", cookie=self.TOKEN)[1])
        self.assertFalse(st["ui_show_branding"])
        self.req("/api/config", {"ui_show_branding": True}, cookie=self.TOKEN)   # Settings switch turns it back on
        self.assertTrue(self.json.loads(self.tmp.read_text())["ui_show_branding"])

    def test_hidden_branding_page_is_locked(self):
        cfg = agent.Handler.cfg
        cfg.update(ui_hide_branding_page=True, ui_show_branding=False)
        self.assertEqual(self.req("/api/branding", cookie=self.TOKEN)[0], 403)
        self.assertEqual(self.req("/api/branding", {"branding": {"organisation_name": "X"}}, cookie=self.TOKEN)[0], 403)
        self.assertEqual(self.req("/api/branding/logo", {"data_b64": ""}, cookie=self.TOKEN)[0], 403)
        st = self.json.loads(self.req("/api/config", {"ui_show_branding": True}, cookie=self.TOKEN)[1])
        self.assertFalse(st["ui_show_branding"])                     # the switch is locked too
        self.assertTrue(st["ui_hide_branding_page"])

    def test_config_values_accept_words(self):
        self.tmp.write_text(self.json.dumps({"ui_show_branding": "no", "ui_hide_branding_page": "yes"}))
        cfg = agent.load_config()
        self.assertEqual((cfg["ui_show_branding"], cfg["ui_hide_branding_page"]), (False, True))


if __name__ == "__main__":
    unittest.main()
