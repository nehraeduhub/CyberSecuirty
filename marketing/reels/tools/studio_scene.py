"""Presenter in the owner's real studio picture: the owner (cut-out) sits behind the front desk of the studio
background, a laptop in front of him (lid to the camera), lit warm like the room. Output 1080x1350 (4:5).
Usage: python3 -I tools/studio_scene.py <cutout.png> <studio background> <logo.png> <out.png>"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

cut, bgf, logo, out = sys.argv[1:5]
W, H = 1080, 1350
bg = Image.open(bgf).convert('RGB'); k = W / bg.width
bg = bg.resize((W, int(bg.height * k)), Image.LANCZOS)
Y0 = 330; scene = bg.crop((0, Y0, W, Y0 + H)).convert('RGBA')
TABLE = int(1318 * k) - Y0                          # top edge of the front desk in the scene

# presenter, graded to the warm room light
p = Image.open(cut).convert('RGBA'); p = p.crop(p.getbbox())
p.putalpha(p.getchannel('A').filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(1.5)))
s = 1060 / 1014; p = p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS)
rgb = np.asarray(p.convert('RGB')).astype(np.float32)
rgb = rgb * np.array([1.04, 0.95, 0.80]) * 0.86 + np.array([10, 4, 0])
rgb = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
p = Image.merge('RGBA', (*rgb.split(), p.getchannel('A')))
px, py = 560 - p.width // 2, 170
# warm rim from the lamp / LED strips behind
rim = Image.new('RGBA', (W, H), (0, 0, 0, 0)); rim.paste(Image.new('RGBA', p.size, (255, 170, 70, 90)), (px - 7, py - 4), p)
scene = Image.alpha_composite(scene, rim.filter(ImageFilter.GaussianBlur(10)))
layer = Image.new('RGBA', (W, H), (0, 0, 0, 0)); layer.paste(p, (px, py), p); scene = Image.alpha_composite(scene, layer)

# put the studio's foreground back on top: the front desk and everything standing on it (mug, plant, old laptop)
front = bg.crop((0, Y0, W, Y0 + H)).convert('RGBA')
m = Image.new('L', (W, H), 0); dm = ImageDraw.Draw(m)
dm.rectangle((0, TABLE, W, H), fill=255)
dm.rectangle((int(770 * k), int(1230 * k) - Y0, W, TABLE), fill=255)      # mug
dm.rectangle((0, int(1160 * k) - Y0, int(320 * k), TABLE), fill=255)       # laptop + plant on the left
scene.paste(front, (0, 0), m.filter(ImageFilter.GaussianBlur(2)))

# laptop in front of him, lid towards the camera
lg = Image.open(logo).convert('RGBA'); a = np.array(lg); a[..., 3] = np.where(a[..., :3].min(axis=2) > 190, 0, a[..., 3])
lg = Image.fromarray(a); lg = lg.crop(lg.getbbox())
lx0, lx1, ly1 = 330, 800, TABLE + 6; ly0 = ly1 - 270
sh = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((lx0 - 10, ly0 - 6, lx1 + 10, ly1 + 14), 28, fill=(0, 0, 0, 150))
scene = Image.alpha_composite(scene, sh.filter(ImageFilter.GaussianBlur(12)))
lid = Image.new('RGBA', (lx1 - lx0, ly1 - ly0)); g = np.linspace(0, 1, lid.height)[:, None]
arr = np.zeros((lid.height, lid.width, 4), np.uint8)
arr[..., 0] = (52 + 26 * (1 - g)).astype(np.uint8); arr[..., 1] = (54 + 22 * (1 - g)).astype(np.uint8); arr[..., 2] = (60 + 18 * (1 - g)).astype(np.uint8); arr[..., 3] = 255
lid = Image.fromarray(arr); lm = Image.new('L', lid.size, 0); ImageDraw.Draw(lm).rounded_rectangle((0, 0, lid.width - 1, lid.height - 1), 24, fill=255)
scene.paste(lid, (lx0, ly0), lm)
d = ImageDraw.Draw(scene)
d.rounded_rectangle((lx0, ly0, lx1, ly1), 24, outline=(150, 128, 96, 255), width=3)                  # warm edge light
d.polygon([(lx0 - 70, ly1), (lx1 + 70, ly1), (lx1 + 40, ly1 + 26), (lx0 - 40, ly1 + 26)], fill=(64, 62, 64, 255))
small = lg.resize((110, int(lg.height * 110 / lg.width)), Image.LANCZOS)
scene.alpha_composite(small, ((lx0 + lx1 - 110) // 2, (ly0 + ly1 - small.height) // 2))
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(glow).ellipse((380, 420, 760, 760), fill=(170, 200, 255, 30))
scene = Image.alpha_composite(scene, glow.filter(ImageFilter.GaussianBlur(60)))
scene.convert('RGB').save(out, quality=95)
