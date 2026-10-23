"""Trusted assets never shown as malicious / IOCs, forensic view, attack diagram, learning from stored logs."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_store  # noqa: E402
import forensics  # noqa: E402
import history  # noqa: E402
import memory  # noqa: E402
import pipeline  # noqa: E402
import report_pdf  # noqa: E402
import trust  # noqa: E402
from test_siem_platform import DEMO_TRUST, SAMPLE_FILES, Isolated, analyse_samples  # noqa: E402


class TrustedDisplayTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.r = analyse_samples()

    def test_trusted_never_malicious_or_ioc(self):
        inv = trust.Inventory(copy.deepcopy(DEMO_TRUST))
        for p in self.r["ip_profiles"]:
            cat = inv.classify(p["ip"])["category"]
            if cat in pipeline.TRUSTED_CATEGORIES:
                self.assertEqual(p["verdict"], "Trusted", p)
                self.assertTrue(p["trusted"])
                self.assertNotIn(p["ip"], self.r["iocs"]["ips"])
        self.assertIn("198.51.100.2", self.r["iocs"]["trusted"])      # own web server: green, not an IOC
        self.assertIn("192.0.2.22", self.r["iocs"]["trusted"])        # compromised but trusted workstation
        self.assertIn("203.0.113.50", self.r["iocs"]["ips"])          # the real attacker still is
        ws = next(p for p in self.r["ip_profiles"] if p["ip"] == "192.0.2.22")
        self.assertIn("check whether it was affected", ws["note"])

    def test_trusted_findings_are_still_reported(self):
        # trust is display context only: the attack on the trusted workstation is still found and scored
        fs = [f for f in self.r["findings"] if "192.0.2.22" in f.get("ips", [])]
        self.assertTrue(any(f["severity"] in ("critical", "high") for f in fs))

    def test_block_list_excludes_trusted(self):
        import agent
        md = agent.instant_answer("block", self.r)
        for ip in self.r["iocs"]["trusted"]:
            self.assertNotIn(ip, md)


class ForensicViewTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.r = analyse_samples()

    def test_tabs_by_attack_type(self):
        v = forensics.view(self.r)
        keys = [t["key"] for t in v["tabs"]]
        for k in ("web", "credential", "malware", "lateral", "c2", "exfil", "evasion"):
            self.assertIn(k, keys)
        self.assertEqual(sum(t["count"] for t in v["tabs"]), len(self.r["findings"]))   # every finding in one tab
        web = next(t for t in v["tabs"] if t["key"] == "web")
        self.assertIn("TG-WEB-009", [f["rule_id"] for f in web["findings"]])
        self.assertTrue(web["steps"] and web["commands"]["Linux"] and web["suggestions"] and web["recommendations"])
        self.assertTrue(any("exploitation possible" in a["action"] for a in web["actions"]))
        self.assertIn("203.0.113.50", web["scope"]["attacker_ips"])
        self.assertNotIn("198.51.100.2", web["scope"]["attacker_ips"])
        self.assertIn("forensic", forensics.markdown(self.r).lower())

    def test_diagram(self):
        d = self.r["incidents"][0]["diagram"]
        roles = {n["label"]: n["role"] for n in d["nodes"]}
        self.assertEqual(roles["203.0.113.77"], "attacker")
        self.assertEqual(roles["WS-BOB"], "trusted")
        self.assertEqual(roles["203.0.113.150"], "external")
        self.assertTrue(any(e["from"] == "ws-bob" and e["to"] == "203.0.113.99" for e in d["edges"]))
        levels = {n["id"]: n["level"] for n in d["nodes"]}
        self.assertLess(levels["203.0.113.77"], levels["ws-bob"])
        web = next(i for i in self.r["incidents"] if "203.0.113.50" in i["ips"])["diagram"]
        urls = [n["label"] for n in web["nodes"] if n["role"] == "url"]
        self.assertIn("/uploads/shell.php", urls)
        shell = next(e for e in web["edges"] if e["to"] == "/uploads/shell.php")
        self.assertEqual(shell["result"], "success")
        self.assertIn("exploitation possible", shell["label"])

    def test_pdf_has_diagram_and_forensic_steps(self):
        if not report_pdf.AVAILABLE:
            self.skipTest("reportlab not installed")
        import io
        try:
            import pdfplumber
        except ImportError:
            self.skipTest("pdfplumber not installed")
        pdf = report_pdf.build_pdf(self.r, {"ref": "T"})
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            text = "\n".join(p.extract_text() or "" for p in doc.pages)
            for p in doc.pages:
                self.assertFalse([c for c in p.chars if c["x1"] > p.width - 30 or c["x0"] < 30])
        for needle in ("Attack diagram", "Forensic investigation by attack type", "Web attacks & exploitation",
                       "not indicators", "/uploads/shell.php"):
            self.assertIn(needle, text)


class LearnFromStoredLogsTests(Isolated):
    def test_learn_from_history(self):
        inv = trust.Inventory(copy.deepcopy(DEMO_TRUST))
        web = [(p, n) for p, n in SAMPLE_FILES if n == "web_access.log"]
        ids = []
        for n in range(4):
            r = pipeline.to_json(pipeline.analyze_files(web if n < 3 else SAMPLE_FILES, inventory=inv, learn_baseline=False))
            r["analysis_id"] = f"{n + 1:016x}"
            history.save(r, "upload", f"run {n}", web if n < 3 else SAMPLE_FILES)
            ids.append(r["analysis_id"])
        calls = []
        self.assertTrue(memory.learn_from_history(lambda files: calls.append(files), "test"))
        self.assertFalse(memory.JOB["running"])
        self.assertEqual((memory.JOB["done"], memory.JOB["baselines"], memory.JOB["errors"]), (4, 4, []))
        self.assertEqual(len(calls), 4)
        memory.learn_from_history(lambda files: calls.append(files), "test")
        self.assertEqual(len(calls), 4, "stored logs teach the baselines only once")
        s = memory.summary()
        self.assertEqual((s["analyses_learned"], s["baselined"]), (4, 4))

        # a new analysis knows which rules are new compared with the history
        r = pipeline.to_json(pipeline.analyze_files(SAMPLE_FILES, inventory=inv, learn_baseline=False))
        r["analysis_id"] = "f" * 16
        memory.annotate(r)
        shell = next(f for f in r["findings"] if f["rule_id"] == "TG-WEB-009")
        self.assertEqual(shell["prevalence"], {"seen_in": 4, "of": 4, "text": "This rule fired in 4 of 4 earlier analyses"})
        vpn = next(f for f in r["findings"] if f["rule_id"] == "TG-AUTH-002")
        self.assertEqual(vpn["prevalence"]["seen_in"], 1)
        prof = next(p for p in r["ip_profiles"] if p["ip"] == "203.0.113.50")
        self.assertEqual(len(prof["seen_before"]), 4)

        history.delete(ids[0], "t")
        memory.forget_analysis(ids[0])
        self.assertEqual(memory.summary()["analyses_learned"], 3)


if __name__ == "__main__":
    unittest.main()
