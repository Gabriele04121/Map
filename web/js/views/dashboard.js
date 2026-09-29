import { get } from '../api.js';
import { h, clear, loading, errorBox, eur, num, fdate, barChart, donut, badge, mockBadge, empty } from '../ui.js';

const kpi = (label, value, sub) => h('div', { class: 'card kpi' }, h('span', {}, label), h('b', {}, value), sub ? h('span', { class: 'muted', style: { textTransform: 'none', letterSpacing: 0 } }, sub) : null);
const tripRow = (t) => h('tr', {}, h('td', {}, `${t.city || ''} ${t.country_name}`.trim()), h('td', {}, fdate(t.depart_date)), h('td', { class: 'num' }, t.duration_days ? `${t.duration_days} d` : '—'), h('td', { class: 'num' }, t.cost_eur != null ? eur(t.cost_eur) : '—'), h('td', {}, t.rating ? '★'.repeat(t.rating) : ''));

export async function render(view) {
  const root = h('div', { class: 'page' }, h('h1', {}, 'Dashboard'), h('div', { class: 'sub' }, 'Your travel footprint, upcoming trips and price radar'), loading());
  view.append(root);
  let d;
  try { d = await get('/api/dashboard'); } catch (e) { root.append(errorBox(e)); return; }
  const s = d.stats, page = h('div', {});
  page.append(h('div', { class: 'grid g4' },
    kpi('Countries', s.countries_visited, `${s.pct_countries}% of ${s.countries_total_un} UN members`), kpi('Cities', s.cities_visited), kpi('Continents', `${s.continents_visited.count}/${s.continents_visited.of}`, Object.keys(s.continents_visited.detail).join(', ')),
    kpi('World explored', `${s.pct_land_area}%`, 'of land area (visited countries)'), kpi('Trips', s.trips, `${s.total_days} days`), kpi('Total spend', eur(s.total_spend_eur), s.avg_cost_per_trip_eur ? `avg ${eur(s.avg_cost_per_trip_eur)}/trip` : ''), kpi('Avg rating', s.avg_rating ?? '—'), kpi('Longest trip', s.longest_trip ? `${s.longest_trip.days} d` : '—', s.longest_trip?.country)));
  page.append(h('h2', {}, 'Travel statistics'), h('div', { class: 'grid g3' }, h('div', { class: 'card' }, h('h3', {}, 'Trips per year'), barChart(s.trips_per_year)), h('div', { class: 'card' }, h('h3', {}, 'Spend per year (EUR)'), barChart(s.spend_per_year_eur, { color: 'var(--accent2)' })),
    h('div', { class: 'card' }, h('h3', {}, 'Transport mix'), donut(s.transport_mix)), h('div', { class: 'card' }, h('h3', {}, 'Days travelling per year'), barChart(s.days_per_year, { color: 'var(--ok)' })), h('div', { class: 'card' }, h('h3', {}, 'Spend by continent (EUR)'), barChart(s.spend_by_continent_eur, { color: 'var(--warn)' })), h('div', { class: 'card' }, h('h3', {}, 'Ratings'), barChart(s.rating_distribution, { color: 'var(--analyzed)' }))));
  const table = (title, rows, emptyMsg) => h('div', { class: 'card' }, h('h3', {}, title), rows.length ? h('table', {}, h('thead', {}, h('tr', {}, ['Trip', 'Date', 'Days', 'Cost', ''].map((x) => h('th', {}, x)))), h('tbody', {}, rows.map(tripRow))) : empty(emptyMsg));
  page.append(h('h2', {}, 'Trips'), h('div', { class: 'grid g2' }, table('Latest trips', d.recent_trips, 'No trips yet - add some in My Travels'), table('Upcoming trips', d.upcoming_trips, 'No planned trips')));
  page.append(h('h2', {}, 'Suggested destinations'), h('div', { class: 'grid g3' }, d.suggested.map((x) => h('a', { class: 'card', href: `#/map?focus=country:${x.iso3}`, style: { color: 'inherit', textDecoration: 'none' } }, h('div', { class: 'row spread' }, h('b', {}, `${x.flag || ''} ${x.country}`), badge(`score ${x.score}`)), h('div', { class: 'bar', style: { margin: '8px 0' } }, h('i', { style: { width: `${x.score}%` } })), h('div', { class: 'small muted' }, x.reasons[0] || `data coverage ${Math.round(x.coverage * 100)}%`)))));
  page.append(h('h2', {}, 'Price radar'), h('div', { class: 'grid g2' },
    h('div', { class: 'card' }, h('h3', {}, 'Monitored prices'), d.monitored.length ? h('table', {}, h('thead', {}, h('tr', {}, ['Route', 'Last', 'Δ', 'Min seen', 'Verdict'].map((x) => h('th', {}, x)))), h('tbody', {}, d.monitored.map((m) => h('tr', {}, h('td', {}, m.route, ' ', m.is_mock ? mockBadge() : null), h('td', { class: 'num' }, eur(m.last_price_eur)), h('td', { class: 'num' }, m.change_pct != null ? `${m.change_pct > 0 ? '+' : ''}${m.change_pct}%` : '—'), h('td', { class: 'num' }, eur(m.min_eur)), h('td', {}, m.verdict ? badge(m.verdict.replace('_', ' '), m.verdict) : '—'))))) : empty('No watches yet - add one in Price monitor')),
    h('div', { class: 'card' }, h('h3', {}, 'Interesting offers'), d.offers.length ? d.offers.map((o) => h('div', { class: 'row spread' }, h('span', {}, o.route, ' ', o.best.is_mock ? mockBadge() : null), h('b', {}, eur(o.best.price_eur)), h('span', { class: 'muted small' }, `target ${eur(o.target)} · ${fdate(o.best.depart)}`))) : empty('No offer below your targets yet'),
      d.alerts.length ? h('div', {}, h('h3', {}, 'Recent alerts'), d.alerts.map((a) => h('div', { class: 'small' }, '🔔 ', a.message))) : null)));
  clear(root).append(h('h1', {}, 'Dashboard'), h('div', { class: 'sub' }, `Home airport ${d.home}`), page);
}
