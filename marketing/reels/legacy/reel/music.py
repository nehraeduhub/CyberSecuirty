"""Original 60 s background track for the reel: pad chords, bass, kick, hats, arp.
Usage: python3 -I music.py out.wav"""
import math, random, struct, sys, wave

SR = 22050
DUR = 60.0
BPM = 100
BEAT = 60 / BPM
N = int(SR * DUR)
buf = [0.0] * N
random.seed(7)

def midi(n): return 440.0 * 2 ** ((n - 69) / 12)

# A minor, F, C, G (one chord per bar of 4 beats)
PROG = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
BAR = 4 * BEAT

def add(start, dur, fn):
    a = int(start * SR); b = min(N, int((start + dur) * SR))
    for i in range(max(0, a), b):
        buf[i] += fn((i - a) / SR)

def pad(freqs, dur):
    def f(t):
        env = min(1, t / 0.6) * min(1, (dur - t) / 0.6)
        s = 0.0
        for fr in freqs:
            for det in (0.997, 1.003):
                ph = t * fr * det
                s += (2 * abs(2 * (ph - math.floor(ph + 0.5))) - 1)  # triangle
        return 0.035 * env * s
    return f

def bass(fr, dur):
    def f(t):
        env = min(1, t / 0.01) * math.exp(-t * 2.2) * min(1, (dur - t) / 0.05)
        return 0.22 * env * math.sin(2 * math.pi * fr * t)
    return f

def kick(t):
    fr = 50 + 90 * math.exp(-t * 30)
    return 0.55 * math.exp(-t * 9) * math.sin(2 * math.pi * fr * t)

def hat(t):
    return 0.05 * math.exp(-t * 60) * (random.random() * 2 - 1)

def pluck(fr):
    def f(t):
        return 0.07 * math.exp(-t * 6) * (math.sin(2 * math.pi * fr * t) + 0.4 * math.sin(4 * math.pi * fr * t))
    return f

bars = int(DUR / BAR) + 1
for bi in range(bars):
    t0 = bi * BAR
    chord = PROG[bi % 4]
    add(t0, BAR, pad([midi(n) for n in chord], BAR))
    full = 1 <= bi < bars - 2          # drums after the intro bar, out for the last bars
    for k in range(4):
        tb = t0 + k * BEAT
        add(tb, BEAT * 0.95, bass(midi(chord[0] - 12), BEAT * 0.95))
        if full:
            add(tb, 0.4, kick)
            add(tb + BEAT / 2, 0.08, hat)
            if k % 2: add(tb + BEAT * 0.75, 0.06, hat)
    if bi >= 2 and bi < bars - 1:      # arpeggio over the chord
        notes = chord + [chord[1] + 12]
        for k in range(8):
            add(t0 + k * BEAT / 2, 0.5, pluck(midi(notes[k % 4] + 12)))

# fade in/out and normalise
peak = max(abs(x) for x in buf) or 1
out = wave.open(sys.argv[1], 'wb')
out.setnchannels(1); out.setsampwidth(2); out.setframerate(SR)
frames = bytearray()
for i, x in enumerate(buf):
    t = i / SR
    g = min(1, t / 1.5) * min(1, (DUR - t) / 2.5)
    frames += struct.pack('<h', int(max(-1, min(1, x / peak * 0.85 * g)) * 32767))
out.writeframes(bytes(frames)); out.close()
