"""One quality-check overview for the whole series: out/VOICE-QC-REPORT.md from every reel's
work/*/voice-qc-summary.json (written by voice_report.py).   Usage: python3 -I tools/voice_summary.py <reels dir>"""
import glob, json, os, sys
R = sys.argv[1]
rows = sorted((json.load(open(f, encoding='utf-8')) for f in glob.glob(os.path.join(R, 'work', '*', 'voice-qc-summary.json'))),
              key=lambda r: (not r['name'][0].isalpha() or r['name'][0] not in 'BP', r['name']))
rows = [r for r in rows if os.path.isdir(os.path.join(R, 'out', r['name']))]
ph = sum(r['phrases'] for r in rows); fx = sum(r['corrected'] for r in rows); at = [(r['name'], a) for r in rows for a in r['attention']]
md = ['# Voice quality check — all reels', '',
      f'{len(rows)} reels · {ph} phrases checked · {fx} regenerated after a failed check · {len(at)} still flagged (listen to these)', '',
      'Each reel folder has `<name>-voice-script.md` (script with voice directions, direction sheet, correction report) '
      'and `<name>-voiceover.mp3` (voice only).', '',
      'The check is automatic (Whisper transcription + pause, speed, loudness, pitch, ending and clipping measurements); '
      'nobody has listened to the audio. Please listen to a few reels, and to every phrase listed below, before posting.', '',
      '| Reel | Length | Phrases | Regenerated | Still flagged |', '|---|---|---|---|---|']
md += [f"| {r['name']} | {r['length']:.0f} s | {r['phrases']} | {r['corrected']} | {len(r['attention'])} |" for r in rows]
md += ['', '## Phrases to listen to', ''] + ([f'- **{n}** {a}' for n, a in at] or ['None — every phrase passed after correction.'])
open(os.path.join(R, 'out', 'VOICE-QC-REPORT.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
print(len(rows), 'reels,', ph, 'phrases,', fx, 'regenerated,', len(at), 'flagged')
