import { get } from '../api.js';
import { h, clear, loading, errorBox, badge, field, select, MONTHS, estBadge } from '../ui.js';

export async function render(view) {
  const root = h('div', { class: 'page' }, h('h1', {}, 'Recommendations'), h('div', { class: 'sub' }, 'Deterministic and explainable: every score shows the factors behind it. Factors without data are dropped, never guessed.'));
  view.append(root);
  const I = {}, out = h('div', {});
  const run = async () => {
    clear(out).append(loading());
    const q = new URLSearchParams({ top: 15 }); for (const [k, el] of Object.entries(I)) if (el.value) q.set(k, el.value); if (I.live.checked) q.set('live', '1');
    try { const d = await get(`/api/recommendations?${q}`); clear(out).append(show(d)); } catch (e) { clear(out).append(errorBox(e)); }
  };
  root.append(h('div', { class: 'card' }, h('div', { class: 'form' }, field('Month', I.month = select([['', 'any'], ...MONTHS.map((m, i) => [i + 1, m])], '')), field('Days', I.days = h('input', { type: 'number', placeholder: 'from prefs' })), field('Budget (EUR)', I.budget = h('input', { type: 'number', placeholder: 'from prefs' })),
    field('Live climate data (slower)', h('label', { class: 'row' }, I.live = h('input', { type: 'checkbox' }), 'fetch missing')), h('button', { class: 'btn', onclick: run }, 'Recommend'))), out);
  run();
}

function show(d) {
  return h('div', { style: { marginTop: '14px' } }, h('div', { class: 'grid g2' }, d.results.map((r, i) => h('div', { class: 'card' },
    h('div', { class: 'row spread' }, h('h3', { style: { margin: 0, fontSize: '16px' } }, `${i + 1}. ${r.flag || ''} ${r.country}`), h('div', {}, badge(`${r.score}`, 'ok'), ' ', badge(`coverage ${Math.round(r.coverage * 100)}%`))),
    h('div', { class: 'small muted' }, `${r.continent} · ${Math.round(r.distance_km)} km · rough cost ~€${r.estimate.total_est} `, estBadge('EST')),
    h('div', { style: { margin: '8px 0' } }, r.factors.slice(0, 6).map((f) => h('div', { style: { marginBottom: '4px' }, title: f.detail || '' }, h('div', { class: 'row spread small' }, h('span', {}, f.name.replace(/_/g, ' ')), h('span', { class: 'muted' }, `${Math.round(f.value * 100)}% · weight ${f.weight}`)), h('div', { class: 'bar' }, h('i', { style: { width: `${f.value * 100}%` } }))))),
    r.reasons.length ? h('ul', { class: 'small', style: { paddingLeft: '18px', margin: '4px 0' } }, r.reasons.map((x) => h('li', {}, x))) : null,
    r.missing.length ? h('div', { class: 'small muted' }, 'No data for: ', r.missing.join(', ')) : null,
    h('div', { class: 'row', style: { marginTop: '8px' } }, h('a', { class: 'btn sm', href: `#/package?destination=${encodeURIComponent(r.country)}` }, 'Build package'), h('a', { class: 'btn sm sec', href: `#/map?focus=country:${r.iso3}` }, 'On map'))))),
    h('p', { class: 'small muted' }, d.note));
}
