// Builds the voiceover script (with timings) + Instagram/Facebook caption for a reel.
const mmss = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
function script({ crime: c, T, duration }) {
  const r = (a, b) => `[${mmss(a)} - ${mmss(b)}]`;
  const L = [];
  L.push(`REEL: ${c.title} (${c.tag})`, `Duration: ${mmss(duration)}`, '');
  L.push('=== VOICEOVER SCRIPT (RJ Nehra) ===', 'इसे अपनी आवाज़ में रिकॉर्ड करके voice/' + c.id + '.mp3 में रखें, render दोबारा चलाएँ।', '');
  L.push(`${r(T.hook, T.title)} HOOK`, `${c.hook} ${c.hookSub}।`, '');
  L.push(`${r(T.title, T.how)} INTRO`, `राम राम सा! मैं RJ नेहरा, साइबर सेफ झुंझुनूं से। आज का साइबर क्राइम है: ${c.title}। वीडियो आखिर तक देखिए, अंत में फोन की ज़रूरी सेटिंग बताऊँगा।`, '');
  L.push(`${r(T.how, T.flags)} ठगी ऐसे होती है`);
  c.steps.forEach((s, i) => L.push(`  ${i + 1}. ${s}।`));
  L.push('');
  L.push(`${r(T.flags, T.tips)} खतरे के 3 संकेत`, '  ' + c.flags.join('। ') + '। ये दिखे तो रुक जाइए।', '');
  L.push(`${r(T.tips, T.settings)} ऐसे बचें`);
  c.tips.forEach(s => L.push(`  • ${s}।`));
  L.push('');
  L.push(`${r(T.settings, T.help)} अभी करें ये सेटिंग (वीडियो रोककर साथ-साथ करें)`);
  c.settings.forEach((s, i) => L.push(`  ${i + 1}. ${s.path.join(' > ')} > "${s.label}" को ${s.on ? 'ON' : 'OFF'} करें।`));
  L.push('');
  L.push(`${r(T.help, T.outro)} ठगी हो जाए तो`, '  घबराएँ नहीं, तुरंत 1930 पर कॉल करें। पहला एक घंटा सबसे कीमती है। cybercrime.gov.in पर शिकायत दर्ज करें और बैंक को कॉल करके खाता या कार्ड ब्लॉक करवाएँ।', '');
  L.push(`${r(T.outro, duration)} OUTRO`, '  अब हम किसी के साथ कोई साइबर क्राइम नहीं होने देंगे। आप भी साइबर फौजी बनिए: वीडियो को फॉलो, शेयर कीजिए और परिवार के WhatsApp ग्रुप में ज़रूर भेजिए। जय हिंद!', '');
  L.push('=== CAPTION ===', '');
  L.push(`🚨 ${c.title}: ${c.hook}`, '', `❓ ठगी ऐसे होती है:`);
  c.steps.forEach((s, i) => L.push(`${i + 1}️⃣ ${s}`));
  L.push('', '🛡️ ऐसे बचें:'); c.tips.forEach(s => L.push(`✅ ${s}`));
  L.push('', '⚙️ फोन सेटिंग:'); c.settings.forEach(s => L.push(`🔧 ${s.path.join(' › ')} › ${s.label}: ${s.on ? 'ON' : 'OFF'}`));
  L.push('', '📞 ठगी हो तो तुरंत 1930 | 🌐 cybercrime.gov.in', '', 'अब हम किसी के साथ कोई साइबर क्राइम नहीं होने देंगे 🇮🇳',
    'RJ Nehra | Master in AI Cyber Security | TechGuardians | Cyber Fouji', '');
  const tag = '#' + c.tag.replace(/[^A-Za-z0-9 ]/g, '').split(' ').map(w => w[0].toUpperCase() + w.slice(1)).join('');
  L.push(`#CyberSafeJhunjhunu #TechGuardians #CyberFouji #RJNehra #Jhunjhunu #Shekhawati #Rajasthan #RajasthanPolice #CyberCrime #CyberAwareness #CyberSafety #OnlineFraud #Scam #1930 ${tag} #साइबर_सुरक्षा #झुंझुनूं`);
  return L.join('\n') + '\n';
}
module.exports = { script };
