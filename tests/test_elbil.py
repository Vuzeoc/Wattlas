# Elbil: laderens effekt, holdet med efterløb, klemmen i reguleringen, husprognosen uden bilen og Konfigurer.
# Kør: python tests/test_elbil.py   (kræver: pip install homeassistant)
import asyncio, sqlite3, tempfile, time
from datetime import timedelta

from test_flow import REPO, fang_kald, ny_hass, opsaet
from homeassistant import bootstrap, config_entries, core, loader
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

PK = REPO / 'packages/wattlas'
LADER, LOAD, EFF, HOLD = 'sensor.min_lader_effekt', 'sensor.emhass_m_load_w_totalpower', 'sensor.wattlas_elbil_effekt', 'binary_sensor.wattlas_elbil_hold'
TIL = 'input_boolean.wattlas_elbil_hold'


async def main():
    hass = core.HomeAssistant(tempfile.mkdtemp())
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    assert await bootstrap.async_load_base_functionality(hass)
    hass.set_state(core.CoreState.running)
    f = load_yaml(str(PK / 'wattlas_elbil.yaml'))
    hold = f['template'][1]['binary_sensor'][0]
    assert hold['delay_on'] == {'seconds': 15} and hold['delay_off'] == {'minutes': 5}
    hold['delay_on'], hold['delay_off'] = {'milliseconds': 300}, {'milliseconds': 900}  # samme forløb, hurtigere
    for dom in ('input_text', 'input_boolean', 'template'):
        assert await async_setup_component(hass, dom, {dom: f[dom]}), dom
    await hass.async_block_till_done()
    v = lambda e: hass.states.get(e).state  # noqa: E731

    async def sæt(e, s, **attr):
        hass.states.async_set(e, str(s), attr)
        await hass.async_block_till_done()

    async def vælg(e):
        await hass.services.async_call('input_text', 'set_value', {'entity_id': 'input_text.wattlas_elbil_entitet', 'value': e}, blocking=True)
        await hass.async_block_till_done()

    async def lader(p, load, enhed='W'):
        await sæt(LADER, p, unit_of_measurement=enhed); await sæt(LOAD, load)
        return v(EFF)

    # --- laderens effekt ---
    await sæt(LOAD, 8000)
    await sæt(LADER, 7000, unit_of_measurement='W')
    assert v(EFF) == 'unavailable', 'ingen lader valgt'
    await vælg(LADER)
    assert float(v(EFF)) == 7000
    assert float(await lader(11, 12000, 'kW')) == 11000
    assert float(await lader(0, 600)) == 0 and float(await lader(-5000, 600)) == 0  # V2G: bilen forsyner huset
    assert float(await lader(11000, 5400)) == 0  # huset bruger under halvdelen: lader uden for målingen, eller sensoren hænger
    assert float(await lader(11000, 5500)) == 11000
    for tilstand, enhed in (('unavailable', 'W'), ('unknown', 'W'), ('Charging', 'W'), (7000, 'A'), (7000, None), (7000, 'MW')):
        assert await lader(tilstand, 9000, enhed) == 'unavailable', (tilstand, enhed)
    assert await lader(7000, 'unavailable') == 'unavailable'
    await sæt('input_number.lader', 7000, unit_of_measurement='W')
    await sæt(LOAD, 9000)
    for forkert in ('input_number.lader', 'switch.lader', 'sensor.findes_ikke', ''):
        await vælg(forkert)
        assert v(EFF) == 'unavailable', forkert
    await vælg(LADER)
    print('Laderens effekt (W, kW, uden for målingen, hængende sensor): OK')

    # --- holdet ---
    async def vent(s):
        await asyncio.sleep(s)
        await hass.async_block_till_done()
    await lader(7000, 8000); await vent(.5)
    assert v(HOLD) != 'on', 'slået fra som standard'
    await hass.services.async_call('input_boolean', 'turn_on', {'entity_id': TIL}, blocking=True)
    await hass.async_block_till_done()
    assert v(HOLD) != 'on', 'venter lidt'
    await vent(.6)
    assert v(HOLD) == 'on'
    await lader(0, 600); await vent(.3)
    assert v(HOLD) == 'on', 'en pause slipper ikke holdet'
    await lader(7000, 8000); await vent(1.2)
    assert v(HOLD) == 'on', 'pausen tæller ikke videre'
    await lader(400, 1000); await vent(1.3)
    assert v(HOLD) == 'off', 'standby er ikke ladning'
    await lader(7000, 8000); await vent(.6)
    assert v(HOLD) == 'on'
    await lader('unavailable', 8000); await vent(1.3)
    assert v(HOLD) == 'off', 'uden måling styres der som ellers'
    await lader(7000, 8000); await vent(.6)
    await hass.services.async_call('input_boolean', 'turn_off', {'entity_id': TIL}, blocking=True)
    await vent(1.3)
    assert v(HOLD) == 'off'
    print('Holdet med efterløb: OK')

    # --- klemmen i reguleringen ---
    def blokke(o):
        if isinstance(o, dict):
            if 'variables' in o: yield o['variables']
            for x in o.values(): yield from blokke(x)
        elif isinstance(o, list):
            for x in o: yield from blokke(x)
    alle = list(blokke(load_yaml(str(PK / 'emhass_forbindelse.yaml'))['script']['emhass_reguler']['sequence']))
    i = next(n for n, b in enumerate(alle) if 'elbil' in b)
    assert 'ts' in alle[i - 2] and 'p_batt' in alle[i - 1] and 'fase_ok' in alle[i + 2], 'efter tilsidesættelserne, før grænserne'
    rend = lambda t, vs: Template(t, hass).async_render(vs)  # noqa: E731

    def reguler(p_batt, maal, soc, ts, on, p_net=0):
        hass.states.async_set(HOLD, 'on' if on else 'off')
        vs = {'p_batt': p_batt, 'maal': maal, 'soc': soc, 'ts': ts, 'p_net': p_net}
        vs['elbil'] = rend(alle[i]['elbil'], vs)
        ny = {k: rend(alle[i + 1][k], vs) for k in ('p_batt',)}
        vs.update(ny)
        return ny['p_batt'], rend(alle[i + 1]['maal'], vs)
    for ts in ('ingen', 'lad', 'ingen_netladning', 'gem', 'brug'):
        for p, m, soc in ((4000, 15, 63), (-5000, 80, 63), (0, 50, 100), (2500.5, 40, 20)):
            assert reguler(p, m, soc, ts, False) == (p, m), 'uden hold er intet ændret'
            assert reguler(p, m, soc, 'brug', True) == (p, m), '"brug batteriet" vinder'
    for ts in ('ingen', 'lad', 'ingen_netladning', 'gem'):
        assert reguler(4000, 15, 63, ts, True) == (0, 65)      # ingen afladning: gulvet over batteriets niveau
        assert reguler(-5000, 80, 63, ts, True) == (-5000, 80)  # ladning fortsætter mod planens mål
        assert reguler(3000, 15, 100, ts, True) == (0, 100) and reguler(3000, 'x', 60, ts, True) == (0, 60)
    # gulvet må ikke lokke netladningen over planens mål (60): 61 % ville ellers give målet 65, så 70 …
    for soc, ventet in ((55, -3000), (59.9, -3000), (60, 0), (60.4, 0), (61, 0), (66, 0)):
        assert reguler(-3000, 60, soc, 'ingen', True, 3500)[0] == ventet, soc
        assert reguler(-3000, 60, soc, 'ingen', False, 3500) == (-3000, 60)
    assert reguler(-3000, 60, 66, 'ingen', True, 0)[0] == -3000, 'sol må stadig lade'
    # samme resultat som "gem batteriet", der er afprøvet på alle kanaler
    gem = alle[i - 1]
    for p, m, soc in ((4000, 15, 63), (-5000, 80, 63), (0, 50, 100), (3000, 15, 15)):
        vs = {'p_batt': p, 'maal': m, 'soc': soc, 'ts': 'gem', 'p_net': 0}
        assert (rend(gem['p_batt'], vs), rend(gem['maal'], vs)) == reguler(p, m, soc, 'ingen', True)
    print('Klemmen i reguleringen: OK')

    # --- husprognosen uden elbilen ---
    sql = next(q['query'] for q in load_yaml(str(PK / 'emhass_husprognose.yaml'))['sql'] if q['unique_id'] == 'emhass_husforbrug_historik')

    def prognose(hus, bil=None, sql=sql):
        c = sqlite3.connect(':memory:')
        c.execute('CREATE TABLE statistics_meta (id INTEGER PRIMARY KEY, statistic_id TEXT)')
        c.execute('CREATE TABLE statistics_short_term (metadata_id INTEGER, start_ts REAL, mean REAL)')
        t0 = (int(time.time()) // 1800 - 4) * 1800
        for n, (navn, rk) in enumerate((('sensor.emhass_m_load_w_totalpower', hus), ('sensor.andet', [9000] * 6), *([('sensor.wattlas_elbil_effekt', bil)] if bil is not None else []))):
            c.execute('INSERT INTO statistics_meta VALUES (?, ?)', (n + 1, navn))
            c.executemany('INSERT INTO statistics_short_term VALUES (?, ?, ?)', [(n + 1, t0 + 300 * k, x) for k, x in enumerate(rk)])
        return c.execute(sql).fetchone()
    import json
    tal = lambda *a, **k: [r[1] for r in json.loads(prognose(*a, **k)[1])]  # noqa: E731
    gammel = sql.replace("ROUND(AVG(MAX(st.mean - COALESCE(ev.mean, 0), MIN(st.mean, 0))))", "ROUND(AVG(st.mean))")
    gammel = gammel[:gammel.index('LEFT JOIN')] + gammel[gammel.index("WHERE sm.statistic_id"):]
    assert gammel != sql
    for hus in ([500, 700, 900, 1100, 1300, 1500, 300], [-100, 500, 0, 0, 0, 0], [400, None, 600, None, 500, 500]):
        assert prognose(hus) == prognose(hus, sql=gammel), 'uden lader er prognosen uændret'
        assert prognose(hus, [None] * 7) == prognose(hus, sql=gammel)
    assert tal([8000] * 6, [7000] * 6) == [1000]
    assert tal([8000] * 3 + [1000] * 3, [7000] * 3 + [0] * 3) == [1000]
    assert tal([8000] * 6, [7000] * 3) == [4500], 'kun perioder med en måling trækkes fra'
    assert tal([5000] * 6, [9000] * 6) == [0], 'aldrig negativt'
    print('Husprognosen uden elbilen: OK')
    await hass.async_stop(force=True)

    # --- Konfigurer → Elbil-lader ---
    hass, _ = await ny_hass('default_config:\n')
    await opsaet(hass, 'deye', 'sensor.deye_pv_power')
    kald = fang_kald(hass)
    entry = hass.config_entries.async_entries('wattlas')[0]
    om = hass.config_entries.options
    from homeassistant.helpers import entity_registry as er
    ENT = 'input_text.wattlas_elbil_entitet'

    async def menu():
        r = await om.async_init(entry.entry_id)
        return await om.async_configure(r['flow_id'], {'next_step_id': 'elbil'})

    def std(r):
        return {str(k): k.default() if callable(getattr(k, 'default', None)) else (k.description or {}).get('suggested_value') for k in r['data_schema'].schema}
    # pakkerne er fra før denne version (genstart mangler): intet gemmes
    r = await menu()
    assert r['type'] == 'abort' and r['reason'] == 'genstart_foerst', r
    hass.states.async_set(ENT, ''); hass.states.async_set(TIL, 'off')
    hass.states.async_set('sensor.vaerksted_power', '20', {'device_class': 'power', 'unit_of_measurement': 'W'})
    r = await menu()
    assert std(r) == {'elbil_sensor': None, 'elbil_hold': True} and 'Ingen' in r['description_placeholders']['fundet'], r
    # en kendt lader foreslås – den samlede effekt, ikke faserne eller slåede fra
    reg = er.async_get(hass)
    for platform, uid, enhed, navn in (('zaptec', 'x_total_charge_power', 'W', 'Zaptec Carport'), ('zaptec', 'x_phase1', 'W', 'Zaptec fase 1'), ('easee', 'a_import_power', 'kW', 'Equalizer'), ('deye', 'y', 'W', 'Inverter')):
        e = reg.async_get_or_create('sensor', platform, uid, original_name=navn)
        hass.states.async_set(e.entity_id, '0', {'device_class': 'power', 'unit_of_measurement': enhed, 'friendly_name': navn})
    zap = next(e.entity_id for e in reg.entities.values() if e.unique_id == 'x_total_charge_power')
    r = await menu()
    assert std(r)['elbil_sensor'] == zap and 'Zaptec Carport' in r['description_placeholders']['fundet'] and 'fase 1' not in r['description_placeholders']['fundet'], r
    # inverterens egne sensorer (også omdøbte) er husets forbrug, ikke bilen
    from homeassistant.helpers import device_registry as dr
    dev = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={('x', 'inv')})
    for uid, eid in (('i1', 'deye_pv_power'), ('i2', 'hus_effekt')):
        e = reg.async_get_or_create('sensor', 'deyetest', uid, suggested_object_id=eid, device_id=dev.id)
        hass.states.async_set(e.entity_id, '900', {'device_class': 'power', 'unit_of_measurement': 'W'})
    for forkert, attr in (('sensor.hus_effekt', None), ('sensor.deye_load_power', {'unit_of_measurement': 'W'}), ('sensor.p_load_forecast', {'unit_of_measurement': 'W'}), ('sensor.findes_ikke', None), ('sensor.x_kwh', {'unit_of_measurement': 'kWh'}), ('sensor.tekst', {'unit_of_measurement': 'W'}),
                          ('sensor.wattlas_elbil_effekt', {'unit_of_measurement': 'W'}), (LOAD, {'unit_of_measurement': 'W'})):
        if attr:
            hass.states.async_set(forkert, 'Charging' if forkert == 'sensor.tekst' else '500', attr)
        kald.clear()
        f = await om.async_configure(r['flow_id'], {'elbil_sensor': forkert, 'elbil_hold': True})
        assert f['errors'] == {'elbil_sensor': 'elbil_sensor'} and not kald, (forkert, f)
    r = await om.async_configure(r['flow_id'], {'elbil_sensor': zap, 'elbil_hold': True})
    assert r['type'] == 'create_entry' and ('input_text', 'set_value', ENT, zap) in kald and ('input_boolean', 'turn_on', TIL, None) in kald, kald
    # en lader, der er offline lige nu, må gerne vælges, når enheden kendes
    hass.states.async_set(zap, 'unavailable', {'unit_of_measurement': 'W', 'device_class': 'power'}); hass.states.async_set(ENT, zap); hass.states.async_set(TIL, 'on')
    r = await menu()
    assert std(r) == {'elbil_sensor': zap, 'elbil_hold': True}
    kald.clear()
    r = await om.async_configure(r['flow_id'], {'elbil_sensor': zap, 'elbil_hold': False})
    assert r['type'] == 'create_entry' and ('input_boolean', 'turn_off', TIL, None) in kald, kald
    hass.states.async_set(TIL, 'off')
    assert std(await menu()) == {'elbil_sensor': zap, 'elbil_hold': False}, 'et hold, man har slået fra, må ikke slås til igen'
    # ryddes feltet, er det slået helt fra
    r = await menu(); kald.clear()
    r = await om.async_configure(r['flow_id'], {'elbil_hold': True})
    assert r['type'] == 'create_entry' and ('input_text', 'set_value', ENT, '') in kald and ('input_boolean', 'turn_off', TIL, None) in kald, kald
    # flere kendte ladere: intet gættes
    e = reg.async_get_or_create('sensor', 'wallbox', 'charging_power-1', original_name='Wallbox')
    hass.states.async_set(e.entity_id, '0', {'device_class': 'power', 'unit_of_measurement': 'kW'}); hass.states.async_set(ENT, '')
    r = await menu()
    assert std(r)['elbil_sensor'] is None and 'Wallbox' in r['description_placeholders']['fundet']
    # Sonnen kan ikke holdes
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'kanal': 'sonnen'})
    r = await menu(); kald.clear()
    assert set(std(r)) == {'elbil_sensor'}
    r = await om.async_configure(r['flow_id'], {'elbil_sensor': zap})
    assert r['type'] == 'create_entry' and ('input_text', 'set_value', ENT, zap) in kald and ('input_boolean', 'turn_off', TIL, None) in kald, kald
    await hass.async_stop(force=True)
    print('Konfigurer → Elbil-lader: OK')


asyncio.run(main())
