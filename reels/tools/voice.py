"""Offline Hindi voiceover with Piper (neural TTS) + broadcast-style polish.

Usage: python3 tools/voice.py lines.json outdir [voice] [speed]
  lines.json = [{"key": "hook", "say": "..."}]
  voice      = rohan (male, default) | pratham (male) | priyamvada (female)
  speed      = length_scale, <1 is faster (default 0.92)
Writes outdir/<key>.wav (44.1k, processed) and prints {"key": seconds} JSON.
Models: reels/models/hi_IN-<voice>-medium.onnx (see README for download).
"""
import json, os, subprocess, sys, wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    lines = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else 'rohan'
    speed = float(sys.argv[4]) if len(sys.argv) > 4 else 0.92
    from piper import PiperVoice, SynthesisConfig
    model = os.path.join(ROOT, 'models', f'hi_IN-{voice}-medium.onnx')
    pv = PiperVoice.load(model)
    cfg = SynthesisConfig(length_scale=speed, noise_scale=0.6, noise_w_scale=0.75)
    os.makedirs(out, exist_ok=True)
    durs = {}
    for ln in lines:
        raw = os.path.join(out, ln['key'] + '.raw.wav')
        with wave.open(raw, 'wb') as w:
            pv.synthesize_wav(ln['say'], w, syn_config=cfg)
        fin = os.path.join(out, ln['key'] + '.wav')
        # radio-voice chain: trim silences, de-rumble, presence EQ, compression, warmth, loudness
        af = ('silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,'
              'areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,'
              'highpass=f=80,equalizer=f=200:t=q:w=1:g=2,equalizer=f=3200:t=q:w=1.2:g=3,'
              'equalizer=f=7500:t=q:w=1:g=-2,acompressor=threshold=-20dB:ratio=3.5:attack=5:release=120:makeup=3,'
              'aecho=0.8:0.5:28:0.08,aresample=44100,loudnorm=I=-15:TP=-1.5:LRA=7')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw, '-af', af, '-ac', '1', '-ar', '44100', fin], check=True)
        os.remove(raw)
        with wave.open(fin) as w:
            durs[ln['key']] = round(w.getnframes() / w.getframerate(), 3)
    print(json.dumps(durs))


if __name__ == '__main__':
    main()
