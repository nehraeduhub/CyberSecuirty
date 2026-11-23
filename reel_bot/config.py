"""Branding and settings for the daily cyber-fraud reel."""

BRAND_TOP = "CYBER SAFE JHUNJHUNU"
BRAND_BOTTOM_1 = "Tech Guardians"
BRAND_BOTTOM_2 = "RJ Nehra | Master in AI & Cyber Security"
HELPLINE = "Fraud ho to turant call karo 1930 | cybercrime.gov.in"

# Google News RSS search (India, Hindi + English results)
NEWS_QUERIES = [
    'cyber fraud OR "online scam" OR "digital arrest" India when:1d',
    'साइबर ठगी OR ऑनलाइन फ्रॉड when:1d',
]

# Video
WIDTH, HEIGHT = 1080, 1920
FPS = 30
BG_TOP = (10, 14, 35)        # dark navy
BG_BOTTOM = (60, 6, 20)      # dark red
ACCENT = (255, 204, 0)       # yellow
TEXT = (255, 255, 255)

# Claude model used to write the script
CLAUDE_MODEL = "claude-opus-5-5"
