<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Sample images (bring your own)
Place a photo YOU took here as `sample.jpg` for the live ExifTool demo.
Do not commit real personal photos to any shared repo. A quick way to create a
dummy image with a GPS tag for teaching:

```bash
# create a plain test image (needs ImageMagick)
convert -size 800x600 xc:gray sample.jpg
# add FICTIONAL metadata with ExifTool (teaching only)
exiftool -Make="DemoCam" -Model="SeminarPhone" \
  -GPSLatitude="28.6139" -GPSLatitudeRef=N \
  -GPSLongitude="77.2090" -GPSLongitudeRef=E sample.jpg
exiftool sample.jpg     # show the tags
exiftool -all= sample.jpg  # strip them
```
(The coordinates above point at a public landmark area, not a person's home.)
