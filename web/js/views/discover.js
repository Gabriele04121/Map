import { post } from '../api.js';
import { h, clear, loading, errorBox, badge, mockBadge, estBadge, eur, fdate, field, select, MONTHS } from '../ui.js';

export async function render(view, r) {
  const root = h('div', { class: 'page' }, h('h1', {}, 'Discover'), h('div', { class: 'sub' }, '“I have €1,000 and 10 days in November - where can I go?” → complete proposals, not a list of names'));
  view.append(root);
  const I = {}, out = h('div', {});
  const btn = h('button', { class: 'btn', onclick: async () => {
    btn.disabled = true; clear(out).append(loading('Scoring countries, then pricing the best candidates live (this can take a little while)…'));
    try { clear(out).append(show(await post('/api/discover', { budget_eur: I.budget.value, days: I.days.value, month: I.month.value, candidates: I.n.value }))); } catch (e) { clear(out).append(errorBox(e)); }
    btn.disabled = false;
  } }, 'Find trips');
  root.append(h('div', { class: 'card' }, h('div', { class: 'form' }, field('Budget (EUR)', I.budget = h('input', { type: 'number', value: r.params.budget || 1000 })), field('Days', I.days = h('input', { type: 'number', value: r.params.days || 10 })),
    field('Month', I.month = select([['', 'any'], ...MONTHS.map((m, i) => [i + 1, m])], r.params.month || '')), field('Proposals', I.n = h('input', { type: 'number', value: 5, min: 1, max: 10 })), btn)), out);
  if (r.params.month) btn.click();
}

function show(d) {
  return h('div', {}, d.proposals.length ? null : h('div', { class: 'empty' }, 'No complete proposal could be built. Check provider configuration in System status.'),
    h('div', { class: 'grid g2', style: { marginTop: '14px' } }, d.proposals.map((p) => h('div', { class: 'card' },
      h('div', { class: 'row spread' }, h('h2', { style: { margin: 0 } }, `${p.destination.flag || ''} ${p.destination.name}`), h('div', {}, badge(`score ${p.score}`), ' ', badge(`data ${Math.round(p.coverage * 100)}%`))),
      h('div', { class: 'row', style: { margin: '8px 0' } }, p.within_budget === false ? badge('over budget', 'mock') : badge('within budget', 'ok'), p.flags.has_mock ? mockBadge() : null, p.flags.has_estimates ? estBadge('INCL. ESTIMATES') : null, p.incomplete ? badge('no flight fare', 'mock') : null),
      h('dl', { class: 'kv' }, h('dt', {}, 'Transport'), h('dd', {}, p.transport), h('dt', {}, 'Dates'), h('dd', {}, `${fdate(p.dates.depart)} → ${fdate(p.dates.return)} (${p.duration_days} days)`), h('dt', {}, 'Itinerary'), h('dd', {}, p.route.join(' → ')), h('dt', {}, 'Lodging'), h('dd', {}, p.accommodation), h('dt', {}, 'Total'), h('dd', {}, h('b', {}, eur(p.total_eur)))),
      h('div', { style: { marginTop: '8px' } }, h('div', { class: 'small muted' }, 'Why this proposal'), p.reasons.length ? h('ul', { class: 'small', style: { margin: '4px 0', paddingLeft: '18px' } }, p.reasons.map((x) => h('li', {}, x))) : h('div', { class: 'small' }, 'Limited data: ranked mostly on budget, distance and novelty.')),
      h('div', { class: 'row', style: { marginTop: '8px' } }, h('a', { class: 'btn sm', href: `#/package?destination=${encodeURIComponent(p.destination.name)}&days=${d.days}&budget_eur=${d.budget_eur}${d.month ? '&month=' + d.month : ''}` }, 'Open full package'), h('a', { class: 'btn sm sec', href: `#/place/country:${p.destination.iso3}` }, 'Destination report'))))),
    d.failed.length ? h('div', { class: 'small muted' }, 'Could not price: ', d.failed.map((f) => `${f.country} (${f.error})`).join('; ')) : null, h('p', { class: 'small muted' }, d.shortlist_basis, ' ', d.note));
}
