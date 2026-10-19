"""Tech Guardians branded PDF incident / audit report (same format as the VAPT portal).

Optional dependency: reportlab  (pip install reportlab). Everything else in the
agent works without it.
"""
import io
import re
from datetime import datetime

try:
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Circle, Drawing, Path, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, KeepTogether, ListFlowable,
                                    ListItem, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)
    AVAILABLE = True
except ImportError:  # pragma: no cover - reported to the user by the API
    AVAILABLE = False

import knowledge

# Branding - override any of these under "report" in config.json
BRAND = {
    "brand_name": "Tech Guardians",
    "brand_tagline": "Security Operations & Incident Response",
    "author_mark": "Designed & Developed by Rajesh Nehra · Master in Cyber Security",
    "author_name": "Rajesh Nehra",
    "author_title": "Master in Cyber Security",
    "classification": "CONFIDENTIAL",
    "doc_prefix": "TG-IR",
    "color_primary": "#123E6B",   # navy (shield)
    "color_accent": "#1E9E4F",    # green (the "G")
    "color_accent2": "#F59E1E",   # orange (the "T")
    "color_light": "#eef3f9",
    "color_ink": "#16202e",
}
STANDARDS = [
    "MITRE ATT&CK® Enterprise framework",
    "NIST SP 800-61 Rev. 2 - Computer Security Incident Handling Guide",
    "NIST SP 800-92 - Guide to Computer Security Log Management",
    "CIS Benchmarks (Linux / Windows)",
    "OWASP Top 10 (2021)",
    "CERT-In guidelines and incident reporting directions",
]
SEV_ORDER = ["critical", "high", "medium", "low", "info"]


def build_pdf(result, meta=None, ai_text="", brand=None):
    """Return the PDF as bytes. result = detector.analyze() or host_audit.run_audit() output."""
    if not AVAILABLE:
        raise RuntimeError("PDF reports need reportlab:  pip install reportlab")
    b = dict(BRAND, **(brand or {}))
    meta = dict(meta or {})
    meta.setdefault("ref", f"{b['doc_prefix']}-{datetime.now():%Y%m%d-%H%M}")
    r = _Report(result, meta, ai_text or "", b)
    return r.build()


def _clean(text):
    """Helvetica only covers Latin-1; drop emoji etc. so nothing renders as black boxes."""
    return str(text).encode("cp1252", errors="ignore").decode("cp1252")


def _esc(text):
    return _clean(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _Report:
    def __init__(self, result, meta, ai_text, brand):
        self.r, self.meta, self.ai, self.b = result, meta, ai_text, brand
        c = colors.HexColor
        self.PRIMARY, self.ACCENT, self.ACCENT2 = c(brand["color_primary"]), c(brand["color_accent"]), \
            c(brand["color_accent2"])
        self.LIGHT, self.INK = c(brand["color_light"]), c(brand["color_ink"])
        self.SEV = {"critical": c("#b00020"), "high": c("#e2571e"), "medium": c("#e0a800"),
                    "low": c("#2a9d8f"), "info": c("#5a6470"), "clean": c("#2a9d8f")}
        self.title = "Live Host Security Audit Report" if result.get("kind") == "host" \
            else "Security Log Analysis & Incident Report"
        self.st = self._styles()
        self.n = 0  # section counter

    # ------------------------------------------------------------ styles & page
    def _styles(self):
        ss = getSampleStyleSheet()
        P, A, I = self.PRIMARY, self.ACCENT, self.INK
        ss.add(ParagraphStyle("TGTitle", parent=ss["Title"], textColor=P, fontSize=28, leading=32))
        ss.add(ParagraphStyle("TGH1", parent=ss["Heading1"], textColor=P, fontSize=16, spaceBefore=14, spaceAfter=6))
        ss.add(ParagraphStyle("TGH2", parent=ss["Heading2"], textColor=A, fontSize=12.5, spaceBefore=10, spaceAfter=4))
        ss.add(ParagraphStyle("TGBody", parent=ss["BodyText"], textColor=I, fontSize=9.5, leading=14,
                              alignment=TA_JUSTIFY))
        ss.add(ParagraphStyle("TGSmall", parent=ss["BodyText"], textColor=colors.grey, fontSize=8, leading=11))
        ss.add(ParagraphStyle("TGCellH", parent=ss["BodyText"], textColor=colors.white, fontSize=9, leading=12))
        ss.add(ParagraphStyle("TGCell", parent=ss["BodyText"], textColor=I, fontSize=8.8, leading=12))
        ss.add(ParagraphStyle("TGCode", parent=ss["BodyText"], fontName="Courier", fontSize=7.6, leading=10,
                              textColor=colors.HexColor("#1b2733"), backColor=self.LIGHT, borderPadding=3))
        return ss

    def _page(self, canvas, doc):
        b, w, h = self.b, *A4
        canvas.saveState()
        canvas.setFillColor(self.PRIMARY)
        canvas.rect(0, h - 16 * mm, w, 16 * mm, fill=1, stroke=0)
        canvas.setFillColor(self.ACCENT)
        canvas.rect(0, h - 16 * mm, 6 * mm, 16 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(12 * mm, h - 11 * mm, _clean(b["brand_name"]))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(w - 12 * mm, h - 11 * mm, _clean(f"{b['classification']} — {self.title}"))
        canvas.setStrokeColor(self.ACCENT)
        canvas.setLineWidth(0.6)
        canvas.line(12 * mm, 13 * mm, w - 12 * mm, 13 * mm)
        canvas.setFillColor(self.PRIMARY)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(12 * mm, 9 * mm, _clean(b["author_mark"]))
        canvas.setFillColor(colors.grey)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(w - 12 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def build(self):
        buf = io.BytesIO()
        doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=22 * mm,
                              bottomMargin=16 * mm, title=_clean(f"{self.b['brand_name']} {self.title}"),
                              author=_clean(self.b["author_name"]))
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="m")
        doc.addPageTemplates([PageTemplate(id="tg", frames=[frame], onPage=self._page)])
        s = self._cover() + [PageBreak()] + self._doc_control() + self._toc() + [PageBreak()]
        s += self._exec_summary() + [PageBreak()]
        s += self._scope() + [PageBreak()]
        s += self._summary_table() + [PageBreak()]
        s += self._detailed()
        if self.r.get("ip_profiles") or self.r.get("timeline"):
            s += [PageBreak()] + self._threat_actors()
        if any((self.r.get("iocs") or {}).values()):
            s += self._iocs()
        s += [PageBreak()] + self._roadmap() + self._mitre()
        if self.ai.strip():
            s += [PageBreak()] + self._ai_section()
        s += self._appendix()
        doc.build(s)
        return buf.getvalue()

    def _h1(self, title):
        self.n += 1
        return Paragraph(f"{self.n}. {_esc(title)}", self.st["TGH1"])

    # ------------------------------------------------------------ drawings
    def _logo(self, height=None):
        height = height or 38 * mm
        d = Drawing(240, 300)
        P, G, O = self.PRIMARY, self.ACCENT, self.ACCENT2
        y = lambda v: 300 - v  # SVG coordinates are top-down
        shield = Path(fillColor=P, strokeColor=None)
        shield.moveTo(120, y(58)); shield.lineTo(200, y(74)); shield.lineTo(200, y(150))
        shield.curveTo(200, y(208), 168, y(244), 120, y(270))
        shield.curveTo(72, y(244), 40, y(208), 40, y(150))
        shield.lineTo(40, y(74)); shield.closePath()
        d.add(shield)
        d.add(Circle(122, y(196), 48, fillColor=G, strokeColor=None))
        d.add(Circle(122, y(196), 27, fillColor=P, strokeColor=None))
        d.add(Rect(122, y(208), 68, 24, fillColor=P, strokeColor=None))
        d.add(Rect(148, y(206), 32, 13, fillColor=G, strokeColor=None))
        d.add(Rect(167, y(216), 13, 23, fillColor=G, strokeColor=None))
        d.add(Rect(74, y(114), 96, 22, fillColor=O, strokeColor=None))
        d.add(Rect(112, y(178), 20, 66, fillColor=O, strokeColor=None))
        k = height / 300
        d.scale(k, k)
        d.width, d.height = 240 * k, 300 * k
        d.hAlign = "CENTER"
        return d

    def _gauge(self):
        score, level = self.r.get("risk_score", 0), self.r.get("risk_level", "-")
        col = self.SEV.get(level, self.SEV["info"])
        d = Drawing(170, 136)
        d.add(Circle(85, 80, 48, fillColor=self.LIGHT, strokeColor=col, strokeWidth=6))
        d.add(String(85, 84, str(score), fontSize=26, fillColor=col, textAnchor="middle", fontName="Helvetica-Bold"))
        d.add(String(85, 68, "/ 100", fontSize=9, fillColor=self.INK, textAnchor="middle"))
        d.add(String(85, 6, level.upper(), fontSize=11, fillColor=col, textAnchor="middle",
                     fontName="Helvetica-Bold"))
        return d

    def _grade(self):
        g = self.r.get("grade", "-")
        pal = {"A": "#2a9d8f", "B": "#5aa84b", "C": "#e0a800", "D": "#e2571e", "E": "#d1391c", "F": "#b00020"}
        d = Drawing(70, 70)
        d.add(Rect(5, 5, 60, 60, rx=8, ry=8, fillColor=colors.HexColor(pal.get(g, "#5a6470")), strokeColor=None))
        d.add(String(35, 22, g, fontSize=34, fillColor=colors.white, textAnchor="middle", fontName="Helvetica-Bold"))
        return d

    def _bar(self, labels, values, bar_colors=None, width=460, height=160):
        d = Drawing(width, height)
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 30, 30, width - 50, height - 45
        bc.data = [values]
        top = max([1] + values)
        bc.valueAxis.valueMin, bc.valueAxis.valueMax = 0, top
        bc.valueAxis.valueStep = max(1, top // 5)
        bc.valueAxis.labels.fontSize = 7
        bc.categoryAxis.categoryNames = labels
        bc.categoryAxis.labels.fontSize = 6.5 if len(labels) > 8 else 8
        if len(labels) > 8:
            bc.categoryAxis.labels.angle = 35
            bc.categoryAxis.labels.boxAnchor = "ne"
        bc.bars.strokeColor = None
        bc.bars.fillColor = self.PRIMARY
        for i, c in enumerate(bar_colors or []):
            bc.bars[(0, i)].fillColor = c
        d.add(bc)
        return d

    def _chip(self, sev, w=None):
        w = w or 22 * mm
        t = Table([[Paragraph(f"<b>{sev.upper()}</b>", ParagraphStyle(
            "c", textColor=colors.white, fontSize=8, alignment=TA_CENTER))]], colWidths=[w])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), self.SEV.get(sev, colors.grey)),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    def _grid(self, rows, widths, header=True):
        t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, self.LIGHT]),
                 ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                 ("LEFTPADDING", (0, 0), (-1, -1), 5)]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), self.PRIMARY))
        t.setStyle(TableStyle(style))
        return t

    def _kv(self, rows, key_w=None):
        key_w = key_w or 48 * mm
        t = Table([[k, Paragraph(_esc(v), self.st["TGCell"])] for k, v in rows], colWidths=[key_w, None])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), self.PRIMARY), ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, self.LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
        return t

    def _cell(self, text, style="TGCell"):
        return Paragraph(_esc(text), self.st[style])

    def _target(self):
        if self.r.get("kind") == "host":
            h = self.r.get("host", {})
            return f"{h.get('hostname', '-')} ({h.get('os', '-')})"
        return self.meta.get("source") or "Uploaded log file"

    # ------------------------------------------------------------ sections
    def _cover(self):
        b, m, r = self.b, self.meta, self.r
        flow = [Spacer(1, 14 * mm), self._logo(), Spacer(1, 8 * mm),
                Paragraph(_esc(b["brand_name"]), self.st["TGTitle"]),
                Paragraph(_esc(b["brand_tagline"]), ParagraphStyle("cs", alignment=TA_CENTER,
                                                                    textColor=self.ACCENT, fontSize=12)),
                Spacer(1, 3 * mm), HRFlowable(width="55%", thickness=1.4, color=self.ACCENT), Spacer(1, 12 * mm),
                Paragraph(_esc(self.title), ParagraphStyle("rt", alignment=TA_CENTER, textColor=self.INK,
                                                           fontSize=18)), Spacer(1, 10 * mm)]
        flow.append(self._kv([
            ("Target / Source", self._target()),
            ("Client / Organisation", m.get("client") or "-"),
            ("Analyst", m.get("assessor") or b["brand_name"]),
            ("Reference", m["ref"]),
            ("Overall Risk", f"{r.get('risk_level', '-').upper()} (score {r.get('risk_score', 0)}/100)"),
            ("Security Grade", r.get("grade", "-")),
            ("Report Date", datetime.now().strftime("%d %B %Y")),
            ("Classification", b["classification"]),
        ]))
        flow += [Spacer(1, 12 * mm),
                 Paragraph(f"<b>{_esc(b['author_mark'])}</b>", ParagraphStyle(
                     "auth", alignment=TA_CENTER, textColor=self.PRIMARY, fontSize=10)), Spacer(1, 4 * mm),
                 Paragraph("This document is confidential and intended solely for the named client. It describes "
                           "security events and weaknesses identified on systems the client owns or is "
                           "<b>authorised</b> to assess, and must be handled on a strict need-to-know basis.",
                           self.st["TGSmall"])]
        return flow

    def _doc_control(self):
        b, m = self.b, self.meta
        rows = [[self._cell("Field", "TGCellH"), self._cell("Detail", "TGCellH")]] + [
            [self._cell(k), self._cell(v)] for k, v in [
                ("Document title", f"{b['brand_name']} {self.title}"), ("Document reference", m["ref"]),
                ("Version", "1.0"), ("Prepared by", m.get("assessor") or b["brand_name"]),
                ("Author / Developer", f"{b['author_name']} ({b['author_title']})"),
                ("Client", m.get("client") or "-"), ("Date of report", datetime.now().strftime("%d %B %Y")),
                ("Generated by", "CyberSec AI Agent (offline, local AI)"),
                ("Classification", b["classification"]), ("Distribution", "Named client only")]]
        return [Paragraph("Document Control", self.st["TGH1"]), self._grid(rows, [52 * mm, None]),
                Spacer(1, 6 * mm), Paragraph("Confidentiality & Legal Notice", self.st["TGH2"]),
                Paragraph("This analysis was performed on data supplied by, or systems owned by, the client. Findings "
                          "reflect the evidence available at the time of analysis; missing or tampered logs may hide "
                          "further activity. Automated detections should be validated by an analyst before "
                          "disciplinary or legal action.", self.st["TGBody"])]

    def _toc(self):
        items = ["Executive Summary", "Scope & Methodology", "Findings Summary", "Detailed Findings"]
        if self.r.get("ip_profiles") or self.r.get("timeline"):
            items.append("Attack Timeline & Threat Actors")
        if any((self.r.get("iocs") or {}).values()):
            items.append("Indicators of Compromise")
        items += ["Remediation Roadmap", "MITRE ATT&CK Mapping"]
        if self.ai.strip():
            items.append("AI Analyst Assessment")
        items.append("Appendices")
        return [Spacer(1, 6 * mm), Paragraph("Table of Contents", self.st["TGH1"]),
                ListFlowable([ListItem(Paragraph(f"{i}. {t}", self.st["TGBody"]), leftIndent=6)
                              for i, t in enumerate(items, 1)], bulletType="bullet", start="square")]

    def _exec_summary(self):
        r = self.r
        counts = r.get("summary", {})
        total = len(r.get("findings", []))
        if r.get("kind") == "host":
            intro = (f"A live security audit of host <b>{_esc(self._target())}</b> was performed, covering "
                     f"{len(r.get('checks_run', []))} control areas and the system's own logs.")
        else:
            tr = r.get("time_range") or {}
            span = f" covering {tr['start']} to {tr['end']}" if tr.get("start") else ""
            intro = (f"<b>{r.get('lines', 0):,}</b> log lines from <b>{_esc(self._target())}</b>{span} were "
                     f"analysed ({_esc(', '.join(r.get('log_types', [])))}).")
        flow = [self._h1("Executive Summary"), Paragraph(
            f"{intro} A total of <b>{total}</b> finding(s) were identified, giving an overall risk rating of "
            f"<b>{r.get('risk_level', '-').upper()}</b> (score {r.get('risk_score', 0)}/100) and a security grade "
            f"of <b>{r.get('grade', '-')}</b>.", self.st["TGBody"]), Spacer(1, 4 * mm)]
        rows = [[Paragraph(f"<b>{s.capitalize()}</b>", ParagraphStyle("x", textColor=colors.white, fontSize=9)),
                 Paragraph(f"<b>{counts.get(s, 0)}</b>", ParagraphStyle("y", textColor=colors.white, fontSize=9,
                                                                        alignment=TA_CENTER))] for s in SEV_ORDER]
        ct = Table(rows, colWidths=[30 * mm, 14 * mm])
        cst = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        cst += [("BACKGROUND", (0, i), (-1, i), self.SEV[s]) for i, s in enumerate(SEV_ORDER)]
        ct.setStyle(TableStyle(cst))
        lay = Table([[self._gauge(), self._grade(), ct]], colWidths=[46 * mm, 26 * mm, None])
        lay.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        flow += [lay, Spacer(1, 4 * mm), Paragraph("Severity Distribution", self.st["TGH2"]),
                 self._bar([s.capitalize() for s in SEV_ORDER], [counts.get(s, 0) for s in SEV_ORDER],
                           [self.SEV[s] for s in SEV_ORDER])]
        flow.append(Paragraph("Key Risk Themes", self.st["TGH2"]))
        top = [f for f in r.get("findings", []) if f["severity"] in ("critical", "high")][:6]
        if top:
            flow.append(ListFlowable([ListItem(Paragraph(
                f"<b>{_esc(f['title'])}</b> - {_esc(f.get('impact') or f.get('description', ''))}",
                self.st["TGBody"])) for f in top], bulletType="bullet"))
        else:
            flow.append(Paragraph("No critical or high-risk issues were identified. Lower-severity items remain; "
                                  "see the detailed findings.", self.st["TGBody"]))
        summary = _first_paragraph(self.ai)
        if summary:
            flow += [Paragraph("Analyst Summary (AI-assisted)", self.st["TGH2"]),
                     Paragraph(_inline_md(summary), self.st["TGBody"])]
        return flow

    def _scope(self):
        r = self.r
        flow = [self._h1("Scope & Methodology"), Paragraph(f"{self.n}.1 Scope", self.st["TGH2"])]
        if r.get("kind") == "host":
            h = r.get("host", {})
            flow.append(self._kv([("Hostname", h.get("hostname", "-")), ("Operating system", h.get("os", "-")),
                                  ("Kernel", f"{h.get('kernel', '-')} ({h.get('arch', '')})"),
                                  ("Hardware", f"{h.get('cpus', '-')} CPUs, {h.get('ram_gb', '-')} GB RAM"),
                                  ("Uptime", f"{h.get('uptime_days', '-')} days"),
                                  ("Audit privileges", h.get("audited_as", "-")),
                                  ("Logs analysed", ", ".join(r.get("log_sources") or []) or "none readable")]))
        else:
            tr = r.get("time_range") or {}
            flow.append(self._kv([("Source", self._target()), ("Lines analysed", f"{r.get('lines', 0):,}"),
                                  ("Log types", ", ".join(r.get("log_types", []))),
                                  ("Time range", f"{tr.get('start') or '-'}  to  {tr.get('end') or '-'}"),
                                  ("Suspicious lines", str(r.get("suspicious_lines", "-")))]))
        if self.meta.get("scope_note"):
            flow.append(Paragraph(_esc(self.meta["scope_note"]), self.st["TGBody"]))
        flow += [Paragraph(f"{self.n}.2 Methodology", self.st["TGH2"]), Paragraph(
            "Analysis was performed fully offline. A deterministic rule engine examined every record for known "
            "attack patterns and correlated events across records (brute force followed by success, enumeration, "
            "port scans). Findings were enriched with an offline knowledge base and mapped to MITRE ATT&amp;CK. "
            "A locally hosted language model was used only to summarise and prioritise; no data left the "
            "analysis machine. The approach aligns with:", self.st["TGBody"]),
            ListFlowable([ListItem(Paragraph(_esc(x), self.st["TGBody"])) for x in STANDARDS], bulletType="bullet"),
            Paragraph(f"{self.n}.3 Severity Model", self.st["TGH2"]), Paragraph(
                "Findings are rated Critical / High / Medium / Low / Informational, indicatively aligned to CVSS "
                "v3.1 bands (Critical 9.0-10.0, High 7.0-8.9, Medium 4.0-6.9, Low 0.1-3.9). The overall risk score "
                "(0-100) weights each finding by severity; grade A (no risk) to F (critical).", self.st["TGBody"])]
        if r.get("checks_run"):
            flow += [Paragraph(f"{self.n}.4 Checks Performed", self.st["TGH2"]),
                     ListFlowable([ListItem(Paragraph(_esc(c), self.st["TGBody"])) for c in r["checks_run"]],
                                  bulletType="bullet")]
        return flow

    def _summary_table(self):
        flow = [self._h1("Findings Summary")]
        f = self.r.get("findings", [])
        if not f:
            return flow + [Paragraph("No findings were produced by the automated checks.", self.st["TGBody"])]
        rows = [[self._cell(h, "TGCellH") for h in ("ID", "Finding", "Severity", "Events", "MITRE", "Category")]]
        for i, x in enumerate(f, 1):
            rows.append([self._cell(f"F-{i:02d}"), self._cell(x["title"]),
                         Paragraph(x["severity"].upper(), ParagraphStyle(
                             "sv", fontSize=8.5, textColor=self.SEV[x["severity"]], fontName="Helvetica-Bold")),
                         self._cell(x.get("count", 1)), self._cell(x.get("mitre", "-")),
                         self._cell(x.get("category", "-"))])
        return flow + [self._grid(rows, [14 * mm, None, 19 * mm, 15 * mm, 20 * mm, 30 * mm])]

    def _detailed(self):
        flow = [self._h1("Detailed Findings")]
        for i, f in enumerate(self.r.get("findings", []), 1):
            head = Table([[Paragraph(f"<b>F-{i:02d}  {_esc(f['title'])}</b>", self.st["TGH2"]),
                           self._chip(f["severity"])]], colWidths=[None, 24 * mm])
            head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            rows = [("Severity / CVSS", f"{f['severity'].upper()} · CVSS band {f.get('cvss_band', '-')}"),
                    ("Category", f.get("category", "-")),
                    ("MITRE ATT&CK", f"{f.get('mitre', '-')} {f.get('mitre_name', '')}".strip()),
                    ("Events", str(f.get("count", 1)))]
            if f.get("first_seen"):
                rows.append(("First / last seen", f"{f['first_seen']}  /  {f['last_seen']}"))
            if f.get("ips"):
                rows.append(("Source IPs", ", ".join(f["ips"])))
            for k, key in (("Description", "description"), ("Impact", "impact")):
                if f.get(key):
                    rows.append((k, f[key]))
            key = lambda k: Paragraph(f"<b>{_esc(k)}</b>", self.st["TGCell"])
            cells = [[key(k), self._cell(v)] for k, v in rows]
            if f.get("samples"):
                ev = "<br/>".join((f"L{s['line']}: " if s.get("line") else "") + _esc(s["text"])
                                  for s in f["samples"][:4])
                cells.append([key("Evidence"), Paragraph(ev, self.st["TGCode"])])
            if f.get("recommendation"):
                cells.append([key("Remediation"), self._cell(f["recommendation"])])
            if f.get("references"):
                cells.append([key("References"), Paragraph("<br/>".join(_esc(x) for x in f["references"]),
                                                                  self.st["TGCell"])])
            t = Table(cells, colWidths=[32 * mm, None])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, -1), self.LIGHT),
                                   ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
            # Keep short findings on one page; long ones may split across pages
            flow += [Spacer(1, 3 * mm)] + ([KeepTogether([head, t])] if len(cells) < 12 else [head, t])
        if not self.r.get("findings"):
            flow.append(Paragraph("No findings to detail. A manual review is still recommended.", self.st["TGBody"]))
        return flow

    def _threat_actors(self):
        flow = [self._h1("Attack Timeline & Threat Actors")]
        tl = self.r.get("timeline") or []
        if tl:
            flow.append(Paragraph(f"Suspicious events per {self.r.get('timeline_bucket', 'hour')}", self.st["TGH2"]))
            tl = tl[-30:]
            flow.append(self._bar([k[5:] if len(k) > 10 else k for k, _ in tl], [v for _, v in tl],
                                  [self.ACCENT2] * len(tl), height=180))
        prof = self.r.get("ip_profiles") or []
        if prof:
            flow.append(Paragraph("Source IP Profiles", self.st["TGH2"]))
            rows = [[self._cell(h, "TGCellH") for h in ("IP address", "Verdict", "Events", "Activity", "First / last seen")]]
            for p in prof[:25]:
                rows.append([self._cell(p["ip"] + ("" if p.get("public") else " (internal)")),
                             Paragraph(f"<b>{p['verdict']}</b>", ParagraphStyle(
                                 "v", fontSize=8.5, textColor=self.SEV[p["severity"]])),
                             self._cell(p["events"]), self._cell("; ".join(p["activity"][:5])),
                             self._cell(f"{p.get('first_seen') or '-'} / {p.get('last_seen') or '-'}")])
            flow.append(self._grid(rows, [30 * mm, 20 * mm, 14 * mm, None, 38 * mm]))
        users = self.r.get("targeted_users") or []
        if users:
            flow += [Paragraph("Accounts Targeted or Affected", self.st["TGH2"]),
                     Paragraph(_esc(", ".join(f"{u} ({n})" for u, n in users)), self.st["TGBody"])]
        return flow

    def _iocs(self):
        i = self.r.get("iocs") or {}
        flow = [self._h1("Indicators of Compromise"), Paragraph(
            "Indicators extracted from suspicious records. Feed these into firewalls, EDR, SIEM watch-lists and "
            "threat-intelligence platforms, and search other systems for them.", self.st["TGBody"])]
        rows = [[self._cell("Type", "TGCellH"), self._cell("Indicator", "TGCellH")]]
        for key, label in (("ips", "IP address"), ("domains", "Domain"), ("urls", "URL"), ("files", "File path")):
            for v in i.get(key) or []:
                rows.append([self._cell(label), Paragraph(_esc(v), self.st["TGCode"])])
        if i.get("users"):
            rows.append([self._cell("Accounts"), Paragraph(_esc(", ".join(i["users"])), self.st["TGCode"])])
        if len(rows) > 1:
            flow.append(self._grid(rows[:120], [30 * mm, None]))
        return flow

    def _roadmap(self):
        flow = [self._h1("Remediation Roadmap")]
        f = self.r.get("findings", [])
        for phase, sevs in (("Immediate (0-24 hours)", ("critical",)), ("Short term (1-7 days)", ("high",)),
                            ("Medium term (1-4 weeks)", ("medium",)), ("Hardening backlog", ("low", "info"))):
            items = [x for x in f if x["severity"] in sevs]
            if items:
                flow += [Paragraph(phase, self.st["TGH2"]), ListFlowable([ListItem(Paragraph(
                    f"<b>{_esc(x['title'])}</b>: {_esc(x.get('recommendation') or 'Review and verify.')}",
                    self.st["TGBody"])) for x in items[:15]], bulletType="bullet")]
        bad = [p["ip"] for p in self.r.get("ip_profiles", []) if p["verdict"] in ("Malicious", "Suspicious")
               and p.get("public")]
        if bad:
            flow += [Paragraph("Block at the perimeter", self.st["TGH2"]),
                     Paragraph(_esc("Deny inbound traffic from: " + ", ".join(bad)), self.st["TGBody"])]
        if not f:
            flow.append(Paragraph("No remediation actions required.", self.st["TGBody"]))
        return flow

    def _mitre(self):
        flow = [self._h1("MITRE ATT&CK Mapping")]
        agg = {}
        for f in self.r.get("findings", []):
            t = f.get("mitre")
            if t and t != "-":
                a = agg.setdefault(t, [0, set()])
                a[0] += f.get("count", 1)
                a[1].add(f["title"])
        rows = [[self._cell(h, "TGCellH") for h in ("Technique", "Name", "Events", "Findings")]]
        for t, (n, titles) in sorted(agg.items(), key=lambda x: -x[1][0]):
            rows.append([self._cell(t), self._cell(knowledge.MITRE_NAMES.get(t, "")), self._cell(n),
                         self._cell("; ".join(sorted(titles)))])
        if len(rows) == 1:
            rows.append([self._cell("-"), self._cell("No mapped techniques"), self._cell(0), self._cell("")])
        return flow + [self._grid(rows, [22 * mm, 48 * mm, 15 * mm, None])]

    def _ai_section(self):
        flow = [self._h1("AI Analyst Assessment"), Paragraph(
            "Generated by a locally hosted language model from the findings above. Review before acting.",
            self.st["TGSmall"]), Spacer(1, 2 * mm)]
        return flow + _markdown_flow(self.ai, self.st)

    def _appendix(self):
        r, b = self.r, self.b
        flow = [PageBreak(), self._h1("Appendices"), Paragraph("Tools & Environment", self.st["TGH2"]),
                Paragraph("CyberSec AI Agent - offline rule engine (log detection & correlation, Linux host audit), "
                          "offline knowledge base, locally hosted LLM via Ollama / OpenAI-compatible server.",
                          self.st["TGBody"])]
        if self.meta.get("model"):
            flow.append(Paragraph(_esc(f"AI model: {self.meta['model']}"), self.st["TGBody"]))
        if r.get("top_ips"):
            flow += [Paragraph("Most Frequent IP Addresses", self.st["TGH2"]),
                     Paragraph(_esc(", ".join(f"{ip} ({n})" for ip, n in r["top_ips"])), self.st["TGBody"])]
        flow += [Spacer(1, 6 * mm), HRFlowable(width="100%", thickness=0.6, color=self.ACCENT),
                 Paragraph(f"<b>{_esc(b['author_mark'])}</b>", ParagraphStyle(
                     "end", alignment=TA_CENTER, textColor=self.PRIMARY, fontSize=10)),
                 Paragraph(_esc(f"- End of Report · {b['brand_name']} -"), ParagraphStyle(
                     "e2", alignment=TA_CENTER, textColor=colors.grey, fontSize=8))]
        return flow


# ------------------------------------------------------------ markdown -> flowables

def _inline_md(text):
    t = _esc(text)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', t)
    return t


def _first_paragraph(md):
    in_code = False
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
        elif not in_code and s and not s.startswith(("#", "-", "*", "|", ">")) and len(s) > 60:
            return s[:900]
    return ""


def _markdown_flow(md, st):
    flow, code, bullets = [], None, []

    def flush():
        if bullets:
            flow.append(ListFlowable([ListItem(Paragraph(_inline_md(b), st["TGBody"])) for b in bullets],
                                     bulletType="bullet"))
            bullets.clear()

    for line in md.splitlines():
        if line.strip().startswith("```"):
            if code is None:
                flush()
                code = []
            else:
                flow.append(Paragraph("<br/>".join(_esc(c) for c in code) or " ", st["TGCode"]))
                flow.append(Spacer(1, 2 * mm))
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        s = line.strip()
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            flush()
            flow.append(Paragraph(_inline_md(m.group(2).strip("# ")), st["TGH2"]))
        elif re.match(r"^([-*]|\d+[.)])\s+", s):
            bullets.append(re.sub(r"^([-*]|\d+[.)])\s+", "", s))
        elif s:
            flush()
            flow.append(Paragraph(_inline_md(s), st["TGBody"]))
    flush()
    if code:
        flow.append(Paragraph("<br/>".join(_esc(c) for c in code), st["TGCode"]))
    return flow
