#!/usr/bin/env bash
# Downloads the free Piper Hindi voices (one-time, ~63 MB each) into reels/models/.
set -e
cd "$(dirname "$0")/../models"
for v in ${@:-rohan pratham priyamvada}; do
  for e in onnx onnx.json; do
    f="hi_IN-$v-medium.$e"
    [ -s "$f" ] || curl -fL -o "$f" "https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/$v/medium/$f"
  done
done
pip install -q piper-tts
echo "voices ready"
