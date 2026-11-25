# Wattlas' opsætning, overførsel af indstillinger, opdatering og fjernelse i en rigtig (minimal) Home Assistant.
# Kør: python tests/test_flow.py   (kræver: pip install homeassistant)
import asyncio, json, os, pathlib, shutil, sys, tempfile, time, types
if sys.platform == 'win32':  # Home Assistant importerer to moduler, der kun findes på Linux
    for m in ('fcntl', 'resource'):
        mod = types.ModuleType(m); mod.__getattr__ = lambda n: (lambda *a, **k: (0, 0)); sys.modules[m] = mod
from datetime import datetime, timedelta
from homeassistant import bootstrap, config_entries, core, loader
from homeassistant.helpers import issue_registry as ir

REPO = pathlib.Path(__file__).parent.parent
TAL = {'batteri': {'batteri_kwh': 20, 'maks_ladeeffekt_w': 10000, 'maks_afladeeffekt_w': 10000, 'maks_ladestroem_a': 200,
                   'maks_afladestroem_a': 200, 'maks_netladestroem_a': 100, 'maks_netladeeffekt_w': 6000},
       'elnet': {'fase_graense_a': 16, 'import_graense_w': 11000, 'maks_netimport_w': 9000, 'maks_eksport_w': 6000},
       'priser': {'nettarif_lav': 0.1, 'nettarif_hoej': 0.3, 'nettarif_spids': 0.9, 'elafgift': 0.8}}
STYRING, OVERTAGET = 'input_boolean.emhass_styring_aktiv', 'input_boolean.emhass_har_overtaget'
GENSTART = 'wattlas_genstart_mangler'


async def ny_hass(conf):
    cfg = pathlib.Path(tempfile.mkdtemp())
    (cfg / 'configuration.yaml').write_text(conf, encoding='utf-8')
    shutil.copytree(REPO / 'custom_components', cfg / 'custom_components')
    hass = core.HomeAssistant(str(cfg))
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    assert await bootstrap.async_load_base_functionality(hass)
    hass.config.language = 'da'
    hass.config.skip_pip = True  # testen installerer ikke Python-pakker (fx app-oversigtens), som en rigtig HA har i forvejen
    hass.config.components.add('repairs')  # rigtig HA har den altid (default_config); her uden http-server
    hass.set_state(core.CoreState.running)
    t0 = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
    hass.states.async_set('sensor.energi_data_service', '1.5', {'raw_today': []})
    hass.states.async_set('binary_sensor.workday_sensor', 'on')
    hass.states.async_set('sensor.helios_power_now', '0', {'forecast': [{'datetime': (t0 + timedelta(minutes=15 * i)).isoformat(), 'watts': 0} for i in range(96)]})
    hass.states.async_set('weather.test', 'sunny', {'temperature': 5})
    return hass, cfg


async def opsaet(hass, kanal, inverter, inv2=None):
    """Går hele opsætningen igennem, som brugeren gør det i vinduet."""
    hass.states.async_set(inverter, '0')
    fm = hass.config_entries.flow
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': kanal})
    r = await fm.async_configure(r['flow_id'], {'inverter': inverter, 'inverter2': bool(inv2)})
    if inv2:
        assert r['step_id'] == 'inverter2', r
        fejl = await fm.async_configure(r['flow_id'], {'inverter2_tilslutning': 'ac'})  # AC uden sensor skal afvises
        assert fejl['errors'] == {'inverter2_effekt': 'mangler_effekt'}, fejl
        fejl = await fm.async_configure(r['flow_id'], {**inv2, 'inverter2_navn': 'SMA "stor"'})  # navnet skrives i YAML
        assert fejl['errors'] == {'inverter2_navn': 'navn_tegn'}, fejl
        r = await fm.async_configure(r['flow_id'], inv2)
    assert r['step_id'] == 'tjek', r
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    for t in ('batteri', 'elnet', 'priser'):
        assert r.get('step_id') == t, r
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()


def alle_tilstande(hass):
    return json.dumps([s.as_dict() for s in hass.states.async_all()], default=str)


def issue(hass, navn):
    return ir.async_get(hass).async_get_issue('wattlas', navn)


def fang_kald(hass, selvforbrug=True):
    """Erstatter hjælpernes tjenester og husker kaldene. turn_off slår også 'har overtaget' fra, som hovedafbryderen gør –
    undtagen med selvforbrug=False, som svarer til en inverter, der ikke svarer."""
    kald = []

    async def fang(call):
        kald.append((call.domain, call.service, call.data.get('entity_id'), call.data.get('value')))
        if call.service == 'turn_off':
            hass.states.async_set(STYRING, 'off')
            if selvforbrug:
                hass.states.async_set(OVERTAGET, 'off')
    for dom, tj in (('input_number', 'set_value'), ('input_text', 'set_value'), ('input_boolean', 'turn_on'), ('input_boolean', 'turn_off')):
        hass.services.async_register(dom, tj, fang)
    return kald


async def genindlaes(hass, genstart=False):
    """Indlæser integrationen igen. genstart=True svarer til, at Home Assistant er genstartet (hukommelsen er tom)."""
    if genstart:
        hass.data.pop(GENSTART, None)
    entry = hass.config_entries.async_entries('wattlas')[0]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    return hass.config_entries.async_entries('wattlas')[0]


async def main():
    W = None  # integrationens modul, når det er indlæst

    # A: Deye, én inverter → overførsel én gang → fjernelse → tilføjet igen uden genstart
    hass, cfg = await ny_hass('homeassistant:\n  name: Test\n')
    await opsaet(hass, 'deye', 'sensor.min_inverter_pv_power')
    W = sys.modules['custom_components.wattlas']
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert issue(hass, 'genstart') is not None
    assert entry.data['tal']['slid'] == 0.25, 'slidprisen skal være forudfyldt'
    assert 'packages: !include_dir_named packages' in (cfg / 'configuration.yaml').read_text(encoding='utf-8')
    r = await hass.config_entries.flow.async_init('wattlas', context={'source': 'user'})
    assert r['type'] == 'abort', 'kun én opsætning'
    kald = fang_kald(hass)  # "efter genstart": hjælperne findes nu (tomme)
    hass.states.async_set('binary_sensor.wattlas_konfigureret', 'off')
    hass.states.async_set('input_number.wattlas_batteri_kwh', '0.0')
    hass.states.async_set('input_number.wattlas_slid', '0.0')
    hass.states.async_set('input_number.wattlas_fase_graense_a', '18.0')  # allerede sat af brugeren – må ikke overskrives
    hass.states.async_set('input_boolean.emhass_fuld_opladning', 'off')
    entry = await genindlaes(hass, genstart=True)
    assert ('input_number', 'set_value', 'input_number.wattlas_batteri_kwh', 20) in kald
    assert ('input_number', 'set_value', 'input_number.wattlas_slid', 0.25) in kald
    assert not any(k[2] == 'input_number.wattlas_fase_graense_a' for k in kald)
    assert not any('wattlas_emhass_' in str(k[2]) or 'hemmelig123' in str(k[3]) for k in kald), 'nøgle og adresse må ikke sættes som tilstand'
    assert ('input_boolean', 'turn_on', 'input_boolean.emhass_fuld_opladning', None) in kald
    assert issue(hass, 'genstart') is None
    assert entry.data['emhass_noegle'] == 'hemmelig123' and 'slid' in entry.data['overfoert'], 'nøglen ligger kun i integrationens opsætning'
    assert 'hemmelig123' not in alle_tilstande(hass)
    kald.clear()
    await genindlaes(hass, genstart=True)
    assert not kald, 'indstillingerne overføres kun én gang'
    # en senere version får en ny indstilling med standardværdi: den skal nå en opsætning, der allerede er overført
    W.STANDARD['ny_ting'] = 5
    hass.states.async_set('input_number.wattlas_ny_ting', '0.0')
    entry = await genindlaes(hass, genstart=True)
    assert kald == [('input_number', 'set_value', 'input_number.wattlas_ny_ting', 5)], kald
    assert 'ny_ting' in entry.data['overfoert']
    del W.STANDARD['ny_ting']
    print('A opsætning og overførsel: OK')
    kald.clear()
    hass.states.async_set(STYRING, 'on'); hass.states.async_set(OVERTAGET, 'on')
    await hass.config_entries.async_remove(entry.entry_id); await hass.async_block_till_done()
    assert ('input_boolean', 'turn_off', STYRING, None) in kald, 'styringen skal slås fra, før filerne flyttes'
    assert not (cfg / 'packages/wattlas').exists() and list(cfg.glob('wattlas_backup_*/packages_wattlas'))
    assert issue(hass, 'fjernet').translation_key == 'fjernet' and not issue(hass, 'fjernet').is_persistent
    print('A fjernelse: OK')
    # tilføjet igen uden genstart: de gamle pakker (og sensoren) lever stadig i hukommelsen
    kald.clear()
    await opsaet(hass, 'deye', 'sensor.min_inverter_pv_power')
    assert issue(hass, 'genstart') is not None, 'der skal stadig bedes om genstart'
    assert not kald, 'intet må overføres til de gamle hjælpere'
    await genindlaes(hass)  # "Genindlæs" på integrationen er ikke en genstart
    assert issue(hass, 'genstart') is not None and not kald
    hass.states.async_set('input_number.wattlas_batteri_kwh', '0.0')
    await genindlaes(hass, genstart=True)
    assert issue(hass, 'genstart') is None and ('input_number', 'set_value', 'input_number.wattlas_batteri_kwh', 20) in kald
    print('A tilføjet igen uden genstart: OK')
    await hass.async_stop(force=True)

    # B: Deye + ekstra AC-koblet inverter → opdatering → opdatering der fejler
    hass, cfg = await ny_hass('default_config:\n')
    await opsaet(hass, 'deye', 'sensor.min_inverter_pv_power',
                 {'inverter2_navn': 'SMA', 'inverter2_tilslutning': 'ac', 'inverter2_effekt': 'sensor.sma_power'})
    assert "states('sensor.sma_power')" in (cfg / 'packages/wattlas_kanal/wattlas_kanal_deye.yaml').read_text(encoding='utf-8')
    assert 'inverter2_prefix: sma_' in (cfg / 'wattlas/dashboards/wattlas_styring.yaml').read_text(encoding='utf-8')
    print('B ekstra AC-inverter: OK')
    fang_kald(hass)
    hass.states.async_set('binary_sensor.wattlas_konfigureret', 'on')
    entry = await genindlaes(hass, genstart=True)
    ny_version = entry.data['version']
    fil = cfg / 'packages/wattlas/emhass_forbindelse.yaml'
    fil.write_text('# gammel\n', encoding='utf-8')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)  # genstart efter at markedspladsen har hentet en ny version
    assert 'gammel' not in fil.read_text(encoding='utf-8')
    assert issue(hass, 'genstart') is not None, 'efter en opdatering skal brugeren bedes om at genstarte'
    assert entry.data['version'] == ny_version and list(cfg.glob('wattlas_backup_*/packages_wattlas'))
    # efter genstarten: reparationen væk, ingen ny installation, og overførslen har ikke skrevet den gamle version tilbage
    backups = len(list(cfg.glob('wattlas_backup_*')))
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'genstart') is None
    assert entry.data['version'] == ny_version and len(list(cfg.glob('wattlas_backup_*'))) == backups
    print('B opdatering: OK')

    async def tjek_fejler(_hass):
        return types.SimpleNamespace(errors=[types.SimpleNamespace(message='testfejl')])
    rigtigt_tjek, W.async_check_ha_config_file = W.async_check_ha_config_file, tjek_fejler
    await asyncio.sleep(1.1)  # backup-mappen navngives pr. sekund
    fil.write_text('# gammel\n', encoding='utf-8')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert 'gammel' in fil.read_text(encoding='utf-8'), 'den gamle version skal lægges tilbage'
    assert entry.data['version'] == '0.0.1' and issue(hass, 'opdatering_fejlede') is not None
    W.async_check_ha_config_file = rigtigt_tjek
    print('B opdatering der fejler: OK')
    await hass.async_stop(force=True)

    # C: SunMate → fjernelse, hvor inverteren ikke svarer
    hass, cfg = await ny_hass('default_config:\n')
    await opsaet(hass, 'sunmate', 'number.min_sunmate_timepoint_1_power')
    assert (cfg / 'packages/wattlas_kanal/wattlas_kanal_sunmate.yaml').exists()
    assert 'homeassistant:' in (cfg / 'configuration.yaml').read_text(encoding='utf-8')
    print('C SunMate: OK')
    fang_kald(hass, selvforbrug=False)
    W.VENT_S = 2
    hass.states.async_set(STYRING, 'on'); hass.states.async_set(OVERTAGET, 'on')
    await hass.config_entries.async_remove(hass.config_entries.async_entries('wattlas')[0].entry_id); await hass.async_block_till_done()
    assert issue(hass, 'fjernet').translation_key == 'fjernet_tjek', 'brugeren skal have at vide, at inverteren ikke svarede'
    print('C fjernelse uden svar fra inverteren: OK')
    await hass.async_stop(force=True)

    # D: Huawei – tre enheder, A-grænser udregnes fra W, og en opdatering bruger de samme enheder
    hass, cfg = await ny_hass('default_config:\n')
    for e in ('sensor.inverter_input_power', 'sensor.batteries_state_of_capacity', 'sensor.power_meter_active_power'):
        hass.states.async_set(e, '0')
    fm = hass.config_entries.flow
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'huawei'})
    r = await fm.async_configure(r['flow_id'], {'inverter': 'sensor.inverter_input_power', 'inverter2': False})
    assert r['step_id'] == 'huawei', r
    fejl = await fm.async_configure(r['flow_id'], {'batteri': 'sensor.power_meter_active_power', 'maaler': 'sensor.power_meter_active_power'})
    assert fejl['errors'] == {'batteri': 'forkert_entitet'}, fejl
    r = await fm.async_configure(r['flow_id'], {'batteri': 'sensor.batteries_state_of_capacity', 'maaler': 'sensor.power_meter_active_power'})
    assert r['step_id'] == 'tjek', r
    assert 'number.batteries_maximum_discharging_power' in r['description_placeholders']['liste'] or 'entiteter' in r['description_placeholders']['liste']
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    assert r['step_id'] == 'batteri' and not any(str(k).endswith('_a') for k in r['data_schema'].schema), 'Huawei spørges ikke om A'
    hb = {k: v for k, v in TAL['batteri'].items() if not k.endswith('_a')}
    r = await fm.async_configure(r['flow_id'], hb)
    for t in ('elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert entry.data['ekstra'] == {'min_luna': 'batteries', 'min_hmaaler': 'power_meter'}, entry.data
    assert entry.data['tal']['maks_ladestroem_a'] == 200 and entry.data['tal']['maks_netladestroem_a'] == 120  # 10000/50, 6000/50
    kanal = (cfg / 'packages/wattlas_kanal/wattlas_kanal_huawei.yaml').read_text(encoding='utf-8')
    assert 'sensor.batteries_state_of_capacity' in kanal and 'min_luna_' not in kanal
    print('D Huawei: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None, 'opdateringen skal kende batteri og elmåler'
    assert entry.data['version'] != '0.0.1' and 'sensor.power_meter_active_power' in \
        (cfg / 'packages/wattlas_kanal/emhass_maalinger.yaml').read_text(encoding='utf-8')
    print('D Huawei opdatering: OK')
    await hass.async_stop(force=True)

    # E: Huawei med EMMA (ekstern måler = "_2") – opsætning og opdatering
    hass, cfg = await ny_hass('default_config:\n')
    for e in ('sensor.inverter_input_power', 'sensor.batteries_state_of_capacity', 'sensor.emma_feed_in_power',
              'sensor.emma_phase_a_active_power_2'):
        hass.states.async_set(e, '0')
    fm = hass.config_entries.flow
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'huawei'})
    r = await fm.async_configure(r['flow_id'], {'inverter': 'sensor.inverter_input_power', 'inverter2': False})
    assert r['step_id'] == 'huawei', r
    fejl = await fm.async_configure(r['flow_id'], {'elmaaler': 'emma', 'batteri': 'sensor.batteries_state_of_capacity',
                                                   'maaler': 'sensor.emma_load_power'})  # en anden EMMA-sensor end Feed in power
    assert fejl['errors'] == {'maaler': 'forkert_emma'}, fejl
    r = await fm.async_configure(r['flow_id'], {'elmaaler': 'emma', 'batteri': 'sensor.batteries_state_of_capacity',
                                                'maaler': 'sensor.emma_feed_in_power', 'ekstern_maaler': True})
    assert r['step_id'] == 'tjek', r
    assert 'sensor.emma_phase_a_active_power_2' in r['description_placeholders']['liste'] or 'entiteter' in r['description_placeholders']['liste'], 'slåede-fra fasesensorer skal nævnes'
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    assert r['step_id'] == 'batteri' and not any(str(k).endswith('_a') for k in r['data_schema'].schema), 'EMMA spørges ikke om A'
    r = await fm.async_configure(r['flow_id'], {k: v for k, v in TAL['batteri'].items() if not k.endswith('_a')})
    for t in ('elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert entry.data['kanal'] == 'huawei_emma' and entry.data['ekstra'] == {'min_luna': 'batteries', 'min_hmaaler': 'emma|_2', 'min_emma': 'emma'}, entry.data
    assert entry.data['tal']['maks_ladestroem_a'] == 200
    assert 'sensor.emma_phase_a_active_power_2' in (cfg / 'packages/wattlas_kanal/emhass_maalinger.yaml').read_text(encoding='utf-8')
    print('E Huawei med EMMA: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1'
    assert "device_id('sensor.emma_feed_in_power')" in (cfg / 'packages/wattlas_kanal/wattlas_kanal_huawei.yaml').read_text(encoding='utf-8')
    print('E Huawei med EMMA opdatering: OK')
    await hass.async_stop(force=True)

    # G: Growatt (solax_modbus) – én enhed valgt via batteriets SOC, A-grænser fra W, og opdateringen består HA's konfigurationstjek
    hass, cfg = await ny_hass('default_config:\n')
    fm = hass.config_entries.flow
    hass.states.async_set('sensor.mod_10k_battery_soc', '50')
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'growatt'})
    fejl = await fm.async_configure(r['flow_id'], {'inverter': 'sensor.weather_temp', 'inverter2': False})
    assert fejl['errors'] == {'inverter': 'forkert_entitet'}, fejl
    r = await fm.async_configure(r['flow_id'], {'inverter': 'sensor.mod_10k_battery_soc', 'inverter2': False})
    assert r['step_id'] == 'tjek' and 'select.mod_10k_vpp_status' in r['description_placeholders']['liste'] or 'entiteter' in r['description_placeholders']['liste'], r
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    assert r['step_id'] == 'batteri' and not any(str(k).endswith('_a') for k in r['data_schema'].schema), 'Growatt spørges ikke om A'
    r = await fm.async_configure(r['flow_id'], {k: v for k, v in TAL['batteri'].items() if not k.endswith('_a')})
    for t in ('elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert entry.data['kanal'] == 'growatt' and entry.data['prefix'] == 'mod_10k' and entry.data['tal']['maks_ladestroem_a'] == 200, entry.data
    assert 'number.mod_10k_vpp_power' in (cfg / 'packages/wattlas_kanal/wattlas_kanal_growatt.yaml').read_text(encoding='utf-8')
    print('G Growatt: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1', 'Growatt-kanalen skal bestå konfigurationstjekket'
    print('G Growatt opdatering: OK')
    await hass.async_stop(force=True)

    # X: SolaX (solax_modbus, X3-Hybrid G4) – valgt via batteriets SOC ("Battery Capacity"), A-grænser fra W (højvolt),
    #    og opdateringen består HA's konfigurationstjek
    hass, cfg = await ny_hass('default_config:\n')
    fm = hass.config_entries.flow
    hass.states.async_set('sensor.x3_g4_battery_capacity', '50')
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'solax'})
    r = await fm.async_configure(r['flow_id'], {'inverter': 'sensor.x3_g4_battery_capacity', 'inverter2': False})
    assert r['step_id'] == 'tjek', r
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    assert r['step_id'] == 'batteri' and not any(str(k).endswith('_a') for k in r['data_schema'].schema), 'SolaX spørges ikke om A'
    r = await fm.async_configure(r['flow_id'], {k: v for k, v in TAL['batteri'].items() if not k.endswith('_a')})
    for t in ('elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert entry.data['kanal'] == 'solax' and entry.data['prefix'] == 'x3_g4' and entry.data['tal']['maks_ladestroem_a'] == 200, entry.data
    kanalfil = (cfg / 'packages/wattlas_kanal/wattlas_kanal_solax.yaml').read_text(encoding='utf-8')
    assert 'button.x3_g4_remotecontrol_trigger_mode_1_7' in kanalfil and 'min_solax' not in kanalfil
    print('X SolaX: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1', 'SolaX-kanalen skal bestå konfigurationstjekket'
    print('X SolaX opdatering: OK')
    await hass.async_stop(force=True)

    # Y: Sofar (solax_modbus, Passive Mode) – valgt via "Battery Capacity Total", A-grænser fra W, opdateringen består tjekket
    hass, cfg = await ny_hass('default_config:\n')
    fm = hass.config_entries.flow
    hass.states.async_set('sensor.hyd_battery_capacity_total', '50')
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'sofar'})
    r = await fm.async_configure(r['flow_id'], {'inverter': 'sensor.hyd_battery_capacity_total', 'inverter2': False})
    assert r['step_id'] == 'tjek', r
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    r = await fm.async_configure(r['flow_id'], {k: v for k, v in TAL['batteri'].items() if not k.endswith('_a')})
    for t in ('elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    kanalfil = (cfg / 'packages/wattlas_kanal/wattlas_kanal_sofar.yaml').read_text(encoding='utf-8')
    assert entry.data['prefix'] == 'hyd' and 'button.hyd_passive_update_battery_charge_discharge' in kanalfil and 'min_sofar' not in kanalfil
    print('Y Sofar: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1', 'Sofar-kanalen skal bestå konfigurationstjekket'
    print('Y Sofar opdatering: OK')
    await hass.async_stop(force=True)

    # Z: Solis (solax_modbus, plugin Solis FB00) – valgt via "Remote Dispatch Function Version", opdateringen består tjekket
    hass, cfg = await ny_hass('default_config:\n')
    fm = hass.config_entries.flow
    hass.states.async_set('sensor.s6_remote_dispatch_function_version', '1')
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'solis'})
    r = await fm.async_configure(r['flow_id'], {'inverter': 'sensor.s6_remote_dispatch_function_version', 'inverter2': False})
    assert r['step_id'] == 'tjek', r
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    r = await fm.async_configure(r['flow_id'], {k: v for k, v in TAL['batteri'].items() if not k.endswith('_a')})
    for t in ('elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    kanalfil = (cfg / 'packages/wattlas_kanal/wattlas_kanal_solis.yaml').read_text(encoding='utf-8')
    assert entry.data['prefix'] == 's6' and 'button.s6_apply_remote_dispatch' in kanalfil and 'min_solis' not in kanalfil
    print('Z Solis: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1', 'Solis-kanalen skal bestå konfigurationstjekket'
    print('Z Solis opdatering: OK')
    await hass.async_stop(force=True)

    # SPF: Growatt off-grid via Solar Assistants MQTT – ingen inverter-entitet at vælge, kun et tjek af, at emnerne kommer
    hass, cfg = await ny_hass('default_config:\n')
    fm = hass.config_entries.flow
    CF = sys.modules['custom_components.wattlas.config_flow']
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'spf'})
    assert r['step_id'] == 'spf', r
    r = await fm.async_configure(r['flow_id'], {})
    assert r['errors'] == {'base': 'mqtt_mangler'}, r          # ingen MQTT-integration
    rigtig = CF._sa_svarer

    async def svarer(_hass):
        return None
    CF._sa_svarer = svarer
    r = await fm.async_configure(r['flow_id'], {})
    assert r['step_id'] == 'tjek', r
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    for t in ('batteri', 'elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    CF._sa_svarer = rigtig
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    kanalfil = (cfg / 'packages/wattlas_kanal/wattlas_kanal_spf.yaml').read_text(encoding='utf-8')
    assert entry.data['prefix'] == 'min_spf' and 'solar_assistant/inverter_1/load_power/state' in kanalfil and entry.data['tal'].get('maks_ladestroem_a')
    print('SPF via Solar Assistant: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1', 'SPF-kanalen skal bestå konfigurationstjekket'
    print('SPF opdatering: OK')
    await hass.async_stop(force=True)

    # E2: Deye via ESPHome – valgt via PV1 Power, A-grænser spørges om (lavvolt), og opdateringen består konfigurationstjekket
    hass, cfg = await ny_hass('default_config:\n')
    await opsaet(hass, 'deye_esphome', 'sensor.sun12k_pv1_power')
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert entry.data['kanal'] == 'deye_esphome' and entry.data['prefix'] == 'sun12k', entry.data
    assert 'switch.sun12k_time_point_3_charge_enable' in (cfg / 'packages/wattlas_kanal/wattlas_kanal_deye.yaml').read_text(encoding='utf-8')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1', 'ESPHome-kanalen skal bestå konfigurationstjekket'
    print('E2 Deye via ESPHome + opdatering: OK')
    await hass.async_stop(force=True)

    # R: skift af styrekanal (fx Huawei → Growatt) efterlader registreringer; de gamle fjernes, og "_2"-tvillingen får navnet tilbage
    hass, cfg = await ny_hass('default_config:\n')
    from homeassistant.helpers import entity_registry as er
    reg = er.async_get(hass)
    W = sys.modules['custom_components.wattlas']
    gammel = reg.async_get_or_create('sensor', 'template', 'wattlas_total_koebt', suggested_object_id='wattlas_total_koebt')
    ny = reg.async_get_or_create('sensor', 'integration', 'wattlas_total_koebt', suggested_object_id='wattlas_total_koebt')
    assert ny.entity_id == 'sensor.wattlas_total_koebt_2', ny.entity_id  # sådan ser fejlen ud
    hass.states.async_set(ny.entity_id, '1.2')
    reg.async_get_or_create('automation', 'automation', 'wattlas_huawei_netladning', suggested_object_id='wattlas_huawei_netladning')
    reg.async_get_or_create('automation', 'automation', 'wattlas_min_egen', suggested_object_id='wattlas_min_egen',
                            disabled_by=er.RegistryEntryDisabler.USER)  # brugerens egen, slået fra: har ingen tilstand
    reg.async_get_or_create('sensor', 'template', 'wattlas_i_dag_ladet', suggested_object_id='wattlas_i_dag_ladet')  # står i filerne
    reg.async_get_or_create('sensor', 'template', 'helt_anden', suggested_object_id='helt_anden')  # ikke Wattlas'
    reg.async_get_or_create('sensor', 'template', 'emhass_min_egen', suggested_object_id='emhass_min_egen')  # brugerens egen EMHASS-sensor
    for uid in ('min_spf_soc', 'min_spf_egen'):  # SPF-kanalens mqtt-sensorer, og brugerens egen med samme forstavelse
        reg.async_get_or_create('sensor', 'mqtt', uid, suggested_object_id=uid)
    for e in ('sensor.wattlas_total_koebt', 'automation.wattlas_huawei_netladning', 'sensor.wattlas_i_dag_ladet', 'sensor.helt_anden',
              'sensor.emhass_min_egen', 'sensor.min_spf_soc', 'sensor.min_spf_egen'):
        hass.states.async_set(e, 'unavailable', {'restored': True})  # sådan står efterladte registreringer efter en genstart
    kendt = sys.modules['custom_components.wattlas.installer'].kendt_tekst()
    assert 'wattlas_huawei_netladning' in kendt and 'emhass_min_egen' not in kendt
    ryddet = W._ryd_efterladte(hass, 'unique_id: wattlas_i_dag_ladet\nunique_id: wattlas_total_koebt\n', kendt)
    assert sorted(ryddet) == ['automation.wattlas_huawei_netladning', 'sensor.min_spf_soc', 'sensor.wattlas_total_koebt'], ryddet
    assert reg.async_get_entity_id('sensor', 'integration', 'wattlas_total_koebt') == 'sensor.wattlas_total_koebt'
    behold = ('sensor.wattlas_i_dag_ladet', 'sensor.helt_anden', 'automation.wattlas_min_egen', 'sensor.emhass_min_egen', 'sensor.min_spf_egen')
    assert all(reg.async_get(e) for e in behold), [e for e in behold if not reg.async_get(e)]
    assert W._ryd_efterladte(hass, '', kendt) == [], 'uden filer (fx midlertidig fejl) må kun tvillinger ryddes'
    print('R kanalskift rydder efterladte registreringer: OK')
    await hass.async_stop(force=True)

    # D2: en anden database end SQLite (fx MariaDB) giver en advarsel i tjekket – husprognosen og historikken bruger SQLite-SQL
    hass, cfg = await ny_hass('default_config:\n')
    CF = sys.modules['custom_components.wattlas.config_flow']
    rigtig_db, CF._database = CF._database, (lambda _h: 'mysql')
    hass.states.async_set('sensor.min_inverter_pv_power', '0')
    r = await hass.config_entries.flow.async_init('wattlas', context={'source': 'user'})
    r = await hass.config_entries.flow.async_configure(r['flow_id'], {'kanal': 'deye'})
    r = await hass.config_entries.flow.async_configure(r['flow_id'], {'inverter': 'sensor.min_inverter_pv_power', 'inverter2': False})
    CF._database = rigtig_db
    assert r['step_id'] == 'tjek' and 'SQLite' in r['description_placeholders']['liste'], r
    assert CF._database(hass) is None, 'uden recorder kendes databasen ikke – ingen advarsel'
    print('D2 advarsel ved anden database end SQLite: OK')
    await hass.async_stop(force=True)

    # P: to Deye i parallel – slaven vælges i et ekstra trin; samme inverter to gange afvises; opdateringen består konfigurationstjekket
    hass, cfg = await ny_hass('default_config:\n')
    for e in ('sensor.deye_m_pv_power', 'sensor.deye_s_pv_power'):
        hass.states.async_set(e, '0')
    fm = hass.config_entries.flow
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'deye_parallel'})
    r = await fm.async_configure(r['flow_id'], {'inverter': 'sensor.deye_m_pv_power', 'inverter2': False})
    assert r['step_id'] == 'slave', r
    fejl = await fm.async_configure(r['flow_id'], {'slave': 'sensor.deye_m_pv_power'})
    assert fejl['errors'] == {'slave': 'samme_inverter'}, fejl
    r = await fm.async_configure(r['flow_id'], {'slave': 'sensor.deye_s_pv_power'})
    assert r['step_id'] == 'tjek', r
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    for t in ('batteri', 'elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert entry.data['ekstra'] == {'min_slave': 'deye_s'} and entry.data['prefix'] == 'deye_m', entry.data
    assert 'number.deye_s_battery_grid_charging_current' in (cfg / 'packages/wattlas_kanal/wattlas_kanal_deye.yaml').read_text(encoding='utf-8')
    print('P Deye i parallel: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1', 'parallel-kanalen skal bestå konfigurationstjekket'
    print('P Deye i parallel opdatering: OK')
    await hass.async_stop(force=True)

    # S: Sonnen – adresse og token i et eget trin (batteriet "svarer" her uden netværk); opdateringen beholder dem
    hass, cfg = await ny_hass('default_config:\n')
    svar = {'kode': 'sonnen_afvist'}
    async def svarer(hass, host, token):
        return svar['kode']
    sys.modules['custom_components.wattlas.config_flow']._sonnen_svarer = svarer
    fm = hass.config_entries.flow
    r = await fm.async_init('wattlas', context={'source': 'user'})
    r = await fm.async_configure(r['flow_id'], {'kanal': 'sonnen'})
    assert r['step_id'] == 'sonnen', r
    fejl = await fm.async_configure(r['flow_id'], {'sonnen_host': '10.0.0.5', 'sonnen_token': 'abcdefgh12'})
    assert fejl['errors'] == {'sonnen_host': 'sonnen_adresse'}, fejl
    fejl = await fm.async_configure(r['flow_id'], {'sonnen_host': 'http://10.0.0.5/', 'sonnen_token': 'abcdefgh12'})
    assert fejl['errors'] == {'base': 'sonnen_afvist'}, fejl
    svar['kode'] = None
    r = await fm.async_configure(r['flow_id'], {'sonnen_host': 'http://10.0.0.5/', 'sonnen_token': 'abcdefgh12'})
    assert r['step_id'] == 'tjek', r
    r = await fm.async_configure(r['flow_id'], {'forstaaet': True})
    r = await fm.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123',
                                               'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    for t in ('batteri', 'elnet', 'priser'):
        r = await fm.async_configure(r['flow_id'], TAL[t])
    assert r['type'] == 'create_entry', r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert entry.data['sonnen'] == {'host': 'http://10.0.0.5', 'token': 'abcdefgh12'} and entry.data['prefix'] == 'min_sonnen', entry.data
    kf = cfg / 'packages/wattlas_kanal/emhass_maalinger.yaml'
    assert 'http://10.0.0.5/api/v2/status' in kf.read_text(encoding='utf-8')
    print('S Sonnen: OK')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'opdatering_fejlede') is None and entry.data['version'] != '0.0.1', 'Sonnen-kanalen skal bestå konfigurationstjekket'
    assert 'http://10.0.0.5/api/v2/status' in kf.read_text(encoding='utf-8'), 'opdateringen mistede adressen'
    print('S Sonnen opdatering: OK')
    # Konfigurer → Sonnen: ny adresse (ny IP fra routeren), tomt token = behold; filerne skrives igen, og der bedes om genstart
    om = hass.config_entries.options
    hass.data.pop(GENSTART, None); ir.async_delete_issue(hass, 'wattlas', 'genstart')
    r = await om.async_init(entry.entry_id)
    assert 'sonnen' in r['menu_options'], r
    r = await om.async_configure(r['flow_id'], {'next_step_id': 'sonnen'})
    svar['kode'] = 'sonnen_svarer_ikke'
    fejl = await om.async_configure(r['flow_id'], {'sonnen_host': 'http://10.0.0.9'})
    assert fejl['errors'] == {'base': 'sonnen_svarer_ikke'} and 'http://10.0.0.5/api' in kf.read_text(encoding='utf-8'), fejl
    svar['kode'] = None
    r = await om.async_configure(r['flow_id'], {'sonnen_host': 'http://10.0.0.9'})
    assert r['type'] == 'create_entry', r
    entry = hass.config_entries.async_entries('wattlas')[0]
    assert entry.data['sonnen'] == {'host': 'http://10.0.0.9', 'token': 'abcdefgh12'}, entry.data['sonnen']
    tekst = kf.read_text(encoding='utf-8')
    assert 'http://10.0.0.9/api/v2/status' in tekst and '10.0.0.5' not in tekst and 'Auth-Token: "abcdefgh12"' in tekst
    assert issue(hass, 'genstart') is not None and hass.data.get(GENSTART), 'en ny adresse kræver genstart'
    print('S Sonnen ny adresse i Konfigurer: OK')
    await hass.async_stop(force=True)

    # K: Konfigurer – felterne er udfyldt med de nuværende værdier, ændringer skrives til hjælperne og huskes i opsætningen
    hass, cfg = await ny_hass('default_config:\n')
    await opsaet(hass, 'deye', 'sensor.min_inverter_pv_power')
    kald = fang_kald(hass)
    hass.states.async_set('input_number.wattlas_fase_graense_a', '16')
    hass.states.async_set('input_text.wattlas_solprognose_entitet', 'sensor.helios_power_now')
    hass.states.async_set('input_text.wattlas_vejr_entitet', 'weather.test')
    entry = hass.config_entries.async_entries('wattlas')[0]
    om = hass.config_entries.options
    r = await om.async_init(entry.entry_id)
    assert r['type'] == 'menu' and set(r['menu_options']) == {'forbindelser', 'batteri', 'elnet', 'priser'}, r
    r = await om.async_configure(r['flow_id'], {'next_step_id': 'elnet'})
    standard = {str(k): k.default() for k in r['data_schema'].schema if callable(getattr(k, 'default', None))}
    assert standard.get('fase_graense_a') == 16.0, standard  # den nuværende værdi, ikke opsætningens
    fejl = await om.async_configure(r['flow_id'], {'fase_graense_a': 0, 'import_graense_w': 11000, 'maks_netimport_w': 11000, 'maks_eksport_w': 9000})
    assert fejl['errors'] == {'fase_graense_a': 'over_nul'}, fejl
    r = await om.async_configure(r['flow_id'], {'fase_graense_a': 18, 'import_graense_w': 11000, 'maks_netimport_w': 11000, 'maks_eksport_w': 9000})
    assert r['type'] == 'create_entry', r
    assert ('input_number', 'set_value', 'input_number.wattlas_fase_graense_a', 18) in kald, kald
    assert hass.config_entries.async_entries('wattlas')[0].data['tal']['fase_graense_a'] == 18
    # forbindelser: en tom nøgle beholder den nuværende (ingen skrivning til nøgle-hjælperen)
    kald.clear()
    r = await om.async_init(entry.entry_id)
    r = await om.async_configure(r['flow_id'], {'next_step_id': 'forbindelser'})
    r = await om.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5001', 'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    assert r['type'] == 'create_entry', r
    data = lambda: hass.config_entries.async_entries('wattlas')[0].data  # noqa: E731
    assert data()['emhass_noegle'] == 'hemmelig123' and data()['emhass_adresse'] == 'http://emhass:5001'
    assert not [k for k in kald if 'wattlas_emhass_' in k[2]], kald
    # ny nøgle: gemmes i opsætningen – og kun i den gamle hjælper, hvis pakker fra før 0.4.2 stadig kører
    async def skift(noegle):
        r = await om.async_init(entry.entry_id)
        r = await om.async_configure(r['flow_id'], {'next_step_id': 'forbindelser'})
        udfyldt = {str(k): k.default() for k in r['data_schema'].schema if callable(getattr(k, 'default', None))}
        assert udfyldt['emhass_adresse'] == 'http://emhass:5001', 'adressen skal komme fra opsætningen, ikke fra en tilstand'
        return await om.async_configure(r['flow_id'], {'emhass_adresse': 'http://emhass:5001', 'emhass_noegle': noegle,
                                                       'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'})
    hass.states.async_set('input_text.wattlas_emhass_adresse', 'http://fremmed:1')
    for daarlig in ('kort', 'to linjer\nX-Andet: 1'):
        assert (await skift(daarlig))['errors'] == {'emhass_noegle': 'noegle'}
    hass.states.async_remove('input_text.wattlas_emhass_adresse')
    assert (await skift('ny-noegle-{{ 1 }}"'))['type'] == 'create_entry'
    assert data()['emhass_noegle'] == 'ny-noegle-{{ 1 }}"' and not [k for k in kald if 'noegle' in k[2]], kald
    hass.states.async_set('input_text.wattlas_emhass_noegle', 'ny-noegle-{{ 1 }}"')
    assert (await skift('nyeste-noegle'))['type'] == 'create_entry'
    await genindlaes(hass)
    assert data()['emhass_noegle'] == 'ny-noegle-{{ 1 }}"', 'de gamle pakker kører stadig: deres hjælper er den rigtige (kaldet er kun fanget her)'
    hass.states.async_set('input_text.wattlas_emhass_noegle', 'nyeste-noegle')  # som den rigtige tjeneste ville gøre
    await genindlaes(hass)
    assert data()['emhass_noegle'] == 'nyeste-noegle', 'en nøgle fra Konfigurer mellem de to genstarter skal overleve'
    assert ('input_text', 'set_value', 'input_text.wattlas_emhass_noegle', 'nyeste-noegle') in kald
    hass.states.async_remove('input_text.wattlas_emhass_noegle')
    print('K Konfigurer: OK')
    await hass.async_stop(force=True)

    # N: EMHASS-nøglen – migrering fra 0.4.1 (nøglen lå i en hjælper), manglende nøgle og selve kaldet til EMHASS
    from aiohttp import ClientSession, web
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.template import Template
    import yaml
    hass, cfg = await ny_hass('default_config:\n')
    await opsaet(hass, 'deye', 'sensor.deye_x_pv_power')
    W = sys.modules['custom_components.wattlas']
    W.TJEK_S = 10 ** 6
    GL, GLA = 'input_text.wattlas_emhass_noegle', 'input_text.wattlas_emhass_adresse'
    fang_kald(hass)
    hass.states.async_set('binary_sensor.wattlas_konfigureret', 'off')
    entry = hass.config_entries.async_entries('wattlas')[0]
    reg = er.async_get(hass)

    def som_041(tilstand, adresse='http://rettet-i-041:5000', **attr):
        # 0.4.1: nøglen kun i hjælperen, adressen i opsætningen er den fra dengang (0.4.1's Konfigurer rettede kun hjælperen)
        hass.config_entries.async_update_entry(entry, data={**{k: v for k, v in entry.data.items() if k != 'emhass_noegle'},
                                                            'emhass_adresse': 'http://gammel:5000', 'overfoert': ['emhass_adresse', 'emhass_noegle', 'slid']})
        hass.states.async_set(GL, tilstand, attr)
        hass.states.async_set(GLA, adresse, attr)
    # 1) gyldige værdier i de levende hjælpere: flyttes (også før de nye filer lægges på plads)
    som_041('gammel "nøgle" {{x}} 1')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.4.1'})
    rigtig_opdater, set_ved_install = W.installer.opdater, []
    W.installer.opdater = lambda cfg_, data, v: (set_ved_install.append(entry.data.get('emhass_noegle')), rigtig_opdater(cfg_, data, v))[1]
    entry = await genindlaes(hass)
    W.installer.opdater = rigtig_opdater
    assert set_ved_install == ['gammel "nøgle" {{x}} 1'], 'nøglen skal være gemt, før de nye filer lægges på plads'
    assert entry.data['emhass_noegle'] == 'gammel "nøgle" {{x}} 1' and entry.data['emhass_adresse'] == 'http://rettet-i-041:5000'
    assert entry.data['overfoert'] == ['slid'], entry.data['overfoert']
    # rettes hjælperen mellem de to genstarter, er den nye værdi den rigtige
    hass.states.async_set(GL, 'rettet mellem genstarterne')
    entry = await genindlaes(hass)
    assert entry.data['emhass_noegle'] == 'rettet mellem genstarterne'
    # ... og de gamle, døde registreringer ryddes efter genstarten, en levende røres ikke
    for e, uid in ((GL, 'wattlas_emhass_noegle'), (GLA, 'wattlas_emhass_adresse')):
        hass.states.async_remove(e)
        reg.async_get_or_create('input_text', 'input_text', uid, suggested_object_id=uid)
        assert reg.async_get(e) is not None
    hass.states.async_set(GL, 'levende')
    hass.states.async_set(GLA, 'unavailable', {'restored': True})
    entry = await genindlaes(hass, genstart=True)
    assert reg.async_get(GL) is not None and reg.async_get(GLA) is None, 'kun den døde hjælper må fjernes'
    hass.states.async_set(GL, 'unavailable', {'restored': True})
    entry = await genindlaes(hass, genstart=True)
    assert reg.async_get(GL) is None and issue(hass, 'noegle_mangler') is None
    assert 'mellem genstarterne' not in ''.join(f.read_text(encoding='utf-8') for f in cfg.rglob('*.yaml')), 'nøglen må ikke stå i filerne'
    # 2) ingen brugbar nøgle: intet flyttes, og brugeren får besked
    for tilstand, attr in (('', {}), ('unknown', {}), ('unavailable', {}), ('langnok-men-gendannet', {'restored': True})):
        som_041(tilstand, adresse='', **attr)
        entry = await genindlaes(hass, genstart=True)
        assert 'emhass_noegle' not in entry.data and entry.data['emhass_adresse'] == 'http://gammel:5000', tilstand
        assert issue(hass, 'noegle_mangler') is not None
    for e in (GL, GLA):
        hass.states.async_remove(e)
    # kommer nøglen til senere, forsvinder beskeden igen
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'emhass_noegle': 'kom-til-senere'})
    entry = await genindlaes(hass, genstart=True)
    assert issue(hass, 'noegle_mangler') is None
    hass.config_entries.async_update_entry(entry, data={k: v for k, v in entry.data.items() if k != 'emhass_noegle'})
    # 3) kaldet: nøglen sendes i headeren, svaret er som rest_command's – også ved 401 – og fejl viser aldrig nøglen
    set_, status = [], [200]

    async def svar(req):
        set_.append((req.path, req.headers.get('Authorization'), await req.json()))
        return web.Response(status=status[0], text='svaret')
    app = web.Application(); app.router.add_post('/{sti:.*}', svar)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    port = site._server.sockets[0].getsockname()[1]
    sess = ClientSession()  # HA's egen kræver zeroconf og netværk, som denne minimale HA ikke har
    W.emhass.async_get_clientsession = lambda _hass: sess
    kald_emhass = lambda h='publish-data', **d: hass.services.async_call('wattlas', 'emhass', {'handling': h, 'data': d}, blocking=True, return_response=True)  # noqa: E731

    async def afvist(hvad):
        try:
            await hvad
        except HomeAssistantError as e:
            assert 'hemmelig-9' not in str(e) and e.__cause__ is None
            return str(e)
        raise AssertionError('skulle være afvist')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'emhass_adresse': f'http://127.0.0.1:{port}/'})
    assert 'mangler' in await afvist(kald_emhass())
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'emhass_noegle': 'hemmelig-9'})
    hass.states.async_set(GLA, 'http://fremmed.invalid:1')  # en tilstand må ikke kunne sende nøglen et andet sted hen
    assert await kald_emhass('naive-mpc-optim', a=[1.5], b=False) == {'status': 200, 'content': 'svaret'}
    assert set_ == [('/action/naive-mpc-optim', 'Bearer hemmelig-9', {'a': [1.5], 'b': False})], set_
    status[0] = 401
    assert (await kald_emhass())['status'] == 401
    await runner.cleanup()
    assert 'svarede ikke' in await afvist(kald_emhass())
    await sess.close()
    try:
        await kald_emhass('../config')
        raise AssertionError('kun de to handlinger må kaldes')
    except __import__('voluptuous').Invalid:
        pass
    assert 'hemmelig-9' not in alle_tilstande(hass)
    # 4) scriptets skabeloner giver det samme indhold som før (dict, ikke tekst)
    trin = []

    def find(x):
        if isinstance(x, dict):
            if x.get('action') == 'wattlas.emhass':
                trin.append(x['data'])
            for v in x.values(): find(v)
        elif isinstance(x, list):
            for v in x: find(v)
    find(yaml.safe_load((REPO / 'packages/wattlas/emhass_forbindelse.yaml').read_text(encoding='utf-8')))
    assert [t['handling'] for t in trin] == ['naive-mpc-optim', 'naive-mpc-optim', 'publish-data', 'publish-data']
    base = {'method_ts_round': 'first', 'continual_publish': False, 'set_use_battery': True, 'number_of_deferrable_loads': 0}
    forbr = {'number_of_deferrable_loads': 1, 'custom_deferrable_forecast_id': [{'entity_id': 'sensor.p_deferrable0', 'unit_of_measurement': 'W', 'friendly_name': 'Wattlas fleksibel forbruger'}]}
    for t, ekstra in zip(trin[2:], ({'publish_prefix': 'hh_'}, {})):
        assert Template(t['data'], hass).async_render({'fb_ekstra': {}}) == {**base, **ekstra}
        assert Template(t['data'], hass).async_render({'fb_ekstra': {'x': 1}}) == {**base, **ekstra, **forbr}
    r = Template(trin[0]['data'], hass).async_render({'hus': {'ok': True, 'liste': [1, 2]}, 'beregning_basis': {'a': True}, 'fb_ekstra': {'b': 1}, 'hh_ekstra': {}})
    assert r == {'a': True, 'load_forecast_method': 'list', 'load_power_forecast': [1, 2], 'b': 1}, r
    # genforsøget uden den fleksible forbruger (EMHASS svarer 400, når opgaven ikke kan løses)
    r = Template(trin[1]['data'], hass).async_render({'hus': {'ok': True, 'liste': [1, 2]}, 'beregning_basis': {'a': True}, 'fb_ekstra': {'b': 1}, 'hh_ekstra': {'c': 2}})
    assert r == {'a': True, 'load_forecast_method': 'list', 'load_power_forecast': [1, 2], 'c': 2}, r
    # startspærren og stop må ikke afhænge af noget, integrationen selv laver: det forsvinder, før inverteren gives tilbage ved fjernelse
    pakker = ''.join(f.read_text(encoding='utf-8') for f in (REPO / 'packages').rglob('*.yaml'))
    egne = [e.entity_id for e in reg.entities.values() if e.platform == 'wattlas']
    assert not [e for e in egne if e in pakker] and not (REPO / 'custom_components/wattlas/binary_sensor.py').exists(), egne
    # 5) fjernelse: nøglen forsvinder med opsætningen
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service('wattlas', 'emhass') and not hass.config_entries.async_entries('wattlas')
    print('N EMHASS-nøglen: migrering, kald og fjernelse: OK')

    # diagnostik-download: med alt det, fejlsøgning kræver, men uden hemmeligheder, navne og brugerens egne entiteter
    from custom_components.wattlas import diagnostics
    hass, cfg = await ny_hass('homeassistant:\n')
    await opsaet(hass, 'deye', 'sensor.hemmeligvej_12_pv_power', None)
    entry = hass.config_entries.async_entries('wattlas')[0]
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'sonnen': {'host': '10.9.8.7', 'token': 'tok-hemmelig'}})
    hass.states.async_set('binary_sensor.wattlas_konfigureret', 'off', {'mangler': ['input_number.wattlas_slid'], 'friendly_name': 'Hemmeligt navn'})
    hass.states.async_set('sensor.wattlas_regler', '1', {'regler': [{'navn': 'Hemmelig regel'}]})
    hass.states.async_set('input_text.wattlas_besked_handling', 'notify.mobile_app_hemmelig')
    hass.states.async_set('person.hemmelig', 'home')
    hass.states.async_set('automation.wattlas_lad_hemmelig_bil', 'on')
    hass.states.async_set('sensor.p_deferrable0', '3000')
    r = json.dumps(await diagnostics.async_get_config_entry_diagnostics(hass, entry), ensure_ascii=False)
    assert '"kanal": "deye"' in r and 'input_number.wattlas_slid' in r and '"tal"' in r and 'sensor.p_deferrable0' in r and '"emhass_sat": true' in r, r[:600]
    for ord_ in ('hemmelig', 'Hemmelig', '10.9.8.7', 'http://emhass', 'helios_power_now', 'weather.test'):
        assert ord_ not in r, ord_
    print('D diagnostik uden hemmeligheder: OK')

    # Energi Data Service med tariffer slået til: opsætningen spærrer, og en kørende Wattlas får en reparation
    from custom_components.wattlas.config_flow import priser_fejl
    for attr, fejl in (({}, False), ({'tariffs': None, 'use_cent': False, 'unit': 'kWh'}, False), ({'tariffs': {'tariffs': {'0': .1}}}, True), ({'use_cent': True}, True), ({'unit': 'MWh'}, True)):
        hass.states.async_set('sensor.energi_data_service', '1.5', {'raw_today': [], **attr})
        assert priser_fejl(hass) is fejl, attr
    hass2, _ = await ny_hass('homeassistant:\n')
    hass2.states.async_set('sensor.energi_data_service', '1.5', {'raw_today': [], 'tariffs': {'tariffs': {'0': .1}}})
    hass2.states.async_set('sensor.deye_pv_power', '0')
    r = await hass2.config_entries.flow.async_init('wattlas', context={'source': 'user'})
    r = await hass2.config_entries.flow.async_configure(r['flow_id'], {'kanal': 'deye'})
    r = await hass2.config_entries.flow.async_configure(r['flow_id'], {'inverter': 'sensor.deye_pv_power', 'inverter2': False})
    assert r['step_id'] == 'tjek' and 'ren spotpris' in r['description_placeholders']['liste'], r
    r = await hass2.config_entries.flow.async_configure(r['flow_id'], {})
    assert r['step_id'] == 'tjek', r
    await hass2.async_stop(force=True)
    print('D prisvagt: OK')
    await hass.async_stop(force=True)

    # U: én genstart – en nyere version på disken (hentet af Markedspladsen, endnu ikke indlæst) lægges på plads af den
    #    kørende version med den NYE versions installer. Efter genstarten passer kode og filer, så der ikke skal genstartes igen.
    hass, cfg = await ny_hass('default_config:\n')
    await opsaet(hass, 'deye', 'sensor.deye_x_pv_power')
    W = sys.modules['custom_components.wattlas']
    W.TJEK_S = 10 ** 6  # Wattlas' eget minut-tjek må ikke køre i baggrunden samtidig med testens kald (de ville dele samme opdatering)
    entry = await genindlaes(hass, genstart=True)
    her = W.HER  # integrationens mappe på "disken" (den, modulet blev indlæst fra)
    original = pathlib.Path(tempfile.mkdtemp()) / 'wattlas'
    shutil.copytree(her, original, ignore=shutil.ignore_patterns('__pycache__'))
    overblik, installeret = her / 'payload/packages/wattlas/emhass_overblik.yaml', cfg / 'packages/wattlas/emhass_overblik.yaml'

    def hentet(version, tillaeg, alder_s):
        """Som når Markedspladsen har lagt en ny version i mappen for alder_s sekunder siden."""
        m = json.loads((original / 'manifest.json').read_text(encoding='utf-8'))
        (her / 'manifest.json').write_text(json.dumps({**m, 'version': version}), encoding='utf-8')
        overblik.write_text((original / 'payload/packages/wattlas/emhass_overblik.yaml').read_text(encoding='utf-8') + tillaeg, encoding='utf-8')
        t = time.time() - alder_s
        for f in her.rglob('*'):
            if f.is_file():
                os.utime(f, (t, t))

    def backups():
        return len(list(cfg.glob('wattlas_backup_*')))
    try:
        ir.async_delete_issue(hass, 'wattlas', 'genstart')
        hass.data.pop(GENSTART, None)
        # 1) filerne skrives stadig (lige ændret): der ventes
        hentet('9.9.9', '\n# ny-9.9.9\n', 0)
        await W._forbered_opdatering(hass, entry)
        assert entry.data['version'] == W.VERSION and 'ny-9.9.9' not in installeret.read_text(encoding='utf-8'), 'en halvt hentet version må ikke lægges på plads'
        # 2) filerne har ligget stille: den nye version lægges på plads nu, og der bedes om én genstart
        hentet('9.9.9', '\n# ny-9.9.9\n', 100)
        await W._forbered_opdatering(hass, entry)
        assert entry.data['version'] == '9.9.9' and 'ny-9.9.9' in installeret.read_text(encoding='utf-8'), entry.data['version']
        assert '?v=9.9.9' in (cfg / 'packages/wattlas/wattlas_frontend.yaml').read_text(encoding='utf-8')
        assert issue(hass, 'genstart') is not None, 'brugeren skal bedes om (én) genstart'
        # 3) efter genstarten kører den nye kode: filerne passer allerede, så der installeres ikke igen og bedes ikke om genstart
        n = backups()
        rigtig, W.VERSION = W.VERSION, '9.9.9'
        ir.async_delete_issue(hass, 'wattlas', 'genstart')
        entry = await genindlaes(hass, genstart=True)
        W.VERSION = rigtig
        assert backups() == n and issue(hass, 'genstart') is None and issue(hass, 'opdatering_fejlede') is None, 'der blev bedt om en genstart mere'
        # 4) genindlæses Wattlas, mens den gamle kode stadig kører, må den ikke lægge sine egne (gamle) filer tilbage
        hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
        entry = await genindlaes(hass)
        assert backups() == n and entry.data['version'] == '0.0.1', 'den gamle kode installerede oven i den nye version'
        hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '9.9.9'})
        # 5) en ny version, der ikke består konfigurationstjekket: alt rulles tilbage, og der prøves ikke igen før genstarten
        hentet('9.9.10', '\nautomation: {{{\n', 100)
        await W._forbered_opdatering(hass, entry)
        tekst = installeret.read_text(encoding='utf-8')
        assert entry.data['version'] == '9.9.9' and 'ny-9.9.9' in tekst and '{{{' not in tekst, 'den fejlende version blev ikke rullet tilbage'
        n = backups()
        await W._forbered_opdatering(hass, entry)
        assert backups() == n and hass.data[W.FORSOEGT] == '9.9.10'
        # 6) selve konfigurationstjekket går i stykker: også da rulles der tilbage
        async def i_stykker(_hass):
            raise OSError('tjekket kunne ikke køre')
        rigtigt, W.async_check_ha_config_file = W.async_check_ha_config_file, i_stykker
        hentet('9.9.11', '\n# ny-9.9.11\n', 100)
        await W._forbered_opdatering(hass, entry)
        W.async_check_ha_config_file = rigtigt
        assert entry.data['version'] == '9.9.9' and 'ny-9.9.11' not in installeret.read_text(encoding='utf-8'), 'der blev ikke rullet tilbage'
        print('U én genstart ved opdatering: OK')
    finally:
        shutil.copytree(original, her, dirs_exist_ok=True)
    await hass.async_stop(force=True)

    # F: opdateret uden genstart (koden på disken er nyere end den version, HA læste ved start) → opsætningen beder om genstart
    hass, cfg = await ny_hass('default_config:\n')
    CF = sys.modules['custom_components.wattlas.config_flow']
    rigtig, CF.VERSION = CF.VERSION, '99.0.0'
    r = await hass.config_entries.flow.async_init('wattlas', context={'source': 'user'})
    CF.VERSION = rigtig
    assert r['type'] == 'abort' and r['reason'] == 'install_fejl' and 'Genstart' in r['description_placeholders']['fejl'], r
    print('F opdateret uden genstart: OK')
    await hass.async_stop(force=True)

asyncio.run(main())
