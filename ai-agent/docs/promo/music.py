"""Original 48 s soundtrack for the ad: dark tension intro, impact at 5 s, driving 120 BPM groove, final hit at 41.5 s."""
import wave

import numpy as np

SR, DUR, BPM = 48000, 48.0, 120
BEAT = 60 / BPM
N = int(SR * DUR)
L = np.zeros(N)
R = np.zeros(N)
rng = np.random.default_rng(3)


def add(sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= N:
        return
    sig = sig[: N - i] * gain
    L[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 - pan))
    R[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 + pan))


def t_(d):
    return np.arange(int(d * SR)) / SR


def env(d, a=0.005, r=None):
    t = t_(d)
    e = np.minimum(1, t / a) if a else np.ones_like(t)
    return e * (np.exp(-t / r) if r else np.clip((d - t) / max(d * 0.3, 1e-3), 0, 1))


def tone(f, d, harm=6, bright=1.0):
    t = t_(d)
    return sum(np.sin(2 * np.pi * f * k * t) / k ** (1.6 / bright) for k in range(1, harm + 1) if f * k < 16000)


def hp(x, n=2):
    for _ in range(n):
        x = np.diff(x, prepend=0)
    return x


def kick(d=0.45):
    t = t_(d)
    f = 45 + 110 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) + 0.3 * hp(rng.standard_normal(len(t)), 1) * np.exp(-t * 200)


def hat(d=0.06):
    return hp(rng.standard_normal(int(d * SR)), 3) * np.exp(-t_(d) * 70) * 0.08


def clap(d=0.25):
    n = hp(rng.standard_normal(int(d * SR)), 2) * 0.25
    t = t_(d)
    e = np.exp(-t * 18) + 0.6 * np.exp(-((t - 0.012) % 0.011) * 400) * (t < 0.035)
    return n * e


def boom(d=3.0):
    t = t_(d)
    f = 30 + 60 * np.exp(-t * 3)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    noise = hp(rng.standard_normal(len(t)), 1) * np.exp(-t * 2.5) * 0.25
    return s + noise


def riser(d):
    t = t_(d)
    f = 200 * (12 ** (t / d))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.15 + hp(rng.standard_normal(len(t)), 2) * 0.12
    return s * (t / d) ** 2


NOTE = lambda m: 440 * 2 ** ((m - 69) / 12)
# Am - F - C - G, two bars (4 s) each
CHORDS = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [55, 60, 64]), (55, [55, 59, 62])]

# ---- intro 0-5 s: drone, heartbeat, ticking, riser
add(tone(NOTE(33), 5.2, 8, 0.6) * np.minimum(1, t_(5.2) / 1.5) * np.clip((5.2 - t_(5.2)) / 0.3, 0, 1), 0, 0.35)
add(tone(NOTE(45) * 1.005, 5.2, 4) * np.minimum(1, t_(5.2) / 2.5) * np.clip((5.2 - t_(5.2)) / 0.3, 0, 1), 0, 0.12, 0.3)
for b in np.arange(0, 5, BEAT):
    add(kick(0.3), b, 0.45)
    add(kick(0.25), b + 0.18, 0.25)
for s in np.arange(0, 5, BEAT / 4):
    add(hat(0.03), s, 0.5 if (s / (BEAT / 4)) % 4 == 0 else 0.25, 0.4)
add(riser(1.6), 3.4, 1.0)

# ---- impacts
add(boom(3.5), 5.0, 1.0)
add(boom(4.0), 41.5, 1.0)
add(riser(1.5), 40.0, 1.0)

# ---- groove 5-41.5 s
for bar_t in np.arange(5.0, 41.5, 4 * BEAT * 2):
    idx = int(round((bar_t - 5.0) / (8 * BEAT))) % 4
    root, triad = CHORDS[idx]
    seg = min(8 * BEAT, 41.5 - bar_t)
    pad = sum(tone(NOTE(m), seg + 0.4, 5, 0.7) for m in triad) * env(seg + 0.4, 0.4)
    add(pad, bar_t, 0.07, -0.2)
    add(pad, bar_t + 0.012, 0.07, 0.2)
    for k in range(int(seg / (BEAT / 2))):
        add(tone(NOTE(root - 12), BEAT / 2, 6, 1.3) * env(BEAT / 2, 0.004, 0.12), bar_t + k * BEAT / 2 + 0.0, 0.32)
    if bar_t >= 9.4:
        arp = [triad[0] + 12, triad[1] + 12, triad[2] + 12, triad[1] + 12]
        for k in range(int(seg / (BEAT / 4))):
            add(tone(NOTE(arp[k % 4]), 0.2, 4, 1.5) * env(0.2, 0.002, 0.06), bar_t + k * BEAT / 4, 0.09, (-0.5, 0.5)[k % 2])
for b in np.arange(5.0, 41.5 - 1e-6, BEAT):
    building = 36.5 <= b
    add(kick(), b, 0.9)
    add(hat(), b + BEAT / 2, 1.0, 0.3)
    if b >= 9.4:
        add(hat(0.03), b + BEAT / 4, 0.5, -0.3)
        add(hat(0.03), b + 3 * BEAT / 4, 0.5, -0.3)
    if b >= 9.4 and round((b - 5.0) / BEAT) % 2 == 1:
        add(clap(), b, 0.9 if not building else 1.1)
    if building:
        add(clap(0.12), b + BEAT / 2, 0.35 * (b - 36.5) / 5)

# ---- outro 41.5-48: chord ring out
seg = 6.5
pad = sum(tone(NOTE(m), seg, 6, 0.8) for m in [57, 60, 64, 69]) * env(seg, 0.02, 2.2)
add(pad, 41.5, 0.12)
add(tone(NOTE(33), seg, 8, 0.6) * env(seg, 0.01, 2.0), 41.5, 0.35)

mix = np.stack([L, R], 1)
fade = np.ones(N)
fade[:int(0.05 * SR)] = np.linspace(0, 1, int(0.05 * SR))
fade[-int(2.0 * SR):] *= np.linspace(1, 0, int(2.0 * SR)) ** 1.5
mix *= fade[:, None]
mix = np.tanh(mix * 1.4) / np.tanh(1.4)
mix *= 0.89 / np.max(np.abs(mix))
with wave.open("music_raw.wav", "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype("<i2").tobytes())
print("ok")
