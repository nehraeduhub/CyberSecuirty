"""Branding & Report Configuration: names, colours, report labels and a custom logo.

Stored in config/branding.json; logos in assets/branding/. No code change or rebuild is
needed to rebrand. Logos are validated by content (magic bytes + header dimensions), never
by file name, and are stored under generated names, so an upload can't overwrite an
existing asset or escape the branding folder.
"""
import base64
import hashlib
import re
import struct
import time
from pathlib import Path

import config_store

FILE = "branding.json"
LOGO_DIR = config_store.ROOT / "assets" / "branding"
MAX_LOGO_BYTES = 2 * 1024 * 1024
MIN_DIM, MAX_DIM = 16, 4096
DEFAULTS = {
    "application_name": "CyberSec AI Agent",
    "organisation_name": "Tech Guardians",
    "logo_path": "",                      # empty = built-in Tech Guardians shield
    "report_title": "Security Incident Analysis Report",
    "report_subtitle": "Security Operations & Incident Response",
    "organisation_address": "",
    "analyst_name": "",
    "classification": "CONFIDENTIAL",
    "primary_colour": "#123E6B",
    "secondary_colour": "#EEF3F9",
    "accent_colour": "#1E9E4F",
    "highlight_colour": "#F59E1E",
    "header_text": "",
    "footer_text": "Designed & Developed by Rajesh Nehra · Master in Cyber Security",
    "report_version": "1.0",
    "contact": "",
    "confidentiality_notice": ("This document is confidential and intended solely for the named recipient. It "
                               "describes security events identified on systems the organisation owns or is "
                               "authorised to assess, and must be handled on a strict need-to-know basis."),
    "filename_prefix": "security-report",
}
COLOUR_KEYS = ("primary_colour", "secondary_colour", "accent_colour", "highlight_colour")
LONG_KEYS = ("confidentiality_notice", "organisation_address")


def load():
    raw, err = config_store.load_json(config_store.live_path(FILE), {})
    b = dict(DEFAULTS)
    if isinstance(raw, dict):
        try:
            b.update(validate(raw, partial=True))
        except ValueError as e:
            err = f"{FILE}: {e}"
    b["_error"] = err
    b["logo_url"] = "/branding/logo" + (f"?v={Path(b['logo_path']).stem}" if b["logo_path"] else "")
    return b


def validate(data, partial=False):
    out = {}
    for k, v in data.items():
        if k not in DEFAULTS:
            continue
        v = "" if v is None else str(v).strip()
        limit = 1500 if k in LONG_KEYS else 200
        if len(v) > limit:
            raise ValueError(f"{k} is too long (max {limit} characters)")
        if k in COLOUR_KEYS and not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            raise ValueError(f"{k} must be a colour like #0A1931")
        if k == "filename_prefix" and not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", v):
            raise ValueError("filename_prefix may only contain letters, digits, '-' and '_'")
        if k == "logo_path" and v and resolve_logo(v) is None:
            raise ValueError("logo_path must be a logo uploaded through Branding settings")
        out[k] = v
    if not partial:
        for k in ("application_name", "organisation_name", "report_title"):
            if not out.get(k, DEFAULTS[k]):
                raise ValueError(f"{k} is required")
    return out


def save(changes, actor, confirm_replace=False):
    """Validate and persist. Replacing an existing custom logo needs confirm_replace=True."""
    current = load()
    clean = validate(changes)
    new_logo = clean.get("logo_path")
    if new_logo is not None and current["logo_path"] and new_logo != current["logo_path"] and not confirm_replace:
        raise PermissionError("a custom logo is already set; confirm to replace it")
    stored = {k: current[k] for k in DEFAULTS}
    stored.update(clean)
    before = {k: current[k] for k in clean if current.get(k) != clean[k]}
    after = {k: clean[k] for k in before}
    config_store.save_json(config_store.live_path(FILE), stored)
    config_store.audit(actor, "branding", "update", FILE, before, after)
    return load()


# ------------------------------------------------------------------ logo handling

def _image_info(data):
    """(kind, width, height) from the file header, or raise ValueError. PNG and JPEG only."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpeg", w, h
            i += 2 + seg_len
        raise ValueError("JPEG file has no image size information")
    if data.lstrip()[:5] in (b"<?xml", b"<svg ") or b"<svg" in data[:512]:
        raise ValueError("SVG logos are not accepted (they can contain scripts); export the logo as PNG")
    raise ValueError("only PNG and JPEG logos are supported")


def check_logo(data):
    if not data:
        raise ValueError("empty file")
    if len(data) > MAX_LOGO_BYTES:
        raise ValueError(f"logo is larger than {MAX_LOGO_BYTES // 1024 // 1024} MB")
    kind, w, h = _image_info(data)
    if not (MIN_DIM <= w <= MAX_DIM and MIN_DIM <= h <= MAX_DIM):
        raise ValueError(f"logo must be between {MIN_DIM} and {MAX_DIM} pixels on each side (got {w}x{h})")
    try:  # full decode check when Pillow is available (it ships with reportlab)
        from PIL import Image
        import io
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001 - any decoder error means a broken or disguised file
        raise ValueError(f"logo could not be decoded as an image ({e.__class__.__name__})")
    return kind, w, h


def store_logo(b64data, actor):
    """Save an uploaded logo under a new unique name. Nothing existing is overwritten."""
    try:
        data = base64.b64decode(b64data, validate=True)
    except (ValueError, TypeError):
        raise ValueError("logo upload is not valid base64")
    kind, w, h = check_logo(data)
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"logo-{time.strftime('%Y%m%d-%H%M%S')}-{hashlib.sha256(data).hexdigest()[:10]}.{'png' if kind == 'png' else 'jpg'}"
    path = LOGO_DIR / name
    if not path.exists():
        path.write_bytes(data)
    config_store.audit(actor, "branding", "logo uploaded (not yet applied)", name, None,
                       {"bytes": len(data), "size": f"{w}x{h}", "type": kind})
    return {"logo_path": str(path.relative_to(config_store.ROOT)), "width": w, "height": h, "type": kind}


def resolve_logo(logo_path):
    """Absolute path of a stored logo, or None if missing or outside assets/branding."""
    if not logo_path:
        return None
    p = (config_store.ROOT / logo_path).resolve()
    try:
        p.relative_to(LOGO_DIR.resolve())
    except ValueError:
        return None
    return p if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg") else None


def logo_bytes(b):
    p = resolve_logo(b.get("logo_path"))
    if not p:
        return None, None
    return p.read_bytes(), "image/png" if p.suffix.lower() == ".png" else "image/jpeg"


def report_brand(b):
    """Map branding to the keys the PDF report uses."""
    return {
        "brand_name": b["organisation_name"], "brand_tagline": b["report_subtitle"],
        "report_title": b["report_title"], "application_name": b["application_name"],
        "author_mark": b["footer_text"], "header_text": b["header_text"], "author_name": b["analyst_name"],
        "classification": b["classification"], "color_primary": b["primary_colour"],
        "color_light": b["secondary_colour"], "color_accent": b["accent_colour"],
        "color_accent2": b["highlight_colour"], "report_version": b["report_version"],
        "contact": b["contact"], "address": b["organisation_address"],
        "notice": b["confidentiality_notice"], "logo_file": str(resolve_logo(b["logo_path"]) or ""),
        "doc_prefix": "TG-IR",
    }
