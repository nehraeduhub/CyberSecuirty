"""Synthesise a royalty-free cyber-thriller music bed + SFX synced to reel events.

Usage: python3 tools/music.py events.json out.wav
events.json = {"duration": 88, "events": [{"t": 0, "type": "alarm"}, ...]}
Everything is generated here, so there are no copyright claims on the audio.
"""
import json, sys, wave
import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def env(n, a=0.005, r=None, curve=4.0):
    t = np.arange(n) / SR
    e = np.minimum(1, t / a) if a else np.ones(n)
    if r:
        e *= np.exp(-curve * t / r)
    return e


def sine(f, d):
    return np.sin(2 * np.pi * f * np.arange(int(d * SR)) / SR)


def saw(f, d):
    n = int(d * SR)
    ph = np.cumsum(np.full(n, f) if np.ndim(f) == 0 else f) / SR
    return 2 * (ph % 1) - 1


def lp_fast(x, cutoff):
    # FFT brick-ish low-pass, fast for long buffers
    X = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (fr / cutoff) ** 4)
    return np.fft.irfft(X, len(x))


def hp_fast(x, cutoff):
    X = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 - 1 / (1 + (fr / cutoff) ** 4)
    return np.fft.irfft(X, len(x))


def add(buf, sig, t, g=1.0):
    i = int(t * SR)
    if i >= len(buf): return
    j = min(len(buf), i + len(sig))
    buf[i:j] += g * sig[: j - i]


# ---------------- instruments ----------------
def kick():
    d = 0.45; n = int(d * SR); t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, .002, .25, 3) * 1.0


def snare():
    d = 0.25; n = int(d * SR)
    nz = hp_fast(rng.standard_normal(n), 1500) * env(n, .001, .12, 5)
    tone = sine(190, d) * env(n, .001, .08, 6)
    return (nz * .55 + tone * .4)


def hat(open_=False):
    d = .25 if open_ else .05; n = int(d * SR)
    return hp_fast(rng.standard_normal(n), 7000) * env(n, .001, d, 5) * .22


def bass(f, d):
    n = int(d * SR)
    s = lp_fast(saw(f, d) * .6 + sine(f / 2, d) * .8, 260)
    return s * env(n, .01, d * 1.2, 1.5)


def pluck(f, d=.35):
    n = int(d * SR)
    s = saw(f, d) * .5 + sine(f * 2, d) * .3
    return lp_fast(s, 2400) * env(n, .003, .22, 4)


def pad(freqs, d):
    n = int(d * SR); s = np.zeros(n)
    for f in freqs:
        for det in (-.25, .25):
            s += saw(f * (1 + det / 100), d)
    s = lp_fast(s, 1100) / (len(freqs) * 2)
    e = np.minimum(1, np.arange(n) / (SR * .6)) * np.minimum(1, (n - np.arange(n)) / (SR * .6))
    return s * e


# ---------------- sfx ----------------
def sfx(kind):
    if kind == 'whoosh':
        d = .5; n = int(d * SR); t = np.arange(n) / SR
        nz = rng.standard_normal(n)
        sweep = np.zeros(n); acc = 0
        cut = 300 + 5000 * np.sin(np.pi * t / d) ** 2
        a = 1 - np.exp(-2 * np.pi * cut / SR)
        for i in range(n):
            acc += a[i] * (nz[i] - acc); sweep[i] = acc
        return sweep * np.sin(np.pi * t / d) ** 2 * .9
    if kind == 'ping':
        d = .25; n = int(d * SR)
        return (sine(1320, d) + .6 * sine(1980, d)) * env(n, .002, .12, 4) * .35
    if kind == 'pop':
        d = .12; n = int(d * SR); t = np.arange(n) / SR
        return np.sin(2 * np.pi * np.cumsum(500 + 900 * np.exp(-t * 40)) / SR) * env(n, .001, .08, 5) * .45
    if kind == 'notif':
        a = sine(988, .14) * env(int(.14 * SR), .002, .12, 3)
        b = sine(1319, .3) * env(int(.3 * SR), .002, .25, 3)
        return np.concatenate([a, b]) * .4
    if kind == 'error':
        d = .9; n = int(d * SR)
        s = lp_fast(saw(110, d) + saw(116.5, d), 900) * env(n, .005, .9, 2)
        s *= (np.sign(np.sin(2 * np.pi * 6 * np.arange(n) / SR)) * .3 + .7)
        return s * .45
    if kind == 'stamp':
        k = kick()[: int(.3 * SR)] * .8
        nz = hp_fast(rng.standard_normal(len(k)), 800) * env(len(k), .001, .06, 6) * .4
        return k + nz
    if kind == 'success':
        out = np.zeros(int(.5 * SR))
        for i, f in enumerate((784, 988, 1175)):
            s = sine(f, .3) * env(int(.3 * SR), .002, .2, 3) * .25
            add(out, s, i * .07)
        return out
    if kind in ('tap', 'toggle'):
        d = .05; n = int(d * SR)
        f = 2500 if kind == 'tap' else 1800
        return (sine(f, d) * .5 + hp_fast(rng.standard_normal(n), 3000) * .4) * env(n, .0005, .02, 6) * .5
    if kind == 'boom':
        d = 1.4; n = int(d * SR); t = np.arange(n) / SR
        sub = np.sin(2 * np.pi * np.cumsum(35 + 80 * np.exp(-t * 6)) / SR) * env(n, .002, 1.2, 2.5)
        nz = lp_fast(rng.standard_normal(n), 900) * env(n, .002, .5, 4) * .5
        return (sub + nz) * .8
    if kind == 'alarm':
        d = 2.6; n = int(d * SR); t = np.arange(n) / SR
        f = 750 + 350 * np.sin(2 * np.pi * 1.6 * t)
        s = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR))
        return lp_fast(s, 3000) * np.minimum(1, (d - t) / .5) * .16
    return np.zeros(1)


def build(duration, events, beat_start=5.0, voice=None):
    n = int((duration + 1.5) * SR)
    music = np.zeros(n); fx = np.zeros(n)
    bpm = 100; spb = 60 / bpm; bar = spb * 4
    # A minor tense progression: Am  F  Dm  E
    prog = [(55.0, (220, 261.6, 329.6)), (43.65, (174.6, 220, 261.6)), (36.71, (146.8, 174.6, 220)), (41.2, (164.8, 207.7, 246.9))]
    arp_notes = {0: (440, 523.3, 659.3, 523.3), 1: (349.2, 440, 523.3, 440), 2: (293.7, 349.2, 440, 349.2), 3: (329.6, 415.3, 493.9, 415.3)}
    K, Sn, H, Ho = kick(), snare(), hat(), hat(True)
    # intro: tense pad + ticking only
    add(music, pad((110, 130.8, 164.8), beat_start + .5) * .5, 0)
    t = 0.0
    while t < beat_start:
        add(music, H * .6, t); t += spb / 2
    # main groove
    bi = 0; t = beat_start
    while t < duration - 0.5:
        root, chord = prog[bi % 4]
        add(music, pad(chord, bar + .3) * .35, t)
        for b in range(4):
            tb = t + b * spb
            if b in (0, 2): add(music, K, tb)
            if b == 2 and bi % 2: add(music, K * .7, tb + spb * .75)
            if b in (1, 3): add(music, Sn * .55, tb)
            add(music, H, tb); add(music, (Ho if b == 3 else H) * .8, tb + spb / 2)
            add(music, bass(root, spb * .9) * .55, tb)
            for s in range(2):
                add(music, pluck(arp_notes[bi % 4][(b * 2 + s) % 4]) * .16, tb + s * spb / 2)
        t += bar; bi += 1
    # ending fade
    fade = int(2.0 * SR); end = int(duration * SR)
    music[end - fade:end] *= np.linspace(1, 0, fade); music[end:] = 0
    for e in events:
        add(fx, sfx(e['type']), e['t'])
    vo = np.zeros(n)
    for v in voice or []:
        with wave.open(v['file']) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(float) / 32768
            if w.getnchannels() == 2: a = a.reshape(-1, 2).mean(1)
        add(vo, a, v['t'])
    # sidechain: smooth voice envelope, music drops ~10 dB while RJ speaks
    env_v = np.abs(vo)
    k = int(.25 * SR); cs = np.concatenate([[0], np.cumsum(env_v)]); i0 = np.clip(np.arange(n) - k // 2, 0, n); i1 = np.clip(np.arange(n) + k // 2, 0, n); env_v = (cs[i1] - cs[i0]) / k
    env_v = np.clip(env_v / (env_v.max() + 1e-9) * 3, 0, 1)
    duck = 1 - .68 * env_v
    mvol = .5 if voice else .55
    mix = music * mvol * duck + fx * (.55 if voice else .9) + vo * 1.0
    mix = np.tanh(mix * 1.05) * .92
    return mix[: int(duration * SR)]


def write(path, x):
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], 1)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype('<i2').tobytes())


if __name__ == '__main__':
    data = json.load(open(sys.argv[1]))
    write(sys.argv[2], build(data['duration'], data['events'], voice=data.get('voice')))
    print('wrote', sys.argv[2])
