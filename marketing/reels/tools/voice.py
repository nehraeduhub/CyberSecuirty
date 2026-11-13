"""Hindi male voice-over per scene with Kokoro TTS (offline, voice hm_omega).
Writes <work>/vo-<scene>.wav (24 kHz mono) and <work>/vo.json with each clip's length.
Usage: python3 -I tools/voice.py <topics.json> <num> <work dir> [voice] [speed]
Model files (kokoro-v1.0.onnx, voices-v1.0.bin) are looked up in $KOKORO_DIR."""
import json, os, sys
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro

topics, num, work = sys.argv[1], int(sys.argv[2]), sys.argv[3]
voice = sys.argv[4] if len(sys.argv) > 4 else 'hm_omega'
speed = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
t = next(x for x in json.load(open(topics, encoding='utf-8')) if x['num'] == num)
if 'vo' not in t: sys.exit(f'topic {num}: no voice-over script in scripts.json yet')
d = os.environ.get('KOKORO_DIR', '.')
k = Kokoro(os.path.join(d, 'kokoro-v1.0.onnx'), os.path.join(d, 'voices-v1.0.bin'))
os.makedirs(work, exist_ok=True)
meta = {}
for scene, text in t['vo'].items():
    s, sr = k.create(text, voice=voice, speed=speed, lang='hi')
    s = np.asarray(s, dtype=np.float32)
    nz = np.nonzero(np.abs(s) > 0.01)[0]               # trim silence at both ends
    s = s[max(0, nz[0] - 600): nz[-1] + 2400] if len(nz) else s
    sf.write(os.path.join(work, f'vo-{scene}.wav'), s, sr)
    meta[scene] = round(len(s) / sr, 3)
    print(scene, meta[scene], 's')
json.dump(meta, open(os.path.join(work, 'vo.json'), 'w'))
