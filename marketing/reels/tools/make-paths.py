"""Learning-path reels P01–P10 (one per CTF path): writes guides/pNN.json from topics.json + paths.json.
Each: hook → the path's handbooks (cover grid) → its CTF rooms (list) → what you can do after → CTA → "seen this reel?".
Usage: python3 -I tools/make-paths.py <website-classic dir> <reels dir>   (run make-topics.py first)"""
import json, os, re, sys
SITE, REELS = sys.argv[1], sys.argv[2]
topics = json.load(open(os.path.join(REELS, 'topics.json'), encoding='utf-8'))
lines = json.load(open(os.path.join(REELS, 'paths.json'), encoding='utf-8'))
paths = json.load(open(os.path.join(SITE, 'public/api/ctf-data/rooms.json'), encoding='utf-8'))['paths']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from voice_qc import HI_NUM                     # Hindi number words 0–100: the voice never reads digits
HI = HI_NUM[1:]

def intro_directions(vo):
    """'Question? Answer.' -> questioning, long pause, confident answer; 'A। B।' -> confident, emphasised B."""
    if '?' in vo:
        q, a = vo.split('?', 1); return f"[QUESTIONING] {q}? [LONG PAUSE] [EMPHASIZE] {a.strip()}"
    a, b = vo.split('।', 1); return f"[CONFIDENT] {a}। [SHORT PAUSE] [EMPHASIZE] {b.strip()}"
dummy = [{'img': 'pdfstore', 'scroll': [[0, 0]]}]
for i, p in enumerate(paths, 1):
    ts = [t for t in topics if t['path'] == p['key']]; L = lines[p['key']]; n = len(ts); tasks = sum(t['tasks'] for t in ts)
    covers = [f"cover-{t['series']:02d}" for t in ts]; first = ts[0]
    slug = re.sub(r'[^A-Za-z0-9]+', '-', p['title']).strip('-')
    g = {'name': f'P{i:02d}-Path-{slug}', 'kicker': 'Learning path', 'accent': first['accent'], 'mood': first['mood'], 'shots': 'brand', 'speed': 1.13,
     'intro': {'pill': f"Learning Path · {p['title']}", 'hook': L['hook'], 'chips': [f'📘 {n} handbooks', f'🚩 {n} rooms', f'🧪 {tasks} tasks'], 'vo': intro_directions(L['vo']), 'sub': L['sub']},
     'steps': [
      {'label': f'{n} Handbooks', 'icon': '📚', 'title': f'<em>{n}</em> handbooks', 'tip': '📘 Zero → Mastery', 'visual': 'covers', 'coverSet': covers, 'shots': dummy,
       'vo': f"[CALM] इस पाथ में {HI[n - 1]} हैंडबुक्स हैं। [SHORT PAUSE] [CONFIDENT] {first['tdev']} से, {ts[-1]['tdev']} तक।",
       'sub': f"Is path me {n} handbooks hain. {first['title']} se {ts[-1]['title']} tak."},
      {'label': f'{n} CTF Rooms', 'icon': '🚩', 'title': f'<em>{tasks}</em> hands-on tasks', 'tip': '🚩 Har room ka task 1 FREE', 'visual': 'list', 'shots': dummy,
       'items': [[f"{t['num']:02d}", t['roomTitle']] for t in ts],
       'vo': f"[CALM] और {HI[n - 1]} सीटीएफ़ रूम्स, जिनमें {HI[tasks - 1]} हैंड्स-ऑन टास्क हैं। [SHORT PAUSE] [EMPHASIZE] हर रूम का पहला टास्क फ़्री है।",
       'sub': f"Aur {n} CTF rooms, jinme {tasks} hands-on tasks hain. Har room ka pehla task FREE hai."},
      {'label': 'Is path ke baad', 'icon': '🎯', 'title': 'Aap kya <em>kar paayenge</em>', 'tip': f"🎓 {p['title']}", 'visual': 'list', 'shots': dummy,
       'items': [['✓', o] for o in L['out']], 'vo': '[CONFIDENT] ' + L['outVo'].replace('इस पाथ के बाद,', 'इस पाथ के बाद, [SHORT PAUSE]', 1), 'sub': L['outSub'], 'confetti': 0.6},
     ],
     'cta': {'headline': 'Ye path <em>shuru</em> kijiye 👇', 'button': f"🚩 Room {first['num']} se start", 'chips': [f'📘 {n} handbooks', f'🚩 {n} rooms'],
             'vo': '[EXCITED] आज ही ये पाथ शुरू कीजिए, [SHORT PAUSE] [CONFIDENT] टेक गार्डियन्स डॉट इन पर।', 'sub': 'Aaj hi ye path shuru kijiye — techguardians.in par.'},
     'ref': {'kind': 'seen', 'name': first['name'], 'rom': f"Room {first['num']} · {first['title']}", 'cover': first['book'],
             'vo': f"[POLITE] इस पाथ की पहली रील, {first['tdev']}, प्रोफ़ाइल पर ज़रूर देखिए।",
             'sub': f"Is path ki pehli reel — {first['title']} — profile par zaroor dekhiye."},
     'cover': {'pill': f"Learning Path · {n} rooms", 'hook': L['hook'], 'covers': covers, 'chip': f'📘 {n} handbooks · 🚩 {tasks} tasks'},
     'caption': f"{re.sub('<[^>]+>', '', L['hook'])}\n\n{p['title']} path — {p['desc']}\n\n📘 {n} handbooks: " + ', '.join(t['title'] for t in ts)
                + f"\n🚩 {n} CTF rooms · {tasks} hands-on tasks · har room ka task 1 FREE\n🎯 " + ' · '.join(L['out'])
                + "\n\n👉 techguardians.in (link in bio)\nKeep Learning · Keep Sharing 🇮🇳",
     'tags': ['#techguardians', '#cybersecurity', '#learningpath', '#ctf', '#cybersecuritycareer', '#cybersecurityindia', '#hinglish', '#' + p['key'].lower()]}
    json.dump(g, open(os.path.join(REELS, 'guides', f'p{i:02d}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(g['name'], n, 'rooms', tasks, 'tasks')
