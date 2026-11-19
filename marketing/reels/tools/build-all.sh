#!/usr/bin/env bash
# Builds every reel that is not in out/ yet: brand reels B1–B6, learning paths P01–P10, then the 43 topic reels.
# Safe to re-run: finished reels (.mp4, thumbnail and voice script in out/<name>/) are skipped.
# Voice QC needs ASR_DIR (sherpa-onnx-whisper-small); without it the pronunciation check is skipped.
# Needs the screens already captured (tools/capture.js for all rooms, capture-brand/account/enroll.js),
# the local site only for those captures, KOKORO_DIR and SITE.   Usage: tools/build-all.sh [log file]
set -uo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"; LOG="${1:-$R/work/build-all.log}"; export SKIP_CAPTURE=1
python3 -I "$R/tools/make-topics.py" "${SITE:-$R/../..}" "$R" >/dev/null
python3 -I "$R/tools/make-paths.py" "${SITE:-$R/../..}" "$R" >/dev/null
done_reel() { ls "$R/out/$1/$1.mp4" "$R/out/$1/$1-thumbnail.jpg" >/dev/null 2>&1 && grep -q "flow v5" "$R/out/$1/$1-voice-script.md" 2>/dev/null; }
for G in b1 b2 b3 b4 b5 account p01 p02 p03 p04 p05 p06 p07 p08 p09 p10; do
  NAME=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['name'])" "$R/guides/$G.json")
  done_reel "$NAME" && continue
  echo "$(date +%H:%M:%S) guide $G $NAME" >> "$LOG"
  "$R/tools/build-guide.sh" "$R/guides/$G.json" >> "$LOG" 2>&1 </dev/null || echo "FAILED guide $G" >> "$LOG"
done
while read -r N NAME; do
  done_reel "$NAME" && continue
  echo "$(date +%H:%M:%S) topic $N $NAME" >> "$LOG"
  "$R/tools/build.sh" "$N" >> "$LOG" 2>&1 </dev/null || echo "FAILED topic $N" >> "$LOG"
done < <(python3 -I -c "import json,sys;[print(t['num'],t['name']) for t in json.load(open(sys.argv[1]))]" "$R/topics.json")
echo "ALL DONE $(date +%H:%M:%S)" >> "$LOG"
