// EMHASS-planens logik – hvad planen bygger på, hvorfor den gør som den gør, og automatiske tjek.
// Læser kun: sensor.p_batt/p_load/p_pv/p_grid_forecast, soc_batt_forecast, unit_load_cost, unit_prod_price, planvalg.
// Parametrene nedenfor er de samme, som script.emhass_test_helios sender til EMHASS (emhass_forbindelse.yaml).
(() => {
  const VERSION = '1.2.0';
  // Tab er faste; batteri, reserve, slut-SOC, slid og net-loft læses fra Wattlas-indstillingerne (wattlas_styring.yaml)
  const P = {cap: 0, minSoc: 15, slutSoc: 30, eff: 0.95, slid: 0.25, maxNet: 0};
  const C = {sol: '#ffb547', net: '#a78bfa', hus: '#38bdf8', bat: '#34d399', ok: '#22c55e', warn: '#f59e0b', err: '#ef4444', mut: '#64748b', blue: '#3b82f6', salg: '#f472b6'};
  const nf = (v, d = 0) => v === null || v === undefined || isNaN(v) ? '–' : Number(v).toLocaleString('da-DK', {minimumFractionDigits: d, maximumFractionDigits: d});
  const kr = (v, d = 2) => nf(v, d) + ' kr.';
  const hm = t => { const d = new Date(t); return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); };
  const dag = t => { const d = new Date(t), n = new Date(); const dd = Math.round((new Date(d.toDateString()) - new Date(n.toDateString())) / 864e5);
    return dd === 0 ? 'i dag' : dd === 1 ? 'i morgen' : ['søn', 'man', 'tir', 'ons', 'tor', 'fre', 'lør'][d.getDay()]; };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const avg = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
  const RT = P.eff * P.eff; // tab ind og ud

  class EmhassPlanCard extends HTMLElement {
    constructor() { super(); this.attachShadow({mode: 'open'}); this._last = 0; this._open = false;
      this.shadowRoot.addEventListener('click', e => { const t = e.target.closest('[data-a]'); if (t && t.dataset.a === 'tabel') { this._open = !this._open; this._last = 0; this._render(); } }); }
    setConfig(c) { this._cfg = c || {}; }
    getCardSize() { return 14; }
    getGridOptions() { return {columns: 'full', rows: 'auto'}; }
    set hass(h) { this._hass = h; if (Date.now() - this._last > 10000) { this._last = Date.now(); this._render(); } }
    a(id, k) { return this._hass.states[id]?.attributes?.[k]; }
    n(id) { const v = parseFloat(this._hass.states[id]?.state); return isNaN(v) ? null : v; }
    w(f) { const cw = this.clientWidth || 1100; return Math.max(320, f === 'half' && cw >= 900 ? (cw - 40) / 2 - 40 : cw - 64); }

    params() { const v = (id, d) => { const x = parseFloat(this._hass.states[id]?.state); return isNaN(x) ? d : x; };
      P.minSoc = Math.max(15, v('input_number.wattlas_reserve', 15)); P.slutSoc = Math.max(P.minSoc, v('input_number.wattlas_slut_soc', 30));
      P.slid = v('input_number.wattlas_slid', 0.25); P.cap = v('input_number.wattlas_batteri_kwh', 0);
      P.maxNet = Math.min(v('input_number.wattlas_maks_netimport_w', 0) / 1000, v('input_number.wattlas_max_net_kw', 0)) * 1000; }
    slots() {
      const m = new Map(), put = (id, attr, key, f) => (this.a(id, attr) || []).forEach(r => {
        const t = new Date(r.date).getTime(), v = parseFloat(r[key]); if (isNaN(t) || isNaN(v)) return;
        const o = m.get(t) || {t}; o[f] = v; m.set(t, o); });
      put('sensor.p_batt_forecast', 'battery_scheduled_power', 'p_batt_forecast', 'b');
      put('sensor.p_load_forecast', 'forecasts', 'p_load_forecast', 'l');
      put('sensor.p_pv_forecast', 'forecasts', 'p_pv_forecast', 'pv');
      put('sensor.p_grid_forecast', 'forecasts', 'p_grid_forecast', 'g');
      put('sensor.soc_batt_forecast', 'battery_scheduled_soc', 'soc_batt_forecast', 'soc');
      put('sensor.unit_load_cost', 'unit_load_cost_forecasts', 'unit_load_cost', 'buy');
      put('sensor.unit_prod_price', 'unit_prod_price_forecasts', 'unit_prod_price', 'sell');
      const now = Date.now();
      return [...m.values()].filter(s => s.t + 1800e3 > now && s.b !== undefined).sort((a, b) => a.t - b.t).map(s => {
        const b = s.b || 0, g = s.g || 0;
        s.akt = b < -150 ? (g > 150 && g > (s.l || 0) + 150 ? 'netlad' : 'sollad') : b > 150 ? 'aflad' : 'hvile';
        if (g < -150) s.salg = true;
        return s; });
    }

    _render() {
      if (!this._hass) return;
      let body;
      try { body = this.side(); } catch (e) { body = `<div class="card">Fejl: ${esc(e.message)}</div>`; console.error(e); }
      this.shadowRoot.innerHTML = `<style>${CSS}</style><div class="app">${body}</div>`;
    }

    side() {
      this.params(); const S = this.slots();
      if (!S.length) return `<div class="card">Der er ingen aktuel plan fra EMHASS lige nu.</div>`;
      const h = 0.5, kwh = w => w * h / 1000;
      const gen = this.a('sensor.emhass_planvalg', 'generated'), alder = this.a('sensor.emhass_planvalg', 'age_minutes');
      const status = this._hass.states['sensor.optim_status']?.state, mode = this._hass.states['sensor.emhass_planvalg']?.state;
      const sum = f => S.reduce((a, s) => a + f(s), 0);
      const pvK = sum(s => kwh(s.pv || 0)), lK = sum(s => kwh(s.l || 0));
      const impK = sum(s => kwh(Math.max(0, s.g || 0))), expK = sum(s => kwh(Math.max(0, -(s.g || 0))));
      const impKr = sum(s => kwh(Math.max(0, s.g || 0)) * (s.buy || 0)), expKr = sum(s => kwh(Math.max(0, -(s.g || 0))) * (s.sell || 0));
      const disK = sum(s => kwh(Math.max(0, s.b || 0))), chK = sum(s => kwh(Math.max(0, -(s.b || 0))));
      const udenKr = sum(s => { const r = (s.l || 0) - (s.pv || 0); return r > 0 ? kwh(r) * (s.buy || 0) : -kwh(-r) * (s.sell || 0); });
      const medKr = impKr - expKr + disK * P.slid;
      const socs = S.map(s => s.soc).filter(v => v !== undefined), socMin = Math.min(...socs), socSlut = socs[socs.length - 1];
      const buys = S.map(s => s.buy).filter(v => v !== undefined);
      const t0 = S[0].t, t1 = S[S.length - 1].t + 1800e3;

      // ---- segmenter (sammenhængende halvtimer med samme handling)
      const seg = []; S.forEach(s => { const l = seg[seg.length - 1]; if (l && l.akt === s.akt) l.s.push(s); else seg.push({akt: s.akt, s: [s]}); });
      const navn = {netlad: 'Lader fra elnettet', sollad: 'Lader fra solen', aflad: 'Batteriet forsyner huset', hvile: 'Batteriet hviler'};
      const ikon = {netlad: 'mdi:transmission-tower-import', sollad: 'mdi:solar-power-variant', aflad: 'mdi:home-lightning-bolt', hvile: 'mdi:pause-circle-outline'};
      const farve = {netlad: C.net, sollad: C.sol, aflad: C.bat, hvile: C.mut};
      // batteriets pris pr. kWh leveret: senest netladede strøm (eller 0 hvis sol) / tab + slid
      const netLad = seg.filter(x => x.akt === 'netlad');
      const ladePris = x => avg(x.s.map(s => s.buy));
      const forklar = (x, i) => {
        const p = avg(x.s.map(s => s.buy)), e = x.s.reduce((a, s) => a + kwh(Math.abs(s.b || 0)), 0);
        const senere = seg.slice(i + 1).filter(y => y.akt === 'aflad'), tidl = seg.slice(0, i).filter(y => y.akt === 'netlad');
        if (x.akt === 'netlad') {
          const brug = senere[0], bp = brug ? avg(brug.s.map(s => s.buy)) : null, kost = p / RT + P.slid;
          return `Køber ${nf(e, 1)} kWh til gns. <b>${kr(p)}</b>. Efter tab ind og ud (×${nf(1 / RT, 2)}) og slid (${kr(P.slid)}) koster strømmen <b>${kr(kost)}</b> pr. kWh, når den bruges.` +
            (bp !== null ? ` Den bruges ${dag(brug.s[0].t)} kl. ${hm(brug.s[0].t)}–${hm(brug.s[brug.s.length - 1].t + 1800e3)}, hvor strømmen koster gns. <b>${kr(bp)}</b> → <b style="color:${bp - kost > 0 ? C.ok : C.err}">${bp - kost > 0 ? 'gevinst' : 'tab'} ${kr(Math.abs(bp - kost))} pr. kWh</b>.`
              : ' Strømmen gemmes til efter planens horisont (eller til slut-SOC på 30 %).');
        }
        if (x.akt === 'sollad') return `Overskudssol (${nf(e, 1)} kWh) gemmes i batteriet i stedet for at sælges til gns. ${kr(avg(x.s.map(s => s.sell)))}. Den er mere værd senere, hvor strømmen koster ${kr(Math.max(...S.map(s => s.buy || 0)))} på det dyreste.`;
        if (x.akt === 'aflad') {
          const kilde = tidl.length ? ladePris(tidl[tidl.length - 1]) / RT + P.slid : null;
          return `Strømmen koster gns. <b>${kr(p)}</b> fra elnettet. Batteriet leverer ${nf(e, 1)} kWh i stedet` +
            (kilde !== null ? ` til ca. <b>${kr(kilde)}</b> pr. kWh (netladet strøm inkl. tab og slid) → sparer <b style="color:${C.ok}">${kr(p - kilde)}</b> pr. kWh.` : ` – strømmen i batteriet er allerede betalt (eller sol), så kun slid på ${kr(P.slid)} tæller.`);
        }
        const næste = senere[0];
        return `Prisen (gns. ${kr(p)}) er ikke høj nok til, at det betaler sig at bruge batteriet nu` + (næste ? ` – strømmen gemmes til ${dag(næste.s[0].t)} kl. ${hm(næste.s[0].t)}, hvor den er dyrere.` : '.');
      };
      const segHtml = seg.map((x, i) => `<li><div class="si" style="background:${farve[x.akt]}22;color:${farve[x.akt]}"><ha-icon icon="${ikon[x.akt]}"></ha-icon></div>
        <div><div class="sh"><b>${navn[x.akt]}</b><span>${dag(x.s[0].t)} ${hm(x.s[0].t)}–${hm(x.s[x.s.length - 1].t + 1800e3)} · SOC ${nf(x.s[0].soc)} → ${nf(x.s[x.s.length - 1].soc)} %</span></div>
        <p>${forklar(x, i)}</p></div></li>`).join('');

      // ---- tjek
      const tjek = [];
      tjek.push([socMin >= P.minSoc - 0.5, `Batteriet går aldrig under reserven på ${P.minSoc} %`, `laveste niveau i planen: ${nf(socMin)} %`]);
      tjek.push([socSlut >= P.slutSoc - 0.5, `Planen slutter med mindst ${P.slutSoc} % i batteriet`, `slutter på ${nf(socSlut)} % kl. ${hm(t1)}`]);
      const maxG = Math.max(...S.map(s => s.g || 0));
      tjek.push([maxG <= P.maxNet + 50, `Køb fra elnettet holder sig under ${nf(P.maxNet / 1000, 0)} kW (sikringerne)`, `højeste: ${nf(maxG / 1000, 1)} kW`]);
      const betaler = netLad.map(x => { const i = seg.indexOf(x), brug = seg.slice(i + 1).find(y => y.akt === 'aflad'); return brug ? avg(brug.s.map(s => s.buy)) - (ladePris(x) / RT + P.slid) : null; }).filter(v => v !== null);
      tjek.push([betaler.every(v => v > 0), 'Hver netopladning tjener sig hjem efter tab og slid', betaler.length ? `gevinst ${betaler.map(v => kr(v)).join(', ')} pr. kWh` : 'ingen netopladning med senere forbrug i planen']);
      // billigste timer valgt: ladetimer vs. de billigste timer før første afladning
      let billig = true, billigTxt = 'ingen netopladning';
      if (netLad.length) {
        const forsteAflad = S.find(s => s.akt === 'aflad' && s.t > netLad[0].s[0].t), vindue = S.filter(s => !forsteAflad || s.t < forsteAflad.t);
        // alle netladninger før næste forbrug tælles med; lille tolerance, da EMHASS spreder ladningen under netgrænsen
        const lad = vindue.filter(s => s.akt === 'netlad' && s.t >= netLad[0].s[0].t), n = lad.length;
        const graense = [...vindue.map(s => s.buy)].sort((a, b) => a - b)[n - 1], dyrest = Math.max(...lad.map(s => s.buy));
        billig = dyrest <= graense + Math.max(0.10, graense * 0.05);
        billigTxt = `${n} ladehalvtime${n === 1 ? '' : 'r'} koster op til ${kr(dyrest)} – de ${n} billigste halvtime${n === 1 ? '' : 'r'} før næste forbrug koster op til ${kr(graense)}` + (billig && dyrest > graense + 0.005 ? ' (inden for 10 øre/5 % – fx pga. grænsen for køb fra nettet)' : '');
      }
      tjek.push([billig, 'Netopladningen ligger i de billigste timer', billigTxt]);
      const solSalg = S.filter(s => s.salg && (s.soc || 0) < 97 && s.akt !== 'sollad');
      tjek.push([solSalg.length === 0, 'Solstrøm sælges først, når batteriet er fuldt', solSalg.length ? `${solSalg.length} halvtimer sælger, mens batteriet ikke lader` : 'intet salg før batteriet er fuldt']);
      tjek.push([(alder ?? 99) < 12 && status === 'Optimal', 'Planen er frisk og matematisk optimal', `${status || '?'} · ${nf(alder, 0)} min gammel · ${mode || ''}`]);
      const okN = tjek.filter(x => x[0]).length;

      // ---- grafer
      const W = this.w('full');
      const effekt = this.effektGraf(S, W), pris = this.prisGraf(S, W);
      const top = `<div class="hero"><div><h2>Wattlas · planens logik</h2><p>EMHASS har beregnet de næste <b>${S.length / 2} timer</b> (${dag(t0)} ${hm(t0)} → ${dag(t1)} ${hm(t1)}). Beregnet kl. ${gen ? hm(gen * 1000) : '–'} · ${nf(alder, 0)} min siden · status <b>${esc(status || '?')}</b>.</p></div>
        <div class="score ${okN === tjek.length ? 'ok' : 'warn'}"><b>${okN}/${tjek.length}</b><span>tjek bestået</span></div></div>`;
      const kpi = (t, v, sub, c, i) => `<div class="kpi"><div class="ki" style="background:${c}22;color:${c}"><ha-icon icon="${i}"></ha-icon></div><div><div class="kv">${v}</div><div class="kl">${t}</div><div class="ks">${sub}</div></div></div>`;
      const kpis = `<div class="kpis">
        ${kpi('Forventet regning', kr(medKr, 0), `uden batteri ${kr(udenKr, 0)} → sparer ${kr(udenKr - medKr, 0)}`, C.ok, 'mdi:cash-check')}
        ${kpi('Køb fra elnettet', nf(impK, 1) + ' kWh', `${kr(impKr, 0)} · gns. ${kr(impK ? impKr / impK : null)}`, C.net, 'mdi:transmission-tower-import')}
        ${kpi('Sol i perioden', nf(pvK, 1) + ' kWh', `husforbrug ${nf(lK, 1)} kWh`, C.sol, 'mdi:white-balance-sunny')}
        ${kpi('Batteri', `${nf(chK, 1)} / ${nf(disK, 1)} kWh`, `lades / aflades · slid ${kr(disK * P.slid, 0)}`, C.bat, 'mdi:battery-sync')}
        ${kpi('Batteriniveau', `${nf(S[0].soc)} → ${nf(socSlut)} %`, `laveste ${nf(socMin)} %`, C.hus, 'mdi:battery-heart-variant')}
        ${kpi('Elpris i perioden', `${nf(Math.min(...buys), 2)}–${nf(Math.max(...buys), 2)}`, `kr./kWh · spænd ${kr(Math.max(...buys) - Math.min(...buys))}`, C.warn, 'mdi:currency-usd')}</div>`;
      const grundlag = `<table class="tbl kv2"><tbody>
        <tr><td>Hvad EMHASS minimerer</td><td>Samlet pris = køb fra nettet − salg + slid på batteriet (${kr(P.slid)} pr. afladet kWh), over hele horisonten</td></tr>
        <tr><td>Batteri</td><td>${nf(P.cap, 2)} kWh · må ikke under ${P.minSoc} % · skal slutte på mindst ${P.slutSoc} %</td></tr>
        <tr><td>Tab</td><td>${nf(P.eff * 100)} % ind og ${nf(P.eff * 100)} % ud → ${nf(RT * 100, 1)} % kommer tilbage</td></tr>
        <tr><td>Maks. effekt</td><td>lade ${nf(this.n('sensor.emhass_ui_plan_ladegraense_w') / 1000, 1)} kW · aflade ${nf(this.n('sensor.emhass_ui_afladegraense_w') / 1000, 1)} kW · fra nettet ${nf(P.maxNet / 1000, 0)} kW</td></tr>
        <tr><td>Salg fra batteri</td><td>Nej – batteriet sælger aldrig til nettet, kun overskudssol sælges</td></tr>
        <tr><td>Solprognose</td><td>Solprognose (Wattlas-indstilling) – ${nf(pvK, 1)} kWh i perioden</td></tr>
        <tr><td>Husprognose</td><td>Sidste 8 døgn halvtime for halvtime, justeret for udetemperatur – ${nf(lK, 1)} kWh</td></tr>
        <tr><td>Priser</td><td>Spotpris + nettarif (lav/høj/spids) + elafgift + moms (køb) · spot − gebyrer (salg)</td></tr>
        <tr><td>Genberegning</td><td>Hvert 5. minut med friske målinger · styringen følger planen hvert 30. sekund</td></tr></tbody></table>`;
      const rows = S.map(s => `<tr><td>${dag(s.t)} ${hm(s.t)}</td><td>${nf(s.buy, 2)}</td><td>${nf(s.sell, 2)}</td><td>${nf((s.pv || 0) / 1000, 1)}</td><td>${nf((s.l || 0) / 1000, 1)}</td>
        <td style="color:${(s.b || 0) < -150 ? C.net : (s.b || 0) > 150 ? C.bat : 'inherit'}">${nf(-(s.b || 0) / 1000, 1)}</td><td>${nf((s.g || 0) / 1000, 1)}</td><td>${nf(s.soc)} %</td>
        <td><span class="tag" style="background:${farve[s.akt]}33;color:${farve[s.akt]}">${navn[s.akt].replace('Batteriet ', '')}</span></td></tr>`).join('');
      const tabel = `<button class="lnk" data-a="tabel">${this._open ? 'Skjul' : 'Vis'} alle ${S.length} halvtimer ›</button>${this._open ? `<div class="scroll"><table class="tbl"><thead><tr><th>Tid</th><th>Køb kr.</th><th>Salg kr.</th><th>Sol kW</th><th>Hus kW</th><th>Batteri ind kW</th><th>Net kW</th><th>SOC</th><th>Handling</th></tr></thead><tbody>${rows}</tbody></table></div>` : ''}`;
      const card = (t, i, inner, x = '') => `<section class="card ${x}"><h3><ha-icon icon="${i}"></ha-icon>${t}</h3>${inner}</section>`;
      return top + kpis +
        card('Pris og batteriniveau', 'mdi:chart-bar', pris + this.legend([['Lader fra net', C.net], ['Lader fra sol', C.sol], ['Batteri forsyner', C.bat], ['Hviler', C.mut], ['Batteriniveau (højre akse)', C.hus]])) +
        card('Energi pr. halvtime', 'mdi:chart-timeline-variant', effekt + this.legend([['Sol', C.sol], ['Fra elnettet', C.net], ['Fra batteriet', C.bat], ['Ind i batteriet', '#7c3aed'], ['Solgt', C.salg], ['Husforbrug', C.hus]])) +
        `<div class="g2">${card('Hvorfor gør planen sådan?', 'mdi:head-question-outline', `<ul class="seg">${segHtml}</ul>`)}
        <div class="stack">${card('Tjek – er planen fornuftig?', 'mdi:clipboard-check-outline', `<ul class="chk">${tjek.map(([ok, t, d]) => `<li><ha-icon icon="${ok ? 'mdi:check-circle' : 'mdi:alert-circle'}" style="color:${ok ? C.ok : C.warn}"></ha-icon><div><b>${t}</b><span>${d}</span></div></li>`).join('')}</ul>`)}
        ${card('Det regner EMHASS ud fra', 'mdi:calculator-variant-outline', grundlag)}</div></div>` +
        card('Halvtime for halvtime', 'mdi:table', tabel);
    }

    legend(items) { return `<div class="legend">${items.map(([n, c]) => `<span><i style="background:${c}"></i>${n}</span>`).join('')}</div>`; }

    // søjler = købspris farvet efter handling, linje = SOC (højre akse 0-100 %)
    prisGraf(S, W) {
      const H = 280, L = 46, R = 44, T = 14, B = 30, n = S.length, bw = (W - L - R) / n;
      const mx = Math.ceil(Math.max(...S.map(s => s.buy || 0)) * 2) / 2 || 1;
      const y = v => T + (H - T - B) * (1 - v / mx), ys = v => T + (H - T - B) * (1 - v / 100);
      const f = {netlad: C.net, sollad: C.sol, aflad: C.bat, hvile: C.mut};
      let g = '';
      for (let k = 0; k <= 4; k++) { const v = mx * k / 4; g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="gl"/><text x="${L - 6}" y="${y(v) + 4}" class="ax" text-anchor="end">${nf(v, 1)}</text><text x="${W - R + 6}" y="${y(v) + 4}" class="ax">${nf(k * 25)}%</text>`; }
      g += `<line x1="${L}" x2="${W - R}" y1="${ys(P.minSoc)}" y2="${ys(P.minSoc)}" stroke="${C.err}" stroke-dasharray="3 4" stroke-width="1"/>`;
      const every = Math.max(1, Math.ceil(n * 44 / W));
      S.forEach((s, i) => { const x = L + i * bw, v = s.buy || 0;
        g += `<rect x="${x + 1}" y="${y(v)}" width="${Math.max(1, bw - 2)}" height="${H - B - y(v)}" rx="2" fill="${f[s.akt]}" opacity=".85"><title>${dag(s.t)} ${hm(s.t)}: køb ${kr(v)}, salg ${kr(s.sell)} · SOC ${nf(s.soc)} %</title></rect>`;
        if (i % every === 0) g += `<text x="${x + bw / 2}" y="${H - 10}" class="ax" text-anchor="middle">${hm(s.t)}</text>`;
        if (i && new Date(s.t).getHours() === 0 && new Date(s.t).getMinutes() === 0) g += `<line x1="${x}" x2="${x}" y1="${T}" y2="${H - B}" stroke="var(--secondary-text-color)" stroke-dasharray="2 3"/><text x="${x + 4}" y="${T + 10}" class="ax">${dag(s.t)}</text>`; });
      g += `<polyline points="${S.map((s, i) => `${L + i * bw + bw / 2},${ys(s.soc || 0)}`).join(' ')}" fill="none" stroke="${C.hus}" stroke-width="3" stroke-linejoin="round"/>`;
      const nuX = L + (Date.now() - S[0].t) / 1800e3 * bw;
      if (nuX >= L && nuX <= W - R) g += `<line x1="${nuX}" x2="${nuX}" y1="${T}" y2="${H - B}" stroke="#fff" stroke-width="1.5" stroke-dasharray="4 3" opacity=".8"/><text x="${nuX + 4}" y="${H - B - 6}" class="ax" fill="#fff">nu</text>`;
      g += `<text x="${L}" y="${T - 2}" class="ax">kr./kWh</text>`;
      return `<svg viewBox="0 0 ${W} ${H}" class="chart">${g}</svg>`;
    }

    // over nul: hvor strømmen kommer fra (sol, net, batteri). under nul: hvor den går hen ud over huset (batteri ind, salg)
    effektGraf(S, W) {
      const H = 300, L = 46, R = 14, T = 14, B = 30, n = S.length, bw = (W - L - R) / n;
      const op = S.map(s => [Math.min(s.pv || 0, (s.l || 0) + Math.max(0, -(s.b || 0)) + Math.max(0, -(s.g || 0))), Math.max(0, s.g || 0), Math.max(0, s.b || 0)]);
      const ned = S.map(s => [Math.max(0, -(s.b || 0)), Math.max(0, -(s.g || 0))]);
      const top = Math.max(...op.map(a => a[0] + a[1] + a[2]), ...S.map(s => s.l || 0), 1) / 1000, bund = Math.max(...ned.map(a => a[0] + a[1]), 0) / 1000;
      const mx = Math.ceil(top / 2) * 2, mn = -Math.ceil(bund / 2) * 2;
      const y = v => T + (H - T - B) * (1 - (v - mn) / ((mx - mn) || 1));
      let g = '';
      for (let k = 0; k <= 5; k++) { const v = mn + (mx - mn) * k / 5; g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="gl"/><text x="${L - 6}" y="${y(v) + 4}" class="ax" text-anchor="end">${nf(v, 0)}</text>`; }
      const every = Math.max(1, Math.ceil(n * 44 / W));
      S.forEach((s, i) => { const x = L + i * bw + 1, w = Math.max(1, bw - 2);
        let acc = 0; [[op[i][0], C.sol, 'sol'], [op[i][1], C.net, 'fra nettet'], [op[i][2], C.bat, 'fra batteriet']].forEach(([v, c, nm]) => { v /= 1000; if (v <= 0) return;
          g += `<rect x="${x}" y="${y(acc + v)}" width="${w}" height="${y(acc) - y(acc + v)}" fill="${c}"><title>${hm(s.t)} ${nm}: ${nf(v, 1)} kW</title></rect>`; acc += v; });
        acc = 0; [[ned[i][0], '#7c3aed', 'ind i batteriet'], [ned[i][1], C.salg, 'solgt']].forEach(([v, c, nm]) => { v /= 1000; if (v <= 0) return;
          g += `<rect x="${x}" y="${y(-acc)}" width="${w}" height="${y(-acc - v) - y(-acc)}" fill="${c}"><title>${hm(s.t)} ${nm}: ${nf(v, 1)} kW</title></rect>`; acc += v; });
        if (i % every === 0) g += `<text x="${x + bw / 2}" y="${H - 10}" class="ax" text-anchor="middle">${hm(s.t)}</text>`; });
      g += `<line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="var(--secondary-text-color)"/>`;
      g += `<polyline points="${S.map((s, i) => `${L + i * bw + bw / 2},${y((s.l || 0) / 1000)}`).join(' ')}" fill="none" stroke="${C.hus}" stroke-width="2.5" stroke-dasharray="5 3"/>`;
      const nuX = L + (Date.now() - S[0].t) / 1800e3 * bw;
      if (nuX >= L && nuX <= W - R) g += `<line x1="${nuX}" x2="${nuX}" y1="${T}" y2="${H - B}" stroke="#fff" stroke-width="1.5" stroke-dasharray="4 3" opacity=".8"/><text x="${nuX + 4}" y="${H - B - 6}" class="ax" fill="#fff">nu</text>`;
      g += `<text x="${L}" y="${T - 2}" class="ax">kW</text>`;
      return `<svg viewBox="0 0 ${W} ${H}" class="chart">${g}</svg>`;
    }
  }

  const CSS = `
  :host{display:block}.app{container:pl/inline-size;font-family:var(--ha-font-family-body,Roboto,sans-serif);color:var(--primary-text-color);max-width:1500px;margin:0 auto;padding:8px 12px 40px}
  .hero{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:4px 0 16px}.hero h2{margin:0 0 4px;font-size:24px}.hero p{margin:0;color:var(--secondary-text-color);font-size:14px}
  .score{border-radius:16px;padding:10px 18px;text-align:center;flex:none}.score b{display:block;font-size:26px}.score span{font-size:12px}
  .score.ok{background:#22c55e22;color:${C.ok}}.score.warn{background:#f59e0b22;color:${C.warn}}
  .kpis{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));margin-bottom:16px}
  .kpi{display:flex;gap:12px;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:16px;padding:14px}
  .ki{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;flex:none}.kv{font-size:20px;font-weight:700}.kl{font-size:13px;color:var(--secondary-text-color)}.ks{font-size:12px;color:var(--secondary-text-color);margin-top:4px}
  .card{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:16px;padding:16px 18px;margin-bottom:16px;min-width:0}
  .card h3{margin:0 0 12px;font-size:16px;display:flex;gap:8px;align-items:center}.card h3 ha-icon{--mdc-icon-size:20px;color:var(--secondary-text-color)}
  .g2{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:16px}.stack{display:flex;flex-direction:column}
  .chart{width:100%;height:auto;display:block}.gl{stroke:var(--divider-color)}.ax{fill:var(--secondary-text-color);font-size:12px}
  .legend{display:flex;gap:16px;flex-wrap:wrap;justify-content:center;font-size:13px;color:var(--secondary-text-color);margin-top:6px}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}
  ul{list-style:none;margin:0;padding:0}
  .seg li{display:flex;gap:12px;padding:12px 0;border-bottom:1px solid var(--divider-color)}.seg li:last-child{border:0}
  .si{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;flex:none}.sh b{display:block}.sh span{font-size:12px;color:var(--secondary-text-color)}
  .seg p{margin:6px 0 0;font-size:13px;line-height:1.55;color:var(--secondary-text-color)}.seg p b{color:var(--primary-text-color)}
  .chk li{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--divider-color)}.chk li:last-child{border:0}.chk b{display:block;font-size:14px}.chk span{font-size:12px;color:var(--secondary-text-color)}
  .tbl{width:100%;border-collapse:collapse;font-size:13px}.tbl th{text-align:left;font-size:12px;color:var(--secondary-text-color);padding:7px;background:var(--secondary-background-color);position:sticky;top:0}
  .tbl td{padding:7px;border-bottom:1px solid var(--divider-color)}.kv2 td:first-child{color:var(--secondary-text-color);width:34%;vertical-align:top}
  .tag{font-size:11px;padding:2px 8px;border-radius:8px;white-space:nowrap}.scroll{max-height:520px;overflow:auto;margin-top:10px}
  .lnk{border:0;background:var(--secondary-background-color);color:${C.blue};font:inherit;font-weight:600;padding:8px 14px;border-radius:10px;cursor:pointer}
  @container pl (max-width:900px){.g2{grid-template-columns:1fr}.hero{flex-direction:column;align-items:flex-start}}`;

  if (!customElements.get('emhass-plan-card')) customElements.define('emhass-plan-card', EmhassPlanCard);
  window.customCards = window.customCards || [];
  window.customCards.push({type: 'emhass-plan-card', name: 'EMHASS planens logik', description: 'Forklarer EMHASS-planen'});
  console.info('%c EMHASS-PLAN ' + VERSION, 'background:#34d399;color:#000;padding:2px 6px;border-radius:4px');
})();
