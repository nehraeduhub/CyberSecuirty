#!/usr/bin/env bash
# One command per topic reel:  tools/build.sh 12 [18 23 ...]
#   -> out/<NN-Name>/<NN-Name>.mp4, -thumbnail.jpg, .srt, .txt
# Needs: the local site running on 127.0.0.1:8110 (PLAN.md §7), KOKORO_DIR with the Kokoro model files,
# SITE = path to website-classic (default: ../../ from this folder). MUSIC_VOL (default 0.75) / SFX_VOL (0.45) set the music / sound-effect levels.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
SITE="${SITE:-$R/../..}"; JOBS="${JOBS:-3}"; MUSIC_VOL="${MUSIC_VOL:-0.75}"
python3 -I "$R/tools/make-topics.py" "$SITE" "$R" >/dev/null
[ -n "${SKIP_CAPTURE:-}" ] || node "$R/tools/capture.js" "$R/topics.json" "$(IFS=,; echo "$*")" "$R/work"
for N in "$@"; do
  W="$R/work/$N"; mkdir -p "$W"
  read -r NAME BOOK MOOD < <(python3 -I -c "import json,sys;t=[x for x in json.load(open(sys.argv[1])) if x['num']==int(sys.argv[2])][0];print(t['name'],t['book'],t['mood'])" "$R/topics.json" "$N")
  O="$R/out/$NAME"; mkdir -p "$O"
  cp "$SITE/public/images/store/books/$BOOK-cover.png" "$W/cover.png"
  cp "$SITE/public/images/store/books/$BOOK-feature.png" "$W/feature.png"
  cp "$R/legacy/launch/shield.png" "$W/logo.png"
  REFB=$(python3 -I -c "import json,sys;t=[x for x in json.load(open(sys.argv[1])) if x['num']==int(sys.argv[2])][0];print(t['ref'].get('cover',''))" "$R/topics.json" "$N")
  rm -f "$W/refcover.png"; [ -z "$REFB" ] || cp "$SITE/public/images/store/books/$REFB-cover.png" "$W/refcover.png"
  python3 -I "$R/tools/voice.py" "$R/topics.json" "$N" "$W" hm_omega "${VOICE_SPEED:-1.06}" >/dev/null
  python3 -I "$R/tools/timeline.py" "$R/topics.json" "$N" "$W" "$O"
  TOTAL=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['total'])" "$W/data.json")
  python3 -I "$R/tools/music.py" "$MOOD" "$TOTAL" "$W/music.wav" >/dev/null
  python3 -I "$R/tools/sfx.py" "$W/data.json" "$W/sfx.wav" >/dev/null
  # voice clips at their times, music ducked under the voice (sidechain), loudness -14 LUFS, peak -1.5 dB
  IN=(-i "$W/music.wav" -i "$W/sfx.wav"); F=""; i=2; L=""
  while read -r SCENE AT; do
    IN+=(-i "$W/vo-$SCENE.wav"); MS=$(python3 -c "print(int($AT*1000))")
    F+="[$i]aresample=48000,highpass=f=80,volume=1.4,pan=stereo|c0=c0|c1=c0,adelay=$MS|$MS[v$i];"; L+="[v$i]"; i=$((i+1))
  done < <(python3 -I -c "import json,sys;[print(c['scene'],c['at']) for c in json.load(open(sys.argv[1]))['clips']]" "$W/data.json")
  F+="${L}amix=inputs=$((i-2)):normalize=0,apad[vo];[vo]asplit[vo1][sc];[0]volume=$MUSIC_VOL[m];"
  F+="[m][sc]sidechaincompress=threshold=0.08:ratio=2:attack=30:release=450[md];[1]volume=${SFX_VOL:-0.45}[fx];[md][vo1][fx]amix=inputs=3:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
  ffmpeg -loglevel error -y "${IN[@]}" -filter_complex "$F" -map "[a]" -ar 48000 -ac 2 "$W/mix.wav"
  # frames, rendered in JOBS parallel slices
  rm -rf "$W/frames"; NF=$(python3 -c "import math;print(math.ceil($TOTAL*30))"); STEP=$(( (NF + JOBS - 1) / JOBS ))
  for ((s=0; s<NF; s+=STEP)); do node "$R/tools/render.js" "$W" "$W/frames" "$s,$((s+STEP))" & done; wait
  ffmpeg -loglevel error -y -framerate 30 -i "$W/frames/f%05d.jpg" -i "$W/mix.wav" -c:v libx264 -profile:v high -crf 18 -preset slow \
    -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart "$O/$NAME.mp4"
  node "$R/tools/render.js" "$W" "$W/frames" cover "$O/$NAME-thumbnail.jpg"
  rm -rf "$W/frames"
  echo "done: $O/$NAME.mp4 (${TOTAL}s)"
done
