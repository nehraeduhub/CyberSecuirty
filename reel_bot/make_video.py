"""Render slides with Pillow, add Hindi voiceover (gTTS) and join with ffmpeg."""
import os
import subprocess

from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont

import config as C

FONT_BOLD = os.getenv("REEL_FONT_BOLD", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT_REG = os.getenv("REEL_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _asset(name):
    try:
        return Image.open(os.path.join(ASSETS, name)).convert("RGBA")
    except OSError:
        return None


def _wrap(draw, text, font, max_w):
    lines = []
    for para in text.replace(" | ", "\n• ").split("\n"):
        words, cur = para.split(), ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textlength(test, font=font) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _strip_emoji(text):
    # DejaVu fonts cannot draw emoji; keep text readable
    return "".join(ch for ch in text if ord(ch) < 0x2190 or ch == "•").strip()


def _paste_fit(img, logo, box_w, box_h, cx, top, alpha=1.0):
    scale = min(box_w / logo.width, box_h / logo.height)
    lg = logo.resize((int(logo.width * scale), int(logo.height * scale)), Image.LANCZOS)
    if alpha < 1:
        a = lg.getchannel("A").point(lambda v: int(v * alpha))
        lg.putalpha(a)
    img.alpha_composite(lg, (int(cx - lg.width / 2), int(top)))
    return lg.height


def render_slide(text, idx, total, path):
    text = _strip_emoji(text)
    W, H = C.WIDTH, C.HEIGHT
    img = Image.new("RGBA", (W, H), C.CREAM + (255,))
    d = ImageDraw.Draw(img)

    # 1. header banner (Cyber Safe Jhunjhunu | RJ Nehra | Tech Guardians)
    banner = _asset("header_banner.png")
    head_h = _paste_fit(img, banner, W - 20, 400, W / 2, 30) if banner else 0
    if not banner:
        d.text((W / 2, 110), C.BRAND_TOP, font=_font(FONT_BOLD, 64), fill=C.MAROON, anchor="mm")
        head_h = 160
    y0 = 30 + head_h + 15
    d.rectangle([0, y0, W, y0 + 10], fill=C.ORANGE)
    d.rectangle([0, y0 + 10, W, y0 + 20], fill=C.GREEN)

    # 2. progress dots
    for i in range(total):
        x = W / 2 + (i - (total - 1) / 2) * 50
        d.ellipse([x - 12, y0 + 50, x + 12, y0 + 74], fill=C.MAROON if i <= idx else (210, 200, 185))

    # 3. main card with faint shield watermark
    card = [50, y0 + 110, W - 50, H - 450]
    d.rounded_rectangle(card, 40, fill=(255, 255, 255), outline=C.MAROON, width=6)
    shield = _asset("tg_shield.png")
    if shield:
        ch = card[3] - card[1]
        _paste_fit(img, shield, 600, ch * 0.7, W / 2, card[1] + ch * 0.15, alpha=0.07)
        d = ImageDraw.Draw(img)

    box_w, box_top, box_bot = card[2] - card[0] - 90, card[1] + 50, card[3] - 50
    size = 84
    while size > 40:
        f = _font(FONT_BOLD, size)
        lines = _wrap(d, text, f, box_w)
        lh = int(size * 1.35)
        if lh * len(lines) <= box_bot - box_top:
            break
        size -= 4
    y = box_top + ((box_bot - box_top) - lh * len(lines)) / 2
    head = text.split("\n")[0]
    n_head = len(_wrap(d, head, f, box_w)) if head.endswith(":") else 0
    for i, line in enumerate(lines):
        d.text((W / 2, y + lh / 2), line, font=f, anchor="mm",
               fill=C.ORANGE if i < n_head else (C.MAROON if idx == 0 else C.DARK))
        y += lh

    # 4. helpline
    d.rounded_rectangle([60, H - 410, W - 60, H - 305], 30, fill=C.RED)
    d.text((W / 2, H - 357), "HELPLINE 1930 | cybercrime.gov.in",
           font=_font(FONT_BOLD, 44), fill=(255, 255, 255), anchor="mm")

    # 5. footer: TG shield + Tech Guardians text
    if shield:
        _paste_fit(img, shield, 150, 190, 150, H - 270)
        d = ImageDraw.Draw(img)
    tx = 260
    d.text((tx, H - 245), C.BRAND_BOTTOM_1.upper(), font=_font(FONT_BOLD, 66), fill=C.NAVY)
    d.text((tx, H - 165), "CYBER CRIME AWARENESS", font=_font(FONT_BOLD, 40), fill=C.GREEN)
    d.text((tx, H - 110), C.BRAND_BOTTOM_2, font=_font(FONT_REG, 34), fill=(110, 110, 120))
    img.convert("RGB").save(path)


def _duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", path])
    return float(out.strip())


def build_reel(script, out_path, work_dir):
    os.makedirs(work_dir, exist_ok=True)
    slides = script["slides"]
    parts = []
    for i, s in enumerate(slides):
        img = os.path.join(work_dir, f"slide{i}.png")
        mp3 = os.path.join(work_dir, f"voice{i}.mp3")
        mp4 = os.path.join(work_dir, f"part{i}.mp4")
        render_slide(s["screen_text"], i, len(slides), img)
        try:
            gTTS(s["voiceover_hindi"], lang="hi").save(mp3)
        except Exception as e:  # keep going with silent audio if TTS is unreachable
            print("TTS failed, using silent audio:", e)
            secs = max(3, len(s["voiceover_hindi"]) / 14)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            "anullsrc=r=44100:cl=mono", "-t", f"{secs:.1f}", mp3], check=True)
        dur = _duration(mp3) + 0.6
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img, "-i", mp3,
            "-filter_complex",
            f"[0:v]scale={C.WIDTH}:{C.HEIGHT},fps={C.FPS},format=yuv420p,"
            f"fade=t=in:st=0:d=0.3[v];[1:a]apad[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-ar", "44100", mp4,
        ], check=True)
        parts.append(mp4)

    lst = os.path.join(work_dir, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", "-movflags", "+faststart", out_path], check=True)
    return out_path
