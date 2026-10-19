"""Branded A4 PDF investigation report (Tech Guardians VAPT report format, 15 sections).

Optional dependency: reportlab (pip install reportlab / apt install python3-reportlab).

A4 layout rules used throughout (they are what keeps Section 4 on the page):
  * every width is derived from the frame width (A4 minus margins) - nothing is hard-coded wider;
  * table cells are Paragraphs, so text wraps; evidence uses character-level wrapping (CJK mode)
    so long URLs, paths, Base64 and commands break inside the cell instead of overflowing;
  * a finding is a CARD: a small header table, a fixed 4-column metrics grid, then paragraphs
    and row-limited tables. Paragraphs and table rows can flow onto the next page, so no single
    element is ever taller than a page (the old one-table-per-finding layout could not split);
  * long tables repeat their header row on each page; cell text is capped so a row always fits;
  * CondPageBreak keeps a card's header with its first lines; "Page X of Y" in every footer.
"""
import io
import re
from datetime import datetime

try:
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Circle, Drawing, Path, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, HRFlowable, Image, KeepTogether,
                                    ListFlowable, ListItem, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                    TableStyle)
    AVAILABLE = True
except ImportError:  # pragma: no cover - reported to the user by the API
    AVAILABLE = False

import knowledge
import rules as rulebook

# Branding defaults - normally supplied by branding.report_brand(branding.load())
BRAND = {
    "brand_name": "Tech Guardians",
    "brand_tagline": "Security Operations & Incident Response",
    "report_title": "",
    "author_mark": "Designed & Developed by Rajesh Nehra · Master in Cyber Security",
    "author_name": "Rajesh Nehra",
    "author_title": "Master in Cyber Security",
    "header_text": "",
    "classification": "CONFIDENTIAL",
    "doc_prefix": "TG-IR",
    "report_version": "1.0",
    "contact": "",
    "address": "",
    "notice": ("This document is confidential and intended solely for the named recipient. It describes security "
               "events identified on systems the organisation owns or is authorised to assess, and must be handled "
               "on a strict need-to-know basis."),
    "logo_file": "",
    "color_primary": "#123E6B",
    "color_accent": "#1E9E4F",
    "color_accent2": "#F59E1E",
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
MARGIN = 16  # mm
CELL_MAX = 900  # characters per table cell - keeps every row shorter than a page


def build_pdf(result, meta=None, ai_text="", brand=None):
    """Return the PDF as bytes. result = pipeline.analyze_*() or host_audit.run_audit() output."""
    if not AVAILABLE:
        raise RuntimeError("PDF reports need reportlab:  pip install reportlab")
    b = dict(BRAND)
    b.update({k: v for k, v in (brand or {}).items() if v not in (None,)})
    meta = dict(meta or {})
    meta.setdefault("ref", f"{b['doc_prefix']}-{datetime.now():%Y%m%d-%H%M}")
    return _Report(result, meta, ai_text or "", b).build()


def _clean(text):
    """Helvetica only covers Latin-1; map common symbols, drop the rest (no black boxes)."""
    s = str(text if text is not None else "")
    s = s.replace("→", "->").replace("←", "<-").replace("≤", "<=").replace("≥", ">=")
    return s.encode("cp1252", errors="ignore").decode("cp1252")


def _esc(text, limit=None):
    s = _clean(text)
    if limit and len(s) > limit:
        s = s[:limit] + " ..."
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _NumberedCanvas(rl_canvas.Canvas if AVAILABLE else object):
    """Two-pass canvas so every footer can say 'Page X of Y'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.grey)
            self.drawRightString(A4[0] - 12 * mm, 9 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


class _Report:
    def __init__(self, result, meta, ai_text, brand):
        self.r, self.meta, self.ai, self.b = result, meta, ai_text, brand
        c = colors.HexColor
        self.PRIMARY, self.ACCENT, self.ACCENT2 = c(brand["color_primary"]), c(brand["color_accent"]), \
            c(brand["color_accent2"])
        self.LIGHT, self.INK = c(brand["color_light"]), c(brand["color_ink"])
        self.SEV = {"critical": c("#b00020"), "high": c("#e2571e"), "medium": c("#b58400"),
                    "low": c("#2a9d8f"), "info": c("#5a6470"), "clean": c("#2a9d8f")}
        self.host_mode = result.get("kind") == "host"
        self.title = brand.get("report_title") or ("Live Host Security Audit Report" if self.host_mode
                                                   else "Security Incident Analysis Report")
        self.W = A4[0] - 2 * MARGIN * mm          # usable frame width
        self.st = self._styles()
        self.n = 0
        self.findings = result.get("findings", [])
        for i, f in enumerate(self.findings, 1):
            f.setdefault("fid", f"F-{i:02d}")

    # ------------------------------------------------------------ styles & page furniture
    def _styles(self):
        ss = getSampleStyleSheet()
        P, A, I = self.PRIMARY, self.ACCENT, self.INK
        add = lambda name, **kw: ss.add(ParagraphStyle(name, **kw))
        add("TGTitle", parent=ss["Title"], textColor=P, fontSize=26, leading=30)
        add("TGH1", parent=ss["Heading1"], textColor=P, fontSize=15.5, leading=19, spaceBefore=12, spaceAfter=6)
        add("TGH2", parent=ss["Heading2"], textColor=A, fontSize=12, leading=15, spaceBefore=9, spaceAfter=4)
        add("TGH3", parent=ss["Heading3"], textColor=P, fontSize=10.2, leading=13, spaceBefore=6, spaceAfter=2)
        add("TGBody", parent=ss["BodyText"], textColor=I, fontSize=9.4, leading=13.2, alignment=TA_JUSTIFY,
            splitLongWords=1)
        add("TGSmall", parent=ss["BodyText"], textColor=colors.HexColor("#5a6470"), fontSize=7.8, leading=10.4)
        add("TGCellH", parent=ss["BodyText"], textColor=colors.white, fontSize=8.4, leading=10.5,
            fontName="Helvetica-Bold")
        add("TGCell", parent=ss["BodyText"], textColor=I, fontSize=8.4, leading=10.8, alignment=TA_LEFT,
            splitLongWords=1)
        add("TGCellB", parent=ss["TGCell"], fontName="Helvetica-Bold")
        add("TGMetricL", parent=ss["BodyText"], textColor=colors.HexColor("#5a6470"), fontSize=6.9, leading=8.4)
        add("TGMetricV", parent=ss["BodyText"], textColor=I, fontSize=9.2, leading=11, fontName="Helvetica-Bold")
        # Evidence/code: wrap at ANY character so URLs, Base64 and paths never overflow the page
        add("TGCode", parent=ss["BodyText"], fontName="Courier", fontSize=7.3, leading=9.2,
            textColor=colors.HexColor("#1b2733"), backColor=self.LIGHT, borderPadding=(3, 4, 3, 4),
            wordWrap="CJK", spaceBefore=2, spaceAfter=4)
        add("TGCodeCell", parent=ss["TGCell"], fontName="Courier", fontSize=7.3, leading=9.2, wordWrap="CJK")
        return ss

    def _page(self, canvas, doc):
        b, (w, h) = self.b, A4
        canvas.saveState()
        canvas.setFillColor(self.PRIMARY)
        canvas.rect(0, h - 16 * mm, w, 16 * mm, fill=1, stroke=0)
        canvas.setFillColor(self.ACCENT)
        canvas.rect(0, h - 16 * mm, 6 * mm, 16 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(12 * mm, h - 10.2 * mm, _clean(b["brand_name"])[:60])
        canvas.setFont("Helvetica", 7.5)
        right = f"{b['classification']} — {self.title}"
        canvas.drawRightString(w - 12 * mm, h - 9.4 * mm, _clean(right)[:110])
        if b.get("header_text"):
            canvas.setFont("Helvetica", 6.8)
            canvas.drawRightString(w - 12 * mm, h - 13.2 * mm, _clean(b["header_text"])[:120])
        canvas.setStrokeColor(self.ACCENT)
        canvas.setLineWidth(0.6)
        canvas.line(12 * mm, 13 * mm, w - 12 * mm, 13 * mm)
        canvas.setFillColor(self.PRIMARY)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(12 * mm, 9 * mm, _clean(b["author_mark"])[:95])
        canvas.setFillColor(colors.grey)
        canvas.setFont("Helvetica", 6.6)
        canvas.drawString(12 * mm, 5.6 * mm, _clean(f"Ref {self.meta['ref']} · v{b.get('report_version') or '1.0'}"
                                                     f" · generated {datetime.now():%Y-%m-%d %H:%M}"))
        canvas.restoreState()

    def build(self):
        buf = io.BytesIO()
        doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGIN * mm, rightMargin=MARGIN * mm, topMargin=22 * mm,
                              bottomMargin=17 * mm, title=_clean(f"{self.b['brand_name']} {self.title}"),
                              author=_clean(self.b.get("author_name") or self.b["brand_name"]))
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="m", leftPadding=0, rightPadding=0)
        doc.addPageTemplates([PageTemplate(id="tg", frames=[frame], onPage=self._page)])
        s = self._cover() + [PageBreak()] + self._doc_control() + self._toc() + [PageBreak()]
        for section in (self._s1_exec, self._s2_scope, self._s3_data, self._s4_findings, self._s5_timeline,
                        self._s6_ueba, self._s7_trust, self._s8_attack, self._s9_ti, self._s10_risk, self._s11_fp,
                        self._s12_remediation, self._s13_appendix, self._s14_limits, self._s15_conclusion):
            s += section()
        s += self._end()
        doc.build(s, canvasmaker=_NumberedCanvas)
        return buf.getvalue()

    # ------------------------------------------------------------ small builders
    def _h1(self, title):
        self.n += 1
        return [CondPageBreak(45 * mm), Paragraph(f"{self.n}. {_esc(title)}", self.st["TGH1"])]

    def _p(self, text, style="TGBody"):
        return Paragraph(_esc(text), self.st[style])

    def _cell(self, text, style="TGCell", limit=CELL_MAX):
        return Paragraph(_esc(text, limit), self.st[style])

    RESULT_SEV = {"success": "critical", "executed": "critical", "allowed": "high", "changed": "high",
                  "error": "medium", "detected": "medium", "blocked": "clean", "failed": "clean", "info": "info"}

    def _act(self, action, result=None, by=None):
        """'Action taken' cell: what the firewall/server/machine did, coloured by outcome for the defender."""
        if not action:
            return self._cell("-")
        col = self.SEV.get(self.RESULT_SEV.get(result or "info", "info"))
        txt = f"<font color='{col.hexval().replace('0x', '#')}'><b>{_esc(action, 160)}</b></font>"
        if by:
            txt += f"<br/><font color='#5a6470'>{_esc(by, 60)}</font>"
        return Paragraph(txt, self.st["TGCell"])

    def _table(self, header, rows, fractions, font_small=False, zebra=True):
        """Table whose columns are fractions of the usable width; wraps cells; repeats header."""
        widths = [self.W * f for f in fractions]
        data = [[Paragraph(_esc(h), self.st["TGCellH"]) for h in header]] if header else []
        for r in rows:
            data.append([c if not isinstance(c, (str, int, float)) else self._cell(c) for c in r])
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0, splitByRow=1)
        style = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cfd8e3")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                 ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), self.PRIMARY))
        if zebra:
            style.append(("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, self.LIGHT]))
        t.setStyle(TableStyle(style))
        return t

    def _kv(self, rows, key_frac=0.28):
        t = Table([[Paragraph(f"<b>{_esc(k)}</b>", ParagraphStyle("k", parent=self.st["TGCell"], textColor=colors.white)),
                    self._cell(v)] for k, v in rows], colWidths=[self.W * key_frac, self.W * (1 - key_frac)])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), self.PRIMARY), ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, self.LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
        return t

    def _bullets(self, items, style="TGBody"):
        items = [i for i in items if i]
        if not items:
            return []
        return [ListFlowable([ListItem(Paragraph(i if isinstance(i, str) and i.startswith("<b>") else _esc(i),
                                                 self.st[style]), leftIndent=8) for i in items],
                             bulletType="bullet", leftIndent=10, bulletFontSize=7)]

    def _chip(self, sev, width=None):
        width = width or 24 * mm
        t = Table([[Paragraph(f"<b>{_esc(sev.upper())}</b>", ParagraphStyle(
            "c", textColor=colors.white, fontSize=7.8, alignment=TA_CENTER, leading=9.5))]], colWidths=[width])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), self.SEV.get(sev, colors.grey)),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        return t

    def _target(self):
        if self.host_mode:
            h = self.r.get("host", {})
            return f"{h.get('hostname', '-')} ({h.get('os', '-')})"
        files = [i["file"] for i in self.r.get("ingestion") or []]
        return self.meta.get("source") or (", ".join(files[:4]) + (f" (+{len(files) - 4} more)" if len(files) > 4 else "")) \
            or "Uploaded logs"

    # ------------------------------------------------------------ drawings
    def _logo(self, height=None):
        height = height or 34 * mm
        path = self.b.get("logo_file")
        if path:
            try:
                img = Image(path)
                ratio = img.imageWidth / float(img.imageHeight or 1)
                h = height
                w = min(h * ratio, self.W * 0.6)
                h = w / ratio
                img.drawWidth, img.drawHeight = w, h
                img.hAlign = "CENTER"
                return img
            except Exception:  # noqa: BLE001 - fall back to the built-in logo
                pass
        d = Drawing(240, 300)
        P, G, O = self.PRIMARY, self.ACCENT, self.ACCENT2
        y = lambda v: 300 - v
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
        d = Drawing(150, 128)
        d.add(Circle(75, 76, 46, fillColor=self.LIGHT, strokeColor=col, strokeWidth=6))
        d.add(String(75, 79, str(score), fontSize=25, fillColor=col, textAnchor="middle", fontName="Helvetica-Bold"))
        d.add(String(75, 63, "/ 100", fontSize=8.5, fillColor=self.INK, textAnchor="middle"))
        d.add(String(75, 6, level.upper(), fontSize=10.5, fillColor=col, textAnchor="middle", fontName="Helvetica-Bold"))
        return d

    def _grade(self):
        g = self.r.get("grade", "-")
        pal = {"A": "#2a9d8f", "B": "#5aa84b", "C": "#e0a800", "D": "#e2571e", "E": "#d1391c", "F": "#b00020"}
        d = Drawing(64, 64)
        d.add(Rect(4, 4, 56, 56, rx=8, ry=8, fillColor=colors.HexColor(pal.get(g, "#5a6470")), strokeColor=None))
        d.add(String(32, 19, g, fontSize=32, fillColor=colors.white, textAnchor="middle", fontName="Helvetica-Bold"))
        return d

    def _bar(self, labels, values, bar_colors=None, height=150):
        width = self.W
        d = Drawing(width, height)
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 32, 34, width - 46, height - 44
        bc.data = [values]
        top = max([1] + values)
        bc.valueAxis.valueMin, bc.valueAxis.valueMax = 0, top
        bc.valueAxis.valueStep = max(1, top // 5)
        bc.valueAxis.labels.fontSize = 7
        bc.categoryAxis.categoryNames = [_clean(x) for x in labels]
        bc.categoryAxis.labels.fontSize = 6.4 if len(labels) > 8 else 8
        if len(labels) > 8:
            bc.categoryAxis.labels.angle = 35
            bc.categoryAxis.labels.boxAnchor = "ne"
        bc.bars.strokeColor = None
        bc.bars.fillColor = self.PRIMARY
        for i, c in enumerate(bar_colors or []):
            bc.bars[(0, i)].fillColor = c
        d.add(bc)
        return d

    # ------------------------------------------------------------ front matter
    def _cover(self):
        b, m, r = self.b, self.meta, self.r
        flow = [Spacer(1, 10 * mm), self._logo(), Spacer(1, 7 * mm),
                Paragraph(_esc(b["brand_name"]), self.st["TGTitle"]),
                Paragraph(_esc(b["brand_tagline"]), ParagraphStyle("cs", alignment=TA_CENTER, textColor=self.ACCENT,
                                                                    fontSize=11.5, leading=14)),
                Spacer(1, 3 * mm), HRFlowable(width="55%", thickness=1.4, color=self.ACCENT), Spacer(1, 9 * mm),
                Paragraph(_esc(self.title), ParagraphStyle("rt", alignment=TA_CENTER, textColor=self.INK, fontSize=17,
                                                           leading=21)), Spacer(1, 8 * mm)]
        incs = r.get("incidents") or []
        rows = [("Target / Source", self._target()), ("Client / Organisation", m.get("client") or "-"),
                ("Analyst", m.get("assessor") or b.get("author_name") or b["brand_name"]), ("Reference", m["ref"]),
                ("Overall Risk", f"{r.get('risk_level', '-').upper()} (score {r.get('risk_score', 0)}/100)"),
                ("Security Grade", r.get("grade", "-"))]
        if not self.host_mode:
            rows.append(("Findings / Incidents", f"{len(self.findings)} findings, {len(incs)} correlated incident(s)"))
        rows += [("Report Date", datetime.now().strftime("%d %B %Y")), ("Classification", b["classification"])]
        flow.append(self._kv(rows))
        flow += [Spacer(1, 9 * mm), Paragraph(f"<b>{_esc(b['author_mark'])}</b>", ParagraphStyle(
            "auth", alignment=TA_CENTER, textColor=self.PRIMARY, fontSize=9.5, leading=12))]
        if b.get("address") or b.get("contact"):
            flow.append(Paragraph(_esc(" · ".join(x for x in (b.get("address"), b.get("contact")) if x)),
                                  ParagraphStyle("addr", alignment=TA_CENTER, fontSize=8, textColor=colors.grey)))
        if b.get("notice"):
            flow += [Spacer(1, 3 * mm), self._p(b["notice"], "TGSmall")]
        return flow

    def _doc_control(self):
        b, m = self.b, self.meta
        rows = [("Document title", f"{b['brand_name']} {self.title}"), ("Document reference", m["ref"]),
                ("Version", b.get("report_version") or "1.0"),
                ("Prepared by", m.get("assessor") or b.get("author_name") or b["brand_name"]),
                ("Client", m.get("client") or "-"), ("Date of report", datetime.now().strftime("%d %B %Y")),
                ("Generated by", "CyberSec AI Agent - offline detection engine" +
                 (f" + local AI model ({m['model']})" if m.get("model") else " (deterministic analysis)")),
                ("Classification", b["classification"]), ("Distribution", "Named recipients only")]
        if b.get("contact"):
            rows.append(("Contact", b["contact"]))
        return [Paragraph("Document Control", self.st["TGH1"]),
                self._table(["Field", "Detail"], rows, [0.3, 0.7]), Spacer(1, 5 * mm),
                Paragraph("Confidentiality & Legal Notice", self.st["TGH2"]),
                self._p("This analysis was performed on log data supplied by, or systems owned by, the client. "
                        "Findings reflect the evidence available at the time of analysis; missing, filtered or "
                        "tampered logs may hide further activity. Automated detections and AI-assisted text must be "
                        "validated by an analyst before disciplinary, legal or operational action.")]

    SECTIONS = ["Executive Summary", "Analysis Scope and Methodology", "Data Sources and Log Processing",
                "Detailed Findings", "Correlated Events and Attack Timeline", "UEBA and Behavioural Analysis",
                "Trusted Network and Asset Context", "MITRE ATT&CK Mapping", "Threat Intelligence Findings",
                "Incident Risk and Severity Assessment", "False-Positive Considerations",
                "Recommended Containment and Remediation", "Evidence and Technical Appendix",
                "Limitations and Missing Telemetry", "Conclusion"]

    def _toc(self):
        return [Spacer(1, 5 * mm), Paragraph("Table of Contents", self.st["TGH1"])] + self._bullets(
            [f"{i}. {t}" for i, t in enumerate(self.SECTIONS, 1)])

    # ------------------------------------------------------------ 1-3
    def _s1_exec(self):
        r = self.r
        counts = r.get("summary", {})
        flow = self._h1("Executive Summary")
        summary = _first_paragraph(self.ai) or self._deterministic_summary()
        flow.append(Paragraph(_inline_md(summary), self.st["TGBody"]))
        flow.append(Spacer(1, 3 * mm))
        rows = [[Paragraph(f"<b>{s.capitalize()}</b>", ParagraphStyle("x", textColor=colors.white, fontSize=8.5)),
                 Paragraph(f"<b>{counts.get(s, 0)}</b>", ParagraphStyle("y", textColor=colors.white, fontSize=8.5,
                                                                        alignment=TA_CENTER))] for s in SEV_ORDER]
        ct = Table(rows, colWidths=[28 * mm, 13 * mm])
        cst = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
               ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
        cst += [("BACKGROUND", (0, i), (-1, i), self.SEV[s]) for i, s in enumerate(SEV_ORDER)]
        ct.setStyle(TableStyle(cst))
        lay = Table([[self._gauge(), self._grade(), ct]], colWidths=[self.W * 0.34, self.W * 0.2, self.W * 0.46])
        lay.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        flow += [lay, Paragraph("Severity Distribution", self.st["TGH2"]),
                 self._bar([s.capitalize() for s in SEV_ORDER], [counts.get(s, 0) for s in SEV_ORDER],
                           [self.SEV[s] for s in SEV_ORDER], height=135)]
        incs = r.get("incidents") or []
        if incs:
            flow.append(Paragraph("Incidents", self.st["TGH2"]))
            flow.append(self._table(["ID", "Status", "Risk", "Actors / hosts", "Attack stages"], [
                [i["id"], i["status"], f"{i['risk']['score']}/100",
                 ", ".join(i["users"][:4] + i["hosts"][:3]) or "-", " > ".join(i["tactics"])] for i in incs],
                [0.1, 0.2, 0.08, 0.27, 0.35]))
        flow.append(Paragraph("Key Risk Themes", self.st["TGH2"]))
        top = [f for f in self.findings if f["severity"] in ("critical", "high")][:7]
        flow += self._bullets([f"<b>{_esc(f['fid'])} {_esc(f['title'], 120)}</b> - "
                               f"{_esc(f.get('impact') or f.get('description', ''), 220)}" for f in top]) or \
            [self._p("No critical or high-risk issues were identified.")]
        return flow

    def _deterministic_summary(self):
        try:
            import investigator
            return investigator.executive_summary(self.r)
        except Exception:  # noqa: BLE001
            return f"{len(self.findings)} findings were identified."

    def _s2_scope(self):
        r = self.r
        flow = self._h1("Analysis Scope and Methodology") + [Paragraph(f"{self.n}.1 Scope", self.st["TGH2"])]
        if self.host_mode:
            h = r.get("host", {})
            flow.append(self._kv([("Hostname", h.get("hostname", "-")), ("Operating system", h.get("os", "-")),
                                  ("Kernel", f"{h.get('kernel', '-')} ({h.get('arch', '')})"),
                                  ("Hardware", f"{h.get('cpus', '-')} CPUs, {h.get('ram_gb', '-')} GB RAM"),
                                  ("Audit privileges", h.get("audited_as", "-")),
                                  ("Logs analysed", ", ".join(r.get("log_sources") or []) or "none readable")]))
        else:
            tr = r.get("time_range") or {}
            flow.append(self._kv([("Sources", self._target()), ("Events analysed", f"{r.get('lines', 0):,}"),
                                  ("Log types", ", ".join(r.get("log_types", []))),
                                  ("Time range (UTC)", f"{tr.get('start') or '-'}  to  {tr.get('end') or '-'}"),
                                  ("Analysis duration", f"{r.get('duration_s', '-')} s")]))
        if self.meta.get("scope_note"):
            flow.append(self._p(self.meta["scope_note"]))
        flow += [Paragraph(f"{self.n}.2 Methodology", self.st["TGH2"]), self._p(
            "The analysis ran fully offline. A deterministic Python engine normalised every record into a common "
            "event model, applied signature, threshold, statistical and behavioural (UEBA) rules, matched offline "
            "threat-intelligence feeds, classified every IP address against the organisation's trusted network and "
            "asset inventory, and correlated related findings into incidents through shared users, hosts and "
            "addresses within time windows. Each conclusion references original records through evidence IDs "
            "(E-xxxx). A locally hosted language model was used only to review these structured results; its text "
            "is checked against the evidence register and never replaces the deterministic findings."),
            self._p("The approach aligns with:")] + self._bullets(STANDARDS)
        flow += [Paragraph(f"{self.n}.3 Scoring Model", self.st["TGH2"]), self._table(["Measure", "Meaning"], [
            ["Severity", "Potential impact of the detected behaviour (Critical / High / Medium / Low / Info), "
                         "indicatively aligned to CVSS v3.1 bands."],
            ["Confidence", "How strongly the evidence supports the detection (0-100%), from the rule's base "
                           "confidence, event volume and corroboration across log sources."],
            ["UEBA score", "How far the involved account deviates from its own baseline and its peers (0-100)."],
            ["Incident risk", "Explainable 0-100 score combining severity, confidence, correlation, attack stage, "
                              "asset criticality, threat intelligence and behaviour. Factors are listed per finding."],
            ["Asset trust", "Classification of involved addresses from the trusted inventory. Context only - it "
                            "never lowers severity or suppresses a finding."]], [0.2, 0.8])]
        return flow

    def _s3_data(self):
        flow = self._h1("Data Sources and Log Processing")
        ing = self.r.get("ingestion") or []
        if not ing:
            return flow + [self._p("Live host audit: data was read directly from the system "
                                   f"({', '.join(self.r.get('log_sources') or []) or 'no log files readable'}).")]
        flow.append(self._table(["File", "Format", "Probable source", "Events", "Parse failures", "Time range (UTC)"], [
            [i["file"], i["format"], ", ".join(i["probable_source"]), f"{i['events']:,}", str(i["parse_failures"]),
             f"{i['time_range']['start'] or '-'} to {i['time_range']['end'] or '-'}"] for i in ing],
            [0.22, 0.08, 0.17, 0.09, 0.1, 0.34]))
        flow.append(Paragraph("Field coverage (% of events with the field)", self.st["TGH2"]))
        fields = ["ts", "src_ip", "dst_ip", "dst_port", "user", "host", "event_id", "action", "process", "command",
                  "domain", "bytes_out"]
        flow.append(self._table(["File"] + fields, [
            [i["file"]] + [f"{i['fields_available'].get(f, 0):g}" if i["fields_available"].get(f) else "-" for f in fields]
            for i in ing], [0.2] + [0.8 / len(fields)] * len(fields)))
        flow.append(Paragraph("Timestamps and time zones", self.st["TGH2"]))
        flow.append(self._table(["File", "Timestamp formats", "Time zones", "Without timestamp"], [
            [i["file"], ", ".join(f"{k} ({v})" for k, v in i["timestamp_formats"].items()) or "-",
             ", ".join(f"{k} ({v})" for k, v in i["timezones"].items()) or "-", str(i["no_timestamp"])] for i in ing],
            [0.24, 0.28, 0.32, 0.16]))
        maps = [(i["file"], i["column_mapping"], i["unmapped_columns"]) for i in ing if i.get("column_mapping")]
        if maps:
            flow.append(Paragraph("Column mapping (structured exports)", self.st["TGH2"]))
            flow.append(self._table(["File", "Mapped columns", "Not mapped"], [
                [f, ", ".join(f"{k}->{v}" for k, v in m.items()), ", ".join(u) or "-"] for f, m, u in maps],
                [0.2, 0.55, 0.25]))
        fails = [(i["file"], s) for i in ing for s in i.get("failure_samples", [])]
        if fails:
            flow.append(Paragraph("Parsing failures (samples)", self.st["TGH2"]))
            flow.append(self._table(["File", "Line", "Problem"], [[f, str(s["line"]), s["error"]] for f, s in fails[:20]],
                                    [0.25, 0.1, 0.65]))
        return flow

    # ------------------------------------------------------------ 4. Detailed findings (A4-safe cards)
    def _s4_findings(self):
        flow = self._h1("Detailed Findings")
        if not self.findings:
            return flow + [self._p("No findings were produced by the automated checks. A manual review is still "
                                   "recommended for areas listed under Limitations.")]
        flow.append(self._table(["ID", "Finding", "Severity", "Conf.", "Risk", "Rule", "Incident"], [
            [f["fid"], f["title"], Paragraph(f"<b>{f['severity'].upper()}</b>", ParagraphStyle(
                "sv", parent=self.st["TGCell"], textColor=self.SEV[f["severity"]])),
             f"{f.get('confidence', '-')}%", str((f.get("risk") or {}).get("score", "-")), f.get("rule_id", f.get("id")),
             f.get("incident", "-")] for f in self.findings],
            [0.08, 0.42, 0.11, 0.08, 0.07, 0.13, 0.11]))
        for f in self.findings:
            flow += self._card(f)
        return flow

    def _card(self, f):
        W = self.W
        head = Table([[Paragraph(f"<b>{_esc(f['fid'])}&nbsp;&nbsp;{_esc(f['title'], 200)}</b>",
                                 ParagraphStyle("ch", parent=self.st["TGH3"], spaceBefore=0, spaceAfter=0)),
                       self._chip(f["severity"])]], colWidths=[W - 27 * mm, 27 * mm])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (0, 0), self.LIGHT),
                                  ("LINEBELOW", (0, 0), (-1, 0), 1, self.SEV.get(f["severity"], colors.grey)),
                                  ("LEFTPADDING", (0, 0), (0, 0), 6), ("TOPPADDING", (0, 0), (-1, -1), 4),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        risk = f.get("risk") or {}
        mitre = ", ".join(f"{t} {rulebook.technique(t)['name']}" for t in f.get("mitre_list") or
                          ([f["mitre"]] if f.get("mitre") not in (None, "-") else []))
        metrics = [("Severity", f["severity"].upper()), ("Confidence", f"{f.get('confidence', '-')}%" +
                                                          (f" ({f['confidence_label']})" if f.get("confidence_label") else "")),
                   ("Risk score", f"{risk.get('score', '-')}/100"), ("UEBA score", str(f.get("ueba_score", "-"))),
                   ("Rule ID", f.get("rule_id", f.get("id"))), ("Detection method", f.get("method", "-")),
                   ("First observed", f.get("first_seen") or "-"), ("Last observed", f.get("last_seen") or "-")]
        grid = []
        for row in (metrics[:4], metrics[4:]):
            grid.append([Paragraph(f"{_esc(k)}<br/><font size='9' color='#16202e'><b>{_esc(v, 60)}</b></font>",
                                   self.st["TGMetricL"]) for k, v in row])
        mt = Table(grid, colWidths=[W / 4] * 4)
        mt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cfd8e3")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
        flow = [CondPageBreak(70 * mm), Spacer(1, 3 * mm), KeepTogether([head, mt])]
        rows = []
        if mitre:
            rows.append(("ATT&CK", mitre))
        if f.get("incident"):
            rows.append(("Incident", f["incident"]))
        assets = sorted(set(f.get("hosts", [])))[:10]
        if assets:
            rows.append(("Affected assets", ", ".join(assets)))
        if f.get("users"):
            rows.append(("Accounts", ", ".join(f["users"][:10])))
        if f.get("ips"):
            rows.append(("IP addresses", ", ".join(f["ips"][:15])))
        acts = f.get("actions_taken") or []
        if acts:
            rows.append(("Action taken", Paragraph("<br/>".join(
                f"<font color='{self.SEV.get(self.RESULT_SEV.get(a['result'], 'info')).hexval().replace('0x', '#')}'>"
                f"<b>{_esc(a['action'], 140)}</b></font>" + (f" x{a['count']}" if a["count"] > 1 else "")
                + f" <font color='#5a6470'>({_esc(a['by'], 60)})</font>" for a in acts), self.st["TGCell"])))
        ctx = f.get("trust_context") or []
        if ctx:
            rows.append(("Trust context", "; ".join(
                f"{c.get('ip') or c.get('host')}: {c['label']}" + (f" ({c['name']})" if c.get("name") else "")
                for c in ctx[:8])))
        if rows:
            flow.append(self._table(None, [[Paragraph(f"<b>{_esc(k)}</b>", self.st["TGCell"]), v] for k, v in rows],
                                    [0.2, 0.8], zebra=True))
        for label, key in (("What was detected", "description"), ("Analysis and interpretation", "impact")):
            if f.get(key):
                flow += [Paragraph(label, self.st["TGH3"]), self._p(f[key])]
        details = {k: v for k, v in (f.get("details") or {}).items() if k not in ("reasons",) and v not in (None, "", [])}
        notes = list(f.get("notes") or [])
        if f.get("also_matched"):
            notes.append("Also matched: " + "; ".join(f["also_matched"]))
        if details or notes:
            flow.append(Paragraph("Detection details", self.st["TGH3"]))
            flow += self._bullets([f"{k.replace('_', ' ')}: {', '.join(map(str, v)) if isinstance(v, list) else v}"
                                   for k, v in list(details.items())[:10]] + notes)
        if (f.get("details") or {}).get("reasons"):
            flow += [Paragraph("Behavioural reasons", self.st["TGH3"])] + self._bullets(f["details"]["reasons"])
        if risk.get("factors"):
            flow.append(Paragraph("Why this risk score", self.st["TGH3"]))
            flow.append(Paragraph(_esc("; ".join(f"{x['factor']} ({'+' if x['points'] >= 0 else ''}{x['points']})"
                                                for x in risk["factors"])), self.st["TGSmall"]))
        if f.get("samples"):
            flow.append(Paragraph("Supporting log evidence", self.st["TGH3"]))
            for s in f["samples"][:4]:
                label = " ".join(x for x in (s.get("evidence") and f"[{s['evidence']}]", s.get("ref") or
                                             (s.get("line") and f"line {s['line']}")) if x)
                flow.append(Paragraph((f"<b>{_esc(label)}</b>  " if label else "") + _esc(s["text"], 700),
                                      self.st["TGCode"]))
        refs = f.get("evidence") or []
        more = len(f.get("evidence_refs") or []) - len(f.get("samples") or [])
        if refs:
            flow.append(Paragraph(f"<b>Correlated evidence ({len(f.get('evidence_refs', []))} event(s)):</b> "
                                  f"{_esc(', '.join(refs[:25]))}" + (" ... (see Section 13)" if more > 0 else ""),
                                  self.st["TGSmall"]))
        for label, key in (("False-positive considerations", "fp"), ("Recommended actions", "recommendation"),
                           ("Evidence limitations", "limitation"), ("Telemetry needed to validate", "telemetry")):
            if f.get(key):
                flow += [Paragraph(label, self.st["TGH3"]), self._p(f[key])]
        flow.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#cfd8e3"), spaceBefore=4))
        return flow

    # ------------------------------------------------------------ 5-9
    def _s5_timeline(self):
        flow = self._h1("Correlated Events and Attack Timeline")
        tl = self.r.get("timeline") or []
        if tl:
            tl = tl[-32:]
            flow += [Paragraph(f"Suspicious events per {self.r.get('timeline_bucket', 'hour')}", self.st["TGH2"]),
                     self._bar([k[5:] if len(k) > 10 else k for k, _ in tl], [v for _, v in tl],
                               [self.ACCENT2] * len(tl), height=150)]
        incs = self.r.get("incidents") or []
        if not incs:
            return flow + [self._p("No findings were correlated into multi-step incidents.")]
        for inc in incs:
            flow += [CondPageBreak(50 * mm), Paragraph(f"{_esc(inc['id'])} - {_esc(inc['status'])} "
                                                       f"(risk {inc['risk']['score']}/100)", self.st["TGH2"]),
                     self._p(inc["title"]),
                     self._kv([("Time window", f"{inc.get('first_seen')} to {inc.get('last_seen')}"),
                               ("Actor accounts", ", ".join(inc["users"]) or "-"),
                               ("Hosts", ", ".join(inc["hosts"]) or "-"), ("Addresses", ", ".join(inc["ips"][:10]) or "-"),
                               ("Accounts targeted", ", ".join(inc.get("targeted_accounts", [])[:15]) or "-"),
                               ("Log sources", ", ".join(inc["source_types"])), ("Findings", ", ".join(inc.get("finding_ids", [])))],
                              key_frac=0.22)]
            if inc.get("attack_path"):
                flow += [Paragraph("Attack path", self.st["TGH3"]),
                         Paragraph(_esc(inc["attack_path"], 900), self.st["TGCode"])]
            steps = inc.get("flow") or []
            if steps:
                flow += [CondPageBreak(45 * mm), Paragraph("Attack flow - what each firewall, server and machine did", self.st["TGH3"])]
                flow.append(self._table(["#", "Time (UTC)", "Flow: source → device → target", "URL / path / command",
                                         "Action taken", "Evidence"], [
                    [str(x["step"]), (x.get("first") or "-") + (f" → {x['last'][11:]}" if x.get("last") and x["last"] != x.get("first") else ""),
                     Paragraph(_esc(" → ".join(v for v in (x.get("from") or ", ".join(x.get("users") or []), x.get("via"), x.get("to")) if v), 300)
                               + (f"<br/><font color='#5a6470'>{_esc(x.get('stage') or 'Alert')}"
                                  + (f" · account {_esc(', '.join(x['users']))}" if x.get("users") and x.get("from") else "") + "</font>"),
                               self.st["TGCell"]),
                     Paragraph(_esc(x.get("object") or "", 300), self.st["TGCodeCell"]),
                     self._act(x.get("action"), x.get("result"), x.get("action_by")),
                     ", ".join(x.get("evidence") or [])[:60]] for x in steps],
                    [0.05, 0.13, 0.27, 0.23, 0.21, 0.11]))
                flow.append(Paragraph("Action colours show the outcome for the defender: red = the attacker's action "
                                      "succeeded or ran, orange = allowed or changed, amber = detected only or server "
                                      "error, green = blocked or failed. \"Exploitation possible\" means the server "
                                      "answered an attack request; it must be confirmed on the host.", self.st["TGSmall"]))
            flow += [CondPageBreak(45 * mm), Paragraph("Chronological sequence", self.st["TGH3"])]
            flow.append(self._table(["Time (UTC)", "Evidence", "Stage", "Event / detection", "Action taken"], [
                [t["ts"] or "-", t["evidence"] or "-", t["tactic"] or "Alert",
                 f"{t['finding']} - {t.get('path') or t['summary']}",
                 self._act(t.get("action"), t.get("result"), t.get("action_by"))] for t in inc.get("timeline", [])[:60]],
                [0.14, 0.09, 0.14, 0.42, 0.21]))
        return flow

    def _s6_ueba(self):
        flow = self._h1("UEBA and Behavioural Analysis")
        ents = (self.r.get("ueba") or {}).get("entities") or []
        if not ents:
            return flow + [self._p("No authentication activity suitable for behavioural analysis was present.")]
        flow.append(self._p("Each account is compared with its own history (earlier events in the data and any "
                            "persisted baseline) and with its peers. Scores are explainable sums of the reasons "
                            "listed; accounts with little history are marked and their scores are less reliable."))
        rows = []
        for u in ents[:30]:
            b = u.get("baseline", {})
            rows.append([u["entity"], str(u["score"]), f"{b.get('logons', 0)} logons / {b.get('history_days', 0)} days"
                         + (" (thin)" if u.get("insufficient_history") else ""),
                         "; ".join(f"{r['text']} [{r.get('ref') or '-'}]" for r in u["reasons"][:5]) or "No anomalies"])
        flow.append(self._table(["Account", "Score", "Baseline", "Reasons (evidence reference)"], rows,
                                [0.14, 0.07, 0.17, 0.62]))
        return flow

    def _s7_trust(self):
        flow = self._h1("Trusted Network and Asset Context")
        t = self.r.get("trust") or {}
        flow.append(self._p("Every IP address was classified against the organisation's configured networks, ISP "
                            "addresses and assets using CIDR membership with explicit precedence: suspicious "
                            "indicators first, then exact assets, then the most specific configured range, then "
                            "private / public. Trusted status is analytical context only: trusted, internal and ISP "
                            "addresses can be compromised, spoofed or reassigned, so they never suppress a detection "
                            "or lower its severity."))
        if not t.get("configured"):
            flow.append(self._p("No trusted networks or assets were configured for this analysis, so addresses are "
                                "classified only as private or public."))
        else:
            flow.append(Paragraph("Configured inventory", self.st["TGH2"]))
            flow.append(Paragraph(_esc(t.get("summary", "")).replace("\n", "<br/>"), self.st["TGCell"]))
        rows = []
        for f in self.findings:
            for c in (f.get("trust_context") or [])[:4]:
                rows.append([f["fid"], c.get("ip") or c.get("host"), c["label"], c.get("name") or "-",
                             f.get("severity", "").upper()])
        if rows:
            flow.append(Paragraph("Addresses involved in findings", self.st["TGH2"]))
            flow.append(self._table(["Finding", "Address / host", "Classification", "Asset", "Severity"], rows[:120],
                                    [0.1, 0.2, 0.3, 0.28, 0.12]))
        return flow

    def _s8_attack(self):
        flow = self._h1("MITRE ATT&CK Mapping")
        amap = self.r.get("attack_mapping")
        if amap is None:
            agg = {}
            for f in self.findings:
                for tid in f.get("mitre_list") or ([f["mitre"]] if f.get("mitre") not in (None, "-") else []):
                    m = rulebook.technique(tid)
                    a = agg.setdefault(tid, dict(m, technique=tid, findings=[], events=0))
                    a["findings"].append(f["fid"])
                    a["events"] += f.get("count", 1)
            amap = list(agg.values())
        if not amap:
            return flow + [self._p("No findings were mapped to ATT&CK techniques.")]
        flow.append(self._table(["Tactic", "Technique", "Name", "Findings", "Events"], [
            [a.get("tactic") or "-", a["technique"], a.get("name") or knowledge.MITRE_NAMES.get(a["technique"], ""),
             ", ".join(map(str, a["findings"][:12])), str(a["events"])] for a in amap],
            [0.2, 0.12, 0.3, 0.28, 0.1]))
        return flow

    def _s9_ti(self):
        flow = self._h1("Threat Intelligence Findings")
        ti = self.r.get("ti") or {}
        flow.append(self._p(f"Offline indicator feeds loaded: {ti.get('feeds_loaded', 0)} indicators. Matching covered "
                            "source/destination IPs, VPN-assigned IPs, queried domains (including parent domains), "
                            "URLs and file hashes."))
        tif = [f for f in self.findings if str(f.get("rule_id", "")).startswith("TG-TI")]
        if tif:
            flow.append(self._table(["Finding", "Indicator", "Feed / source", "Description", "Events"], [
                [f["fid"], (f.get("details") or {}).get("indicator", "-"), (f.get("details") or {}).get("feed") or
                 (f.get("details") or {}).get("reason") or "-", (f.get("details") or {}).get("description") or f["title"],
                 str(f["count"])] for f in tif], [0.1, 0.24, 0.18, 0.38, 0.1]))
        else:
            flow.append(self._p("No activity matched the loaded indicator feeds."))
        iocs = self.r.get("iocs") or {}
        rows = [[k, v] for k in ("ips", "domains", "urls", "files", "hashes") for v in (iocs.get(k) or [])[:30]]
        if rows:
            flow.append(Paragraph("Indicators of compromise extracted from this analysis", self.st["TGH2"]))
            flow.append(self._table(["Type", "Indicator"], [[k, Paragraph(_esc(v), self.st["TGCodeCell"])]
                                                            for k, v in rows[:90]], [0.14, 0.86]))
        return flow

    # ------------------------------------------------------------ 10-15
    def _s10_risk(self):
        flow = self._h1("Incident Risk and Severity Assessment")
        flow.append(self._p("Severity, confidence, UEBA score, incident risk and asset trust are kept separate. Risk "
                            "is the sum of the factors shown; trusted-asset status never reduces it, and contextual "
                            "adjustments (for example an approved scanner) are listed explicitly."))
        for inc in self.r.get("incidents") or []:
            flow.append(Paragraph(f"{_esc(inc['id'])}: risk {inc['risk']['score']}/100, confidence "
                                  f"{inc.get('confidence', '-')}%", self.st["TGH3"]))
            flow += self._bullets([f"{x['factor']} ({'+' if x['points'] >= 0 else ''}{x['points']})"
                                   for x in inc["risk"]["factors"]])
        rows = [[f["fid"], f["title"], f["severity"].upper(), f"{f.get('confidence', '-')}%", str(f.get("ueba_score", "-")),
                 str((f.get("risk") or {}).get("score", "-")),
                 "; ".join(f"{x['factor']} ({'+' if x['points'] >= 0 else ''}{x['points']})"
                           for x in (f.get("risk") or {}).get("factors", [])[1:5])] for f in self.findings[:40]]
        flow.append(self._table(["ID", "Finding", "Severity", "Conf.", "UEBA", "Risk", "Main risk factors"], rows,
                                [0.07, 0.27, 0.09, 0.07, 0.07, 0.07, 0.36]))
        return flow

    def _s11_fp(self):
        flow = self._h1("False-Positive Considerations")
        rows = [[f["fid"], f["title"], f.get("fp") or "-", _rule_out(f)] for f in self.findings if f.get("fp")]
        if not rows:
            return flow + [self._p("No false-positive guidance is recorded for these findings.")]
        flow.append(self._table(["ID", "Finding", "Possible benign explanation", "How to rule it out"], rows[:40],
                                [0.07, 0.27, 0.33, 0.33]))
        return flow

    def _s12_remediation(self):
        flow = self._h1("Recommended Containment and Remediation")
        flow.append(self._p("All actions below are recommendations. The platform does not block addresses, disable "
                            "accounts or change any system; operational actions require explicit authorisation."))
        for inc in self.r.get("incidents") or []:
            flow.append(Paragraph(f"{_esc(inc['id'])} response plan", self.st["TGH2"]))
            rows = [[a["phase"], a["action"], "Yes" if a.get("requires_authorisation") else "No",
                     ", ".join(a.get("evidence", [])[:6]) or "-"] for a in inc.get("actions", [])]
            rows = [[c["phase"], c["step"], "No", ", ".join(c.get("evidence", [])[:6]) or "-"]
                    for c in inc.get("checklist", [])] + rows
            flow.append(self._table(["Phase", "Action / checklist item", "Needs authorisation", "Evidence"], rows,
                                    [0.14, 0.56, 0.12, 0.18]))
        flow.append(Paragraph("Remediation roadmap by severity", self.st["TGH2"]))
        for phase, sevs in (("Immediate (0-24 hours)", ("critical",)), ("Short term (1-7 days)", ("high",)),
                            ("Medium term (1-4 weeks)", ("medium",)), ("Hardening backlog", ("low", "info"))):
            items = [x for x in self.findings if x["severity"] in sevs]
            if items:
                flow += [Paragraph(phase, self.st["TGH3"])] + self._bullets(
                    [f"<b>{_esc(x['fid'])} {_esc(x['title'], 100)}</b>: {_esc(x.get('recommendation') or 'Review and verify.', 400)}"
                     for x in items[:15]])
        return flow

    def _s13_appendix(self):
        flow = self._h1("Evidence and Technical Appendix")
        reg = self.r.get("evidence") or []
        if reg:
            flow.append(Paragraph("Evidence register", self.st["TGH2"]))
            flow.append(self._p("Original records referenced by findings and timelines (file:line). Raw text is "
                                "shortened; the original files are the authoritative source."))
            flow.append(self._table(["ID", "Time (UTC)", "Reference", "Summary", "Action taken"], [
                [e["id"], e["ts"] or "-", Paragraph(_esc(e["ref"]), self.st["TGCodeCell"]), e.get("path") or e["summary"],
                 self._act(e.get("action"), e.get("result"), e.get("action_by"))]
                for e in reg[:400]], [0.08, 0.14, 0.2, 0.36, 0.22]))
            flow.append(Paragraph("Raw record excerpts (first 40)", self.st["TGH2"]))
            for e in reg[:40]:
                flow.append(Paragraph(f"<b>{_esc(e['id'])} {_esc(e['ref'])}</b>  {_esc(e['raw'], 600)}", self.st["TGCode"]))
        try:
            import investigator
            inv = investigator.investigate(self.r) if not self.host_mode else {"incidents": []}
        except Exception:  # noqa: BLE001
            inv = {"incidents": []}
        for i in inv["incidents"][:3]:
            if i.get("queries"):
                flow.append(Paragraph(f"Suggested read-only queries - {i['id']}", self.st["TGH2"]))
                for q in i["queries"]:
                    flow.append(Paragraph(f"<b>{_esc(q['purpose'])}</b>", self.st["TGCell"]))
                    for k in ("splunk", "kql", "grep"):
                        if q.get(k):
                            flow.append(Paragraph(f"{k.upper()}: {_esc(q[k], 900)}", self.st["TGCode"]))
        if self.ai.strip():
            flow += [Paragraph("AI investigation (local model, full text)", self.st["TGH2"]),
                     self._p("Generated by a locally hosted language model from the structured findings. Statements "
                             "are only as reliable as the evidence IDs they cite.", "TGSmall")]
            flow += _markdown_flow(self.ai, self.st)
        return flow

    def _s14_limits(self):
        flow = self._h1("Limitations and Missing Telemetry")
        lim = self.r.get("limitations")
        if lim is None:
            lim = [{"area": "Scope", "detail": "Live host audit of one system.", "impact": "Other systems not assessed."}]
        flow.append(self._table(["Area", "Detail", "Impact"], [[l["area"], l["detail"], l["impact"]] for l in lim],
                                [0.18, 0.46, 0.36]))
        cov = self.r.get("coverage")
        if cov:
            flow.append(Paragraph("Telemetry coverage", self.st["TGH2"]))
            flow.append(self._table(["Area", "Events", "Available"], [[c["area"], f"{c['events']:,}",
                                                                      "Yes" if c["available"] else "No"] for c in cov],
                                    [0.5, 0.25, 0.25]))
        return flow

    def _s15_conclusion(self):
        flow = self._h1("Conclusion")
        incs = self.r.get("incidents") or []
        if incs:
            i = incs[0]
            text = (f"The evidence supports {len(incs)} correlated incident(s). The most serious, {i['id']}, is "
                    f"assessed as '{i['status'].lower()}' with a risk of {i['risk']['score']}/100 across "
                    f"{len(i['tactics'])} ATT&CK tactics ({', '.join(i['tactics'][:6])}). Containment and credential "
                    f"actions in Section 12 should be authorised and started without delay, while the evidence gaps "
                    f"in Section 14 are closed to confirm scope and impact.")
        elif self.findings:
            text = (f"{len(self.findings)} individual findings were identified without a multi-step attack chain. "
                    "Review the high-severity items first and apply the hardening recommendations.")
        else:
            text = "No suspicious activity was detected in the analysed data within the limits described above."
        flow.append(self._p(text))
        flow.append(self._p("This assessment is based solely on the supplied logs. Conclusions marked suspected or "
                            "probable require validation by an analyst; absence of evidence is not evidence of absence."))
        return flow

    def _end(self):
        b = self.b
        return [Spacer(1, 6 * mm), HRFlowable(width="100%", thickness=0.6, color=self.ACCENT),
                Paragraph(f"<b>{_esc(b['author_mark'])}</b>", ParagraphStyle(
                    "end", alignment=TA_CENTER, textColor=self.PRIMARY, fontSize=9.5)),
                Paragraph(_esc(f"- End of Report · {b['brand_name']} -"), ParagraphStyle(
                    "e2", alignment=TA_CENTER, textColor=colors.grey, fontSize=8))]


def _rule_out(f):
    try:
        import investigator
        return investigator._rule_out(f)
    except Exception:  # noqa: BLE001
        return "Validate with the system owner."


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
            return s[:1200]
    return ""


def _markdown_flow(md, st):
    flow, code, bullets = [], None, []

    def flush():
        if bullets:
            flow.append(ListFlowable([ListItem(Paragraph(_inline_md(b), st["TGBody"]), leftIndent=8) for b in bullets],
                                     bulletType="bullet", leftIndent=10, bulletFontSize=7))
            bullets.clear()

    for line in md.splitlines():
        if line.strip().startswith("```"):
            if code is None:
                flush()
                code = []
            else:
                if code:
                    flow.append(Paragraph("<br/>".join(_esc(c) for c in code), st["TGCode"]))
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        s = line.strip()
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            flush()
            flow.append(Paragraph(_inline_md(m.group(2).strip("# ")), st["TGH3"]))
        elif re.match(r"^([-*]|\d+[.)])\s+", s):
            bullets.append(re.sub(r"^([-*]|\d+[.)])\s+", "", s))
        elif s and s != "---":
            flush()
            flow.append(Paragraph(_inline_md(s), st["TGBody"]))
    flush()
    if code:
        flow.append(Paragraph("<br/>".join(_esc(c) for c in code), st["TGCode"]))
    return flow
