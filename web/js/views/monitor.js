import { get, post, del, api } from '../api.js';
import { h, clear, loading, errorBox, toast, badge, mockBadge, eur, fdate, ago, field, lineChart, empty, modal } from '../ui.js';

export async function render(view, r) {
  const root = h('div', { class: 'page' });
  view.append(root);
  async function load() {
    clear(root).append(loading());
    let w, a;
    try { [w, a] = await Promise.all([get('/api/watches'), get('/api/alerts')]); } catch (e) { clear(root).append(errorBox(e)); return; }
    const I = {};
    const inp = (k, label, type, v) => field(label, I[k] = h('input', { type, value: v }));
    const now = (n) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);
    clear(root).append(h('h1', {}, 'Price monitor'), h('div', { class: 'sub' }, 'Watches re-check on a TTL schedule (≥6 h) and raise in-app alerts on targets, drops ≥10% and cheap-vs-history anomalies'),
      h('div', { class: 'card' }, h('h3', {}, 'New watch'), h('div', { class: 'form' }, inp('origin', 'From', 'text', r.params.from || 'FCO'), inp('destination', 'To', 'text', r.params.to || ''), inp('date_from', 'Window start', 'date', now(30)), inp('date_to', 'Window end', 'date', now(150)), inp('min_days', 'Min days', 'number', 7), inp('max_days', 'Max days', 'number', 14), inp('target_price_eur', 'Alert below (EUR)', 'number', ''),
        h('button', { class: 'btn', onclick: async () => { const b = {}; for (const [k, el] of Object.entries(I)) b[k] = el.value; try { await post('/api/watches', b); toast('Watch created', 'ok'); load(); } catch (e) { toast(e.message, 'bad'); } } }, 'Add watch'))),
      h('h2', {}, `Alerts ${a.alerts.filter((x) => !x.seen).length ? '(' + a.alerts.filter((x) => !x.seen).length + ' new)' : ''}`),
      a.alerts.length ? h('div', { class: 'card' }, a.alerts.slice(0, 15).map((x) => h('div', { class: 'row', style: { padding: '4px 0', opacity: x.seen ? .6 : 1 } }, badge(x.level, x.level === 'deal' ? 'ok' : ''), h('span', {}, x.message), h('span', { class: 'small muted' }, ago(x.created_at)))), h('button', { class: 'btn sec sm', onclick: async () => { await post('/api/alerts/seen'); load(); } }, 'Mark all seen')) : empty('No alerts yet'),
      h('h2', {}, 'Watches'), w.watches.length ? h('div', { class: 'grid g2' }, w.watches.map((x) => card(x))) : empty('No watches yet'));
  }
  function card(x) {
    const st = x.stats || {};
    return h('div', { class: 'card' }, h('div', { class: 'row spread' }, h('b', {}, `${x.origin} → ${x.destination}`), h('div', {}, x.best?.is_mock ? mockBadge() : null, ' ', badge(x.active ? 'active' : 'paused', x.active ? 'ok' : ''))),
      h('div', { class: 'small muted' }, `${fdate(x.date_from)} … ${fdate(x.date_to)} · ${x.min_days}-${x.max_days} days${x.target_price_eur ? ' · target ' + eur(x.target_price_eur) : ''}`),
      h('div', { class: 'row', style: { margin: '8px 0' } }, h('b', { style: { fontSize: '22px' } }, x.last_price_eur ? eur(x.last_price_eur) : '—'), st.verdict ? badge(st.verdict.replace('_', ' '), st.verdict) : null, st.change_pct != null ? badge(`${st.change_pct > 0 ? '+' : ''}${st.change_pct}%`) : null, st.trend?.direction && st.trend.direction !== 'unknown' ? badge(`trend ${st.trend.direction}`) : null),
      h('div', { class: 'small' }, st.message || 'No history yet'), h('div', { class: 'small muted' }, `Checked ${ago(x.last_checked_at)}${x.last_error ? ' · ' + x.last_error : ''}${st.min_eur ? ' · min seen ' + eur(st.min_eur) : ''}`),
      h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn sm', onclick: async (e) => { e.target.disabled = true; try { const res = await post(`/api/watches/${x.id}/check`); toast(res.status === 'ok' ? `Best ${eur(res.price_eur)}` : `Check: ${res.status}${res.error ? ' - ' + res.error : ''}`, res.status === 'ok' ? 'ok' : 'bad'); } catch (er) { toast(er.message, 'bad'); } load(); } }, 'Check now'),
        h('button', { class: 'btn sm sec', onclick: () => history(x) }, 'History'), h('button', { class: 'btn sm sec', onclick: async () => { await api(`/api/watches/${x.id}`, { method: 'PATCH', body: { active: !x.active } }); load(); } }, x.active ? 'Pause' : 'Resume'), h('button', { class: 'btn sm bad', onclick: async () => { await del(`/api/watches/${x.id}`); load(); } }, 'Delete')));
  }
  async function history(x) {
    try {
      const s = await get(`/api/prices/stats?origin=${x.origin}&destination=${x.destination}${x.best?.is_mock ? '&include_mock=1' : ''}`);
      modal(`${x.origin} → ${x.destination} price history`, h('div', {}, x.best?.is_mock ? h('div', { class: 'bn warn' }, 'This history contains MOCK observations only.') : null,
        s.series ? lineChart(s.series) : empty(s.message), h('div', { class: 'grid g4', style: { marginTop: '10px' } }, [['Current', s.current_eur], ['Min', s.min_eur], ['Avg', s.avg_eur], ['Median', s.median_eur]].map(([k, v]) => h('div', { class: 'card kpi' }, h('span', {}, k), h('b', {}, v != null ? eur(v) : '—')))),
        h('p', {}, s.message), s.cheapest_months ? h('p', {}, 'Cheapest departure months: ', s.cheapest_months.join(', ')) : null));
    } catch (e) { toast(e.message, 'bad'); }
  }
  load();
}
