"""VAPT reel voice-over: every scene of script.json spoken by its host (Kokoro, with the reels' voice direction and QC).
Usage: python3 -I voice.py <script.json> <work dir>   (env KOKORO_DIR, ASR_DIR, SPEED default 1.0)
Writes <work>/voice.wav (24 kHz) and <work>/timeline.json: scene start/end, sentence spans, total length."""
import json, os, sys
import numpy as np, soundfile as sf
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'reels', 'tools'))
from speak import render
import voice_qc
from voice_qc import QC
from kokoro_onnx import Kokoro

S = json.load(open(sys.argv[1], encoding='utf-8')); W = sys.argv[2]; os.makedirs(W, exist_ok=True)
SPEED = float(os.environ.get('SPEED', '1.0'))
d = os.environ['KOKORO_DIR']; k = Kokoro(os.path.join(d, 'kokoro-v1.0.onnx'), os.path.join(d, 'voices-v1.0.bin'))
qc = QC()
LEAD, GAP, TAIL = 0.35, 0.18, 2.4          # silence before the first line, between scenes, end card after the last
sr, out, scenes, t = 24000, [np.zeros(int(LEAD * 24000), np.float32)], [], LEAD
for sc in S['scenes']:
    voice_qc.RANGE['f0'] = (150.0, 300.0) if sc['voice'].startswith('hf') else (95.0, 175.0)
    a, sr, segs, log = render(k, sc['vo'], sc['voice'], SPEED, sc['style'], qc)
    bad = [e for e in log if e and e.get('problems') and not e.get('fixed')]
    print(f"{sc['id']:8s} {sc['voice']} {len(a) / sr:5.2f}s", 'QC: ' + '; '.join(p for e in bad for p in e['problems']) if bad else 'QC ok', flush=True)
    dur = len(a) / sr
    scenes.append({'id': sc['id'], 'voice': sc['voice'], 'cap': sc['cap'], 'start': round(t, 3), 'end': round(t + dur, 3),
                   'sents': [[round(t + s[0], 3), round(t + s[1], 3), s[2]] for s in segs]})
    out += [a, np.zeros(int(GAP * sr), np.float32)]; t += dur + GAP
total = t + TAIL
v = np.concatenate(out); v = np.concatenate([v, np.zeros(int(total * sr) - len(v), np.float32)])
sf.write(os.path.join(W, 'voice.wav'), v, sr, subtype='PCM_16')
# scene i lasts until scene i+1 starts; the last one holds through the end card
for i, s in enumerate(scenes): s['until'] = scenes[i + 1]['start'] if i + 1 < len(scenes) else round(total, 3)
json.dump({'total': round(total, 3), 'byline': S['byline'], 'scenes': scenes}, open(os.path.join(W, 'timeline.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('total', round(total, 2), 's')
