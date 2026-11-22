#!/usr/bin/env bash
# Tech Guardians VAPT reel: voice -> music + sfx -> mix -> frames -> MP4.
# Usage: src/build-reel.sh <work dir> <out.mp4>   (env KOKORO_DIR, ASR_DIR; SPEED voice speed, default 1.08; JOBS 4)
set -euo pipefail
SRC=$(cd "$(dirname "$0")" && pwd); T=$(cd "$SRC/../../reels/tools" && pwd)
W=$1; OUT=$2; mkdir -p "$W"; J=${JOBS:-4}
[ -f "$W/timeline.json" ] && [ "$W/timeline.json" -nt "$SRC/script.json" ] || SPEED=${SPEED:-1.08} python3 "$SRC/voice.py" "$SRC/script.json" "$W"
TOTAL=$(python3 -c "import json;print(json.load(open('$W/timeline.json'))['total'])")
python3 -I "$T/music.py" drive "$TOTAL" "$W/music.wav" >/dev/null
python3 - "$W" <<'EOF'
import json, sys
W = sys.argv[1]; T = json.load(open(W + '/timeline.json', encoding='utf-8'))
sc = {s['id']: [s['start'], s['until']] for s in T['scenes']}; at = lambda k, d: sc[k][0] + d
json.dump({'total': T['total'], 'scenes': sc, 'marks': {'cards': [at('threats', .15 + i * .9) for i in range(3)] + [at('sell', .1 + i * 1.6) for i in range(3)],
  'sparkles': [at('turn', .05), at('intro', .2), at('cta', 1.0)]}}, open(W + '/sfx.json', 'w'))
EOF
python3 -I "$T/sfx.py" "$W/sfx.json" "$W/sfx.wav" >/dev/null
ffmpeg -nostdin -v error -y -i "$W/music.wav" -i "$W/sfx.wav" -i "$W/voice.wav" -filter_complex \
 "[2]aresample=48000,volume=2.0,asplit[vo1][sc];[0]volume=0.75[m];[m][sc]sidechaincompress=threshold=0.08:ratio=2:attack=30:release=450[md];[1]volume=0.45[fx];[md][vo1][fx]amix=inputs=3:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]" \
 -map "[a]" -ar 48000 -ac 2 "$W/mix.wav"
N=$(python3 -c "import math;print(math.ceil($TOTAL*30))"); rm -rf "$W/frames"; mkdir -p "$W/frames"
for k in $(seq 0 $((J-1))); do node "$SRC/render.js" "$W" "$W/frames" "$((N*k/J)),$((N*(k+1)/J))" & done; wait
[ "$(ls "$W/frames" | wc -l)" -eq "$N" ] || { echo "FRAMES MISSING"; exit 1; }
ffmpeg -nostdin -v error -y -framerate 30 -i "$W/frames/f%05d.jpg" -i "$W/mix.wav" -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
 -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT"
echo "done: $OUT ($TOTAL s)"
