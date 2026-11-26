# Priser og solprognose fra flere kilder: Energi Data Service, Nordpool (øre, MWh, uden moms) og Solcast bliver til det samme format,
# og opsætningen genkender dem. Kør: python tests/test_kilder.py   (kræver: pip install homeassistant)
import asyncio
from datetime import timedelta

from test_flow import REPO, ny_hass
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml


async def main():
    hass, _ = await ny_hass('')
    from custom_components.wattlas import config_flow as CF
    hass.states.async_remove('sensor.wattlas_spotpris')  # test_flows hjælper sætter en falsk; her er det den rigtige
    f = load_yaml(str(REPO / 'packages/wattlas/wattlas_kilder.yaml'))
    for dom in ('input_text', 'template'):
        assert await async_setup_component(hass, dom, {dom: f[dom]}), dom
    await hass.async_block_till_done()
    S = hass.states.async_set
    v = lambda e: hass.states.get(e)  # noqa: E731

    async def tekst(e, x):
        await hass.services.async_call('input_text', 'set_value', {'entity_id': e, 'value': x}, blocking=True)
        await hass.async_block_till_done()
    nul = dt_util.start_of_local_day()
    kvarter = lambda dag, fn: [fn(nul + timedelta(days=dag, minutes=15 * i), i) for i in range(96)]  # noqa: E731

    S('sensor.helios', '1', {'forecast': [{'datetime': (nul + timedelta(minutes=15 * i)).isoformat(), 'watts': 1} for i in range(10)]})
    # --- Energi Data Service: uændret (tom hjælper) ---
    S('sensor.energi_data_service', '1.23', {'raw_today': kvarter(0, lambda t, i: {'hour': t, 'price': 1 + i / 100}), 'raw_tomorrow': kvarter(1, lambda t, i: {'hour': t, 'price': 2.0})})
    await hass.async_block_till_done()
    s = v('sensor.wattlas_spotpris')
    assert s.state == '1.23' and len(s.attributes['raw_today']) == 96 and s.attributes['raw_today'][4]['price'] == 1.04, s
    assert dt_util.parse_datetime(s.attributes['raw_today'][4]['hour']) == nul + timedelta(hours=1) and s.attributes['raw_tomorrow'][0]['price'] == 2.0
    # det, resten af Wattlas gør med listen (as_timestamp på hour, tal i price)
    r = Template("{{ (state_attr('sensor.wattlas_spotpris', 'raw_today') or []) | map(attribute='hour') | map('as_timestamp') | select('number') | list | count }}", hass).async_render()
    assert r == 96, r
    print('Energi Data Service gennem Wattlas-prisen: OK')

    # --- Nordpool: øre/MWh, uden moms; faktoren laves af opsætningen ---
    for attr, moms, fakt in (({'unit': 'kWh', 'price_in_cents': False}, False, '1'), ({'unit': 'kWh', 'price_in_cents': True}, False, '0.01'),
                             ({'unit': 'MWh', 'price_in_cents': False}, True, '0.00125'), ({'unit': 'kWh', 'price_in_cents': True}, True, '0.0125')):
        S('sensor.nordpool_kwh_dk1', '100', {**attr, 'raw_today': kvarter(0, lambda t, i: {'start': t, 'end': t + timedelta(minutes=15), 'value': 100.0}), 'raw_tomorrow': []})
        ui = {'priser': 'sensor.nordpool_kwh_dk1', 'priser_uden_moms': moms, 'solprognose': ''}
        CF._kilder(hass, ui)
        assert ui['pris'] == f'sensor.nordpool_kwh_dk1|{fakt}', (attr, moms, ui)
        assert CF._faktor_med_moms(ui['pris']) == moms, ('fluebenet huskes', ui['pris'])
        await tekst('input_text.wattlas_pris_entitet', ui['pris'])
        s = v('sensor.wattlas_spotpris')
        assert abs(float(s.state) - 100 * float(fakt)) < 1e-6 and abs(s.attributes['raw_today'][0]['price'] - 100 * float(fakt)) < 1e-6 and s.attributes['raw_tomorrow'] == [], (attr, s)
    S('sensor.nordpool_kwh_dk1', '1', {'unit': 'kWh', 'additional_costs_current_hour': 0.85, 'raw_today': kvarter(0, lambda t, i: {'start': t, 'end': t, 'value': 1.0})})
    assert CF._kilder(hass, {'priser': 'sensor.nordpool_kwh_dk1', 'solprognose': 'sensor.helios'}).get('priser') == 'priser_tillaeg', 'tariffer lagt på i Nordpool'
    y = load_yaml(str(REPO / 'packages/wattlas/emhass_husprognose.yaml'))
    assert CF.SOLCAST in y['recorder']['exclude']['entities'], 'for stor til databasen'
    S('sensor.nordpool_kwh_dk1', '1', {'unit': 'kWh', 'currency': 'EUR', 'raw_today': kvarter(0, lambda t, i: {'start': t, 'end': t, 'value': 0.1})})
    assert CF._kilder(hass, {'priser': 'sensor.nordpool_kwh_dk1', 'solprognose': 'sensor.helios'}).get('priser') == 'priser_format', 'euro er ikke kroner'
    S('sensor.nordpool_kwh_dk1', '1', {'unit': 'GWh', 'raw_today': kvarter(0, lambda t, i: {'start': t, 'end': t, 'value': 1.0})})
    assert CF._kilder(hass, {'priser': 'sensor.nordpool_kwh_dk1', 'solprognose': 'sensor.helios'}).get('priser') == 'priser_format'
    for daarlig in ({}, {'raw_today': []}, {'raw_today': [{'x': 1}]}, {'raw_today': 'tekst'}):
        S('sensor.daarlig', '1', daarlig)
        assert CF._kilder(hass, {'priser': 'sensor.daarlig', 'solprognose': 'sensor.helios'}).get('priser') == 'priser_format', daarlig
    S('sensor.eds_med_tariffer', '2.5', {'raw_today': [{'hour': nul, 'price': 2.5}], 'tariffs': {'tariffs': {'0': 0.1}}})
    assert CF._kilder(hass, {'priser': 'sensor.eds_med_tariffer', 'solprognose': 'sensor.helios'}).get('priser') == 'priser_tillaeg', 'tariffer i en anden EDS-sensor'
    ui = {'priser': 'sensor.energi_data_service', 'solprognose': 'sensor.helios'}
    assert CF._kilder(hass, ui) == {} and ui['pris'] == 'sensor.energi_data_service'
    ui = {'priser': None, 'solprognose': 'sensor.helios'}
    CF._kilder(hass, ui)
    assert ui['pris'] == '', 'tom = Energi Data Service'
    await tekst('input_text.wattlas_pris_entitet', 'sensor.findes_ikke|1')
    assert v('sensor.wattlas_spotpris').state == 'unavailable', 'kilden mangler: ingen pris, ikke 0 kr.'
    await tekst('input_text.wattlas_pris_entitet', 'sensor.nordpool_kwh_dk1|x')
    assert v('sensor.wattlas_spotpris').state == 'unavailable'
    await tekst('input_text.wattlas_pris_entitet', '')
    assert v('sensor.wattlas_spotpris').state == '1.23'
    print('Nordpool (kr., øre, MWh, uden moms) og forkerte kilder: OK')

    # --- Solcast: halve timer i kW → kvarterer i W; i dag, i morgen og dag 3 findes på samme opsætning ---
    from homeassistant.config_entries import ConfigEntry
    entry = ConfigEntry(domain='solcast_solar', title='Solcast', data={}, options={}, version=1, minor_version=1, source='user', unique_id='sc', discovery_keys={}, subentries_data=None)
    hass.config_entries._entries[entry.entry_id] = entry
    reg = er.async_get(hass)
    navne = {}
    for dag, nøgle in enumerate(('total_kwh_forecast_today', 'total_kwh_forecast_tomorrow', 'total_kwh_forecast_d3', 'total_kwh_forecast_d4')):
        e = reg.async_get_or_create('sensor', 'solcast_solar', nøgle, suggested_object_id=f'solcast_pv_forecast_{nøgle}', config_entry=entry, translation_key=nøgle)
        navne[nøgle] = e.entity_id
        S(e.entity_id, '10', {'detailedForecast': [{'period_start': nul + timedelta(days=dag, minutes=30 * i), 'pv_estimate': (i % 24) / 10, 'pv_estimate10': 0, 'pv_estimate90': 0} for i in range(48)]})
    ui = {'solprognose': navne['total_kwh_forecast_tomorrow']}  # valgt i morgen: i dag kommer alligevel først
    assert CF._kilder(hass, ui) == {} and ui['solprognose'] == CF.SOLCAST
    assert ui['solcast'] == ','.join(navne[k] for k in ('total_kwh_forecast_today', 'total_kwh_forecast_tomorrow', 'total_kwh_forecast_d3')), ui
    await tekst('input_text.wattlas_solcast_entiteter', ui['solcast'])
    s = v(CF.SOLCAST)
    fc = s.attributes['forecast']
    assert len(fc) == 3 * 96 and fc[0]['watts'] == 0 and fc[2]['watts'] == fc[3]['watts'] == 100 and fc[46]['watts'] == 2300, fc[:4]
    t = [dt_util.parse_datetime(x['datetime']) for x in fc]
    assert all((b - a).total_seconds() == 900 for a, b in zip(t, t[1:])), 'kvarterer i træk, uden huller og dubletter'
    assert CF._prognose_fejl(hass, CF.SOLCAST) is None, 'Wattlas godtager den som Helios'
    ui = {'solprognose': CF.SOLCAST}
    assert CF._kilder(hass, ui) == {}, 'Konfigurer igen uden ændring'
    # overlap mellem dagene og en sensor uden data
    S(navne['total_kwh_forecast_tomorrow'], '10', {'detailedForecast': [{'period_start': nul + timedelta(hours=23 + i / 2), 'pv_estimate': 1.0} for i in range(4)]})
    await hass.async_block_till_done()
    t = [dt_util.parse_datetime(x['datetime']) for x in v(CF.SOLCAST).attributes['forecast']]
    assert len(t) == len(set(t)) and t == sorted(t), 'ingen dubletter'
    S(navne['total_kwh_forecast_today'], 'unavailable', {})
    await hass.async_block_till_done()
    assert v(CF.SOLCAST).state == 'unavailable'
    ui = {'solprognose': CF.SOLCAST}
    assert CF._kilder(hass, ui) == {} and ui['solcast'].startswith(navne['total_kwh_forecast_today']), ('Solcast nede et øjeblik må ikke blokere Konfigurer, og dagene beholdes', ui)
    await tekst('input_text.wattlas_solcast_entiteter', '')
    assert CF._kilder(hass, {'solprognose': CF.SOLCAST}) == {'solprognose': 'prognose_format'}, 'Wattlas egen sensor uden dage'
    S('sensor.solcast_forkert', '1', {'detailedForecast': [{'period_start': nul + timedelta(hours=i), 'pv_estimate': 1} for i in range(8)]})
    assert CF._kilder(hass, {'solprognose': 'sensor.solcast_forkert'}) == {'solprognose': 'prognose_format'}, 'timetal er ikke Solcasts halve timer'
    S('sensor.helios', '1', {'forecast': [{'datetime': (nul + timedelta(minutes=15 * i)).isoformat(), 'watts': 1} for i in range(10)]})
    ui = {'solprognose': 'sensor.helios'}
    assert CF._kilder(hass, ui) == {} and ui['solprognose'] == 'sensor.helios' and ui['solcast'] == '', 'Helios som før'
    print('Solcast (kvarterer, dage, overlap, udfald) og Helios som før: OK')
    await hass.async_stop(force=True)


asyncio.run(main())
