"""Builds topics.json for all 43 topics from the site data (handbook + CTF room).
Hand-written lines (hook, points, voice-over, captions) live in scripts.json and are merged in.
Usage: python3 -I tools/make-topics.py <website-classic dir> <reels dir>"""
import json, os, re, sys

SITE, REELS = sys.argv[1], sys.argv[2]
books = json.load(open(os.path.join(SITE, 'public/api/store-books.json'), encoding='utf-8'))
rooms = json.load(open(os.path.join(SITE, 'public/api/ctf-data/rooms.json'), encoding='utf-8'))['rooms']
scripts = json.load(open(os.path.join(REELS, 'scripts.json'), encoding='utf-8'))

# One accent colour + music mood per learning path, so the feed does not look repetitive.
PATHS = {
    'Core':      {'accent': '#ff9933', 'mood': 'bright'},
    'Networking':{'accent': '#38bdf8', 'mood': 'pulse'},
    'Perimeter': {'accent': '#f97316', 'mood': 'drive'},
    'Detection': {'accent': '#22d3ee', 'mood': 'scan'},
    'SOC':       {'accent': '#ef4444', 'mood': 'tension'},
    'Windows':   {'accent': '#60a5fa', 'mood': 'drive'},
    'Linux':     {'accent': '#facc15', 'mood': 'pulse'},
    'Forensics': {'accent': '#a78bfa', 'mood': 'scan'},
    'CTI':       {'accent': '#34d399', 'mood': 'tension'},
    'Infra':     {'accent': '#2dd4bf', 'mood': 'bright'},
}
DIFF = {'easy': 'Easy', 'med': 'Medium', 'hard': 'Hard'}

books.sort(key=lambda b: b['series'])
out = []
for book, room in zip(books, rooms):
    n = int(room['num'])
    assert book['series'] == n, (book['id'], room['num'])
    bullets = re.findall(r'^• (.+)$', book['description'], re.M)
    name = re.sub(r'[^A-Za-z0-9]+', '-', book['title']).strip('-')
    t = {
        'num': n, 'slug': room['slug'], 'book': book['id'], 'name': f'{n:02d}-{name}',
        'title': book['title'], 'subtitle': book['subtitle'], 'pages': book['pages'],
        'category': book['category'], 'path': room['path'], 'difficulty': DIFF.get(room['difficulty'], room['difficulty']),
        'roomTitle': room['title'], 'tasks': len(room['tasks']),
        'taskTitles': [x['title'] for x in room['tasks']],   # titles only — never flags or answers
        'points': bullets[:3],
        **PATHS[room['path']],
    }
    t.update(scripts.get(str(n), {}))
    out.append(t)

json.dump(out, open(os.path.join(REELS, 'topics.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(out), 'topics;', sum(1 for t in out if 'vo' in t), 'with a voice-over script')
