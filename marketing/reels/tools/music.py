"""Original background music (no samples, no copyright): pads, bass, kick, hats, arpeggio.
Mood per learning path. Usage: python3 -I tools/music.py <mood> <seconds> <out.wav>"""
import sys, numpy as np, soundfile as sf

mood, DUR, OUT = sys.argv[1], float(sys.argv[2]), sys.argv[3]
SR = 48000
MOODS = {  # bpm, root midi, chord progression (semitones from root), arp pattern
    'bright':  (108, 57, [[0, 4, 7], [-3, 0, 4], [-7, -3, 0], [-5, -1, 2]], [0, 1, 2, 3, 2, 1, 0, 2]),
    'pulse':   (112, 52, [[0, 3, 7], [-4, 0, 3], [-2, 2, 5], [-5, -2, 2]], [0, 2, 1, 3, 0, 2, 1, 3]),
    'drive':   (118, 50, [[0, 3, 7], [-2, 2, 5], [-4, 0, 3], [-5, -1, 2]], [0, 1, 2, 1, 3, 2, 1, 2]),
    'scan':    (100, 54, [[0, 3, 7], [0, 3, 8], [-2, 3, 7], [-4, 0, 3]], [0, 2, 3, 2, 1, 2, 3, 2]),
    'tension': (96, 49, [[0, 3, 7], [1, 5, 8], [-2, 3, 7], [-4, 0, 3]], [0, 1, 2, 3, 1, 2, 3, 2]),
}
BPM, ROOT, PROG, ARP = MOODS.get(mood, MOODS['bright'])
BEAT = 60 / BPM; BAR = 4 * BEAT
N = int(SR * DUR); L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(7)
hz = lambda m: 440 * 2 ** ((m - 69) / 12)

def put(t0, sig, pan=0.0):
    a = int(t0 * SR); b = min(N, a + len(sig))
    if b <= a: return
    s = sig[:b - a]; L[a:b] += s * (1 - pan) ** .5 * .9; R[a:b] += s * (1 + pan) ** .5 * .9

def tt(d): return np.arange(int(d * SR)) / SR
def saw(f, t): return 2 * ((f * t) % 1) - 1

def pad(freqs, d):
    t = tt(d); env = np.minimum(1, t / .8) * np.minimum(1, (d - t) / .8)
    s = sum(np.sin(2 * np.pi * f * det * t) + .3 * np.sin(4 * np.pi * f * det * t) for f in freqs for det in (.996, 1.004))
    return .045 * env * s

def bass(f, d):
    t = tt(d); env = np.minimum(1, t / .005) * np.exp(-t * 3) * np.minimum(1, (d - t) / .03)
    return .3 * env * (np.sin(2 * np.pi * f * t) + .25 * np.tanh(3 * np.sin(2 * np.pi * f * t)))

def kick():
    t = tt(.35); f = 48 + 110 * np.exp(-t * 35)
    return .75 * np.exp(-t * 10) * np.sin(2 * np.pi * np.cumsum(f) / SR)

def snare():
    t = tt(.25); return .22 * np.exp(-t * 18) * rng.uniform(-1, 1, len(t)) + .12 * np.exp(-t * 25) * np.sin(2 * np.pi * 190 * t)

def hat(): t = tt(.06); return .06 * np.exp(-t * 70) * rng.uniform(-1, 1, len(t))

def pluck(f):
    t = tt(.45); return .085 * np.exp(-t * 7) * (np.sin(2 * np.pi * f * t) + .35 * saw(f * 2, t) * np.exp(-t * 15))

bars = int(DUR / BAR) + 1
for bi in range(bars):
    t0 = bi * BAR; ch = [ROOT + n for n in PROG[bi % len(PROG)]]
    put(t0, pad([hz(n) for n in ch], BAR))
    drums = 1 <= bi and t0 < DUR - BAR * 1.2
    for k in range(4):
        tb = t0 + k * BEAT
        put(tb, bass(hz(ch[0] - 12), BEAT * .9))
        if drums:
            put(tb, kick())
            if k in (1, 3): put(tb, snare(), .1)
            put(tb + BEAT / 2, hat(), .35); put(tb + BEAT * .75, hat() * .6, -.3)
    if bi >= 2 and t0 < DUR - BAR:
        notes = ch + [ch[1] + 12]
        for k in range(8): put(t0 + k * BEAT / 2, pluck(hz(notes[ARP[k] % 4] + 12)), (-.4, .4)[k % 2])

x = np.stack([L, R], 1)
t = np.arange(N) / SR
x *= (np.minimum(1, t / 1.0) * np.minimum(1, (DUR - t) / 2.0))[:, None]
x /= np.abs(x).max() or 1
sf.write(OUT, (x * .89).astype(np.float32), SR, subtype='PCM_16')
print('music', mood, DUR, 's')
