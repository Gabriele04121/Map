import { post } from '../api.js';
import { h, clear, loading, errorBox, badge, mockBadge, estBadge, eur, fdate, dur, field, select } from '../ui.js';

export async function render(view, r) {
  const root = h('div', { class: 'page' }, h('h1', {}, 'Package builder'), h('div', { class: 'sub' }, '“Build me a 7-day trip to Japan under €1,200” → flight, inland transport, hotels, itinerary, total'));
  view.append(root);
  const I = {}, P = r.params, out = h('div', {});
  const inp = (k, label, type, v, extra = {}) => field(label, I[k] = h('input', { type, value: P[k] ?? v, ...extra }));
  const btn = h('button', { class: 'btn', onclick: async () => {
    btn.disabled = true; clear(out).append(loading('Building package (flight search + inland legs)…'));
    const b = {}; for (const [k, el] of Object.entries(I)) if (el.value !== '') b[k] = el.value;
    try { clear(out).append(show(await post('/api/packages', b))); } catch (e) { clear(out).append(errorBox(e)); }
    btn.disabled = false;
  } }, 'Build package');
  root.append(h('div', { class: 'card' }, h('div', { class: 'form' }, inp('destination', 'Destination (country or city)', 'text', 'Japan'), inp('days', 'Days', 'number', 7), inp('budget_eur', 'Budget (EUR)', 'number', 1200), inp('origin', 'From (blank = home)', 'text', ''), field('Month', I.month = select([['', 'flexible (next 3 months)'], ...Array.from({ length: 12 }, (_, i) => [i + 1, new Date(2000, i).toLocaleString('en', { month: 'long' })])], P.month || '')), field('Style', I.style = select([['', 'from preferences'], 'budget', 'mid', 'comfort'], '')), inp('travelers', 'Travellers', 'number', '', { placeholder: 'prefs' }), btn)), out);
  if (P.destination) btn.click();
}

function show(p) {
  const L = p.breakdown, names = { flight: 'Flight (round trip)', inland_transport: 'Train / inland transport', hotel: 'Hotel', food: 'Food', local_transport: 'Local transport', activities: 'Activities' };
  const over = p.within_budget === false;
  return h('div', {},
    h('h2', {}, p.route.join('  →  ')),
    h('div', { class: 'row' }, badge(`${p.days} days`), badge(`${fdate(p.dates.depart)} → ${fdate(p.dates.return)}`), badge(p.style), p.flags.has_mock ? mockBadge() : null, p.flags.has_estimates ? estBadge('CONTAINS ESTIMATES') : null, p.incomplete ? badge('INCOMPLETE: no flight fare', 'mock') : null),
    h('div', { class: 'grid g2', style: { marginTop: '14px' } },
      h('div', { class: 'card' }, h('h3', {}, 'Cost breakdown'), h('table', {}, h('tbody', {}, Object.entries(L).map(([k, v]) => h('tr', {}, h('td', {}, names[k], h('div', { class: 'small muted' }, v.basis)), h('td', { class: 'num' }, v.eur != null ? eur(v.eur) : 'n/a', ' ', v.mock ? mockBadge() : v.estimate ? estBadge('EST') : badge('real', 'ok'))))),
        h('tfoot', {}, h('tr', {}, h('th', {}, 'TOTAL'), h('th', { class: 'num', style: { fontSize: '18px', color: over ? 'var(--bad)' : 'var(--ok)' } }, eur(p.total_eur))))),
        p.budget_eur ? h('div', { class: 'small', style: { marginTop: '8px' } }, over ? `⚠ Over budget by ${eur(p.total_eur - p.budget_eur)} (budget ${eur(p.budget_eur)})` : `✓ Within budget ${eur(p.budget_eur)} (${eur(p.budget_eur - p.total_eur)} left)`) : null,
        p.travelers > 1 ? h('div', { class: 'small muted' }, `${eur(p.per_person_eur)} per person`) : null, p.suggestions.map((s) => h('div', { class: 'small' }, '💡 ', s))),
      h('div', { class: 'card' }, h('h3', {}, 'Itinerary'), p.itinerary.map((s, i) => h('div', { class: 'row', style: { marginBottom: '6px' } }, h('b', {}, `${i + 1}. ${s.city}`), badge(`${s.nights} night${s.nights > 1 ? 's' : ''}`), h('span', { class: 'small muted' }, `${fdate(s.from)} → ${fdate(s.to)}`), s.place_id ? h('a', { class: 'small', href: `#/place/${encodeURIComponent(s.place_id)}` }, 'guide') : null)),
        p.legs.length ? h('div', {}, h('h3', { style: { marginTop: '12px' } }, 'Inland legs'), p.legs.map((l) => h('div', { class: 'small' }, `${l.from} → ${l.to}: ${l.mode}, ${dur(l.min)}, ${eur(l.eur)} `, l.mock ? mockBadge() : l.estimate ? estBadge('EST') : null))) : null,
        p.flight ? h('div', { class: 'small muted', style: { marginTop: '10px' } }, `Flight: ${p.flight.origin}→${p.flight.destination} via ${p.flight.provider}, ${p.flight.stops ?? '?'} stop(s)`) : null)),
    h('h2', {}, 'Book / verify'), h('div', { class: 'row' }, [...p.links.flights, ...p.links.hotels].map((l) => h('a', { class: 'btn sec sm', href: l.url, target: '_blank', rel: 'noopener noreferrer' }, `${l.label} ↗`))), h('p', { class: 'small muted' }, p.note));
}
