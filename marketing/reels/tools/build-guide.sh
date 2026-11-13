#!/usr/bin/env bash
# Guide reels (step-by-step how-to), e.g.:  tools/build-guide.sh guides/account.json
#   -> out/<name>/<name>.mp4, -thumbnail.jpg, .srt, .txt
# Needs the local site on 127.0.0.1:8110 (PLAN.md §7), KOKORO_DIR, SITE_DATA=<site>/api/data (account guide)
# and SITE=<website-classic> (brand reels; default ../..).
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"; GJ="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
JOBS="${JOBS:-3}"; MUSIC_VOL="${MUSIC_VOL:-0.75}"; SFX_VOL="${SFX_VOL:-0.45}"
read -r NAME SHOTS MOOD < <(python3 -I -c "import json,sys;g=json.load(open(sys.argv[1]));print(g['name'],g['shots'],g['mood'])" "$GJ")
W="$R/work/guide-$NAME"; O="$R/out/$NAME"; mkdir -p "$W" "$O"
[ -n "${SKIP_CAPTURE:-}" ] || SITE="${SITE:-$R/../..}" node "$R/tools/capture-$SHOTS.js" "$R/work/$SHOTS"   # SKIP_CAPTURE=1 reuses the screens
cp "$R/legacy/launch/shield.png" "$W/logo.png"
REFB=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('ref',{}).get('cover',''))" "$GJ")
rm -f "$W/refcover.png"; [ -z "$REFB" ] || cp "${SITE:-$R/../..}/public/images/store/books/$REFB-cover.png" "$W/refcover.png"
python3 -I "$R/tools/guide.py" "$GJ" "$W" "$O"
TOTAL=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['total'])" "$W/data.json")
python3 -I "$R/tools/music.py" "$MOOD" "$TOTAL" "$W/music.wav" >/dev/null
python3 -I "$R/tools/sfx.py" "$W/data.json" "$W/sfx.wav" >/dev/null
IN=(-i "$W/music.wav" -i "$W/sfx.wav"); F=""; i=2; L=""
while read -r FILE AT; do
  IN+=(-i "$W/$FILE"); MS=$(python3 -c "print(int($AT*1000))")
  F+="[$i]aresample=48000,highpass=f=80,volume=1.4,pan=stereo|c0=c0|c1=c0,adelay=$MS|$MS[v$i];"; L+="[v$i]"; i=$((i+1))
done < <(python3 -I -c "import json,sys;[print(c['file'],c['at']) for c in json.load(open(sys.argv[1]))['clips']]" "$W/data.json")
F+="${L}amix=inputs=$((i-2)):normalize=0,apad[vo];[vo]asplit[vo1][sc];[0]volume=$MUSIC_VOL[m];"
F+="[m][sc]sidechaincompress=threshold=0.08:ratio=2:attack=30:release=450[md];[1]volume=$SFX_VOL[fx];[md][vo1][fx]amix=inputs=3:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
ffmpeg -loglevel error -y "${IN[@]}" -filter_complex "$F" -map "[a]" -ar 48000 -ac 2 "$W/mix.wav"
rm -rf "$W/frames"; NF=$(python3 -c "import math;print(math.ceil($TOTAL*30))"); STEP=$(( (NF + JOBS - 1) / JOBS ))
for ((s=0; s<NF; s+=STEP)); do node "$R/tools/render.js" "$W" "$W/frames" "$s,$((s+STEP))" & done; wait
ffmpeg -loglevel error -y -framerate 30 -i "$W/frames/f%05d.jpg" -i "$W/mix.wav" -c:v libx264 -profile:v high -crf 18 -preset slow \
  -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart "$O/$NAME.mp4"
node "$R/tools/render.js" "$W" "$W/frames" cover "$O/$NAME-thumbnail.jpg"
rm -rf "$W/frames"
echo "done: $O/$NAME.mp4 (${TOTAL}s)"
