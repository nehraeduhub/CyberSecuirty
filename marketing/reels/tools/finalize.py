"""Final reels in the owner's voice. For every reel in out/: the cloned voice track (clone/<name>.wav, made by
voice-clone-convert.py from work/.../voice-male.wav, or voiceover.wav for a one-host reel) is raised by +3 Hz (owner's choice), brought to the level the
Kokoro voice had, mixed with that reel's music + sound effects exactly as build.sh does, and put on the reel's video
(video untouched). Thumbnail: the reel's cover + brand strip (thumb_brand.py). Output: final/<name>.mp4 + <name>.jpg.
Then the whole reel (picture, voice, music) is played SPEED times faster (owner: 1.2x; voice pitch kept by rubberband).
Usage: python3 -I tools/finalize.py <reels dir> <owner photo> [name ...]      env SPEED (default 1.2)"""
import glob, json, os, re, subprocess, sys
R, PHOTO, only = sys.argv[1], sys.argv[2], set(sys.argv[3:])
PLAIN = os.environ.get('PLAIN') == '1'   # PLAIN=1: keep the built AI voices, no owner's voice
SPEED = float(os.environ.get('SPEED', '1.0'))
FIN = os.path.join(R, 'final'); os.makedirs(FIN, exist_ok=True)
run = lambda *a: subprocess.run(a, check=True, capture_output=True, text=True)

def f0(path):
    """Median pitch of the voiced parts (works with long silences, e.g. a host track that is quiet half the reel)."""
    import numpy as np, soundfile as sf
    sys.path.insert(0, os.path.join(R, 'tools')); from voice_qc import f0_median
    a, sr = sf.read(path, dtype='float32'); a = a.mean(1) if a.ndim > 1 else a
    return f0_median(a * (.5 / (np.abs(a).max() or 1)), sr)

def lufs(path, vol):
    err = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', path, '-af', f'volume={vol},ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float(re.findall(r'I:\s+(-?[0-9.]+) LUFS', err)[-1])

reels = []
for t in json.load(open(os.path.join(R, 'topics.json'), encoding='utf-8')):
    reels.append((t['name'], os.path.join(R, 'work', str(t['num'])), t['accent']))
for g in sorted(glob.glob(os.path.join(R, 'guides', '*.json'))):
    G = json.load(open(g, encoding='utf-8')); reels.append((G['name'], os.path.join(R, 'work', 'guide-' + G['name']), G.get('accent', '#ff9933')))
for name, W, accent in reels:
    if only and name not in only: continue
    clone, video, cover = os.path.join(R, 'clone', name + '.wav'), os.path.join(R, 'out', name, name + '.mp4'), os.path.join(R, 'out', name, name + '-thumbnail.jpg')
    if PLAIN:      # AI voices only (female hf_alpha + male hm_omega): the built reel is final as it is
        if not all(os.path.exists(p) for p in (video, cover)): print('skip (missing input)', name); continue
        run('cp', video, os.path.join(FIN, name + '.mp4'))
        run('python3', '-I', os.path.join(R, 'tools', 'thumb_brand.py'), cover, PHOTO, accent, os.path.join(FIN, name + '.jpg'))
        print('done', name, ' AI voices'); continue
    if not all(os.path.exists(p) for p in (clone, video, cover)): print('skip (missing input)', name); continue
    up = os.path.join(W, 'clone-up.wav'); hz = f0(clone)
    run('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', clone, '-af', f'rubberband=pitch={(hz + 3) / hz:.5f}:formant=preserved:pitchq=quality', up)
    male, female = os.path.join(W, 'voice-male.wav'), os.path.join(W, 'voice-female.wav')
    mixed = os.path.exists(female) and os.path.getsize(female) > 0 and lufs(female, 1.0) > -60
    gain = 10 ** ((lufs(male if mixed else os.path.join(W, 'voiceover.wav'), 2.0) - lufs(up, 1.0)) / 20)
    mix = os.path.join(W, 'mix-clone.wav')
    fin = ['-i', female] if mixed else []
    voc = (f'[2]aresample=48000,highpass=f=80,volume={gain:.3f}[cm];[3]aresample=48000,highpass=f=80,volume=2.0[fm];'
           '[cm][fm]amix=inputs=2:normalize=0:duration=longest,pan=stereo|c0=c0|c1=c0,apad[vo];' if mixed else
           f'[2]aresample=48000,highpass=f=80,volume={gain:.3f},pan=stereo|c0=c0|c1=c0,apad[vo];')
    run('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', os.path.join(W, 'music.wav'), '-i', os.path.join(W, 'sfx.wav'), '-i', up, *fin, '-filter_complex',
        voc + '[vo]asplit[vo1][sc];[0]volume=0.75[m];'
        '[m][sc]sidechaincompress=threshold=0.08:ratio=2:attack=30:release=450[md];[1]volume=0.45[fx];'
        f'[md][vo1][fx]amix=inputs=3:normalize=0:duration=first,{f'rubberband=tempo={SPEED}:pitchq=quality,' if SPEED != 1 else ''}loudnorm=I=-14:TP=-1.5:LRA=11[a]', '-map', '[a]', '-ar', '48000', '-ac', '2', mix)
    vcodec = ['-c:v', 'copy'] if SPEED == 1 else ['-vf', f'setpts=PTS/{SPEED},fps=30', '-c:v', 'libx264', '-profile:v', 'high', '-crf', '20', '-preset', 'medium', '-pix_fmt', 'yuv420p']
    run('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', video, '-i', mix, '-map', '0:v', '-map', '1:a', *vcodec, '-c:a', 'aac', '-b:a', '192k',
        '-shortest', '-movflags', '+faststart', os.path.join(FIN, name + '.mp4'))
    run('python3', '-I', os.path.join(R, 'tools', 'thumb_brand.py'), cover, PHOTO, accent, os.path.join(FIN, name + '.jpg'))
    print(f'done {name}  {"male+female" if mixed else "male"}  voice {hz:.1f}->{hz + 3:.1f} Hz  gain {gain:.2f}  speed {SPEED}x')
