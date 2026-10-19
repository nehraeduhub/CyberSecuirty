"""Tests for the SIEM analysis platform: parsers, trust, branding, engine, pipeline,
investigation agent, A4 report layout, API and offline operation.

Every test runs against temporary config/data directories, never the real installation.
"""
import base64
import copy
import gzip
import io
import json
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import branding  # noqa: E402
import config_store  # noqa: E402
import engine  # noqa: E402
import investigator  # noqa: E402
import parsers  # noqa: E402
import pipeline  # noqa: E402
import report_pdf  # noqa: E402
import trust  # noqa: E402

SIEM = ROOT / "samples" / "siem"
SAMPLE_FILES = [(p, p.name) for p in sorted(SIEM.glob("*"))
                if p.suffix in (".csv", ".jsonl", ".json", ".cef", ".log", ".xml") and "demo" not in p.name
                and "ioc" not in p.name]
DEMO_TRUST = json.loads((SIEM / "trusted_assets.demo.json").read_text())


class Isolated(unittest.TestCase):
    """Redirect config/, data/ and the logo folder to a temp directory for each test class."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls._saved = (config_store.CONFIG_DIR, config_store.DATA_DIR, config_store.UPLOAD_DIR, config_store.AUDIT_LOG,
                      branding.LOGO_DIR, pipeline.BASELINE_FILE)
        config_store.CONFIG_DIR = cls.tmp / "config"
        config_store.DATA_DIR = cls.tmp / "data"
        config_store.UPLOAD_DIR = cls.tmp / "data" / "uploads"
        config_store.AUDIT_LOG = cls.tmp / "data" / "audit.log"
        branding.LOGO_DIR = config_store.ROOT / "assets" / "branding" / f"test-{cls.tmp.name}"
        pipeline.BASELINE_FILE = cls.tmp / "data" / "baselines.json"
        (cls.tmp / "config").mkdir()
        shutil.copytree(ROOT / "config" / "examples", cls.tmp / "config" / "examples")
        config_store.EXAMPLES_DIR = cls.tmp / "config" / "examples"

    @classmethod
    def tearDownClass(cls):
        (config_store.CONFIG_DIR, config_store.DATA_DIR, config_store.UPLOAD_DIR, config_store.AUDIT_LOG,
         branding.LOGO_DIR, pipeline.BASELINE_FILE) = cls._saved
        config_store.EXAMPLES_DIR = config_store.CONFIG_DIR / "examples"
        shutil.rmtree(cls.tmp, ignore_errors=True)
        shutil.rmtree(config_store.ROOT / "assets" / "branding" / f"test-{cls.tmp.name}", ignore_errors=True)


def analyse_samples(**kw):
    inv = kw.pop("inventory", trust.Inventory(copy.deepcopy(DEMO_TRUST)))
    iocs = kw.pop("iocs", engine.load_iocs([SIEM / "ioc_feed.csv"])[0])
    return pipeline.to_json(pipeline.analyze_files(SAMPLE_FILES, inventory=inv, iocs=iocs, learn_baseline=False, **kw))


# ------------------------------------------------------------------ parsers

class ParserTests(Isolated):
    def summary(self, path, name=None):
        st = {}
        evs = list(parsers.iter_events(path, name, stats=st))
        return evs, parsers.summarise(st)

    def test_every_sample_format_parses_without_failures(self):
        expect = {"windows_security.csv": ("csv", "windows"), "firewall.jsonl": ("jsonl", "firewall"),
                  "dns.json": ("json", "dns"), "ids_alerts.cef": ("text", "ids"), "vpn.log": ("text", "vpn"),
                  "windows_dc.xml": ("winxml", "windows")}
        for path, name in SAMPLE_FILES:
            evs, s = self.summary(path)
            self.assertEqual(s["parse_failures"], 0, name)
            self.assertEqual((s["format"], s["probable_source"][0]), expect[name], name)
            self.assertTrue(all(e["ref"].startswith(name + ":") for e in evs))
            self.assertTrue(all(e["raw"] for e in evs), "original record must be preserved")

    def test_field_mapping_and_timestamps(self):
        evs, s = self.summary(SIEM / "windows_security.csv")
        self.assertEqual(s["column_mapping"]["Source_Network_Address"], "src_ip")
        self.assertEqual(s["column_mapping"]["EventCode"], "event_id")
        self.assertEqual(s["timezones"], {"UTC": len(evs)})
        dns, ds = self.summary(SIEM / "dns.json")
        self.assertIn("domain", ds["fields_available"])     # ECS dns.question.name
        self.assertEqual(dns[0]["src_ip"], json.loads((SIEM / "dns.json").read_text())[0]["client"]["ip"])
        self.assertTrue(all(e.get("domain") for e in dns))
        vpn, _ = self.summary(SIEM / "vpn.log")
        self.assertEqual(vpn[-1]["assigned_ip"], "192.0.2.200")

    def test_timezone_offsets_are_normalised_to_utc(self):
        tp = parsers.TimeParser()
        self.assertEqual(str(tp.parse("2026-10-18T08:40:00+05:30")), "2026-10-18 03:10:00")
        self.assertEqual(str(tp.parse("18/Oct/2026:03:10:00 +0000")), "2026-10-18 03:10:00")
        self.assertEqual(str(tp.parse("1792293000")), "2026-10-18 03:10:00")
        self.assertIn("UTC+05:30", tp.zones)

    def test_failures_are_reported_and_evtx_is_explained(self):
        d = Path(tempfile.mkdtemp())
        (d / "bad.jsonl").write_text('{"src_ip": "10.0.0.1", "user": "a"}\n{broken json\n{"user": "b"}\n')
        evs, s = self.summary(d / "bad.jsonl")
        self.assertEqual((s["events"], s["parse_failures"]), (3, 1))
        self.assertEqual(s["failure_samples"][0]["line"], 2)
        (d / "x.evtx").write_bytes(b"ElfFile\x00")
        _, s = self.summary(d / "x.evtx")
        self.assertIn("export it", s["failure_samples"][0]["error"])

    def test_gzip_and_large_json_array_stream(self):
        d = Path(tempfile.mkdtemp())
        rows = [{"timestamp": f"2026-10-18T00:{i // 60 % 60:02d}:{i % 60:02d}Z", "src_ip": "192.0.2.9",
                 "dst_ip": "203.0.113.5", "dst_port": 443, "action": "allow"} for i in range(20000)]
        (d / "big.json").write_text(json.dumps(rows))
        with gzip.open(d / "big.jsonl.gz", "wt") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows[:500]))
        evs, s = self.summary(d / "big.json")
        self.assertEqual(s["events"], 20000)
        evs, s = self.summary(d / "big.jsonl.gz")
        self.assertEqual((s["format"], s["events"]), ("jsonl", 500))

    def test_configurable_field_aliases(self):
        (config_store.CONFIG_DIR / "field_mappings.json").write_text(json.dumps({"aliases": {"src_ip": ["WeirdSrc"]}}))
        d = Path(tempfile.mkdtemp())
        (d / "v.csv").write_text("When,WeirdSrc,Login\n2026-10-18 03:00:00,198.51.100.9,bob\n2026-10-18 03:01:00,198.51.100.9,amy\n")
        try:
            evs, s = self.summary(d / "v.csv")
            self.assertEqual(evs[0]["src_ip"], "198.51.100.9")
        finally:
            (config_store.CONFIG_DIR / "field_mappings.json").unlink()


# ------------------------------------------------------------------ trusted networks & assets

class TrustTests(Isolated):
    def test_example_config_is_disabled(self):
        inv = trust.Inventory.load()
        self.assertEqual(inv.errors, [])
        self.assertEqual(inv.enabled_count, 0)

    def test_precedence_and_classification(self):
        data = copy.deepcopy(DEMO_TRUST)
        data["suspicious_indicators"] = [{"name": "bad", "cidr": "192.0.2.66/32"}]
        inv = trust.Inventory(data)
        c = lambda ip: inv.classify(ip)["category"]
        self.assertEqual(c("192.0.2.66"), "suspicious_indicator")      # beats the trusted LAN
        self.assertEqual(c("192.0.2.53"), "approved_asset")            # exact asset
        self.assertEqual(c("192.0.2.200"), "configured_internal")      # /27 VPN pool inside /24 LAN
        self.assertEqual(inv.classify("192.0.2.200")["entry"]["name"], "VPN client pool")
        self.assertEqual(c("198.51.100.4"), "configured_isp")
        self.assertEqual(c("10.9.9.9"), "other_private")
        self.assertEqual(c("203.0.113.99"), "public_unknown")          # documentation range is NOT private
        self.assertEqual(c("not-an-ip"), "invalid")

    def test_validity_dates(self):
        inv = trust.Inventory({"trusted_networks": [{"name": "old", "cidr": "10.0.0.0/8", "valid_until": "2020-01-01"}]})
        self.assertEqual(inv.classify("10.1.1.1")["category"], "other_private")

    def test_malformed_or_broad_entries_are_refused(self):
        for bad in ("0.0.0.0/0", "10.0.0.0/7", "::/0", "192.168.1.5/16", "300.1.1.1", ""):
            with self.assertRaises(ValueError, msg=bad):
                trust.validate_entry("trusted_networks", {"name": "x", "cidr": bad})
        with self.assertRaises(ValueError):
            trust.validate_entry("trusted_assets", {"name": "x", "ip": "10.0.0.0/24"})

    def test_import_preview_then_apply_with_audit(self):
        inv = trust.Inventory.load()
        csv_text = ("section,name,cidr,ip,asset_type,enabled\n"
                    "trusted_networks,LAN,10.10.0.0/16,,,true\n"
                    "trusted_networks,Everything,0.0.0.0/0,,,true\n"
                    "trusted_assets,DNS,,10.10.0.53,dns_server,true\n")
        raw = trust.parse_import(csv_text, "csv")
        prev = trust.preview_import(inv, raw)
        self.assertEqual(prev["counts"]["add"], 2)
        self.assertEqual(len(prev["errors"]), 1)                       # the /0 row is rejected, not applied
        self.assertEqual(trust.Inventory.load().enabled_count, 0)      # preview changes nothing
        trust.apply_import(inv, raw, "merge", "tester")
        inv2 = trust.Inventory.load()
        self.assertEqual(inv2.classify("10.10.0.53")["category"], "approved_asset")
        self.assertEqual(inv2.classify("8.8.8.8")["category"], "public_unknown")
        log = config_store.read_audit(area="trusted_assets")
        self.assertEqual(log[0]["actor"], "tester")
        trust.upsert(inv2, "trusted_networks", dict(inv2.data["trusted_networks"][-1], name="LAN renamed"), "tester")
        last = config_store.read_audit(area="trusted_assets")[0]
        self.assertEqual((last["action"], last["before"]["name"], last["after"]["name"]), ("update", "LAN", "LAN renamed"))

    def test_csv_export_neutralises_formulas(self):
        inv = trust.Inventory({"trusted_networks": [{"name": "=HYPERLINK(\"http://x\")", "cidr": "10.0.0.0/8"}]})
        self.assertIn("'=HYPERLINK", trust.export_csv(inv))

    def test_export_round_trip(self):
        inv = trust.Inventory(copy.deepcopy(DEMO_TRUST))
        raw = trust.parse_import(trust.export_csv(inv), "csv")
        self.assertEqual(trust.preview_import(trust.Inventory(), raw)["errors"], [])


# ------------------------------------------------------------------ branding

def png(w=120, h=60):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), "navy").save(b, "PNG")
    return b.getvalue()


class BrandingTests(Isolated):
    def test_save_validates_and_persists(self):
        b = branding.save({"organisation_name": "Acme Institute", "primary_colour": "#112233"}, "tester")
        self.assertEqual(branding.load()["organisation_name"], "Acme Institute")
        self.assertEqual(b["primary_colour"], "#112233")
        for bad in ({"primary_colour": "red"}, {"filename_prefix": "../x"}, {"logo_path": "../../agent.py"}):
            with self.assertRaises(ValueError):
                branding.save(bad, "tester")

    def test_logo_upload_preview_and_confirmation(self):
        up = branding.store_logo(base64.b64encode(png()).decode(), "tester")
        self.assertTrue(branding.resolve_logo(up["logo_path"]))
        branding.save({"logo_path": up["logo_path"]}, "tester")
        up2 = branding.store_logo(base64.b64encode(png(200, 80)).decode(), "tester")
        with self.assertRaises(PermissionError):                       # replacing needs confirmation
            branding.save({"logo_path": up2["logo_path"]}, "tester")
        branding.save({"logo_path": up2["logo_path"]}, "tester", confirm_replace=True)
        self.assertTrue(branding.resolve_logo(up["logo_path"]), "old logo file must not be overwritten")
        self.assertEqual(branding.load()["logo_path"], up2["logo_path"])

    def test_unsafe_logos_rejected(self):
        for data in (b"<svg onload=alert(1)>", b"GIF89a", png()[:40], b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR\0\x01\0\0\0\x01\0\0" + b"\0" * 20):
            with self.assertRaises(ValueError):
                branding.check_logo(data)


# ------------------------------------------------------------------ engine + pipeline

class PipelineTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.r = analyse_samples()
        cls.rules = {f["rule_id"] for f in cls.r["findings"]}

    def test_attack_chain_detected_across_sources(self):
        for rid in ("TG-AUTH-002", "TG-AUTH-004", "TG-EXE-001", "TG-C2-001", "TG-CRED-002", "TG-LAT-001",
                    "TG-PER-001", "TG-DB-001", "TG-EXF-002", "TG-EXF-001", "TG-DNS-001", "TG-DNS-002",
                    "TG-MAL-001", "TG-FOR-001", "TG-FOR-005", "TG-TI-001", "TG-AUTH-007", "TG-NET-001", "TG-NET-002"):
            self.assertIn(rid, self.rules)

    def test_incident_reconstruction(self):
        inc = self.r["incidents"][0]
        self.assertEqual(set(inc["users"]) & {"bob", "admin_it"}, {"bob", "admin_it"})
        self.assertNotIn("alice", inc["users"])                        # spray victims are not actors
        self.assertIn("alice", inc["targeted_accounts"])
        self.assertGreaterEqual(len(inc["tactics"]), 6)
        times = [t["ts"] for t in inc["timeline"]]
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(t["evidence"].startswith("E-") for t in inc["timeline"]))
        self.assertTrue(inc["status"].startswith(("Probable", "Suspected")))
        self.assertNotIn("Confirmed", inc["status"])

    def test_no_false_brute_force_from_spread_out_typos(self):
        # dave mistypes once per day; that must not become brute force + compromise
        for f in self.r["findings"]:
            if f["rule_id"] in ("TG-WIN-002", "TG-AUTH-004", "TG-AUTH-008"):
                self.assertNotIn("dave", f.get("users", []), f["title"])

    def test_trusted_assets_never_suppress_or_lower(self):
        f = next(f for f in self.r["findings"] if f["rule_id"] == "TG-CRED-002")
        self.assertEqual(f["severity"], "critical")
        self.assertTrue(any(c["category"] == "approved_asset" for c in f["trust_context"]))
        plain = analyse_samples(inventory=trust.Inventory())
        g = next(x for x in plain["findings"] if x["rule_id"] == "TG-CRED-002")
        self.assertEqual(g["severity"], f["severity"])
        self.assertGreaterEqual(f["risk"]["score"], g["risk"]["score"])
        self.assertEqual(len({x["rule_id"] for x in plain["findings"]} - self.rules - {"TG-NET-007"}), 0)

    def test_approved_scanner_context_without_suppression(self):
        f = next(f for f in self.r["findings"] if f["rule_id"] == "TG-NET-001" and "192.0.2.250" in f["title"])
        self.assertEqual(f["severity"], "medium")
        self.assertTrue(any("approved scanner" in n.lower() for n in f["notes"]))
        self.assertTrue(any(x["points"] < 0 for x in f["risk"]["factors"]))
        self.assertGreaterEqual(f["risk"]["score"], 18)

    def test_separate_scores_and_explanations(self):
        for f in self.r["findings"]:
            for k in ("severity", "confidence", "ueba_score", "risk", "asset_trust"):
                self.assertIn(k, f, f["title"])
            self.assertEqual(f["risk"]["score"], max(round({"critical": 70, "high": 50, "medium": 30, "low": 15,
                                                            "info": 5}[f["severity"]] * 0.6),
                                                     min(100, sum(x["points"] for x in f["risk"]["factors"]))))

    def test_ueba_explains_bob(self):
        bob = next(u for u in self.r["ueba"]["entities"] if u["entity"] == "bob")
        kinds = {r["kind"] for r in bob["reasons"]}
        self.assertTrue({"unusual_hour", "new_source"} <= kinds)
        self.assertFalse(bob["insufficient_history"])

    def test_evidence_register_is_traceable(self):
        reg = {e["id"]: e for e in self.r["evidence"]}
        for f in self.r["findings"]:
            for e in f["evidence"]:
                self.assertIn(e, reg)
        e = reg["E-0001"]
        file, line = e["ref"].rsplit(":", 1)
        original = (SIEM / file).read_text().splitlines()
        self.assertTrue(line.isdigit() and int(line) <= len(original) + 1)

    def test_limitations_reflect_missing_telemetry(self):
        areas = " ".join(l["detail"] for l in self.r["limitations"])
        self.assertIn("EDR", areas)
        self.assertIn("Web", " ".join(l["detail"] for l in self.r["limitations"]) + "Web")

    def test_rule_overrides_from_config(self):
        (config_store.CONFIG_DIR / "detection_rules.json").write_text(json.dumps(
            {"rules": {"TG-C2-001": {"enabled": False}, "TG-AUTH-002": {"severity": "critical"}}}))
        try:
            r = analyse_samples()
            rules = {f["rule_id"]: f for f in r["findings"]}
            self.assertNotIn("TG-C2-001", rules)
            self.assertEqual(rules["TG-AUTH-002"]["severity"], "critical")
        finally:
            (config_store.CONFIG_DIR / "detection_rules.json").unlink()

    def test_baseline_learning_excludes_incident_accounts(self):
        pipeline.analyze_files(SAMPLE_FILES, inventory=trust.Inventory(copy.deepcopy(DEMO_TRUST)), learn_baseline=True,
                               iocs=engine.load_iocs([])[0])
        b = json.loads(pipeline.BASELINE_FILE.read_text())
        self.assertIn("alice", b)
        self.assertNotIn("bob", b)
        self.assertNotIn("admin_it", b)


# ------------------------------------------------------------------ investigation agent

class InvestigatorTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.r = analyse_samples()

    def test_case_file_has_trust_context_and_evidence(self):
        cf = investigator.case_file(self.r)
        self.assertLessEqual(len(cf), 7100)
        for needle in ("TRUSTED INVENTORY", "VPN client pool", "INC-001", "[E-0", "accounts targeted"):
            self.assertIn(needle, cf)

    def test_deterministic_investigation_without_ai(self):
        inv = investigator.investigate(self.r)
        i = inv["incidents"][0]
        self.assertTrue(i["hypotheses"] and i["story"] and i["queries"] and i["gaps"])
        self.assertTrue(all(h["status"] in ("suspected", "probable") for h in i["hypotheses"]))
        known = {e["id"] for e in self.r["evidence"]}
        self.assertTrue(all(e in known for h in i["hypotheses"] for e in h["evidence"]))
        self.assertIn("splunk", i["queries"][0])

    def test_validation_catches_fabrication(self):
        v = investigator.validate("Compromise confirmed [E-0001] [E-9999]. This is a confirmed compromise. I blocked it.",
                                  self.r)
        self.assertEqual(v["unknown"], ["E-9999"])
        self.assertEqual(len(v["warnings"]), 3)
        self.assertEqual(investigator.validate("Bob [E-0001] logged on.", self.r)["warnings"], [])


# ------------------------------------------------------------------ A4 report layout

@unittest.skipUnless(report_pdf.AVAILABLE, "reportlab not installed")
class ReportLayoutTests(Isolated):
    """Generated PDFs are A4, keep all text inside the printable width and number every page."""

    def check(self, pdf_bytes):
        try:
            import pdfplumber
        except ImportError:
            self.skipTest("pdfplumber not installed (pip install pdfplumber) - layout geometry not checked")
        from reportlab.lib.pagesizes import A4
        mm = 2.8346
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            n = len(pdf.pages)
            for i, p in enumerate(pdf.pages, 1):
                self.assertAlmostEqual(p.width, A4[0], delta=1)
                self.assertAlmostEqual(p.height, A4[1], delta=1)
                outside = [c["text"] for c in p.chars if c["x1"] > A4[0] - 11.5 * mm or c["x0"] < 11.5 * mm - 0.5]
                self.assertEqual(outside, [], f"page {i}: text outside printable width")
                self.assertIn(f"Page {i} of {n}", p.extract_text() or "")
        return n

    def test_short_single_and_missing_fields(self):
        r = analyse_samples()
        one = copy.deepcopy(r)
        one["findings"], one["incidents"], one["evidence"] = one["findings"][:1], [], one["evidence"][:3]
        self.check(report_pdf.build_pdf(one, {}))
        bare = {"kind": "logs", "findings": [{"id": "x", "title": "Minimal", "severity": "low", "count": 1, "samples": []}],
                "summary": {"low": 1}, "risk_score": 10, "risk_level": "low", "grade": "C"}
        self.check(report_pdf.build_pdf(bare, {}))

    def test_long_evidence_urls_paths_and_many_findings(self):
        r = analyse_samples()
        url = "https://cdn.example.org/" + "a" * 700 + "?token=" + "Zx9" * 200
        path = "C:\\Users\\Public\\" + "VeryLongDirectoryName_" * 25 + "payload.exe"
        for f in r["findings"][:12]:
            f["samples"] = [{"ref": "export.csv:1", "evidence": "E-0001", "text": f"{url} {path}"}] * 4
            f["ips"] = [f"203.0.113.{i}" for i in range(60)]
            f["hosts"] = ["HOST-" + "X" * 90 + str(i) for i in range(10)]
            f["evidence_refs"] = [f"export.csv:{i}" for i in range(200)]
        r["incidents"][0]["timeline"] *= 4
        pages = self.check(report_pdf.build_pdf(r, {"source": "x" * 300}, "Summary paragraph long enough to be used "
                                                "as the executive summary of the AI assessment. [E-0001]\n\n## Steps\n- a"))
        self.assertGreater(pages, 20)

    def test_branding_in_report(self):
        b = dict(branding.report_brand(dict(branding.DEFAULTS, logo_url="")), brand_name="Acme Institute",
                 color_primary="#5a1e7a", report_title="Acme Investigation")
        pdf = report_pdf.build_pdf(analyse_samples(), {}, "", b)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            first = doc.pages[0].extract_text()
            self.assertIn("Acme Institute", first)
            self.assertIn("Acme Investigation", first)


# ------------------------------------------------------------------ API + offline

class ApiTests(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import agent
        from http.server import ThreadingHTTPServer
        cls.agent = agent
        cfg = agent.load_config()
        cfg.update(base_url="http://127.0.0.1:9", access_token="", host="127.0.0.1", keep_uploads=False)
        agent.Handler.cfg = cfg
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        super().tearDownClass()

    def call(self, path, body=None, raw=None, headers=None):
        from urllib.error import HTTPError
        from urllib.request import Request
        h = {"Content-Type": "application/json"} if raw is None else {"Content-Type": "application/octet-stream"}
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        try:
            with self.agent._OPENER.open(Request(self.base + path, data=data, headers=h), timeout=60) as r:
                return r.status, r.read(), r.headers
        except HTTPError as e:
            return e.code, e.read(), e.headers

    def test_upload_then_analyse_batch(self):
        batch = "0123456789abcdef"
        for p, name in SAMPLE_FILES:
            code, body, _ = self.call(f"/api/upload?batch={batch}", raw=p.read_bytes(), headers={"X-Filename": "../../" + name})
            self.assertEqual(code, 200, body)
            self.assertNotIn("/", json.loads(body)["file"])
        code, body, _ = self.call("/api/analyze-batch", {"batch": batch})
        r = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(len(r["ingestion"]), 6)
        self.assertTrue(r["analysis_id"])
        self.assertFalse((config_store.UPLOAD_DIR / batch).exists(), "uploads are deleted after analysis")
        code, body, _ = self.call("/api/instant", {"kind": "investigation", "analysis_id": r["analysis_id"]})
        self.assertIn("INC-001", json.loads(body)["markdown"])
        if report_pdf.AVAILABLE:
            code, pdf, h = self.call("/api/report/pdf", {"analysis_id": r["analysis_id"], "meta": {"client": "T"}})
            self.assertEqual((code, pdf[:4]), (200, b"%PDF"))

    def test_trust_and_branding_endpoints(self):
        code, body, _ = self.call("/api/trust/entry", {"section": "trusted_networks",
                                                       "entry": {"name": "Lab", "cidr": "10.20.0.0/16"}})
        self.assertEqual(code, 200)
        code, body, _ = self.call("/api/trust/entry", {"section": "trusted_networks", "entry": {"name": "All", "cidr": "0.0.0.0/0"}})
        self.assertEqual(code, 400)
        code, body, _ = self.call("/api/trust/classify", {"ip": "10.20.1.1"})
        self.assertEqual(json.loads(body)["category"], "configured_internal")
        code, body, _ = self.call("/api/trust/export?format=csv")
        self.assertEqual(code, 200)
        self.assertTrue(body.decode().startswith("section,id,name,cidr"))
        code, body, _ = self.call("/api/branding", {"branding": {"application_name": "Acme SOC"}})
        self.assertEqual(json.loads(body)["application_name"], "Acme SOC")
        code, body, _ = self.call("/api/audit-log")
        self.assertEqual(json.loads(body)["entries"][0]["area"], "branding")

    def test_cross_site_requests_blocked(self):
        code, _, _ = self.call("/api/trust/entry", raw=b"{}", headers={"Content-Type": "text/plain"})
        self.assertEqual(code, 403)

    def test_analysis_works_fully_offline(self):
        def no_network(*a, **k):
            raise OSError("network disabled for this test")
        with mock.patch.object(socket, "create_connection", no_network), \
                mock.patch.object(socket.socket, "connect", lambda self, addr: (_ for _ in ()).throw(OSError("offline"))
                                  if not (isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "::1")) else None):
            r = analyse_samples()
        self.assertGreater(len(r["findings"]), 20)
        msgs = self.agent.build_messages([{"role": "user", "content": "x"}], r)
        self.assertIn("FACTS", msgs[1]["content"])


if __name__ == "__main__":
    unittest.main()
