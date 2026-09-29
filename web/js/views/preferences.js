import { get, put } from '../api.js';
import { h, clear, loading, errorBox, toast, field, select } from '../ui.js';

export async function render(view) {
  const root = h('div', { class: 'page' }, loading());
  view.append(root);
  let d;
  try { d = await get('/api/preferences'); } catch (e) { clear(root).append(errorBox(e)); return; }
  const p = d.preferences, I = {};
  const inp = (k, type = 'text', attrs = {}) => I[k] = h('input', { type, value: Array.isArray(p[k]) ? p[k].join(', ') : p[k], ...attrs });
  const interests = new Set(p.interests), transport = new Set(p.transport);
  const chips = (set, all) => h('div', { class: 'row' }, all.map((x) => { const c = h('span', { class: `pill chip ${set.has(x) ? 'on' : ''}`, onclick: () => { set.has(x) ? set.delete(x) : set.add(x); c.classList.toggle('on'); } }, x); return c; }));
  clear(root).append(h('h1', {}, 'Preferences'), h('div', { class: 'sub' }, 'Used by the recommendation engine, package builder and searches'),
    h('div', { class: 'card' }, h('div', { class: 'form' },
      field('Home airport (IATA)', inp('home_airport')), field('Home city', inp('home_city')), field('Passport (ISO3)', inp('passport')), field('Budget per trip (EUR)', inp('budget_eur', 'number')),
      field('Trip length min (days)', inp('trip_days_min', 'number')), field('Trip length max (days)', inp('trip_days_max', 'number')), field('Preferred temp min (°C)', inp('temp_min', 'number')), field('Preferred temp max (°C)', inp('temp_max', 'number')),
      field('Travellers', inp('travelers', 'number')), field('Max stops', inp('max_stops', 'number')), field('Alt. airport radius (km)', inp('alt_airport_radius_km', 'number')), field('Accommodation', I.accommodation = select(['budget', 'mid', 'comfort'], p.accommodation)),
      field('Avoid (countries / keywords, comma separated)', inp('avoid'))),
      h('h3', { style: { marginTop: '16px' } }, 'Preferred transportation'), chips(transport, ['flight', 'train', 'bus', 'car', 'ship']),
      h('h3', { style: { marginTop: '16px' } }, 'Interests'), chips(interests, d.interests),
      h('div', { style: { marginTop: '18px' } }, h('button', { class: 'btn', onclick: async () => {
        const body = { transport: [...transport], interests: [...interests], accommodation: I.accommodation.value };
        for (const [k, el] of Object.entries(I)) { if (k === 'accommodation') continue; body[k] = k === 'avoid' ? el.value.split(',').map((x) => x.trim()).filter(Boolean) : el.type === 'number' ? Number(el.value) : el.value; }
        try { await put('/api/preferences', body); toast('Preferences saved', 'ok'); } catch (e) { toast(e.message, 'bad'); }
      } }, 'Save'))));
}
