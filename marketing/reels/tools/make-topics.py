"""Builds topics.json for all 43 topic reels from the site data (handbook + CTF room) and scripts.json.
Every reel's voice-over is assembled here: hook + learn (hand-written per topic in scripts.json), then
a topic-specific format scene (formats.json: quiz / myth / compare / mistake / story / tip), then book / CTF / CTA /
"next reel" lines picked from several wordings, plus a look (theme, layouts, transitions) — so no two neighbouring reels
look or sound alike.
Usage: python3 -I tools/make-topics.py <website-classic dir> <reels dir>"""
import json, os, re, sys

SITE, REELS = sys.argv[1], sys.argv[2]
books = {b['series']: b for b in json.load(open(os.path.join(SITE, 'public/api/store-books.json'), encoding='utf-8'))}
rooms = json.load(open(os.path.join(SITE, 'public/api/ctf-data/rooms.json'), encoding='utf-8'))['rooms']
scripts = json.load(open(os.path.join(REELS, 'scripts.json'), encoding='utf-8'))
formats = json.load(open(os.path.join(REELS, 'formats.json'), encoding='utf-8'))

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

# Voice directions (see tools/speak.py). Scene default styles: hook CONFIDENT, learn CALM, book NORMAL,
# ctf NORMAL, cta EXCITED, ref POLITE.
DEFAULT_STYLE = {'fact': 'CALM', 'hook': 'CONFIDENT', 'learn': 'CALM', 'book': 'NORMAL', 'ctf': 'NORMAL', 'cta': 'EXCITED', 'ref': 'POLITE'}

# ---------- variety: every reel gets its own look, scene order and wording (neighbours never share one) ----------
# look dimensions: (name, number of variants, step). n*step mod count with gcd(step, count) = 1, so consecutive
# topics always differ in every dimension and the combination repeats only after hundreds of topics.
LOOK = [('theme', 8, 3), ('hook', 4, 1), ('learn', 5, 2), ('book', 4, 3), ('ctf', 3, 1), ('cta', 4, 1), ('ref', 3, 2),
        ('trans', 5, 3), ('cap', 4, 3), ('cover', 3, 1), ('lines', 5, 2)]
MOODS = ['bright', 'pulse', 'drive', 'scan', 'tension']
ICON = {1: 'shield', 2: 'triad', 3: 'gauge', 4: 'blueprint', 5: 'layers', 6: 'nodes', 7: 'packets', 8: 'switch', 9: 'switch',
        10: 'nodes', 11: 'globe', 12: 'firewall', 13: 'balance', 14: 'firewall', 15: 'terminal', 16: 'radar', 17: 'chart',
        18: 'packets', 19: 'radar', 20: 'logs', 21: 'logs', 22: 'chart', 23: 'siren', 24: 'magnifier', 25: 'nodes',
        26: 'terminal', 27: 'windows', 28: 'shield', 29: 'tree', 30: 'nodes', 31: 'magnifier', 32: 'terminal', 33: 'chart',
        34: 'terminal', 35: 'logs', 36: 'hexdump', 37: 'hexdump', 38: 'magnifier', 39: 'globe', 40: 'radar', 41: 'vms',
        42: 'boxes', 43: 'racks'}
# where the format scene goes: right after the hook (it answers the hook) or after "what you will learn"
FACT_AT = {'quiz': 1, 'myth': 1, 'story': 1, 'mistake': 1, 'compare': 2, 'tip': 2}
LEARN_OPEN = [('हमारे साथ आप सीखेंगे,', 'Humare saath aap seekhenge —'), ('इस रील के बाद आप जानेंगे,', 'Is reel ke baad aap jaanenge —'),
              ('आज हम समझेंगे,', 'Aaj hum samjhenge —'), ('चलिए समझते हैं,', 'Chaliye samajhte hain —'), ('आप सीखेंगे,', 'Aap seekhenge —')]
BOOK = [("पहले हैंडबुक से, कॉन्सेप्ट क्लियर करो। [LONG PAUSE] [CONFIDENT] {d}, [SHORT PAUSE] ज़ीरो से मास्टरी तक, [CALM] आसान भाषा में।",
         "Pehle handbook se concept clear karo. {t} — zero se mastery tak, aasaan bhasha me."),
        ("[CONFIDENT] इसकी पूरी हैंडबुक तैयार है। [LONG PAUSE] {d}, [SHORT PAUSE] [CALM] बेसिक से एडवांस तक, स्टेप बाय स्टेप।",
         "Iski poori handbook taiyaar hai. {t} — basic se advance tak, step by step."),
        ("[CALM] थ्योरी के लिए, हमारी हैंडबुक पढ़िए। [LONG PAUSE] [CONFIDENT] {d}, [SHORT PAUSE] उदाहरणों के साथ, बिल्कुल क्लियर।",
         "Theory ke liye humari handbook padhiye. {t} — udaharanon ke saath, bilkul clear."),
        ("[POLITE] शुरुआत कीजिए, हैंडबुक से। [LONG PAUSE] [CONFIDENT] {d}, [SHORT PAUSE] ज़ीरो से मास्टरी तक।",
         "Shuruaat kijiye handbook se. {t} — zero se mastery tak."),
        ("[CONFIDENT] पहले कॉन्सेप्ट्स मज़बूत कीजिए। [LONG PAUSE] {d} हैंडबुक में, [CALM] सब कुछ एक जगह।",
         "Pehle concepts mazboot kijiye. {t} handbook me — sab kuch ek jagah.")]
CTF = [("फिर सीटीएफ़ पोर्टल के, रूम नंबर {n} में, [SHORT PAUSE] {k} हैंड्स-ऑन टास्क से प्रैक्टिस करो। [LONG PAUSE] [EXCITED] पहला टास्क, [EMPHASIZE] बिल्कुल फ़्री है! [LONG PAUSE] [POLITE] सीटीएफ़ एक्सेस के लिए, अपना अकाउंट ज़रूर बना लें।",
        "Phir CTF Portal ke Room {N} me, {K} hands-on tasks se practice karo. Pehla task bilkul FREE hai! CTF access ke liye apna account zaroor bana lein."),
       ("[CONFIDENT] अब असली प्रैक्टिस, सीटीएफ़ पोर्टल के रूम नंबर {n} में। [SHORT PAUSE] {k} हैंड्स-ऑन टास्क। [LONG PAUSE] [EXCITED] पहला टास्क, [EMPHASIZE] बिल्कुल फ़्री! [LONG PAUSE] [POLITE] सीटीएफ़ एक्सेस के लिए, अपना अकाउंट ज़रूर बना लें।",
        "Ab asli practice — CTF Portal ke Room {N} me. {K} hands-on tasks. Pehla task bilkul FREE! CTF access ke liye apna account zaroor bana lein."),
       ("[CALM] पढ़ने के बाद, हाथ से करके देखिए। [SHORT PAUSE] [CONFIDENT] रूम नंबर {n}, {k} टास्क, ब्राउज़र में ही। [LONG PAUSE] [EXCITED] पहला टास्क, [EMPHASIZE] फ़्री है! [LONG PAUSE] [POLITE] सीटीएफ़ एक्सेस के लिए, अकाउंट बना लीजिए।",
        "Padhne ke baad haath se karke dekhiye. Room {N}, {K} tasks, browser me hi. Pehla task FREE hai! CTF access ke liye account bana lijiye."),
       ("[CONFIDENT] फिर बारी है, सीटीएफ़ चैलेंज की। [SHORT PAUSE] रूम नंबर {n} में, {k} टास्क आपका इंतज़ार कर रहे हैं। [LONG PAUSE] [EXCITED] पहला टास्क, [EMPHASIZE] फ़्री में ट्राई करो! [LONG PAUSE] [POLITE] सीटीएफ़ एक्सेस के लिए, अपना अकाउंट ज़रूर बनाएँ।",
        "Phir baari hai CTF challenge ki. Room {N} me {K} tasks aapka intezaar kar rahe hain. Pehla task FREE me try karo! CTF access ke liye apna account zaroor banayein."),
       ("[CALM] सीखा हुआ, प्रैक्टिस से पक्का होता है। [SHORT PAUSE] [CONFIDENT] सीटीएफ़ रूम नंबर {n}, {k} हैंड्स-ऑन टास्क के साथ। [LONG PAUSE] [EXCITED] पहला टास्क, [EMPHASIZE] बिल्कुल फ़्री! [LONG PAUSE] [POLITE] सीटीएफ़ एक्सेस के लिए, अकाउंट ज़रूर बना लें।",
        "Seekha hua practice se pakka hota hai. CTF Room {N}, {K} hands-on tasks ke saath. Pehla task bilkul FREE! CTF access ke liye account zaroor bana lein.")]
CTA = [("[CONFIDENT] पहले सीखो, [SHORT PAUSE] फिर प्रैक्टिस करो। [LONG PAUSE] [EXCITED] टेक गार्डियन्स डॉट इन पर, अभी एनरोल करो, [SHORT PAUSE] और सीखना स्टार्ट करो!",
        "Pehle seekho, phir practice karo. techguardians.in par abhi enroll karo — aur seekhna start karo!"),
       ("[CONFIDENT] तो देर किस बात की? [LONG PAUSE] [EXCITED] टेक गार्डियन्स डॉट इन पर जाइए, और आज ही एनरोल कीजिए!",
        "To der kis baat ki? techguardians.in par jaaiye, aur aaj hi enroll kijiye!"),
       ("[CALM] सीखो, प्रैक्टिस करो, और आगे बढ़ो। [LONG PAUSE] [EXCITED] टेक गार्डियन्स डॉट इन पर, अभी एनरोल करो!",
        "Seekho, practice karo, aur aage badho. techguardians.in par abhi enroll karo!"),
       ("[POLITE] आपकी साइबर सिक्योरिटी जर्नी, यहीं से शुरू होती है। [LONG PAUSE] [EXCITED] टेक गार्डियन्स डॉट इन पर, एनरोल कीजिए!",
        "Aapki cyber security journey yahin se shuru hoti hai. techguardians.in par enroll kijiye!"),
       ("[CONFIDENT] स्किल बनाओ, डिफ़ेंडर बनो। [LONG PAUSE] [EXCITED] टेक गार्डियन्स डॉट इन पर, अभी एनरोल करो, [SHORT PAUSE] और शुरू हो जाओ!",
        "Skill banao, defender bano. techguardians.in par abhi enroll karo — aur shuru ho jao!")]
NEXT = [("[POLITE] अगली रील में देखिए, [SHORT PAUSE] [CONFIDENT] {d}। [LONG PAUSE] [EXCITED] उसे मिस मत कीजिए!", "Agli reel me dekhiye — {r}. Use miss mat kijiye!"),
        ("[POLITE] अगली रील है, [SHORT PAUSE] [CONFIDENT] {d}। [LONG PAUSE] [POLITE] फ़ॉलो कर लीजिए, ताकि मिस न हो।", "Agli reel hai — {r}. Follow kar lijiye, taaki miss na ho."),
        ("[CONFIDENT] आगे आ रहा है, {d}। [LONG PAUSE] [POLITE] अगली रील ज़रूर देखिए।", "Aage aa raha hai — {r}. Agli reel zaroor dekhiye."),
        ("[POLITE] अगर ये रील पसंद आई, तो अगली रील, [SHORT PAUSE] {d}, [SHORT PAUSE] भी ज़रूर देखिए।", "Agar ye reel pasand aayi, to agli reel — {r} — bhi zaroor dekhiye."),
        ("[CONFIDENT] अगली रील में, {d}। [LONG PAUSE] [EXCITED] साथ बने रहिए!", "Agli reel me — {r}. Saath bane rahiye!")]

def look_for(n):
    return {name: (n * step) % count for name, count, step in LOOK}

def ref_lines(ref, kind, v=0):
    if kind == 'next':
        d, r = NEXT[v]; return d.format(d=ref['dev']), r.format(r=ref['rom'])
    return (f"[POLITE] {ref['dev']} वाली रील भी, प्रोफ़ाइल पर ज़रूर देखिए।",
            f"{ref['rom']} wali reel bhi profile par zaroor dekhiye.")

def learn_directions(vo, v=0):
    """'हमारे साथ आप सीखेंगे, कैसे A, कैसे B, और कैसे C।' -> polite opening (wording varies per reel), calm list, a pause before each item."""
    vo = vo.replace('हमारे साथ आप सीखेंगे,', f'[POLITE] {LEARN_OPEN[v][0]} [SHORT PAUSE] [CALM]', 1)
    vo = vo.replace(', और कैसे', ', [SHORT PAUSE] और कैसे').replace(', कैसे', ', [SHORT PAUSE] कैसे')
    return vo.replace('। सिर्फ़ अपने या अनुमति वाले नेटवर्क पर।', '। [LONG PAUSE] [WARNING] सिर्फ़ अपने या अनुमति वाले नेटवर्क पर।')

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
    t['look'] = look_for(n); t['iconAnim'] = ICON.get(n, 'emoji'); t['fact'] = formats[str(n)]
    t['mood'] = MOODS[(n * 2) % len(MOODS)]
    order = ['hook', 'learn', 'book', 'ctf', 'cta', 'ref']; order.insert(FACT_AT[t['fact']['kind']], 'fact'); t['order'] = order
    out.append(t)

for i, t in enumerate(out):
    s = scripts[str(t['num'])]
    if i + 1 < len(out):
        nx = out[i + 1]; ref = {'name': nx['name'], 'rom': f"Room {nx['num']} · {nx['title']}", 'dev': nx['tdev'], 'cover': nx['book'], 'kind': 'next'}
    else: ref = dict(WEBSITE_REEL, kind='seen')
    L = t['look']['lines']; lv = t['look']['learn'] % len(LEARN_OPEN)
    rv, rs = ref_lines(ref, ref['kind'], (t['num'] * 3) % len(NEXT))
    nh, kh = HI[t['num'] - 1], HI[t['tasks'] - 1]
    t['ref'] = ref; t['accountRef'] = ACCOUNT_REEL
    bv, ctv, cav = (L * 2 + 1) % 5, L, (L * 3 + 2) % 5
    vo = {'hook': s['hookVo'], 'fact': t['fact']['vo'], 'learn': learn_directions(s['learnVo'], lv),
          'book': BOOK[bv][0].format(d=t['tdev']), 'ctf': CTF[ctv][0].format(n=nh, k=kh), 'cta': CTA[cav][0], 'ref': rv}
    sub = {'hook': s['hookSub'], 'fact': t['fact']['sub'], 'learn': s['learnSub'].replace('Humare saath aap seekhenge —', LEARN_OPEN[lv][1], 1),
           'book': BOOK[bv][1].format(t=t['title']), 'ctf': CTF[ctv][1].format(N=t['num'], K=t['tasks']), 'cta': CTA[cav][1], 'ref': rs}
    t['vo'] = {k: vo[k] for k in t['order']}; t['sub'] = {k: sub[k] for k in t['order']}
    t['voStyle'] = DEFAULT_STYLE
    # two hosts: female (Kokoro hf_alpha) and male (hm_omega, later converted to the owner's cloned voice);
    # who takes which scene swaps on every other reel
    fem = {'hook', 'fact', 'cta'} if t['num'] % 2 else {'learn', 'book', 'ctf', 'ref'}
    t['voVoice'] = {k: ('hf_alpha' if k in fem else 'hm_omega') for k in t['order']}

json.dump(out, open(os.path.join(REELS, 'topics.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(out), 'topics')
