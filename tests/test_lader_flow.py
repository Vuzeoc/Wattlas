# Elbil-lader: findes den af sig selv, hele opsætningen i Konfigurer, prøven med målt effekt, og planens anden last i EMHASS-kaldet.
# Kør: python tests/test_lader_flow.py   (kræver: pip install homeassistant)
import asyncio
from datetime import timedelta

from test_flow import REPO, ny_hass
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml


def lader(hass, platform, entiteter, navn='Min lader'):
    """En enhed i registreret med de entiteter, den rigtige integration laver."""
    from homeassistant.config_entries import ConfigEntry
    entry = ConfigEntry(domain=platform, title=platform, data={}, options={}, version=1, minor_version=1, source='user', unique_id=navn, discovery_keys={}, subentries_data=None)
    hass.config_entries._entries[entry.entry_id] = entry
    enhed = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={(platform, navn)}, name=navn)
    for dom, noegle, tilstand, attr in entiteter:
        e = er.async_get(hass).async_get_or_create(dom, platform, f'{navn}_{noegle}', suggested_object_id=f'{navn}_{noegle}', device_id=enhed.id, config_entry=entry)
        hass.states.async_set(e.entity_id, tilstand, attr)
    return enhed.id


W, A = {'unit_of_measurement': 'W', 'device_class': 'power'}, {'unit_of_measurement': 'A', 'min': 6, 'max': 16, 'step': 1}


async def main():
    hass, cfg = await ny_hass('')
    import custom_components.wattlas.lader_find as F
    import custom_components.wattlas.lader as M
    S = hass.states.async_set
    v2c = lader(hass, 'v2c', [('sensor', 'charge_power', '0', W), ('sensor', 'house_power', '500', W), ('number', 'intensity', '16', A), ('number', 'min_current', '6', A),
                              ('switch', 'paused', 'on', {}), ('switch', 'locked', 'off', {}), ('binary_sensor', 'connected', 'on', {'device_class': 'plug'})], 'v2c')
    goe = lader(hass, 'goecharger_api2', [('sensor', 'nrg_11', '0', {**W, 'x': 1}), ('sensor', 'charging_power', '0', W), ('number', 'amp', '16', A), ('select', 'frc', '0', {'options': ['0', '1', '2']}),
                                          ('sensor', 'car_status', '2', {})], 'goe')
    zap = lader(hass, 'zaptec', [('sensor', 'total_charge_power', '0', W), ('sensor', 'charger_operation_mode', 'connected_requesting', {}), ('number', 'available_current', '20', A),
                                 ('number', 'charger_max_current', '16', A), ('number', 'charger_min_current', '6', A), ('switch', 'charger_operation_mode', 'off', {}),
                                 ('switch', 'permanent_cable_lock', 'off', {})], 'zap')
    eas = lader(hass, 'easee', [('sensor', 'power', '0', {**W, 'unit_of_measurement': 'kW'}), ('sensor', 'easee_status', 'awaiting_start', {}), ('switch', 'smart_charging', 'off', {})], 'eas')
    ocp = lader(hass, 'ocpp', [('sensor', 'power_active_import', '0', W), ('sensor', 'power_offered', '0', W), ('sensor', 'transaction_id', '0', {}), ('sensor', 'status_connector', 'Preparing', {}),
                               ('switch', 'charge_control', 'off', {}), ('number', 'maximum_current', '16', A)], 'ocp')
    tes = lader(hass, 'wallbox', [('sensor', 'charging_power', '0', W)], 'kunlaes')  # kan ikke styres
    d = {k: v for k, (_, v) in F.fundne(hass).items()}
    assert set(d) == {v2c, goe, zap, eas, ocp} and tes not in d, d
    assert d[v2c]['effekt'] == 'sensor.v2c_charge_power' and d[v2c]['strom'] == 'number.v2c_intensity' and d[v2c]['til_fra'] == 'switch.v2c_paused' and d[v2c]['omvendt'], d[v2c]
    assert d[v2c]['status'] == 'binary_sensor.v2c_connected'
    assert d[goe]['til_fra'] == 'select.goe_frc' and (d[goe]['til_valg'], d[goe]['fra_valg']) == ('2', '1') and d[goe]['strom'] == 'number.goe_amp' and not d[goe].get('omvendt')
    assert d[zap]['strom'] == 'number.zap_charger_max_current' and d[zap]['til_fra'] == 'switch.zap_charger_operation_mode' and d[zap]['langsom'] and d[zap]['status'] == 'sensor.zap_charger_operation_mode', d[zap]
    assert d[eas]['slags'] == 'easee' and d[eas]['enhed'] == eas and not d[eas].get('til_fra'), d[eas]
    assert d[ocp]['slags'] == 'ocpp' and d[ocp]['devid'] == 'ocp' and d[ocp]['transaktion'] == 'sensor.ocp_transaction_id' and not d[ocp].get('strom') and d[ocp]['effekt'] == 'sensor.ocp_power_active_import', d[ocp]
    assert F.kan(hass, d[eas]) == (True, True) and F.kan(hass, {'slags': 'entiteter', 'til_fra': 'switch.x'}) == (True, False) and F.kan(hass, {'slags': 'entiteter', 'start': 'button.x'}) == (False, False)
    S('number.kun6', 6, {'unit_of_measurement': 'A', 'min': 6, 'max': 16}); S('number.kun0', 6, {'unit_of_measurement': 'A', 'min': 0, 'max': 16})
    assert F.kan(hass, {'slags': 'entiteter', 'strom': 'number.kun6'}) == (False, True) and F.kan(hass, {'slags': 'entiteter', 'strom': 'number.kun0'}) == (True, True), 'et strøm-tal stopper kun, hvis det kan sættes til 0'
    fup = lader(hass, 'alfen_wallbox', [('sensor', 'power_phase_l1', '0', W), ('sensor', 'power_offered', '0', W), ('number', 'min_current', '6', A), ('number', 'circuit_fuse_current', '6', A),
                                        ('switch', 'charge_lock', 'on', {}), ('switch', 'smart_charging_schedule', 'on', {}), ('button', 'restart', 'x', {}), ('sensor', 'wifi_status', 'connected', {})], 'fup')
    assert fup not in F.fundne(hass) and {'effekt', 'strom', 'til_fra', 'start', 'stop', 'status'}.isdisjoint(F.fra_enhed(hass, fup)), F.fra_enhed(hass, fup)
    print('Ladere findes og rollerne gættes (V2C, go-e, Zaptec, Easee, OCPP): OK')

    # --- prøven: en lader, der adlyder – og fire, der ikke gør ---
    f = load_yaml(str(REPO / 'packages/wattlas/wattlas_lader.yaml'))
    g = load_yaml(str(REPO / 'packages/wattlas/wattlas_elbil.yaml'))
    for dom in ('input_select', 'input_number', 'input_datetime', 'template'):
        assert await async_setup_component(hass, dom, {dom: f[dom]}), dom
    for dom in ('input_text', 'input_boolean'):
        assert await async_setup_component(hass, dom, {dom: g[dom]}), dom
    await hass.async_block_till_done()
    fys = {}

    def verden():
        w = fys['a'] * 690 if fys['til'] else 0
        S('sensor.v2c_charge_power', w, W)
        for i in (1, 2, 3):
            S(f'sensor.emhass_m_external_ct_w_l{i}', fys['hus'] + w / 3); S(f'sensor.emhass_m_grid_current_v_l{i}', 230)
        S('sensor.emhass_m_grid_out_total_power', 3 * fys['hus'] + w)

    async def tj(call):
        if call.domain == 'number':
            if fys['lyd_a']:
                fys['a'] = call.data['value']
            S('number.v2c_intensity', call.data['value'], A)
        else:
            til = call.service == 'turn_off'  # pause-kontakt
            if til and fys['lyd_start'] or not til and fys['lyd_stop']:
                fys['til'] = til
        verden()
    for dom, t in (('number', 'set_value'), ('homeassistant', 'turn_on'), ('homeassistant', 'turn_off')):
        hass.services.async_register(dom, t, tj)
    S('input_number.wattlas_fase_graense_a', 23); S('input_number.wattlas_sikring_a', 25); S('input_number.wattlas_import_graense_w', 30000)
    S('binary_sensor.emhass_ui_data_frisk', 'on')

    async def sov(_s):
        verden()
        await asyncio.sleep(0)

    async def proev(**k):
        fys.update({'a': 16, 'til': False, 'lyd_a': True, 'lyd_start': True, 'lyd_stop': True, 'hus': 300, **k}); S('number.v2c_intensity', 16, A)
        S('binary_sensor.v2c_connected', 'on', {'device_class': 'plug'}); verden()
        return await F.proev(hass, {**d[v2c], 'faser': 3}, sov)
    assert await proev() == {'start': True, 'strom': True, 'stop': True} and not fys['til'], fys
    assert fys['a'] == 16, ('prøven giver brugerens strøm tilbage', fys)
    assert await proev(lyd_a=False) == {'start': True, 'strom': False, 'stop': True} and not fys['til']
    assert (await proev(lyd_stop=False))['stop'] is False
    assert await proev(lyd_start=False) == {'start': False, 'strom': False, 'stop': False}
    assert await proev(hus=3400) == {'fejl': 'plads'} and (await proev(hus=2500))['stop'] and await proev(til=True) == {'fejl': 'lader_allerede'}
    S('binary_sensor.emhass_ui_data_frisk', 'off')
    assert await proev() == {'fejl': 'maalinger'}
    S('binary_sensor.emhass_ui_data_frisk', 'on')
    ægte_w, F.Styring._effekt = F.Styring._effekt, (lambda self: None if fys['til'] else 0.0)
    r = await proev()
    assert r['fejl'] == 'effekt_ingen' and not r['stop'] and not fys['til'], ('lader, men melder ingen effekt: stoppes igen', r)
    F.Styring._effekt = ægte_w
    S('binary_sensor.emhass_ui_data_frisk', 'on')
    fys.update(til=False, hus=300); verden(); S('binary_sensor.v2c_connected', 'off')
    assert await F.proev(hass, {**d[v2c], 'faser': 3}, sov) == {'fejl': 'frakoblet'}
    S('binary_sensor.v2c_connected', 'on', {'device_class': 'plug'}); fys.update(til=False, hus=2500); verden()
    assert await F.proev(hass, {**{k: x for k, x in d[v2c].items() if k != 'strom'}, 'faser': 3}, sov) == {'fejl': 'plads'}, 'kan kun tændes: der skal være plads til det hele'
    print('Prøven (adlyder, strøm, stop, start, plads, målinger, frakoblet): OK')

    # --- opsætningen ---
    from homeassistant.config_entries import ConfigEntry
    from custom_components.wattlas.config_flow import WattlasOptionsFlow
    entry = ConfigEntry(domain='wattlas', title='Wattlas', data={'kanal': 'deye', 'prefix': 'min_inverter'}, options={}, version=1, minor_version=1, source='user', unique_id='w',
                        discovery_keys={}, subentries_data=None)
    hass.config_entries._entries[entry.entry_id] = entry

    def flow():
        o = WattlasOptionsFlow(); o.hass, o.handler, o.flow_id, o.context = hass, entry.entry_id, 'x', {}
        return o
    o = flow(); r = await o.async_step_lader()
    assert r['step_id'] == 'lader' and [x['value'] for x in r['data_schema'].schema['lader'].config['options']][-2:] == ['anden', 'ingen'], r
    r = await o.async_step_lader({'lader': v2c})
    assert r['step_id'] == 'lader_ok' and r['description_placeholders'] == {'effekt': '✓', 'status': '✓', 'til': '✓', 'strom': '✓'}, r
    r = await o.async_step_lader_ok({'faser': '3', 'maks_a': 15, 'ret': False})
    assert r['step_id'] == 'lader_proev'
    # bilen: ét felt – stikket og rækkevidden findes på bilens enhed
    bil = lader(hass, 'bilmaerke', [('sensor', 'battery_level', '61', {'unit_of_measurement': '%', 'device_class': 'battery'}), ('sensor', 'range', '240', {'unit_of_measurement': 'km'}),
                                    ('sensor', 'odometer', '24000', {'unit_of_measurement': 'km'}), ('binary_sensor', 'charging', 'off', {}), ('binary_sensor', 'plugged_in', 'on', {'device_class': 'plug'})], 'bil')
    assert F.bil_fra(hass, 'sensor.bil_battery_level') == {'bil_soc': 'sensor.bil_battery_level', 'bil_stik': 'binary_sensor.bil_plugged_in', 'bil_km': 'sensor.bil_range'}, F.bil_fra(hass, 'sensor.bil_battery_level')
    assert F.bil_fra(hass, 'sensor.ukendt') == {'bil_soc': 'sensor.ukendt'}
    r = await o.async_step_lader_ok({'faser': '3', 'maks_a': 15, 'ret': False, 'bil_soc': 'sensor.bil_battery_level'})
    assert r['errors'] == {'bil_kwh': 'bil_kwh'}, r
    r = await o.async_step_lader_ok({'faser': '3', 'maks_a': 15, 'ret': False, 'bil_soc': 'sensor.bil_battery_level', 'bil_kwh': 60})
    assert r['step_id'] == 'lader_proev' and o._lader['bil_kwh'] == 60 and o._lader['bil_stik'] == 'binary_sensor.bil_plugged_in'
    r = await o.async_step_lader_proev({'proev': False})
    assert entry.data['lader']['bil_km'] == 'sensor.bil_range' and hass.states.get('input_number.wattlas_lader_maal').state == '80.0'
    o = flow(); await o.async_step_lader({'lader': v2c})
    await o.async_step_lader_ok({'faser': '3', 'maks_a': 15, 'ret': False})
    assert 'bil_soc' not in o._lader, 'ryddet igen'
    ægte = F.proev
    for svar, gemt in (({'start': True, 'strom': True, 'stop': True}, True), ({'start': True, 'strom': False, 'stop': True}, 'kun til/fra'), ({'start': True, 'strom': True, 'stop': False}, False),
                       ({'fejl': 'plads'}, False)):
        async def falsk(*_):
            await asyncio.sleep(.03)
            return svar
        F.proev = falsk
        hass.config_entries.async_update_entry(entry, data={k: v for k, v in entry.data.items() if k != 'lader'})
        o = flow(); await o.async_step_lader({'lader': v2c}); await o.async_step_lader_ok({'faser': '3', 'maks_a': 15, 'ret': False})
        r = await o.async_step_lader_proev({'proev': True})
        assert r['type'] == 'progress', r
        await asyncio.sleep(.05)
        r = await o.async_step_lader_koer()
        assert r['type'] == 'progress_done', r
        r = await o.async_step_lader_resultat()
        if gemt:
            r = await o.async_step_lader_resultat({})
        assert r['type'] == ('create_entry' if gemt else 'abort'), (svar, r)
        k = entry.data.get('lader')
        assert (k is None) if not gemt else (k['proevet'] and k['maks_a'] == 15 and (k.get('strom') is None) == (gemt == 'kun til/fra')), (svar, k)
        assert (M.NOEGLE in hass.data) == bool(gemt)
    F.proev = ægte
    o = flow(); await o.async_step_lader({'lader': v2c}); await o.async_step_lader_ok({'faser': '1', 'maks_a': 10, 'ret': False}); r = await o.async_step_lader_proev({'proev': False})
    assert r['type'] == 'create_entry' and entry.data['lader']['proevet'] is False and entry.data['lader']['faser'] == 1
    assert hass.states.get('input_number.wattlas_lader_maks_a').state == '10.0' and hass.states.get('input_text.wattlas_elbil_entitet').state == 'sensor.v2c_charge_power'
    assert hass.states.get('input_select.wattlas_lader_tilstand').state == 'fra', 'styres ikke, før brugeren vælger det'
    # ikke på listen: selv vælge, og fejlene
    o = flow(); r = await o.async_step_lader({'lader': 'anden'})
    assert r['step_id'] == 'lader_enhed' and list(r['data_schema'].schema) == ['enhed'], 'enheden vælges i sit eget trin'
    assert r['data_schema'].schema['enhed'].config['entity'] == [{'domain': ['sensor'], 'device_class': ['power']}], 'kun enheder, der måler effekt'
    r = await o.async_step_lader_enhed({})
    assert r['step_id'] == 'lader_roller'
    r = await o.async_step_lader_roller({'effekt': 'sensor.v2c_charge_power'})
    assert r['errors'] == {'base': 'lader_ingen_styring'}, r
    r = await o.async_step_lader_roller({'effekt': 'sensor.v2c_charge_power', 'strom': 'number.kun6'})
    assert r['errors'] == {'base': 'lader_ingen_styring'}, ('kan ikke stoppes', r)
    r = await o.async_step_lader_roller({'effekt': 'sensor.emhass_ui_fase_1', 'til_fra': 'switch.v2c_paused'})
    assert r['errors'] == {'effekt': 'elbil_sensor'}
    S('select.underlig', 'x', {'options': ['x', 'y']})
    r = await o.async_step_lader_roller({'effekt': 'sensor.v2c_charge_power', 'til_fra': 'select.underlig'})
    assert r['errors'] == {'til_fra': 'lader_valg'}
    r = await o.async_step_lader_roller({'effekt': 'sensor.v2c_charge_power', 'til_fra': 'select.goe_frc'})
    assert r['step_id'] == 'lader_ok' and o._lader['til_valg'] == '2' and r['description_placeholders']['strom'] == '–'
    r = await flow().async_step_lader({'lader': 'ingen'})
    assert r['type'] == 'create_entry' and 'lader' not in entry.data and M.NOEGLE not in hass.data
    # elbil-trinnet: med en valgt lader er målingen laderens, og der er intet at vælge (kontakten ligger på fanen Elbil)
    o = flow(); await o.async_step_lader({'lader': v2c}); await o.async_step_lader_ok({'faser': '3', 'maks_a': 15, 'ret': False}); await o.async_step_lader_proev({'proev': False})
    r = await flow().async_step_elbil()
    assert r['type'] == 'abort' and r['reason'] == 'lader_styret', r
    assert hass.states.get('input_text.wattlas_elbil_entitet').state == 'sensor.v2c_charge_power'
    print('Opsætningen (på listen, ikke på listen, prøve, uden prøve, fjern): OK')

    # --- planens anden last ---
    y = load_yaml(str(REPO / 'packages/wattlas/emhass_forbindelse.yaml'))

    def find(o, key):
        if isinstance(o, dict):
            if key in o:
                return o[key]
            o = list(o.values())
        for v in o if isinstance(o, list) else []:
            if (r := find(v, key)) is not None:
                return r
        return None
    skabelon = find(y, 'fb_ekstra')

    def last(hus=(1500, 2500), net=11000, interval=48):
        return Template(skabelon, hass).async_render({'hh': None, 'hus': {'ok': True, 'liste': list(hus)}, 'prognose': {'intervaller': interval}, 'beregning_basis': {'maximum_power_from_grid': net}}, parse_result=True)
    S('input_boolean.wattlas_forbruger1_aktiv', 'off'); S('input_datetime.wattlas_forbruger1_faerdig', '06:00:00')
    assert last() == {}
    om = (dt_util.now() + timedelta(hours=8)).strftime('%H:%M')
    ev = {'tilsluttet': True, 'rest_kwh': 20, 'p_maks_w': 11040, 'klar': om}
    S('sensor.wattlas_lader', 'venter', ev)
    assert last() == {}, 'kun i tilstanden klar'
    S('input_select.wattlas_lader_tilstand', 'klar')
    x = last()
    assert x['number_of_deferrable_loads'] == 1 and x['nominal_power_of_deferrable_loads'] == [8500], x  # 11 kW loft − husets højeste 2,5 kW
    assert x['operating_hours_of_each_deferrable_load'] == [2.5] and 15 <= x['end_timesteps_of_each_deferrable_load'][0] <= 16 and x['custom_deferrable_forecast_id'][0]['entity_id'] == 'sensor.wattlas_lader_plan', x
    S('sensor.wattlas_lader', 'venter', {**ev, 'rest_kwh': 200})
    assert last()['operating_hours_of_each_deferrable_load'][0] <= 8, 'klippet til vinduet, så planen kan løses'
    for k in ({'tilsluttet': False}, {'rest_kwh': 0}, {'p_maks_w': 0}):
        S('sensor.wattlas_lader', 'venter', {**ev, **k})
        assert last() == {}, k
    S('sensor.wattlas_lader', 'venter', ev)
    assert last(net=3000) == {}, 'ingen plads under importloftet: bilen udelades'
    S('input_boolean.wattlas_forbruger1_aktiv', 'on'); S('input_number.wattlas_forbruger1_effekt', 2000); S('input_number.wattlas_forbruger1_timer', 2); S('input_number.wattlas_forbruger1_koert', 0)
    x = last()
    assert x['number_of_deferrable_loads'] == 2 and x['nominal_power_of_deferrable_loads'] == [2000, 8500] and [c['entity_id'] for c in x['custom_deferrable_forecast_id']] == ['sensor.p_deferrable0', 'sensor.wattlas_lader_plan']
    assert all(len(v) == 2 for v in x.values() if isinstance(v, list)), x
    S('input_select.wattlas_lader_tilstand', 'fra')
    x = last()
    assert x['number_of_deferrable_loads'] == 1 and x['nominal_power_of_deferrable_loads'] == [2000], 'forbrugeren alene er som før'
    print('Planens laster (ingen, bil, begge, klippet, uden plads): OK')
    await hass.async_stop(force=True)


asyncio.run(main())
