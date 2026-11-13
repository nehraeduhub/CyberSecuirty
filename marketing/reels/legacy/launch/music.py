"""Original 60 s launch soundtrack timed to launch.html.
Countdown ticks + riser (0-4.4 s), boom at the logo reveal, festive groove, boom at the finale.
Usage: python3 -I music.py out.wav"""
import math, random, struct, sys, wave

SR = 22050
DUR = 60.0
N = int(SR * DUR)
L = [0.0] * N
R = [0.0] * N
random.seed(11)
BPM = 110
BEAT = 60 / BPM
START = 4.4                      # the groove starts on the reveal
BAR = 4 * BEAT

def midi(n): return 440.0 * 2 ** ((n - 69) / 12)

def add(start, dur, fn, pan=0.0):
    a = int(start * SR); b = min(N, int((start + dur) * SR))
    gl, gr = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    for i in range(max(0, a), b):
        v = fn((i - a) / SR)
        L[i] += v * gl; R[i] += v * gr

def tri(ph): return 2 * abs(2 * (ph - math.floor(ph + 0.5))) - 1

# --- countdown: ticks, drone, riser ---
for k, at in enumerate([0.0, 1.4, 2.8]):
    fr = [880, 988, 1175][k]
    add(at, 0.35, lambda t, fr=fr: 0.30 * math.exp(-t * 12) * math.sin(2 * math.pi * fr * t))
add(0, 4.4, lambda t: 0.10 * min(1, t / 0.8) * (math.sin(2 * math.pi * 55 * t) + 0.5 * math.sin(2 * math.pi * 82.5 * t)))
def riser(t):
    p = t / 4.4
    fr = 200 + 1400 * p * p
    return (0.05 + 0.12 * p) * (0.6 * math.sin(2 * math.pi * fr * t * (0.5 + p / 2)) + 0.4 * (random.random() * 2 - 1) * p)
add(0, 4.4, riser)

# --- booms ---
def boom(t):
    fr = 38 + 120 * math.exp(-t * 10)
    return 0.9 * math.exp(-t * 2.2) * math.sin(2 * math.pi * fr * t) + 0.25 * math.exp(-t * 6) * (random.random() * 2 - 1)
for at in (4.4, 54.3):
    add(at, 2.5, boom)
    add(at, 3.0, lambda t: 0.08 * math.exp(-t * 1.2) * (random.random() * 2 - 1), -0.3)  # cymbal wash
    add(at, 3.0, lambda t: 0.08 * math.exp(-t * 1.2) * (random.random() * 2 - 1), 0.3)

# --- groove: D A Bm G ---
PROG = [[62, 66, 69], [57, 61, 64], [59, 62, 66], [55, 59, 62]]
def pad(freqs, dur, amp=0.03):
    def f(t):
        env = min(1, t / 0.4) * min(1, (dur - t) / 0.4)
        return amp * env * sum(tri(t * fr * d) for fr in freqs for d in (0.996, 1.004))
    return f
def bass(fr, dur):
    return lambda t: 0.24 * min(1, t / 0.01) * math.exp(-t * 3) * math.sin(2 * math.pi * fr * t) * min(1, (dur - t) / 0.03)
def kick(t):
    fr = 48 + 100 * math.exp(-t * 32)
    return 0.6 * math.exp(-t * 10) * math.sin(2 * math.pi * fr * t)
def clap(t): return 0.16 * math.exp(-t * 28) * (random.random() * 2 - 1)
def hat(t): return 0.045 * math.exp(-t * 70) * (random.random() * 2 - 1)
def bell(fr):
    return lambda t: 0.08 * math.exp(-t * 2.5) * (math.sin(2 * math.pi * fr * t) + 0.5 * math.sin(2 * math.pi * fr * 2.76 * t) * math.exp(-t * 4))
def pluck(fr): return lambda t: 0.055 * math.exp(-t * 7) * tri(fr * t)

MELODY = [74, 76, 78, 81, 78, 76, 74, 69]   # D major pentatonic bells
END = 54.3
bar = 0
t0 = START
while t0 < END:
    chord = PROG[bar % 4]
    add(t0, min(BAR, END - t0 + 0.4), pad([midi(n) for n in chord], min(BAR, END - t0 + 0.4)))
    drums = t0 >= START + BAR - 0.01        # one bar of pads after the boom, then drums
    for k in range(4):
        tb = t0 + k * BEAT
        if tb >= END: break
        add(tb, BEAT * 0.9, bass(midi(chord[0] - 24), BEAT * 0.9))
        if drums:
            add(tb, 0.4, kick)
            if k % 2: add(tb, 0.25, clap)
            add(tb + BEAT / 2, 0.08, hat, 0.4)
    if bar >= 2:                            # arp
        notes = chord + [chord[1] + 12]
        for k in range(8):
            tb = t0 + k * BEAT / 2
            if tb < END: add(tb, 0.4, pluck(midi(notes[k % 4] + 12)), -0.35 if k % 2 else 0.35)
    if bar >= 4 and bar % 2 == 0:           # bell phrase every other bar
        for k, n in enumerate(MELODY[:4] if bar % 4 == 0 else MELODY[4:]):
            tb = t0 + k * BEAT
            if tb < END: add(tb, 1.2, bell(midi(n)), 0.2)
    t0 += BAR; bar += 1

# --- outro: held chord after the final boom ---
add(54.3, 5.7, pad([midi(n) for n in [50, 57, 62, 66, 69]], 5.7, 0.04))
for k, n in enumerate([74, 78, 81, 86]):
    add(54.6 + k * 0.35, 3, bell(midi(n)), -0.3 + k * 0.2)

# --- firework crackles at the bursts in launch.html ---
for at in [4.5, 5.2, 5.6, 6.4, 6.9, 11.2, 11.6, 12.4, 17.6, 18, 54.2, 54.7, 55.1, 55.9, 56.4, 57.3, 57.8]:
    pan = random.uniform(-0.7, 0.7)
    add(at, 0.15, lambda t: 0.25 * math.exp(-t * 25) * (random.random() * 2 - 1), pan)
    for c in range(14):
        add(at + 0.4 + random.random() * 1.2, 0.03, lambda t: 0.06 * (random.random() * 2 - 1), pan)

peak = max(max(abs(x) for x in L), max(abs(x) for x in R)) or 1
out = wave.open(sys.argv[1], 'wb')
out.setnchannels(2); out.setsampwidth(2); out.setframerate(SR)
fr = bytearray()
for i in range(N):
    t = i / SR
    g = 0.88 / peak * min(1, (DUR - t) / 2.0)
    fr += struct.pack('<hh', int(max(-1, min(1, L[i] * g)) * 32767), int(max(-1, min(1, R[i] * g)) * 32767))
out.writeframes(bytes(fr)); out.close()
