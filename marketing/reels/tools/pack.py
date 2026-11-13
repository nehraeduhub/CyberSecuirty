"""Packs the finished reels in out/ into zips of at most ~90 MB (GitHub refuses files over 100 MB) and writes
the posting calendar. Groups: brand reels, learning paths, topic reels by path. Zip names say what is inside.
Usage: python3 -I tools/pack.py <reels dir> <zip dir> [first posting date YYYY-MM-DD]"""
import csv, datetime, json, os, sys, zipfile
R, Z = sys.argv[1], sys.argv[2]
start = datetime.date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else None
LIMIT = 90 * 1024 * 1024
topics = json.load(open(os.path.join(R, 'topics.json'), encoding='utf-8'))
out = os.path.join(R, 'out')
size = lambda n: sum(os.path.getsize(os.path.join(out, n, f)) for f in os.listdir(os.path.join(out, n)))
have = sorted(d for d in os.listdir(out) if os.path.exists(os.path.join(out, d, d + '.mp4')))
groups = [('Brand', [d for d in have if d.startswith('B')]), ('Learning-Paths', [d for d in have if d.startswith('P')])]
paths = []
for t in topics:
    if t['path'] not in paths: paths.append(t['path'])
for p in paths:
    groups.append((f'Topics-{p}', [t['name'] for t in topics if t['path'] == p and t['name'] in have]))
os.makedirs(Z, exist_ok=True)
for f in os.listdir(Z):
    if f.endswith('.zip'): os.remove(os.path.join(Z, f))
index = []
for label, names in groups:
    parts, cur, tot = [], [], 0
    for n in names:
        s = size(n)
        if cur and tot + s > LIMIT: parts.append(cur); cur, tot = [], 0
        cur.append(n); tot += s
    if cur: parts.append(cur)
    for i, part in enumerate(parts, 1):
        first, last = part[0].split('-')[0], part[-1].split('-')[0]
        zn = f"TechGuardians-Reels-{label}{'-Part%d' % i if len(parts) > 1 else ''}-{first}{'-to-' + last if last != first else ''}.zip"
        with zipfile.ZipFile(os.path.join(Z, zn), 'w', zipfile.ZIP_STORED) as z:
            for n in part:
                for f in sorted(os.listdir(os.path.join(out, n))): z.write(os.path.join(out, n, f), f'{n}/{f}')
        mb = os.path.getsize(os.path.join(Z, zn)) / 1e6
        index.append((zn, mb, part)); print(f'{zn}  {mb:.0f} MB  {len(part)} reels')
with open(os.path.join(Z, 'INDEX.md'), 'w', encoding='utf-8') as f:
    f.write('# Tech Guardians reels — zip index\n\nEach reel folder has: `.mp4` (1080×1920), `-thumbnail.jpg`, `.srt` captions, `.txt` post caption + hashtags.\n\n')
    for zn, mb, part in index: f.write(f'## {zn} ({mb:.0f} MB)\n' + ''.join(f'- {n}\n' for n in part) + '\n')
if start:    # one reel a day: brand reels, then path by path in series order (the path reel, then its topics),
    # so the "Agli reel: Room N+1" line at the end of every topic reel matches what is posted next
    brand = [d for d in have if d.startswith('B')]; pr = dict(zip(paths, [d for d in have if d.startswith('P')]))
    order = brand[:]
    for p in paths: order += [x for x in [pr.get(p)] if x] + [t['name'] for t in topics if t['path'] == p and t['name'] in have]
    with open(os.path.join(R, 'calendar.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['day', 'date', 'weekday', 'time_IST', 'reel', 'video', 'thumbnail', 'caption_file', 'also_post_on'])
        for i, n in enumerate(order):
            d = start + datetime.timedelta(days=i)
            w.writerow([i + 1, d.isoformat(), d.strftime('%a'), '19:30', n, f'{n}.mp4', f'{n}-thumbnail.jpg', f'{n}.txt', 'YouTube Shorts + WhatsApp Status + Facebook Reels'])
    print('calendar.csv:', len(order), 'days from', start)
