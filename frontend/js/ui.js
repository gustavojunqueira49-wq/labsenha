// Helpers de interface. Todo texto entra via textContent/atributos => sem XSS por construção.
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
export function mount(el, ...children) { clear(el); append(el, children); return el; }

export function toast(msg, kind = 'info', ms = 4000) {
  const box = document.getElementById('toasts');
  const t = h('div', { class: 'toast ' + kind, role: 'status' }, msg);
  box.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

export const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
export const fmtDateTime = (iso) => iso ? new Date(iso).toLocaleString('pt-BR') : '—';
export function fmtDur(sec) {
  if (sec == null) return '—';
  const m = Math.floor(sec / 60), s = sec % 60;
  return m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

export const STATUS = {
  AGUARDANDO: ['Aguardando', 'st-wait'], CHAMADA: ['Chamada', 'st-call'], RECHAMADA: ['Rechamada', 'st-call'],
  EM_ATENDIMENTO: ['Em atendimento', 'st-doing'], ATENDIDA: ['Atendida', 'st-done'],
  NAO_COMPARECEU: ['Não compareceu', 'st-noshow'], CANCELADA: ['Cancelada', 'st-cancel'],
};
export const statusBadge = (s) => h('span', { class: 'badge ' + (STATUS[s]?.[1] || '') }, STATUS[s]?.[0] || s);

export function modal(title, bodyBuilder, { wide = false } = {}) {
  return new Promise((resolve) => {
    const close = (v) => { overlay.remove(); document.removeEventListener('keydown', onKey); resolve(v); };
    const onKey = (e) => { if (e.key === 'Escape') close(null); };
    const body = h('div', { class: 'modal-body' });
    const box = h('div', { class: 'modal' + (wide ? ' wide' : ''), role: 'dialog', 'aria-modal': 'true' },
      h('div', { class: 'modal-head' }, h('h2', {}, title), h('button', { class: 'btn ghost', type: 'button', onclick: () => close(null), 'aria-label': 'Fechar' }, '✕')),
      body);
    const overlay = h('div', { class: 'overlay', onmousedown: (e) => { if (e.target === overlay) close(null); } }, box);
    document.body.appendChild(overlay);
    document.addEventListener('keydown', onKey);
    bodyBuilder(body, close);
    const first = body.querySelector('input,select,textarea,button');
    if (first) first.focus();
  });
}

export function confirmBox(message, { ok = 'Confirmar', danger = false, requireText = null } = {}) {
  return modal('Confirmação', (body, close) => {
    const input = requireText ? h('input', { type: 'text', placeholder: `Digite ${requireText}`, autocomplete: 'off' }) : null;
    const okBtn = h('button', { class: 'btn ' + (danger ? 'danger' : 'primary'), disabled: !!requireText, onclick: () => close(true) }, ok);
    if (input) input.addEventListener('input', () => { okBtn.disabled = input.value !== requireText; });
    body.append(h('p', {}, message), input || '', h('div', { class: 'row end' },
      h('button', { class: 'btn', onclick: () => close(false) }, 'Cancelar'), okBtn));
  }).then(v => v === true);
}

// Formulário genérico. fields: [{key,label,type,options,help,required,min,max,pattern}]
export function formFields(fields, values = {}) {
  const inputs = {};
  const rows = fields.map(f => {
    let input;
    const v = values[f.key] ?? f.default ?? (f.type === 'bool' ? false : '');
    if (f.type === 'bool') input = h('input', { type: 'checkbox', checked: !!v });
    else if (f.type === 'select') input = h('select', {}, f.options.map(o => h('option', { value: o.value, selected: String(o.value) === String(v) }, o.label)));
    else if (f.type === 'multi') {
      input = h('div', { class: 'multi' }, f.options.map(o => h('label', { class: 'check' },
        h('input', { type: 'checkbox', value: o.value, checked: (v || []).includes(o.value) }), ' ', o.label)));
    } else if (f.type === 'textarea') input = h('textarea', { rows: 3, maxlength: f.max || 500 }, v);
    else input = h('input', { type: f.type === 'number' ? 'number' : f.type === 'color' ? 'color' : f.type === 'password' ? 'password' : 'text',
      value: v, min: f.min, max: f.max, maxlength: f.type === 'text' ? (f.max || 200) : undefined, autocomplete: 'off', required: f.required, disabled: f.disabled });
    inputs[f.key] = input;
    return h('label', { class: 'field' + (f.type === 'bool' ? ' inline' : '') }, h('span', { class: 'lbl' }, f.label), input, f.help ? h('small', {}, f.help) : '');
  });
  const read = () => {
    const out = {};
    for (const f of fields) {
      const el = inputs[f.key];
      if (f.type === 'bool') out[f.key] = el.checked;
      else if (f.type === 'number') out[f.key] = el.value === '' ? null : Number(el.value);
      else if (f.type === 'select') out[f.key] = el.value === '' ? null : (f.numeric ? Number(el.value) : el.value);
      else if (f.type === 'multi') out[f.key] = [...el.querySelectorAll('input:checked')].map(i => Number(i.value));
      else out[f.key] = el.value;
    }
    return out;
  };
  return { rows, read };
}

export function table(columns, rows, { empty = 'Nenhum registro.' } = {}) {
  if (!rows.length) return h('p', { class: 'muted' }, empty);
  return h('div', { class: 'table-wrap' }, h('table', {},
    h('thead', {}, h('tr', {}, columns.map(c => h('th', {}, c.label)))),
    h('tbody', {}, rows.map(r => h('tr', {}, columns.map(c => h('td', { class: c.class || '' }, c.render ? c.render(r) : (r[c.key] ?? '')))))),
  ));
}

// Gráfico de barras em SVG (sem bibliotecas externas).
export function barChart(data, { width = 640, height = 200, series }) {
  const NS = 'http://www.w3.org/2000/svg';
  const max = Math.max(1, ...data.flatMap(d => series.map(s => d[s.key])));
  const bw = (width - 30) / data.length;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height + 24}`);
  svg.setAttribute('class', 'chart'); svg.setAttribute('role', 'img');
  const add = (n, a, txt) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); if (txt != null) e.textContent = txt; svg.appendChild(e); return e; };
  add('line', { x1: 28, y1: height, x2: width, y2: height, stroke: 'var(--line)' });
  add('text', { x: 0, y: 10, class: 'axis' }, String(max));
  data.forEach((d, i) => {
    const sw = (bw - 4) / series.length;
    series.forEach((s, j) => {
      const v = d[s.key], bh = (v / max) * (height - 14);
      const r = add('rect', { x: 30 + i * bw + j * sw, y: height - bh, width: Math.max(2, sw - 1), height: bh, fill: s.color, rx: 2 });
      const t = document.createElementNS(NS, 'title'); t.textContent = `${d.label} — ${s.label}: ${v}`; r.appendChild(t);
    });
    if (data.length <= 12 || i % 2 === 0) add('text', { x: 30 + i * bw + bw / 2, y: height + 15, 'text-anchor': 'middle', class: 'axis' }, d.label);
  });
  return svg;
}
