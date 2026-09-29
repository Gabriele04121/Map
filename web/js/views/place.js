import { get } from '../api.js';
import { h, clear, loading, errorBox, badge, toast } from '../ui.js';
import { sectionView } from './dossier.js';
import { post } from '../api.js';

const TABS = [['overview', 'Overview'], ['when_to_go', 'When to go'], ['how_to_get_there', 'How to get there'], ['cost', 'Cost'], ['transport', 'Transport'], ['food', 'Food'], ['attractions', 'Attractions'], ['nightlife', 'Nightlife'], ['safety', 'Safety'], ['weather', 'Weather'], ['events', 'Events'], ['itineraries', 'Itineraries'], ['hotels', 'Hotels'], ['flights', 'Flights'], ['trains', 'Trains'], ['local_costs', 'Local costs']];

export async function render(view, r) {
  const id = r.arg;
  const root = h('div', { class: 'page' }, loading());
  view.append(root);
  let place;
  try { place = (await get(`/api/place?id=${encodeURIComponent(id)}`)); } catch (e) { clear(root).append(errorBox(e)); return; }
  const body = h('div', {}), tabs = h('div', { class: 'tabs' });
  const loaded = {};
  const show = async (name, force = false) => {
    [...tabs.children].forEach((b) => b.classList.toggle('active', b.dataset.t === name));
    clear(body).append(loading());
    if (!loaded[name] || force) {
      try { const d = await get(`/api/dossier?place=${encodeURIComponent(id)}&sections=${name}${force ? '&force=1' : ''}`); loaded[name] = d.sections[name]; } catch (e) { clear(body).append(errorBox(e)); return; }
    }
    clear(body).append(sectionView(name, loaded[name], place), h('div', { style: { marginTop: '12px' } }, h('button', { class: 'btn sec sm', onclick: () => show(name, true) }, '↻ Refresh this section')));
  };
  TABS.forEach(([n, l]) => tabs.append(h('button', { 'data-t': n, onclick: () => show(n) }, l)));
  const mark = (m) => async () => { try { await post('/api/marks', { place_id: id, mark: m, on: !place.marks.includes(m) }); place.marks = place.marks.includes(m) ? place.marks.filter((x) => x !== m) : [...place.marks, m]; toast(`${m}: ${place.marks.includes(m) ? 'added' : 'removed'}`, 'ok'); paintHead(); } catch (e) { toast(e.message, 'bad'); } };
  const head = h('div', {});
  const paintHead = () => clear(head).append(h('div', { class: 'row spread' }, h('div', {}, h('h1', {}, place.name), h('div', { class: 'sub' }, `${place.type}${place.country ? ' · ' + place.country.name : ''}`, ' ', place.marks.map((m) => badge(m, 'ok')))),
    h('div', { class: 'row' }, h('a', { class: 'btn sec', href: `#/map?focus=${encodeURIComponent(id)}` }, 'Show on map'), h('button', { class: 'btn sec', onclick: mark('planned') }, place.marks.includes('planned') ? '✓ Planned' : '+ Plan'), h('button', { class: 'btn sec', onclick: mark('wishlist') }, place.marks.includes('wishlist') ? '✓ Wishlist' : '+ Wishlist'))));
  paintHead();
  clear(root).append(head, tabs, body);
  show('overview');
}
