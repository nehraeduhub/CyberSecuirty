"""Hindi male voice-over per scene with Kokoro TTS (offline, voice hm_omega), following the delivery marks
(pauses, LOUD, polite) described in tools/speak.py.
Writes <work>/vo-<scene>.wav (24 kHz mono), <work>/vo.json (each clip's length) and <work>/vo-segs.json
(when each phrase starts and ends, for caption timing).
Usage: python3 -I tools/voice.py <topics.json> <num> <work dir> [voice] [speed]
Model files (kokoro-v1.0.onnx, voices-v1.0.bin) are looked up in $KOKORO_DIR."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soundfile as sf
from kokoro_onnx import Kokoro
from speak import render
import voice_qc
from voice_qc import QC

topics, num, work = sys.argv[1], int(sys.argv[2]), sys.argv[3]
voice = sys.argv[4] if len(sys.argv) > 4 else 'hm_omega'
speed = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
if voice.startswith('hf'): voice_qc.RANGE['f0'] = (150.0, 300.0)   # female voices sit higher than hm_omega's calibrated range
t = next(x for x in json.load(open(topics, encoding='utf-8')) if x['num'] == num)
if 'vo' not in t: sys.exit(f'topic {num}: no voice-over script in scripts.json yet')
d = os.environ.get('KOKORO_DIR', '.')
k = Kokoro(os.path.join(d, 'kokoro-v1.0.onnx'), os.path.join(d, 'voices-v1.0.bin'))
os.makedirs(work, exist_ok=True)
meta, segs, qclog = {}, {}, {}
qc = QC()
for scene, text in t['vo'].items():
    s, sr, segs[scene], qclog[scene] = render(k, text, voice, speed, t.get('voStyle', {}).get(scene, 'NORMAL'), qc)
    sf.write(os.path.join(work, f'vo-{scene}.wav'), s, sr)
    meta[scene] = round(len(s) / sr, 3)
    print(scene, meta[scene], 's')
json.dump(meta, open(os.path.join(work, 'vo.json'), 'w'))
json.dump(segs, open(os.path.join(work, 'vo-segs.json'), 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(qclog, open(os.path.join(work, 'vo-qc.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
