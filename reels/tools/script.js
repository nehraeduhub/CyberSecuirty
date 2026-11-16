// SEO caption (Instagram / Facebook / YouTube Shorts) + voiceover script for a reel.
const V = require('../data/voice.js');
const mmss = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const camel = s => '#' + s.replace(/[^A-Za-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean).map(w => w[0].toUpperCase() + w.slice(1)).join('');

const BRAND = ['#CyberSafeJhunjhunu', '#CSJ', '#TechGuardians', '#CyberFouji', '#RJNehra'];
const LOCAL = ['#Jhunjhunu', '#JhunjhunuNews', '#Shekhawati', '#Rajasthan', '#RajasthanNews', '#RajasthanPolice', '#Sikar', '#Churu'];
const TOPIC = ['#CyberCrime', '#CyberSecurity', '#CyberAwareness', '#CyberSafety', '#OnlineFraud', '#ScamAlert', '#FraudAlert',
  '#CyberJagrukta', '#SaavdhanRahein', '#DigitalIndia', '#1930', '#CyberDost', '#StaySafeOnline'];
const REACH = ['#Reels', '#ReelsIndia', '#InstaReels', '#TrendingReels', '#ViralReels', '#Explore', '#HindiReels'];
const HINDI = ['#साइबर_सुरक्षा', '#साइबर_ठगी', '#सावधान_रहें', '#झुंझुनूं', '#राजस्थान'];

function caption({ crime: c, name, day }) {
  const tagCrime = camel(c.tag);
  const kw = c.tag.toLowerCase();
  const L = [];
  L.push(`FILE: ${name}`, '');
  L.push('══════ INSTAGRAM / FACEBOOK CAPTION ══════', '');
  L.push(`🚨 ${c.title} से सावधान! | ${c.tag} | Cyber Safe Jhunjhunu`, '');
  L.push(`${c.hook}`, `${c.hookSub}।`, '');
  L.push('❓ ठगी कैसे होती है?');
  c.steps.forEach((s, i) => L.push(`${i + 1}️⃣ ${s}`));
  L.push('', '🚩 खतरे के संकेत:'); c.flags.forEach(s => L.push(`🔴 ${s}`));
  L.push('', '🛡️ ऐसे बचें:'); c.tips.forEach(s => L.push(`✅ ${s}`));
  L.push('', '⚙️ अभी करें ये फोन सेटिंग:');
  c.settings.forEach(s => L.push(`🔧 ${s.path.join(' › ')} › ${s.label} → ${s.on ? 'ON' : 'OFF'}`));
  L.push('', '📞 ठगी हो जाए तो तुरंत साइबर हेल्पलाइन 1930 पर कॉल करें', '🌐 शिकायत: cybercrime.gov.in', '');
  L.push('👉 ये वीडियो परिवार और दोस्तों के WhatsApp ग्रुप में भेजें। किसी अपने को ठगी से बचाएँ 🙏');
  L.push('💬 कमेंट करें: क्या आपके पास भी ऐसा मैसेज / कॉल आया है?');
  L.push('🔔 रोज़ एक नया साइबर क्राइम और बचाव जानने के लिए Follow करें', '');
  L.push('अब हम किसी के साथ कोई साइबर क्राइम नहीं होने देंगे 🇮🇳');
  L.push('🎙️ RJ Nehra | Master in AI Cyber Security | Cyber Fouji', '📍 Cyber Safe Jhunjhunu (झुंझुनूं, राजस्थान) × TechGuardians', '');
  const tags = [...BRAND, tagCrime, ...TOPIC, ...LOCAL, ...HINDI, ...REACH];
  L.push(tags.join(' '), '');
  L.push('══════ INSTAGRAM (max 5 hashtags, new rule) ══════', '');
  L.push(['#CyberSafeJhunjhunu', tagCrime, '#CyberAwareness', '#Rajasthan', '#ScamAlert'].join(' '), '');
  L.push('══════ YOUTUBE SHORTS ══════', '');
  L.push(`TITLE: ${c.title} से सावधान! 🚨 ${c.tag} | 1930 | #Shorts`.slice(0, 100), '');
  L.push('DESCRIPTION:', `${c.hook} ${c.hookSub}। इस वीडियो में जानिए ${c.title} कैसे होता है, इसके संकेत, बचाव और फोन की ज़रूरी सेटिंग।`,
    'ठगी हो तो तुरंत 1930 पर कॉल करें या cybercrime.gov.in पर शिकायत करें।', 'RJ Nehra | Cyber Safe Jhunjhunu × TechGuardians', '#Shorts #CyberCrime #CyberAwareness #Rajasthan #Jhunjhunu', '');
  L.push('TAGS: ' + [c.title, kw, 'cyber crime', 'cyber fraud', 'online fraud hindi', 'cyber awareness hindi', 'cyber safe jhunjhunu', 'jhunjhunu', 'rajasthan cyber crime',
    'scam alert', '1930 helpline', 'rj nehra', 'tech guardians', 'cyber fouji', 'how to avoid online fraud', 'phone security settings'].join(', '), '');
  L.push('══════ SEO KEYWORDS ══════', '');
  L.push([c.title, kw, `${kw} kaise hota hai`, `${kw} se kaise bache`, 'cyber crime awareness in hindi', 'online fraud se kaise bache',
    'rajasthan cyber fraud news', 'jhunjhunu cyber crime', 'cyber helpline 1930', 'mobile security settings hindi'].join(' | '), '');
  L.push('BEST TIME TO POST: शाम 7 से 9 बजे (IST)', '');
  return L.join('\n');
}

function script({ crime: c, T, duration, voice }) {
  const lines = V.lines(c);
  const L = [`VOICEOVER: ${c.title} (${mmss(duration)})`, 'अपनी आवाज़ में रिकॉर्ड करने के लिए: voice/' + c.id + '.mp3 रखें और render दोबारा चलाएँ।', ''];
  for (const v of voice) {
    const l = lines.find(x => x.key === v.key);
    L.push(`[${mmss(v.t)}] (${v.key})  ${l ? l.say : ''}`);
  }
  return L.join('\n') + '\n';
}
function voiceReport({ crime: c, name, qc, voice, duration, voiceName }) {
  const at = Object.fromEntries(voice.map(v => [v.key, v]));
  const ts = k => at[k] ? `${mmss(at[k].t)}.${String(Math.round((at[k].t % 1) * 10))}` : '--:--';
  const pass = qc.filter(r => r.status === 'PASS').length;
  const fixed = qc.filter(r => r.corrections.length);
  const L = [];
  L.push(`VOICE REPORT: ${name}`, `${c.title} (${c.tag})`, `Voice: ${voiceName} (Piper hi_IN, offline)  |  Reel: ${mmss(duration)}  |  Lines: ${qc.length}`, '');
  L.push(`FINAL QC STATUS: ${pass === qc.length ? 'PASS' : 'PASS WITH REVIEW'} (${pass}/${qc.length} lines pass, ${qc.length - pass} need a human listen)`, '');
  L.push('How QC works: every take is transcribed by Whisper large-v3-turbo and compared with the script',
    '(CER = character error rate; spelling-equivalent forms count as equal). Also checked: speaking rate,',
    'unplanned gaps, clipping, loudness. 3 takes per line; failing lines get correction rounds',
    '(slower, steadier) and only those lines are regenerated. Final listening by a human is still advised.', '');
  L.push('1) FINAL SCRIPT WITH VOICE DIRECTIONS', '-'.repeat(60));
  for (const r of qc) L.push(`[${ts(r.key)}] (${r.key})`, `  ${r.markers}`, '');
  L.push('2) SENTENCE-WISE VOICE DIRECTION SHEET', '-'.repeat(60));
  L.push('time    | line        | pace   pitch  gain  | directions / emphasis');
  for (const r of qc) for (const ch of r.chunks) {
    const p = ch.params;
    L.push(`${ts(r.key).padEnd(7)} | ${r.key.padEnd(11)} | ${String(p.ls).padEnd(6)} ${(p.pitch >= 0 ? '+' : '') + p.pitch.toFixed(1)}st ${(p.gain >= 0 ? '+' : '') + p.gain.toFixed(1)}dB | ${ch.emph ? '[EMPHASIZE ' + ch.emph + '] ' : ''}${ch.text}${ch.pause_after ? `  (+${ch.pause_after}s pause)` : ''}`);
  }
  L.push('', 'pace = Piper length_scale (higher = slower); pitch in semitones; gain relative to the reel loudness.', '');
  L.push('3) TIMESTAMP-WISE CORRECTION REPORT', '-'.repeat(60));
  if (!fixed.length) L.push('No corrections needed: every line passed on its first round.');
  for (const r of fixed) {
    L.push(`[${ts(r.key)}] ${r.key}: "${r.say}"`);
    for (const k of r.corrections) L.push(`   round ${k.round}: problem = ${k.problem}`, `            action  = ${k.action}`);
    const first = r.attempts[0];
    L.push(`   result: take ${r.chosen} chosen, CER ${first.cer} -> ${r.final.cer}; status ${r.status}`, '');
  }
  L.push('', '4) LINE-BY-LINE QC RESULT', '-'.repeat(60));
  for (const r of qc) {
    L.push(`[${ts(r.key)}] ${r.status.padEnd(6)} ${r.key.padEnd(11)} CER ${String(r.final.cer).padEnd(5)} rate ${r.final.rate} ch/s  takes ${r.attempts.length}${r.final.issues.length ? '  issues: ' + r.final.issues.join('; ') : ''}`);
    L.push(`         ASR heard: ${r.final.hyp}`);
  }
  L.push('', '5) KNOWN LIMITS OF THIS AI VOICE', '-'.repeat(60),
    '- Piper has no emotion tags: directions are realised through pace, pitch, expressiveness, loudness and pauses.',
    '  [WHISPER] is not used (the model cannot whisper naturally).',
    '- The aspirated "झ" (as in झुंझुनूं) comes out close to "ज" in all three Hindi voices; no spelling fixes it.',
    '  Context keeps it clear; a human recording (voice/<crime-id>.mp3) avoids it completely.',
    '- ASR checks words, not feeling: emotion and naturalness still need one human listen before posting.');
  return L.join('\n') + '\n';
}
module.exports = { caption, script, voiceReport };
