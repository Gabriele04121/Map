import { get, post } from '../api.js';
import { h, clear, loading, errorBox, badge, toast, num, compact } from '../ui.js';
import { WorldMap } from '../globe.js';
import { quickFacts, sectionView } from './dossier.js';

const norm = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
let cache = null;   // geometry + cities are big: load once per session

async function loadStatic() {
  if (cache) return cache;
  const [geo, cities, sums] = await Promise.all([get('/geo/countries.geo.json'), get('/geo/cities.json'), get('/api/geo/countries')]);
  cache = { geo, cities, countries: Object.fromEntries(sums.countries.map((c) => [c.iso3, c])) };
  return cache;
}

export async function render(view, r) {
  const wrap = h('div', { class: 'mapview' });
  view.append(wrap);
  wrap.append(loading('Loading world…'));
  let S, state;
  try { [S, state] = await Promise.all([loadStatic(), get('/api/map/state')]); } catch (e) { clear(wrap).append(errorBox(e)); return; }
  clear(wrap);

  const canvas = h('canvas'), tip = h('div', { class: 'tip hidden' }), crumbs = h('div', { class: 'crumbs' });
  const panel = h('div', { class: 'sidepanel' });
  const layers = { visited: true, planned: true, recommended: true, analyzed: true, cities: true };
  const legendItem = (key, color, label) => h('label', { style: { flexDirection: 'row', alignItems: 'center', gap: '6px', color: 'var(--text)', cursor: 'pointer' } },
    h('input', { type: 'checkbox', checked: true, onchange: (e) => { layers[key] = e.target.checked; map.layers[key] = e.target.checked; map.draw(); } }), h('i', { style: { background: color, width: '12px', height: '12px', borderRadius: '3px', display: 'inline-block' } }), label);
  const legend = h('div', { class: 'legend' }, legendItem('visited', 'var(--ok)', 'Visited'), legendItem('planned', 'var(--planned)', 'Planned'), legendItem('recommended', 'var(--rec)', 'Recommended'), legendItem('analyzed', 'var(--analyzed)', 'Analysed (outline)'), legendItem('cities', 'var(--text)', 'Cities'),
    h('div', { class: 'small muted' }, h('i', { style: { background: 'var(--land)', width: '12px', height: '12px', borderRadius: '3px', display: 'inline-block', marginRight: '6px' } }), 'Not visited'));
  const modeBtn = h('button', { class: 'btn sec sm', onclick: () => { map.setMode(map.mode === 'globe' ? 'flat' : 'globe'); modeBtn.textContent = map.mode === 'globe' ? '🌍 Globe' : '🗺 Flat'; } }, '🌍 Globe');
  const tools = h('div', { class: 'maptools' }, h('div', { class: 'box' }, crumbs), h('div', { class: 'box' }, h('button', { class: 'btn sec sm', onclick: () => map.zoomBy(1.6) }, '＋'), h('button', { class: 'btn sec sm', onclick: () => map.zoomBy(1 / 1.6) }, '－'), modeBtn, h('button', { class: 'btn sec sm', onclick: () => go({ level: 'world' }) }, '⌂ World')));
  wrap.append(h('div', { class: 'mapwrap' }, canvas, tools, legend, tip), panel);

  // ---- status resolvers (what is visited / planned / recommended / analysed)
  const marks = state.marks, rec = new Set(state.recommended.map((x) => x.iso3)), plannedC = new Set(state.planned_trips.map((t) => t.place_id));
  const visitedNames = (iso) => state.visited[iso] ? state.visited[iso] : null;
  const status = (iso3) => {
    const out = [], m = marks[`country:${iso3}`] || [];
    if (state.visited[iso3]) out.push('visited');
    if (m.includes('planned') || plannedC.has(`country:${iso3}`)) out.push('planned');
    if (rec.has(iso3) || m.includes('recommended') || m.includes('wishlist')) out.push('recommended');
    if (m.includes('analyzed')) out.push('analyzed');
    return out;
  };
  const map = new WorldMap(canvas, {
    onSelect: (hit) => go(hit ? hit : { level: 'world' }),
    onHover: (hit, p) => { if (!hit) return tip.classList.add('hidden'); tip.classList.remove('hidden'); tip.style.left = p[0] + 14 + 'px'; tip.style.top = p[1] + 14 + 'px'; tip.textContent = hit.level === 'country' ? hit.name : hit.level === 'region' ? hit.region.name : hit.city.name; },
  });
  map.status = status;
  map.regionStatus = (rg) => {
    const out = [], v = visitedNames(rg.iso3), m = marks[`region:${rg.iso3}:${rg.id}`] || [];
    if (v && v.regions.some((n) => norm(n) === norm(rg.name) || norm(n) === norm(rg.name_en))) out.push('visited');
    if (m.includes('planned')) out.push('planned'); if (m.includes('wishlist') || m.includes('recommended')) out.push('recommended'); if (m.includes('analyzed')) out.push('analyzed');
    return out;
  };
  map.cityStatus = (c) => {
    const out = [], v = visitedNames(c.iso3), m = marks[`city:${c.id}`] || [];
    if (v && v.cities.some((n) => norm(n) === norm(c.name))) out.push('visited');
    if (m.includes('planned')) out.push('planned'); if (m.includes('wishlist')) out.push('recommended'); if (m.includes('analyzed')) out.push('analyzed');
    return out;
  };
  map.setCountries(S.geo); map.setCities(S.cities);
  map.markers = [...(state.home ? [{ lat: state.home.lat, lon: state.home.lon, color: '#f43f5e', label: `Home ${state.home.iata}`, r: 5 }] : []), ...state.trip_points.map((p) => ({ lat: p.lat, lon: p.lon, color: 'var(--ok)', r: 3 }))];

  // ---- navigation (WORLD > COUNTRY > REGION > CITY)
  const nav = { level: 'world', iso3: null, region: null, city: null };
  const regionsCache = {};
  async function ensureRegions(iso3) {
    if (map.regionsIso === iso3 && map.regions) return;
    map.setRegions(iso3, null);
    try { regionsCache[iso3] = regionsCache[iso3] || await get(`/geo/admin1/${iso3}.json`); map.setRegions(iso3, regionsCache[iso3]); } catch { map.setRegions(iso3, null); }   // some countries have no admin-1 file
  }
  async function go(t) {
    if (t.level === 'world') { Object.assign(nav, { level: 'world', iso3: null, region: null, city: null }); map.setSelection({}); map.setRegions(null, null); map.home(); }
    else if (t.level === 'country') {
      Object.assign(nav, { level: 'country', iso3: t.iso3, region: null, city: null });
      map.setSelection({ iso3: t.iso3 }); const c = map.byIso[t.iso3]; if (c) map.fitBBox(c.bbox); await ensureRegions(t.iso3);
    } else if (t.level === 'region') {
      Object.assign(nav, { level: 'region', iso3: t.iso3, region: t.region, city: null });
      map.setSelection({ iso3: t.iso3, regionId: t.region.id }); map.fitBBox(t.region.bbox);
    } else if (t.level === 'city') {
      const c = t.city; await ensureRegions(c.iso3);
      const region = (regionsCache[c.iso3] || []).find((rg) => norm(rg.name) === norm(c.admin1) || norm(rg.name_en) === norm(c.admin1)) || null;
      Object.assign(nav, { level: 'city', iso3: c.iso3, region, city: c });
      map.setSelection({ iso3: c.iso3, regionId: region?.id, cityId: c.id }); map.focusPoint(c.lon, c.lat, Math.max(map.k, 22));
    }
    paintCrumbs(); paintPanel();
  }
  function paintCrumbs() {
    clear(crumbs);
    const parts = [['World', () => go({ level: 'world' })]];
    if (nav.iso3) parts.push([S.countries[nav.iso3].name, () => go({ level: 'country', iso3: nav.iso3 })]);
    if (nav.region) parts.push([nav.region.name, () => go({ level: 'region', iso3: nav.iso3, region: nav.region })]);
    if (nav.city) parts.push([nav.city.name, () => {}]);
    parts.forEach(([t, f], i) => { if (i) crumbs.append('›'); crumbs.append(h('a', { onclick: f }, t)); });
  }

  // ---- side panel
  let token = 0;
  function placeId() { return nav.level === 'city' ? `city:${nav.city.id}` : nav.level === 'region' ? `region:${nav.iso3}:${nav.region.id}` : nav.level === 'country' ? `country:${nav.iso3}` : null; }
  async function toggleMark(pid, mark) {
    const on = !(marks[pid] || []).includes(mark);
    try { await post('/api/marks', { place_id: pid, mark, on }); marks[pid] = on ? [...(marks[pid] || []), mark] : (marks[pid] || []).filter((x) => x !== mark); map.draw(); paintPanel(); toast(`${mark} ${on ? 'set' : 'removed'}`, 'ok'); } catch (e) { toast(e.message, 'bad'); }
  }
  function worldPanel() {
    const v = Object.keys(state.visited).length;
    return h('div', {}, h('h2', { style: { marginTop: 0 } }, 'World'), h('p', { class: 'muted' }, 'Click a country to zoom in, then a region, then a city. Drag to rotate, wheel to zoom.'),
      h('div', { class: 'facts' }, h('div', { class: 'fact' }, h('span', {}, 'Countries visited'), h('b', {}, v)), h('div', { class: 'fact' }, h('span', {}, 'Recommended'), h('b', {}, state.recommended.length))),
      h('h3', {}, 'Suggested next'), h('div', { class: 'list' }, state.recommended.slice(0, 8).map((x) => h('a', { class: 'row', href: '#', onclick: (e) => { e.preventDefault(); go({ level: 'country', iso3: x.iso3 }); } }, `${S.countries[x.iso3].flag || ''} ${S.countries[x.iso3].name}`, h('span', { class: 'badge' }, `score ${x.score}`)))),
      h('div', { class: 'small muted' }, 'Scores come from the explainable recommendation engine - see Recommendations.'));
  }
  async function paintPanel() {
    const my = ++token, pid = placeId();
    clear(panel);
    if (!pid) return panel.append(worldPanel());
    const c = S.countries[nav.iso3], name = nav.city?.name || nav.region?.name || c.name;
    const ms = marks[pid] || [];
    const st = nav.level === 'country' ? status(nav.iso3) : [];
    panel.append(h('div', {}, h('div', { class: 'row spread' }, h('h2', { style: { margin: 0 } }, `${nav.level === 'country' ? (c.flag || '') + ' ' : ''}${name}`), h('span', { class: 'badge' }, nav.level.toUpperCase())),
      h('div', { class: 'row', style: { margin: '8px 0' } }, [...new Set([...st, ...ms])].map((x) => badge(x, x === 'visited' ? 'ok' : x === 'recommended' ? 'est' : ''))),
      h('div', { class: 'row' }, ['planned', 'wishlist'].map((m) => h('button', { class: `btn sm ${ms.includes(m) ? '' : 'sec'}`, onclick: () => toggleMark(pid, m) }, `${ms.includes(m) ? '✓ ' : '+ '}${m}`)),
        h('a', { class: 'btn sm sec', href: `#/place/${encodeURIComponent(pid)}` }, 'Full report →'))));
    const factsHost = h('div', {}, loading('Loading facts…')), extra = h('div', {}), children = h('div', {});
    panel.append(factsHost, children, extra);
    // children: regions of country / cities of region or country
    if (nav.level === 'country') {
      const regs = map.regions && map.regionsIso === nav.iso3 ? map.regions : null;
      if (regs) children.append(h('h3', {}, `Regions (${regs.length})`), h('div', { class: 'list' }, [...regs].sort((a, b) => a.name.localeCompare(b.name)).slice(0, 60).map((rg) => h('a', { class: 'row', href: '#', onclick: (e) => { e.preventDefault(); go({ level: 'region', iso3: nav.iso3, region: rg }); } }, rg.name, h('span', { class: 'small muted' }, rg.type || '')))));
      const cs = S.cities.filter((x) => x.iso3 === nav.iso3).slice(0, 12);
      children.append(h('h3', {}, 'Main cities'), h('div', { class: 'list' }, cs.map((x) => cityRow(x))));
    } else if (nav.level === 'region') {
      try {
        const rs = await get(`/api/geo/country/${nav.iso3}/cities?region=${encodeURIComponent(nav.region.id)}`);
        if (my !== token) return;
        children.append(h('h3', {}, `Cities in ${nav.region.name}`), rs.cities.length ? h('div', { class: 'list' }, rs.cities.map((x) => cityRow(x))) : h('div', { class: 'muted small' }, 'No cities in the dataset for this region.'));
      } catch (e) { children.append(errorBox(e)); }
    } else if (nav.level === 'city') {
      children.append(h('div', { class: 'facts' }, h('div', { class: 'fact' }, h('span', {}, 'Region'), h('b', {}, nav.city.admin1 || '—')), h('div', { class: 'fact' }, h('span', {}, 'Coordinates'), h('b', {}, `${nav.city.lat}, ${nav.city.lon}`))));
    }
    // facts load progressively: offline sections first, live ones after
    const secs = {};
    const upd = () => { if (my === token) clear(factsHost).append(quickFacts(secs, { type: nav.level, name })); };
    upd();
    const batches = [['overview', 'cost', 'how_to_get_there'], ['when_to_go', 'safety', 'events']];
    for (const b of batches) {
      get(`/api/dossier?place=${encodeURIComponent(pid)}&sections=${b.join(',')}`).then((d) => { Object.assign(secs, d.sections); upd(); if (b[0] === 'overview' && !(marks[pid] || []).includes('analyzed')) { marks[pid] = [...(marks[pid] || []), 'analyzed']; map.draw(); } })
        .catch((e) => { if (my === token) factsHost.append(errorBox(e)); });
    }
    // text sections (public transport, attractions, food) are heavier: lazy accordions
    ['transport', 'attractions', 'food'].forEach((n) => {
      const body = h('div', { class: 'muted small' }, 'Open to load…');
      let done = false;
      const det = h('details', { ontoggle: async () => {
        if (!det.open || done) return; done = true; clear(body).append(loading());
        try { const d = await get(`/api/dossier?place=${encodeURIComponent(pid)}&sections=${n}`); clear(body).append(sectionView(n, d.sections[n], { name })); } catch (e) { clear(body).append(errorBox(e)); }
      } }, h('summary', {}, { transport: 'Public transport', attractions: 'Main attractions', food: 'Local food' }[n]), body);
      extra.append(det);
    });
  }
  function cityRow(x) { return h('a', { class: 'row', href: '#', onclick: (e) => { e.preventDefault(); go({ level: 'city', city: x }); } }, `${x.capital ? '★ ' : ''}${x.name}`, h('span', { class: 'small muted' }, compact(x.pop))); }

  // deep-link: #/map?focus=country:JPN | city:JPN:123 | region:...
  const focus = r.params.focus;
  paintCrumbs(); paintPanel();
  if (focus) {
    try {
      const [kind, ...rest] = focus.split(':');
      if (kind === 'country') go({ level: 'country', iso3: rest[0] });
      else if (kind === 'city') { const c = S.cities.find((x) => x.id === rest.join(':')); if (c) go({ level: 'city', city: c }); }
      else if (kind === 'region') { await ensureRegions(rest[0]); const rg = (regionsCache[rest[0]] || []).find((x) => x.id === rest.slice(1).join(':')); if (rg) go({ level: 'region', iso3: rest[0], region: rg }); }
    } catch { /* ignore bad focus */ }
  }
  return { destroy() { /* canvas + observers are GC'd with the view */ } };
}
