"""Step-by-step guide reels (brand reels such as B6 "How to create a student account").
Voice-over per step (Kokoro, Hindi male), scene timing from the voice, captions and the post caption.
Usage: python3 -I tools/guide.py <guides/x.json> <work dir> <out dir>
Writes <work>/data.json (read by template/guide.html), <out>/<name>.srt and .txt. Voice clips are cached by text."""
import hashlib, json, math, os, re, sys
import numpy as np, soundfile as sf

G = json.load(open(sys.argv[1], encoding='utf-8')); WORK, OUT = sys.argv[2], sys.argv[3]
os.makedirs(WORK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
VOICE, SPEED = G.get('voice', 'hm_omega'), G.get('speed', 1.0)
_k = None
def tts(text):
    global _k
    key = hashlib.sha1(f'{VOICE}|{SPEED}|{text}'.encode()).hexdigest()[:12]
    f = os.path.join(WORK, f'vo-{key}.wav')
    if not os.path.exists(f):
        if _k is None:
            from kokoro_onnx import Kokoro
            d = os.environ.get('KOKORO_DIR', '.'); _k = Kokoro(os.path.join(d, 'kokoro-v1.0.onnx'), os.path.join(d, 'voices-v1.0.bin'))
        s, sr = _k.create(text, voice=VOICE, speed=SPEED, lang='hi'); s = np.asarray(s, dtype=np.float32)
        nz = np.nonzero(np.abs(s) > 0.01)[0]; s = s[max(0, nz[0] - 600): nz[-1] + 2400]
        sf.write(f, s, sr)
    return f, sf.info(f).duration

scenes, clips, cur = {}, [], 0.0
items = [('intro', G['intro'], .4, 4)] + [(f's{i + 1}', s, .3, 3.8) for i, s in enumerate(G['steps'])] + [('cta', G['cta'], .3, 4.5)] + ([('ref', G['ref'], .3, 4.5)] if G.get('ref') else [])
for name, it, lead, minimum in items:
    f, dur = tts(it['vo'])
    d = max(minimum, lead + dur + .4)
    scenes[name] = [round(cur, 3), round(cur + d, 3)]
    clips.append({'scene': name, 'at': round(cur + lead, 3), 'dur': round(dur, 3), 'file': os.path.basename(f), 'sub': it['sub']})
    cur += d
scenes['end'] = [round(cur, 3), round(cur + 3.2, 3)]
total = round(cur + 3.2, 2)

def chunks(text, maxc=32):
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
    parts = chunks(c['sub']); wts = [len(p) + 6 for p in parts]; s = c['at']
    for p, w in zip(parts, wts):
        d = c['dur'] * w / sum(wts); subs.append({'t0': round(s, 3), 't1': round(s + d, 3), 'text': p}); s += d

# absolute times of taps / confetti for the sound effects
cl = {c['scene']: c for c in clips}; taps, sparkles = [], []
for i, st in enumerate(G['steps']):
    c = cl[f's{i + 1}']
    for sh in st['shots']:
        taps += [round(c['at'] + c['dur'] * t['p'], 3) for t in sh.get('tap', [])]
    if 'confetti' in st: sparkles.append(round(c['at'] + c['dur'] * st['confetti'], 3))
data = {'guide': G, 'scenes': scenes, 'clips': clips, 'subs': subs, 'total': total, 'marks': {'taps': taps, 'sparkles': sparkles}}
json.dump(data, open(os.path.join(WORK, 'data.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
ts = lambda x: f'{int(x // 3600):02d}:{int(x // 60 % 60):02d}:{int(x % 60):02d},{int(round(x * 1000)) % 1000:03d}'
with open(os.path.join(OUT, G['name'] + '.srt'), 'w', encoding='utf-8') as f:
    for i, s in enumerate(subs, 1): f.write(f"{i}\n{ts(s['t0'])} --> {ts(s['t1'])}\n{s['text']}\n\n")
more = f"\n▶ Ye reel bhi dekho: {G['ref']['rom']}" if G.get('ref') else ''
open(os.path.join(OUT, G['name'] + '.txt'), 'w', encoding='utf-8').write(G['caption'] + more + '\n\n' + ' '.join(G['tags']) + '\n')
print('total', total, 's;', ' '.join(f'{k}:{v[1] - v[0]:.1f}' for k, v in scenes.items()))
