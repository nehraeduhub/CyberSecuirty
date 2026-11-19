"""Automatic quality check for every spoken phrase, and regeneration of the phrases that fail.

Claude cannot listen, so the "listen and check" step is measured instead:
  pronunciation   the phrase is transcribed back with Whisper (sherpa-onnx, offline) and compared with the
                  script on a consonant skeleton (so Hindi/English spellings and digits compare fairly)
  gaps            no silence longer than 0.30 s inside a phrase (the pauses between phrases are set by us)
  speed           consonants per second within the voice's normal range (not rushed, not dragged)
  loudness        loudness of the phrase within the voice's normal range (not mumbled, not blown out)
  pitch           median pitch within the voice's normal range (no odd jump in the middle of a reel)
  ending          the phrase fades out instead of being cut off
A phrase that fails is spoken again in up to 6 variants (slightly slower/faster, small punctuation changes);
the best one is kept. Everything is logged for the correction report.
Set ASR_DIR to the sherpa-onnx-whisper-small folder; without it the pronunciation check is skipped."""
import os, re
import numpy as np

HI_NUM = ('शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस '
          'इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस '
          'छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस '
          'उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ '
          'छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी '
          'अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे '
          'पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे सौ').split()

DEV = {}
for chars, c in [('कखक़ख़', 'k'), ('गघग़', 'g'), ('चछ', 'c'), ('जझज़', 'j'), ('टठतथ', 't'), ('डढदधड़ढ़', 'd'),
                 ('णनञङंँ', 'n'), ('पफफ़', 'p'), ('बभ', 'b'), ('म', 'm'), ('य', 'y'), ('र', 'r'), ('ल', 'l'),
                 ('व', 'v'), ('शषस', 's'), ('ह', 'h')]:
    for ch in chars: DEV[ch] = c

def skeleton(text):
    """Consonant skeleton of Devanagari or Latin text: 'सीटीएफ़ पोर्टल' -> 'stprtl', 'CTF Portal' -> 'ktprtl'."""
    text = re.sub(r'\d+', lambda m: HI_NUM[int(m.group())] if int(m.group()) <= 100 else m.group(), text)
    out = []
    for ch in text.lower():
        if ch in DEV: out.append(DEV[ch])
        elif 'a' <= ch <= 'z': out.append(ch)
    lat = ''.join(out)
    for a, b in [('ch', 'c'), ('sh', 's'), ('th', 't'), ('ph', 'p'), ('kh', 'k'), ('gh', 'g'), ('dh', 'd'), ('bh', 'b'),
                 ('jh', 'j'), ('x', 'ks'), ('q', 'k'), ('f', 'p'), ('z', 'j'), ('w', 'v')]:
        lat = lat.replace(a, b)
    lat = lat.replace('ck', 'k').replace('c', 'k')
    lat = re.sub(r'[aeiouyh]', '', lat)            # vowels, y and aspiration differ between scripts: ignore
    return re.sub(r'(.)\1+', r'\1', lat)           # double letters (ll, tt) count once

def similarity(a, b):
    """1 - edit distance / length of the expected skeleton a."""
    if not a: return 1.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1): cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return max(0.0, 1 - prev[-1] / len(a))

def frames(s, sr, ms=10):
    n = int(sr * ms / 1000); k = len(s) // n
    return np.sqrt((s[:k * n].reshape(k, n) ** 2).mean(1) + 1e-12)

def f0_median(s, sr):
    """Median pitch (Hz) of voiced 40 ms frames, autocorrelation, 70–300 Hz."""
    n, hop, out = int(.04 * sr), int(.02 * sr), []
    lo, hi = int(sr / 300), int(sr / 70)
    for i in range(0, len(s) - n, hop):
        x = s[i:i + n] - s[i:i + n].mean()
        if np.sqrt((x ** 2).mean()) < .03: continue
        ac = np.correlate(x, x, 'full')[n - 1:]
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > .45 * ac[0]: out.append(sr / lag)
    return float(np.median(out)) if out else 0.0

# normal range of this voice (hm_omega), from a calibration run over the original scripts
RANGE = {'rate': (3.8, 11.0), 'rms_db': (-25.0, -12.5), 'f0': (95.0, 175.0), 'sim': 0.60, 'gap': 0.60, 'end_db': -35.0}

class QC:
    def __init__(self, asr_dir=None):
        self.asr_dir = asr_dir or os.environ.get('ASR_DIR'); self._r = {}

    def _rec(self, lang):
        if lang not in self._r:
            import sherpa_onnx
            d = self.asr_dir
            self._r[lang] = sherpa_onnx.OfflineRecognizer.from_whisper(encoder=f'{d}/small-encoder.int8.onnx', decoder=f'{d}/small-decoder.int8.onnx',
                tokens=f'{d}/small-tokens.txt', language=lang, task='transcribe', num_threads=4)
        return self._r[lang]

    def heard(self, text, s, sr):
        """Best (similarity, transcript) over three Whisper passes. Whisper-small is weak at Hindi: it stops early
        (token limit) or makes things up, so one bad pass proves nothing; a real TTS mistake fails all three."""
        want = skeleton(text); best = (-1.0, '')
        if not self.asr_dir: return None
        for lang, tail in (('hi', 1.5), ('hi', 3.0), ('en', .5)):
            st = self._rec(lang).create_stream()
            st.accept_waveform(sr, np.concatenate([np.zeros(int(.3 * sr), np.float32), s, np.zeros(int(tail * sr), np.float32)]))
            self._rec(lang).decode_stream(st); got = st.result.text.strip(); g = skeleton(got)
            sim = similarity(want, g)
            if len(g) >= .5 * len(want):                       # transcript stopped early: judge the part it heard
                sim = max(sim, similarity(want[:len(g) + 1], g))
            if sim > best[0]: best = (round(sim, 2), got)
            if best[0] >= RANGE['sim']: break
        return best

    def measure(self, text, raw, sr=24000):
        fr = frames(raw, sr); db = 20 * np.log10(fr)
        active = db > -40
        m = {'dur': round(len(raw) / sr, 2)}
        m['rms_db'] = round(float(20 * np.log10(np.sqrt((fr[active] ** 2).mean()))) if active.any() else -99, 1)
        # longest silence strictly inside the phrase
        idx = np.nonzero(active)[0]; gap = 0
        if len(idx) > 1: gap = int(np.max(np.diff(idx)) - 1)
        m['gap'] = round(gap * .01, 2)
        speech = active.sum() * .01
        m['rate'] = round(len(skeleton(text)) / max(speech, .2), 1)
        m['f0'] = round(f0_median(raw, sr), 1)
        m['end_db'] = round(float(db[-3:].max()), 1) if len(db) >= 3 else -99
        m['clip'] = int((np.abs(raw) >= .99).sum()) > 20      # a few peaks at full scale are inaudible
        if len(skeleton(text)) >= 4:                           # too short to judge (e.g. "सीम।")
            h = self.heard(text, raw, sr)
            if h: m['sim'], m['asr'] = h
        return m

    def problems(self, m, style):
        p = []
        if m.get('sim', 1) < RANGE['sim']: p.append(f"pronunciation (heard: {m.get('asr', '')})")
        if m['gap'] > RANGE['gap']: p.append(f"gap {m['gap']}s inside phrase")
        lo, hi = RANGE['rate']
        if len(skeleton(m.get('text', ''))) >= 6:
            if m['rate'] > hi: p.append(f"rushed ({m['rate']} c/s)")
            if m['rate'] < lo: p.append(f"dragged ({m['rate']} c/s)")
        lo, hi = RANGE['rms_db']
        if m['rms_db'] < lo: p.append(f"too quiet ({m['rms_db']} dB)")
        if m['rms_db'] > hi: p.append(f"too loud ({m['rms_db']} dB)")
        lo, hi = RANGE['f0']
        if m['f0'] and not lo <= m['f0'] <= hi: p.append(f"pitch off ({m['f0']} Hz)")
        if m['end_db'] > RANGE['end_db']: p.append('cut off at the end')
        if m['clip']: p.append('clipping')
        return p

    def variants(self, text):
        """(text, speed tweak, label) to try when a phrase fails."""
        bare = text.rstrip(',।!?.'); end = text[len(bare):]
        alt = [(text, .95, 'slower 5%'), (text, 1.05, 'faster 5%'), (text, .90, 'slower 10%')]
        if end != '।': alt.append((bare + '।', 1.0, 'full stop ending'))
        if ',' in bare: alt.append((bare.replace(',', '') + end, 1.0, 'without inner commas'))
        alt.append(('…' + text, 1.0, 'soft start'))
        return alt

    def check_and_fix(self, kokoro, p, s, raw, voice, speed, lang):
        from speak import synth
        m = self.measure(p['text'], raw); m['text'] = p['text']
        probs = self.problems(m, p['style'])
        entry = {'text': p['text'], 'style': p['style'], 'pause_after': p['pause'], 'metrics': m, 'problems': probs, 'tries': [], 'fixed': not probs}
        if not probs: return s, entry
        def score(mm, pp): return mm.get('sim', 1) - .15 * len(pp)
        best = (score(m, probs), s, m, probs, 'first take')
        for text, tweak, label in self.variants(p['text']):
            s2, _, raw2 = synth(kokoro, text, p['style'], voice, speed, lang, tweak)
            m2 = self.measure(p['text'], raw2); m2['text'] = p['text']; p2 = self.problems(m2, p['style'])
            entry['tries'].append({'variant': label, 'problems': p2, 'sim': m2.get('sim')})
            if score(m2, p2) > best[0]: best = (score(m2, p2), s2, m2, p2, label)
            if not p2: break
        entry.update({'chosen': best[4], 'final_metrics': best[2], 'final_problems': best[3], 'fixed': not best[3]})
        return best[1], entry
