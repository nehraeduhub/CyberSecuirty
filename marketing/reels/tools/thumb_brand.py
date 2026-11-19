"""Final thumbnail: the reel's own cover (topic-specific) + a brand strip at the bottom: the owner's photo in a
circle with the accent ring and a website call to action. Same file name as the reel, .jpg.
Usage: python3 -I tools/thumb_brand.py <cover.jpg> <owner photo> <accent #hex> <out.jpg>"""
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

cover, photo, accent, out = sys.argv[1:5]
W, H = 1080, 1920
im = Image.open(cover).convert('RGB').resize((W, H))
F = '/usr/share/fonts/opentype/inter/'
big = ImageFont.truetype(F + 'Inter-ExtraBold.otf', 58); mid = ImageFont.truetype(F + 'Inter-SemiBold.otf', 40)
acc = tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))

# strip: dark glass card across the bottom
y0, y1 = 1662, 1878
card = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(card)
d.rounded_rectangle((40, y0, W - 40, y1), 44, fill=(6, 21, 43, 235), outline=acc + (255,), width=4)
im = Image.alpha_composite(im.convert('RGBA'), card)

# owner photo: face-centred square crop -> circle with accent ring and a soft glow
p = Image.open(photo).convert('RGB'); pw, ph = p.size
s = int(min(pw, ph) * 0.62); cx, cy = pw // 2, int(ph * 0.36)
p = p.crop((cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2)).resize((180, 180), Image.LANCZOS)
mask = Image.new('L', (180, 180), 0); ImageDraw.Draw(mask).ellipse((0, 0, 179, 179), fill=255)
px, py = 78, y0 + (y1 - y0) // 2 - 90
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(glow).ellipse((px - 12, py - 12, px + 192, py + 192), fill=acc + (150,))
im = Image.alpha_composite(im, glow.filter(ImageFilter.GaussianBlur(12)))
ring = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(ring).ellipse((px - 7, py - 7, px + 187, py + 187), fill=acc + (255,))
im = Image.alpha_composite(im, ring); im.paste(p, (px, py), mask)

d = ImageDraw.Draw(im); tx = px + 222
d.text((tx, y0 + 34), 'Abhi enroll karo', font=mid, fill=(203, 213, 225))
d.text((tx, y0 + 82), 'techguardians.in', font=big, fill=acc)
d.text((tx, y0 + 156), 'Handbook  +  CTF  +  Training', font=ImageFont.truetype(F + 'Inter-Medium.otf', 32), fill=(148, 163, 184))
im.convert('RGB').save(out, quality=92)
