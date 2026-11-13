"""Sound effects synced to the animation: whoosh on scene changes, impact on the hook, pops on cards,
sparkle on "Task 1 FREE" and the enroll button. All synthesised (no samples).
Usage: python3 -I tools/sfx.py <work/NN/data.json> <out.wav>"""
import json, sys, numpy as np, soundfile as sf

d = json.load(open(sys.argv[1], encoding='utf-8')); SR = 48000
N = int(d['total'] * SR) + SR; L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(3)
def put(t0, s, pan=0.0):
    a = max(0, int(t0 * SR)); b = min(N, a + len(s)); L[a:b] += s[:b - a] * (1 - pan); R[a:b] += s[:b - a] * (1 + pan)
def tt(dur): return np.arange(int(dur * SR)) / SR

def whoosh(dur=.55):
    t = tt(dur); n = rng.uniform(-1, 1, len(t))
    env = np.sin(np.pi * t / dur) ** 2
    cut = 300 + 5000 * np.sin(np.pi * t / dur)            # sweeping one-pole low-pass
    y = np.zeros_like(n); a = 1 - np.exp(-2 * np.pi * cut / SR)
    for i in range(1, len(n)): y[i] = y[i - 1] + a[i] * (n[i] - y[i - 1])
    return .5 * env * y
def impact():
    t = tt(1.2); f = 40 + 80 * np.exp(-t * 8)
    return .7 * np.exp(-t * 3.5) * np.sin(2 * np.pi * np.cumsum(f) / SR) + .15 * np.exp(-t * 12) * rng.uniform(-1, 1, len(t))
def pop(f=880):
    t = tt(.18); return .35 * np.exp(-t * 30) * np.sin(2 * np.pi * (f + 600 * np.exp(-t * 40)) * t)
def sparkle():
    s = np.zeros(int(.9 * SR))
    for k, f in enumerate([1568, 2093, 2637, 3136]):
        t = tt(.5); x = .12 * np.exp(-t * 9) * np.sin(2 * np.pi * f * t); a = int(k * .07 * SR); s[a:a + len(x)] += x
    return s

put(0.02, impact())
for name, (a, b) in d['scenes'].items():
    if a > 0: put(a - .3, whoosh(), (-.3, .3)[int(a) % 2])
for i, c in enumerate(d['marks']['cards']): put(c, pop(700 + 140 * i))
put(d['marks']['free'], sparkle()); put(d['marks']['url'], pop(1000)); put(d['marks']['enroll'], sparkle(), .2)
x = np.stack([L, R], 1)[: int(d['total'] * SR)]
sf.write(sys.argv[2], (x / max(1, np.abs(x).max() / .9)).astype(np.float32), SR, subtype='PCM_16')
print('sfx ok')
