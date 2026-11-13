"""Scene timing from the voice-over lengths, plus captions (.srt) and the post caption (.txt).
Usage: python3 -I tools/timeline.py <topics.json> <num> <work dir> <out dir>
Writes <work>/data.json (read by template/topic.html), <out>/<name>.srt and <out>/<name>.txt."""
import json, os, re, sys

topics, num, work, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
t = next(x for x in json.load(open(topics, encoding='utf-8')) if x['num'] == num)
vo = json.load(open(os.path.join(work, 'vo.json')))
# scene: (gap before the voice, minimum scene length)
PLAN = [('hook', .5, 5.5), ('learn', .35, 9), ('book', .35, 8.5), ('ctf', .35, 11.5), ('cta', .35, 6)]
TAIL = .6        # breath after each clip
END = 3.2        # end card, music only
scenes, clips, cur = {}, [], 0.0
for name, lead, minimum in PLAN:
    d = max(minimum, lead + vo[name] + TAIL)
    scenes[name] = [round(cur, 3), round(cur + d, 3)]
    clips.append({'scene': name, 'at': round(cur + lead, 3), 'dur': vo[name]})
    cur += d
scenes['end'] = [round(cur, 3), round(cur + END, 3)]
total = round(cur + END, 2)

def chunks(text, maxc=32):
    """Caption lines: split at sentence/comma breaks, then evenly by words; no tiny leftovers."""
    import math
    clauses = [c.strip(' —') for c in re.split(r'(?<=[.?!,])\s+|\s+—\s+', text) if c.strip(' —')]
    out = []
    for c in clauses:
        w = c.split(); n = max(1, math.ceil(len(c) / maxc)); k = math.ceil(len(w) / n)
        out += [' '.join(w[i:i + k]) for i in range(0, len(w), k)]
    for i in range(len(out) - 1, 0, -1):
        if len(out[i].split()) <= 1 or (len(out[i - 1]) + len(out[i]) <= 22):
            out[i - 1] += ' ' + out.pop(i)
    return out

subs = []
for c in clips:
    parts = chunks(t['sub'][c['scene']])
    weights = [len(p) + 6 for p in parts]
    s, tot = c['at'], sum(weights)
    for p, w in zip(parts, weights):
        d = c['dur'] * w / tot
        subs.append({'t0': round(s, 3), 't1': round(s + d, 3), 'text': p.strip(' —')})
        s += d

# moments shared by the animation (template) and the sound effects (sfx.py)
cl = {c['scene']: c for c in clips}
marks = {
    'cards': [round(cl['learn']['at'] + cl['learn']['dur'] * (.2 + i * .27), 3) for i in range(3)],
    # "Task 1 FREE" pops when the voice says पहला टास्क फ़्री; the account card when it says सीटीएफ़ एक्सेस (by position in the text)
    'free': round(cl['ctf']['at'] + cl['ctf']['dur'] * max(0, t['vo']['ctf'].find('पहला')) / len(t['vo']['ctf']) + .4, 3),
    'account': round(cl['ctf']['at'] + cl['ctf']['dur'] * max(0, t['vo']['ctf'].find('सीटीएफ़ एक्सेस')) / len(t['vo']['ctf']), 3),
    'url': round(scenes['cta'][0] + 1.2, 3),
    'enroll': round(cl['cta']['at'] + cl['cta']['dur'] * .55, 3),
}
data = {'topic': t, 'scenes': scenes, 'clips': clips, 'subs': subs, 'marks': marks, 'total': total}
json.dump(data, open(os.path.join(work, 'data.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def ts(x):
    ms = int(round(x * 1000)); return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, t['name'] + '.srt'), 'w', encoding='utf-8') as f:
    for i, s in enumerate(subs, 1): f.write(f"{i}\n{ts(s['t0'])} --> {ts(s['t1'])}\n{s['text']}\n\n")

strip = lambda h: re.sub(r'<[^>]+>', '', h)
caption = f"""{strip(t['hook'])}

{t['title']} — {t['subtitle']} 🛡️
Humare saath seekhenge: {' · '.join(strip(p) for p in t['points'])}

📘 Pehle seekho: {t['title']} Handbook (PDF, {t['pages']} pages)
🚩 Phir practice karo: CTF Room {t['num']} · {t['tasks']} hands-on tasks · Task 1 FREE
👤 CTF access ke liye apna account zaroor banayein

👉 Abhi enroll karo aur seekhna start karo: techguardians.in (link in bio)
Keep Learning · Keep Sharing 🇮🇳

{' '.join(t.get('tags', []) + ['#techguardians', '#cybersecurityindia', '#ctf', '#learncybersecurity', '#hinglish'])}
"""
open(os.path.join(out, t['name'] + '.txt'), 'w', encoding='utf-8').write(caption)
print('total', total, 's;', {k: v for k, v in scenes.items()})
