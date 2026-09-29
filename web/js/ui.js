// Tiny DOM toolkit. All dynamic text goes through textContent => no HTML injection from API data.
export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'value') el.value = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
export const $ = (sel, root = document) => root.querySelector(sel);
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

const ICONS = {
  map: 'M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15M15 6v15',
  dash: 'M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z',
  bag: 'M4 8h16l-1 12H5zM9 8V6a3 3 0 016 0v2',
  compass: 'M12 21a9 9 0 100-18 9 9 0 000 18zM15.5 8.5l-2 5-5 2 2-5z',
  search: 'M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3',
  box: 'M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  star: 'M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z',
  cog: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19 12a7 7 0 00-.1-1l2-1.5-2-3.4-2.4 1a7 7 0 00-1.7-1L14.5 3h-4l-.3 3.1a7 7 0 00-1.7 1l-2.4-1-2 3.4 2 1.5a7 7 0 000 2l-2 1.5 2 3.4 2.4-1a7 7 0 001.7 1l.3 3.1h4l.3-3.1a7 7 0 001.7-1l2.4 1 2-3.4-2-1.5c.1-.3.1-.7.1-1z',
  pulse: 'M3 12h4l3-8 4 16 3-8h4', info: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v6M12 7.5v.01',
};
export function icon(name) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', ICONS[name] || ICONS.info);
  s.append(p);
  return s;
}

export const eur = (v, d = 0) => v == null ? '—' : new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: d }).format(v);
export const num = (v) => v == null ? '—' : new Intl.NumberFormat('en-GB').format(Math.round(v));
export const compact = (v) => v == null ? '—' : new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(v);
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const fdate = (s) => { if (!s) return '—'; const d = new Date(s.length === 10 ? s + 'T00:00:00' : s); return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); };
export const dur = (min) => min == null ? '—' : `${Math.floor(min / 60)}h ${String(Math.round(min % 60)).padStart(2, '0')}m`;
export const ago = (ts) => { if (!ts) return 'never'; const s = Date.now() / 1000 - ts; return s < 90 ? 'just now' : s < 5400 ? `${Math.round(s / 60)} min ago` : s < 129600 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`; };

export function badge(text, kind = '', title = '') { return h('span', { class: `badge ${kind}`, title }, text); }
export const mockBadge = () => badge('MOCK', 'mock', 'Synthetic data for development - NOT a real price');
export const estBadge = (t = 'ESTIMATE') => badge(t, 'est', 'Heuristic estimate, not live data');
export function statusBadge(sec) {
  if (!sec) return null;
  const m = { ok: ['OK', 'ok'], stale: ['STALE CACHE', 'stale'], estimate: ['ESTIMATE', 'est'], unavailable: ['UNAVAILABLE', 'mock'], not_implemented: ['NOT IMPLEMENTED', 'mock'] }[sec.status];
  return m ? badge(m[0], m[1], sec.source || '') : null;
}

export function toast(msg, kind = '') {
  const t = h('div', { class: `toast ${kind}` }, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), kind === 'bad' ? 7000 : 3500);
}
export function modal(title, body, actions = []) {
  const root = document.getElementById('modal-root');
  const close = () => clear(root);
  const back = h('div', { class: 'back', onclick: (e) => { if (e.target === back) close(); } },
    h('div', { class: 'modal' }, h('div', { class: 'row spread' }, h('h2', { style: { margin: 0 } }, title), h('button', { class: 'ghost', onclick: close }, '✕')), body,
      actions.length ? h('div', { class: 'row', style: { marginTop: '14px', justifyContent: 'flex-end' } }, actions.map((a) => h('button', { class: `btn ${a.cls || ''}`, onclick: () => a.onclick(close) }, a.label))) : null));
  clear(root).append(back);
  return close;
}
export const loading = (msg = 'Loading…') => h('div', { class: 'empty' }, h('span', { class: 'spinner' }), ' ', msg);
export const errorBox = (e) => h('div', { class: 'err' }, '⚠ ', e.message || String(e));
export const empty = (msg) => h('div', { class: 'empty' }, msg);

export function field(label, input) { return h('label', {}, label, input); }
export function select(options, value, attrs = {}) {
  return h('select', attrs, options.map((o) => { const [v, t] = Array.isArray(o) ? o : [o, o]; return h('option', { value: v, selected: String(v) === String(value) }, t); }));
}

// ---- SVG charts (no library) ------------------------------------------------
const NS = 'http://www.w3.org/2000/svg';
const svg = (tag, attrs = {}, ...kids) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); kids.forEach((k) => e.append(k)); return e; };
const stxt = (x, y, t, a = {}) => { const e = svg('text', { x, y, ...a }); e.textContent = t; return e; };

export function barChart(data, { w = 420, hgt = 170, color = 'var(--accent)', fmt = num } = {}) {
  const entries = Object.entries(data);
  if (!entries.length) return empty('No data yet');
  const max = Math.max(...entries.map(([, v]) => v), 1), pad = 22, bw = (w - pad) / entries.length;
  const s = svg('svg', { class: 'chart', viewBox: `0 0 ${w} ${hgt}`, width: '100%' });
  entries.forEach(([k, v], i) => {
    const bh = (hgt - 40) * v / max, x = pad + i * bw;
    s.append(svg('rect', { x: x + 4, y: hgt - 22 - bh, width: Math.max(4, bw - 8), height: bh, rx: 4, fill: color }));
    s.append(stxt(x + bw / 2, hgt - 8, k, { 'text-anchor': 'middle' }));
    s.append(stxt(x + bw / 2, hgt - 26 - bh, fmt(v), { 'text-anchor': 'middle' }));
  });
  return s;
}
export function lineChart(points, { w = 520, hgt = 180, key = 'price_eur', label = 'date' } = {}) {
  if (points.length < 2) return empty(points.length ? 'One observation so far - the chart appears after more.' : 'No observations yet');
  const ys = points.map((p) => p[key]), lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || 1, pad = 34;
  const X = (i) => pad + (w - pad - 8) * i / (points.length - 1), Y = (v) => 14 + (hgt - 40) * (1 - (v - lo) / span);
  const s = svg('svg', { class: 'chart', viewBox: `0 0 ${w} ${hgt}`, width: '100%' });
  s.append(svg('polyline', { points: points.map((p, i) => `${X(i)},${Y(p[key])}`).join(' '), fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2 }));
  points.forEach((p, i) => { const c = svg('circle', { cx: X(i), cy: Y(p[key]), r: 3, fill: 'var(--accent)' }); c.append(svg('title', {}, `${p[label]}: ${eur(p[key])}`)); s.append(c); });
  s.append(stxt(2, 16, eur(hi)), stxt(2, hgt - 26, eur(lo)), stxt(pad, hgt - 8, points[0][label]), stxt(w - 8, hgt - 8, points.at(-1)[label], { 'text-anchor': 'end' }));
  return s;
}
export function donut(data, colors = ['#0ea5e9', '#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#14b8a6']) {
  const entries = Object.entries(data), tot = entries.reduce((a, [, v]) => a + v, 0);
  if (!tot) return empty('No data yet');
  const s = svg('svg', { class: 'chart', viewBox: '0 0 200 130', width: '100%' });
  let a0 = -Math.PI / 2;
  entries.forEach(([k, v], i) => {
    const a1 = a0 + 2 * Math.PI * v / tot, big = a1 - a0 > Math.PI ? 1 : 0, R = 52, r = 32, cx = 62, cy = 65;
    const p = (a, rad) => `${cx + rad * Math.cos(a)},${cy + rad * Math.sin(a)}`;
    const path = entries.length === 1 ? `M${p(0, R)} A${R},${R} 0 1 1 ${p(Math.PI, R)} A${R},${R} 0 1 1 ${p(0, R)} M${p(0, r)} A${r},${r} 0 1 0 ${p(Math.PI, r)} A${r},${r} 0 1 0 ${p(0, r)}`
      : `M${p(a0, R)} A${R},${R} 0 ${big} 1 ${p(a1, R)} L${p(a1, r)} A${r},${r} 0 ${big} 0 ${p(a0, r)} Z`;
    s.append(svg('path', { d: path, fill: colors[i % colors.length], 'fill-rule': 'evenodd' }));
    s.append(svg('rect', { x: 128, y: 14 + i * 16, width: 9, height: 9, rx: 2, fill: colors[i % colors.length] }), stxt(142, 22 + i * 16, `${k} (${v})`));
    a0 = a1;
  });
  return s;
}
export function sourceList(sources) {
  const rows = (sources || []).map((s) => h('li', {}, `${s.route || ''} ${s.month || ''} `, s.error ? badge(s.error, 'mock') : s.skipped ? badge(s.skipped, 'est') :
    (s.providers || []).map((p) => badge(`${p.provider}${p.ok ? '' : ' ✕'}`, p.ok ? (p.is_mock ? 'mock' : 'ok') : 'est', p.error || `${p.ms} ms`))));
  return h('details', {}, h('summary', {}, `Data sources & fallbacks (${rows.length})`), h('ul', { class: 'small' }, rows));
}
