"""Voice direction for the reel scripts, rendered with Kokoro (offline TTS, one voice for the whole series).

Kokoro has no emotion control and barely pauses at commas, so every phrase is spoken on its own, given the
speed / loudness / pitch of its direction, and joined to the next with a fixed silence. Each phrase is then
checked (tools/voice_qc.py) and regenerated if it fails — see render().

A voice line is Devanagari text with direction tags (the owner's voice-direction list):
  pauses     [SHORT PAUSE] 0.18 s   [LONG PAUSE] 0.40 s
             and automatically: comma 0.10 s · end of sentence (। . !) 0.25 s · question (?) 0.32 s
             Short on purpose: the owner's reference reel (2026-11-16) talks ~73 % of the time with pauses of
             0.1–0.2 s (longest 0.6 s) — a flowing presenter, not a reader who stops at every comma.
  styles     a style tag holds until the next style tag; every line starts in its scene's default style
             [NORMAL] [CALM] [POLITE] [SOFT] [WHISPER] [SERIOUS] [WARNING] [SLOW] [EXCITED]
             [CONFIDENT] [LOUD] [EMPHASIZE] [QUESTIONING]
`plain(text)` removes the tags (for searching and captions)."""
import re
from fractions import Fraction
import numpy as np

#            speed  gain dB  pitch (semitones)   — small steps on purpose: LOUD is not shouting
STYLE = {
    'NORMAL':      (1.00,  0.0,  0.0),
    'CALM':        (0.96, -1.0, -0.3),
    'POLITE':      (0.94, -1.5,  0.2),
    'SOFT':        (0.93, -4.0,  0.0),
    'WHISPER':     (0.90, -7.0, -0.2),   # Kokoro cannot really whisper: this is "very soft and slow"
    'SERIOUS':     (0.94,  0.5, -0.8),
    'WARNING':     (0.92,  2.0, -0.5),
    'SLOW':        (0.88,  0.0,  0.0),
    'EXCITED':     (1.04,  2.0,  0.8),
    'CONFIDENT':   (0.98,  1.5, -0.2),
    'LOUD':        (0.97,  3.5,  0.3),
    'EMPHASIZE':   (0.93,  3.0,  0.5),
    'QUESTIONING': (0.98,  0.0,  0.4),
}
PAUSE_TAG = {'SHORT PAUSE': .18, 'LONG PAUSE': .40}
PUNCT_PAUSE = {',': .10, '।': .25, '.': .25, '!': .25, '?': .32}
JOIN = .05                                   # style change inside a phrase: just a breath
TAG = re.compile(r'\[([A-Z ]+)\]')

def plain(text):
    return re.sub(r'\s+', ' ', TAG.sub(' ', text)).strip()

def pieces(text, default='NORMAL'):
    """[{'text', 'style', 'pause' (after), 'ends' (sentence)}] — one per phrase."""
    out, style = [], default
    for tok in re.split(r'(\[[A-Z ]+\])', text):
        m = TAG.fullmatch(tok.strip())
        if m:
            name = m.group(1)
            if name in PAUSE_TAG:
                if out: out[-1]['pause'] = max(out[-1]['pause'], PAUSE_TAG[name])
            elif name in STYLE: style = name
            else: raise ValueError(f'unknown voice direction [{name}] in: {text}')
            continue
        for part in re.findall(r'[^,।!?.]+[,।!?.]*', tok):
            p = part.strip()
            if not p or not re.search(r'[ऀ-ॿ\w]', p): continue
            end = p[-1] if p[-1] in PUNCT_PAUSE else ''
            out.append({'text': p, 'style': style, 'pause': PUNCT_PAUSE.get(end, JOIN), 'ends': end in '।.!?'})
    if out: out[-1]['pause'] = 0.0
    return out

def synth(kokoro, text, style, voice, speed, lang='hi', tweak=1.0):
    """One phrase in one style -> float32 samples (24 kHz), silence trimmed, gain and pitch applied."""
    f, gain, st = STYLE[style]
    r = 2 ** (st / 12)                       # pitch: speak slower by r, then play back faster by r
    s, sr = kokoro.create(text, voice=voice, speed=speed * f * tweak / r, lang=lang)
    s = np.asarray(s, dtype=np.float32) * .7      # Kokoro peaks go above 1.0 (would clip in a 16-bit wav): leave headroom
    if abs(st) > 1e-6:
        from scipy.signal import resample_poly
        q = Fraction(1 / r).limit_denominator(400); s = resample_poly(s, q.numerator, q.denominator).astype(np.float32)
    nz = np.nonzero(np.abs(s) > 0.01)[0]
    if len(nz): s = s[max(0, nz[0] - int(.015 * sr)): nz[-1] + int(.05 * sr)]
    raw = s.copy()
    s = s * (10 ** (gain / 20))
    if np.abs(s).max() > .9: s = (np.tanh(s / .95) * .95).astype(np.float32)   # soft limiter: only the peaks of loud phrases
    n = min(len(s) // 2, int(.008 * sr)); ramp = np.linspace(0, 1, n, dtype=np.float32)
    s[:n] *= ramp; s[len(s) - n:] *= ramp[::-1]
    return s, sr, raw

def render(kokoro, text, voice, speed, default='NORMAL', qc=None, lang='hi'):
    """Whole voice line -> (samples, sr, segments, log).
    segments: [t0, t1, phrase, sentence index, style, pause after]; log: QC result per phrase (and every retry)."""
    sr, chunks, segs, log, t, sent = 24000, [], [], [], 0.0, 0
    for p in pieces(text, default):
        s, sr, raw = synth(kokoro, p['text'], p['style'], voice, speed, lang)
        if qc: s, entry = qc.check_and_fix(kokoro, p, s, raw, voice, speed, lang); entry['at'] = round(t, 3); log.append(entry)
        segs.append([round(t, 3), round(t + len(s) / sr, 3), p['text'], sent, p['style'], p['pause']])
        chunks += [s, np.zeros(int(p['pause'] * sr), np.float32)]
        t += len(s) / sr + p['pause']
        if p['ends']: sent += 1
    a = np.concatenate(chunks + [np.zeros(int(.06 * sr), np.float32)]) if chunks else np.zeros(1, np.float32)
    peak = np.abs(a).max()
    if peak > .98: a *= .98 / peak
    return a, sr, segs, log

def sentences(text):
    return [s for s in re.split(r'(?<=[।!?.])\s+', text.strip()) if s]

def caption_spans(sub, segs, at, dur, chunker):
    """Caption chunks timed to the voice, sentence by sentence when caption and voice have the same sentences."""
    out, subs = [], sentences(sub)
    n = (segs[-1][3] + 1) if segs else 0
    if segs and len(subs) == n:
        groups = [(min(s[0] for s in segs if s[3] == i), max(s[1] for s in segs if s[3] == i), subs[i]) for i in range(n)]
    else:
        groups = [(0.0, dur, sub)]
    for g0, g1, text in groups:
        parts = chunker(text); w = [len(p) + 6 for p in parts]; s = at + g0
        for p, x in zip(parts, w):
            d = (g1 - g0) * x / sum(w); out.append({'t0': round(s, 3), 't1': round(s + d, 3), 'text': p.strip(' —')}); s += d
    return out
