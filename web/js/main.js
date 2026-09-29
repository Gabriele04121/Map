import { get, post } from './api.js';
import { $, h, icon, clear, toast, badge } from './ui.js';

const ROUTES = [
  ['map', 'Map', 'map', () => import('./views/map.js')],
  ['dashboard', 'Dashboard', 'dash', () => import('./views/dashboard.js')],
  ['travels', 'My Travels', 'bag', () => import('./views/travels.js')],
  ['discover', 'Discover', 'compass', () => import('./views/discover.js')],
  ['search', 'Search & Compare', 'search', () => import('./views/search.js')],
  ['package', 'Package builder', 'box', () => import('./views/package.js')],
  ['monitor', 'Price monitor', 'chart', () => import('./views/monitor.js')],
  ['recommend', 'Recommendations', 'star', () => import('./views/recommend.js')],
  ['preferences', 'Preferences', 'cog', () => import('./views/preferences.js')],
  ['status', 'System status', 'pulse', () => import('./views/status.js')],
];
const HIDDEN = { place: () => import('./views/place.js') };
let current = null;

export function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const [name, ...rest] = path.split('/');
  return { name: name || 'map', arg: decodeURIComponent(rest.join('/')), params: Object.fromEntries(new URLSearchParams(query)) };
}

async function render() {
  const r = parseHash();
  const entry = ROUTES.find((x) => x[0] === r.name);
  const loader = entry ? entry[3] : HIDDEN[r.name];
  document.querySelectorAll('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.r === r.name || (r.name === 'place' && a.dataset.r === 'map')));
  const view = $('#view');
  if (current?.destroy) { try { current.destroy(); } catch { /* ignore */ } }
  clear(view);
  if (!loader) { view.append(h('div', { class: 'page' }, h('h1', {}, 'Not found'))); return; }
  try {
    const mod = await loader();
    current = await mod.render(view, r);
  } catch (e) {
    console.error(e);
    clear(view).append(h('div', { class: 'page' }, h('h1', {}, 'Something went wrong'), h('div', { class: 'err' }, e.message || 'Unexpected error while loading this page.')));
  }
  $('#sidebar').classList.remove('open');
}

function buildNav() {
  const nav = $('#nav');
  ROUTES.forEach(([id, label, ic]) => nav.append(h('a', { href: `#/${id}`, 'data-r': id }, icon(ic), label)));
}

function setupTheme() {
  const saved = localStorage.getItem('theme');
  document.documentElement.dataset.theme = saved || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  $('#theme').onclick = () => {
    const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = t; localStorage.setItem('theme', t);
    window.dispatchEvent(new Event('themechange'));
  };
}

function setupSearch() {
  const input = $('#gsearch'), box = $('#gresults');
  let timer = null, items = [], sel = -1;
  const hide = () => { box.classList.add('hidden'); sel = -1; };
  const go = (it) => { hide(); input.value = ''; if (it.href) location.hash = it.href.replace(/^#/, ''); else if (it.type === 'airport') location.hash = `/search?tab=compare&from=${it.iata}`; else if (it.id) location.hash = `/map?focus=${encodeURIComponent(it.id)}`; };
  const draw = (res) => {
    clear(box); items = [];
    (res.actions || []).forEach((a) => { items.push(a); box.append(h('div', { class: 'item', onclick: () => go(a) }, '⚡ ', a.label)); });
    if (res.results.length) box.append(h('div', { class: 'grp' }, 'Places'));
    res.results.forEach((r) => { items.push(r); box.append(h('div', { class: 'item', onclick: () => go(r) }, r.flag || ({ city: '🏙', airport: '✈', trip: '🧳', country: '🌍' }[r.type] || '•'), h('div', {}, h('div', {}, r.name), h('div', { class: 'small muted' }, `${r.type}${r.sub ? ' · ' + r.sub : ''}`)))); });
    if (!items.length) box.append(h('div', { class: 'item muted' }, 'No results'));
    box.classList.remove('hidden');
  };
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) return hide();
    timer = setTimeout(async () => { try { draw(await get(`/api/search?q=${encodeURIComponent(q)}`)); } catch (e) { hide(); } }, 180);
  });
  input.addEventListener('keydown', (e) => {
    const els = [...box.querySelectorAll('.item')];
    if (e.key === 'ArrowDown') { sel = Math.min(els.length - 1, sel + 1); }
    else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); }
    else if (e.key === 'Enter' && items[Math.max(sel, 0)]) { go(items[Math.max(sel, 0)]); return; }
    else if (e.key === 'Escape') return hide();
    else return;
    els.forEach((el, i) => el.classList.toggle('sel', i === sel));
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('.searchbox')) hide(); });
}

async function refreshStatus() {
  try {
    const s = await get('/api/status');
    const b = clear($('#banner'));
    if (s.offline) b.append(h('div', { class: 'bn warn' }, 'Offline mode: only cached and bundled data is used.'));
    if (!s.has_real_flight_provider) b.append(h('div', { class: 'bn warn' }, 'No real flight provider configured (set TRAVELPAYOUTS_TOKEN in .env). ', s.mock_enabled ? 'Flight/train prices shown are SYNTHETIC (MOCK) and clearly labelled.' : 'Flight search returns nothing until a provider is configured.', ' ', h('a', { href: '#/status' }, 'Details')));
    const bc = $('#bellcount');
    bc.textContent = s.unseen_alerts; bc.classList.toggle('hidden', !s.unseen_alerts);
    $('#fxbox').textContent = s.fx ? `EUR rates: ${s.fx.date}` : 'EUR rates: unavailable';
  } catch { /* server hiccup: ignore */ }
}

buildNav(); setupTheme(); setupSearch();
$('#burger').onclick = () => $('#sidebar').classList.toggle('open');
$('#bell').onclick = () => { location.hash = '/monitor'; };
window.addEventListener('hashchange', render);
render();
refreshStatus();
post('/api/refresh').then(() => setTimeout(refreshStatus, 4000)).catch(() => {});   // selective TTL refresh on open
setInterval(refreshStatus, 120000);
