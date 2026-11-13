"""Builds topics.json for all 43 topic reels from the site data (handbook + CTF room) and scripts.json.
Every reel's voice-over is assembled here: hook + learn (hand-written per topic in scripts.json), then
book / CTF / CTA / "next reel" lines from fixed patterns, so all 43 sound like one series.
Usage: python3 -I tools/make-topics.py <website-classic dir> <reels dir>"""
import json, os, re, sys

SITE, REELS = sys.argv[1], sys.argv[2]
books = {b['series']: b for b in json.load(open(os.path.join(SITE, 'public/api/store-books.json'), encoding='utf-8'))}
rooms = json.load(open(os.path.join(SITE, 'public/api/ctf-data/rooms.json'), encoding='utf-8'))['rooms']
scripts = json.load(open(os.path.join(REELS, 'scripts.json'), encoding='utf-8'))

# Handbook series and CTF rooms share 43 topics; only Linux / Forensics are in a different order.
BOOK_FOR_ROOM = {34: 37, 35: 38, 36: 34, 37: 35, 38: 36}
PATHS = {   # accent colour + music mood per learning path
    'Core': ('#ff9933', 'bright'), 'Networking': ('#38bdf8', 'pulse'), 'Perimeter': ('#f97316', 'drive'),
    'Detection': ('#22d3ee', 'scan'), 'SOC': ('#ef4444', 'tension'), 'Windows': ('#60a5fa', 'drive'),
    'Linux': ('#facc15', 'pulse'), 'Forensics': ('#a78bfa', 'scan'), 'CTI': ('#34d399', 'tension'), 'Infra': ('#2dd4bf', 'bright')}
DIFF = {'easy': 'Easy', 'med': 'Medium', 'hard': 'Hard'}
HI = ('एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस बाईस तेईस चौबीस '
      'पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस').split()
ACCOUNT_REEL = {'name': 'B6-How-to-Create-Student-Account', 'rom': 'Student Account kaise banayein', 'dev': 'स्टूडेंट अकाउंट कैसे बनाएँ'}
WEBSITE_REEL = {'name': 'B1-Website-Tour', 'rom': 'Tech Guardians Website Tour', 'dev': 'टेक गार्डियन्स वेबसाइट टूर'}

def ref_lines(ref, kind):
    if kind == 'next':
        return (f"अगली रील में देखिए, {ref['dev']}। उसे मिस मत कीजिए!", f"Agli reel me dekhiye — {ref['rom']}. Use miss mat kijiye!")
    return (f"{ref['dev']} वाली रील देखी क्या? नहीं देखी, तो प्रोफ़ाइल पर ज़रूर देखिए।", f"{ref['rom']} wali reel dekhi kya? Nahi dekhi, to profile par zaroor dekhiye.")

out = []
for room in rooms:
    n = int(room['num']); book = books[BOOK_FOR_ROOM.get(n, n)]; s = scripts[str(n)]
    bullets = re.findall(r'^• (.+)$', book['description'], re.M)
    name = re.sub(r'[^A-Za-z0-9]+', '-', book['title']).strip('-')
    k = len(room['tasks'])
    t = {'num': n, 'series': book['series'], 'slug': room['slug'], 'book': book['id'], 'name': f'{n:02d}-{name}',
         'title': book['title'], 'subtitle': book['subtitle'], 'pages': book['pages'], 'category': book['category'],
         'path': room['path'], 'difficulty': DIFF.get(room['difficulty'], room['difficulty']), 'roomTitle': room['title'],
         'tasks': k, 'taskTitles': [x['title'] for x in room['tasks']],    # titles only — never flags or answers
         'accent': PATHS[room['path']][0], 'mood': PATHS[room['path']][1],
         'icon': s['icon'], 'hook': s['hook'], 'points': s.get('points') or bullets[:3], 'tags': s['tags'], 'tdev': s['tdev'],
         'showTasks': s.get('showTasks', [2, 5, k])}
    out.append(t)

for i, t in enumerate(out):
    s = scripts[str(t['num'])]
    if i + 1 < len(out):
        nx = out[i + 1]; ref = {'name': nx['name'], 'rom': f"Room {nx['num']} · {nx['title']}", 'dev': nx['tdev'], 'cover': nx['book'], 'kind': 'next'}
    else: ref = dict(WEBSITE_REEL, kind='seen')
    rv, rs = ref_lines(ref, ref['kind'])
    nh, kh = HI[t['num'] - 1], HI[t['tasks'] - 1]
    t['ref'] = ref; t['accountRef'] = ACCOUNT_REEL
    t['vo'] = {'hook': s['hookVo'], 'learn': s['learnVo'],
        'book': f"पहले हैंडबुक से कॉन्सेप्ट क्लियर करो। {t['tdev']}, ज़ीरो से मास्टरी तक, आसान भाषा में।",
        'ctf': f"फिर सीटीएफ़ पोर्टल के रूम नंबर {nh} में, {kh} हैंड्स-ऑन टास्क से प्रैक्टिस करो। पहला टास्क बिल्कुल फ़्री है। सीटीएफ़ एक्सेस के लिए, अपना अकाउंट ज़रूर बना लें। कैसे बनाएँ, वो रील देखी क्या?",
        'cta': "पहले सीखो, फिर प्रैक्टिस करो। टेक गार्डियन्स डॉट इन पर, अभी एनरोल करो, और सीखना स्टार्ट करो!",
        'ref': rv}
    t['sub'] = {'hook': s['hookSub'], 'learn': s['learnSub'],
        'book': f"Pehle handbook se concept clear karo. {t['title']} — zero se mastery tak, aasaan bhasha me.",
        'ctf': f"Phir CTF Portal ke Room {t['num']} me, {t['tasks']} hands-on tasks se practice karo. Pehla task bilkul FREE hai. CTF access ke liye apna account zaroor bana lein — kaise banayein, wo reel dekhi kya?",
        'cta': "Pehle seekho, phir practice karo. techguardians.in par abhi enroll karo — aur seekhna start karo!",
        'ref': rs}

json.dump(out, open(os.path.join(REELS, 'topics.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(out), 'topics')
