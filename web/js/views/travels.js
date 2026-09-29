import { get, post, put, del } from '../api.js';
import { h, clear, loading, errorBox, toast, modal, eur, fdate, badge, field, select, empty } from '../ui.js';

const TRANSPORT = ['', 'flight', 'train', 'bus', 'car', 'ship', 'multimodal', 'other'];
const FIELDS = [['country', 'Country (name or ISO3) *', 'text'], ['region', 'Region', 'text'], ['city', 'City', 'text'], ['depart_date', 'Departure date', 'date'], ['return_date', 'Return date', 'date'], ['origin', 'Departure airport/station', 'text'], ['destination', 'Destination airport/station', 'text'], ['carrier', 'Carrier / company', 'text'], ['lodging', 'Hotel / lodging', 'text'], ['cost_amount', 'Cost', 'number'], ['cost_currency', 'Currency', 'text'], ['rating', 'Rating (1-5)', 'number'], ['tags', 'Tags (comma separated)', 'text']];

export async function render(view) {
  const root = h('div', { class: 'page' });
  view.append(root);
  let status = '';
  async function load() {
    clear(root).append(loading());
    let trips;
    try { trips = (await get('/api/trips' + (status ? `?status=${status}` : ''))).trips; } catch (e) { clear(root).append(errorBox(e)); return; }
    clear(root).append(
      h('div', { class: 'row spread' }, h('div', {}, h('h1', {}, 'My Travels'), h('div', { class: 'sub' }, `${trips.length} trip(s)`)),
        h('div', { class: 'row' }, select([['', 'All'], ['done', 'Done'], ['planned', 'Planned']], status, { onchange: (e) => { status = e.target.value; load(); } }), h('button', { class: 'btn sec', onclick: importDlg }, 'Import CSV/JSON'), h('button', { class: 'btn sec', onclick: exportJson }, 'Export'), h('button', { class: 'btn', onclick: () => edit() }, '+ Add trip'))),
      trips.length ? h('div', { class: 'card pad0' }, h('table', {}, h('thead', {}, h('tr', {}, ['Destination', 'Dates', 'Days', 'Transport', 'Cost', 'Rating', 'Status', ''].map((x) => h('th', {}, x)))),
        h('tbody', {}, trips.map((t) => h('tr', {}, h('td', {}, h('b', {}, t.city || t.country_name), h('div', { class: 'small muted' }, [t.region, t.city ? t.country_name : ''].filter(Boolean).join(' · '), t.photos.length ? ` · 📷${t.photos.length}` : '')),
          h('td', {}, `${fdate(t.depart_date)}${t.return_date ? ' → ' + fdate(t.return_date) : ''}`), h('td', {}, t.duration_days ?? '—'), h('td', {}, [t.transport, t.carrier].filter(Boolean).join(' · ') || '—'),
          h('td', { class: 'num' }, t.cost_amount != null ? (t.cost_currency === 'EUR' ? eur(t.cost_amount) : `${t.cost_amount} ${t.cost_currency}${t.cost_eur ? ' (' + eur(t.cost_eur) + ')' : ''}`) : '—'), h('td', {}, t.rating ? '★'.repeat(t.rating) : '—'), h('td', {}, badge(t.status, t.status === 'done' ? 'ok' : '')),
          h('td', {}, h('button', { class: 'btn sec sm', onclick: () => edit(t) }, 'Edit')))))))
        : empty('No trips yet. Add your first trip, or import a CSV.'));
  }
  function edit(t) {
    const data = t ? { ...t, country: t.country_iso3, tags: (t.tags || []).join(', ') } : { cost_currency: 'EUR' };
    const inputs = {};
    const form = h('div', { class: 'form' }, FIELDS.map(([k, label, type]) => field(label, inputs[k] = h('input', { type, value: data[k] ?? '', step: type === 'number' ? 'any' : null }))),
      field('Transport', inputs.transport = select(TRANSPORT, data.transport || '')), field('Status', inputs.status = select([['', 'auto'], ['done', 'done'], ['planned', 'planned']], data.status || '')));
    const notes = h('textarea', { rows: 3, style: { width: '100%' } }, data.notes || '');
    const photos = t ? h('div', {}, h('h3', { style: { marginTop: '14px' } }, 'Photos'), h('div', { class: 'photos' }, t.photos.map((p) => h('div', {}, h('img', { src: `/photos/${p.filename}`, alt: p.caption || 'trip photo' }), h('button', { class: 'ghost small', onclick: async () => { await del(`/api/photos/${p.id}`); toast('Photo removed'); close(); load(); } }, '✕')))),
      h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/gif', onchange: async (e) => {
        const f = e.target.files[0]; if (!f) return;
        const b64 = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result.split(',')[1]); r.readAsDataURL(f); });
        try { await post(`/api/trips/${t.id}/photos`, { mime: f.type, data: b64, caption: f.name }); toast('Photo added', 'ok'); close(); load(); } catch (er) { toast(er.message, 'bad'); }
      } })) : h('div', { class: 'small muted' }, 'Save the trip first to attach photos.');
    const close = modal(t ? 'Edit trip' : 'Add trip', h('div', {}, form, field('Personal notes', notes), photos), [
      ...(t ? [{ label: 'Delete', cls: 'bad', onclick: async (c) => { if (confirm('Delete this trip?')) { await del(`/api/trips/${t.id}`); c(); load(); } } }] : []),
      { label: 'Save', onclick: async (c) => {
        const body = { notes: notes.value };
        for (const [k, el] of Object.entries(inputs)) if (el.value !== '') body[k] = el.value;
        if (!t) delete body.status;
        try { t ? await put(`/api/trips/${t.id}`, body) : await post('/api/trips', body); toast('Saved', 'ok'); c(); load(); } catch (e) { toast(e.message, 'bad'); }
      } }]);
  }
  function importDlg() {
    const ta = h('textarea', { rows: 9, style: { width: '100%' }, placeholder: 'country;city;depart_date;return_date;cost;currency;rating\nJapan;Tokyo;2024-04-01;2024-04-10;2100;EUR;5' });
    const file = h('input', { type: 'file', accept: '.csv,.json,.txt', onchange: async (e) => { ta.value = await e.target.files[0].text(); } });
    modal('Import trips', h('div', {}, h('p', { class: 'muted small' }, 'CSV (comma or semicolon) or JSON list. Columns: country*, region, city, depart_date, return_date, origin, destination, transport, carrier, lodging, cost, currency, rating, notes, tags. Invalid rows are reported, valid ones imported.'), file, ta), [{ label: 'Import', onclick: async (c) => {
      try { const txt = ta.value.trim(); const body = txt.startsWith('[') ? { trips: JSON.parse(txt) } : { csv: txt }; const r = await post('/api/trips/import', body); toast(`Imported ${r.imported}${r.errors.length ? `, ${r.errors.length} error(s): ${r.errors[0].error}` : ''}`, r.errors.length ? 'bad' : 'ok'); c(); load(); } catch (e) { toast(e.message, 'bad'); }
    } }]);
  }
  async function exportJson() {
    const d = await get('/api/trips/export');
    const a = h('a', { href: URL.createObjectURL(new Blob([JSON.stringify(d.trips, null, 2)], { type: 'application/json' })), download: 'my-travels.json' }); a.click();
  }
  load();
}
