import { get, post } from '../api.js';
import { h, clear, loading, errorBox, badge, ago, toast } from '../ui.js';

export async function render(view) {
  const root = h('div', { class: 'page' }, loading());
  view.append(root);
  let s, provs;
  try { [s, provs] = await Promise.all([get('/api/status'), get('/api/providers')]); } catch (e) { clear(root).append(errorBox(e)); return; }
  const cap = (name) => provs.providers.filter((p) => p.capability === name);
  clear(root).append(h('h1', {}, 'System status'), h('div', { class: 'sub' }, 'What is real, what is cached, what is mock - at a glance'),
    h('h2', {}, 'Provider chains (fallback order: first → last, then cache, then graceful degradation)'),
    h('div', { class: 'grid g2' }, Object.entries(s.chains).map(([c, list]) => h('div', { class: 'card' }, h('h3', {}, c), list.map((p, i) => h('div', { class: 'row' }, `${i + 1}.`, h('b', {}, p.name), p.mock ? badge('MOCK', 'mock') : p.estimate ? badge('ESTIMATE', 'est') : p.configured ? badge('configured', 'ok') : badge(`needs ${p.needs_key}`, 'est'), p.verified_live ? badge('verified live', 'ok') : (p.mock ? null : badge('not verified live yet', ''))))))),
    h('h2', {}, 'Cache (TTL strategy)'), h('div', { class: 'card pad0' }, h('table', {}, h('thead', {}, h('tr', {}, ['Namespace', 'Entries', 'TTL', 'Last fetch'].map((x) => h('th', {}, x)))), h('tbody', {}, Object.entries(s.ttl).map(([ns, ttl]) => { const c = s.cache.find((x) => x.namespace === ns); return h('tr', {}, h('td', {}, ns), h('td', {}, c ? c.n : 0), h('td', {}, ttl >= 86400 ? `${ttl / 86400} d` : ttl >= 3600 ? `${ttl / 3600} h` : `${ttl / 60} min`), h('td', {}, c ? ago(c.last) : 'never')); })))),
    h('div', { class: 'row', style: { marginTop: '12px' } }, h('button', { class: 'btn sec', onclick: async () => { await post('/api/refresh'); toast('Refresh started'); } }, 'Refresh stale data now'), h('button', { class: 'btn sec', onclick: async () => { await post('/api/cache/purge'); toast('Cache cleared', 'ok'); location.reload(); } }, 'Clear cache')),
    h('h2', {}, 'All registered providers'), h('div', { class: 'card pad0' }, h('table', {}, h('thead', {}, h('tr', {}, ['Capability', 'Provider', 'Description', 'Key', 'Terms'].map((x) => h('th', {}, x)))),
      h('tbody', {}, provs.providers.map((p) => h('tr', {}, h('td', {}, p.capability), h('td', {}, p.name, ' ', p.is_mock ? badge('MOCK', 'mock') : ''), h('td', { class: 'small' }, p.description, p.free_tier ? h('div', { class: 'muted' }, p.free_tier) : null), h('td', {}, p.requires_key ? (p.configured ? badge('set', 'ok') : badge(p.requires_key, 'est')) : '—'), h('td', {}, p.terms_url ? h('a', { href: p.terms_url, target: '_blank', rel: 'noopener noreferrer' }, 'link') : '')))))));
}
