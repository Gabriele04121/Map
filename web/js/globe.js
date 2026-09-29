// Interactive world map engine: orthographic globe + Mercator flat map on a plain <canvas>. No libraries, no tiles, works offline.
const D2R = Math.PI / 180, TAU = Math.PI * 2;
const merc = (lat) => Math.log(Math.tan(Math.PI / 4 + Math.max(-1.4835, Math.min(1.4835, lat)) / 2));
const unmerc = (y) => 2 * Math.atan(Math.exp(y)) - Math.PI / 2;

function prep(geom) {
  const polys = geom.type === 'MultiPolygon' ? geom.coordinates : [geom.coordinates];
  return polys.map((rings) => rings.map((ring) => {
    const a = new Float64Array(ring.length * 4);
    ring.forEach(([x, y], i) => { const lat = y * D2R; a[i * 4] = x * D2R; a[i * 4 + 1] = lat; a[i * 4 + 2] = Math.sin(lat); a[i * 4 + 3] = Math.cos(lat); });
    return a;
  }));
}
function inRing(x, y, ring) {
  let ins = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi || 1e-12) + xi) ins = !ins;
  }
  return ins;
}
function inGeom(x, y, g) {
  const polys = g.type === 'MultiPolygon' ? g.coordinates : [g.coordinates];
  return polys.some((p) => inRing(x, y, p[0]) && !p.slice(1).some((h) => inRing(x, y, h)));
}

export class WorldMap {
  constructor(canvas, cb = {}) {
    this.c = canvas; this.ctx = canvas.getContext('2d'); this.cb = cb;
    this.mode = 'globe'; this.lon0 = 12 * D2R; this.lat0 = 30 * D2R; this.k = 1;
    this.countries = []; this.cities = []; this.regions = null; this.regionsIso = null;
    this.status = () => null; this.regionStatus = () => null; this.cityStatus = () => null;
    this.sel = { iso3: null, regionId: null, cityId: null }; this.markers = []; this.dpr = 1;
    this.colors = {}; this.drag = null; this.raf = 0; this.anim = null; this.layers = { visited: true, planned: true, recommended: true, analyzed: true, cities: true };
    this.readColors(); this.bind(); this.resize();
    window.addEventListener('themechange', () => { this.readColors(); this.draw(); });
    new ResizeObserver(() => this.resize()).observe(canvas);
  }
  readColors() {
    const s = getComputedStyle(document.documentElement), g = (n) => s.getPropertyValue(n).trim();
    this.colors = { land: g('--land'), sea: g('--sea'), line: g('--line'), text: g('--text'), muted: g('--muted'), accent: g('--accent'), ok: g('--ok'), planned: g('--planned'), rec: g('--rec'), analyzed: g('--analyzed'), bg: g('--bg') };
  }
  setCountries(list) { this.countries = list.map((c) => ({ ...c, poly: prep(c.geometry) })); this.byIso = Object.fromEntries(this.countries.map((c) => [c.iso3, c])); this.draw(); }
  setCities(list) { this.cities = list; this.draw(); }
  setRegions(iso3, regions) { this.regionsIso = iso3; this.regions = regions ? regions.map((r) => ({ ...r, poly: prep(r.geometry) })) : null; this.draw(); }
  setMode(m) { this.mode = m; this.draw(); }
  setSelection(sel) { this.sel = { iso3: null, regionId: null, cityId: null, ...sel }; this.draw(); }

  resize() {
    const r = this.c.getBoundingClientRect(); this.dpr = window.devicePixelRatio || 1;
    this.w = Math.max(50, r.width); this.h = Math.max(50, r.height);
    this.c.width = this.w * this.dpr; this.c.height = this.h * this.dpr; this.draw();
  }
  get R() { return this.mode === 'globe' ? Math.min(this.w, this.h) / 2 * 0.9 * this.k : (this.w / TAU) * this.k; }

  // ---- projection -----------------------------------------------------------------
  project(lon, lat, sin, cos, off = 0) {
    const R = this.R, cx = this.w / 2, cy = this.h / 2;
    if (this.mode === 'flat') return [cx + R * (lon - this.lon0 + off * TAU), cy - R * (merc(lat) - merc(this.lat0)), true];
    const dl = lon - this.lon0, cd = Math.cos(dl), s0 = Math.sin(this.lat0), c0 = Math.cos(this.lat0);
    const vis = s0 * sin + c0 * cos * cd > 0;
    let x = R * cos * Math.sin(dl), y = R * (c0 * sin - s0 * cos * cd);
    if (!vis) { const l = Math.hypot(x, y) || 1; x *= R / l; y *= R / l; }
    return [cx + x, cy - y, vis];
  }
  pt(lonDeg, latDeg) { const lat = latDeg * D2R; return this.project(lonDeg * D2R, lat, Math.sin(lat), Math.cos(lat)); }
  invert(px, py) {
    const R = this.R, x = px - this.w / 2, y = -(py - this.h / 2);
    if (this.mode === 'flat') {
      let lon = this.lon0 + x / R; lon = ((lon + Math.PI) % TAU + TAU) % TAU - Math.PI;
      return [lon / D2R, unmerc(y / R + merc(this.lat0)) / D2R];
    }
    const rho = Math.hypot(x, y); if (rho > R) return null;
    const c = Math.asin(rho / R), s0 = Math.sin(this.lat0), c0 = Math.cos(this.lat0);
    const lat = rho === 0 ? this.lat0 : Math.asin(Math.cos(c) * s0 + y * Math.sin(c) * c0 / rho);
    const lon = this.lon0 + Math.atan2(x * Math.sin(c), rho * c0 * Math.cos(c) - y * s0 * Math.sin(c));
    return [((lon + Math.PI) % TAU + TAU) % TAU / D2R - 180, lat / D2R];
  }

  // ---- drawing --------------------------------------------------------------------
  draw() { if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = 0; this.render(); }); }
  ringPath(ctx, ring, off) {
    const n = ring.length / 4; let anyVis = false; const pts = [];
    for (let i = 0; i < n; i++) { const p = this.project(ring[i * 4], ring[i * 4 + 1], ring[i * 4 + 2], ring[i * 4 + 3], off); pts.push(p); if (p[2]) anyVis = true; }
    if (!anyVis) return false;
    if (this.mode === 'flat') { const mx = pts.reduce((a, p) => a + p[0], 0) / n; if (mx < -this.w * 0.5 || mx > this.w * 1.5) return false; }
    ctx.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < n; i++) ctx.lineTo(pts[i][0], pts[i][1]); ctx.closePath(); return true;
  }
  fillFeature(f, fill, stroke, lw = 0.6, alpha = 1) {
    const ctx = this.ctx; ctx.beginPath(); let any = false;
    for (const off of this.mode === 'flat' ? [-1, 0, 1] : [0]) for (const poly of f.poly) for (const ring of poly) any = this.ringPath(ctx, ring, off) || any;
    if (!any) return;
    if (fill) { ctx.globalAlpha = alpha; ctx.fillStyle = fill; ctx.fill('evenodd'); ctx.globalAlpha = 1; }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke(); }
  }
  colorFor(status) {
    const L = this.layers, C = this.colors;
    if (status.includes('visited') && L.visited) return C.ok;
    if (status.includes('planned') && L.planned) return C.planned;
    if (status.includes('recommended') && L.recommended) return C.rec;
    return null;
  }
  render() {
    const ctx = this.ctx, C = this.colors, R = this.R; ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);
    const cx = this.w / 2, cy = this.h / 2;
    if (this.mode === 'globe') {
      const g = ctx.createRadialGradient(cx - R * .3, cy - R * .3, R * .1, cx, cy, R); g.addColorStop(0, C.sea); g.addColorStop(1, C.bg);
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, TAU); ctx.fillStyle = g; ctx.fill(); ctx.strokeStyle = C.line; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R, 0, TAU); ctx.clip(); this.scene(); ctx.restore();
    } else { ctx.fillStyle = C.sea; ctx.fillRect(0, 0, this.w, this.h); this.scene(); }
  }
  scene() {
    const ctx = this.ctx, C = this.colors;
    // graticule
    ctx.strokeStyle = C.line; ctx.lineWidth = 0.4; ctx.globalAlpha = 0.5;
    for (let lo = -180; lo < 180; lo += 30) { ctx.beginPath(); for (let la = -80; la <= 80; la += 4) { const p = this.pt(lo, la); if (p[2]) (la === -80 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])); } ctx.stroke(); }
    for (let la = -60; la <= 60; la += 30) { ctx.beginPath(); let first = true; for (let lo = -180; lo <= 180; lo += 4) { const p = this.pt(lo, la); if (p[2]) { first ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]); first = false; } } ctx.stroke(); }
    ctx.globalAlpha = 1;
    const detail = this.regions && this.sel.iso3 === this.regionsIso;
    for (const c of this.countries) {
      const st = this.status(c.iso3) || [];
      const col = this.colorFor(st);
      const isSel = c.iso3 === this.sel.iso3;
      const dim = detail && !isSel;
      this.fillFeature(c, col || C.land, C.bg, 0.7, dim ? 0.55 : 1);
      if (col) this.fillFeature(c, null, col, 1.2);
      if (this.layers.analyzed && st.includes('analyzed')) this.fillFeature(c, null, C.analyzed, 2);
    }
    if (detail) {
      for (const r of this.regions) {
        const st = this.regionStatus(r) || [];
        const col = this.colorFor(st);
        this.fillFeature(r, col ? col : C.land, C.text, 0.6, col ? 0.85 : 1);
        if (this.layers.analyzed && st.includes('analyzed')) this.fillFeature(r, null, C.analyzed, 2);
      }
      const sr = this.regions.find((r) => r.id === this.sel.regionId);
      if (sr) this.fillFeature(sr, C.accent, '#fff', 2, 0.45);
    } else if (this.sel.iso3 && this.byIso[this.sel.iso3]) this.fillFeature(this.byIso[this.sel.iso3], C.accent, '#fff', 2, 0.35);
    this.drawCities(); this.drawMarkers();
  }
  drawCities() {
    if (!this.layers.cities) return;
    const ctx = this.ctx, C = this.colors, k = this.k, sel = this.sel;
    const minPop = this.mode === 'globe' ? (k > 20 ? 0 : k > 9 ? 100e3 : k > 4 ? 800e3 : k > 2.2 ? 3e6 : 1e12) : (k > 25 ? 0 : k > 10 ? 100e3 : k > 5 ? 800e3 : k > 2.5 ? 3e6 : 1e12);
    let n = 0;
    for (const c of this.cities) {
      const inSel = sel.iso3 && c.iso3 === sel.iso3;
      if (!(inSel || c.pop >= minPop)) continue;
      if (sel.iso3 && !inSel && k > 2.5 && this.regions) continue;
      const p = this.pt(c.lon, c.lat); if (!p[2] || p[0] < -20 || p[1] < -20 || p[0] > this.w + 20 || p[1] > this.h + 20) continue;
      if (++n > 700) break;
      const st = this.cityStatus(c) || [], col = this.colorFor(st) || C.text, isSel = c.id === sel.cityId;
      const r = isSel ? 6 : c.capital ? 4.2 : 3;
      ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, TAU); ctx.fillStyle = isSel ? C.accent : col; ctx.fill(); ctx.strokeStyle = C.bg; ctx.lineWidth = 1.2; ctx.stroke();
      if (isSel || inSel || k > 6) { ctx.font = `${isSel ? 700 : 500} 11px system-ui`; ctx.fillStyle = C.text; ctx.strokeStyle = C.bg; ctx.lineWidth = 3; ctx.strokeText(c.name, p[0] + 7, p[1] + 4); ctx.fillText(c.name, p[0] + 7, p[1] + 4); }
    }
  }
  drawMarkers() {
    const ctx = this.ctx, C = this.colors;
    for (const m of this.markers) {
      const p = this.pt(m.lon, m.lat); if (!p[2]) continue;
      ctx.beginPath(); ctx.arc(p[0], p[1], m.r || 4, 0, TAU); ctx.fillStyle = m.color || C.accent; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke();
      if (m.label) { ctx.font = '600 11px system-ui'; ctx.fillStyle = C.text; ctx.strokeStyle = C.bg; ctx.lineWidth = 3; ctx.strokeText(m.label, p[0] + 8, p[1] + 4); ctx.fillText(m.label, p[0] + 8, p[1] + 4); }
    }
  }

  // ---- hit testing -----------------------------------------------------------------
  hit(px, py) {
    const ll = this.invert(px, py); if (!ll) return null;
    if (this.layers.cities) {
      let best = null, bd = 64; // 8px
      for (const c of this.cities) {
        if (Math.abs(c.lat - ll[1]) > 30 / Math.max(1, this.k) + 2) continue;
        const inSel = this.sel.iso3 && c.iso3 === this.sel.iso3;
        if (!inSel && c.pop < 800e3 && this.k < 4) continue;
        const p = this.pt(c.lon, c.lat); if (!p[2]) continue;
        const d = (p[0] - px) ** 2 + (p[1] - py) ** 2;
        if (d < bd) { bd = d; best = c; }
      }
      if (best && (this.k > 2.2 || best.pop > 3e6 || this.sel.iso3 === best.iso3)) return { level: 'city', city: best };
    }
    const [lon, lat] = ll;
    if (this.regions && this.sel.iso3 === this.regionsIso) {
      for (const r of this.regions) {
        const b = r.bbox; if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
        if (inGeom(lon, lat, r.geometry)) return { level: 'region', region: r, iso3: this.regionsIso };
      }
    }
    for (const c of this.countries) {
      const b = c.bbox; if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
      if (inGeom(lon, lat, c.geometry)) return { level: 'country', iso3: c.iso3, name: c.name };
    }
    // tiny states: snap to nearest small country within 9px of its bbox centre
    let best = null, bd = 81;
    for (const c of this.countries) {
      const b = c.bbox; if (b[2] - b[0] > 3 || b[3] - b[1] > 3) continue;
      const p = this.pt((b[0] + b[2]) / 2, (b[1] + b[3]) / 2); if (!p[2]) continue;
      const d = (p[0] - px) ** 2 + (p[1] - py) ** 2; if (d < bd) { bd = d; best = c; }
    }
    return best ? { level: 'country', iso3: best.iso3, name: best.name } : null;
  }

  // ---- interaction -----------------------------------------------------------------
  bind() {
    const c = this.c, pos = (e) => { const r = c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    c.addEventListener('pointerdown', (e) => { c.setPointerCapture(e.pointerId); this.anim = null; this.drag = { p: pos(e), moved: 0, lon0: this.lon0, lat0: this.lat0 }; });
    c.addEventListener('pointermove', (e) => {
      const p = pos(e);
      if (this.drag) {
        const dx = p[0] - this.drag.p[0], dy = p[1] - this.drag.p[1]; this.drag.moved = Math.max(this.drag.moved, Math.hypot(dx, dy));
        if (this.drag.moved > 3) {
          const R = this.R;
          if (this.mode === 'globe') { this.lon0 = this.drag.lon0 - dx / R / Math.cos(this.lat0 * 0.6); this.lat0 = Math.max(-1.45, Math.min(1.45, this.drag.lat0 + dy / R)); }
          else { this.lon0 = this.drag.lon0 - dx / R; this.lat0 = unmerc(merc(this.drag.lat0) + dy / R); }
          this.cb.onMove?.(); this.draw();
        }
      } else if (this.cb.onHover) { const h = this.hit(p[0], p[1]); this.cb.onHover(h, p); c.style.cursor = h ? 'pointer' : 'grab'; }
    });
    c.addEventListener('pointerup', (e) => {
      const d = this.drag; this.drag = null; if (!d || d.moved > 3) return;
      const p = pos(e); this.cb.onSelect?.(this.hit(p[0], p[1]), p);
    });
    c.addEventListener('pointerleave', () => this.cb.onHover?.(null));
    c.addEventListener('wheel', (e) => { e.preventDefault(); this.zoomBy(Math.exp(-e.deltaY * 0.0016)); }, { passive: false });
    c.addEventListener('dblclick', () => this.zoomBy(1.8));
  }
  zoomBy(f) { this.k = Math.max(0.7, Math.min(900, this.k * f)); this.cb.onMove?.(); this.draw(); }

  flyTo(lon, lat, k, ms = 750) {
    const from = { lon: this.lon0, lat: this.lat0, lk: Math.log(this.k) }, to = { lon: lon * D2R, lat: Math.max(-1.4, Math.min(1.4, lat * D2R)), lk: Math.log(Math.max(0.7, Math.min(900, k))) };
    let dl = to.lon - from.lon; dl = ((dl + Math.PI) % TAU + TAU) % TAU - Math.PI;
    const t0 = performance.now(), token = (this.anim = {});
    const step = (t) => {
      if (this.anim !== token) return;
      const u = Math.min(1, (t - t0) / ms), e = u < .5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      this.lon0 = from.lon + dl * e; this.lat0 = from.lat + (to.lat - from.lat) * e; this.k = Math.exp(from.lk + (to.lk - from.lk) * e); this.render(); this.cb.onMove?.();
      if (u < 1) requestAnimationFrame(step); else this.anim = null;
    };
    requestAnimationFrame(step);
  }
  fitBBox(b, pad = 0.72) {
    const [x0, y0, x1, y1] = b, wide = x1 - x0 > 100;
    const lon = wide ? 0 : (x0 + x1) / 2, lat = (y0 + y1) / 2;
    const dLon = Math.max(1e-3, wide ? 200 : x1 - x0) * D2R, dLat = Math.max(1e-3, y1 - y0) * D2R;
    let Rneed, base;
    if (this.mode === 'globe') {
      Rneed = pad * Math.min(this.w, this.h) / Math.max(dLon * Math.cos(lat * D2R), dLat, 0.004); base = Math.min(this.w, this.h) / 2 * 0.9;
    } else {
      Rneed = Math.min(pad * this.w / dLon, pad * this.h / Math.max(1e-3, merc(y1 * D2R) - merc(y0 * D2R))); base = this.w / TAU;
    }
    this.flyTo(lon, lat, Math.max(0.8, Math.min(900, Rneed / base)));
  }
  focusPoint(lon, lat, k = 14) { this.flyTo(lon, lat, k); }
  home() { this.flyTo(12, 30, 1); }
}
