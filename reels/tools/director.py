"""Voice Director: script analysis -> voice directions -> synthesis -> automatic QC -> targeted re-generation.

Usage
  python3 tools/director.py direct lines.json outdir [voice] [base_speed]
      writes outdir/<key>.wav per line, outdir/qc.json (directions, markers, QC, corrections),
      prints {"key": seconds} JSON (same contract as voice.py)
  python3 tools/director.py tempo outdir factor          # speed every clip up/down (pitch kept), prints durations
  python3 tools/director.py track audio.json out.mp3     # voice-only track placed on the reel timeline

How directions become sound (Piper has no emotion tags, so each direction maps to real controls):
  pace -> length_scale, expressiveness -> noise_scale/noise_w, pitch -> rubberband pitch shift,
  intensity -> gain (+ gentle compression, never shouting), pauses -> real silences between phrases,
  [EMPHASIZE] -> short lead-in pause + stand-alone phrase with slower pace, +pitch, +gain.
QC judge: Whisper large-v3-turbo (offline) transcribes every candidate; it is compared with the script
(character error rate), plus speaking rate, unplanned gaps, clipping and loudness. Each line gets
3 candidates; lines that still fail get a correction pass (slower + clearer) until they pass or
attempts run out. Only failing lines are regenerated.
"""
import json, os, re, subprocess, sys, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 22050

# ---------------------------------------------------------------- directions
STYLE = {  # ls = length_scale multiplier, ns/nw = expressiveness, pitch in semitones, gain in dB
    'NORMAL':      dict(ls=1.00, ns=0.45, nw=0.65, pitch=0.0, gain=0.0),
    'WARNING':     dict(ls=0.97, ns=0.55, nw=0.70, pitch=0.7, gain=1.5),
    'SERIOUS':     dict(ls=1.02, ns=0.40, nw=0.60, pitch=-0.6, gain=0.5),
    'CALM':        dict(ls=1.03, ns=0.38, nw=0.58, pitch=-0.3, gain=-0.5),
    'POLITE':      dict(ns=0.42, pitch=0.3, gain=-0.5),
    'CONFIDENT':   dict(ns=0.50, gain=1.0),
    'EXCITED':     dict(ls=0.96, ns=0.60, nw=0.75, pitch=1.0, gain=1.5),
    'QUESTIONING': dict(pitch=0.5),
    'SLOW':        dict(ls_mul=1.07),
    'LOUD':        dict(gain_add=2.0),
    'SOFT':        dict(gain_add=-2.0),
}
PAUSE = {'SHORT': 0.20, 'LONG': 0.45, 'EMPH': 0.10}

SECTION = [  # key regex -> styles
    (r'^hook$', ['WARNING', 'LOUD']),
    (r'^intro$', ['POLITE', 'CONFIDENT']),
    (r'^how\.3$', ['SERIOUS', 'SLOW']),
    (r'^how\.\d$', ['SERIOUS']),
    (r'^flags\.title$', ['WARNING']),
    (r'^flags\.\d$', ['WARNING']),
    (r'^tips\.title$', ['CONFIDENT']),
    (r'^tips\.\d$', ['CALM', 'POLITE', 'SLOW']),
    (r'^set\.title$', ['POLITE', 'CALM']),
    (r'^set\.\d$', ['CALM', 'POLITE', 'SLOW']),
    (r'^help$', ['SERIOUS', 'SLOW']),
    (r'^outro$', ['CONFIDENT']),
]
# words worth stressing, highest priority first (spoken forms)
EMPH = ['उन्नीस सौ तीस', 'कभी नहीं', 'कभी भी', 'कभी न', 'तुरंत', 'नकली', 'सिर्फ', 'अनजान', 'बंद', 'धमकी',
        'ओ टी पी', 'पिन', 'ए पी के', 'ब्लॉक', 'डिलीट', 'फर्जी', 'हैक', 'साइबर क्राइम नहीं होने देंगे']


def styles_for(key):
    for rx, st in SECTION:
        if re.match(rx, key):
            return list(st)
    return ['NORMAL']


def combine(styles, base_ls):
    p = dict(STYLE['NORMAL']); mul = 1.0; gadd = 0.0
    for s in styles:
        d = STYLE[s]
        for k in ('ls', 'ns', 'nw', 'pitch', 'gain'):
            if k in d: p[k] = d[k]
        mul *= d.get('ls_mul', 1.0); gadd += d.get('gain_add', 0.0)
    p['ls'] = round(p['ls'] * mul * base_ls, 3); p['gain'] = max(-3, min(3.5, p['gain'] + gadd))
    return p


def plan_line(key, text, base_ls):
    """Split a line into phrases with pauses, pick the emphasis, attach per-phrase styles."""
    styles = styles_for(key)
    sentences = [s.strip() for s in re.findall(r'[^।!?]+[।!?]?', text) if s.strip()]
    chunks = []
    emph_done = False
    for si, sent in enumerate(sentences):
        st = list(styles)
        if sent.endswith('?'): st.append('QUESTIONING')
        if key == 'outro':
            st = ['CONFIDENT', 'SLOW', 'LOUD'] if si == 0 else (['CONFIDENT', 'LOUD'] if 'जय हिंद' in sent else ['EXCITED'])
        if key == 'intro' and si == 0: st = ['POLITE', 'EXCITED']
        phrases = [p.strip(' …') for p in re.split(r'(?<=[,…])', sent) if p.strip(' …')]
        for pi, ph in enumerate(phrases):
            pause_after = PAUSE['SHORT'] if pi < len(phrases) - 1 else (PAUSE['LONG'] if si < len(sentences) - 1 else 0.0)
            kw = None
            if not emph_done:
                kw = next((w for w in EMPH if w in ph), None)
            if kw:
                emph_done = True
                i = ph.index(kw)
                before = ph[:i].strip(' ,')
                if len(before.split()) >= 2:   # stress needs a lead-in, otherwise keep phrase whole
                    chunks.append(dict(text=before, styles=st, pause_after=PAUSE['EMPH']))
                    chunks.append(dict(text=ph[i:], styles=st, emph=kw, pause_after=pause_after))
                    continue
                chunks.append(dict(text=ph, styles=st, emph=kw, pause_after=pause_after))
                continue
            chunks.append(dict(text=ph, styles=st, pause_after=pause_after))
    for c in chunks:
        p = combine(c['styles'], base_ls)
        if c.get('emph'):  # stress: a touch slower, higher and louder (natural, not exaggerated)
            p['ls'] = round(p['ls'] * 1.06, 3); p['pitch'] += 0.6; p['gain'] = min(3.5, p['gain'] + 1.5)
        c['params'] = p
    return chunks


def markers(chunks):
    out = []
    for c in chunks:
        tag = ''.join(f'[{s}]' for s in c['styles'])
        t = c['text']
        if c.get('emph'): t = t.replace(c['emph'], f'[EMPHASIZE]{c["emph"]}[/EMPHASIZE]', 1)
        out.append(f'{tag} {t}')
        if c['pause_after'] >= PAUSE['LONG']: out.append('[LONG PAUSE]')
        elif c['pause_after'] > PAUSE['EMPH']: out.append('[SHORT PAUSE]')
    return ' '.join(out)


# ---------------------------------------------------------------- QC judge
ONES = ('शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस '
        'सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस '
        'सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर '
        'सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी '
        'नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे').split()


def num(n):
    if n < 100: return ONES[n]
    parts = []
    for div, w in ((10**7, 'करोड़'), (10**5, 'लाख'), (1000, 'हज़ार')):
        q, n = divmod(n, div)
        if q: parts.append(num(q) + ' ' + w)
    q, n = divmod(n, 100)
    if q: parts.append(ONES[q] + ' सौ')
    if n: parts.append(ONES[n])
    return ' '.join(parts)


# English words the ASR sometimes writes in Latin script -> Devanagari (so they are not counted as errors)
LEX = {'cybersafe': 'साइबर सेफ', 'cyber': 'साइबर', 'safe': 'सेफ', 'crime': 'क्राइम', 'arrest': 'अरेस्ट', 'digital': 'डिजिटल',
       'police': 'पुलिस', 'video': 'वीडियो', 'call': 'कॉल', 'jhunjhunu': 'झुंझुनूं', 'follow': 'फॉलो', 'share': 'शेयर', 'setting': 'सेटिंग'}
LETTERS = {}


def norm(s):
    s = s.lower()
    s = s.replace('1930', ' उन्नीस सौ तीस ')
    s = re.sub(r'₹\s?([\d,]+)', lambda m: num(int(m.group(1).replace(',', ''))) + ' रुपये', s)
    s = re.sub(r'\d[\d,]*', lambda m: ' ' + num(int(m.group(0).replace(',', ''))) + ' ', s)
    for en, hi in LEX.items(): s = s.replace(en, hi)
    s = re.sub(r'[a-z]', lambda m: LETTERS.get(m.group(0).upper(), ''), s)
    # spelling-equivalent forms count as the same sound: nasal marks, nukta, ये/ए, ई/इ, ू/ु length
    s = s.replace('ँ', '').replace('ं', '').replace('़', '').replace('ॉ', 'ो').replace('ऑ', 'ओ')
    s = s.replace('ये', 'ए').replace('यी', 'ई').replace('ी', 'ि').replace('ई', 'इ').replace('ू', 'ु').replace('ऊ', 'उ').replace('्', '')
    return re.sub(r'[^ऀ-ॿ]', '', s)


def cer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    if not r: return 0.0
    prev = list(range(len(h) + 1))
    for i, a in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, b in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a != b))
        prev = cur
    return prev[-1] / len(r)


_ASR = None


def asr(path):
    global _ASR
    if _ASR is None:
        os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
        from faster_whisper import WhisperModel
        _ASR = WhisperModel('large-v3-turbo', device='cpu', compute_type='int8', cpu_threads=int(os.environ.get('ASR_THREADS', '4')))
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-f', 's16le', '-ac', '1', '-ar', '16000', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, '<i2').astype(np.float32) / 32768
    segs, _ = _ASR.transcribe(a, language='hi', beam_size=5, condition_on_previous_text=False)
    return ' '.join(s.text.strip() for s in segs)


def read(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32768, w.getframerate()


def acoustic(path, planned_gaps):
    a, sr = read(path)
    win = int(.02 * sr); n = len(a) // win
    rms = np.sqrt((a[:n * win].reshape(n, win) ** 2).mean(1) + 1e-12)
    thr = max(rms.max() * 0.03, 1e-4)
    silent = rms < thr
    gaps, run = [], 0
    for s in silent:
        if s: run += 1
        else:
            if run: gaps.append(run * win / sr)
            run = 0
    long_gaps = [g for g in gaps if g > 0.65]
    unplanned = max(0, len(long_gaps) - planned_gaps)
    voiced = (~silent).sum() * win / sr
    return dict(dur=round(len(a) / sr, 2), voiced=round(voiced, 2), clip=bool(np.abs(a).max() > 0.995), unplanned_gaps=unplanned)


# ---------------------------------------------------------------- synthesis
# Pronunciation dictionary: spellings that make Piper say the word correctly (found by A/B tests
# scored with the ASR judge). Applied only to TTS input; QC still compares against the real word.
PRON = {'क्राइम': 'क्राईम'}
_PV = None


def synth_chunk(text, p, out):
    from piper import SynthesisConfig
    raw = out + '.raw.wav'
    with wave.open(raw, 'wb') as w:
        for k, v in PRON.items(): text = text.replace(k, v)
        _PV.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=p['ls'], noise_scale=p['ns'], noise_w_scale=p['nw']))
    af = ['silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02',
          'areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.04,areverse']
    if abs(p['pitch']) > 0.05: af.append(f'rubberband=pitch={2 ** (p["pitch"] / 12):.4f}:formant=preserved')
    af.append(f'volume={p["gain"]:.2f}dB')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw, '-af', ','.join(af), '-ar', '44100', '-ac', '1', out], check=True)
    os.remove(raw)


def build_line(chunks, out, tag):
    parts = []
    for i, c in enumerate(chunks):
        cp = f'{out}.{tag}.{i}.wav'
        synth_chunk(c['text'], c['params'], cp)
        a, _ = read(cp); os.remove(cp)
        fade = min(len(a) // 4, int(.008 * 44100))
        if fade: a[:fade] *= np.linspace(0, 1, fade); a[-fade:] *= np.linspace(1, 0, fade)
        parts.append(a); parts.append(np.zeros(int(c['pause_after'] * 44100), np.float32))
    a = np.concatenate(parts)
    tmp = f'{out}.{tag}.cat.wav'
    with wave.open(tmp, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype('<i2').tobytes())
    # one shared polish chain for every line = consistent identity; relative style gains survive
    # because each line is normalised first and the style gain is re-applied after.
    gain = np.mean([c['params']['gain'] for c in chunks])
    af = ('highpass=f=70,equalizer=f=180:t=q:w=1:g=3,equalizer=f=3000:t=q:w=1.2:g=-1,treble=g=-3:f=6500,'
          'acompressor=threshold=-22dB:ratio=2.2:attack=15:release=250:makeup=2,aecho=0.8:0.4:35:0.05,'
          f'loudnorm=I=-16:TP=-2:LRA=9,volume={gain:.2f}dB,alimiter=limit=0.89:level=disabled')
    final = f'{out}.{tag}.wav'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp, '-af', af, '-ar', '44100', '-ac', '1', final], check=True)
    os.remove(tmp)
    return final


def evaluate(path, line, chunks):
    hyp = asr(path)
    e = cer(line['say'], hyp)
    ac = acoustic(path, sum(1 for c in chunks if c['pause_after'] >= 0.4))
    syl = len(norm(line['say'])) / max(ac['voiced'], .3)  # devanagari chars per voiced second
    issues = []
    if e > 0.15: issues.append(f'pronunciation/words (CER {e:.2f})')
    if ac['unplanned_gaps']: issues.append(f'{ac["unplanned_gaps"]} unplanned gap(s)')
    if syl > 17.5: issues.append(f'rushed ({syl:.1f} chars/s)')
    if ac['clip']: issues.append('clipping')
    score = e + 0.05 * ac['unplanned_gaps'] + max(0, syl - 17.5) * 0.02 + (0.05 if ac['clip'] else 0)
    return dict(hyp=hyp, cer=round(e, 3), rate=round(syl, 1), score=round(score, 3), issues=issues, **ac)


def direct(lines_file, out, voice='rohan', base=0.93):
    global _PV
    data = json.load(open(lines_file))
    lines = data['lines'] if isinstance(data, dict) else data
    if isinstance(data, dict):
        LEX.update({k.lower(): v for k, v in data.get('lex', {}).items()}); LETTERS.update(data.get('letters', {}))
    from piper import PiperVoice
    _PV = PiperVoice.load(os.path.join(ROOT, 'models', f'hi_IN-{voice}-medium.onnx'))
    os.makedirs(out, exist_ok=True)
    K = int(os.environ.get('CANDIDATES', '3')); MAX_FIX = int(os.environ.get('FIX_ROUNDS', '2'))
    qc, durs = [], {}
    for line in lines:
        key = line['key']
        chunks = plan_line(key, line['say'], base)
        rec = dict(key=key, text=line.get('text') or '', say=line['say'], styles=styles_for(key),
                   markers=markers(chunks), chunks=[dict(text=c['text'], emph=c.get('emph'), pause_after=c['pause_after'], params=c['params']) for c in chunks],
                   attempts=[], corrections=[])
        best = None
        rounds = [('initial', chunks)]
        for r in range(MAX_FIX + 1):
            label, ch = rounds[-1]
            for k in range(K):
                path = build_line(ch, os.path.join(out, key), f'{label}{k}')
                ev = evaluate(path, line, ch); ev['label'] = f'{label}#{k + 1}'; ev['path'] = path
                rec['attempts'].append({x: ev[x] for x in ('label', 'cer', 'rate', 'score', 'issues', 'hyp', 'dur')})
                if best is None or ev['score'] < best['score']: best = ev
                if not ev['issues'] and k >= 0 and ev['cer'] <= 0.08: break   # clean pass: stop early
            if not best['issues']: break
            if r == MAX_FIX: break
            # correction: clearer, slightly slower, steadier; keep the same voice identity
            fix = [dict(c, params=dict(c['params'], ls=round(c['params']['ls'] * 1.06, 3), ns=max(0.33, c['params']['ns'] - 0.07),
                                       nw=max(0.5, c['params']['nw'] - 0.05))) for c in ch]
            rec['corrections'].append(dict(round=r + 1, problem='; '.join(best['issues']), action='slower (+6%), steadier intonation, regenerated this line only'))
            rounds.append((f'fix{r + 1}_', fix))
        final = os.path.join(out, key + '.wav')
        os.replace(best['path'], final)
        for f in os.listdir(out):
            if f.startswith(key + '.') and f.endswith('.wav') and os.path.join(out, f) != final: os.remove(os.path.join(out, f))
        rec['chosen'] = best['label']; rec['final'] = {x: best[x] for x in ('cer', 'rate', 'issues', 'hyp', 'dur')}
        rec['status'] = 'PASS' if not best['issues'] else 'REVIEW'
        durs[key] = read(final)[0].size / 44100
        qc.append(rec)
        print(f'{key:12s} {rec["status"]:6s} cer={best["cer"]:.2f} rate={best["rate"]} tries={len(rec["attempts"])}', file=sys.stderr)
    json.dump(qc, open(os.path.join(out, 'qc.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: round(v, 3) for k, v in durs.items()}))


def tempo(out, factor):
    durs = {}
    for f in sorted(os.listdir(out)):
        if not f.endswith('.wav'): continue
        p = os.path.join(out, f); t = p + '.t.wav'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', p, '-af', f'rubberband=tempo={factor}', t], check=True)
        os.replace(t, p); durs[f[:-4]] = round(read(p)[0].size / 44100, 3)
    print(json.dumps(durs))


def track(audio_json, out):
    d = json.load(open(audio_json))
    n = int((d['duration'] + .5) * 44100); buf = np.zeros(n, np.float32)
    for v in d['voice']:
        a, _ = read(v['file']); i = int(v['t'] * 44100); j = min(n, i + len(a)); buf[i:j] += a[:j - i]
    tmp = out + '.wav'
    with wave.open(tmp, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((np.clip(buf, -1, 1) * 32767).astype('<i2').tobytes())
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp, '-c:a', 'libmp3lame', '-b:a', '192k', out], check=True)
    os.remove(tmp)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'direct': direct(sys.argv[2], sys.argv[3], *(sys.argv[4:5] or ['rohan']), float(sys.argv[5]) if len(sys.argv) > 5 else 0.93)
    elif cmd == 'tempo': tempo(sys.argv[2], float(sys.argv[3]))
    elif cmd == 'track': track(sys.argv[2], sys.argv[3])
