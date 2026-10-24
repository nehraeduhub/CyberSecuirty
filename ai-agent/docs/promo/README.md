# Promo video

`CyberSec-AI-Agent-ad.mp4`: 48-second 16:9 advert (1920×1080, 30 fps, H.264 + AAC) with an original synthesized soundtrack.

To re-render after editing the scenes in `ad.html` or the music in `music.py` (needs Node with Playwright, Python with numpy, and ffmpeg):

```bash
cd docs/promo
python3 music.py
ffmpeg -y -i music_raw.wav -af "aecho=0.8:0.5:60|120:0.18|0.10,highpass=f=28,loudnorm=I=-15:TP=-1.5:LRA=9" music.wav
node render.js        # writes CyberSec-AI-Agent-ad.mp4
```
