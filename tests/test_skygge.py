# Skygge-tilstand og de to læse-sensorer kørt i en rigtig (minimal) Home Assistant med kernens egne scripts og skabeloner.
# Kør: python tests/test_skygge.py   (kræver: pip install homeassistant)
import asyncio, pathlib, sys, tempfile, types
if sys.platform == 'win32':  # Home Assistant importerer to moduler, der kun findes på Linux
    for m in ('fcntl', 'resource'):
        mod = types.ModuleType(m); mod.__getattr__ = lambda n: (lambda *a, **k: (0, 0)); sys.modules[m] = mod
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from homeassistant import bootstrap, config_entries, core, loader
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml

PK = pathlib.Path(__file__).parent.parent / 'packages/wattlas'
SKYGGE, OVERTAGET = 'input_boolean.wattlas_skygge', 'input_boolean.emhass_har_overtaget'


async def main():
    hass = core.HomeAssistant(tempfile.mkdtemp())
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    assert await bootstrap.async_load_base_functionality(hass)
    await hass.config.async_set_time_zone('Europe/Copenhagen')
    hass.set_state(core.CoreState.running)
    f = load_yaml(str(PK / 'emhass_forbindelse.yaml'))
    s = load_yaml(str(PK / 'wattlas_skygge.yaml'))
    p = load_yaml(str(PK / 'wattlas_prognoser.yaml'))
    for dom, conf in {'input_boolean': {**f['input_boolean'], **s['input_boolean']}, 'input_number': f['input_number'],
                      'script': f['script'], 'template': s['template'] + p['template']}.items():
        assert await async_setup_component(hass, dom, {dom: conf}), dom
    assert await async_setup_component(hass, 'system_log', {})
    # solsalg-automationen (den eneste automation, der skriver til styrekanalen)
    solsalg = next(a for a in f['automation'] if a['id'] == 'emhass_solsalg_efter_netto_salgspris')
    assert await async_setup_component(hass, 'automation', {'automation': [solsalg]})
    await hass.async_block_till_done()

    # en Deye-agtig styrekanal; et andet system har slået netladningen til
    kald = []

    async def fang(call):
        kald.append((call.domain, call.service, call.data.get('entity_id'), call.data.get('value')))
    for dom, tj in (('number', 'set_value'), ('switch', 'turn_on'), ('switch', 'turn_off')):
        hass.services.async_register(dom, tj, fang)
    sæt = hass.states.async_set
    sæt('binary_sensor.wattlas_konfigureret', 'on')
    sæt('number.wattlas_program_1_soc', '30', {'min': 0, 'max': 100})
    sæt('switch.wattlas_netladning', 'on')
    for i in range(1, 7):
        sæt(f'switch.emhass_netladning_p{i}', 'on' if i == 1 else 'off')

    async def kør(script, **data):
        await hass.services.async_call('script', script, data, blocking=True)
        await hass.async_block_till_done()

    async def boolsk(e, on):
        await hass.services.async_call('input_boolean', 'turn_on' if on else 'turn_off', {'entity_id': e}, blocking=True)
        await hass.async_block_till_done()

    # 1) skygge: intet skrives – den ønskede værdi meldes i sensor.wattlas_skygge
    await boolsk(SKYGGE, True)
    await kør('emhass_skriv_tal', entitet='number.wattlas_program_1_soc', vaerdi=80)
    await kør('emhass_netopladning_fra')
    await kør('emhass_selvforbrug')
    assert kald == [], f'skygge skrev til inverteren: {kald}'
    sk = hass.states.get('sensor.wattlas_skygge')
    assert sk.attributes['ville'] == {'number.wattlas_program_1_soc': 80.0, 'switch.wattlas_netladning': 'off'}, sk.attributes
    assert sk.state == 'Ville ikke lade fra nettet', sk.state
    # start i skygge: Wattlas overtager ikke (så kanalernes egne automationer heller ikke styrer)
    sæt('binary_sensor.emhass_ui_data_frisk', 'off')
    await kør('emhass_start')
    assert hass.states.get(OVERTAGET).state == 'off', 'skygge må ikke sætte "har overtaget"'
    # solsalg ved negativ pris: meldes, skrives ikke
    for e in ('input_boolean.emhass_styring_aktiv', 'input_boolean.emhass_opstart_klar'):
        await boolsk(e, True)
    sæt('binary_sensor.emhass_styrekanal_ok', 'on')
    sæt('switch.wattlas_solsalg', 'on')
    sæt('sensor.emhass_ui_salgspris', '-0.12')
    await hass.async_block_till_done()
    assert kald == [], f'skygge stoppede solsalget i inverteren: {kald}'
    sk = hass.states.get('sensor.wattlas_skygge')
    assert sk.attributes['ville'].get('switch.wattlas_solsalg') == 'off' and sk.state.endswith('ville stoppe solsalget'), sk
    print('Skygge: intet skrives, ønsket meldes: OK')

    # 2) mens skyggen slås til, og Wattlas stadig har overtaget, skal inverteren gives tilbage (selvforbrug skrives)
    await boolsk(OVERTAGET, True)
    await kør('emhass_netopladning_fra')
    assert ('switch', 'turn_off', ['switch.wattlas_netladning'], None) in kald, kald
    # 3) skygge fra: alt som før
    await boolsk(OVERTAGET, False)
    await boolsk(SKYGGE, False)
    assert hass.states.get('sensor.wattlas_skygge').state == 'Slået fra'
    kald.clear()
    await kør('emhass_skriv_tal', entitet='number.wattlas_program_1_soc', vaerdi=80)
    assert kald == [('number', 'set_value', ['number.wattlas_program_1_soc'], 80.0)], kald
    sæt('binary_sensor.emhass_ui_data_frisk', 'off')
    await kør('emhass_start')
    assert hass.states.get(OVERTAGET).state == 'on', 'uden skygge overtager Wattlas som før'
    print('Skygge fra: skriver og overtager som før: OK')

    # 4) "batteriet rækker til": planens SOC gælder ved slutningen af halvtimen; bunden er reserven (25 %)
    nu = dt_util.now()
    t0 = (nu.timestamp() // 1800) * 1800
    sæt('input_number.wattlas_reserve', '25')
    soc = [60, 50, 40, 30, 25, 25, 40, 70, 100, 90]
    sæt('sensor.emhass_gemt_plan', nu.isoformat(), {'schema': 1, 'rows': [[t0 + i * 1800, 1000, 0, s] for i, s in enumerate(soc)]})
    await hass.async_block_till_done()
    b = hass.states.get('sensor.wattlas_batteri_raekker_til')
    assert dt_util.parse_datetime(b.state).timestamp() == t0 + 4 * 1800 + 1800, (b.state, t0)
    assert b.attributes['laveste_soc'] == 25 and b.attributes['hele_planen'] is False and b.attributes['tekst'].startswith('Rækker til kl.'), b.attributes
    sæt('sensor.emhass_gemt_plan', dt_util.now().isoformat(), {'schema': 1, 'rows': [[t0 + i * 1800, 0, 0, 80 - i] for i in range(10)]})
    await hass.async_block_till_done()
    b = hass.states.get('sensor.wattlas_batteri_raekker_til')
    assert b.attributes['hele_planen'] is True and b.attributes['laveste_soc'] == 71 and b.attributes['tekst'].startswith('Rækker hele planen'), b.attributes
    sæt('sensor.emhass_gemt_plan', (nu - timedelta(hours=3)).isoformat(), {'schema': 1, 'rows': [[t0, 0, 0, 20]]})
    await hass.async_block_till_done()
    assert hass.states.get('sensor.wattlas_batteri_raekker_til').state == 'unavailable', 'en gammel plan må ikke vises'
    print('Batteriet rækker til: OK')

    # 5) billigste time: købspris med tariffen for netop den time; kvarterpriser = timens gennemsnit; kun fra næste time
    for e, v in {'nettarif_lav': 0.1, 'nettarif_hoej': 0.3, 'nettarif_spids': 0.9, 'elafgift': 0.8, 'tillaeg': 0.05}.items():
        sæt(f'input_number.wattlas_{e}', str(v))
    h0 = nu.replace(minute=0, second=0, microsecond=0)
    # time 0 (den nuværende) er dyrest: i timens første minut holder sensoren den, så testen må ikke afhænge af klokken
    spot = {0: 9.0, 1: 1.0, 2: 0.95, 3: 1.2, 4: 0.9, 5: 1.1}

    def koeb(h, sp):
        t = (h0 + timedelta(hours=h)).astimezone(ZoneInfo('Europe/Copenhagen')).hour
        net = 0.1 if t < 6 else 0.9 if 17 <= t < 21 else 0.3
        return sp + (net + 0.8) * 1.25 + 0.05
    forvent = min(range(1, 6), key=lambda h: koeb(h, spot[h]))
    kv = [{'hour': (h0 + timedelta(hours=h, minutes=15 * q)).isoformat(), 'price': spot[h] + (0.02 if q == 3 else -0.02 if q == 0 else 0)}
          for h in spot for q in range(4)]
    sæt('sensor.energi_data_service', '1', {'raw_today': kv, 'raw_tomorrow': []})
    await hass.async_block_till_done()
    sæt('sensor.energi_data_service', '1', {'raw_today': kv, 'raw_tomorrow': [{'hour': (h0 + timedelta(hours=6)).isoformat(), 'price': 9}]})
    await hass.async_block_till_done()
    bt = hass.states.get('sensor.wattlas_billigste_time')
    assert dt_util.parse_datetime(bt.state) == h0 + timedelta(hours=forvent), (bt.state, forvent)
    assert abs(bt.attributes['pris'] - round(koeb(forvent, spot[forvent]), 2)) < 0.005, bt.attributes
    print('Billigste time: OK')
    await hass.async_stop(force=True)

    # 6) Sonnen-kanalen på en helt ny installation: tidsprogrammer, ladestrøm og solsalg har en værdi fra start (ellers
    #    nægter kernen at skrive til dem, og styrekanalen bliver aldrig klar)
    hass = core.HomeAssistant(tempfile.mkdtemp())
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    assert await bootstrap.async_load_base_functionality(hass)
    hass.set_state(core.CoreState.running)
    k = load_yaml(str(PK.parent.parent / 'styrekanaler/sonnen/wattlas_kanal_sonnen.yaml'))
    hass.states.async_set('sensor.min_sonnen_status', '900', {'Ubat': 52, 'OperatingMode': 2, 'Production_W': 0, 'GridFeedIn_W': -900, 'Pac_total_W': 0})
    for i in (1, 2, 3):
        hass.states.async_set(f'sensor.min_sonnen_maaler_w_l{i}', '300'); hass.states.async_set(f'sensor.min_sonnen_maaler_v_l{i}', '230')
    hass.states.async_set('input_number.wattlas_fase_graense_a', '16')
    for dom in ('input_boolean', 'input_number', 'template'):
        assert await async_setup_component(hass, dom, {dom: k[dom]}), dom
    await hass.async_block_till_done()
    for i in range(1, 7):
        for e in (f'number.wattlas_program_{i}_soc', f'number.wattlas_program_{i}_power'):
            assert hass.states.get(e).state not in ('unknown', 'unavailable'), (e, hass.states.get(e))
        assert hass.states.get(f'switch.emhass_netladning_p{i}').state in ('on', 'off')
    assert hass.states.get('switch.wattlas_solsalg').state in ('on', 'off') and hass.states.get('switch.wattlas_netladning').state == 'off'
    n = hass.states.get('number.wattlas_netladestroem')
    assert n.state == '0.0' and n.attributes['max'] == (16 * 230 - 300) * 0.95 // 52, n
    print('Sonnen fra start: OK')
    await hass.async_stop(force=True)

    # 7) Tilbagelevering med de RIGTIGE automationer (hovedafbryder, oprydning, skygge-skift): svarer inverteren ikke, må
    #    "har overtaget" ikke slukkes – ellers prøver ingen igen, og fjernelse og skygge tror, at inverteren står i selvforbrug.
    #    Ventetiderne i selvforbrug-scriptet (15 s) og skygge-skiftet (2 min) forkortes, så testen er hurtig.
    hass = core.HomeAssistant(tempfile.mkdtemp())
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    assert await bootstrap.async_load_base_functionality(hass)
    hass.set_state(core.CoreState.running)
    f = load_yaml(str(PK / 'emhass_forbindelse.yaml'))
    s = load_yaml(str(PK / 'wattlas_skygge.yaml'))
    next(a for a in f['script']['emhass_selvforbrug']['sequence'] if 'wait_template' in a)['timeout'] = '00:00:02'
    skift = next(a for a in s['automation'] if a['id'] == 'wattlas_skygge_skift')
    next(a for a in skift['actions'] if 'wait_template' in a)['timeout'] = '00:00:04'
    auto = [a for a in f['automation'] if a['id'] in ('emhass_hovedafbryder', 'emhass_oprydning_efter_genstart')] + [skift]
    assert len(auto) == 3
    for dom, conf in {'input_boolean': {**f['input_boolean'], **s['input_boolean']}, 'input_number': f['input_number'],
                      'script': f['script'], 'automation': auto}.items():
        assert await async_setup_component(hass, dom, {dom: conf}), dom
    svarer = {'ja': False}
    kald = []

    async def inverter(call):  # en Deye-agtig inverter: skrivninger slår kun igennem, når den svarer
        kald.append((call.service, call.data.get('entity_id')))
        for e in call.data.get('entity_id') or [] if svarer['ja'] else []:
            if call.domain == 'switch':
                hass.states.async_set(e, 'on' if call.service == 'turn_on' else 'off')
            else:
                hass.states.async_set(e, str(call.data['value']), {'min': 0, 'max': 100})
    for dom, tj in (('number', 'set_value'), ('switch', 'turn_on'), ('switch', 'turn_off')):
        hass.services.async_register(dom, tj, inverter)

    def lader():  # Wattlas netlader i program 1
        hass.states.async_set('binary_sensor.wattlas_konfigureret', 'on')
        hass.states.async_set('switch.wattlas_netladning', 'on')
        for i in range(1, 7):
            hass.states.async_set(f'switch.emhass_netladning_p{i}', 'on' if i == 1 else 'off')
            hass.states.async_set(f'number.wattlas_program_{i}_soc', '80', {'min': 0, 'max': 100})

    async def boolsk(e, on):
        await hass.services.async_call('input_boolean', 'turn_on' if on else 'turn_off', {'entity_id': e}, blocking=True)

    async def vent(e, tilstand, sek):
        for _ in range(sek * 10):
            if hass.states.get(e).state == tilstand:
                return True
            await asyncio.sleep(0.1)
        return False

    async def faerdig(e, sek):  # venter, til scriptet/automationen har kørt og er færdig igen
        set_i_gang = False
        for _ in range(sek * 20):
            i_gang = (hass.states.get(e).attributes.get('current') or 0) > 0
            set_i_gang = set_i_gang or i_gang
            if set_i_gang and not i_gang:
                await asyncio.sleep(0.3)  # handlingen lige efter (slukke flaget) når at køre
                return True
            await asyncio.sleep(0.05)
        return False
    STYRING = 'input_boolean.emhass_styring_aktiv'
    lader()
    for e in (OVERTAGET, STYRING):
        await boolsk(e, True)
    await asyncio.sleep(0.5)
    # a) styringen slås fra, inverteren svarer ikke: netladningen står stadig til, og Wattlas skylder stadig en tilbagelevering
    await boolsk(STYRING, False)
    assert await faerdig('script.emhass_selvforbrug', 20), 'selvforbrug-scriptet kørte ikke'
    assert hass.states.get('switch.wattlas_netladning').state == 'on' and hass.states.get(OVERTAGET).state == 'on', \
        'inverteren svarede ikke – "har overtaget" må ikke slukkes'
    # b) inverteren svarer igen: oprydningen (hvert minut) giver den tilbage og slukker først derefter flaget
    svarer['ja'] = True
    await hass.services.async_call('automation', 'trigger', {'entity_id': 'automation.emhass_oprydning_efter_genstart_eller_afbrudt_stop'}, blocking=False)
    assert await vent(OVERTAGET, 'off', 10), 'oprydningen gav ikke inverteren tilbage'
    assert hass.states.get('switch.wattlas_netladning').state == 'off' and float(hass.states.get('number.wattlas_program_1_soc').state) == 15
    print('Tilbagelevering: flaget slukkes kun, når inverteren er givet tilbage: OK')
    # c) skygge slås til, mens Wattlas styrer, og inverteren svarer ikke: styringen bliver slukket, og Wattlas går IKKE i skygge-drift
    svarer['ja'] = False
    lader()
    for e in (OVERTAGET, STYRING):
        await boolsk(e, True)
    await asyncio.sleep(0.5)
    await boolsk(SKYGGE, True)
    assert await faerdig('automation.wattlas_skift_mellem_skygge_og_styring', 30), 'skygge-skiftet kørte ikke'
    assert hass.states.get(STYRING).state == 'off' and hass.states.get(OVERTAGET).state == 'on', \
        (hass.states.get(STYRING).state, hass.states.get(OVERTAGET).state)
    # d) inverteren svarer: skiftet giver den tilbage og slår derefter styringen til igen – nu i skygge
    svarer['ja'] = True
    await boolsk(SKYGGE, False)
    await boolsk(STYRING, True)
    await asyncio.sleep(0.5)
    await boolsk(SKYGGE, True)
    assert await vent(OVERTAGET, 'off', 10) and await vent(STYRING, 'on', 5), 'skiftet til skygge blev ikke gennemført'
    assert hass.states.get('switch.wattlas_netladning').state == 'off'
    kald.clear()
    await asyncio.sleep(2)
    assert not kald, f'i skygge skrives der ikke til inverteren: {kald}'
    print('Skygge-skift: tilbagelevering først, ellers stoppes styringen: OK')
    await hass.async_stop(force=True)


asyncio.run(main())
