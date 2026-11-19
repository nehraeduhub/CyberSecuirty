"""Delivery zips of the final reels (owner's voice): every reel as <name>.mp4 + <name>.jpg (same topic name), flat,
so they can replace the files in the owner's folder. Zips stay under ~90 MB (GitHub's 100 MB file limit), grouped as
Brand / Learning paths / Topics by path. Writes INDEX.md (what is in which zip).
Usage: python3 -I tools/pack_final.py <reels dir> <zip dir>"""
import json, os, sys, zipfile
R, Z = sys.argv[1], sys.argv[2]
F = os.path.join(R, 'final'); LIMIT = 90 * 1024 * 1024
topics = json.load(open(os.path.join(R, 'topics.json'), encoding='utf-8'))
have = sorted(n[:-4] for n in os.listdir(F) if n.endswith('.mp4') and os.path.exists(os.path.join(F, n[:-4] + '.jpg')))
size = lambda n: os.path.getsize(os.path.join(F, n + '.mp4')) + os.path.getsize(os.path.join(F, n + '.jpg'))
groups = [('Brand', [n for n in have if n.startswith('B')]), ('Learning-Paths', [n for n in have if n.startswith('P')])]
for p in dict.fromkeys(t['path'] for t in topics):
    groups.append((f'Topics-{p}', [t['name'] for t in topics if t['path'] == p and t['name'] in have]))
os.makedirs(Z, exist_ok=True)
for f in os.listdir(Z):
    if f.endswith('.zip'): os.remove(os.path.join(Z, f))
index = []
for label, names in groups:
    parts, cur, tot = [], [], 0
    for n in names:
        if cur and tot + size(n) > LIMIT: parts.append(cur); cur, tot = [], 0
        cur.append(n); tot += size(n)
    if cur: parts.append(cur)
    for i, part in enumerate(parts, 1):
        a, b = part[0].split('-')[0], part[-1].split('-')[0]
        zn = f"TechGuardians-Reels-{label}{'-Part%d' % i if len(parts) > 1 else ''}-{a}{'-to-' + b if b != a else ''}.zip"
        with zipfile.ZipFile(os.path.join(Z, zn), 'w', zipfile.ZIP_STORED) as z:
            for n in part:
                z.write(os.path.join(F, n + '.mp4'), n + '.mp4'); z.write(os.path.join(F, n + '.jpg'), n + '.jpg')
        index.append((zn, os.path.getsize(os.path.join(Z, zn)) / 1e6, part)); print(f'{zn}  {index[-1][1]:.0f} MB  {len(part)} reels')
with open(os.path.join(Z, 'INDEX.md'), 'w', encoding='utf-8') as f:
    f.write('# Tech Guardians reels — final (owner\'s voice)\n\nEvery reel: `<name>.mp4` (1080×1920) + `<name>.jpg` thumbnail, same name. '
            'Unzip into the reels folder and replace the old files.\n\n')
    for zn, mb, part in index: f.write(f'## {zn} ({mb:.0f} MB)\n' + ''.join(f'- {n}.mp4 + {n}.jpg\n' for n in part) + '\n')
print(len(have), 'reels packed')
