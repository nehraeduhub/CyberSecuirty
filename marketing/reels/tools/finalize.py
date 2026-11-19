"""Final reels in the owner's voice. For every reel in out/: the cloned voice track (clone/<name>.wav, made by
voice-clone-convert.py from work/.../voiceover.wav) is raised by +3 Hz (owner's choice), brought to the level the
Kokoro voice had, mixed with that reel's music + sound effects exactly as build.sh does, and put on the reel's video
(video untouched). Thumbnail: the reel's cover + brand strip (thumb_brand.py). Output: final/<name>.mp4 + <name>.jpg.
Usage: python3 -I tools/finalize.py <reels dir> <owner photo> [name ...]"""
import glob, json, os, re, subprocess, sys
R, PHOTO, only = sys.argv[1], sys.argv[2], set(sys.argv[3:])
FIN = os.path.join(R, 'final'); os.makedirs(FIN, exist_ok=True)
run = lambda *a: subprocess.run(a, check=True, capture_output=True, text=True)

def f0(path):
    out = run('python3', '-I', os.path.join(R, '..', 'ptest', 'prosody.py'), os.path.join(R, 'tools'), path).stdout
    return float(re.search(r'f0 median ([0-9.]+)', out).group(1))

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
    if not all(os.path.exists(p) for p in (clone, video, cover)): print('skip (missing input)', name); continue
    up = os.path.join(W, 'clone-up.wav'); hz = f0(clone)
    run('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', clone, '-af', f'rubberband=pitch={(hz + 3) / hz:.5f}:formant=preserved:pitchq=quality', up)
    gain = 10 ** ((lufs(os.path.join(W, 'voiceover.wav'), 2.0) - lufs(up, 1.0)) / 20)
    mix = os.path.join(W, 'mix-clone.wav')
    run('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', os.path.join(W, 'music.wav'), '-i', os.path.join(W, 'sfx.wav'), '-i', up, '-filter_complex',
        f'[2]aresample=48000,highpass=f=80,volume={gain:.3f},pan=stereo|c0=c0|c1=c0,apad[vo];[vo]asplit[vo1][sc];[0]volume=0.75[m];'
        '[m][sc]sidechaincompress=threshold=0.08:ratio=2:attack=30:release=450[md];[1]volume=0.45[fx];'
        '[md][vo1][fx]amix=inputs=3:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]', '-map', '[a]', '-ar', '48000', '-ac', '2', mix)
    run('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', video, '-i', mix, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
        '-shortest', '-movflags', '+faststart', os.path.join(FIN, name + '.mp4'))
    run('python3', '-I', os.path.join(R, 'tools', 'thumb_brand.py'), cover, PHOTO, accent, os.path.join(FIN, name + '.jpg'))
    print(f'done {name}  voice {hz:.1f}->{hz + 3:.1f} Hz  gain {gain:.2f}')
