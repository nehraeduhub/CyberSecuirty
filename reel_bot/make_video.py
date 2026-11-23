"""Render slides with Pillow, add Hindi voiceover (gTTS) and join with ffmpeg."""
import os
import subprocess
import textwrap

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


def _background():
    img = Image.new("RGB", (C.WIDTH, C.HEIGHT))
    d = ImageDraw.Draw(img)
    for y in range(C.HEIGHT):
        t = y / C.HEIGHT
        col = tuple(int(C.BG_TOP[i] * (1 - t) + C.BG_BOTTOM[i] * t) for i in range(3))
        d.line([(0, y), (C.WIDTH, y)], fill=col)
    return img


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


def render_slide(text, idx, total, path):
    text = _strip_emoji(text)
    img = _background()
    d = ImageDraw.Draw(img)
    W = C.WIDTH
    # top brand bar
    d.rectangle([0, 0, W, 170], fill=C.ACCENT)
    f_top = _font(FONT_BOLD, 62)
    d.text((W / 2, 85), C.BRAND_TOP,
           font=f_top, fill=(10, 14, 35), anchor="mm")
    # progress dots
    for i in range(total):
        x = W / 2 + (i - (total - 1) / 2) * 50
        d.ellipse([x - 12, 210, x + 12, 234], fill=C.ACCENT if i <= idx else (90, 90, 110))

    # main text (auto-shrink to fit)
    box_w, box_top, box_bot = W - 140, 300, C.HEIGHT - 420
    size = 86
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
        first = i < n_head
        d.text((W / 2, y + lh / 2), line, font=f, anchor="mm",
               fill=C.ACCENT if first else C.TEXT, stroke_width=3, stroke_fill=(0, 0, 0))
        y += lh

    # helpline + footer
    f_help = _font(FONT_BOLD, 40)
    d.rounded_rectangle([60, C.HEIGHT - 390, W - 60, C.HEIGHT - 290], 25, fill=(200, 0, 30))
    d.text((W / 2, C.HEIGHT - 340), "HELPLINE 1930 | cybercrime.gov.in",
           font=f_help, fill=C.TEXT, anchor="mm")
    d.text((W / 2, C.HEIGHT - 210), C.BRAND_BOTTOM_1, font=_font(FONT_BOLD, 58),
           fill=C.ACCENT, anchor="mm")
    d.text((W / 2, C.HEIGHT - 140), C.BRAND_BOTTOM_2, font=_font(FONT_REG, 38),
           fill=C.TEXT, anchor="mm")
    img.save(path)


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
            f"[0:v]scale={C.WIDTH}:{C.HEIGHT},zoompan=z='min(zoom+0.0006,1.06)':d={int(dur*C.FPS)}"
            f":s={C.WIDTH}x{C.HEIGHT}:fps={C.FPS},format=yuv420p[v];[1:a]apad[a]",
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
