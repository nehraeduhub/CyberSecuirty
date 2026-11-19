"""Studio presenter picture from a cut-out photo of the owner: brand-dark studio backdrop with soft light and the
Tech Guardians logo on the wall, the owner from the waist up behind a desk with a laptop and a microphone, so it reads
as "recording the script at a desk". Output 1080x1350 (4:5).
Usage: python3 -I tools/studio_portrait.py <cutout.png (RGBA)> <logo.png> <out.png>"""
import random, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

cut, logo, out = sys.argv[1:4]
W, H = 1080, 1350
# backdrop: navy radial gradient, warm key light top-left, cool rim right
y, x = np.mgrid[0:H, 0:W]
r = np.sqrt(((x - W * .55) / W) ** 2 + ((y - H * .38) / H) ** 2)
base = np.clip(1 - r * 1.35, 0, 1)[..., None]
bg = (np.array([5, 14, 30]) + base * np.array([22, 52, 96])).astype(np.float32)
warm = np.exp(-(((x - W * .12) / (W * .35)) ** 2 + ((y - H * .22) / (H * .3)) ** 2))[..., None]
bg += warm * np.array([70, 38, 10])
img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert('RGBA')
# bokeh lights on the back wall
rnd = random.Random(7); bok = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(bok)
for _ in range(26):
    cx, cy, rr = rnd.randint(0, W), rnd.randint(40, 700), rnd.randint(14, 42)
    col = rnd.choice([(255, 153, 51), (56, 189, 248), (255, 255, 255)])
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=col + (rnd.randint(25, 60),))
img = Image.alpha_composite(img, bok.filter(ImageFilter.GaussianBlur(10)))
# logo on the wall, behind the presenter, softly lit and slightly out of focus
lg = Image.open(logo).convert('RGBA')
a = np.array(lg); white = (a[..., :3].min(axis=2) > 190)          # the logo file sits on a white card: drop it
a[..., 3] = np.where(white, 0, a[..., 3]); lg = Image.fromarray(a); lg = lg.crop(lg.getbbox())
lg = lg.resize((200, int(lg.height * 200 / lg.width)), Image.LANCZOS)
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0)); glow.paste(lg, (800, 150), lg)
img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(28)))
lg2 = lg.copy(); lg2.putalpha(lg2.getchannel('A').point(lambda a: a * .55))
wall = Image.new('RGBA', (W, H), (0, 0, 0, 0)); wall.paste(lg2, (800, 150), lg2)
img = Image.alpha_composite(img, wall.filter(ImageFilter.GaussianBlur(2.5)))
# presenter: head-to-waist, light grade to sit in the studio light
p = Image.open(cut).convert('RGBA'); p = p.crop(p.getbbox())
p.putalpha(p.getchannel('A').filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(1.5)))   # pull the edge in: no light fringe
s = 900 / 1014; p = p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS)
rgb = ImageEnhance.Contrast(ImageEnhance.Brightness(p.convert('RGB')).enhance(.93)).enhance(1.06)
rgb = Image.merge('RGB', [c.point(f) for c, f in zip(rgb.split(), (lambda v: min(255, int(v * 1.03)), lambda v: v, lambda v: int(v * .96)))])
p = Image.merge('RGBA', (*rgb.split(), p.getchannel('A')))
px, py = (W - p.width) // 2 + 10, 150
rim = Image.new('RGBA', (W, H), (0, 0, 0, 0)); rim.paste(Image.new('RGBA', p.size, (120, 190, 255, 55)), (px + 6, py), p)
img = Image.alpha_composite(img, rim.filter(ImageFilter.GaussianBlur(16)))
layer = Image.new('RGBA', (W, H), (0, 0, 0, 0)); layer.paste(p, (px, py), p); img = Image.alpha_composite(img, layer)
# desk (covers below the waist) with a soft shadow line
top = 1035; desk = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(desk)
d.polygon([(-40, top), (W + 40, top), (W + 160, H), (-160, H)], fill=(24, 30, 42, 255))
d.line([(-40, top), (W + 40, top)], fill=(70, 84, 110, 255), width=5)
for i in range(18): d.line([(-160, top + 18 + i * 17), (W + 160, top + 18 + i * 17)], fill=(30, 37, 51, 255), width=1)
sh = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(sh).rectangle((0, top - 30, W, top + 4), fill=(0, 0, 0, 120))
img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(14))); img = Image.alpha_composite(img, desk)
d = ImageDraw.Draw(img)
# laptop seen from behind, right side, with the logo glowing on the lid
lx0, ly0, lx1, ly1 = 700, 860, 1040, 1060
d.rounded_rectangle((lx0, ly0, lx1, ly1), 18, fill=(52, 58, 70, 255), outline=(92, 100, 118, 255), width=3)
d.polygon([(lx0 - 30, ly1), (lx1 + 30, ly1), (lx1 + 10, ly1 + 22), (lx0 - 10, ly1 + 22)], fill=(70, 78, 94, 255))
small = lg.resize((80, int(lg.height * 90 / lg.width))); img.alpha_composite(small, ((lx0 + lx1 - 80) // 2, (ly0 + ly1 - small.height) // 2))
# microphone on a short desk stand, left side
d = ImageDraw.Draw(img); mx = 215
d.rectangle((mx - 6, 980, mx + 6, 1080), fill=(40, 44, 54, 255))
d.ellipse((mx - 70, 1066, mx + 70, 1100), fill=(34, 38, 48, 255))
d.rounded_rectangle((mx - 46, 820, mx + 46, 990), 46, fill=(30, 33, 41, 255), outline=(110, 118, 136, 255), width=4)
for yy in range(842, 975, 14): d.line([(mx - 32, yy), (mx + 32, yy)], fill=(70, 76, 92, 255), width=3)
d.rounded_rectangle((mx - 50, 906, mx + 50, 920), 7, fill=(205, 120, 40, 255))
img.convert('RGB').save(out, quality=95)
