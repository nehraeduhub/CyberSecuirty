"""Turn the Kokoro voice into the owner's own voice (kNN-VC: WavLM features matched against the owner's recording,
re-synthesised with HiFi-GAN). Pronunciation, pauses and delivery stay as generated; only the voice changes.
Model weights are loaded from local files with torch.load(weights_only=True).
Usage: python3 convert.py <owner reference audio> <out dir> <in.wav> [in2.wav ...]  -> <out dir>/<same name>.wav (16 kHz)"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'src'))
import soundfile as sf, torch, torchaudio
from wavlm.WavLM import WavLM, WavLMConfig
from hifigan.models import Generator as HiFiGAN
from hifigan.utils import AttrDict
from matcher import KNeighborsVC

torch.set_num_threads(4)


def load_models():
    h = AttrDict(json.load(open(os.path.join(HERE, 'src', 'hifigan', 'config_v1_wavlm.json'))))
    gen = HiFiGAN(h)
    gen.load_state_dict(torch.load(os.path.join(HERE, 'prematch_g_02500000.pt'), map_location='cpu', weights_only=True)['generator'])
    gen.eval(); gen.remove_weight_norm()
    ck = torch.load(os.path.join(HERE, 'WavLM-Large.pt'), map_location='cpu', weights_only=True)
    wavlm = WavLM(WavLMConfig(ck['cfg'])); wavlm.load_state_dict(ck['model']); wavlm.eval()
    return KNeighborsVC(wavlm, gen, h, 'cpu')


def load16(path):
    a, sr = sf.read(path, dtype='float32')
    if a.ndim > 1: a = a.mean(1)
    t = torch.from_numpy(a)[None]
    return torchaudio.functional.resample(t, sr, 16000) if sr != 16000 else t


if __name__ == '__main__':
    ref, out, ins = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(out, exist_ok=True)
    vc = load_models()
    t0 = time.time(); r = load16(ref); step = 16000 * 6
    # matching set: the owner's speech in ~6 s pieces, silence trimmed, so pauses do not count as "voice"
    pool = vc.get_matching_set([r[:, i:i + step] for i in range(0, r.shape[1], step) if r.shape[1] - i > 16000])
    print('matching frames', pool.shape[0], f'({pool.shape[0] / 50:.1f} s of voice)', round(time.time() - t0, 1), 's')
    for f in ins:
        t0 = time.time()
        y = vc.match(vc.get_features(load16(f)), pool, topk=4).cpu().numpy()
        sf.write(os.path.join(out, os.path.basename(f).rsplit('.', 1)[0] + '.wav'), y, 16000)
        print(os.path.basename(f), f'{len(y) / 16000:.1f} s audio in {time.time() - t0:.1f} s')
