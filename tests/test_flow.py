# Wattlas' opsætning, overførsel af indstillinger, opdatering og fjernelse i en rigtig (minimal) Home Assistant.
# Kør: python tests/test_flow.py   (kræver: pip install homeassistant)
import asyncio, pathlib, shutil, sys, tempfile, types
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


async def ny_hass(conf):
    cfg = pathlib.Path(tempfile.mkdtemp())
    (cfg / 'configuration.yaml').write_text(conf, encoding='utf-8')
    shutil.copytree(REPO / 'custom_components', cfg / 'custom_components')
    hass = core.HomeAssistant(str(cfg))
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    assert await bootstrap.async_load_base_functionality(hass)
    hass.config.language = 'da'
    hass.config.components.add('repairs')  # rigtig HA har den altid (default_config); her uden http-server
    hass.set_state(core.CoreState.running)
    t0 = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
    hass.states.async_set('sensor.energi_data_service', '1.5', {'raw_today': []})
    hass.states.async_set('binary_sensor.workday_sensor', 'on')
    hass.states.async_set('sensor.helios_power_now', '0', {'forecast': [{'datetime': (t0 + timedelta(minutes=15 * i)).isoformat(), 'watts': 0} for i in range(96)]})
    hass.states.async_set('weather.test', 'sunny', {'temperature': 5})
    return hass, cfg


async def forloeb(kanal, inverter, inv2=None, conf='default_config:\n'):
    hass, cfg = await ny_hass(conf)
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
    return hass, cfg


def issue(hass, navn):
    return ir.async_get(hass).async_get_issue('wattlas', navn)


def fang_kald(hass):
    """Erstatter hjælpernes tjenester og husker kaldene. turn_off slår også 'har overtaget' fra, som hovedafbryderen gør."""
    kald = []

    async def fang(call):
        kald.append((call.domain, call.service, call.data.get('entity_id'), call.data.get('value')))
        if call.service == 'turn_off':
            for e in (STYRING, OVERTAGET):
                hass.states.async_set(e, 'off')
    for dom, tj in (('input_number', 'set_value'), ('input_text', 'set_value'), ('input_boolean', 'turn_on'), ('input_boolean', 'turn_off')):
        hass.services.async_register(dom, tj, fang)
    return kald


async def genindlaes(hass):
    entry = hass.config_entries.async_entries('wattlas')[0]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    return hass.config_entries.async_entries('wattlas')[0]


async def main():
    # A: Deye, én inverter → overførsel én gang → fjernelse
    hass, cfg = await forloeb('deye', 'sensor.min_inverter_pv_power', conf='homeassistant:\n  name: Test\n')
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
    hass.states.async_set('input_text.wattlas_emhass_noegle', '')
    hass.states.async_set('input_boolean.emhass_fuld_opladning', 'off')
    entry = await genindlaes(hass)
    assert ('input_number', 'set_value', 'input_number.wattlas_batteri_kwh', 20) in kald
    assert ('input_number', 'set_value', 'input_number.wattlas_slid', 0.25) in kald
    assert not any(k[2] == 'input_number.wattlas_fase_graense_a' for k in kald)
    assert ('input_text', 'set_value', 'input_text.wattlas_emhass_noegle', 'hemmelig123') in kald
    assert ('input_boolean', 'turn_on', 'input_boolean.emhass_fuld_opladning', None) in kald
    assert issue(hass, 'genstart') is None
    assert 'emhass_noegle' not in entry.data and entry.data['overfoert'], 'nøglen må ikke blive liggende i integrationen'
    kald.clear()
    await genindlaes(hass)
    assert not kald, 'indstillingerne overføres kun én gang'
    print('A opsætning og overførsel: OK')
    hass.states.async_set(STYRING, 'on'); hass.states.async_set(OVERTAGET, 'on')
    await hass.config_entries.async_remove(entry.entry_id); await hass.async_block_till_done()
    assert ('input_boolean', 'turn_off', STYRING, None) in kald, 'styringen skal slås fra, før filerne flyttes'
    assert not (cfg / 'packages/wattlas').exists() and list(cfg.glob('wattlas_backup_*/packages_wattlas'))
    assert issue(hass, 'fjernet') is not None and not issue(hass, 'fjernet').is_persistent
    print('A fjernelse: OK')
    await hass.async_stop(force=True)

    # B: Deye + ekstra AC-koblet inverter → opdatering → opdatering der fejler
    hass, cfg = await forloeb('deye', 'sensor.min_inverter_pv_power',
                              {'inverter2_navn': 'SMA', 'inverter2_tilslutning': 'ac', 'inverter2_effekt': 'sensor.sma_power'})
    assert "states('sensor.sma_power')" in (cfg / 'packages/wattlas_kanal/wattlas_kanal_deye.yaml').read_text(encoding='utf-8')
    assert 'inverter2_prefix: sma_' in (cfg / 'wattlas/dashboards/wattlas_styring.yaml').read_text(encoding='utf-8')
    print('B ekstra AC-inverter: OK')
    entry = hass.config_entries.async_entries('wattlas')[0]
    ny_version = entry.data['version']
    fil = cfg / 'packages/wattlas/emhass_forbindelse.yaml'
    ir.async_delete_issue(hass, 'wattlas', 'genstart')
    fil.write_text('# gammel\n', encoding='utf-8')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass)
    assert 'gammel' not in fil.read_text(encoding='utf-8') and issue(hass, 'genstart') is not None
    assert entry.data['version'] == ny_version and list(cfg.glob('wattlas_backup_*/packages_wattlas'))
    fang_kald(hass)  # efter genstarten: overførslen må ikke skrive den gamle version tilbage (ellers geninstalleres der ved hver start)
    hass.states.async_set('binary_sensor.wattlas_konfigureret', 'on')
    backups = len(list(cfg.glob('wattlas_backup_*')))
    entry = await genindlaes(hass)
    assert entry.data['version'] == ny_version and entry.data['overfoert'] and len(list(cfg.glob('wattlas_backup_*'))) == backups
    print('B opdatering: OK')

    async def tjek_fejler(_hass):
        return types.SimpleNamespace(errors=[types.SimpleNamespace(message='testfejl')])
    sys.modules['custom_components.wattlas'].async_check_ha_config_file = tjek_fejler
    await asyncio.sleep(1.1)  # backup-mappen navngives pr. sekund
    fil.write_text('# gammel\n', encoding='utf-8')
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '0.0.1'})
    entry = await genindlaes(hass)
    assert 'gammel' in fil.read_text(encoding='utf-8'), 'den gamle version skal lægges tilbage'
    assert entry.data['version'] == '0.0.1' and issue(hass, 'opdatering_fejlede') is not None
    print('B opdatering der fejler: OK')
    await hass.async_stop(force=True)

    # C: SunMate
    hass, cfg = await forloeb('sunmate', 'number.min_sunmate_timepoint_1_power')
    assert (cfg / 'packages/wattlas_kanal/wattlas_kanal_sunmate.yaml').exists()
    assert 'homeassistant:' in (cfg / 'configuration.yaml').read_text(encoding='utf-8')
    print('C SunMate: OK')
    await hass.async_stop(force=True)

asyncio.run(main())
