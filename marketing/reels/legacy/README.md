# Legacy reel tooling (working references)

- `reel/` — 9:16 "How to enroll for CTF" reel (60 s). `capture.js` takes phone screenshots from the
  local site (needs a demo student `arjun.m` / `Student12345` with no CTF plan), `reel.html` is the
  animation (`window.render(t)`), `render.js` writes 1,800 JPEG frames, `music.py` makes the soundtrack.
  Encode: `ffmpeg -framerate 30 -i frames/f%05d.jpg -i music.wav -c:v libx264 -crf 19 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest -movflags +faststart out.mp4`
- `launch/` — 16:9 grand-launch intro (60 s). Same pattern; `shield.png` is the clean logo.
- `local-site/router.php` — router for `php -S`: `DOCROOT=<site> php -S 127.0.0.1:8110 -t <site> router.php`.
  In the copied site, replace the line `tg_enforce_license();` in `api/lib.php` with a comment
  (local copies are not licensed for 127.0.0.1). Never commit that change.

Paths inside these scripts point at the old scratchpad; adjust them when reusing.
