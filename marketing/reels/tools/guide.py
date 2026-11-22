"""Step-by-step guide reels (brand reels such as B6 "How to create a student account").
Voice-over per step (Kokoro, Hindi male), scene timing from the voice, captions and the post caption.
Usage: python3 -I tools/guide.py <guides/x.json> <work dir> <out dir>
Writes <work>/data.json (read by template/guide.html), <out>/<name>.srt and .txt. Voice clips are cached by text."""
import hashlib, json, math, os, re, sys
import numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from speak import render, caption_spans
import voice_qc
from voice_qc import QC

G = json.load(open(sys.argv[1], encoding='utf-8')); WORK, OUT = sys.argv[2], sys.argv[3]
os.makedirs(WORK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
VOICE, SPEED = G.get('voice', 'hm_omega'), G.get('speed', 1.0)
_k, _qc = None, QC()
DEFAULT = {'intro': 'CONFIDENT', 'cta': 'EXCITED', 'ref': 'POLITE'}        # steps: CALM (explaining)
def tts(text, default, VOICE=VOICE):
    """Voice line with directions -> (wav file, length, phrase timings, QC log); cached by text + style."""
    global _k
    key = hashlib.sha1(f'v3|{VOICE}|{SPEED}|{default}|{text}'.encode()).hexdigest()[:12]
    f = os.path.join(WORK, f'vo-{key}.wav'); j = f[:-4] + '.json'
    if not os.path.exists(f) or not os.path.exists(j):
        if _k is None:
            from kokoro_onnx import Kokoro
            d = os.environ.get('KOKORO_DIR', '.'); _k = Kokoro(os.path.join(d, 'kokoro-v1.0.onnx'), os.path.join(d, 'voices-v1.0.bin'))
        voice_qc.RANGE['f0'] = (150.0, 300.0) if VOICE.startswith('hf') else (95.0, 175.0)
        s, sr, segs, log = render(_k, text, VOICE, SPEED, default, _qc)
        sf.write(f, s, sr); json.dump({'segs': segs, 'qc': log}, open(j, 'w', encoding='utf-8'), ensure_ascii=False)
    meta = json.load(open(j, encoding='utf-8'))
    return f, sf.info(f).duration, meta['segs'], meta['qc']

scenes, clips, cur = {}, [], 0.0
items = [('intro', G['intro'], .35, 4)] + [(f's{i + 1}', s, .25, 3.8) for i, s in enumerate(G['steps'])] + [('cta', G['cta'], .25, 4.5)] + ([('ref', G['ref'], .25, 4.5)] if G.get('ref') else [])
MIX = G.get('mix', True)      # two hosts: female hf_alpha / male hm_omega (owner's cloned voice later), alternating
def host(i):
    return VOICE if not MIX else ('hf_alpha', 'hm_omega')[(i + len(G['name'])) % 2]
for idx, (name, it, lead, minimum) in enumerate(items):
    hv = host(0 if name in ('intro', 'cta') else idx if name.startswith('s') else 1)
    f, dur, segs, qc = tts(it['vo'], DEFAULT.get(name, 'CALM'), hv)
    d = max(minimum, lead + dur + .3)
    scenes[name] = [round(cur, 3), round(cur + d, 3)]
    clips.append({'scene': name, 'at': round(cur + lead, 3), 'dur': round(dur, 3), 'file': os.path.basename(f), 'sub': it['sub'], 'segs': segs, 'qc': qc,
                  'script': it['vo'], 'default': DEFAULT.get(name, 'CALM'), 'voice': hv})
    cur += d
scenes['end'] = [round(cur, 3), round(cur + 3.2, 3)]
total = round(cur + 3.2, 2)

def chunks(text, maxc=20):
    clauses = [c.strip(' —') for c in re.split(r'(?<=[.?!,])\s+|\s+—\s+', text) if c.strip(' —')]
    out = []
    for c in clauses:
        w = c.split(); n = max(1, math.ceil(len(c) / maxc)); k = math.ceil(len(w) / n)
        out += [' '.join(w[i:i + k]) for i in range(0, len(w), k)]
    for i in range(len(out) - 1, 0, -1):
        if len(out[i].split()) <= 1 or (len(out[i - 1]) + len(out[i]) <= 14):
            out[i - 1] += ' ' + out.pop(i)
    return out
subs = []
for c in clips:
    subs += caption_spans(c['sub'], c['segs'], c['at'], c['dur'], chunks)

# absolute times of taps / confetti for the sound effects
cl = {c['scene']: c for c in clips}; taps, sparkles = [], []
for i, st in enumerate(G['steps']):
    c = cl[f's{i + 1}']
    for sh in st['shots']:
        taps += [round(c['at'] + c['dur'] * t['p'], 3) for t in sh.get('tap', [])]
    if 'confetti' in st: sparkles.append(round(c['at'] + c['dur'] * st['confetti'], 3))
json.dump({'voice': VOICE, 'speed': SPEED, 'total': total, 'clips': clips}, open(os.path.join(WORK, 'voice.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
data = {'guide': G, 'scenes': scenes, 'clips': clips, 'subs': subs, 'total': total, 'marks': {'taps': taps, 'sparkles': sparkles}}
json.dump(data, open(os.path.join(WORK, 'data.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
ts = lambda x: f'{int(x // 3600):02d}:{int(x // 60 % 60):02d}:{int(x % 60):02d},{int(round(x * 1000)) % 1000:03d}'
with open(os.path.join(OUT, G['name'] + '.srt'), 'w', encoding='utf-8') as f:
    for i, s in enumerate(subs, 1): f.write(f"{i}\n{ts(s['t0'])} --> {ts(s['t1'])}\n{s['text']}\n\n")
more = f"\n▶ Ye reel bhi dekho: {G['ref']['rom']}" if G.get('ref') else ''
open(os.path.join(OUT, G['name'] + '.txt'), 'w', encoding='utf-8').write(G['caption'] + more + '\n\n' + ' '.join(G['tags']) + '\n')
print('total', total, 's;', ' '.join(f'{k}:{v[1] - v[0]:.1f}' for k, v in scenes.items()))
