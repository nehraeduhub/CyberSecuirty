"""Hostile log content: XML bombs / XXE, ReDoS-style lines, binary garbage, decompression, PDF markup injection."""
import gzip
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import detector  # noqa: E402
import engine  # noqa: E402
import flow  # noqa: E402
import parsers  # noqa: E402
import pipeline  # noqa: E402
import trust  # noqa: E402

BOMB = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
        '<Events><Event><System><EventID>&lol3;</EventID></System></Event></Events>')
XXE = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
       '<Events><Event><System><EventID>&e;</EventID></System></Event></Events>')


def events(path, name=None):
    st = {}
    evs = list(parsers.iter_events(Path(path), name or Path(path).name, 0, parsers.load_aliases(), st))
    return evs, parsers.summarise(st)


class HostileInputTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_xml_bombs_refused(self):
        for name, body in (("bomb.xml", BOMB), ("xxe.xml", XXE),
                           ("split.xml", "<Events>" + " " * 16380 + "<!DOC" + "TYPE x []><Event/></Events>")):
            p = self.d / name
            p.write_text(body)
            t = time.time()
            evs, s = events(p)
            self.assertLess(time.time() - t, 1.0)
            self.assertEqual(evs, [], name)
            self.assertEqual(s["parse_failures"], 1, name)
            self.assertNotIn("root:", str(evs))

    def test_binary_and_garbage_never_crash(self):
        import random
        rnd = random.Random(7)
        for i in range(30):
            p = self.d / f"g{i}.log"
            p.write_bytes(bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 6000))))
            r = pipeline.analyze_files([(p, p.name)], learn_baseline=False, inventory=trust.Inventory({}))
            self.assertIn("findings", r)

    def test_attack_strings_are_fast(self):
        worst = ["union" + "/*" * 20000, "'" + " or " * 20000, "../" * 30000, "<script" * 10000,
                 "a" * 200000, "${jndi:" * 20000, "%2e%2e/" * 20000, "cmd=" + ";id" * 20000]
        for w in worst:
            t = time.time()
            a = detector.LogAnalyzer()
            a.feed(w, 1, "x:1", None)
            a.result()
            self.assertLess(time.time() - t, 1.0, w[:20])

    def test_gzip_streams(self):
        p = self.d / "big.log.gz"
        with gzip.open(p, "wt") as fh:
            for i in range(50000):
                fh.write(f"Oct 18 02:55:{i % 60:02d} vpn01 vpnd[1]: event=auth_failure user=u{i} src_ip=203.0.113.7\n")
        evs, s = events(p)
        self.assertEqual(len(evs), 50000)

    def test_pdf_markup_injection(self):
        import report_pdf
        if not report_pdf.AVAILABLE:
            self.skipTest("reportlab not installed")
        p = self.d / "x.log"
        p.write_text('203.0.113.9 - - [18/Oct/2026:02:13:00 +0000] "GET /a.php?cmd=</para><font size=99>'
                     '<a href=\'javascript:x\'>x</a> HTTP/1.1" 200 1 "-" "sqlmap <b>&amp;"\n' * 3)
        r = pipeline.to_json(pipeline.analyze_files([(p, p.name)], learn_baseline=False, inventory=trust.Inventory({})))
        pdf = report_pdf.build_pdf(r, {"ref": "T"})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertNotIn(b"javascript:x", pdf.replace(b"\\", b""))


N = 100_000


def rep(s, n=N):
    return (s * (n // len(s) + 1))[:n]


def analyse(path):
    return pipeline.analyze_files([(path, Path(path).name)], learn_baseline=False, inventory=trust.Inventory({}))


class ReDoSTests(unittest.TestCase):
    """Every pattern runs on hostile 100 KB input in well under a second (before the fix several took 5-20 s,
    and web_sqli was exponential: a 198-byte line ran for minutes)."""

    def test_patterns_are_linear(self):
        D = {r[0]: r[4] for r in detector.COMPILED}
        cases = [
            (D["web_sqli"], "union" + "/**/" * 27 + "x"), (D["web_sqli"], rep("union/*")),
            (D["sudo_fail"], rep("sudo:")), (D["account_create"], "usermod " + rep("-g")),
            (D["account_create"], rep("usermod -g ")), (D["reverse_shell"], rep("socat ")),
            (D["encoded_powershell"], rep("powershell ")), (D["cred_dump"], rep("procdump")),
            (D["log_tamper"], rep("shred ")), (D["download_exec"], rep("curl ")),
            (D["web_shell"], rep("/uploads/a.php?")), (D["web_shell"], "/uploads/" + rep("a.php")),
            (detector.FW_RE, rep("SRC=a ")),
            (parsers.SUDO_RE, "sudo: a :" + rep("USER=x ")), (parsers.SUDO_RE, rep("sudo: a : ")),
            (parsers.CEF_SPLIT_RE, "a=" + rep("x")), (parsers.CEF_SPLIT_RE, "a=" + rep(" ")),
            (parsers.CEF_SPLIT_RE, rep("ab") + "="), (parsers.SOURCE_HINTS[6][1], rep("deny ")),
            (engine.RX["TG-EXF-002"], "tar c" + rep("z")), (engine.RX["TG-LNX-001"], rep("vi")),
            (engine.RX["TG-DB-001"], rep("bcp copy select sqlcmd ")), (engine.RX["TG-MAL-001"], rep("bcdedit .locked ")),
            (engine.RX["TG-CRED-001"], rep("procdump ntdsutil")), (engine.RX["TG-EXE-001"], rep("iwr ")),
            (engine.RX["TG-EXE-002"], rep("certutil regsvr32 rundll32 bitsadmin installutil ")),
            (engine.RX["TG-DEF-001"], rep("set-mppreference ")), (flow.EXPLOIT_HINT, rep("select")),
        ]
        for rx, s in cases:
            t = time.perf_counter()
            rx.findall(s)
            self.assertLess(time.perf_counter() - t, 0.6, f"{rx.pattern[:50]} on {s[:20]!r}")

    def test_hostile_lines_end_to_end_and_detection_kept(self):
        d = Path(tempfile.mkdtemp())
        lines = ['203.0.113.5 - - [18/Oct/2026:02:13:00 +0000] "GET /?q=union' + "/**/" * 31 + 'x HTTP/1.1" 200 1',
                 "CEF:0|V|P|1|100|sig|5|msg=" + "x" * N, "Oct 18 02:55:01 h sudo: a :" + "USER=x " * 15000,
                 "Oct 18 02:55:02 h bash[1]: usermod " + "-g" * 50000]
        (d / "h.log").write_text("\n".join(lines) + "\n")
        t = time.time()
        analyse(d / "h.log")
        self.assertLess(time.time() - t, 5)
        # the bounded patterns still catch the real attacks
        (d / "a.log").write_text(
            '203.0.113.5 - - [18/Oct/2026:02:13:00 +0000] "GET /p?id=1/**/union/**/all/**/select/**/1,2 HTTP/1.1" 200 1\n'
            '203.0.113.5 - - [18/Oct/2026:02:13:01 +0000] "GET /uploads/x.php?a=1&cmd=id HTTP/1.1" 200 1\n'
            "Oct 18 02:55:03 h sudo:   bob : 3 incorrect password attempts ; TTY=pts/0 ; USER=root ; COMMAND=/bin/sh\n"
            "Oct 18 02:55:04 h bash[2]: usermod -aG sudo eve\n")
        ids = {f["id"] for f in analyse(d / "a.log")["findings"]}
        for rid in ("web_sqli", "web_shell", "sudo_fail", "account_create"):
            self.assertTrue(any(rid in i for i in ids), (rid, ids))

    def test_sudo_and_cef_fields(self):
        norm = parsers.Normaliser(parsers.load_aliases(), parsers.TimeParser(0))
        ev = parsers.parse_text_line("Oct 18 02:55:03 h sudo: bob : TTY=pts/0 ; PWD=/ ; USER=root ; COMMAND=/bin/sh -c id",
                                     norm)
        self.assertEqual((ev.get("target_user"), ev.get("command")), ("root", "/bin/sh -c id"))
        ev = parsers.parse_text_line("CEF:0|Fortinet|FGT|1|13|deny|5|src=203.0.113.9 dst=10.0.0.5 dpt=443 "
                                     "msg=blocked by policy request=http://x/?a=b", norm)
        self.assertEqual((ev.get("src_ip"), ev.get("dst_ip"), str(ev.get("dst_port"))), ("203.0.113.9", "10.0.0.5", "443"))


class MalformedInputTests(unittest.TestCase):
    """Hostile records become parse failures; they never abort the analysis (found by fuzzing)."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def run_file(self, name, data):
        p = self.d / name
        p.write_bytes(data) if isinstance(data, bytes) else p.write_text(data)
        t = time.time()
        r = analyse(p)
        self.assertLess(time.time() - t, 10, name)
        return r, r["ingestion"][0]

    def test_never_abort(self):
        for name, data, fails in (
                ("inf.log", "Oct 18 02:55:01 h fw: src=1.2.3.4 bytes_out=1e999 dst_port=1e400\n", 0),
                ("inf.jsonl", '{"src_ip":"1.2.3.4","dst_port":"1e400","bytes_out":1e999}\n', 0),
                ("deep.json", "[" * 100000, 1), ("deep.jsonl", '{"a":1}\n' + "[" * 100000 + "\n", 1),
                ("obj.json", '{"a":1,', 1), ("deep.xml", "<Events>" + "<Event>" * 200000, 1),
                ("bad.log.gz", b"not gzip", 1),
                ("big.csv", "time,src_ip,user,msg\n2026-10-18 02:00:00,1.2.3.4,u," + "x" * (2 * 1024 * 1024) + "\n", 1)):
            r, ing = self.run_file(name, data)
            self.assertEqual(ing["parse_failures"], fails, (name, ing.get("failure_samples")))

    def test_gzip_bomb_and_long_lines(self):
        p = self.d / "bomb.log.gz"
        with gzip.open(p, "wb", compresslevel=1) as fh:
            fh.write(b"Oct 18 02:55:01 h sshd[1]: Failed password for root from 203.0.113.7 port 22 ssh2\n")
            fh.write(b"A" * (64 * 1024 * 1024) + b"\n")
            fh.write(b"Oct 18 02:55:02 h sshd[1]: Failed password for root from 203.0.113.7 port 22 ssh2\n")
        t = time.time()
        evs, s = events(p)
        self.assertLess(time.time() - t, 10)
        self.assertEqual((len(evs), s["cut_lines"]), (3, 1))
        self.assertLessEqual(max(len(e["text"]) for e in evs), parsers.MAX_LINE + 20)
        old = parsers.MAX_DECOMPRESSED
        parsers.MAX_DECOMPRESSED = 1024 * 1024
        try:
            evs, s = events(p)
        finally:
            parsers.MAX_DECOMPRESSED = old
        self.assertEqual(len(evs), 1)
        self.assertIn("decompression bomb", s["failure_samples"][0]["error"])

    def test_json_item_cap(self):
        p = self.d / "big.json"
        p.write_text('[{"src_ip":"1.2.3.4"},{"message":"' + "x" * (3 * 1024 * 1024) + '"}]')
        t = time.time()
        evs, s = events(p)
        self.assertLess(time.time() - t, 3)
        self.assertEqual((len(evs), s["parse_failures"]), (1, 1))

    def test_memory_budget_stops_ingestion(self):
        p = self.d / "many.log"
        p.write_text("".join(f"Oct 18 02:55:01 h sshd[1]: Failed password for u{i} from 198.51.{i // 250 % 250}.{i % 250} "
                             "port 22 ssh2\n" for i in range(25000)))
        readings = iter([1000.0])  # first reading is the baseline; every later one is 9 GB more
        old = pipeline._rss_mb
        pipeline._rss_mb = lambda: next(readings, 1000.0 + 9 * 1024)
        try:
            r = analyse(p)
        finally:
            pipeline._rss_mb = old
        self.assertEqual(r["lines"], 20000)
        self.assertEqual(r["limitations"][0]["area"], "Resource limit")

    def test_pdf_survives_misnested_ai_markdown(self):
        import report_pdf
        if not report_pdf.AVAILABLE:
            self.skipTest("reportlab not installed")
        p = self.d / "x.log"
        p.write_text("Oct 18 02:55:01 h sshd[1]: Failed password for root from 203.0.113.7 port 22 ssh2\n")
        r = pipeline.to_json(analyse(p))
        for ai in ("Summary **bold `code** tail`\n\n- item **a `b** c`", "x <b> & </para> `**y`**"):
            self.assertTrue(report_pdf.build_pdf(r, {"ref": "T"}, ai).startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
