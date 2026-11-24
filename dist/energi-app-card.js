// Wattlas – energi-app som "hjemmeside" i Home Assistant. Ét kort, egne SVG-grafer, ingen afhængigheder.
// Faner: Live · Økonomi · Historik · Elpris · Solprognose.
// Data: hass.states (live), sql.query (daglig historik fra langtidsstatistikken), recorder-statistik (i dag),
// sensor.energi_dagslog (sparet kr. pr. dag).
if (!customElements.get('emhass-plan-card')) import('./emhass-plan-card.js' + new URL(import.meta.url).search).catch(e => console.warn('Wattlas: planens logik kunne ikke hentes', e));
(() => {
  const VERSION = '3.0.5';
  // Wattlas HUD-palet (bevidst forskellig fra SunMate)
  const C = {sol: '#fbbf24', net: '#f472b6', hus: '#22d3ee', bat: '#34d399', ok: '#4ade80', warn: '#fb923c', err: '#fb7185',
    goal: '#64748b', blue: '#818cf8', cyan: '#22d3ee', lav: '#4ade80', hoej: '#fb923c', spids: '#fb7185'};
  const SEED = {};
  let FOER_NOV = 0, FOER_DATO = null; // kort-konfiguration: startsaldo (kr. sparet før Wattlas) og startsaldo_dato
  let START = ymd0(new Date()); // sættes fra input_datetime.solcelle_start_dato
  const LOGO = new URL('./wattlas-logo.svg', import.meta.url).href;
  let T = {}; // tariffer fra Wattlas-indstillingerne
  function ymd0(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
  const MAANED = ['januar', 'februar', 'marts', 'april', 'maj', 'juni', 'juli', 'august', 'september', 'oktober', 'november', 'december'];
  const MDK = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];
  const UGEDAG = ['søn', 'man', 'tir', 'ons', 'tor', 'fre', 'lør'];

  const nf = (v, d = 0) => v === null || v === undefined || isNaN(v) ? '–' :
    Number(v).toLocaleString('da-DK', {minimumFractionDigits: d, maximumFractionDigits: d});
  const kr = (v, d = 0) => nf(v, d) + ' kr.';
  const ymd = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const pd = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
  const addD = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const monday = d => { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const tv = k => T[k] || 0;
  const net = hr => hr < 6 ? tv('lav') : (hr >= 17 && hr < 21 ? tv('spids') : tv('hoej'));
  const buy = (spot, hr) => spot + (net(hr) + tv('afgift')) * 1.25 + tv('tillaeg');
  const sell = spot => spot / 1.25 - tv('salg_net') * 1.25 - tv('salg_gebyr');
  const tarif = hr => hr < 6 ? 'lav' : (hr >= 17 && hr < 21 ? 'spids' : 'hoej');

  const SQL_DAGE = start => `WITH r AS (SELECT sm.statistic_id id, st.start_ts ts, st.state sv, st.sum - LAG(st.sum) OVER (PARTITION BY sm.statistic_id ORDER BY st.start_ts) ds
 FROM statistics st JOIN statistics_meta sm ON st.metadata_id = sm.id
 WHERE sm.statistic_id IN ('sensor.wattlas_i_dag_produktion','sensor.wattlas_total_koebt','sensor.wattlas_total_solgt',
 'sensor.wattlas_i_dag_ladet','sensor.wattlas_i_dag_afladet','sensor.energi_data_service')
 AND st.start_ts >= CAST(strftime('%s', '${start}', '-1 day') AS INTEGER)),
h AS (SELECT ts, CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INTEGER) hr,
 MAX(0, COALESCE(SUM(CASE WHEN id = 'sensor.wattlas_i_dag_produktion' THEN ds END), 0)) pv, MAX(0, COALESCE(SUM(CASE WHEN id = 'sensor.wattlas_total_koebt' THEN ds END), 0)) b,
 MAX(0, COALESCE(SUM(CASE WHEN id = 'sensor.wattlas_total_solgt' THEN ds END), 0)) s, MAX(0, COALESCE(SUM(CASE WHEN id = 'sensor.wattlas_i_dag_ladet' THEN ds END), 0)) ch,
 MAX(0, COALESCE(SUM(CASE WHEN id = 'sensor.wattlas_i_dag_afladet' THEN ds END), 0)) dis, MAX(CASE WHEN id = 'sensor.energi_data_service' THEN sv END) p FROM r GROUP BY ts)
SELECT date(ts, 'unixepoch', 'localtime') d, ROUND(SUM(pv), 1) pv, ROUND(SUM(b), 1) b, ROUND(SUM(s), 1) s, ROUND(SUM(ch), 1) ch, ROUND(SUM(dis), 1) dis,
 ROUND(SUM(CASE WHEN hr < 6 THEN b ELSE 0 END), 1) bl, ROUND(SUM(CASE WHEN hr >= 17 AND hr < 21 THEN b ELSE 0 END), 1) bs,
 ROUND(SUM(CASE WHEN (hr >= 6 AND hr < 17) OR hr >= 21 THEN b ELSE 0 END), 1) bh
FROM h WHERE date(ts, 'unixepoch', 'localtime') >= '${start}' GROUP BY 1 ORDER BY 1`;

  // ---------- SVG-grafer ----------
  const niceMax = v => { if (v <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(v))); const n = v / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; };

  function bars({labels, series, height = 240, stacked = false, unit = '', line = null, min = null, every = 1, fmt = v => nf(v, v < 10 ? 1 : 0), highlight = -1, W = 760}) {
    W = Math.round(W); const H = height;
    every = Math.max(every, Math.ceil(labels.length * 46 / W));
    const L = 46, R = 10, T = 14, B = 30;
    const n = labels.length || 1;
    const tot = i => stacked ? series.reduce((a, s) => a + Math.max(0, s.values[i] || 0), 0) : Math.max(...series.map(s => s.values[i] || 0));
    const neg = Math.min(0, ...series.flatMap(s => s.values.map(v => v || 0)));
    let mx = Math.max(...labels.map((_, i) => tot(i)), line ? Math.max(...line.values.filter(v => v != null)) : 0, 0.001);
    mx = niceMax(mx); const mn = min !== null ? min : (neg < 0 ? -niceMax(-neg) : 0);
    const y = v => T + (H - T - B) * (1 - (v - mn) / (mx - mn));
    const bw = (W - L - R) / n, gap = Math.min(10, bw * 0.25);
    let g = '';
    for (let k = 0; k <= 4; k++) { const v = mn + (mx - mn) * k / 4; g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${L - 6}" y="${y(v) + 4}" class="ax" text-anchor="end">${nf(v, Math.abs(mx - mn) < 5 ? 1 : 0)}</text>`; }
    labels.forEach((lb, i) => {
      const x0 = L + i * bw + gap / 2, w = bw - gap;
      if (i === highlight) g += `<rect x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - B}" class="hl"/>`;
      if (stacked) {
        let acc = 0;
        series.forEach(s => { const v = Math.max(0, s.values[i] || 0); if (!v) return; const y1 = y(acc + v), y0 = y(acc); acc += v;
          g += `<rect x="${x0}" y="${y1}" width="${w}" height="${Math.max(0, y0 - y1)}" rx="2" fill="${s.color}"><title>${esc(lb)} · ${esc(s.name)}: ${fmt(v)} ${unit}</title></rect>`; });
      } else {
        const sw = w / series.length;
        series.forEach((s, j) => { const v = s.values[i]; if (v == null) return; const c = typeof s.color === 'function' ? s.color(v, i) : s.color;
          const ya = y(Math.max(v, 0)), yb = y(Math.min(v, 0));
          g += `<rect x="${x0 + j * sw + 1}" y="${ya}" width="${Math.max(1, sw - 2)}" height="${Math.max(1, yb - ya)}" rx="3" fill="${c}"><title>${esc(lb)} · ${esc(s.name)}: ${fmt(v)} ${unit}</title></rect>`; });
      }
      if (i % every === 0) g += `<text x="${L + i * bw + bw / 2}" y="${H - 10}" class="ax" text-anchor="middle">${esc(lb)}</text>`;
    });
    if (line) {
      const pts = line.values.map((v, i) => v == null ? null : `${L + i * bw + bw / 2},${y(v)}`).filter(Boolean);
      g += `<polyline points="${pts.join(' ')}" fill="none" stroke="${line.color}" stroke-width="2.5" stroke-dasharray="${line.dash || ''}"/>`;
    }
    if (mn < 0) g += `<line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="var(--secondary-text-color)" stroke-width="1"/>`;
    return `<svg viewBox="0 0 ${W} ${H}" class="chart">${g}</svg>`;
  }

  function lines({series, height = 260, xmin, xmax, xticks = [], unit = '', hlines = [], vlines = [], area = true, fmt = v => nf(v), W = 760}) {
    W = Math.round(W); const H = height;
    const L = 56, R = 26, T = 14, B = 30;
    const all = series.flatMap(s => s.pts.map(p => p[1])).concat(hlines.map(h => h.v));
    const mx = niceMax(Math.max(...all, 0.001)), mn = Math.min(0, ...all);
    const x = t => L + (W - L - R) * (t - xmin) / ((xmax - xmin) || 1), y = v => T + (H - T - B) * (1 - (v - mn) / (mx - mn));
    let g = '';
    for (let k = 0; k <= 4; k++) { const v = mn + (mx - mn) * k / 4; g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${L - 6}" y="${y(v) + 4}" class="ax" text-anchor="end">${fmt(v)}</text>`; }
    xticks.forEach(([t, lb]) => { g += `<line x1="${x(t)}" x2="${x(t)}" y1="${T}" y2="${H - B}" class="grid"/><text x="${x(t)}" y="${H - 10}" class="ax" text-anchor="middle">${esc(lb)}</text>`; });
    vlines.forEach(v => { g += `<line x1="${x(v.x)}" x2="${x(v.x)}" y1="${T}" y2="${H - B}" stroke="${v.color}" stroke-dasharray="3 4" stroke-width="1.5"/><text x="${x(v.x) + 5}" y="${T + 12}" class="ax" fill="${v.color}" style="fill:${v.color}">${esc(v.label)}</text>`; });
    hlines.forEach(h => { g += `<line x1="${L}" x2="${W - R}" y1="${y(h.v)}" y2="${y(h.v)}" stroke="${h.color}" stroke-dasharray="4 4" stroke-width="1.5"/>
      <rect x="${W / 2 - 70}" y="${y(h.v) - 20}" width="140" height="16" rx="4" fill="#334155"/><text x="${W / 2}" y="${y(h.v) - 8}" text-anchor="middle" class="tag">${esc(h.label)}</text>`; });
    series.forEach(s => {
      if (!s.pts.length) return;
      const d = s.pts.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
      if (area && (!s.dash || s.fill)) g += `<path d="${d}L${x(s.pts[s.pts.length - 1][0])},${y(mn)}L${x(s.pts[0][0])},${y(mn)}Z" fill="${s.color}" opacity="${s.fill || 0.14}"/>`;
      g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.w || 2.5}" stroke-dasharray="${s.dash || ''}" stroke-linejoin="round"/>`;
      (s.dots || []).forEach(p => { g += `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="4" fill="${s.color}"><title>${esc(p[2] || '')}: ${fmt(p[1])} ${unit}</title></circle>`; });
    });
    return `<svg viewBox="0 0 ${W} ${H}" class="chart">${g}</svg>`;
  }

  const donut = (segs, label, sub) => {
    const tot = segs.reduce((a, s) => a + s.v, 0) || 1; let a0 = -Math.PI / 2, g = '';
    segs.forEach(s => { if (s.v <= 0) return; const a1 = a0 + 2 * Math.PI * s.v / tot - 0.0001, big = a1 - a0 > Math.PI ? 1 : 0;
      g += `<path d="M${60 + 50 * Math.cos(a0)},${60 + 50 * Math.sin(a0)} A50,50 0 ${big} 1 ${60 + 50 * Math.cos(a1)},${60 + 50 * Math.sin(a1)}" stroke="${s.c}" stroke-width="16" fill="none"><title>${esc(s.n)}: ${nf(100 * s.v / tot)} %</title></path>`; a0 = a1; });
    return `<svg viewBox="0 0 120 120" class="donut">${g}<text x="60" y="58" text-anchor="middle" class="dv">${esc(label)}</text><text x="60" y="76" text-anchor="middle" class="ds">${esc(sub || '')}</text></svg>`;
  };
  const ring = (pct, color, label, sub) => {
    const p = Math.max(0, Math.min(1, pct)), a = -Math.PI / 2 + 2 * Math.PI * p - 0.0001, big = p > 0.5 ? 1 : 0;
    return `<svg viewBox="0 0 120 120" class="donut"><circle cx="60" cy="60" r="50" stroke="var(--divider-color)" stroke-width="12" fill="none"/>
      ${p > 0 ? `<path d="M60,10 A50,50 0 ${big} 1 ${60 + 50 * Math.cos(a)},${60 + 50 * Math.sin(a)}" stroke="${color}" stroke-width="12" fill="none" stroke-linecap="round"/>` : ''}
      <text x="60" y="58" text-anchor="middle" class="dv">${esc(label)}</text><text x="60" y="76" text-anchor="middle" class="ds">${esc(sub || '')}</text></svg>`;
  };

  // ---------- Kortet ----------
  class EnergiAppCard extends HTMLElement {
    constructor() {
      super(); this.attachShadow({mode: 'open'});
      this._tab = (location.hash || '').replace('#', '') || 'live';
      this._hist = 'maaneder'; this._ugeOffset = 0; this._maaned = null; this._prisMode = 'koeb'; this._valgtMaaned = null;
      this._dage = null; this._idag = null; this._sol = null; this._last = 0; this._loading = false; this._dur = '120'; this._tsoc = 80; this._log = null; this._hh = null;
      this.shadowRoot.addEventListener('click', e => this._klik(e));
      this.shadowRoot.addEventListener('change', e => { const el = e.target;
        if (el.dataset.r) { const [i, k] = el.dataset.r.split('|'); const r = this._reglerUdkast()[Number(i)]; r[k] = k === 'soc' ? Number(el.value) : el.value; this._rDirty = true; this._last = 0; this._render(); return; }
        if (!el.dataset.set) return;
        const [dom, id] = el.dataset.set.split('|');
        if (dom === 'text') this._hass.callService('input_text', 'set_value', {entity_id: id, value: el.value.trim()});
        if (dom === 'time') this._hass.callService('input_datetime', 'set_datetime', {entity_id: id, time: el.value + ':00'}); });
    }
    setConfig(c) { this._cfg = c || {}; FOER_NOV = Number(this._cfg.startsaldo) || 0; FOER_DATO = this._cfg.startsaldo_dato || null; }
    getCardSize() { return 12; }
    getGridOptions() { return {columns: 'full', rows: 'auto'}; }
    set hass(h) {
      this._hass = h;
      const sd = h.states['input_datetime.solcelle_start_dato']?.state; if (/^\d{4}-\d\d-\d\d$/.test(sd || '')) START = sd;
      const tn = k => parseFloat(h.states['input_number.wattlas_' + k]?.state) || 0;
      T = {lav: tn('nettarif_lav'), hoej: tn('nettarif_hoej'), spids: tn('nettarif_spids'), afgift: tn('elafgift'), tillaeg: tn('tillaeg'), salg_net: tn('salg_nettarif'), salg_gebyr: tn('salg_gebyr')};
      if (this._planEl && this._tab === 'plan') this._planEl.hass = h;
      if (['INPUT', 'SELECT'].includes(this.shadowRoot.activeElement?.tagName)) return;
      if (!this._dage && !this._loading) this._hent();
      else if (!this._loading && !this._idagHenter && Date.now() - (this._idagT || 0) > 5 * 60000) this._hentIdag();
      const now = Date.now();
      if (now - this._last > 5000) { this._last = now; this._render(); }
    }
    // grafernes bredde i px, så teksten bliver læselig (svg skaleres ellers ned)
    w(kind) { const cw = this.shadowRoot.querySelector('.app')?.clientWidth || Math.min(this.clientWidth || 1200, 1560); // samme brudpunkter som @container app i CSS
      const v = kind === 'half' ? (cw < 800 ? cw - 64 : (cw - 40) / 2 - 40) : kind === 'main' ? (cw < 1100 ? cw - 64 : (cw - 40) * 2 / 3 - 40) : kind === 'side' ? (cw < 1100 ? cw - 64 : (cw - 40) / 3 - 40) : cw - 64;
      return Math.max(300, v); }
    st(id) { return this._hass?.states[id]; }
    prog(k) { const e = this.st('input_text.wattlas_solprognose_entitet')?.state || ''; return k === 'power_now' ? e : e.replace(/_power_now$/, '_' + k); }
    n(id) { const s = this.st(id); const v = s ? parseFloat(s.state) : NaN; return isNaN(v) ? null : v; }
    a(id, k) { return this.st(id)?.attributes?.[k]; }

    async _sql(q) {
      const r = await this._hass.callWS({type: 'call_service', domain: 'sql', service: 'query', service_data: {query: q}, return_response: true});
      return (r && r.response && r.response.result) || [];
    }
    async _hentIdag() {
      this._idagHenter = true;
      try { const m0 = new Date(); m0.setHours(0, 0, 0, 0);
        this._idag = await this._hass.callWS({type: 'recorder/statistics_during_period', start_time: m0.toISOString(),
          statistic_ids: ['sensor.emhass_solproduktion_samlet', 'sensor.emhass_m_load_w_totalpower'], period: '5minute', types: ['mean']});
      } catch (e) { /* prøver igen om 5 min */ }
      this._idagT = Date.now(); this._idagHenter = false; this._last = 0; this._render();
    }
    async _hent() {
      this._loading = true;
      try {
        this._dage = await this._sql(SQL_DAGE(START));
        const nu = new Date(), m0 = new Date(nu); m0.setHours(0, 0, 0, 0);
        const st = await this._hass.callWS({type: 'recorder/statistics_during_period', start_time: m0.toISOString(),
          statistic_ids: ['sensor.emhass_solproduktion_samlet', 'sensor.emhass_m_load_w_totalpower'], period: '5minute', types: ['mean']});
        this._idag = st; this._idagT = Date.now();
      } catch (e) { this._fejl = String(e?.message || e); this._dage = this._dage || []; }
      this._loading = false; this._last = 0; this._render();
      setTimeout(() => { this._dage = null; }, 10 * 60 * 1000); // genindlæs historik hvert 10. min.
    }

    // sparet kr. pr. dag (dagslog > startdata) + i dag live
    sparetDage() {
      const m = {...SEED};
      (this.a('sensor.energi_dagslog', 'dage') || []).forEach(r => { if (r && r.d && typeof r.sparet === 'number') m[r.d] = r.sparet; });
      const i = this.n('sensor.solcelle_sparet_i_dag'); if (i !== null) m[ymd(new Date())] = i;
      return m;
    }
    maal() { return Math.max(1, (this.n('input_number.solcelle_investering') || 0) / (15 * 365)); }

    _klik(e) {
      const t = e.target.closest('[data-a]'); if (!t) return;
      const a = t.dataset.a, v = t.dataset.v;
      if (a === 'tab') { this._tab = v; history.replaceState(null, '', '#' + v); }
      else if (a === 'hist') { this._hist = v; this._valgtMaaned = null; }
      else if (a === 'uge') this._ugeOffset += Number(v);
      else if (a === 'maaned') this._maaned = v;
      else if (a === 'pris') this._prisMode = v;
      else if (a === 'vmaaned') { this._valgtMaaned = v; this._hist = 'maaned'; }
      else if (a === 'info') { const ev = new Event('hass-more-info', {bubbles: true, composed: true}); ev.detail = {entityId: v}; this.dispatchEvent(ev); return; }
      else if (a === 'reload') { this._dage = null; this._hent(); return; }
      else if (a === 'script') { this._hass.callService('script', v, {}); return; }
      else if (a === 'dur') this._dur = v;
      else if (a === 'tsoc') this._tsoc = Number(v);
      else if (a === 'ts') { this._tilsidesaet(v); return; }
      else if (a === 'hhset') { const [k, d] = v.split('|'), lim = {reserve: [15, 80], slut_soc: [15, 100], max_net_kw: [0, Math.max(1, (this.n('input_number.wattlas_maks_netimport_w') || 50000) / 1000)], slid: [0, 1]}[k];
        this._hh[k] = Math.max(lim[0], Math.min(lim[1], Math.round((this._hh[k] + Number(d)) * 100) / 100)); }
      else if (a === 'hhfb') this._hh.forbruger = !this._hh.forbruger;
      else if (a === 'rny') { this._reglerUdkast().push({navn: 'Ny regel', aktiv: false, type: 'gem', dage: 'hverdage', fra: '16:00', til: '21:00', soc: 80}); }
      else if (a === 'rdel') { this._reglerUdkast().splice(Number(v), 1); }
      else if (a === 'rtog') { const r = this._reglerUdkast()[Number(v)]; r.aktiv = !r.aktiv; }
      else if (a === 'rgem') { this._hass.callWS({type: 'fire_event', event_type: 'wattlas_regler_gem', event_data: {regler: this._reglerUdkast()}}).then(() => { this._rDirty = false; this._last = 0; this._render(); }); return; }
      else if (a === 'rfortryd') { this._rUdkast = null; this._rDirty = false; }
      else if (a === 'hhrun') { this._hass.callService('script', 'wattlas_hvadhvis', {...this._hh}); this._hhKoert = true; return; }
      else if (a === 'hhapply') { if (!confirm('Brug disse indstillinger i den rigtige styring?')) return;
        [['reserve', 'wattlas_reserve'], ['slut_soc', 'wattlas_slut_soc'], ['max_net_kw', 'wattlas_max_net_kw'], ['slid', 'wattlas_slid']]
          .forEach(([k, id]) => this._hass.callService('input_number', 'set_value', {entity_id: 'input_number.' + id, value: this._hh[k]})); return; }
      else if (a === 'num') { const [id, d] = v.split('|'), s = this.st(id); if (!s) return;
        const x = Math.max(s.attributes.min, Math.min(s.attributes.max, Math.round((parseFloat(s.state) + Number(d)) * 100) / 100));
        this._hass.callService('input_number', 'set_value', {entity_id: id, value: x}); this._last = 0; return; }
      else if (a === 'tog') { const s = this.st(v); if (!s) return;
        if (v === 'input_boolean.wattlas_skygge' && !confirm(s.state === 'on' ? 'Slå skygge fra? Wattlas begynder at styre inverteren.' : 'Slå skygge til? Wattlas giver inverteren tilbage (selvforbrug) og viser derefter kun, hvad den ville gøre.')) return;
        if (v === 'input_boolean.emhass_styring_aktiv' && !confirm(s.state === 'on' ? 'Stop Wattlas-styringen? Batteriet går i selvforbrug med 15 % reserve.' : 'Start Wattlas-styringen? EMHASS overtager inverterens tidsprogrammer.')) return;
        this._hass.callService('input_boolean', 'toggle', {entity_id: v}); this._last = 0; return; }
      this._last = 0; this._html = null; this._render();
      if (a === 'tab') window.scrollTo({top: 0}); // kun ved faneskift: tilbage til toppen (HA's topbjælke dækker ellers)
    }

    _render() {
      if (!this._hass) return;
      const ALLE = {live: ['mdi:flash', 'Live'], styring: ['mdi:tune-variant', 'Styring'], regler: ['mdi:calendar-clock', 'Regler'], plan: ['mdi:head-question-outline', 'Planens logik'],
        overvaagning: ['mdi:shield-check-outline', 'Overvågning'], teknik: ['mdi:sine-wave', 'Teknik'], okonomi: ['mdi:piggy-bank', 'Økonomi'], historik: ['mdi:chart-areaspline', 'Historik'],
        elpris: ['mdi:currency-usd', 'Elpris'], sol: ['mdi:weather-sunny', 'Solprognose']};
      const valgte = (this._cfg?.tabs || ['live', 'okonomi', 'historik', 'elpris', 'sol']).filter(k => ALLE[k]);
      if (!valgte.includes(this._tab)) this._tab = valgte[0];
      const tabs = valgte.map(k => [k, ...ALLE[k]]);
      const andet = this._cfg?.link;
      let body = '';
      try {
        body = {live: () => this.live(), styring: () => this.styring(), regler: () => this.regler(), plan: () => '<div class="plan-host"></div>',
          overvaagning: () => this.overvaagning(), teknik: () => this.teknik(), okonomi: () => this.okonomi(), historik: () => this.historik(), elpris: () => this.elpris(),
          sol: () => this.solprognose()}[this._tab]?.() || this.live();
      } catch (e) { body = `<div class="card">Fejl i visningen: ${esc(e.message)}</div>`; console.error(e); }
      const offline = this.st('binary_sensor.wattlas_forbindelse')?.state !== 'on';
      const html = `<style>${CSS}</style><div class="app">
        <header><div class="brand"><img src="${LOGO}" alt=""><div><b>WATTLAS</b><span>${esc(this._cfg?.undertitel || 'Energi-intelligens')}</span></div>${andet ? `<a class="lnk swap" href="${esc(andet.url)}">${esc(andet.navn)} ›</a>` : ''}</div>
        <nav>${tabs.map(([k, i, n]) => `<button data-a="tab" data-v="${k}" class="${this._tab === k ? 'on' : ''}"><ha-icon icon="${i}"></ha-icon><span>${n}</span></button>`).join('')}</nav></header>
        ${offline ? `<div class="alert"><ha-icon icon="mdi:alert-circle"></ha-icon> Inverteren svarer ikke – tallene står stille.</div>` : ''}
        ${this.st('binary_sensor.wattlas_konfigureret')?.state !== 'on' ? `<div class="alert warn"><ha-icon icon="mdi:shield-lock"></ha-icon> Wattlas er ikke færdigindstillet – styringen er spærret. Mangler: ${esc((this.a('binary_sensor.wattlas_konfigureret', 'mangler') || ['binary_sensor.wattlas_konfigureret']).join(', '))}</div>` : ''}
        ${this._fejl ? `<div class="alert warn">Historik kunne ikke hentes: ${esc(this._fejl)} <button data-a="reload">Prøv igen</button></div>` : ''}
        <div class="page">${body}</div></div>`;
      if (html === this._html) return; // intet nyt at vise – lad siden være i fred
      this._html = html;
      const rul = this._rulleflade(), top = rul.scrollTop;
      this.style.minHeight = this.offsetHeight + 'px'; // højden må ikke falde sammen, mens indholdet skiftes
      this.shadowRoot.innerHTML = html;
      if (rul.scrollTop !== top) rul.scrollTop = top;
      requestAnimationFrame(() => { this.style.minHeight = ''; if (rul.scrollTop !== top && top <= rul.scrollHeight - rul.clientHeight) rul.scrollTop = top; });
      const host = this.shadowRoot.querySelector('.plan-host');
      if (host && !customElements.get('emhass-plan-card')) { host.textContent = 'Henter planens logik …'; setTimeout(() => { this._last = 0; this._render(); }, 500); }
      else if (host) { if (!this._planEl) this._planEl = document.createElement('emhass-plan-card'); try { this._planEl.setConfig({}); } catch (e) {}
        this._planEl.hass = this._hass; host.appendChild(this._planEl); }
    }

    // det element, siden ruller i (HA's visning eller selve dokumentet)
    _rulleflade() {
      for (let el = this.parentNode; el; el = el.parentNode || el.host) {
        if (el.nodeType === 1 && el.scrollHeight > el.clientHeight + 1 && /(auto|scroll)/.test(getComputedStyle(el).overflowY)) return el;
      }
      return document.scrollingElement || document.documentElement;
    }

    // ---------- komponenter ----------
    kpi(t, v, icon, color, {sub = '', bar = null, tab = null, info = null} = {}) {
      const act = tab ? `data-a="tab" data-v="${tab}"` : info ? `data-a="info" data-v="${info}"` : '';
      return `<div class="kpi ${act ? 'click' : ''}" ${act}><div class="kt"><div><div class="kv">${v}</div><div class="kl">${t}</div></div>
        <div class="ki" style="background:${color}22;color:${color}"><ha-icon icon="${icon}"></ha-icon></div></div>
        ${sub ? `<div class="ks">${sub}</div>` : ''}
        ${bar !== null ? `<div class="kb"><i style="width:${Math.max(2, Math.min(100, bar * 100))}%;background:${color}"></i></div>` : ''}</div>`;
    }
    card(title, inner, {icon = '', right = '', cls = ''} = {}) {
      return `<section class="card ${cls}"><div class="ch"><h3>${icon ? `<ha-icon icon="${icon}"></ha-icon>` : ''}${title}</h3><div class="cr">${right}</div></div>${inner}</section>`;
    }
    legend(items) { return `<div class="legend">${items.map(([n, c]) => `<span><i style="background:${c}"></i>${n}</span>`).join('')}</div>`; }
    seg(name, opts, cur) { return `<div class="seg">${opts.map(([v, l]) => `<button data-a="${name}" data-v="${v}" class="${cur === v ? 'on' : ''}">${l}</button>`).join('')}</div>`; }

    // ---------- LIVE ----------
    live() {
      const pv = Math.max(0, this.n('sensor.emhass_solproduktion_samlet') || 0), load = Math.max(0, this.n('sensor.emhass_m_load_w_totalpower') || 0);
      const grid = this.n('sensor.emhass_m_grid_out_total_power') || 0, bat = this.n('sensor.emhass_m_battery_output_w_power') || 0;
      const soc = this.n('sensor.emhass_m_battery_soc') || 0;
      const pvD = (this.n('sensor.wattlas_i_dag_produktion') || 0);
      const progn = pvD + (this.n(this.prog('energy_today_remaining')) || 0);
      const ind = this.n('sensor.wattlas_i_dag_koebt') || 0, ud = this.n('sensor.wattlas_i_dag_solgt') || 0;
      const lastD = this.n('sensor.wattlas_i_dag_forbrug') || 0;
      const ch = this.n('sensor.wattlas_i_dag_ladet') || 0, dis = this.n('sensor.wattlas_i_dag_afladet') || 0;
      const sparet = this.n('sensor.solcelle_sparet_i_dag'), maal = this.maal();
      // hvem forsyner hvem lige nu
      const lad = Math.max(0, -bat), afl = Math.max(0, bat);
      const solHus = Math.min(pv, load), solRest = pv - solHus, solBat = Math.min(solRest, lad), solNet = Math.max(0, solRest - solBat);
      const husRest = load - solHus, batHus = Math.min(afl, husRest), netHus = Math.max(0, husRest - batHus), netBat = Math.max(0, lad - solBat);
      const kw = w => w >= 1000 ? nf(w / 1000, 1) + ' kW' : nf(w) + ' W';
      const F = [
        ['M330,118 Q470,128 512,204', solHus, C.sol, 'Sol → hus', 478, 126],
        ['M330,118 L330,352', solBat, C.sol, 'Sol → batteri', 352, 300],
        ['M310,118 Q190,128 148,204', solNet, C.sol, 'Sol → elnet', 182, 126],
        ['M146,250 L494,250', netHus, C.net, 'Elnet → hus', 400, 240],
        ['M150,290 Q190,372 288,398', netBat, C.net, 'Elnet → batteri', 190, 370],
        ['M372,398 Q470,372 512,296', batHus, C.bat, 'Batteri → hus', 488, 331]];
      let flows = '', labels = '';
      F.forEach(([d, w, c, n, lx, ly], k) => {
        flows += `<path d="${d}" class="fb"/>`;
        if (w < 30) return;
        const sw = Math.min(9, 2.5 + w / 1400), dur = Math.max(0.9, 3.2 - w / 4000).toFixed(2);
        flows += `<path d="${d}" class="fa" stroke="${c}" stroke-width="${sw}" style="filter:drop-shadow(0 0 6px ${c})"/>`;
        for (let q = 0; q < 3; q++) flows += `<circle r="${Math.min(5.5, 2.5 + sw / 3)}" fill="#fff" opacity=".9"><animateMotion dur="${dur}s" begin="${(q * dur / 3).toFixed(2)}s" repeatCount="indefinite" path="${d}"/></circle>`;
        labels += `<g class="fl"><rect x="${lx - 40}" y="${ly - 12}" width="80" height="22" rx="11" fill="#0a1426" stroke="${c}" stroke-opacity=".6"/><text x="${lx}" y="${ly + 4}" text-anchor="middle" fill="${c}">${kw(w)}</text></g>`;
      });
      const node = (x, y, c, icon, val, lab, sub, extra = '') => `<g>
        <circle cx="${x}" cy="${y}" r="58" fill="none" stroke="${c}" stroke-opacity=".18" stroke-width="1" stroke-dasharray="3 6" class="spin"/>
        <circle cx="${x}" cy="${y}" r="48" fill="url(#nodebg)" stroke="${c}" stroke-width="2.5" style="filter:drop-shadow(0 0 10px ${c}88)"/>${extra}
        <foreignObject x="${x - 15}" y="${y - 34}" width="30" height="30"><ha-icon icon="${icon}" style="color:${c};--mdc-icon-size:28px"></ha-icon></foreignObject>
        <text x="${x}" y="${y + 14}" text-anchor="middle" class="nv" fill="#fff">${val}</text>
        <text x="${x}" y="${y + 30}" text-anchor="middle" class="nk" fill="${c}">${lab}</text>
        <text x="${x}" y="${y + 74}" text-anchor="middle" class="ns">${sub}</text></g>`;
      const a = -Math.PI / 2 + 2 * Math.PI * Math.min(1, soc / 100) - 0.001;
      const socArc = `<path d="M330,350 A50,50 0 ${soc > 50 ? 1 : 0} 1 ${330 + 50 * Math.cos(a)},${400 + 50 * Math.sin(a)}" fill="none" stroke="${C.bat}" stroke-width="5" stroke-linecap="round"/>`;
      const batTxt = bat > 30 ? 'aflader' : bat < -30 ? 'lader' : 'hviler';
      // detaljer som på Wattlas Styring: priser, faser, strenge, batteriets tilstand
      const koeb = this.n('sensor.emhass_ui_koebspris'), salg = this.n('sensor.emhass_ui_salgspris');
      const husK = this.n('sensor.hus_strompris_kontant'), husS = this.n('sensor.hus_strompris_nu'), tjener = this.a('sensor.hus_strompris_kontant', 'tjener_pr_kwh');
      const ph = [1, 2, 3].map(i => this.n('sensor.emhass_m_external_ct_w_l' + i));
      const anl = (this._cfg?.pv_anlaeg || []).slice(0, 2).map(p => [p.navn, this.n(p.entitet)]);
      const bV = this.n('sensor.emhass_m_battery_voltage'), bT = this.n('sensor.emhass_m_battery_temperature'), bK = this.n('sensor.emhass_ui_energi_til_raadighed');
      const invT = this.n('sensor.emhass_m_inverter_temperature'), batPris = this.n('sensor.batteri_brugspris');
      let eta = '';
      if (bat < -100 && soc < 100) { const m = ((100 - soc) / 100 * (this.n('input_number.wattlas_batteri_kwh') || 0)) / (lad / 1000 * 0.95) * 60, d = new Date(Date.now() + m * 6e4);
        eta = `fuld kl. ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} (${m >= 60 ? Math.floor(m / 60) + ' t ' : ''}${Math.round(m % 60)} min)`; }
      else if (bat > 100 && bK) { const m = bK / (afl / 1000 / 0.95) * 60, d = new Date(Date.now() + m * 6e4);
        eta = `reserve nås kl. ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; }
      const tx = (x, y, s, c, cls = 'ex', anc = 'middle') => `<text x="${x}" y="${y}" text-anchor="${anc}" class="${cls}" fill="${c}">${s}</text>`;
      const extras =
        tx(100, 178, koeb !== null ? `${nf(koeb, 2)} kr/kWh` : '', C.net, 'exb') + tx(100, 192, salg !== null ? `salg ${nf(salg, 2)} kr` : '', C.net) +
        tx(100, 342, ph.every(v => v !== null) ? ph.map((v, i) => `L${i + 1} ${nf(v / 1000, 1)}`).join(' · ') + ' kW' : '', 'var(--secondary-text-color)') +
        tx(560, 178, tjener != null ? `tjener ${nf(tjener, 2)} kr/kWh` : husK !== null ? `${nf(husK, 2)} kr/kWh` : '', C.hus, 'exb') +
        tx(560, 192, tjener == null && husS !== null ? `med slid ${nf(husS, 2)}` : '', C.hus) +
        anl.map(([n, v], k) => tx(398, 52 + 16 * k, v !== null ? `${esc(n)}  ${kw(Math.max(0, v))}` : '', C.sol, 'ex', 'start')).join('') +
        tx(404, 410, bK !== null ? `${nf(bK, 1)} kWh over reserven` : '', C.bat, 'exb', 'start') +
        tx(404, 426, [bV !== null && !['Huawei', 'Growatt', 'SolaX', 'Sofar', 'Solis'].includes(this.st('sensor.emhass_maalekilde')?.state) ? nf(bV, 1) + ' V' : '',  /* Huawei: kanalens beregningsspænding, ikke batteriets */ bT !== null ? nf(bT, 1) + ' °C' : '', batPris !== null ? nf(batPris, 2) + ' kr/kWh' : ''].filter(Boolean).join(' · '), 'var(--secondary-text-color)', 'ex', 'start') +
        tx(404, 442, eta, C.bat, 'ex', 'start') +
        tx(330, 290, invT !== null ? `inverter ${nf(invT, 0)} °C` : '', 'var(--secondary-text-color)');
      const svg = `<svg viewBox="0 0 660 490" class="flow"><defs><radialGradient id="nodebg"><stop offset="0" stop-color="#16294a"/><stop offset="1" stop-color="#0a1426"/></radialGradient></defs>
        ${flows}
        <circle cx="330" cy="250" r="26" fill="#0a1426" stroke="${C.cyan}" stroke-width="1.5" style="filter:drop-shadow(0 0 8px ${C.cyan})"/>
        <image href="${LOGO}" x="308" y="228" width="44" height="44"/>
        ${node(330, 70, C.sol, 'mdi:white-balance-sunny', kw(pv), 'SOL', `${nf(pvD, 1)} kWh i dag · prognose ${nf(progn, 0)} kWh`)}
        ${node(100, 250, C.net, 'mdi:transmission-tower', kw(Math.abs(grid)), grid < -30 ? 'SÆLGER' : 'KØBER', `${nf(ind, 1)} kWh købt · ${nf(ud, 1)} solgt`)}
        ${node(560, 250, C.hus, 'mdi:home-lightning-bolt', kw(load), 'HUS', `${nf(lastD, 1)} kWh i dag`)}
        ${node(330, 400, C.bat, 'mdi:battery-charging-high', nf(soc) + ' %', 'BATTERI', `${batTxt} ${kw(Math.abs(bat))} · ${nf(ch, 1)} ladet / ${nf(dis, 1)} afladet`, socArc)}
        ${extras}${labels}</svg>`;
      const fraNet = Math.min(lastD, Math.max(0, ind - ch)), fraBat = Math.max(0, Math.min(dis, lastD - fraNet)), fraSol = Math.max(0, lastD - fraNet - fraBat);
      const tot = lastD || 1, autark = load > 0 ? 100 * (solHus + batHus) / load : 0;
      const priser = this.priserIdag(), nuP = priser.find(p => p.h === new Date().getHours());
      const billig = priser.length ? priser.reduce((x, y) => y.buy < x.buy ? y : x) : null, dyr = priser.length ? priser.reduce((x, y) => y.buy > x.buy ? y : x) : null;
      const gns = priser.length ? priser.reduce((x, y) => x + y.buy, 0) / priser.length : null;
      const ser = this._idag || {};
      const pts = k => { const m = {}; (ser[k] || []).forEach(r => { const d = new Date(r.start), q = d.getHours() + Math.floor(d.getMinutes() / 15) / 4; (m[q] = m[q] || []).push((r.mean || 0) / 1000); });
        return Object.keys(m).map(Number).sort((x, y) => x - y).map(q => [q + 0.125, m[q].reduce((x, y) => x + y, 0) / m[q].length]); };
      const dagChart = lines({series: [{pts: pts('sensor.emhass_solproduktion_samlet'), color: C.sol}, {pts: pts('sensor.emhass_m_load_w_totalpower'), color: C.hus}],
        xmin: 0, xmax: 24, xticks: [0, 3, 6, 9, 12, 15, 18, 21, 24].map(h => [h, String(h).padStart(2, '0')]), unit: 'kW', fmt: v => nf(v, 1), height: 200, W: this.w('side')});
      const ov = this.st('binary_sensor.wattlas_tilsidesaettelse_aktiv')?.state === 'on';
      const flowList = F.filter(f => f[1] >= 30).map(f => `<li><i style="background:${f[2]}"></i>${f[3]}<b>${kw(f[1])}</b></li>`).join('') || '<li>Ingen strøm flyder lige nu</li>';
      return `${ov ? this.ovBanner() : ''}<div class="grid g21">
        ${this.card('Energi lige nu', svg + `<div class="flowfoot"><ul class="fl2">${flowList}</ul><div class="aut"><b>${nf(autark)} %</b><span>autarki lige nu</span></div></div>`,
          {icon: 'mdi:flash', right: `<span class="pill ${this.st('binary_sensor.wattlas_forbindelse')?.state === 'on' ? 'ok' : 'err'}">● Inverter ${this.st('binary_sensor.wattlas_forbindelse')?.state === 'on' ? 'online' : 'offline'}</span>`})}
        <div class="stack">
          <div class="grid g2s">
            ${this.card('Sparet i dag', `<div class="center">${ring(sparet !== null ? sparet / (maal * 2) : 0, sparet !== null && sparet >= maal ? C.ok : C.warn, sparet !== null ? kr(sparet) : '–', `mål ${kr(maal)}`)}</div>`, {icon: 'mdi:piggy-bank-outline', right: `<button class="lnk" data-a="tab" data-v="okonomi">Økonomi ›</button>`})}
            ${this.card('Strømbalance i dag', `<div class="center">${donut([{v: fraSol, c: C.sol, n: 'Sol'}, {v: fraNet, c: C.net, n: 'Elnet'}, {v: fraBat, c: C.bat, n: 'Batteri'}], nf(100 * fraSol / tot) + ' %', 'fra solen')}</div>
              ${this.legend([[`Sol ${nf(100 * fraSol / tot)} %`, C.sol], [`Elnet ${nf(100 * fraNet / tot)} %`, C.net], [`Batteri ${nf(100 * fraBat / tot)} %`, C.bat]])}`, {icon: 'mdi:chart-donut'})}
          </div>
          ${this.card('Strømpris i dag', `<div class="prices">
              <div data-a="tab" data-v="elpris" class="click"><span>Billigste</span><b style="color:${C.ok}">${billig ? nf(billig.buy, 2) : '–'}</b><small>kl. ${billig ? String(billig.h).padStart(2, '0') : '–'}</small></div>
              <div data-a="tab" data-v="elpris" class="click"><span>Nu</span><b>${nuP ? nf(nuP.buy, 2) : '–'}</b><small>kr./kWh</small></div>
              <div data-a="tab" data-v="elpris" class="click"><span>Gennemsnit</span><b style="color:${C.warn}">${gns !== null ? nf(gns, 2) : '–'}</b><small>inkl. tariffer</small></div>
              <div data-a="tab" data-v="elpris" class="click"><span>Dyreste</span><b style="color:${C.err}">${dyr ? nf(dyr.buy, 2) : '–'}</b><small>kl. ${dyr ? String(dyr.h).padStart(2, '0') : '–'}</small></div></div>`, {icon: 'mdi:currency-usd'})}
          ${this.card('Fremad', `<div class="set"><div><b>Batteriet</b><span>${esc(this.st('sensor.wattlas_batteri_raekker_til')?.attributes?.tekst || 'Ingen gyldig plan')}</span></div></div>
              <div class="set"><div><b>Billigste time</b><span>${(() => { const b = this.st('sensor.wattlas_billigste_time'); const d = b && new Date(b.state);
                return d && !isNaN(d) ? `kl. ${String(d.getHours()).padStart(2, '0')}–${String((d.getHours() + 1) % 24).padStart(2, '0')}${d.getDate() !== new Date().getDate() ? ' i morgen' : ''} · ${nf(b.attributes.pris, 2)} kr./kWh – til opvasker, vaskemaskine o.l.` : '–'; })()}</span></div></div>`, {icon: 'mdi:battery-clock'})}
          ${this.card('I dag time for time', dagChart + this.legend([['Produktion', C.sol], ['Husforbrug', C.hus]]), {icon: 'mdi:chart-line'})}
        </div></div>`;
    }

    planKr(pre, slid) {
      const m = new Map(), put = (id, attr, key, f) => (this.a(id, attr) || []).forEach(r => { const tt = new Date(r.date).getTime(), x = parseFloat(r[key.startsWith(pre) ? key : pre + key]); if (isNaN(x)) return; const o = m.get(tt) || {t: tt}; o[f] = x; m.set(tt, o); });
      put(`sensor.${pre}p_batt_forecast`, 'battery_scheduled_power', 'p_batt_forecast', 'b'); put(`sensor.${pre}p_grid_forecast`, 'forecasts', 'p_grid_forecast', 'g');
      put(`sensor.${pre}soc_batt_forecast`, 'battery_scheduled_soc', 'soc_batt_forecast', 'soc'); put(`sensor.${pre}unit_load_cost`, 'unit_load_cost_forecasts', 'unit_load_cost', 'buy');
      put(`sensor.${pre}unit_prod_price`, 'unit_prod_price_forecasts', 'unit_prod_price', 'sell'); put(`sensor.${pre}p_deferrable0`, 'deferrables_schedule', `${pre}p_deferrable0`, 'fb');
      const S = [...m.values()].filter(s => s.b !== undefined).sort((x, y) => x.t - y.t); if (!S.length) return null;
      const k = w => w / 2000, r = {S, kr: 0, imp: 0, cyk: 0, fbT: [], socMin: 100, socSlut: S[S.length - 1].soc};
      S.forEach(s => { const g = s.g || 0, b = s.b || 0; r.kr += (g > 0 ? k(g) * (s.buy || 0) : -k(-g) * (s.sell || 0)) + Math.max(0, k(b)) * slid; r.imp += Math.max(0, k(g));
        r.cyk += Math.max(0, k(b)); r.socMin = Math.min(r.socMin, s.soc ?? 100); if ((s.fb || 0) > 50) r.fbT.push(s.t); });
      return r;
    }
    prisStribe() {
      const pr = [...this.priserIdag().map(p => ({...p, d: 0})), ...this.priserIdag('raw_tomorrow').map(p => ({...p, d: 1}))];
      if (!pr.length) return '';
      const nu = new Date().getHours(), sorted = pr.map(p => p.buy).sort((x, y) => x - y), lo = sorted[Math.floor(pr.length / 3)], hi = sorted[Math.floor(2 * pr.length / 3)];
      const hl = pr.findIndex(p => p.d === 0 && p.h === nu);
      return bars({labels: pr.map(p => (p.d ? '' : '') + String(p.h).padStart(2, '0')), series: [{name: 'Købspris', values: pr.map(p => p.buy), color: v => v <= lo ? C.lav : v <= hi ? C.hoej : C.spids}],
        unit: 'kr./kWh', fmt: v => nf(v, 2), highlight: hl, height: 170, W: this.w('full'), every: 2})
        + `<div class="legend"><span><i style="background:${C.lav}"></i>billigste tredjedel</span><span><i style="background:${C.hoej}"></i>mellem</span><span><i style="background:${C.spids}"></i>dyreste</span>${pr.some(p => p.d) ? '<span>· i morgen fra midten</span>' : '<span>· morgendagens priser kommer ca. kl. 13</span>'}</div>`;
    }
    hvadHvis() {
      const v = id => parseFloat(this.st(id)?.state);
      if (!this._hh) this._hh = {reserve: v('input_number.wattlas_reserve') || 15, slut_soc: v('input_number.wattlas_slut_soc') || 30,
        max_net_kw: v('input_number.wattlas_max_net_kw') || (v('input_number.wattlas_maks_netimport_w') || 0) / 1000, slid: v('input_number.wattlas_slid') ?? 0.25, forbruger: false};
      const H = this._hh, status = (this.st('input_text.wattlas_hvadhvis_status')?.state || '').replace(/^(unknown|unavailable)$/, ''), koerer = this.st('script.wattlas_hvadhvis')?.state === 'on' || status.startsWith('beregner');
      const base = this.planKr('', v('input_number.wattlas_slid') || 0.25), alt = this.planKr('hh_', H.slid);
      const frisk = alt && status.startsWith('ok') && this._hhKoert;
      const row = (k, t, u, step, dec) => `<div class="set"><div><b>${t}</b></div><div class="stp"><button data-a="hhset" data-v="${k}|-${step}">−</button><em>${k === 'max_net_kw' && !H[k] ? 'ingen grænse' : nf(H[k], dec) + ' ' + u}</em><button data-a="hhset" data-v="${k}|${step}">+</button></div></div>`;
      let res = `<p class="note">Vælg ændringer og tryk "Beregn". EMHASS laver en ekstra plan ved siden af den rigtige – styringen ændres ikke.</p>`;
      if (koerer) res = `<div class="loading">Beregner alternativ plan …</div>`;
      else if (frisk && base) {
        const d = alt.kr - base.kr, col = d <= 0 ? C.ok : C.err;
        const t0 = base.S[0].t, t1 = base.S[base.S.length - 1].t;
        const ch = lines({series: [{pts: base.S.map(s => [s.t, s.soc]), color: C.cyan}, {pts: alt.S.map(s => [s.t, s.soc]), color: C.blue, dash: '6 4'}], xmin: t0, xmax: t1,
          xticks: [0, 0.25, 0.5, 0.75, 1].map(f => { const tt = t0 + (t1 - t0) * f, dd = new Date(tt); return [tt, String(dd.getHours()).padStart(2, '0') + ':00']; }), unit: '%', fmt: x => nf(x), height: 200, W: this.w('half'), area: false});
        res = `<div class="cmp"><div><span>Nuværende plan</span><b>${kr(base.kr, 0)}</b></div><div><span>Hvad-hvis</span><b>${kr(alt.kr, 0)}</b></div>
          <div style="border-color:${col}"><span>Forskel</span><b style="color:${col}">${d > 0 ? '+' : ''}${kr(d, 0)}</b></div></div>
          <table class="tbl"><tbody><tr><td>Køb fra elnettet</td><td>${nf(base.imp, 1)} kWh</td><td>${nf(alt.imp, 1)} kWh</td></tr>
          <tr><td>Batteri afladet</td><td>${nf(base.cyk, 1)} kWh</td><td>${nf(alt.cyk, 1)} kWh</td></tr>
          <tr><td>Laveste batteriniveau</td><td>${nf(base.socMin)} %</td><td>${nf(alt.socMin)} %</td></tr>
          ${H.forbruger ? `<tr><td>Forbruger kører</td><td>–</td><td>${alt.fbT.length ? alt.fbT.map(tt => { const dd = new Date(tt); return String(dd.getHours()).padStart(2, '0') + ':' + String(dd.getMinutes()).padStart(2, '0'); }).join(', ') : 'ikke planlagt'}</td></tr>` : ''}</tbody></table>
          ${ch}${this.legend([['Batteriniveau nu', C.cyan], ['Hvad-hvis', C.blue]])}
          <p class="note">Regning for hele planens horisont: køb − salg + slid. ${d < -1 ? 'Ændringen sparer penge.' : d > 1 ? 'Ændringen koster penge – til gengæld får du det, du bad om (fx mere reserve).' : 'Næsten ingen forskel.'}</p>
          <button class="act" data-a="hhapply">Brug disse indstillinger</button>`;
      }
      return this.card('Hvad-hvis', `<div class="g2i"><div>${row('reserve', 'Reserve', '%', 5, 0)}${row('slut_soc', 'Batteri ved slut', '%', 5, 0)}${row('max_net_kw', 'Maks. fra elnettet', 'kW', 0.5, 1)}${row('slid', 'Batterislid', 'kr.', 0.05, 2)}
          <div class="set"><div><b>Med fleksibel forbruger</b><span>${esc((this.st('input_text.wattlas_forbruger1_navn')?.state || '').replace(/^unknown$/, '') || 'Forbruger 1')} · ${nf(v('input_number.wattlas_forbruger1_effekt'))} W i ${nf(v('input_number.wattlas_forbruger1_timer'), 1)} t</span></div><button class="sw ${H.forbruger ? 'on' : ''}" data-a="hhfb"><i></i></button></div>
          <button class="act" data-a="hhrun" ${koerer ? 'disabled' : ''}>${koerer ? 'Beregner …' : 'Beregn'}</button></div><div>${res}</div></div>`, {icon: 'mdi:flask-outline', right: `<span class="muted">${esc(status)}</span>`});
    }
    forbruger() {
      const v = id => { const s = this.st(id)?.state; return ['unknown', 'unavailable'].includes(s) ? '' : s; }, on = v('input_boolean.wattlas_forbruger1_aktiv') === 'on', ent = v('input_text.wattlas_forbruger1_entitet') || '';
      const gyldig = /^(switch|light|input_boolean)\.[a-z0-9_]+$/.test(ent), es = gyldig ? this.st(ent) : null;
      const plan = (this.a('sensor.p_deferrable0', 'deferrables_schedule') || []).filter(r => parseFloat(r.p_deferrable0) > 50).map(r => new Date(r.date));
      const kl = d => String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      const tid = (v('input_datetime.wattlas_forbruger1_faerdig') || '07:00:00').slice(0, 5);
      return this.card('Fleksibel forbruger', `<p class="note" style="margin:0 0 8px">Wattlas lægger fx varmtvandsbeholder, pool eller elbil i de bedste timer (sol og pris). EMHASS planlægger kørslen sammen med batteriet, og en kontakt i HA tændes og slukkes efter planen. Uden frisk plan er kontakten slukket.</p>
        <div class="set"><div><b>Navn</b></div><input class="inp" data-set="text|input_text.wattlas_forbruger1_navn" value="${esc(v('input_text.wattlas_forbruger1_navn') || '')}" placeholder="fx Varmtvandsbeholder"></div>
        <div class="set"><div><b>Kontakt</b><span>${gyldig ? (es ? `nu: ${es.state}` : '<b style="color:#fb7185">findes ikke</b>') : 'switch.…, light.… eller input_boolean.…'}</span></div><input class="inp" data-set="text|input_text.wattlas_forbruger1_entitet" value="${esc(ent)}" placeholder="switch.varmtvand"></div>
        ${'' /* effekt og timer */}<div class="set"><div><b>Effekt</b><span>det, den bruger, når den kører (typeskilt), fx varmtvand 3000 W. Planen regner med præcis den effekt. Under 100 W planlægges den ikke</span></div><div class="stp"><button data-a="num" data-v="input_number.wattlas_forbruger1_effekt|-100">−</button><em>${nf(parseFloat(v('input_number.wattlas_forbruger1_effekt')))} W</em><button data-a="num" data-v="input_number.wattlas_forbruger1_effekt|100">+</button></div></div>
        <div class="set"><div><b>Timer pr. døgn</b><span>inden færdig-tidspunktet · kørt ${nf(parseFloat(v('input_number.wattlas_forbruger1_koert')), 1)} t i denne periode</span></div><div class="stp"><button data-a="num" data-v="input_number.wattlas_forbruger1_timer|-0.5">−</button><em>${nf(parseFloat(v('input_number.wattlas_forbruger1_timer')), 1)} t</em><button data-a="num" data-v="input_number.wattlas_forbruger1_timer|0.5">+</button></div></div>
        <div class="set"><div><b>Skal være færdig kl.</b><span>ny periode starter her</span></div><input class="inp" type="time" data-set="time|input_datetime.wattlas_forbruger1_faerdig" value="${tid}"></div>
        <div class="set"><div><b>Wattlas styrer forbrugeren</b><span>${on ? (plan.length ? 'planlagt: ' + plan.map(kl).join(', ') : 'ingen kørsel i planen lige nu') : 'slået fra – prøv den i hvad-hvis først'}</span></div><button class="sw ${on ? 'on' : ''}" data-a="tog" data-v="input_boolean.wattlas_forbruger1_aktiv" ${gyldig && es ? '' : 'disabled'}><i></i></button></div>`, {icon: 'mdi:power-socket-eu'});
    }

    // ---------- REGLER (tidsstyrede begrænsninger) ----------
    _reglerUdkast() { if (!this._rUdkast) this._rUdkast = JSON.parse(JSON.stringify(this.a('sensor.wattlas_regler', 'regler') || [])); return this._rUdkast; }
    regler() {
      const R = this._reglerUdkast(), aktiv = this.st('sensor.wattlas_aktiv_regel'), ov = this.st('binary_sensor.wattlas_tilsidesaettelse_aktiv')?.state === 'on';
      const TYPER = [['gem', 'Gem batteriet (ingen afladning)'], ['ingen_netladning', 'Ingen netopladning'], ['lad', 'Lad fra elnettet til …'], ['brug', 'Brug batteriet til huset'], ['solsalg_stop', 'Stop solsalg']];
      const DAGE = [['alle', 'Alle dage'], ['hverdage', 'Hverdage (arbejdsdage)'], ['fridage', 'Fridage/helligdage'], ['weekend', 'Weekend']];
      const sel = (i, k, opts, val) => `<select class="inp" data-r="${i}|${k}">${opts.map(([v, l]) => `<option value="${v}" ${v === val ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
      const rows = R.map((r, i) => `<div class="regel ${r.aktiv ? 'on' : ''}">
          <button class="sw ${r.aktiv ? 'on' : ''}" data-a="rtog" data-v="${i}"><i></i></button>
          <input class="inp nm" data-r="${i}|navn" value="${esc(r.navn || '')}">
          ${sel(i, 'type', TYPER, r.type)}${sel(i, 'dage', DAGE, r.dage)}
          <span class="muted">fra</span><input class="inp tm" type="time" data-r="${i}|fra" value="${esc(r.fra)}"><span class="muted">til</span><input class="inp tm" type="time" data-r="${i}|til" value="${esc(r.til)}">
          ${r.type === 'lad' ? `<input class="inp tm" type="number" min="20" max="100" step="5" data-r="${i}|soc" value="${r.soc || 80}"><span class="muted">%</span>` : ''}
          <button class="lnk del" data-a="rdel" data-v="${i}">Slet</button></div>`).join('') || '<p class="note">Ingen regler endnu.</p>';
      const nu = aktiv && aktiv.state !== 'ingen' ? `<div class="ovb" style="border-color:${C.cyan};background:rgba(34,211,238,.1)"><ha-icon icon="mdi:calendar-check" style="color:${C.cyan}"></ha-icon><div><b>Regel aktiv nu: ${esc(aktiv.attributes.navn || aktiv.state)}</b><span>${ov ? 'En manuel tilsidesættelse har forrang lige nu.' : 'Styringen følger reglen i dette tidsrum i stedet for planen.'}</span></div></div>` : '';
      return nu + this.card('Regler', `<p class="note" style="margin:0 0 12px">Faste regler for bestemte tidsrum, fx "hverdage 16–21: gem batteriet". Rækkefølge: manuel tilsidesættelse → første aktive regel → planen.
          Reglerne ændrer kun hvad styringen udfører – EMHASS kender dem ikke, så planen kan vise noget andet i de tidsrum. Sikkerhedsgrænserne gælder stadig.</p>
          <div class="regler">${rows}</div>
          <div class="toolbar" style="margin-top:12px"><button class="act" data-a="rny">+ Ny regel</button>
          ${this._rDirty ? `<button class="act" data-a="rgem">Gem regler</button><button class="lnk" data-a="rfortryd">Fortryd</button><span class="muted">Ikke gemt endnu</span>` : '<span class="muted">Alt er gemt</span>'}</div>`,
        {icon: 'mdi:calendar-clock'}) + this.card('Elpris i dag og i morgen', this.prisStribe(), {icon: 'mdi:currency-usd'});
    }

    // ---------- OVERVÅGNING ----------
    overvaagning() {
      const s = id => this.st(id), on = id => s(id)?.state === 'on';
      const ALARM = [['planfejl', 'Mangler aktuel plan'], ['datafejl', 'Mangler friske målinger'], ['styrekanalfejl', 'Styrekanal til inverteren'], ['inverterfejl', 'Inverterstatus'],
        ['netbelastning', 'Høj netbelastning'], ['temperatur', 'Batteritemperatur'], ['lav_soc', 'Batteri under reserve'], ['indstillingsfejl', 'Periode følger ikke planen'],
        ['lader_ikke', 'Netopladning uden ladeeffekt'], ['soc_afvigelse', 'SOC-afvigelse']];
      const al = ALARM.map(([k, n]) => { const e = s('binary_sensor.emhass_ui_' + k), a = e?.state === 'on';
        return `<li class="${a ? 'bad' : ''}"><ha-icon icon="${a ? 'mdi:alert-circle' : 'mdi:check-circle'}" style="color:${a ? C.err : C.ok}"></ha-icon><div><b>${n}</b>${a ? `<span>${esc(e.attributes.forklaring || '')}</span>` : ''}</div></li>`; }).join('');
      const nAl = ALARM.filter(([k]) => on('binary_sensor.emhass_ui_' + k)).length;
      const chip = (ok, t) => `<span class="pill ${ok ? 'ok' : 'err'}">● ${t}</span>`;
      const forb = `<div class="chips">${chip(['Deye', 'Solarman', 'SunMate', 'Huawei', 'Growatt', 'ESPHome', 'Sonnen', 'SolaX', 'Sofar', 'Solis', 'SPF'].includes(s('sensor.emhass_maalekilde')?.state), 'Måling: ' + (s('sensor.emhass_maalekilde')?.state || '–'))}${chip(on('binary_sensor.emhass_ui_data_frisk'), 'Målekontrol')}
        ${chip(on('binary_sensor.emhass_styrekanal_ok'), 'Inverterstyring')}${chip(['Frisk', 'Reserve'].includes(s('sensor.emhass_planvalg')?.state), 'Plan: ' + (s('sensor.emhass_planvalg')?.state || '–'))}
        ${chip(s('sensor.optim_status')?.state === 'Optimal', 'EMHASS: ' + (s('sensor.optim_status')?.state || '–'))}${chip(on('binary_sensor.wattlas_forbindelse'), 'Inverterforbindelse')}
        ${chip(on('input_boolean.emhass_har_overtaget'), 'Har overtaget')}${chip(on('input_boolean.emhass_opstart_klar'), 'Opstart klar')}</div>`;
      const tog = (id, t, d) => `<div class="set"><div><b>${t}</b><span>${d}</span></div><button class="sw ${on(id) ? 'on' : ''}" data-a="tog" data-v="${id}"><i></i></button></div>`;
      const knap = (script, t) => `<button class="act" data-a="script" data-v="${script}">${t}</button>`;
      const per = `<table class="tbl"><tbody>
        <tr><td>Drift</td><td>${esc(s('sensor.emhass_ui_drift')?.state || '–')}</td></tr>
        <tr><td>Aktiv Deye-periode</td><td>${esc(s('sensor.emhass_ui_aktiv_periode')?.state || '–')} · effekt ${esc(s('sensor.emhass_ui_periode_effekt')?.state || '–')} W · SOC ${esc(s('sensor.emhass_ui_periode_soc')?.state || '–')} %</td></tr>
        <tr><td>Fasestrøm (estimat)</td><td>${[1, 2, 3].map(i => esc(s('sensor.emhass_ui_fase_' + i)?.state || '–')).join(' · ')} A</td></tr>
        <tr><td>Afladegrænse</td><td>${nf(this.n('sensor.emhass_ui_afladegraense_w'))} W</td></tr>
        <tr><td>Netopladning</td><td>${esc(s('switch.wattlas_netladning')?.state || '–')} · ${esc(s('number.wattlas_netladestroem')?.state || '–')} A</td></tr>
        <tr><td>Seneste diagnose</td><td>${esc(s('sensor.emhass_diagnose_seneste')?.state || '–')}</td></tr></tbody></table>`;
      return `<div class="grid g2">${this.card(`Advarsler · ${nAl ? nAl + ' aktive' : 'alt OK'}`, `<ul class="alarm">${al}</ul>`, {icon: 'mdi:shield-alert-outline'})}
        <div class="stack">${this.card('Forbindelser og plan', forb, {icon: 'mdi:lan-connect'})}
        ${this.card('Beskeder til telefonen', tog('input_boolean.emhass_ui_push', 'Push til mobilen', 'Advarsler sendes som push-besked til mobilen') + tog('input_boolean.emhass_ui_recovery', 'Besked når det er normalt igen', '') +
          `<div class="set"><div><b>Send også til</b><span>notify.mobile_app_… eller dit eget script.…</span></div><input class="inp" data-set="text|input_text.wattlas_besked_handling" value="${esc((s('input_text.wattlas_besked_handling')?.state || '').replace(/^(unknown|unavailable)$/, ''))}" placeholder="notify.mobile_app_din_telefon"></div>` +
          `<p class="note">Seneste: ${esc((s('input_text.emhass_ui_seneste_besked')?.state || '').replace(/^(unknown|unavailable)$/, '') || 'ingen endnu')}</p><div class="toolbar">${knap('emhass_ui_test_besked', 'Send testbesked')}${knap('emhass_diagnose_log', 'Gem diagnose nu')}${knap('emhass_test_helios', 'Beregn ny plan nu')}</div>`, {icon: 'mdi:cellphone-message'})}
        ${this.card('Teknik i styringen', per, {icon: 'mdi:cog-outline'})}</div></div>`;
    }

    // ---------- TEKNIK (til nørden og elektrikeren) ----------
    teknik() {
      const d = (n, pre = this._cfg?.inverter_prefix || 'min_inverter_') => { for (const dom of ['sensor', 'number', 'select', 'switch', 'binary_sensor']) { const e = this.st(`${dom}.${pre}${n}`); if (e) return e; } return null; };
      const val = (n, dec = 1, pre) => { const e = d(n, pre); if (!e) return '–'; const x = parseFloat(e.state); const u = e.attributes.unit_of_measurement || '';
        return isNaN(x) ? esc(e.state) : `${nf(x, Math.abs(x) >= 100 ? 0 : dec)}<small> ${esc(u)}</small>`; };
      const vok = n => { const x = parseFloat(d(n)?.state); return isNaN(x) ? '' : x < 207 || x > 253 ? 'bad' : x < 216 || x > 244 ? 'warn' : 'ok'; };
      const fase = (titel, rows) => `<table class="tbl tk"><thead><tr><th>${titel}</th><th>L1</th><th>L2</th><th>L3</th><th>Σ / øvrigt</th></tr></thead><tbody>${rows.map(([l, f, sum]) =>
        `<tr><td>${l}</td>${[1, 2, 3].map(i => `<td class="${l === 'Spænding' ? vok(f(i)) : ''}">${val(f(i))}</td>`).join('')}<td>${sum ? val(sum) : ''}</td></tr>`).join('')}</tbody></table>`;
      const pv = [1, 2].map(i => { const P = parseFloat(d(`pv${i}_power`)?.state), U = parseFloat(d(`pv${i}_voltage`)?.state), I = parseFloat(d(`pv${i}_current`)?.state);
        return `<div class="mppt"><div class="mh">MPPT ${i}</div><div class="mv">${val(`pv${i}_power`, 0)}</div><div class="ms"><span>${val(`pv${i}_voltage`)}</span><span>${val(`pv${i}_current`, 2)}</span></div>
          <div class="note">U × I = ${isNaN(U * I) ? '–' : nf(U * I)} W</div></div>`; }).join('');
      const kv = rows => `<table class="tbl tk"><tbody>${rows.map(([l, n, dec]) => `<tr><td>${l}</td><td>${typeof n === 'function' ? n() : val(n, dec)}</td></tr>`).join('')}</tbody></table>`;
      const I2 = this._cfg?.inverter2_prefix, R = (this._cfg?.inverter2_relae || '').split('.')[1] || '', v2 = (n, dec = 1) => val(n, dec, I2),
        rel = id => R ? this.st('switch.' + R + id) || this.st('binary_sensor.' + R + id) : null;
      const pv2 = [1, 2].map(i => `<div class="mppt"><div class="mh">MPPT ${i}</div><div class="mv">${v2(`pv${i}_power`, 0)}</div><div class="ms"><span>${v2(`pv${i}_voltage`)}</span><span>${v2(`pv${i}_current`, 2)}</span></div></div>`).join('');
      const fejl = ['overheating', 'overpowering', 'overvoltage', 'overcurrent'].filter(k => rel('_' + k)?.state === 'on');
      const c2 = d('connection', I2)?.state, a2 = d('output_ac_power', I2)?.state;
      const vaek2 = c2 ? c2 !== 'on' : (!a2 || ['unavailable', 'unknown'].includes(a2));
      const solNu = parseFloat(d('pv_power')?.state) || 0; // producerer hovedinverteren, er det ikke nat
      const relae2 = rel('') ? `<p class="note">Relæ: ${esc(rel('').state)}${fejl.length ? ` · <b style="color:${C.err}">${fejl.join(', ')}</b>` : ''}</p>` : '';
      const inv2 = vaek2 ? (solNu > 300
        ? `<div class="sover warn"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><div><b>Svarer ikke</b><span>Der er sol på hovedanlægget (${nf(solNu / 1000, 1)} kW), men inverter 2 svarer ikke. Tjek forbindelsen eller relæet.</span></div></div>${relae2}`
        : `<div class="sover"><ha-icon icon="mdi:weather-night"></ha-icon><div><b>Sover – for lidt lys</b><span>Inverteren slukker sig selv, når solen ikke giver nok strøm, og vågner igen af sig selv.</span></div></div>${relae2}`)
        : `<div class="mppts">${pv2}<div class="mppt"><div class="mh">AC ud</div><div class="mv">${v2('output_ac_power', 0)}</div><div class="ms"><span>i dag ${v2('today_production')}</span></div></div></div>
        <table class="tbl tk"><thead><tr><th>Net</th><th>L1</th><th>L2</th><th>L3</th><th>Øvrigt</th></tr></thead><tbody>
        <tr><td>Spænding</td>${[1, 2, 3].map(i => `<td>${v2(`grid_l${i}_voltage`)}</td>`).join('')}<td>${v2('grid_frequency', 2)}</td></tr>
        <tr><td>Strøm</td>${[1, 2, 3].map(i => `<td>${v2(`grid_l${i}_current`, 2)}</td>`).join('')}<td>${v2('output_apparent_power', 0)}</td></tr>
        <tr><td>Linjespænding</td><td>${v2('grid_l12_voltage')}</td><td>${v2('grid_l23_voltage')}</td><td>${v2('grid_l31_voltage')}</td><td>L1-L2 · L2-L3 · L3-L1</td></tr></tbody></table>
        ${kv([['Model / status', () => `${esc(d('device', I2)?.state || '–')} · ${esc(d('device_state', I2)?.state || '–')}`], ['DC-indgang / AC-udgang', () => `${v2('input_power', 0)} / ${v2('output_ac_power', 0)}`],
          ['Temperatur (inverter / DC)', () => `${v2('temperature')} / ${v2('dc_temperature')}`], ['Alarm / fejl', () => `${esc(d('device_alarm', I2)?.state || '–')} / ${esc(d('device_fault', I2)?.state || '–')}`],
          ['Produceret i dag / i alt', () => `${v2('today_production')} / ${v2('total_production', 0)}`], ['Forbindelse', () => esc(d('connection', I2)?.state || '–')],
          ['Relæ (tænd/sluk)', () => !R ? '–' : `${esc(rel('')?.state || '–')} · ${val('effekt', 0, R + '_')}${fejl.length ? ` · <b style="color:${C.err}">${fejl.join(', ')}</b>` : ' · ingen beskyttelsesfejl'}`]])}
        <p class="note">Sidder inverter 2 på hybrid-inverterens GEN-port, måles den også som "mikroinverter" – tallene kan afvige ved lav effekt.</p>`;
      const prog = `<table class="tbl tk"><thead><tr><th>Program</th><th>Effekt</th><th>SOC</th><th>Spænding</th><th>Netladning</th></tr></thead><tbody>${[1, 2, 3, 4, 5, 6].map(i =>
        `<tr><td>${i}</td><td>${val(`program_${i}_power`, 0)}</td><td>${val(`program_${i}_soc`, 0)}</td><td>${val(`program_${i}_voltage`)}</td><td>${esc(d(`program_${i}_charging`)?.state || '–')}</td></tr>`).join('')}</tbody></table>`;
      return `<div class="grid g2">
        ${this.card(`Inverter 1 · ${esc(this._cfg?.inverter_navn || 'hybrid-inverter')} – strenge`, `<div class="mppts">${pv}<div class="mppt"><div class="mh">GEN-port / mikroinverter</div><div class="mv">${val('microinverter_power', 0)}</div>
          <div class="ms"><span>i dag ${val('microinverter_energy_today')}</span></div></div></div>
        <table class="tbl tk"><thead><tr><th>Udgang</th><th>L1</th><th>L2</th><th>L3</th><th>Øvrigt</th></tr></thead><tbody>
        <tr><td>Spænding</td>${[1, 2, 3].map(i => `<td class="${vok(`output_l${i}_voltage`)}">${val(`output_l${i}_voltage`)}</td>`).join('')}<td>${val('output_frequency', 2)}</td></tr>
        <tr><td>Strøm</td>${[1, 2, 3].map(i => `<td>${val(`output_l${i}_current`, 2)}</td>`).join('')}<td></td></tr>
        <tr><td>Effekt</td>${[1, 2, 3].map(i => `<td>${val(`output_l${i}_power`, 0)}</td>`).join('')}<td>${val('power', 0)}</td></tr></tbody></table>
        ${kv([['Model / status', () => `${esc(d('device')?.state || '–')} · ${esc(d('device_state')?.state || '–')}`], ['DC-indgang (PV) / AC-udgang', () => `${val('pv_power', 0)} / ${val('power', 0)}`],
          ['Temperatur (AC / DC)', () => `${val('temperature')} / ${val('dc_temperature')}`], ['Alarm / fejl', () => `${esc(d('device_alarm')?.state || '–')} / ${esc(d('device_fault')?.state || '–')}`],
          ['Relæ', 'device_relay'], ['Tab nu / i dag', () => `${val('power_losses', 0)} / ${val('today_losses')}`],
          ['Produceret i dag / i alt', () => `${val('today_production')} / ${val('total_production', 0)}`], ['Forbindelse', () => `${esc(d('connection')?.state || '–')} · opdateres hvert ${val('update_interval', 1)}`],
          ['Arbejdstilstand', () => `${esc(d('work_mode')?.state || '–')} · ${esc(d('energy_pattern')?.state || '–')}`]])}`, {icon: 'mdi:solar-panel'})}
        ${I2 ? this.card(`Inverter 2 · ${esc(this._cfg?.inverter2_navn || 'streng-inverter')}`, inv2, {icon: 'mdi:solar-panel-large'}) : ''}
        </div>
        ${this.card('Elnet (eksterne CT – målerpunktet)', fase('Net', [['Spænding', i => `grid_l${i}_voltage`, 'grid_frequency'], ['Strøm', i => `external_ct${i}_current`], ['Effekt', i => `external_ct${i}_power`, 'external_power']])
          + `<p class="note">Spænding: grøn 216–244 V, orange ellers inden for ±10 % (207–253 V), rød udenfor.</p>`, {icon: 'mdi:transmission-tower'})}
        ${this.card('Interne CT', fase('Intern CT', [['Strøm', i => `internal_ct${i}_current`], ['Effekt', i => `internal_ct${i}_power`, 'internal_power']]), {icon: 'mdi:sine-wave'})}
        ${this.card('Husets last', fase('Last', [['Spænding', i => `load_l${i}_voltage`, 'load_frequency'], ['Effekt', i => `load_l${i}_power`, 'load_power'], ['UPS-last', i => `load_ups_l${i}_power`, 'load_ups_power'], ['Mikroinverter', i => `microinverter_l${i}_power`, 'microinverter_power']]), {icon: 'mdi:home-lightning-bolt'})}
        <div class="grid g2">
        ${this.card('Batteri', kv([['Ladeniveau', 'battery', 0], ['Tilstand', 'battery_state'], ['Spænding', 'battery_voltage', 2], ['Strøm', 'battery_current', 1], ['Effekt', 'battery_power', 0],
          ['Temperatur', 'battery_temperature'], ['Sundhed (SOH)', 'battery_soh'], ['Kapacitet', 'battery_capacity'], ['Cykler i dag / i alt', () => `${val('today_battery_life_cycles', 2)} / ${val('total_battery_life_cycles', 0)}`],
          ['Ladet / afladet i dag', () => `${val('today_battery_charge')} / ${val('today_battery_discharge')}`], ['BMS', 'battery_bms_type'], ['Alarm / fejl', () => `${esc(d('battery_alarm')?.state || '–')} / ${esc(d('battery_fault')?.state || '–')}`]]), {icon: 'mdi:battery-high'})}
        ${this.card('Indstillinger (kun aflæsning)', kv([['Maks. lade-/afladestrøm', () => `${val('battery_max_charging_current', 0)} / ${val('battery_max_discharging_current', 0)}`],
          ['Netladestrøm', 'battery_grid_charging_current', 0], ['Shutdown / restart / lav SOC', () => `${val('battery_shutdown_soc', 0)} / ${val('battery_restart_soc', 0)} / ${val('battery_low_soc', 0)}`],
          ['Shutdown / lav spænding', () => `${val('battery_shutdown_voltage')} / ${val('battery_low_voltage')}`], ['Float / absorption', () => `${val('battery_float')} / ${val('battery_absorption')}`],
          ['Nulexport-effekt', 'zero_export_power', 0], ['Maks. import / eksport', () => `${val('grid_max_import_power', 0)} / ${val('grid_max_export_power', 0)}`],
          ['Peak shaving net', () => `${esc(d('grid_peak_shaving')?.state || '–')} · ${val('grid_peak_shaving', 0)}`], ['Netbeskyttelse høj spænding / frekvens', () => `${val('grid_voltage_protection_high')} · ${val('grid_frequency_protection_low')}–${val('grid_frequency_protection_high')}`]]), {icon: 'mdi:tune'})}
        </div>
        ${this.card('Tidsprogrammer i inverteren (Wattlas skriver dem løbende)', prog, {icon: 'mdi:timetable'})}`;
    }

    // ---------- STYRING (tilsidesættelser + indstillinger) ----------
    ovBanner() {
      const s = this.st('binary_sensor.wattlas_tilsidesaettelse_aktiv'), m = s?.attributes?.tilstand, til = new Date(s?.attributes?.til || 0);
      const min = Math.max(0, Math.round((til - Date.now()) / 60000));
      const navn = {lad: `Lader fra elnettet til ${s?.attributes?.lad_til} %`, ingen_netladning: 'Ingen netopladning', gem: 'Batteriet gemmes (ingen afladning)', brug: 'Batteriet forsyner huset'}[m] || m;
      return `<div class="ovb"><ha-icon icon="mdi:hand-back-right"></ha-icon><div><b>Manuel tilsidesættelse: ${navn}</b><span>Udløber kl. ${String(til.getHours()).padStart(2, '0')}:${String(til.getMinutes()).padStart(2, '0')} (om ${min >= 60 ? Math.floor(min / 60) + ' t ' : ''}${min % 60} min) – derefter følger Wattlas planen igen.</span></div><button data-a="ts" data-v="ingen">Stop nu</button></div>`;
    }
    async _tilsidesaet(v) {
      const nu = new Date(), midnat = Math.max(15, Math.round((new Date(nu.getFullYear(), nu.getMonth(), nu.getDate() + 1) - nu) / 60000));
      const minutter = this._dur === 'midnat' ? midnat : Number(this._dur);
      const tekst = {lad: `Lad batteriet fra elnettet til ${this._tsoc} % de næste ${minutter} min?`, brug: `Lad batteriet forsyne huset de næste ${minutter} min, uanset planen?`}[v];
      if (tekst && !confirm(tekst)) return;
      try { await this._hass.callService('script', 'wattlas_tilsidesaet', {tilstand: v, minutter, soc: this._tsoc}); this._log = null; }
      catch (e) { alert('Kunne ikke sætte tilsidesættelse: ' + (e.message || e)); }
    }
    async _hentLog() {
      this._log = [];
      try {
        const r = await this._hass.callWS({type: 'logbook/get_events', start_time: new Date(Date.now() - 7 * 864e5).toISOString(), entity_ids: ['input_select.wattlas_tilsidesaettelse']});
        this._log = (r || []).filter(e => e.message).reverse().slice(0, 8);
      } catch (e) { this._log = []; }
      this._last = 0; this._render();
    }
    styring() {
      if (this._log === null) this._hentLog();
      const on = this.st('input_boolean.emhass_styring_aktiv')?.state === 'on', mode = this.st('sensor.emhass_planvalg')?.state;
      const skygge = this.st('input_boolean.wattlas_skygge')?.state === 'on', ville = this.st('sensor.wattlas_skygge')?.state;
      const pb = this.n('input_number.emhass_plan_batteri_w') || 0, pn = this.n('input_number.emhass_plan_net_w') || 0, ps = this.n('input_number.emhass_plan_soc');
      const handling = !on ? 'Styringen er slukket – inverteren kører selvforbrug' : pb < -150 ? (pn > 150 ? 'Lader batteriet fra elnettet' : 'Lader batteriet fra solen') + ` mod ${nf(ps)} %` : pb > 150 ? `Batteriet forsyner huset (${nf(pb / 1000, 1)} kW)` : 'Batteriet hviler';
      const ov = this.st('binary_sensor.wattlas_tilsidesaettelse_aktiv')?.state === 'on', aktivMode = ov ? this.st('binary_sensor.wattlas_tilsidesaettelse_aktiv').attributes.tilstand : 'ingen';
      const salgStop = this.st('binary_sensor.wattlas_solsalg_stoppet')?.state === 'on';
      const knap = (k, ic, c, t, d) => `<div class="ovc ${aktivMode === k ? 'on' : ''}" style="--c:${c}"><div class="ovh"><ha-icon icon="${ic}"></ha-icon><b>${t}</b></div><p>${d}</p>
        <button data-a="ts" data-v="${aktivMode === k ? 'ingen' : k}">${aktivMode === k ? 'Stop' : 'Start'}</button></div>`;
      const num = (id, t, u, step, d) => { const s = this.st(id); const v = s ? parseFloat(s.state) : null;
        return `<div class="set"><div><b>${t}</b><span>${d}</span></div><div class="stp"><button data-a="num" data-v="${id}|-${step}">−</button><em>${v === null ? '–' : v === 0 && id.endsWith('max_net_kw') ? 'ingen grænse' : id.endsWith('max_net_kw') ? nf(v, 1) + ' kW · ' + nf(v * 1000 / 690) + ' A' : nf(v, step < 1 ? 2 : (step < 1 ? 1 : 0)) + ' ' + u}</em><button data-a="num" data-v="${id}|${step}">+</button></div></div>`; };
      const tog = (id, t, d) => { const s = this.st(id)?.state === 'on'; return `<div class="set"><div><b>${t}</b><span>${d}</span></div><button class="sw ${s ? 'on' : ''}" data-a="tog" data-v="${id}"><i></i></button></div>`; };
      const log = (this._log || []).map(e => { const d = new Date(e.when * 1000); return `<li><span>${String(d.getDate())}/${d.getMonth() + 1} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}</span>${esc(e.message)}</li>`; }).join('') || '<li><span></span>Ingen tilsidesættelser de sidste 7 dage</li>';
      return `<div class="hero ${on ? '' : 'off'}"><img src="${LOGO}" alt=""><div><small>${on && skygge ? 'WATTLAS I SKYGGE – STYRER IKKE INVERTEREN' : `WATTLAS STYRER ${on ? '' : 'IKKE'}`}</small><h2>${on && skygge ? 'Planen: ' + handling.charAt(0).toLowerCase() + handling.slice(1) : handling}</h2>
          ${on && skygge ? `<span><ha-icon icon="mdi:ghost-outline" style="--mdc-icon-size:16px"></ha-icon> ${esc(ville || '–')}</span><br>` : ''}
          <span>Plan: ${esc(mode || '–')} · EMHASS genberegner hvert 5. min · regulerer hvert 30. sek.</span></div>
          <div class="hbtn"><button class="lnk" data-a="tog" data-v="input_boolean.wattlas_skygge" title="Skygge: Wattlas viser, hvad den ville gøre, men styrer ikke inverteren"><ha-icon icon="mdi:ghost${skygge ? '' : '-off-outline'}" style="--mdc-icon-size:16px"></ha-icon> Skygge ${skygge ? 'til' : 'fra'}</button>
          <a class="lnk" href="#plan" data-a="tab" data-v="plan">Planens logik ›</a></div></div>
        ${ov ? this.ovBanner() : ''}
        ${this.card('Elpris i dag og i morgen', this.prisStribe(), {icon: 'mdi:currency-usd', right: `<button class="lnk" data-a="tab" data-v="elpris">Elpris ›</button>`})}
        ${this.card('Manuel tilsidesættelse', `<p class="note" style="margin:0 0 12px">Tilsidesætter planen i en periode og udløber altid af sig selv. Sikkerhedsgrænserne (sikring, faser, spænding, reserve) gælder stadig.</p>
          <div class="toolbar"><span class="muted">Varighed</span>${this.seg('dur', [['30', '30 min'], ['60', '1 time'], ['120', '2 timer'], ['240', '4 timer'], ['midnat', 'Til midnat']], this._dur)}
          <span class="muted">Lad til</span>${this.seg('tsoc', [['60', '60 %'], ['80', '80 %'], ['100', '100 %']], String(this._tsoc))}</div>
          <div class="ovg">
            ${knap('lad', 'mdi:transmission-tower-import', C.net, 'Lad nu', `Køb strøm og lad batteriet til ${this._tsoc} % – fx før en storm eller et varslet strømsvigt.`)}
            ${knap('ingen_netladning', 'mdi:cancel', C.warn, 'Ingen netopladning', 'Batteriet må kun lades af solen. Planens netopladning springes over.')}
            ${knap('gem', 'mdi:battery-lock', C.bat, 'Gem batteriet', 'Batteriet aflader ikke – strømmen gemmes til senere. Huset bruger nettet.')}
            ${knap('brug', 'mdi:home-lightning-bolt', C.hus, 'Brug batteriet', 'Batteriet forsyner huset nu, ned til reserven – uanset hvad planen siger.')}
            <div class="ovc ${salgStop ? 'on' : ''}" style="--c:${C.sol}"><div class="ovh"><ha-icon icon="mdi:solar-power-variant-outline"></ha-icon><b>Stop solsalg</b></div><p>Overskudssol sælges ikke til nettet${salgStop ? ' (aktiv)' : ''}. Ellers sælges kun ved positiv salgspris.</p>
              <button data-a="ts" data-v="${salgStop ? 'solsalg_auto' : 'solsalg_stop'}">${salgStop ? 'Automatisk igen' : 'Start'}</button></div>
          </div>`, {icon: 'mdi:hand-back-right'})}
        <div class="grid g2">${this.card('Indstillinger til optimeringen', `<p class="note" style="margin:0 0 8px">Sendes til EMHASS ved hver beregning, så planen tager højde for dem – reglerne kæmper ikke mod planen.</p>
            ${num('input_number.wattlas_reserve', 'Reserve', '%', 5, 'Laveste batteriniveau i planen (fx højere om vinteren eller ved stormvarsel)')}
            ${num('input_number.wattlas_slut_soc', 'Batteri ved planens slutning', '%', 5, 'Hvor meget der skal være tilbage, når horisonten slutter')}
            ${num('input_number.wattlas_max_net_kw', 'Maks. køb fra elnettet', 'kW', 0.5, 'Sikringsgrænse for opladning (A = pr. fase ved 230 V). 0 = kun importloftet fra opsætningen')}
            ${num('input_number.wattlas_slid', 'Batterislid', 'kr./kWh', 0.01, 'Pris pr. afladet kWh – højere = færre små runder')}
            ${tog('input_boolean.emhass_fuld_opladning', 'Ugentlig fuldladning', 'Lad til 100 % mindst én gang om ugen (cellebalancering)')}
            ${tog('input_boolean.emhass_styring_aktiv', 'Wattlas styrer batteriet', 'Slå fra = inverteren kører selvforbrug med 15 % reserve')}
            ${tog('input_boolean.wattlas_skygge', 'Skygge (vis kun)', 'Wattlas planlægger og viser, hvad den ville gøre, men skriver intet til inverteren – til nye anlæg eller ved siden af din nuværende styring')}`, {icon: 'mdi:tune-variant'})}
          ${this.card('Seneste tilsidesættelser', `<ul class="logl">${log}</ul>`, {icon: 'mdi:history'})}</div>
        ${this.hvadHvis()}
        <div class="grid g2">${this.forbruger()}<div></div></div>`;
    }

    priserIdag(dag = 'raw_today') {
      return (this.a('sensor.energi_data_service', dag) || []).map(r => { const d = new Date(r.hour); const p = Number(r.price);
        return {h: d.getHours(), t: d, spot: p, buy: buy(p, d.getHours()), sell: sell(p)}; }).filter(r => !isNaN(r.spot));
    }

    // ---------- ØKONOMI ----------
    okonomi() {
      const S = this.sparetDage(), maal = this.maal(), nu = new Date(), idag = ymd(nu);
      const inv = this.n('input_number.solcelle_investering') || 1, total = this.n('sensor.solcelle_sparet_i_alt') || 0;
      const sum = (fra, til) => Object.entries(S).filter(([d]) => d >= fra && d <= til).reduce((a, [, v]) => a + v, 0);
      const man = monday(nu), uge = sum(ymd(man), idag), mFra = ymd(new Date(nu.getFullYear(), nu.getMonth(), 1)), md = sum(mFra, idag);
      const dageIUge = (nu.getDay() + 6) % 7 + 1, dageIMd = nu.getDate();
      const dag0 = pd(START), dageAlt = Math.max(1, Math.round((nu - dag0) / 864e5));
      const rate = total / dageAlt, rest = Math.max(0, inv - total), aar = rate > 0 ? rest / rate / 365 : null;
      const i = S[idag];
      let h = `<div class="grid kpis">
        ${this.kpi('Sparet i dag', i !== undefined ? kr(i) : '–', 'mdi:calendar-today', i >= maal ? C.ok : C.err, {bar: (i || 0) / maal, sub: `mål ${kr(maal)}`})}
        ${this.kpi('Sparet denne uge', kr(uge), 'mdi:chart-line', uge >= maal * dageIUge ? C.ok : C.err, {bar: uge / (maal * dageIUge), sub: `mål ${kr(maal * dageIUge)}`})}
        ${this.kpi('Sparet denne måned', kr(md), 'mdi:trending-up', md >= maal * dageIMd ? C.ok : C.err, {bar: md / (maal * dageIMd), sub: `mål ${kr(maal * dageIMd)}`})}
        ${this.kpi('Sparet i år', kr(total), 'mdi:rocket-launch', C.ok, {bar: total / (maal * dageAlt), sub: 'anlægget startede ' + pdFmt(pd(START))})}
        ${this.kpi('Samlede besparelser', kr(total), 'mdi:piggy-bank', C.warn, {bar: total / inv, sub: `${nf(100 * total / inv, 1)} % af investeringen`})}
        ${this.kpi('Samlet investering', kr(inv), 'mdi:briefcase', C.blue, {info: 'input_number.solcelle_investering', sub: 'tryk for at rette'})}
        ${this.kpi('Tjent hjem', nf(100 * total / inv, 1) + ' %', 'mdi:calendar-check', C.goal, {bar: total / inv, sub: aar !== null ? `${nf(aar, 1)} år tilbage · ${pdFmt(addD(nu, rest / rate))}` : ''})}
      </div>`;
      // Overblik mål: akkumuleret faktisk + prognose til 2041 + investering
      const sorted = Object.entries(S).sort(), pts = [[dag0.getTime(), 0]].concat(FOER_NOV && FOER_DATO ? [[pd(FOER_DATO).getTime(), FOER_NOV]] : []);
      let acc = FOER_NOV; sorted.forEach(([d, v]) => { acc += v; pts.push([pd(d).getTime() + 864e5, acc]); });
      const y0 = dag0.getFullYear(), slut = new Date(y0 + 15, 11, 31), progn = [[nu.getTime(), total]];
      for (let y = nu.getFullYear() + 1; y <= y0 + 15; y++) { const t = new Date(y, 0, 1); progn.push([t.getTime(), total + rate * (t - nu) / 864e5]); }
      const dots = progn.slice(1).map(p => [p[0], p[1], String(new Date(p[0]).getFullYear())]);
      const xt = []; for (let y = y0; y <= y0 + 15; y++) xt.push([new Date(y, 0, 1).getTime(), String(y)]);
      const over = lines({series: [{pts, color: C.ok}, {pts: progn, color: C.warn, dash: '6 5', dots}], xmin: new Date(y0, 0, 1).getTime(), xmax: slut.getTime(),
        xticks: xt.filter((_, k) => k % 2 === 0), hlines: [{v: inv, color: C.goal, label: 'Samlet investering'}], unit: 'kr.', fmt: v => v >= 1000 ? nf(v / 1000) + 'k' : nf(v), W: this.w('main')});
      h += `<div class="grid g21">${this.card('Overblik mål', over + this.legend([['Faktiske besparelser', C.ok], ['Prognose (gns. siden start)', C.warn]]), {icon: 'mdi:flag-checkered'})}`;
      // Uge
      const m0 = addD(man, 7 * this._ugeOffset), ugeDage = [...Array(7)].map((_, k) => addD(m0, k));
      const uv = ugeDage.map(d => { const v = S[ymd(d)]; return v === undefined ? null : v; });
      const ugeNr = isoUge(m0);
      h += this.card(`Uge ${ugeNr}`, bars({labels: ugeDage.map(d => UGEDAG[d.getDay()]), series: [
          {name: 'Faktisk', color: v => v >= maal ? C.ok : v >= 0 ? C.warn : C.err, values: uv}, {name: 'Mål', color: '#64748b', values: ugeDage.map(() => maal)}], unit: 'kr.', W: this.w('side'), height: 260})
        + this.legend([['Faktisk', C.ok], ['Mål', '#64748b']]),
        {icon: 'mdi:calendar-week', right: `<button class="lnk" data-a="uge" data-v="-1">‹</button><button class="lnk" data-a="uge" data-v="1" ${this._ugeOffset >= 0 ? 'disabled' : ''}>›</button>`}) + '</div>';
      // Resultater pr. dag + årsstatus
      const mk = this._maaned || idag.slice(0, 7), [yy, mm] = mk.split('-').map(Number);
      const dimd = new Date(yy, mm, 0).getDate(), rows = [];
      for (let d = dimd; d >= 1; d--) { const k = `${mk}-${String(d).padStart(2, '0')}`; if (k > idag) continue; const v = S[k]; if (v === undefined) continue;
        const p = v / maal, c = p >= 1 ? C.ok : p >= 0.8 ? C.warn : C.err;
        rows.push(`<tr><td>${UGEDAG[pd(k).getDay()]}. ${d}. ${MDK[mm - 1]} ${yy}</td><td>${kr(maal, 2)}</td><td><span class="cell" style="background:${c}">${kr(v, 2)}</span></td><td>${nf(p * 100, 1)} %</td></tr>`); }
      const mOpts = [...Array(12)].map((_, k) => ymd(new Date(nu.getFullYear(), nu.getMonth() - 11 + k, 1)).slice(0, 7)).filter(x => x >= START.slice(0, 7))
        .filter((x, k, a) => a.indexOf(x) === k).map(x => [x, MAANED[Number(x.slice(5)) - 1] + ' ' + x.slice(0, 4)]);
      const res = `<table class="tbl"><thead><tr><th>Dato</th><th>Mål</th><th>Faktisk</th><th>Faktisk %</th></tr></thead><tbody>${rows.join('') || '<tr><td colspan="4">Ingen dage endnu</td></tr>'}</tbody></table>`;
      const maaneder = [];
      for (let k = 0; k < 12; k++) { const d = new Date(nu.getFullYear(), k, 1), key = ymd(d).slice(0, 7);
        if (key < START.slice(0, 7) || key > idag.slice(0, 7)) continue;
        const dd = new Date(nu.getFullYear(), k + 1, 0).getDate();
        const v = sum(key + '-01', key + '-31');
        maaneder.push({lb: MDK[k], v, maal: maal * ((key === idag.slice(0, 7) ? nu.getDate() : dd) - (key === START.slice(0, 7) ? pd(START).getDate() - 1 : 0))}); }
      const efter = maaneder;
      const aarLabels = efter.map(x => x.lb);
      const aarF = efter.map(x => x.v), aarM = efter.map(x => x.maal);
      h += `<div class="grid g21">${this.card('Resultater', res, {icon: 'mdi:table', right: `<div class="seg">${mOpts.map(([v, l]) => `<button data-a="maaned" data-v="${v}" class="${mk === v ? 'on' : ''}">${l}</button>`).join('')}</div>`})}
        ${this.card('År status ' + nu.getFullYear(), bars({labels: aarLabels, series: [{name: 'Faktisk', color: C.ok, values: aarF}, {name: 'Mål', color: '#64748b', values: aarM}], unit: 'kr.', height: 280, W: this.w('side')})
          + this.legend([['Faktisk', C.ok], ['Mål', '#64748b']]) + `<p class="note">${FOER_NOV ? `Startsaldo før Wattlas: ${kr(FOER_NOV)} (indgår i totalen). ` : ''}Mål = investering fordelt over 15 år (${kr(maal, 2)} pr. dag).</p>`, {icon: 'mdi:chart-bar'})}</div>`;
      return h;
    }

    // ---------- HISTORIK ----------
    historik() {
      const D = this._dage;
      if (!D) return this.card('Historik', '<div class="loading">Henter historik fra databasen …</div>');
      const nu = new Date(), idag = ymd(nu);
      const sel = this._hist;
      let rows = D, titel = 'siden ' + pdFmt(pd(START));
      if (sel === '30') { rows = D.filter(r => r.d >= ymd(addD(nu, -29))); titel = 'seneste 30 dage'; }
      if (sel === 'aar') { rows = D.filter(r => r.d >= `${nu.getFullYear()}-01-01`); titel = 'i år'; }
      if (sel === 'maaned' && this._valgtMaaned) { rows = D.filter(r => r.d.startsWith(this._valgtMaaned)); titel = MAANED[Number(this._valgtMaaned.slice(5)) - 1] + ' ' + this._valgtMaaned.slice(0, 4); }
      const S = k => rows.reduce((a, r) => a + (r[k] || 0), 0);
      const last = r => r.pv + r.b - r.s - r.ch + r.dis;
      const prod = S('pv'), forb = rows.reduce((a, r) => a + last(r), 0), solgt = S('s'), koebt = S('b');
      let h = `<div class="toolbar">${this.seg('hist', [['maaneder', 'Måneder'], ['30', '30 dage'], ['aar', 'I år']], sel)}<span class="muted">Viser ${titel}</span></div>
        <div class="grid kpis4">
        ${this.kpi('Produceret', nf(prod) + ' kWh', 'mdi:white-balance-sunny', C.sol)}
        ${this.kpi('Forbrug', nf(forb) + ' kWh', 'mdi:home', C.hus)}
        ${this.kpi('Solgt', nf(solgt) + ' kWh', 'mdi:arrow-up-circle', C.bat)}
        ${this.kpi('Købt', nf(koebt) + ' kWh', 'mdi:arrow-down-circle', C.err)}</div>`;
      // grafer: pr. måned eller pr. dag
      let labels, grp;
      if (sel === 'maaneder') {
        const ms = [...new Set(D.map(r => r.d.slice(0, 7)))];
        grp = ms.map(m => { const rr = D.filter(r => r.d.startsWith(m)); const f = k => rr.reduce((a, r) => a + (r[k] || 0), 0);
          return {pv: f('pv'), last: rr.reduce((a, r) => a + last(r), 0), s: f('s'), b: f('b'), ch: f('ch'), dis: f('dis')}; });
        labels = ms.map(m => MDK[Number(m.slice(5)) - 1]);
      } else { grp = rows.map(r => ({pv: r.pv, last: last(r), s: r.s, b: r.b, ch: r.ch, dis: r.dis})); labels = rows.map(r => `${Number(r.d.slice(8))}/${Number(r.d.slice(5, 7))}`); }
      const ev = Math.max(1, Math.ceil(labels.length / 12));
      const g = (t, i, a, b, ca, cb, na, nb) => this.card(t, bars({labels, series: [{name: na, color: ca, values: grp.map(x => x[a])}, {name: nb, color: cb, values: grp.map(x => x[b])}], unit: 'kWh', every: ev, W: this.w('half')})
        + this.legend([[na, ca], [nb, cb]]), {icon: i});
      h += `<div class="grid g2">${g('Produktion og forbrug', 'mdi:chart-bar', 'pv', 'last', C.sol, C.hus, 'Produceret', 'Forbrug')}
        ${g('Solgt og købt', 'mdi:swap-vertical', 's', 'b', C.bat, C.err, 'Solgt', 'Købt')}
        ${g('Batteri', 'mdi:battery-charging', 'ch', 'dis', C.warn, C.net, 'Opladning', 'Afladning')}`;
      // indsigter
      const alle = D, pAll = alle.reduce((a, r) => a + r.pv, 0), lAll = alle.reduce((a, r) => a + last(r), 0);
      const fulde = [...new Set(alle.map(r => r.d.slice(0, 7)))].filter(m => m > START.slice(0, 7) && m < idag.slice(0, 7));
      const gnsM = fulde.length ? fulde.reduce((a, m) => a + alle.filter(r => r.d.startsWith(m)).reduce((x, r) => x + r.pv, 0), 0) / fulde.length : null;
      const selvf = 1 - alle.reduce((a, r) => a + r.b, 0) / (lAll || 1), eget = 1 - alle.reduce((a, r) => a + r.s, 0) / (pAll || 1);
      h += this.card('Indsigter', `<ul class="ins">
        <li><ha-icon icon="mdi:lightbulb-on-outline" style="color:${C.sol}"></ha-icon><div><b>Samlet produktion</b><span>${nf(pAll)} kWh produceret siden ${pdFmt(pd(START))}.</span></div></li>
        <li><ha-icon icon="mdi:calendar-month" style="color:${C.blue}"></ha-icon><div><b>Gennemsnit pr. måned</b><span>${gnsM !== null ? nf(gnsM) + ' kWh i en typisk hel måned.' : 'Kommer efter første hele måned.'}</span></div></li>
        <li><ha-icon icon="mdi:shield-check" style="color:${C.ok}"></ha-icon><div><b>Selvforsyning</b><span>${nf(selvf * 100)} % af forbruget blev dækket uden køb fra elnettet.</span></div></li>
        <li><ha-icon icon="mdi:recycle" style="color:${C.hus}"></ha-icon><div><b>Egetforbrug</b><span>I brugte selv ${nf(eget * 100)} % af jeres egen produktion.</span></div></li>
        <li><ha-icon icon="mdi:battery-heart-variant" style="color:${C.bat}"></ha-icon><div><b>Batteriet</b><span>${nf(alle.reduce((a, r) => a + r.dis, 0))} kWh leveret til huset siden start.</span></div></li></ul>`, {icon: 'mdi:lightbulb-outline'}) + '</div>';
      // rekorder + placeringer + måneder
      const ok = alle.filter(r => r.s <= r.pv + r.dis + 0.5 && r.ch <= r.pv + r.b + 0.5); // datafejl i importeret historik (fx 10/7) tæller ikke
      const top = (k, f = r => r[k]) => ok.reduce((a, r) => f(r) > f(a) ? r : a, ok[0] || {});
      const Sd = this.sparetDage(), spMax = Object.entries(Sd).reduce((a, b) => b[1] > a[1] ? b : a, ['', -1e9]);
      const fd = d => d ? `${Number(d.slice(8))}. ${MDK[Number(d.slice(5, 7)) - 1]}. ${d.slice(0, 4)}` : '–';
      const rek = [['mdi:arrow-up-circle', C.bat, 'Mest solgt på en dag', top('s'), 's', 'kWh'], ['mdi:arrow-down-circle', C.err, 'Mest købt på en dag', top('b'), 'b', 'kWh'],
        ['mdi:home', C.hus, 'Højeste forbrug på en dag', top('x', last), null, 'kWh'], ['mdi:battery-charging', C.warn, 'Største batteridag (ladet)', top('ch'), 'ch', 'kWh'],
        ['mdi:white-balance-sunny', C.sol, 'Mest produceret på en dag', top('pv'), 'pv', 'kWh']];
      const rekHtml = `<ul class="rek">${rek.map(([ic, c, t, r, k, u]) => `<li><div class="ki sm" style="background:${c}22;color:${c}"><ha-icon icon="${ic}"></ha-icon></div><div><b>${t}</b><span>${fd(r.d)}</span></div><em>${nf(k ? r[k] : last(r), 1)} ${u}</em></li>`).join('')}
        <li><div class="ki sm" style="background:${C.ok}22;color:${C.ok}"><ha-icon icon="mdi:piggy-bank"></ha-icon></div><div><b>Mest sparet på en dag</b><span>${fd(spMax[0])}</span></div><em>${kr(spMax[1], 2)}</em></li></ul>`;
      const mList = [...new Set(alle.map(r => r.d.slice(0, 7)))].map(m => { const rr = alle.filter(r => r.d.startsWith(m)); return {m, n: rr.length, pv: rr.reduce((a, r) => a + r.pv, 0)}; });
      const hele = mList.filter(x => x.m < idag.slice(0, 7));
      const top3 = [...hele].sort((a, b) => b.pv - a.pv).slice(0, 3), top5 = [...ok].sort((a, b) => b.pv - a.pv).slice(0, 5), lav = [...hele].filter(x => x.m > START.slice(0, 7)).sort((a, b) => a.pv - b.pv)[0];
      const mNavn = m => MAANED[Number(m.slice(5)) - 1] + ' ' + m.slice(0, 4);
      const plc = `<div class="sub">Top 3 måneder – produktion</div><ol class="plc">${top3.map((x, k) => `<li data-a="vmaaned" data-v="${x.m}" class="click"><span class="rank r${k}">${k + 1}</span>${mNavn(x.m)}<em>${nf(x.pv, 1)} kWh</em></li>`).join('')}</ol>
        <div class="sub">Top 5 dage – produktion</div><ol class="plc">${top5.map((r, k) => `<li><span class="rank r${k}">${k + 1}</span>${fd(r.d)}<em>${nf(r.pv, 1)} kWh</em></li>`).join('')}</ol>
        ${lav ? `<div class="sub">Laveste måned</div><ol class="plc"><li data-a="vmaaned" data-v="${lav.m}" class="click"><span class="rank">↓</span>${mNavn(lav.m)}<em>${nf(lav.pv, 1)} kWh</em></li></ol>` : ''}`;
      const ml = `<ul class="ml">${[...mList].reverse().map(x => `<li data-a="vmaaned" data-v="${x.m}" class="click ${this._valgtMaaned === x.m ? 'on' : ''}"><span>${mNavn(x.m)}</span><span class="muted">${x.n} dage</span><b>${nf(x.pv, 1)} kWh</b><ha-icon icon="mdi:chevron-right"></ha-icon></li>`).join('')}</ul>`;
      h += `<div class="grid g3">${this.card('Rekorder', rekHtml, {icon: 'mdi:trophy-outline'})}${this.card('Placeringer', plc, {icon: 'mdi:podium'})}${this.card('Måneder', ml + '<p class="note">Tryk på en måned for at se den dag for dag.</p>', {icon: 'mdi:calendar-month-outline'})}</div>`;
      return h;
    }

    // ---------- ELPRIS ----------
    elpris() {
      const mode = this._prisMode, nuH = new Date().getHours();
      const liste = (pr, idag) => {
        if (!pr.length) return '<p class="note">Morgendagens priser er endnu ikke tilgængelige (kommer ca. kl. 13).</p>';
        const vals = pr.map(p => mode === 'koeb' ? p.buy : p.sell), mx = Math.max(...vals);
        const sortv = [...vals].sort((a, b) => a - b), lo = sortv[Math.floor(vals.length / 3)], hi = sortv[Math.floor(2 * vals.length / 3)];
        return `<div class="plist">${pr.map((p, k) => { const v = vals[k]; const c = mode === 'koeb' ? (v <= lo ? C.ok : v <= hi ? C.warn : C.err) : (v >= hi ? C.ok : v >= lo ? C.warn : C.err);
          return `<div class="prow ${idag && p.h === nuH ? 'now' : ''}"><span>${String(p.h).padStart(2, '0')}</span><b>${nf(v, 2)} kr.</b><div class="pb"><i style="width:${Math.max(3, 100 * v / mx)}%;background:${c}"></i></div><small class="t ${tarif(p.h)}">${{lav: 'lav', hoej: 'høj', spids: 'spids'}[tarif(p.h)]}</small></div>`; }).join('')}</div>`;
      };
      const pi = this.priserIdag(), pm = this.priserIdag('raw_tomorrow');
      const v = pi.map(p => mode === 'koeb' ? p.buy : p.sell), now = pi.find(p => p.h === nuH);
      const mn = pi.length ? pi[v.indexOf(Math.min(...v))] : null, mx = pi.length ? pi[v.indexOf(Math.max(...v))] : null;
      const val = p => p ? nf(mode === 'koeb' ? p.buy : p.sell, 2) : '–';
      const head = `<div class="prices big"><div><span>Laveste · kl. ${mn ? String(mn.h).padStart(2, '0') : '–'}</span><b style="color:${mode === 'koeb' ? C.ok : C.err}">${val(mn)}</b></div>
        <div><span>Lige nu</span><b>${val(now)}</b></div><div><span>Højeste · kl. ${mx ? String(mx.h).padStart(2, '0') : '–'}</span><b style="color:${mode === 'koeb' ? C.err : C.ok}">${val(mx)}</b></div></div>`;
      const D = this._dage || [], sidste = D.slice(-30);
      const forbrug = bars({labels: sidste.map(r => `${Number(r.d.slice(8))}/${Number(r.d.slice(5, 7))}`), stacked: true, unit: 'kWh', every: 3, series: [
        {name: 'Lav tarif (00-06)', color: C.lav, values: sidste.map(r => r.bl)}, {name: 'Høj tarif', color: C.hoej, values: sidste.map(r => r.bh)},
        {name: 'Spidslast (17-21)', color: C.spids, values: sidste.map(r => r.bs)}], height: 280, W: this.w('half')});
      const ind = this.n('sensor.wattlas_i_dag_koebt');
      return `<div class="toolbar">${this.seg('pris', [['koeb', 'Købspris'], ['salg', 'Salgspris']], mode)}<span class="muted">kr./kWh ${mode === 'koeb' ? 'inkl. tariffer, afgifter og moms' : 'efter fradrag'}</span></div>
        <div class="grid g2">${this.card('Strømpris i dag', head + liste(pi, true), {icon: 'mdi:currency-usd'})}
        <div class="stack">${this.card('I morgen', liste(pm, false), {icon: 'mdi:calendar-arrow-right'})}
        ${this.card('Købt strøm pr. tarif', forbrug + this.legend([['Lav', C.lav], ['Høj', C.hoej], ['Spidslast', C.spids]]), {icon: 'mdi:transmission-tower-import', right: `<span class="muted">købt i dag <b>${nf(ind, 1)} kWh</b></span>`})}</div></div>`;
    }

    // ---------- SOLPROGNOSE ----------
    solprognose() {
      const fc = this.a(this.prog('power_now'), 'forecast') || [];
      const nu = new Date(), idag = ymd(nu);
      const perDag = {}; fc.forEach(r => { const d = new Date(r.datetime), k = ymd(d); perDag[k] = (perDag[k] || 0) + (r.watts || 0) / 4000; });
      const pvD = (this.n('sensor.wattlas_i_dag_produktion') || 0);
      const progn = pvD + (this.n(this.prog('energy_today_remaining')) || 0);
      const imorgen = perDag[ymd(addD(nu, 1))] ?? this.n(this.prog('energy_day_2')); // energy_day_1 er i dag
      const uge = Object.entries(perDag).filter(([d]) => d > idag).reduce((a, [, v]) => a + v, 0) + progn;
      let h = `<div class="grid kpis4">${this.kpi('Dagens prognose', nf(progn, 1) + ' kWh', 'mdi:weather-partly-cloudy', C.sol, {bar: pvD / (progn || 1), sub: `${nf(100 * pvD / (progn || 1))} % nået`})}
        ${this.kpi('Produceret i dag', nf(pvD, 1) + ' kWh', 'mdi:solar-power', C.ok)}
        ${this.kpi('Prognose i morgen', nf(imorgen, 1) + ' kWh', 'mdi:calendar-arrow-right', C.blue)}
        ${this.kpi('Kommende dage', nf(uge, 1) + ' kWh', 'mdi:calendar-week', C.net, {sub: `${Object.keys(perDag).filter(d => d >= idag).length} dage i prognosen`})}</div>`;
      const fcI = fc.filter(r => ymd(new Date(r.datetime)) === idag).map(r => { const d = new Date(r.datetime); return [d.getHours() + d.getMinutes() / 60, (r.watts || 0) / 1000]; });
      const akt = ((this._idag || {})['sensor.emhass_solproduktion_samlet'] || []).map(r => { const d = new Date(r.start); return [d.getHours() + d.getMinutes() / 60, (r.mean || 0) / 1000]; });
      const nuT = nu.getHours() + nu.getMinutes() / 60;
      const fcSaaLangt = fcI.filter(p => p[0] <= nuT).reduce((a, p) => a + p[1] * 0.25, 0); // 15-min-værdier i kW
      const rest = this.n(this.prog('energy_today_remaining')) || 0, afv = fcSaaLangt > 0.2 ? (pvD - fcSaaLangt) / fcSaaLangt * 100 : null;
      const ch = lines({series: [{pts: fcI, color: '#a78bfa', dash: '7 5', fill: 0.10, w: 2.5}, {pts: akt, color: C.sol, fill: 0.35, w: 3}], xmin: 4, xmax: 20, vlines: [{x: nuT, label: 'nu', color: '#e2e8f0'}],
        xticks: [4, 6, 8, 10, 12, 14, 16, 18, 20].map(x => [x, String(x).padStart(2, '0') + ':00']), unit: 'kW', fmt: v => nf(v, 1), W: this.w('main')});
      const D = this._dage || [], hist = D.slice(-3, -1);
      const days = hist.map(r => ({d: r.d, v: r.pv, fakt: true})).concat(Object.entries(perDag).filter(([d]) => d >= idag).map(([d, v]) => ({d, v: d === idag ? progn : v})));
      const mxv = Math.max(...days.map(x => x.v), 1);
      const nd = `<div class="hbars">${days.map(x => `<div class="hb"><span>${x.d === idag ? 'I dag' : UGEDAG[pd(x.d).getDay()] + '. ' + Number(x.d.slice(8)) + '/' + Number(x.d.slice(5, 7))}</span><div><i style="width:${100 * x.v / mxv}%;background:${x.fakt ? C.ok : C.sol}">${nf(x.v, 1)}</i></div></div>`).join('')}</div>`
        + this.legend([['Faktisk', C.ok], ['Prognose', C.sol]]);
      const forkl = `<p class="note"><b style="color:${C.sol}">Gul flade</b> = målt produktion (begge invertere, 5-min-gennemsnit) – den slutter ved "nu", fordi resten af dagen ikke er sket endnu.
        <b style="color:#a78bfa">Violet stiplet</b> = Helios-prognosen for hele dagen.<br>Indtil nu: <b>${nf(pvD, 1)} kWh</b> produceret mod <b>${nf(fcSaaLangt, 1)} kWh</b> forventet${afv !== null ? ` (<b style="color:${afv >= 0 ? C.ok : C.warn}">${afv >= 0 ? '+' : ''}${nf(afv)} %</b>)` : ''} · resten af dagen ca. <b>${nf(rest, 1)} kWh</b>.</p>`;
      h += `<div class="grid g21">${this.card('Solproduktion i dag', ch + this.legend([['Målt produktion', C.sol], ['Prognose', '#a78bfa']]) + forkl, {icon: 'mdi:chart-bell-curve'})}${this.card('Næste dage', nd, {icon: 'mdi:calendar-range'})}</div>`;
      return h;
    }

  }
  const pdFmt = d => `${d.getDate()}. ${MDK[d.getMonth()]}. ${d.getFullYear()}`;
  const isoUge = d => { const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())); const dn = t.getUTCDay() || 7; t.setUTCDate(t.getUTCDate() + 4 - dn);
    const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1)); return Math.ceil(((t - y0) / 864e5 + 1) / 7); };

  const CSS = `
  :host{display:block;min-height:100vh;background:radial-gradient(1200px 600px at 10% -10%,rgba(34,211,238,.13),transparent 60%),radial-gradient(900px 500px at 110% 10%,rgba(167,139,250,.14),transparent 60%),
      repeating-linear-gradient(0deg,rgba(125,211,252,.035) 0 1px,transparent 1px 42px),repeating-linear-gradient(90deg,rgba(125,211,252,.035) 0 1px,transparent 1px 42px),#060c19}
  .app{container:app/inline-size;--r:18px;--card-background-color:rgba(12,24,46,.72);--secondary-background-color:rgba(34,211,238,.06);--divider-color:rgba(125,211,252,.14);
    --primary-text-color:#e6f3ff;--secondary-text-color:#8ba6c4;--bg2:rgba(34,211,238,.07);color:#e6f3ff;
    font-family:var(--ha-font-family-body,Roboto,sans-serif);max-width:1560px;margin:0 auto;padding:10px 14px 48px;min-height:100vh}
  header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:8px 4px 18px;position:sticky;top:0;z-index:5;background:linear-gradient(#060c19 70%,transparent)}
  .brand{display:flex;align-items:center;gap:12px}.brand img{width:46px;height:46px;filter:drop-shadow(0 0 8px rgba(34,211,238,.6))}
  .brand b{display:block;font-size:21px;letter-spacing:.32em;font-weight:700;background:linear-gradient(90deg,#22d3ee,#a78bfa);-webkit-background-clip:text;background-clip:text;color:transparent}
  .brand span{color:var(--secondary-text-color);font-size:11px;letter-spacing:.18em;text-transform:uppercase}
  nav{display:flex;gap:4px;flex-wrap:wrap;background:rgba(10,20,40,.8);padding:5px;border-radius:14px;border:1px solid var(--divider-color);box-shadow:0 0 24px rgba(34,211,238,.08)}
  nav button,.seg button,.lnk,.alert button,.ovb button,.ovc button,.stp button,.sw{border:0;background:transparent;color:inherit;font:inherit;cursor:pointer;border-radius:10px}
  nav button{display:flex;align-items:center;gap:6px;padding:8px 14px;font-size:13px;font-weight:600;letter-spacing:.04em;color:#a9c3df;transition:.2s}
  nav button ha-icon{--mdc-icon-size:18px}nav button:hover{background:rgba(34,211,238,.08);color:#fff}
  nav button.on{background:linear-gradient(135deg,rgba(34,211,238,.25),rgba(167,139,250,.25));color:#fff;box-shadow:inset 0 0 0 1px rgba(34,211,238,.5),0 0 16px rgba(34,211,238,.25)}
  .alert{background:rgba(251,113,133,.12);color:${C.err};border:1px solid rgba(251,113,133,.4);padding:10px 14px;border-radius:12px;margin-bottom:12px;display:flex;gap:8px;align-items:center}
  .alert.warn{background:rgba(251,146,60,.12);color:${C.warn};border-color:rgba(251,146,60,.4)}
  .grid{display:grid;gap:16px;margin-bottom:16px}.g2{grid-template-columns:repeat(2,minmax(0,1fr))}.g21{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}
  .g3{grid-template-columns:repeat(3,minmax(0,1fr))}.g2s{grid-template-columns:1fr 1fr;margin:0}.stack{display:flex;flex-direction:column;gap:16px}
  .kpis{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}.kpis4{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
  .card,.kpi{position:relative;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:var(--r);backdrop-filter:blur(6px);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 10px 30px rgba(0,0,0,.25)}
  .card::before,.kpi::before{content:'';position:absolute;inset:-1px;border-radius:inherit;pointer-events:none;padding:1px;
    background:linear-gradient(135deg,rgba(34,211,238,.55),transparent 28%,transparent 72%,rgba(167,139,250,.5));-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude}
  .card{padding:16px 18px;min-width:0}
  .ch{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap}
  .ch h3{margin:0;font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;display:flex;align-items:center;gap:8px;color:#bfe9f5}
  .ch h3 ha-icon{--mdc-icon-size:18px;color:${C.cyan};filter:drop-shadow(0 0 4px ${C.cyan})}.cr{display:flex;gap:6px;align-items:center}
  .kpi{padding:16px 18px 0;display:flex;flex-direction:column;justify-content:space-between;min-height:118px;overflow:hidden;transition:transform .15s}
  .kpi.click{cursor:pointer}.kpi.click:hover,.click:hover{transform:translateY(-2px)}
  .kt{display:flex;justify-content:space-between;gap:8px}.kv{font-size:25px;font-weight:700;letter-spacing:-.3px;color:#fff;text-shadow:0 0 14px rgba(34,211,238,.35)}
  .kl{color:var(--secondary-text-color);font-size:12px;margin-top:4px;letter-spacing:.05em}
  .ki{width:44px;height:44px;border-radius:12px;display:grid;place-items:center;flex:none;box-shadow:inset 0 0 0 1px currentColor}.ki.sm{width:36px;height:36px;border-radius:10px}
  .ks{color:var(--secondary-text-color);font-size:12px;margin:8px 0 10px}.kb{height:4px;background:rgba(255,255,255,.06);margin:0 -18px}.kb i{display:block;height:100%;box-shadow:0 0 10px currentColor}
  .kpi:not(:has(.kb)){padding-bottom:16px}
  .chart{width:100%;height:auto;display:block}.chart .grid{stroke:var(--divider-color);stroke-width:1}
  .chart .ax{fill:var(--secondary-text-color);font-size:12px}.chart .tag{fill:#fff;font-size:11px}.chart .hl{fill:rgba(34,211,238,.08)}
  .legend{display:flex;gap:16px;justify-content:center;flex-wrap:wrap;font-size:12px;margin-top:8px;color:var(--secondary-text-color)}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;box-shadow:0 0 6px currentColor}
  .donut{width:170px;height:170px}.donut .dv{font-size:17px;font-weight:700;fill:#fff}.donut .ds{font-size:9px;fill:var(--secondary-text-color)}
  .center{display:flex;justify-content:center}
  .flow{width:100%;max-width:860px;display:block;margin:0 auto}.flow .nv{font-size:17px;font-weight:700}.flow .nk{font-size:10px;font-weight:700;letter-spacing:.14em}
  .flow .ns{fill:var(--secondary-text-color);font-size:11px}.flow .ex{font-size:11px}.flow .exb{font-size:13px;font-weight:700}.flow .fb{fill:none;stroke:rgba(125,211,252,.10);stroke-width:2;stroke-dasharray:2 6}
  .flow .fa{fill:none;stroke-linecap:round;opacity:.9}.flow .fl text{font-size:12px;font-weight:700}
  .flow .spin{transform-box:fill-box;transform-origin:center;animation:spin 18s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
  .flowfoot{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:6px;flex-wrap:wrap}
  .fl2{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}.fl2 li{display:flex;align-items:center;gap:6px;background:rgba(34,211,238,.06);border:1px solid var(--divider-color);border-radius:20px;padding:4px 10px;font-size:12px}
  .fl2 i{width:8px;height:8px;border-radius:50%;box-shadow:0 0 6px currentColor}.fl2 b{margin-left:4px}
  .aut{text-align:right}.aut b{display:block;font-size:22px;color:${C.cyan};text-shadow:0 0 12px ${C.cyan}}.aut span{font-size:11px;color:var(--secondary-text-color);letter-spacing:.1em;text-transform:uppercase}
  .pill{font-size:11px;padding:3px 10px;border-radius:20px;font-weight:700;letter-spacing:.06em}.pill.ok{background:rgba(74,222,128,.12);color:${C.ok}}.pill.err{background:rgba(251,113,133,.14);color:${C.err}}
  .lnk{color:${C.cyan};font-weight:700;padding:5px 10px;text-decoration:none;font-size:13px}.lnk:hover{background:rgba(34,211,238,.1)}.lnk[disabled]{opacity:.3;pointer-events:none}
  .prices{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.prices.big{grid-template-columns:repeat(3,1fr);margin-bottom:12px}
  .prices>div{background:rgba(34,211,238,.05);border:1px solid var(--divider-color);border-radius:12px;padding:10px;text-align:center}.prices span{display:block;font-size:11px;color:var(--secondary-text-color);letter-spacing:.06em}
  .prices b{display:block;font-size:22px;margin:4px 0;text-shadow:0 0 12px currentColor}.prices small{color:var(--secondary-text-color);font-size:11px}
  .toolbar{display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap}.muted{color:var(--secondary-text-color);font-size:12px;letter-spacing:.04em}
  .seg{display:inline-flex;background:rgba(10,20,40,.7);border:1px solid var(--divider-color);border-radius:12px;padding:3px;flex-wrap:wrap}
  .seg button{padding:6px 12px;font-size:12px;font-weight:600;color:#a9c3df}.seg button.on{background:linear-gradient(135deg,rgba(34,211,238,.3),rgba(167,139,250,.3));color:#fff}
  .tbl{width:100%;border-collapse:collapse;font-size:13px}.tbl th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--secondary-text-color);font-weight:700;padding:8px;border-bottom:1px solid var(--divider-color);background:rgba(34,211,238,.05)}
  .tbl td{padding:8px;border-bottom:1px solid var(--divider-color)}.cell{display:inline-block;color:#06101f;font-weight:700;padding:4px 10px;border-radius:8px;min-width:90px}
  .note{color:var(--secondary-text-color);font-size:12px;line-height:1.55;margin:10px 0 0}
.sover{display:flex;gap:14px;align-items:center;padding:14px;border-radius:14px;background:rgba(148,163,184,.08)}
.sover ha-icon{--mdc-icon-size:30px;color:#a78bfa;flex:none}.sover.warn ha-icon{color:${C.warn}}
.sover b{display:block;margin-bottom:3px}.sover span{color:var(--secondary-text-color);font-size:13px;line-height:1.5}
  .ins,.rek,.plc,.ml,.logl{list-style:none;margin:0;padding:0}
  .ins li{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--divider-color)}.ins li:last-child{border:0}.ins b{display:block;font-size:14px}.ins span{color:var(--secondary-text-color);font-size:13px}
  .rek li{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid var(--divider-color)}.rek li>div:nth-child(2){flex:1}.rek b{display:block;font-size:14px}.rek span{font-size:12px;color:var(--secondary-text-color)}.rek em{font-style:normal;font-weight:700}
  .sub{font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:${C.cyan};margin:10px 0 4px}
  .plc li{display:flex;align-items:center;gap:10px;padding:8px 4px;border-radius:8px}.plc li em{margin-left:auto;font-style:normal;font-weight:700}
  .rank{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:700;background:rgba(255,255,255,.08)}.rank.r0{background:#fbbf24;color:#3b2500}.rank.r1{background:#cbd5e1;color:#1e293b}.rank.r2{background:#fb923c;color:#3b1500}
  .ml li{display:grid;grid-template-columns:1fr auto auto 20px;gap:12px;align-items:center;padding:11px 6px;border-bottom:1px solid var(--divider-color);border-radius:8px}.ml li.on,.ml li:hover,.plc li.click:hover{background:rgba(34,211,238,.07)}
  .click{cursor:pointer}
  .plist{display:flex;flex-direction:column;gap:2px}.prow{display:grid;grid-template-columns:28px 74px 1fr 44px;gap:10px;align-items:center;padding:5px 8px;border-radius:8px;font-size:13px}
  .prow.now{background:rgba(34,211,238,.1);outline:1px solid ${C.cyan};box-shadow:0 0 12px rgba(34,211,238,.25)}.pb{height:8px;background:rgba(255,255,255,.06);border-radius:4px;overflow:hidden}.pb i{display:block;height:100%;border-radius:4px}
  .t{font-size:10px;text-align:center;border-radius:6px;padding:1px 4px}.t.lav{background:rgba(74,222,128,.14);color:${C.lav}}.t.hoej{background:rgba(251,146,60,.14);color:${C.hoej}}.t.spids{background:rgba(251,113,133,.14);color:${C.spids}}
  .hbars{display:flex;flex-direction:column;gap:8px}.hb{display:grid;grid-template-columns:90px 1fr;gap:10px;align-items:center;font-size:13px}
  .hb>div{background:rgba(255,255,255,.05);border-radius:6px;overflow:hidden}.hb i{display:block;color:#06101f;font-style:normal;font-weight:700;font-size:12px;padding:5px 8px;border-radius:6px;white-space:nowrap}
  .isodato{display:flex;gap:12px;align-items:center;background:rgba(34,211,238,.06);border:1px solid var(--divider-color);border-radius:12px;padding:12px}.isodato ha-icon{--mdc-icon-size:30px;color:${C.cyan}}.isodato b{display:block}.isodato span{font-size:12px;color:var(--secondary-text-color)}
  .loading{padding:40px;text-align:center;color:var(--secondary-text-color)}
  .hero{display:flex;align-items:center;gap:18px;padding:18px 20px;border-radius:var(--r);margin-bottom:16px;border:1px solid rgba(34,211,238,.35);
    background:linear-gradient(120deg,rgba(34,211,238,.14),rgba(167,139,250,.12));box-shadow:0 0 30px rgba(34,211,238,.12)}
  .hero.off{border-color:rgba(251,113,133,.4);background:linear-gradient(120deg,rgba(251,113,133,.12),rgba(30,41,59,.4))}
  .hero img{width:64px;height:64px;filter:drop-shadow(0 0 12px rgba(34,211,238,.7));animation:pulse 3s ease-in-out infinite}@keyframes pulse{50%{filter:drop-shadow(0 0 22px rgba(167,139,250,.9))}}
  .hero>div{flex:1}.hero small{font-size:11px;letter-spacing:.24em;color:${C.cyan}}.hero h2{margin:4px 0;font-size:22px;color:#fff}.hero span{font-size:12px;color:var(--secondary-text-color)}
  .hero>div.hbtn{flex:0 0 auto;display:flex;flex-direction:column;align-items:flex-end;gap:6px}.hbtn .lnk{white-space:nowrap}
  .ovb{display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:14px;margin-bottom:16px;background:rgba(251,146,60,.12);border:1px solid rgba(251,146,60,.5);box-shadow:0 0 20px rgba(251,146,60,.15)}
  .ovb ha-icon{color:${C.warn};--mdc-icon-size:26px}.ovb div{flex:1}.ovb b{display:block}.ovb span{font-size:12px;color:var(--secondary-text-color)}
  .ovb button,.ovc button{padding:8px 16px;font-weight:700;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18)}
  .ovg{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
  .ovc{display:flex;flex-direction:column;gap:8px;padding:14px;border-radius:14px;background:rgba(255,255,255,.03);border:1px solid var(--divider-color);transition:.2s}
  .ovc:hover{border-color:var(--c);box-shadow:0 0 18px color-mix(in srgb,var(--c) 30%,transparent)}
  .ovc.on{border-color:var(--c);background:color-mix(in srgb,var(--c) 14%,transparent);box-shadow:0 0 22px color-mix(in srgb,var(--c) 35%,transparent)}
  .ovh{display:flex;align-items:center;gap:8px}.ovh ha-icon{color:var(--c);filter:drop-shadow(0 0 5px var(--c))}.ovc p{margin:0;font-size:12px;color:var(--secondary-text-color);line-height:1.5;flex:1}
  .ovc button{align-self:flex-start;color:var(--c);border-color:var(--c)}.ovc.on button{background:var(--c);color:#06101f}
  .set{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:11px 0;border-bottom:1px solid var(--divider-color)}.set:last-child{border:0}
  .set b{display:block;font-size:14px}.set span{font-size:12px;color:var(--secondary-text-color)}
  .stp{display:flex;align-items:center;gap:6px;flex:none}.stp button{width:32px;height:32px;font-size:18px;background:rgba(34,211,238,.1);border:1px solid var(--divider-color)}.stp em{font-style:normal;font-weight:700;min-width:86px;text-align:center;color:#fff}
  .sw{width:46px;height:26px;border-radius:13px;background:rgba(255,255,255,.12);position:relative;flex:none}.sw i{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#cbd5e1;transition:.2s}
  .sw.on{background:rgba(34,211,238,.45);box-shadow:0 0 12px rgba(34,211,238,.4)}.sw.on i{left:23px;background:#fff}
  .logl li{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid var(--divider-color);font-size:13px}.logl li span{color:var(--secondary-text-color);min-width:82px;font-size:12px}
  .g2i{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:22px}
  .act{margin-top:12px;border:1px solid ${C.cyan};background:linear-gradient(135deg,rgba(34,211,238,.25),rgba(167,139,250,.25));color:#fff;font:inherit;font-weight:700;padding:9px 18px;border-radius:10px;cursor:pointer;box-shadow:0 0 14px rgba(34,211,238,.25)}
  .act[disabled]{opacity:.5;cursor:default}
  .cmp{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px}.cmp>div{border:1px solid var(--divider-color);border-radius:12px;padding:10px;text-align:center;background:rgba(34,211,238,.04)}
  .cmp span{display:block;font-size:11px;color:var(--secondary-text-color);letter-spacing:.06em}.cmp b{font-size:20px}
  .inp{background:rgba(10,20,40,.8);border:1px solid var(--divider-color);color:#fff;border-radius:8px;padding:7px 10px;font:inherit;min-width:190px}
  .inp:focus{outline:1px solid ${C.cyan}}.sw[disabled]{opacity:.35;cursor:default}
  .brand .swap{margin-left:14px;border:1px solid var(--divider-color);border-radius:20px}
  .regler{display:flex;flex-direction:column;gap:8px}.regel{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:10px;border:1px solid var(--divider-color);border-radius:12px;background:rgba(255,255,255,.02)}
  .regel.on{border-color:rgba(34,211,238,.5);background:rgba(34,211,238,.06)}.regel .nm{min-width:150px;flex:1}.regel .tm{min-width:0;width:100px}.regel .del{color:${C.err}}
  select.inp{min-width:0}.chips{display:flex;flex-wrap:wrap;gap:6px}
  .alarm{list-style:none;margin:0;padding:0}.alarm li{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--divider-color)}.alarm li.bad b{color:${C.err}}.alarm span{display:block;font-size:12px;color:var(--secondary-text-color)}
  .tk td:first-child{color:var(--secondary-text-color)}.tk td{font-variant-numeric:tabular-nums}.tk small{color:var(--secondary-text-color)}
  .tk td.ok{color:${C.ok}}.tk td.warn{color:${C.warn}}.tk td.bad{color:${C.err};font-weight:700}
  .mppts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:10px}
  .mppt{border:1px solid var(--divider-color);border-radius:12px;padding:12px;background:rgba(251,191,36,.05)}.mh{font-size:11px;letter-spacing:.14em;color:${C.sol};font-weight:700}
  .mv{font-size:24px;font-weight:700;color:#fff;text-shadow:0 0 12px rgba(251,191,36,.4)}.ms{display:flex;gap:12px;font-size:13px}
  .plan-host{min-height:200px}
  @container app (max-width:1100px){.g2i{grid-template-columns:1fr}.g21,.g3{grid-template-columns:1fr}}
  @container app (max-width:800px){.g2{grid-template-columns:1fr}nav button span{display:none}nav button{padding:9px 12px}.prices{grid-template-columns:repeat(2,1fr)}header{position:static}.hero{flex-wrap:wrap}}
  @container app (max-width:480px){.fl2{display:none}.aut{text-align:left}.aut b{font-size:15px;display:inline;margin-right:6px}.aut span{font-size:10px}.flowfoot{margin-top:0}.card:has(.flow){padding:12px 4px}.flow{margin:0 -6px;width:calc(100% + 12px);max-width:none}.cmp b{font-size:16px}.inp{min-width:0;width:150px}.kpis,.kpis4{grid-template-columns:1fr 1fr;gap:10px}.kpi{padding:12px 12px 0;min-height:96px}.kpi .ki{width:34px;height:34px}.kb{margin:0 -12px}.ks{margin:6px 0 8px}.g2s{grid-template-columns:1fr}.app{padding:4px 6px 30px}.kv{font-size:20px}.prow{grid-template-columns:24px 64px 1fr 40px}.brand b{font-size:17px}}`;

  if (!customElements.get('energi-app-card')) customElements.define('energi-app-card', EnergiAppCard);
  window.customCards = window.customCards || [];
  window.customCards.push({type: 'energi-app-card', name: 'Wattlas', description: 'Wattlas energi-app'});
  console.info('%c ENERGI-APP ' + VERSION, 'background:#3b82f6;color:#fff;padding:2px 6px;border-radius:4px');
})();
