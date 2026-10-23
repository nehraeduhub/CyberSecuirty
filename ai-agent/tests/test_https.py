"""HTTPS: self-signed certificate creation, TLS server, Secure cookies, http->https redirect."""
import json
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent  # noqa: E402


@unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
class HttpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.crt, cls.key = cls.tmp / "a.crt", cls.tmp / "a.key"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-keyout", str(cls.key),
                        "-out", str(cls.crt), "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                       check=True, capture_output=True)
        cls._cfg_file = agent.CONFIG_FILE
        agent.CONFIG_FILE = cls.tmp / "config.json"
        cls.cfg = agent.load_config()
        cls.cfg.update(host="127.0.0.1", port=0, tls_cert=str(cls.crt), tls_key=str(cls.key), base_url="http://127.0.0.1:9",
                       access_token="tok-123", password_hash="")
        agent.Handler.cfg = cls.cfg
        srv_cls = type("TLSServer", (agent._TLSServerMixin, ThreadingHTTPServer), {"tls_ctx": agent.tls_context(cls.cfg)})
        cls.httpd = srv_cls(("127.0.0.1", 0), agent.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]
        ctx = ssl.create_default_context(cafile=str(cls.crt))
        cls.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ctx))

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        agent.CONFIG_FILE = cls._cfg_file
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_https_login_and_secure_cookie(self):
        with self.opener.open(f"https://localhost:{self.port}/", timeout=10) as r:
            self.assertIn(b"Sign in", r.read())
        req = Request(f"https://localhost:{self.port}/api/login", data=json.dumps({"token": "tok-123"}).encode(),
                      headers={"Content-Type": "application/json"})
        with self.opener.open(req, timeout=10) as r:
            self.assertIn("; Secure", r.headers["Set-Cookie"])

    def test_plain_http_and_bad_handshakes_do_not_break_the_server(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
        try:
            s.recv(100)
        except OSError:
            pass
        s.close()
        with self.opener.open(f"https://localhost:{self.port}/", timeout=10) as r:   # still serving
            self.assertEqual(r.status, 200)
        bad = ssl.create_default_context()                                             # untrusted: must fail
        with self.assertRaises(Exception):
            build_opener(ProxyHandler({}), HTTPSHandler(context=bad)).open(f"https://localhost:{self.port}/", timeout=10)

    def test_old_tls_refused(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        try:
            ctx.maximum_version = ssl.TLSVersion.TLSv1_1
            ctx.minimum_version = ssl.TLSVersion.TLSv1
        except (ValueError, ssl.SSLError):
            self.skipTest("this OpenSSL cannot even offer TLS 1.1")
        with self.assertRaises((ssl.SSLError, OSError)):
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as s:
                with ctx.wrap_socket(s, server_hostname="localhost") as t:
                    t.sendall(b"GET / HTTP/1.0\r\n\r\n")
                    t.recv(10)

    def test_urls_and_redirect(self):
        self.assertEqual(agent.agent_urls(dict(self.cfg, port=443)), ["https://127.0.0.1"])
        self.assertEqual(agent.agent_urls(dict(self.cfg, port=8443)), ["https://127.0.0.1:8443"])
        self.assertEqual(agent.agent_urls(dict(self.cfg, port=8787, tls_cert="")), ["http://127.0.0.1:8787"])
        red = type("R", (agent._Redirect,), {"https_port": 443})
        rs = ThreadingHTTPServer(("127.0.0.1", 0), red)
        threading.Thread(target=rs.serve_forever, daemon=True).start()
        try:
            import http.client
            c = http.client.HTTPConnection("127.0.0.1", rs.server_address[1], timeout=5)
            c.request("GET", "/live?x=1", headers={"Host": "agent.example.com"})
            r = c.getresponse()
            self.assertEqual((r.status, r.getheader("Location")), (301, "https://agent.example.com/live?x=1"))
        finally:
            rs.shutdown()

    def test_make_cert_cli(self):
        import argparse
        cfg = agent.load_config()
        d = ROOT / "config" / "tls"
        existed = d.exists()
        backup = {p.name: p.read_bytes() for p in d.glob("*")} if existed else {}
        try:
            agent.cli_make_cert(cfg, argparse.Namespace(name=["agent.example.lan", "10.9.8.7"], days=3, port=443, force=True))
            out = subprocess.run(["openssl", "x509", "-in", str(d / "agent.crt"), "-noout", "-text"],
                                 capture_output=True, text=True).stdout
            self.assertIn("DNS:agent.example.lan", out)
            self.assertIn("IP Address:10.9.8.7", out)
            self.assertEqual((d / "agent.key").stat().st_mode & 0o777, 0o600)
            saved = json.loads(agent.CONFIG_FILE.read_text())
            self.assertEqual((saved["port"], saved["tls_key"]), (443, str(d / "agent.key")))
            agent.tls_context(saved | {"tls_cert": saved["tls_cert"]})        # loads cleanly
        finally:
            for p in d.glob("*"):
                p.unlink()
            for n, b in backup.items():
                (d / n).write_bytes(b)
            if not existed:
                d.rmdir()


if __name__ == "__main__":
    unittest.main()
