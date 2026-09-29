// Shared rendering of destination-intelligence sections (used by the map side panel and the destination page).
import { h, badge, estBadge, statusBadge, eur, num, compact, MONTHS, fdate, empty } from '../ui.js';

const linkList = (links) => h('div', { class: 'row' }, (links || []).map((l) => h('a', { class: 'btn sec sm', href: l.url, target: '_blank', rel: 'noopener noreferrer' }, `${l.label} ↗`)));
const fact = (label, value, wide) => h('div', { class: `fact${wide ? ' wide' : ''}` }, h('span', {}, label), h('b', {}, value ?? '—'));
const sec = (s, n) => (s && s[n] && s[n].data) ? s[n].data : null;

export function comfortColor(v) { const hue = Math.round(v * 1.2); return `hsl(${hue},62%,${v > 50 ? 38 : 34}%)`; }

export function monthsStrip(months) {
  return h('div', { class: 'months' }, months.map((m) => h('div', { style: { background: comfortColor(m.comfort) }, title: `${MONTHS[m.month - 1]}: ${m.tmin ?? '?'}–${m.tmax}°C, ~${m.rain_days} rain days, ${m.precip_mm} mm` }, MONTHS[m.month - 1])));
}

export function quickFacts(secs, place, partial = false) {
  const o = sec(secs, 'overview'), w = sec(secs, 'when_to_go'), c = sec(secs, 'cost'), t = sec(secs, 'how_to_get_there'), s = sec(secs, 'safety'), ev = sec(secs, 'events');
  const m = new Date().getMonth() + 1, cur = w?.months?.find((x) => x.month === m);
  const cells = [];
  cells.push(fact(place.type === 'city' ? 'Population (city)' : 'Population', o ? num(o.city_population ?? o.country_population) : '…'));
  cells.push(fact('Capital', o ? (o.capital || '—') : '…'));
  cells.push(fact('Language', o ? (o.languages.join(', ') || '—') : '…'));
  cells.push(fact('Currency', o ? o.currencies.map((x) => `${x.name || x.code} (${x.code})`).join(', ') || '—' : '…'));
  cells.push(fact('Time zone', o ? (o.timezone || 'n/a (needs live weather source)') : '…'));
  cells.push(fact('Climate now', w ? (cur ? `${cur.tmin ?? '?'}–${cur.tmax}°C · ${cur.rain_days} rain days` : '—') : (secs.when_to_go ? 'unavailable' : '…')));
  cells.push(fact('Best months', w ? (w.best_months.map((x) => MONTHS[x - 1]).join(', ') || '—') : (secs.when_to_go ? 'unavailable' : '…')));
  cells.push(fact('Avoid', w ? (w.avoid_months.map((x) => MONTHS[x - 1]).join(', ') || 'none flagged') : (secs.when_to_go ? 'unavailable' : '…')));
  cells.push(h('div', { class: 'fact' }, h('span', {}, 'Avg cost / day'), h('b', {}, c ? `~${eur(c.total_day_eur)} ` : '…', c ? estBadge() : null)));
  cells.push(h('div', { class: 'fact' }, h('span', {}, 'Lodging / night'), h('b', {}, c ? `~${eur(c.hotel_night_eur)} ` : '…', c ? estBadge() : null)));
  cells.push(h('div', { class: 'fact' }, h('span', {}, 'Local transport / day'), h('b', {}, c ? `~${eur(c.local_transport_day_eur)} ` : '…', c ? estBadge() : null)));
  cells.push(fact('Safety', s ? (s.advisory ? `${s.advisory.score}/5 (lower = safer)` : 'no advisory data') : (secs.safety ? 'unavailable' : '…')));
  cells.push(fact('Entry / visa', t ? `${t.visa.requirement ?? 'n/d'} (${t.visa.passport})` : '…'));
  cells.push(fact('Suggested stay', o ? `${o.suggested_trip_days.min}–${o.suggested_trip_days.max} days (heuristic)` : '…'));
  cells.push(fact('Airports', t ? t.arrival_airports.join(', ') : '…'));
  cells.push(fact('From home', t ? (t.from_home.distance_km ? `${t.from_home.airport}: ${num(t.from_home.distance_km)} km` : '—') : '…'));
  cells.push(fact('Events', ev ? (ev.upcoming.slice(0, 2).map((e) => `${fdate(e.date)} ${e.name}`).join(' · ') || 'none listed') : (secs.events ? 'unavailable' : '…'), true));
  return h('div', { class: 'facts' }, partial ? cells.filter((c) => !c.textContent.endsWith('…')) : cells);
}

function textBlocks(data, attribution, url) {
  const blocks = Object.entries(data || {}).filter(([, v]) => typeof v === 'string').map(([k, v]) => h('details', { open: true }, h('summary', {}, k), h('div', { class: 'prewrap small' }, v)));
  return h('div', {}, blocks, attribution ? h('div', { class: 'small muted' }, attribution, ' ', url ? h('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, 'Source ↗') : null) : null);
}

export function sectionView(name, s, place) {
  if (!s) return empty('Not loaded');
  const head = h('div', { class: 'row', style: { marginBottom: '8px' } }, statusBadge(s), s.source ? h('span', { class: 'small muted' }, s.source) : null, s.stale ? badge('stale', 'stale') : null);
  if (!s.data) return h('div', {}, head, h('div', { class: 'err' }, s.error || 'No data available right now.'), s.attempts ? h('div', { class: 'small muted' }, 'Tried: ', s.attempts.map((a) => `${a.provider}${a.ok ? '' : ' ✕'}`).join(', ')) : null);
  const d = s.data;
  const body = {
    overview: () => h('div', {}, quickFacts({ overview: s }, place, true), d.summary ? h('p', { class: 'prewrap' }, d.summary) : null, d.guide_url ? h('a', { href: d.guide_url, target: '_blank', rel: 'noopener noreferrer' }, 'Wikivoyage guide ↗') : null, s.attribution ? h('div', { class: 'small muted' }, s.attribution) : null),
    when_to_go: () => h('div', {}, h('p', {}, 'Comfort by month (green = best)'), monthsStrip(d.months), h('p', {}, h('b', {}, 'Best: '), d.best_months.map((x) => MONTHS[x - 1]).join(', '), d.avoid_months.length ? [' · ', h('b', {}, 'Avoid: '), d.avoid_months.map((x) => MONTHS[x - 1]).join(', ')] : ''),
      h('div', { class: 'small muted' }, d.basis), h('h3', { style: { marginTop: '12px' } }, 'Price seasonality'),
      typeof d.price_seasonality === 'string' ? h('div', { class: 'small muted' }, d.price_seasonality) : h('div', {}, `${d.price_seasonality.route}: cheapest months `, d.price_seasonality.cheapest_months.map((x) => MONTHS[x - 1]).join(', ')),
      h('table', {}, h('thead', {}, h('tr', {}, ['Month', 'Tmax', 'Tmin', 'Rain days', 'mm', 'Comfort'].map((x) => h('th', {}, x)))), h('tbody', {}, d.months.map((m) => h('tr', {}, h('td', {}, MONTHS[m.month - 1]), h('td', {}, m.tmax), h('td', {}, m.tmin ?? '—'), h('td', {}, m.rain_days), h('td', {}, m.precip_mm), h('td', {}, m.comfort)))))),
    how_to_get_there: () => h('div', {}, h('dl', { class: 'kv' }, h('dt', {}, 'Visa / entry'), h('dd', {}, `${d.visa.requirement ?? 'n/d'} for passport ${d.visa.passport}`), h('dt', {}, 'Arrival airports'), h('dd', {}, d.arrival_airports.join(', ')),
      h('dt', {}, 'From home'), h('dd', {}, `${d.from_home.airport}: ${d.from_home.distance_km ? num(d.from_home.distance_km) + ' km' : '—'}`)),
      h('div', { class: 'small muted' }, d.visa.note), linkList([d.visa.official]), h('p', {}, h('a', { class: 'btn', href: `#/search?tab=compare&from=${d.from_home.airport}&to=${encodeURIComponent(place.name)}` }, 'Compare transport from home →'))),
    cost: () => costView(d), local_costs: () => costView(d),
    weather: () => h('table', {}, h('thead', {}, h('tr', {}, ['Date', 'Max', 'Min', 'Rain mm'].map((x) => h('th', {}, x)))), h('tbody', {}, d.days.map((x) => h('tr', {}, h('td', {}, fdate(x.date)), h('td', {}, x.tmax + '°'), h('td', {}, x.tmin + '°'), h('td', {}, x.precip_mm))))),
    events: () => h('div', {}, d.upcoming.length ? h('table', {}, h('tbody', {}, d.upcoming.map((e) => h('tr', {}, h('td', {}, fdate(e.date)), h('td', {}, e.name), h('td', { class: 'muted small' }, e.local_name !== e.name ? e.local_name : ''))))) : empty('No upcoming holidays listed'), h('div', { class: 'small muted' }, d.note)),
    safety: () => h('div', {}, d.advisory ? h('div', {}, h('div', { class: 'row' }, h('b', {}, `Advisory score ${d.advisory.score}/5`), h('span', { class: 'muted small' }, 'lower is safer · aggregated government advisories')), h('div', { class: 'bar' }, h('i', { style: { width: `${d.advisory.score * 20}%` } })), h('p', { class: 'small' }, d.advisory.message), h('div', { class: 'small muted' }, `Updated ${d.advisory.updated || 'n/d'}`)) : h('div', { class: 'muted' }, 'Advisory service unavailable: ' + (d.advisory_error || 'n/d')),
      linkList(d.official_links), d.guide_notes ? h('details', { open: true }, h('summary', {}, 'Stay safe (Wikivoyage)'), h('div', { class: 'prewrap small' }, d.guide_notes)) : null),
    hotels: () => h('div', {}, h('p', {}, `Typical mid-range night: ~${eur(d.nightly_estimate_eur)} `, estBadge()), h('div', { class: 'small muted' }, d.live_prices), linkList(d.links)),
    flights: () => h('div', {}, (d.observed || []).map((r) => h('div', { class: 'card', style: { marginBottom: '8px' } }, h('b', {}, r.route), ' ', r.stats.verdict ? badge(r.stats.verdict, r.stats.verdict) : null,
      h('div', { class: 'small muted' }, r.stats.message || 'No history')) ), linkList(d.links), h('div', { class: 'small muted' }, d.note)),
    trains: () => h('div', {}, linkList(d.links), h('div', { class: 'small muted' }, d.note)),
    itineraries: () => h('div', {}, h('p', {}, `Suggested stay: ${d.suggested_days.min}–${d.suggested_days.max} days `, estBadge('HEURISTIC')), h('p', {}, 'Main cities: ', d.main_cities.join(' · ')), h('a', { class: 'btn', href: `#/package?destination=${encodeURIComponent(place.name)}` }, 'Build a costed itinerary →')),
    transport: () => h('div', {}, textBlocks({ 'Get around': d['Get around'] }, s.attribution, s.url), d.airports ? h('p', {}, h('b', {}, 'Airports: '), d.airports.map((a) => `${a.iata} ${a.city || ''}`).join(' · ')) : null, h('div', { class: 'small muted' }, d.stations)),
  }[name];
  return h('div', {}, head, s.note ? h('div', { class: 'small muted' }, s.note) : null, body ? body() : textBlocks(d, s.attribution, s.url));
}

function costView(d) {
  return h('div', {}, h('div', { class: 'row' }, estBadge('ESTIMATE · coarse tier'), h('span', { class: 'small muted' }, `tier ${d.tier} · ${d.confidence} confidence · style ${d.style}`)),
    h('table', {}, h('tbody', {}, [['Lodging / night', d.hotel_night_eur], ['Food / day', d.food_day_eur], ['Local transport / day', d.local_transport_day_eur], ['Activities / day', d.activities_day_eur], ['TOTAL / day', d.total_day_eur]].map(([k, v]) => h('tr', {}, h('td', {}, k), h('td', { class: 'num' }, eur(v)))))),
    d.local_currency ? h('p', { class: 'small' }, `1 EUR = ${d.local_currency.per_eur ?? 'n/d'} ${d.local_currency.currency}`) : null, h('div', { class: 'small muted' }, d.note));
}
