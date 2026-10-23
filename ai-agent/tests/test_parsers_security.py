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


if __name__ == "__main__":
    unittest.main()
