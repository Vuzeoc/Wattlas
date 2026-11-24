# SolaX-, Sofar-, Solis- og SPF-styringen kørt i en rigtig (minimal) Home Assistant: hvilke kald går til inverteren, i hvilken rækkefølge.
# Kør: python tests/test_kanalstyring.py   (kræver: pip install homeassistant)
import asyncio, pathlib, sys, tempfile, time, types
if sys.platform == 'win32':  # Home Assistant importerer to moduler, der kun findes på Linux
    for m in ('fcntl', 'resource'):
        mod = types.ModuleType(m); mod.__getattr__ = lambda n: (lambda *a, **k: (0, 0)); sys.modules[m] = mod
from datetime import datetime, timedelta
from homeassistant import bootstrap, config_entries, core, loader
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml

KANALER = pathlib.Path(__file__).parent.parent / 'styrekanaler'


async def ny_hass(kanal, svartid=0):
    hass = core.HomeAssistant(tempfile.mkdtemp())
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    assert await bootstrap.async_load_base_functionality(hass)
    await hass.config.async_set_time_zone('Europe/Copenhagen')
    hass.set_state(core.CoreState.running)
    k = load_yaml(str(KANALER / {'spf': 'growatt_spf'}.get(kanal, kanal) / f'wattlas_kanal_{kanal}.yaml'))
    styring = next(a for a in k['automation'] if a['id'] == f'wattlas_{kanal}_styring')
    styring['triggers'] = [t for t in styring['triggers'] if t['trigger'] != 'time_pattern']  # testen starter selv minut-kørslerne
    for dom, conf in {'input_boolean': k['input_boolean'], 'input_number': k['input_number'],
                      'input_text': k.get('input_text') or {}, 'automation': [styring]}.items():
        assert await async_setup_component(hass, dom, {dom: conf}), dom
    await hass.async_block_till_done()
    kald = []

    async def inverter(call):  # solax_modbus' lokale tal og valg: skrivningen ses straks i tilstanden
        await asyncio.sleep(svartid)
        e = call.data['entity_id'][0] if isinstance(call.data['entity_id'], list) else call.data['entity_id']
        v = call.data.get('value', call.data.get('option'))
        kald.append((time.monotonic(), call.service, e.split('.', 1)[1].replace(f'min_{kanal}_', ''), v))
        # tal og valg ses straks i tilstanden; en knaps tilstand er tidspunktet for sidste tryk (som i HA)
        hass.states.async_set(e, dt_util.utcnow().isoformat() if call.service == 'press' else str(float(v)) if call.service == 'set_value' else v)
    for dom, tj in (('number', 'set_value'), ('select', 'select_option'), ('button', 'press')):
        hass.services.async_register(dom, tj, inverter)
    return hass, kald


def fælles(hass, kanal, soc, *, netlad='on', styrer='on', a=40):
    sæt = hass.states.async_set
    for e, v in {'input_boolean.emhass_styring_aktiv': styrer, 'input_boolean.emhass_har_overtaget': styrer,
                 'input_number.wattlas_maks_ladeeffekt_w': 10000, 'input_number.wattlas_maks_afladeeffekt_w': 9000}.items():
        sæt(e, str(v))
    for p in range(1, 7):  # alle perioder ens, så testen ikke afhænger af klokken
        sæt(f'input_number.wattlas_{kanal}_p{p}_soc', '80'); sæt(f'input_number.wattlas_{kanal}_p{p}_power', '0')
        sæt(f'input_boolean.wattlas_{kanal}_p{p}', 'on')
    sæt(f'input_number.wattlas_{kanal}_netladestroem', str(a))
    sæt(f'input_boolean.wattlas_{kanal}_netladning', netlad)
    return sæt


async def kør(hass, kanal, kald, ryd=True):  # ryd=False: tæl også kørsler, som et tilstandsskift lige har startet
    if ryd:
        await hass.async_block_till_done(); kald.clear()
    await hass.services.async_call('automation', 'trigger', {'entity_id': f'automation.wattlas_{kanal}_styring', 'skip_condition': False}, blocking=True)
    for _ in range(100):  # Solis venter 2 s mellem Prepare og Apply
        await hass.async_block_till_done()
        if (hass.states.get(f'automation.wattlas_{kanal}_styring').attributes.get('current') or 0) == 0:
            break
        await asyncio.sleep(0.05)
    return [(s, e, v) for _, s, e, v in kald]


async def sofar():
    hass, kald = await ny_hass('sofar')
    sæt = fælles(hass, 'sofar', 50)
    UPD, TID = ('press', 'passive_update_battery_charge_discharge', None), ('press', 'passive_update_timeout', None)
    sæt('sensor.min_sofar_battery_capacity_total', '50'); sæt('select.min_sofar_energy_storage_mode', 'Self Use')
    sæt('button.min_sofar_passive_update_battery_charge_discharge', 'unknown')
    for e in ('desired_grid_power', 'minimum_battery_power', 'maximum_battery_power'):  # ny solax_modbus: tallene er tomme
        sæt(f'number.min_sofar_passive_{e}', 'unknown')
    sæt('button.min_sofar_passive_update_timeout', 'unknown')
    sæt('select.min_sofar_passive_timeout', '6 Hours'); sæt('select.min_sofar_passive_timeout_action', 'unknown')  # brugerens egne
    TAL = lambda mindste: [('set_value', 'passive_maximum_battery_power', 10000), ('set_value', 'passive_minimum_battery_power', mindste),
                           ('set_value', 'passive_desired_grid_power', 0)]
    OVERTAG = [('select_option', 'passive_timeout', '10 Minutes'), ('select_option', 'passive_timeout_action', 'Return to Previous Mode'), TID, UPD,
               ('select_option', 'energy_storage_mode', 'Passive Mode')]
    # Wattlas overtager med netladning 40 A: tallene (største først), Wattlas' egen timeout, kommandoen – og først så Passive Mode
    k = await kør(hass, 'sofar', kald)
    assert k == TAL(2000.0) + OVERTAG, k
    assert hass.states.get('input_boolean.wattlas_sofar_fjern_styret').state == 'on'
    # uændret: fornyes – også tallene, for solax_modbus kan have erstattet dem med inverterens egne uden at vise det
    assert await kør(hass, 'sofar', kald) == TAL(2000.0) + [UPD]
    # fri, mens Wattlas styrer: også fornyet hvert minut – ellers forlader Sofar Passive Mode ved timeout
    for p in range(1, 7):
        sæt(f'input_number.wattlas_sofar_p{p}_soc', '20'); sæt(f'input_number.wattlas_sofar_p{p}_power', '5000')
    assert await kør(hass, 'sofar', kald) == TAL(-9000) + [UPD]
    # inverteren er faldet ud af Passive Mode (fx HA var nede): Wattlas vælger den selv igen
    sæt('select.min_sofar_energy_storage_mode', 'Self Use')
    assert await kør(hass, 'sofar', kald) == TAL(-9000) + OVERTAG
    # styringen slippes midt i netladning: "fri" sendes én gang, og så skriver Wattlas intet mere (heller ikke i Passive Mode)
    fælles(hass, 'sofar', 50); await kør(hass, 'sofar', kald)
    kald.clear(); fælles(hass, 'sofar', 50, styrer='off')
    k = await kør(hass, 'sofar', kald, ryd=False)
    assert ('set_value', 'passive_minimum_battery_power', -9000) in k and k[-1] == UPD, k
    assert hass.states.get('input_boolean.wattlas_sofar_fjern_styret').state == 'off'
    assert await kør(hass, 'sofar', kald) == []
    # inverteren står allerede i Passive Mode uden timeout (din egen eller en afbrudt kørsel), når Wattlas overtager: timeouten sendes
    sæt('select.min_sofar_energy_storage_mode', 'Passive Mode')
    kald.clear(); fælles(hass, 'sofar', 50, netlad='on')
    k = await kør(hass, 'sofar', kald, ryd=False)
    assert TID in k and k.index(TID) < k.index(UPD) and k.index(OVERTAG[0]) < k.index(TID), k
    assert await kør(hass, 'sofar', kald) == TAL(2000.0) + [UPD]              # og ikke hvert minut
    fælles(hass, 'sofar', 50, styrer='off'); await kør(hass, 'sofar', kald)
    # skygge (styring til, men ikke overtaget) med en netladning husket fra før: intet
    sæt('input_boolean.emhass_styring_aktiv', 'on')
    await kør(hass, 'sofar', kald)
    assert await kør(hass, 'sofar', kald) == [] and hass.states.get('input_boolean.wattlas_sofar_netladning').state == 'on'
    await hass.async_stop(force=True)
    print('Sofar: overtagelse, fornyelse (også i fri), tilbagelevering og skygge: OK')


async def solis():
    hass, kald = await ny_hass('solis')
    sæt = fælles(hass, 'solis', 50)
    for e, v in {'sensor.min_solis_battery_soc': 50, 'sensor.min_solis_remote_dispatch_function_version': 1,
                 'sensor.min_solis_pv_total_power': 0, 'sensor.wattlas_solis_husforbrug': 600,
                 'select.min_solis_dispatch_control_mode': 'Battery Hold', 'select.min_solis_dispatch_grid_charging': 'No instruction'}.items():
        sæt(e, str(v))
    for e in ('prepare', 'apply', 'disable'):
        sæt(f'button.min_solis_{e}_remote_dispatch', 'unknown')
    for e in ('dispatch_power', 'dispatch_failsafe_interval', 'dispatch_soc_minimum', 'dispatch_soc_maximum'):
        sæt(f'number.min_solis_{e}', 'unknown')
    # netladning 40 A = 2000 W: tallene sættes, Prepare, mindst 2 s, Apply
    k = await kør(hass, 'solis', kald)
    assert k == [('set_value', 'dispatch_failsafe_interval', 5), ('select_option', 'dispatch_control_mode', 'Battery Charge'),
                 ('set_value', 'dispatch_power', 2000.0), ('select_option', 'dispatch_grid_charging', 'Allow'),
                 ('set_value', 'dispatch_soc_minimum', 0), ('set_value', 'dispatch_soc_maximum', 100),
                 ('press', 'prepare_remote_dispatch', None), ('press', 'apply_remote_dispatch', None)], k
    assert kald[-1][0] - kald[-2][0] >= 1.9, 'Solis skal have 2 s mellem Prepare og Apply'
    assert hass.states.get('input_boolean.wattlas_solis_fjern_styret').state == 'on'
    # uændret: kun Apply (fornyelsen) – Prepare kun hvert 10. minut
    k = await kør(hass, 'solis', kald)
    if datetime.now().minute % 10:
        assert k == [('press', 'apply_remote_dispatch', None)], k
    # inverteren er genstartet og har glemt ordren (målingerne modsiger den): Prepare igen med det samme
    sæt('sensor.emhass_maalekilde', 'Solis', {'balance_ok': False})
    k = await kør(hass, 'solis', kald)
    assert k == [('press', 'prepare_remote_dispatch', None), ('press', 'apply_remote_dispatch', None)], k
    sæt('sensor.emhass_maalekilde', 'Solis', {'balance_ok': True})
    # netladning fra, intet soloverskud, under målet: batteriet holdes (Battery Hold, 0 W)
    kald.clear(); fælles(hass, 'solis', 50, netlad='off')
    k = await kør(hass, 'solis', kald, ryd=False)
    assert ('select_option', 'dispatch_control_mode', 'Battery Hold') in k and ('set_value', 'dispatch_power', 0) in k, k
    assert k[-1] == ('press', 'apply_remote_dispatch', None), k
    # med soloverskud: egen drift (Remote Dispatch slås fra), så solen kan lade
    sæt('sensor.min_solis_pv_total_power', '3000')
    k = await kør(hass, 'solis', kald)
    assert k == [('press', 'disable_remote_dispatch', None)], k
    assert hass.states.get('input_boolean.wattlas_solis_fjern_styret').state == 'off'
    # styringen slået fra: intet sendes (Wattlas' egen Remote Dispatch er allerede slået fra)
    kald.clear(); fælles(hass, 'solis', 50, styrer='off')
    assert await kør(hass, 'solis', kald, ryd=False) == []
    # inverteren kan ikke Remote Dispatch (version 0): Wattlas rører den ikke
    sæt('sensor.min_solis_remote_dispatch_function_version', '0')
    kald.clear(); fælles(hass, 'solis', 50)
    assert await kør(hass, 'solis', kald, ryd=False) == []
    # kernen starter, justerer strømmen flere gange og stopper igen inden for 1 s: en forældet ladeordre må aldrig komme bagefter
    sæt('sensor.min_solis_remote_dispatch_function_version', '1'); sæt('sensor.min_solis_pv_total_power', '0')
    fælles(hass, 'solis', 50, netlad='off', styrer='off')
    await kør(hass, 'solis', kald); kald.clear()
    fælles(hass, 'solis', 50, netlad='on')
    for a in (41, 42, 43):
        await asyncio.sleep(0.2); sæt('input_number.wattlas_solis_netladestroem', str(a))
    await asyncio.sleep(0.2); sæt('input_boolean.wattlas_solis_netladning', 'off')
    await asyncio.sleep(0.1); fra = len(kald)
    await asyncio.sleep(8)
    efter = [(e, v) for _, _, e, v in kald[fra:]]
    assert ('dispatch_control_mode', 'Battery Charge') not in efter, efter
    assert hass.states.get('select.min_solis_dispatch_control_mode').state == 'Battery Hold' and efter[-1][0] == 'apply_remote_dispatch', efter
    # afbrudt mellem Prepare og Apply: den nye kørsel gør Prepare igen, så Apply aldrig kommer uden 2 s efter en Prepare
    sidst = [(t, e) for t, _, e, _ in kald if e in ('prepare_remote_dispatch', 'apply_remote_dispatch')]
    assert sidst[-2][1] == 'prepare_remote_dispatch' and sidst[-1][0] - sidst[-2][0] >= 1.9, sidst
    # skygge (styring til, men ikke overtaget) med en netladning husket fra før: intet
    fælles(hass, 'solis', 50, styrer='off'); sæt('input_boolean.emhass_styring_aktiv', 'on')
    await kør(hass, 'solis', kald)
    assert await kør(hass, 'solis', kald) == [], kald
    await hass.async_stop(force=True)
    print('Solis: rækkefølge, 2 s-pause, fornyelse, hold og fri: OK')


async def solax():
    hass, kald = await ny_hass('solax')
    sæt = fælles(hass, 'solax', 50)
    for e, v in {'sensor.min_solax_battery_capacity': 50, 'sensor.min_solax_pv_power_total': 0, 'sensor.min_solax_house_load': 600,
                 'select.min_solax_remotecontrol_power_control_mode_1': 'Disabled', 'button.min_solax_remotecontrol_trigger_mode_1_7': 'unknown',
                 'number.min_solax_remotecontrol_active_power_mode_1': 'unknown',  # ny solax_modbus: tallene er tomme
                 'number.min_solax_remotecontrol_autorepeat_duration_mode_1_9': 'unknown'}.items():
        sæt(e, str(v))
    k = await kør(hass, 'solax', kald)
    trigger = ('press', 'remotecontrol_trigger_mode_1_7', None)
    assert k == [('set_value', 'remotecontrol_active_power_mode_1', 2000.0), ('select_option', 'remotecontrol_power_control_mode_1', 'Enabled Power Control'),
                 ('set_value', 'remotecontrol_autorepeat_duration_mode_1_9', 600), trigger], k
    assert await kør(hass, 'solax', kald) == [trigger]                           # uændret: kun fornyelsen
    kald.clear(); fælles(hass, 'solax', 50, netlad='off')
    k = await kør(hass, 'solax', kald, ryd=False)                                # netladning fra, intet soloverskud: gem
    assert ('select_option', 'remotecontrol_power_control_mode_1', 'Enabled No Discharge') in k and k[-1] == trigger, k
    kald.clear(); fælles(hass, 'solax', 50, styrer='off')
    k = await kør(hass, 'solax', kald, ryd=False)                                # styringen fra: Wattlas' egen fjernstyring slås fra én gang
    assert ('select_option', 'remotecontrol_power_control_mode_1', 'Disabled') in k and k[-1] == trigger, k
    assert await kør(hass, 'solax', kald) == [] and hass.states.get('input_boolean.wattlas_solax_fjern_styret').state == 'off'
    # skygge (styring til, men ikke overtaget) med en netladning husket fra før: intet
    fælles(hass, 'solax', 50, styrer='off'); sæt('input_boolean.emhass_styring_aktiv', 'on')
    await kør(hass, 'solax', kald)
    assert await kør(hass, 'solax', kald) == [], kald
    await hass.async_stop(force=True)
    print('SolaX: rækkefølge, fornyelse, gem og fri: OK')


async def langsom():
    """Starter, justerer og stopper kernen hurtigt efter hinanden, mens inverteren er langsom, må en forældet ladeordre aldrig komme sidst."""
    for kanal, tilstande, lader in (
            ('growatt', {'sensor.min_growatt_battery_soc': 50, 'sensor.min_growatt_pv_power_total': 0, 'sensor.min_growatt_total_load_power': 600,
                         'select.min_growatt_vpp_remote_control': 'Disabled', 'select.min_growatt_vpp_allow_ac_charging': 'Enabled', 'number.min_growatt_vpp_power': 0},
             lambda s: float(s('number.min_growatt_vpp_power')) > 0),
            ('solax', {'sensor.min_solax_battery_capacity': 50, 'sensor.min_solax_pv_power_total': 0, 'sensor.min_solax_house_load': 600,
                       'select.min_solax_remotecontrol_power_control_mode_1': 'Disabled', 'button.min_solax_remotecontrol_trigger_mode_1_7': 'unknown',
                       'number.min_solax_remotecontrol_active_power_mode_1': 'unknown', 'number.min_solax_remotecontrol_autorepeat_duration_mode_1_9': 'unknown'},
             lambda s: s('select.min_solax_remotecontrol_power_control_mode_1') == 'Enabled Power Control'),
            ('sofar', {'sensor.min_sofar_battery_capacity_total': 50, 'select.min_sofar_energy_storage_mode': 'Self Use', 'button.min_sofar_passive_update_timeout': 'unknown',
                       'button.min_sofar_passive_update_battery_charge_discharge': 'unknown',
                       **{f'number.min_sofar_passive_{e}': 'unknown' for e in ('desired_grid_power', 'minimum_battery_power', 'maximum_battery_power')}},
             lambda s: float(s('number.min_sofar_passive_minimum_battery_power')) > 0)):
        hass, kald = await ny_hass(kanal, svartid=0.4)
        sæt = hass.states.async_set
        for e, v in tilstande.items():
            sæt(e, str(v))
        fælles(hass, kanal, 50, netlad='off', styrer='off'); await asyncio.sleep(0.5)
        fælles(hass, kanal, 50, netlad='on')
        for a in (44, 48, 52):
            await asyncio.sleep(0.3); sæt(f'input_number.wattlas_{kanal}_netladestroem', str(a))
        sæt(f'input_boolean.wattlas_{kanal}_netladning', 'off')
        await asyncio.sleep(5)  # langt før det næste hele minut gør det om
        assert not lader(lambda e: hass.states.get(e).state), (kanal, kald)
        await hass.async_stop(force=True)
    print('Langsom inverter: ingen forældet ladeordre (Growatt, SolaX, Sofar): OK')


async def spf():
    hass, kald = await ny_hass('spf')
    sæt = fælles(hass, 'spf', 50, netlad='off', styrer='off')
    GEM, FRI, LAD = 'Solar only', 'Solar/Battery/Utility', 'Solar and utility simultaneously'
    EMNE = {'output_source_priority': 'output', 'charger_source_priority': 'lader', 'max_grid_charge_current': 'netstroem'}
    ordrer, afvis = [], []

    async def solar_assistant(call):  # som Solar Assistant: tager imod, og inverteren melder den nye værdi (medmindre den afviser)
        emne = call.data['topic'].split('/')[2]
        assert call.data['topic'] == f'solar_assistant/inverter_1/{emne}/set' and not call.data.get('retain'), call.data
        ordrer.append((emne, str(call.data['payload']))); ordretid.append(time.monotonic())  # mqtt.publish gør selv tal til tekst
        if not afvis:
            hass.states.async_set(f'sensor.min_spf_{EMNE[emne]}', str(call.data['payload']))
    ordretid = []
    hass.services.async_register('mqtt', 'publish', solar_assistant)
    for e, v in {'output': 'Solar first', 'lader': 'Solar first', 'netstroem': 30, 'soc': 50, 'sol': 0, 'forbrug': 600, 'net': 600}.items():
        sæt(f'sensor.min_spf_{e}', str(v))
    sæt('number.wattlas_netladestroem', '40', {'max': 60})

    async def skub(ny=()):
        ordrer.clear(); ordretid.clear()
        for e, v in dict(ny).items():
            sæt(e, str(v))
        await hass.services.async_call('automation', 'trigger', {'entity_id': 'automation.wattlas_spf_styring', 'skip_condition': False}, blocking=True)
        await hass.async_block_till_done()
        return list(ordrer)
    # Wattlas styrer ikke: intet
    assert await skub() == [] and hass.states.get('input_boolean.wattlas_spf_styret').state == 'off'
    # overtager (gem): dine egne værdier huskes; laderen før output, 5 s imellem
    fælles(hass, 'spf', 50, netlad='off'); await hass.async_block_till_done()
    assert ordrer == [('charger_source_priority', GEM), ('output_source_priority', 'Utility first')] and ordretid[1] - ordretid[0] >= 4.9, ordrer
    assert [hass.states.get(f'input_text.wattlas_spf_egen_{x}').state for x in ('output', 'lader')] == ['Solar first', 'Solar first']
    assert float(hass.states.get('input_number.wattlas_spf_egen_stroem').state) == 30
    assert await skub() == []                                                          # uændret: intet skrives (inverteren slides)
    # netladning: strømmen først (hele 10 A, aldrig over net-indgangens plads), så laderen
    ordrer.clear(); sæt('input_number.wattlas_spf_netladestroem', '75'); sæt('input_boolean.wattlas_spf_netladning', 'on')
    await hass.async_block_till_done()
    assert ordrer == [('max_grid_charge_current', '60'), ('charger_source_priority', LAD)], ordrer
    # op igen inden for 3 minutter: venter. Ned: med det samme
    assert await skub({'input_number.wattlas_spf_netladestroem': 45}) == [('max_grid_charge_current', '40')], ordrer
    assert hass.states.get('sensor.min_spf_netstroem').state == '40'
    assert await skub({'input_number.wattlas_spf_netladestroem': 60}) == [] and hass.states.get('sensor.min_spf_netstroem').state == '40'
    # efter 3 minutter: op – men ikke, når døgnloftet er brugt
    def gammel():
        n = hass.states.get('input_number.wattlas_spf_sat_stroem')
        hass.states._states[n.entity_id] = type(n)(n.entity_id, n.state, n.attributes, last_changed=n.last_changed, last_updated=n.last_updated, last_reported=n.last_reported - timedelta(seconds=200))
    skriv = lambda v: hass.services.async_call('input_number', 'set_value', {'entity_id': 'input_number.wattlas_spf_skrivninger', 'value': v}, blocking=True)
    await skriv(40); gammel()
    assert await skub() == [], ordrer
    await skriv(5); gammel()
    assert await skub() == [('max_grid_charge_current', '60')], ordrer
    # stop: laderen først, med det samme; og ingen gem/fri-skift inden for 10 minutter, selv om solen kommer
    ordrer.clear(); sæt('input_boolean.wattlas_spf_netladning', 'off'); await hass.async_block_till_done()
    assert ordrer == [('charger_source_priority', GEM)], ordrer
    assert await skub({'sensor.min_spf_sol': 3000}) == [], ordrer
    # døgnloftet: ingen ny netladning efter 40 skrivninger – men stop og tilbagelevering er altid tilladt
    await hass.services.async_call('input_number', 'set_value', {'entity_id': 'input_number.wattlas_spf_skrivninger', 'value': 40}, blocking=True)
    ordrer.clear(); sæt('input_boolean.wattlas_spf_netladning', 'on'); await hass.async_block_till_done()
    assert ordrer == [], ordrer
    sæt('input_boolean.wattlas_spf_netladning', 'off'); await hass.async_block_till_done()
    ordrer.clear(); fælles(hass, 'spf', 50, netlad='off', styrer='off'); await hass.async_block_till_done()
    await skub()
    assert hass.states.get('sensor.min_spf_output').state == 'Solar first' and hass.states.get('sensor.min_spf_lader').state == 'Solar first' \
        and hass.states.get('sensor.min_spf_netstroem').state == '30', 'dine egne indstillinger skal tilbage'
    await skub()
    assert hass.states.get('input_boolean.wattlas_spf_styret').state == 'off' and await skub() == []
    # skygge (styring til, men ikke overtaget): intet
    sæt('input_boolean.emhass_styring_aktiv', 'on'); await hass.async_block_till_done()
    assert await skub() == [], ordrer
    # flere udløsere på én gang giver én skrivning; en afvist ordre gentages ikke for evigt
    await hass.services.async_call('input_number', 'set_value', {'entity_id': 'input_number.wattlas_spf_skrivninger', 'value': 0}, blocking=True)
    ordrer.clear(); fælles(hass, 'spf', 50, netlad='off'); await hass.async_block_till_done()
    assert len(ordrer) == 2, ordrer
    afvis.append(1); ordrer.clear(); sæt('input_boolean.wattlas_spf_netladning', 'on'); await hass.async_block_till_done()
    assert ('charger_source_priority', LAD) in ordrer, ordrer
    o = hass.states.get('input_text.wattlas_spf_oensket')
    hass.states._states['input_text.wattlas_spf_oensket'] = type(o)(o.entity_id, o.state, o.attributes, last_changed=o.last_changed - timedelta(seconds=400))
    k = await skub()
    if datetime.now().minute % 10:
        assert k == [], k
    await hass.async_stop(force=True)
    print('SPF: overtagelse, sjældne skrivninger, døgnloft, stop og tilbagelevering: OK')


async def main():
    await langsom()
    await solax()
    await sofar()
    await solis()
    await spf()

asyncio.run(main())
