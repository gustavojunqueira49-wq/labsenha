// Painel de chamadas (TV). Mostra SOMENTE senha e local de atendimento (privacidade).
import { get } from '../api.js';
import { h, mount } from '../ui.js';

let audioCtx = null;

function chime() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const t0 = audioCtx.currentTime;
    [880, 660].forEach((f, i) => {
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.type = 'sine'; o.frequency.value = f; o.connect(g); g.connect(audioCtx.destination);
      g.gain.setValueAtTime(0.0001, t0 + i * 0.35); g.gain.exponentialRampToValueAtTime(0.5, t0 + i * 0.35 + 0.03);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.35 + 0.33);
      o.start(t0 + i * 0.35); o.stop(t0 + i * 0.35 + 0.35);
    });
  } catch { /* sem áudio */ }
  return new Promise(r => setTimeout(r, 800));
}

// "P015" -> "P 15": a voz lê letra + número em vez de soletrar zeros
export function spokenCode(code) {
  const m = /^([A-Za-z]+)[-\s]?(\d+)$/.exec(code);
  return m ? `${m[1].split('').join(' ')} ${parseInt(m[2], 10)}` : code;
}

function speak(text, lang, rate) {
  return new Promise(resolve => {
    if (!('speechSynthesis' in window)) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang || 'pt-BR'; u.rate = (rate || 90) / 100;
    const v = speechSynthesis.getVoices().find(x => x.lang === u.lang) || speechSynthesis.getVoices().find(x => x.lang.startsWith('pt'));
    if (v) u.voice = v;
    u.onend = u.onerror = () => resolve();
    speechSynthesis.speak(u);
    setTimeout(resolve, 12000);
  });
}

export async function render(root, { store, bus }) {
  let st = null, soundOn = false, announcing = Promise.resolve();
  const cfg = () => (st && st.settings) || store.settings;

  const clock = h('div', { class: 'clock' });
  const now = h('div', { class: 'now' });
  const hist = h('div', { class: 'hist' });
  const foot = h('div', { class: 'foot' });
  const head = h('div', { class: 'head' });
  const conn = h('div', { class: 'conn', style: { display: 'none' } }, 'Sem conexão com o servidor — reconectando…');
  const gate = h('div', { class: 'sound-gate' }, h('button', { class: 'btn primary', onclick: () => {
    soundOn = true; gate.remove(); chime(); if ('speechSynthesis' in window) speechSynthesis.getVoices();
    if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
  } }, '🔊 Clique para ativar som e tela cheia'));
  const tools = h('div', { class: 'tools' }, h('button', { class: 'btn sm', onclick: () => {
    if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {});
  } }, 'Tela cheia'));

  mount(root, h('div', { class: 'panel' }, clock, head, h('div', { class: 'body' }, now, hist), foot), conn, tools, gate);

  function draw() {
    const c = cfg();
    mount(head, c['hospital.logo'] ? h('img', { src: c['hospital.logo'], alt: '' }) : '',
      h('div', {}, h('div', { class: 'h1' }, c['hospital.name'] || ''), h('div', { class: 'h2' }, c['lab.name'] || '')));
    const cur = st && st.current;
    mount(now, h('div', { class: 'lbl' }, 'SENHA'),
      h('div', { class: 'code' }, cur ? cur.code : '—'),
      h('div', { class: 'place' }, cur && cur.counter ? cur.counter.name : ''));
    mount(hist, h('h3', {}, 'ÚLTIMAS CHAMADAS'),
      (st ? st.history : []).map(t => h('div', { class: 'item' }, h('span', {}, t.code), h('span', {}, t.counter ? t.counter.name : ''))));
    mount(foot, c['panel.message'] || '');
  }

  async function load() {
    try { st = await get('/panel/state'); store.settings = st.settings; conn.style.display = 'none'; draw(); }
    catch { conn.style.display = 'block'; }
  }

  function announce(ticket) {
    // atualização visual imediata; áudio entra em fila para não sobrepor chamadas
    st = st || { history: [], settings: store.settings };
    if (st.current && st.current.id !== ticket.id) {
      st.history = [st.current, ...st.history.filter(t => t.id !== ticket.id)].slice(0, cfg()['panel.show_history'] || 6);
    } else if (st.current) { st.history = st.history.filter(t => t.id !== ticket.id); }
    st.current = ticket; draw();
    now.classList.remove('flash'); void now.offsetWidth; now.classList.add('flash');
    const c = cfg();
    if (!soundOn || !c['audio.enabled']) return;
    announcing = announcing.then(async () => {
      if (c['audio.chime']) await chime();
      if (c['audio.voice'] && ticket.counter) {
        const text = (c['audio.template'] || 'Senha {senha}, dirigir-se à {guiche}.')
          .replace('{senha}', spokenCode(ticket.code)).replace('{guiche}', ticket.counter.spoken_name || ticket.counter.name);
        for (let i = 0; i < (c['audio.repeat'] || 1); i++) await speak(text, c['audio.lang'], c['audio.rate']);
      }
    }).catch(() => {});
  }

  const offs = [
    bus.on('ticket.called', d => announce(d.ticket)),
    bus.on('ticket.recalled', d => announce(d.ticket)),
    bus.on('ticket.attended', load), bus.on('ticket.no_show', load), bus.on('ticket.cancelled', load),
    bus.on('settings.updated', load), bus.on('resync', load),
    bus.onStatus(s => { conn.style.display = s === 'online' ? 'none' : 'block'; }),
  ];
  const tick = setInterval(() => { clock.textContent = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }); }, 1000);
  const poll = setInterval(load, 30000); // rede de segurança caso algum evento se perca
  await load();
  return () => { offs.forEach(o => o()); clearInterval(tick); clearInterval(poll); if ('speechSynthesis' in window) speechSynthesis.cancel(); };
}
