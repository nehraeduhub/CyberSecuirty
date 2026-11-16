"""Voice deliverables for one reel, from <work>/voice.json (written by timeline.py / guide.py):
  <out>/<name>-voiceover.mp3      the final voice track alone (no music), timed exactly as in the reel
  <out>/<name>-voice-script.md    script with voice directions, sentence-wise direction sheet with timestamps,
                                  correction report and QC status
Usage: python3 -I tools/voice_report.py <work dir> <out dir> <name>"""
import json, os, subprocess, sys
import numpy as np, soundfile as sf

W, OUT, NAME = sys.argv[1:4]
V = json.load(open(os.path.join(W, 'voice.json'), encoding='utf-8'))
ts = lambda x: f'{int(x // 60)}:{x % 60:04.1f}'

# voice-only track
sr = 24000; total = V['total']; track = np.zeros(int(total * sr) + sr, np.float32)
for c in V['clips']:
    a, sr2 = sf.read(os.path.join(W, c['file']), dtype='float32'); i = int(c['at'] * sr)
    track[i:i + len(a)] += a[:len(track) - i]
wav = os.path.join(W, 'voiceover.wav'); sf.write(wav, track[:int(total * sr)], sr)
subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', wav, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
                '-ar', '44100', '-c:a', 'libmp3lame', '-b:a', '128k', os.path.join(OUT, f'{NAME}-voiceover.mp3')], check=True)

rows, fixes, attention, n = [], [], [], 0
for c in V['clips']:
    qc = c.get('qc') or []
    for i, s in enumerate(c['segs']):
        n += 1; t0 = c['at'] + s[0]; e = qc[i] if i < len(qc) else {}
        m = e.get('final_metrics', e.get('metrics', {}))
        status = 'OK' if e.get('fixed', True) else 'LISTEN'
        if e.get('problems'):
            res = 'fixed' if e.get('fixed') else 'still flagged — please listen'
            fixes.append(f"| {ts(t0)} | {c['scene']} | {s[2]} | {'; '.join(e['problems'])} | regenerated: {e.get('chosen', '')} | {res} |")
            if not e.get('fixed'): attention.append(f"{ts(t0)} — {s[2]} ({'; '.join(e.get('final_problems', []))})")
        heard = m.get('asr', '')
        rows.append(f"| {ts(t0)} | {c['scene']} | {s[2]} | {s[4]} | {s[5]:.2f} s | {status}{' · heard: ' + heard if heard else ''} |")

status = 'PASS' if not attention else f'PASS with {len(attention)} phrase(s) to check by ear'
md = [f"# {NAME} — voice script & quality check", '',
      f"Voice: Kokoro `{V['voice']}` (Hindi male), base speed {V['speed']}, same voice for every line · length {ts(total)} · "
      f"{n} phrases · corrected: {len(fixes)} · **QC status: {status}**", '',
      '## Script with voice directions', '',
      'Tags: [SHORT PAUSE] 0.35 s · [LONG PAUSE] 0.70 s · comma 0.18 s · sentence end 0.42 s · question 0.55 s. '
      'A style tag holds until the next one; each scene starts in its default style.', '']
for c in V['clips']:
    md += [f"**{c['scene']}** (starts {ts(c['at'])}, default {c.get('default', 'NORMAL')})", '', '> ' + c['script'], '']
md += ['## Sentence-wise direction sheet', '', '| Time | Scene | Phrase | Direction | Pause after | Check |', '|---|---|---|---|---|---|'] + rows
md += ['', '## Correction report', '']
md += (['| Time | Scene | Phrase | Problem found | Fix | Result |', '|---|---|---|---|---|---|'] + fixes) if fixes else ['No phrase needed a correction.']
md += ['', '## Quality check', '',
       '- Every phrase was checked automatically: transcribed back with Whisper and compared with the script, gaps inside the phrase, '
       'speed, loudness, pitch, cut-off ending and clipping. A failing phrase was regenerated (up to 6 variants) and the best take kept.',
       '- This is a measured check, not a human listen: Claude cannot hear audio. Whisper-small is weak at Hindi, so "heard" '
       'shows what it understood, not necessarily what was said.',
       '- Phrases to listen to: ' + ('; '.join(attention) if attention else 'none flagged.')]
open(os.path.join(OUT, f'{NAME}-voice-script.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
json.dump({'name': NAME, 'phrases': n, 'corrected': len(fixes), 'attention': attention, 'length': total},
          open(os.path.join(W, 'voice-qc-summary.json'), 'w', encoding='utf-8'), ensure_ascii=False)
print(NAME, status, f'{n} phrases, {len(fixes)} corrected')
