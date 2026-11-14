/*
 * Voiceover lines + audio-synced timeline for a reel.
 * Shared by the browser template and the Node renderer (UMD, like crimes.js).
 *
 *  lines(crime)                -> [{key, text, say}]  text = on-screen, say = what the voice reads
 *  timing(crime, durations)    -> every scene/item start time, sized to the real voice clip lengths.
 *                                 durations = {key: seconds}; when missing, estimated from text length.
 */
(function (root) {
  /* ---------- Hindi pronunciation helpers (Piper hi_IN reads Devanagari best) ---------- */
  const ONES = ['शून्य','एक','दो','तीन','चार','पाँच','छह','सात','आठ','नौ','दस','ग्यारह','बारह','तेरह','चौदह','पंद्रह','सोलह','सत्रह','अठारह','उन्नीस',
    'बीस','इक्कीस','बाईस','तेईस','चौबीस','पच्चीस','छब्बीस','सत्ताईस','अट्ठाईस','उनतीस','तीस','इकतीस','बत्तीस','तैंतीस','चौंतीस','पैंतीस','छत्तीस','सैंतीस','अड़तीस','उनतालीस',
    'चालीस','इकतालीस','बयालीस','तैंतालीस','चवालीस','पैंतालीस','छियालीस','सैंतालीस','अड़तालीस','उनचास','पचास','इक्यावन','बावन','तिरपन','चौवन','पचपन','छप्पन','सत्तावन','अट्ठावन','उनसठ',
    'साठ','इकसठ','बासठ','तिरसठ','चौंसठ','पैंसठ','छियासठ','सड़सठ','अड़सठ','उनहत्तर','सत्तर','इकहत्तर','बहत्तर','तिहत्तर','चौहत्तर','पचहत्तर','छिहत्तर','सतहत्तर','अठहत्तर','उन्यासी',
    'अस्सी','इक्यासी','बयासी','तिरासी','चौरासी','पचासी','छियासी','सत्तासी','अट्ठासी','नवासी','नब्बे','इक्यानवे','बानवे','तिरानवे','चौरानवे','पचानवे','छियानवे','सत्तानवे','अट्ठानवे','निन्यानवे'];
  function num(n) {
    n = Math.floor(n); if (n < 100) return ONES[n];
    const parts = [];
    const cr = Math.floor(n / 1e7); n %= 1e7; if (cr) parts.push(num(cr) + ' करोड़');
    const la = Math.floor(n / 1e5); n %= 1e5; if (la) parts.push(num(la) + ' लाख');
    const th = Math.floor(n / 1e3); n %= 1e3; if (th) parts.push(num(th) + ' हज़ार');
    const hu = Math.floor(n / 100); n %= 100; if (hu) parts.push(ONES[hu] + ' सौ');
    if (n) parts.push(ONES[n]);
    return parts.join(' ');
  }
  const WORDS = [
    ['cybercrime.gov.in', 'साइबर क्राइम डॉट जी ओ वी डॉट इन'], ['techguardians.in', 'टेक गार्डियंस डॉट इन'],
    ['echallan.parivahan.gov.in', 'ई चालान परिवहन की सरकारी वेबसाइट'], ['pmkisan.gov.in', 'पी एम किसान की सरकारी वेबसाइट'], ['joinindianarmy.nic.in', 'ज्वाइन इंडियन आर्मी की सरकारी वेबसाइट'],
    ['Media auto-download', 'मीडिया ऑटो डाउनलोड'], ['auto-download', 'ऑटो डाउनलोड'], ['Two-factor authentication', 'टू फैक्टर ऑथेंटिकेशन'],
    ['Play Store', 'प्ले स्टोर'], ['Play Protect', 'प्ले प्रोटेक्ट'], ['WhatsApp', 'व्हाट्सऐप'], ['Telegram', 'टेलीग्राम'], ['Instagram', 'इंस्टाग्राम'],
    ['Facebook', 'फेसबुक'], ['YouTube', 'यूट्यूब'], ['Google Lens', 'गूगल लेंस'], ['Google', 'गूगल'], ['Amazon', 'अमेज़न'], ['AnyDesk', 'एनी डेस्क'], ['TeamViewer', 'टीम व्यूअर'],
    ['QuickSupport', 'क्विक सपोर्ट'], ['Chrome', 'क्रोम'], ['Safe Browsing', 'सेफ ब्राउज़िंग'], ['Accessibility', 'एक्सेसिबिलिटी'], ['Masked Aadhaar', 'मास्क्ड आधार'],
    ['mAadhaar', 'एम आधार'], ['Unlock', 'अनलॉक'], ['LOCK', 'लॉक'], ['Lock', 'लॉक'], ['Report', 'रिपोर्ट'], ['Debit', 'डेबिट'], ['Charging only', 'चार्जिंग ओनली'],
    ['Auto-connect', 'ऑटो कनेक्ट'], ['Allow', 'अलाउ'], ['Trust', 'ट्रस्ट'], ['Diwali', 'दिवाली'], ['Mega Sale', 'मेगा सेल'], ['iPhone', 'आईफोन'], ['DP', 'डी पी'],
    ['eSIM', 'ई सिम'], ['SIM', 'सिम'], ['WiFi', 'वाई फाई'], ['OTP', 'ओ टी पी'], ['APK', 'ए पी के'], ['SMS', 'एस एम एस'], ['UPI', 'यू पी आई'], ['PIN', 'पिन'],
    ['KYC', 'के वाई सी'], ['e-KYC', 'ई के वाई सी'], ['PDF', 'पी डी एफ'], ['QR', 'क्यू आर'], ['OLX', 'ओ एल एक्स'], ['CBI', 'सी बी आई'], ['ED', 'ई डी'], ['RBI', 'आर बी आई'],
    ['SEBI', 'सेबी'], ['NBFC', 'एन बी एफ सी'], ['VIP', 'वी आई पी'], ['GST', 'जी एस टी'], ['CVV', 'सी वी वी'], ['URL', 'यू आर एल'], ['COD', 'सी ओ डी'], ['USB', 'यू एस बी'],
    ['IPO', 'आई पी ओ'], ['NRI', 'एन आर आई'], ['AePS', 'ए ई पी एस'], ['ECHS', 'ई सी एच एस'], ['PPO', 'पी पी ओ'], ['CDA', 'सी डी ए'], ['CSC', 'सी एस सी'], ['PAN', 'पैन'],
    ['RTO', 'आर टी ओ'], ['AI', 'ए आई'], ['ID', 'आई डी'], ['RJ', 'आर जे'], ['AC', 'ए सी'], ['HR', 'एच आर'], ['PM', 'पी एम'], ['CVV', 'सी वी वी'], ['5G', 'फाइव जी'],
    ['.APK', 'ए पी के'], ['.top', 'डॉट टॉप'], ['.xyz', 'डॉट एक्स वाई ज़ेड'], ['bit.ly', 'बिट डॉट ली'], ['Meta', 'मेटा'], ['Contacts', 'कॉन्टैक्ट्स'], ['Photos', 'फोटोज़'], ['Gallery', 'गैलरी'],
  ].sort((a, b) => b[0].length - a[0].length);
  const LETTERS = { A:'ए',B:'बी',C:'सी',D:'डी',E:'ई',F:'एफ',G:'जी',H:'एच',I:'आई',J:'जे',K:'के',L:'एल',M:'एम',N:'एन',O:'ओ',P:'पी',Q:'क्यू',R:'आर',S:'एस',T:'टी',U:'यू',V:'वी',W:'डब्ल्यू',X:'एक्स',Y:'वाई',Z:'ज़ेड' };

  function speak(s) {
    s = String(s);
    s = s.replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu, ' ');
    s = s.replace(/₹\s?([\d,]+)/g, (_, d) => num(+d.replace(/,/g, '')) + ' रुपये');
    s = s.replace(/\b1930\b/g, 'उन्नीस सौ तीस');
    for (const [en, hi] of WORDS) s = s.split(en).join(hi);
    s = s.replace(/(\d[\d,]*)%/g, (_, d) => num(+d.replace(/,/g, '')) + ' प्रतिशत');
    s = s.replace(/\d[\d,]*/g, d => num(+d.replace(/,/g, '')));
    s = s.replace(/\b[A-Z]{2,5}\b/g, w => w.split('').map(c => LETTERS[c]).join(' '));
    s = s.replace(/[\/|•>›"“”'‘’]/g, ' ').replace(/\s+/g, ' ').replace(/\s+([।,!?])/g, '$1').trim();
    if (!/[।!?.]$/.test(s)) s += '।';
    return s;
  }

  const ORD = ['पहली', 'दूसरी', 'तीसरी', 'चौथी'];
  const NUMS = ['पहला', 'दूसरा', 'तीसरा', 'चौथा'];

  function lines(c) {
    const L = [];
    const add = (key, text, say) => L.push({ key, text, say: speak(say == null ? text : say) });
    add('hook', c.hook);
    add('intro', '', `राम राम सा! मैं आर जे नेहरा, साइबर सेफ झुंझुनूं से। आज का साइबर क्राइम, ${c.title}। अंत तक देखिए, फोन की सेटिंग भी बताऊँगा।`);
    c.steps.forEach((s, i) => add('how.' + i, s));
    add('flags.title', '', 'खतरे के संकेत।');
    c.flags.forEach((s, i) => add('flags.' + i, s));
    add('tips.title', '', 'ऐसे बचें।');
    c.tips.forEach((s, i) => add('tips.' + i, s));
    add('set.title', '', 'अब फोन में ये सेटिंग कीजिए।');
    c.settings.forEach((s, i) => add('set.' + i, s.label, `${s.say || `${s.app} में ${s.label} को ${s.on ? 'ऑन' : 'बंद'} कीजिए`}`));
    add('help', '', 'ठगी हो जाए, तो तुरंत उन्नीस सौ तीस पर कॉल कीजिए। साइबर क्राइम डॉट जी ओ वी डॉट इन पर शिकायत कीजिए, और बैंक से खाता ब्लॉक करवाइए।');
    add('outro', '', 'अब हम किसी के साथ, कोई साइबर क्राइम नहीं होने देंगे। साइबर सेफ झुंझुनूं को फॉलो और शेयर कीजिए। जय हिंद!');
    return L;
  }

  /* ---------- timeline ---------- */
  function timing(c, durations) {
    const ls = lines(c);
    const D = k => {
      if (durations && durations[k] != null) return durations[k];
      const l = ls.find(x => x.key === k); return l ? Math.max(1.2, l.say.length * 0.072) : 0;
    };
    const voice = []; // {key, t, d}
    const V = (k, t) => { if (!ls.find(x => x.key === k)) return t; voice.push({ key: k, t: +t.toFixed(3), d: D(k) }); return t + D(k); };
    const GAP = 0.35;
    const T = {}, X = {};
    let t = 0;
    // HOOK
    T.hook = 0; t = V('hook', 0.7); t = Math.max(t + 0.45, 5);
    // TITLE / INTRO
    T.title = t; t = V('intro', T.title + 0.3); t = Math.max(t + 0.4, T.title + 5);
    // HOW
    T.how = t; let u = t + 0.3;
    X.stepT = []; X.stepLen = [];
    c.steps.forEach((_, i) => { X.stepT.push(u - T.how); const e = V('how.' + i, u + 0.25); const len = Math.max(4.4, e - u + 0.6); X.stepLen.push(len); u += len; });
    // first message bubbles during how.title + step 1, otp at step 3, debit at step 4
    const msgSpan = Math.min(1.6, (X.stepT[0] + X.stepLen[0] - 1.0) / Math.max(1, c.messages.length));
    X.msgT = c.messages.map((_, i) => 0.9 + i * msgSpan);
    X.otpT = X.stepT[(c.notif && c.notif.at != null) ? c.notif.at : 2] + 0.6; X.debitT = X.stepT[3] + 0.9;
    t = u;
    // FLAGS
    T.flags = t; u = V('flags.title', t + 0.2) + GAP; X.flagT = [];
    c.flags.forEach((_, i) => { X.flagT.push(u - T.flags); u = V('flags.' + i, u + 0.15) + GAP; });
    X.flagEnd = u - T.flags; t = u + 1.4;
    // TIPS
    T.tips = t; u = V('tips.title', t + 0.2) + GAP; X.tipT = [];
    c.tips.forEach((_, i) => { X.tipT.push(u - T.tips); u = V('tips.' + i, u + 0.15) + GAP; });
    t = u + 0.4;
    // SETTINGS
    T.settings = t; u = V('set.title', t + 0.3) + 0.2; X.set = [];
    c.settings.forEach((_, i) => { const b = u - T.settings; const e = V('set.' + i, u + 0.2); const len = Math.max(4.8, e - u + 1.1); X.set.push({ b, len }); u += len; });
    t = u;
    // HELP
    T.help = t; u = V('help', t + 0.4); X.helpT = [0.3, 0.9, (u - t) * 0.45, (u - t) * 0.62, (u - t) * 0.8];
    t = Math.max(u + 0.5, t + 6);
    // OUTRO
    T.outro = t; u = V('outro', t + 0.5); t = Math.max(u + 1.2, t + 6);
    T.end = +t.toFixed(3);
    return { T, X, voice, lines: ls };
  }

  const api = { lines, timing, speak, num };
  if (typeof module !== 'undefined') module.exports = api; else root.VOICE = api;
})(this);
