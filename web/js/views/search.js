import { post, get } from '../api.js';
import { h, clear, loading, errorBox, badge, mockBadge, estBadge, eur, dur, fdate, field, select, sourceList, empty, MONTHS, barChart } from '../ui.js';

const today = () => new Date().toISOString().slice(0, 10);
const plus = (n) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);
const linkBtns = (links) => h('div', { class: 'row' }, (links || []).map((l) => h('a', { class: 'btn sec sm', href: l.url, target: '_blank', rel: 'noopener noreferrer' }, `${l.label} ↗`)));
const modeIcon = { FLIGHT: '✈', TRAIN: '🚆', BUS: '🚌', MULTIMODAL: '🔀' };

export async function render(view, r) {
  const root = h('div', { class: 'page' }, h('h1', {}, 'Search & Compare'), h('div', { class: 'sub' }, 'Flights · trains · buses · multimodal, flexible dates and the cheapest possible trip'));
  view.append(root);
  let tab = r.params.tab || 'compare';
  const P = r.params;
  const tabs = h('div', { class: 'tabs' }), out = h('div', {});
  const TABS = [['compare', 'Compare modes'], ['flex', 'Flexible dates'], ['cheapest', 'Cheapest possible trip']];
  const paintTabs = () => { clear(tabs); TABS.forEach(([k, l]) => tabs.append(h('button', { class: k === tab ? 'active' : '', onclick: () => { tab = k; paintTabs(); paintForm(); } }, l))); };
  const formHost = h('div', { class: 'card' });
  root.append(tabs, formHost, out);

  function paintForm() {
    clear(formHost); clear(out);
    const I = {};
    const inp = (k, label, type = 'text', v = '', extra = {}) => field(label, I[k] = h('input', { type, value: P[k] ?? v, ...extra }));
    const from = inp('origin', 'From (city / IATA)', 'text', P.from || 'FCO'), to = inp('destination', 'To (city / country / IATA)', 'text', P.to || '');
    let body;
    if (tab === 'compare') body = [from, to, inp('date', 'Departure', 'date', plus(45)), inp('return_date', 'Return (optional)', 'date', plus(52)), field('Alt. airports', I.alt = select([['1', 'Yes'], ['0', 'No']], '1')), inp('value_of_time', 'Value of time (€/h)', 'number', 12)];
    else body = [from, to, inp('date_from', 'Window start', 'date', plus(30)), inp('date_to', 'Window end', 'date', plus(120)), inp('min_days', 'Min days', 'number', 10), inp('max_days', 'Max days', 'number', 14), tab === 'flex' ? field('Alt. airports', I.alt = select([['1', 'Yes'], ['0', 'No']], '1')) : field('Nearby destinations', I.near = select([['1', 'Yes'], ['0', 'No']], '1')), inp('max_requests', 'Max provider requests', 'number', tab === 'flex' ? 24 : 40)];
    const btn = h('button', { class: 'btn', onclick: async () => {
      btn.disabled = true; clear(out).append(loading(tab === 'compare' ? 'Comparing…' : 'Exploring combinations (bounded, cached)…'));
      const b = {}; for (const [k, el] of Object.entries(I)) b[k] = el.value;
      b.alt_airports = b.alt !== '0'; b.include_nearby = b.near !== '0';
      try {
        const res = await post(tab === 'compare' ? '/api/search/compare' : tab === 'flex' ? '/api/search/flexible' : '/api/search/cheapest', b);
        clear(out).append(tab === 'compare' ? showCompare(res) : tab === 'flex' ? showFlex(res) : showCheapest(res));
      } catch (e) { clear(out).append(errorBox(e)); }
      btn.disabled = false;
    } }, tab === 'cheapest' ? 'Find cheapest trip' : 'Search');
    formHost.append(h('div', { class: 'form' }, body, btn));
    if (tab === 'cheapest') formHost.append(h('div', { class: 'small muted', style: { marginTop: '10px' } }, 'Strategies: flexible dates & duration · alternative airports · nearby destinations · open-jaw. Only documented provider endpoints are queried (no scraping/bypass); sources that can\'t be automated are deep links.'));
  }
  paintTabs(); paintForm();
  if (P.from && P.to) formHost.querySelector('.btn').click();
}

function flags(o) { return [o.is_mock ? mockBadge() : null, o.price_is_estimate ? estBadge() : null]; }

function showCompare(r) {
  const s = r.summary, best = (k, t) => s[k] ? h('div', { class: 'card kpi' }, h('span', {}, t), h('b', {}, eur(s[k].price_eur)), h('span', { class: 'muted', style: { textTransform: 'none' } }, `${modeIcon[s[k].mode]} ${s[k].mode} · ${dur(s[k].door_to_door_min)}`)) : null;
  return h('div', {},
    h('h2', {}, `${r.origin.name} → ${r.destination.name}`, h('span', { class: 'muted small' }, ` · ${r.distance_km} km`)),
    r.has_mock ? h('div', { class: 'bn warn' }, 'Some options use MOCK (synthetic) data because no real provider answered. Configure a provider key for real fares.') : null,
    h('div', { class: 'grid g3' }, best('cheapest', 'Cheapest'), best('fastest', 'Fastest door-to-door'), best('best_value', 'Best value (price + time + comfort)')),
    h('h2', {}, 'All options'),
    r.options.length ? h('div', { class: 'card pad0' }, h('table', {}, h('thead', {}, h('tr', {}, ['Mode', 'Route', 'Price', 'Door-to-door', 'Moving', 'Time lost', 'Changes', 'Score', ''].map((x, i) => h('th', { class: i >= 2 && i <= 7 ? 'num' : '' }, x)))),
      h('tbody', {}, r.options.map((o) => h('tr', {}, h('td', {}, `${modeIcon[o.mode]} ${o.mode}`), h('td', {}, h('div', { class: 'small' }, `${o.origin} → ${o.destination}`), h('div', { class: 'small muted' }, o.provider, ' ', o.notes.join(' · ')), h('div', {}, flags(o))),
        h('td', { class: 'num' }, o.price_eur != null ? eur(o.price_eur) : 'n/a'), h('td', { class: 'num' }, dur(o.door_to_door_min)), h('td', { class: 'num' }, dur(o.moving_min)), h('td', { class: 'num' }, dur(o.lost_min)), h('td', { class: 'num' }, o.transfers), h('td', { class: 'num' }, h('b', {}, o.score)), h('td', {}, o.link ? h('a', { href: o.link, target: '_blank', rel: 'noopener noreferrer' }, 'open ↗') : null)))))) : empty('No options found. Try the deep links below.'),
    h('h2', {}, 'Book / verify manually'), linkBtns([...r.links.flights, ...r.links.trains, ...r.links.hotels]), h('p', { class: 'small muted' }, r.note), sourceList(r.sources));
}

function combosTable(combos) {
  return h('div', { class: 'card pad0' }, h('table', {}, h('thead', {}, h('tr', {}, ['Route', 'Depart', 'Return', 'Nights', 'Stops', 'Price', ''].map((x, i) => h('th', { class: i >= 3 && i <= 5 ? 'num' : '' }, x)))),
    h('tbody', {}, combos.map((c) => h('tr', {}, h('td', {}, `${c.origin} → ${c.destination}`, ' ', (c.flags || []).map((f) => badge(f, 'est')), c.is_mock ? mockBadge() : null, h('div', { class: 'small muted' }, `${c.provider}${c.airline ? ' · ' + c.airline : ''}${c.techniques ? ' · ' + c.techniques.join(', ') : ''}`)),
      h('td', {}, fdate(c.depart)), h('td', {}, fdate(c.return)), h('td', { class: 'num' }, c.nights ?? '—'), h('td', { class: 'num' }, c.stops ?? '—'), h('td', { class: 'num' }, h('b', {}, eur(c.price_eur))), h('td', {}, c.link ? h('a', { href: c.link, target: '_blank', rel: 'noopener noreferrer' }, 'open ↗') : null))))));
}

function showFlex(r) {
  return h('div', {}, h('h2', {}, `${r.origin.name} → ${r.destination.name}`, h('span', { class: 'muted small' }, ` · ${r.window[0]} … ${r.window[1]} · ${r.duration_days[0]}–${r.duration_days[1]} days`)),
    r.has_mock ? h('div', { class: 'bn warn' }, 'MOCK data in results (no real provider answered).') : null,
    h('div', { class: 'small muted' }, `Airports tried: ${r.airports_origin.join(', ')} → ${r.airports_destination.join(', ')} · provider requests used ${r.requests_used}/${r.requests_budget} · ${r.total_found} combinations found`),
    r.cheapest ? h('div', { class: 'grid g3', style: { margin: '12px 0' } }, h('div', { class: 'card kpi' }, h('span', {}, 'Cheapest combination'), h('b', {}, eur(r.cheapest.price_eur)), h('span', { class: 'muted', style: { textTransform: 'none' } }, `${fdate(r.cheapest.depart)} → ${fdate(r.cheapest.return)} (${r.cheapest.nights} nights)`)),
      h('div', { class: 'card' }, h('h3', {}, 'Cheapest by departure month'), barChart(Object.fromEntries(r.by_month.map((m) => [MONTHS[+m.month.slice(5) - 1], Math.round(m.min_eur)])), { w: 300, hgt: 130 })),
      h('div', { class: 'card' }, h('h3', {}, 'Cheapest by trip length (nights)'), barChart(Object.fromEntries(r.by_duration.map((m) => [m.nights, Math.round(m.min_eur)])), { w: 300, hgt: 130, color: 'var(--accent2)' }))) : null,
    r.combos.length ? combosTable(r.combos) : empty('No combinations found in this window.'), h('h2', {}, 'Verify / book'), linkBtns(r.links), h('p', { class: 'small muted' }, r.note), sourceList(r.sources));
}

function showCheapest(r) {
  return h('div', {}, h('h2', {}, `Cheapest trip: ${r.origin.name} → ${r.destination.name}`),
    r.has_mock ? h('div', { class: 'bn warn' }, 'MOCK data in results (no real provider answered).') : null,
    r.best ? h('div', { class: 'grid g3' }, h('div', { class: 'card kpi' }, h('span', {}, 'Best found'), h('b', {}, eur(r.best.price_eur)), h('span', { class: 'muted', style: { textTransform: 'none' } }, `${r.best.origin} → ${r.best.destination} · ${fdate(r.best.depart)} → ${fdate(r.best.return)}`), h('div', {}, r.best.techniques.map((t) => badge(t, 'ok')))),
      h('div', { class: 'card kpi' }, h('span', {}, 'Baseline (no tricks)'), h('b', {}, r.baseline ? eur(r.baseline.price_eur) : '—')), h('div', { class: 'card kpi' }, h('span', {}, 'Saving'), h('b', {}, r.saving_vs_baseline_eur != null ? eur(r.saving_vs_baseline_eur) : '—'))) : empty('No fares found.'),
    h('h2', {}, 'Strategies applied'), h('div', { class: 'card pad0' }, h('table', {}, h('thead', {}, h('tr', {}, ['Strategy', 'Requests', 'Found', 'Best'].map((x) => h('th', {}, x)))), h('tbody', {}, r.strategies.map((s) => h('tr', {}, h('td', {}, s.strategy), h('td', {}, s.requests), h('td', {}, s.found), h('td', {}, s.best_eur ? eur(s.best_eur) : '—')))))),
    h('h2', {}, 'Candidates'), combosTable(r.candidates), h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Not implemented: ', r.not_implemented.join('; ')), h('p', { class: 'small muted' }, r.policy), linkBtns(r.links));
}
