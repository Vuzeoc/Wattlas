# Ferie, "ingen hjemme", stormvarsel, prisniveau og Problem: husprognosen regner med standby i ferien og normalt fra hjemkomsten, en overstået
# ferie tælles ikke med i historikken, stormen fylder batteriet (klippet til det, der kan nås), og intet ændrer sig, når det er slået fra.
# Kør: python tests/test_ferie_storm.py   (kræver: pip install homeassistant)
import asyncio
import json
import time
from datetime import timedelta

from test_flow import REPO, ny_hass
from homeassistant.core import SupportsResponse
from homeassistant.helpers.entity import entity_sources
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml


def variabel(navn):
    """Skabelonen for en variabel i planens script (som i den udgivne pakke)."""
    y = load_yaml(str(REPO / 'packages/wattlas/emhass_forbindelse.yaml'))
    for trin in y['script']['emhass_test_helios']['sequence']:
        if isinstance(trin, dict) and navn in (trin.get('variables') or {}):
            return trin['variables'][navn]
    raise AssertionError(navn)


async def main():
    hass, _ = await ny_hass('')
    S = hass.states.async_set
    pakker = {f: load_yaml(str(REPO / f'packages/wattlas/{f}')) for f in ('wattlas_ferie.yaml', 'wattlas_storm.yaml', 'wattlas_status.yaml')}
    for dom in ('input_boolean', 'input_datetime'):
        assert await async_setup_component(hass, dom, {dom: {k: v for p in pakker.values() for k, v in (p.get(dom) or {}).items()}}), dom
    assert await async_setup_component(hass, 'template', {'template': [x for p in pakker.values() for x in p['template']]})
    await hass.async_block_till_done()

    async def kald(dom, tj, **d):
        await hass.services.async_call(dom, tj, d, blocking=True)
        await asyncio.sleep(1.1)  # ferie-sensoren ser på alle personer, så HA opdaterer den højst én gang i sekundet
        await hass.async_block_till_done()

    async def opdater():
        # skabeloner over alle personer opdateres med en forsinkelse; testen venter ikke på den
        assert await async_setup_component(hass, 'homeassistant', {})
        await kald('homeassistant', 'update_entity', entity_id='binary_sensor.wattlas_ferie')

    # ---------------- husprognosen ----------------
    hus = Template(variabel('hus'), hass)
    t0 = int(time.time() // 1800 * 1800)
    n = 6
    # samme halve time hver dag: dag k har forbruget 1000 + 100·k (dag 1 = i går), 9 dage tilbage
    S('sensor.emhass_husforbrug_historik', '54', {'data': json.dumps([[t0 + i * 1800 - k * 86400, 1000 + 100 * k] for k in range(1, 10) for i in range(n)])})
    S('sensor.emhass_udetemperatur_historik', '0', {'data': '[]'})
    S('input_text.wattlas_vejr_entitet', 'weather.test')
    v = {'prognose': {'intervaller': n}, 'start_ts': t0, 'kulde_w_pr_grad': 0}
    r = hus.async_render(v)
    assert r['ok'] and r['liste'] == [1400] * n and r['ferie'] == 0, ('uden ferie: gennemsnittet af de sidste 7 dage som før', r)
    # en manglende dag: stadig kun de sidste 7 døgn (dag 8 tager ikke over uden ferie)
    hist = [[t0 + i * 1800 - k * 86400, 1000 + 100 * k] for k in range(1, 10) for i in range(n)]
    S('sensor.emhass_husforbrug_historik', '53', {'data': json.dumps([x for x in hist if x[0] != t0 - 3 * 86400])})
    assert hus.async_render(v)['liste'][0] == round((1100 + 1200 + 1400 + 1500 + 1600 + 1700) / 6), 'manglende dag'
    S('sensor.emhass_husforbrug_historik', '54', {'data': json.dumps(hist)})
    # planlagt ferie fra om en time til om to: kun de halvtimer får standby (laveste fra de sidste dage), resten som før
    fra, til = dt_util.as_local(dt_util.utc_from_timestamp(t0 + 3600)), dt_util.as_local(dt_util.utc_from_timestamp(t0 + 7200))
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=fra.strftime('%Y-%m-%d %H:%M:%S'))
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_til', datetime=til.strftime('%Y-%m-%d %H:%M:%S'))
    r = hus.async_render(v)
    assert r['liste'] == [1400] * n, ('datoerne alene gør intet – kontakten skal på', r)
    await kald('input_boolean', 'turn_on', entity_id='input_boolean.wattlas_ferie')
    assert hass.states.get('binary_sensor.wattlas_ferie').state == 'off', ('ferien er ikke begyndt endnu', hass.states.get('binary_sensor.wattlas_ferie'))
    r = hus.async_render(v)
    assert r['liste'] == [1400, 1400, 1100, 1100, 1400, 1400] and r['ferie'] == 2, ('standby i ferien, normalt fra hjemkomsten', r)
    # ferien er i gang: sensoren er tændt
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 - 3600)).strftime('%Y-%m-%d %H:%M:%S'))
    await hass.async_block_till_done()
    assert hass.states.get('binary_sensor.wattlas_ferie').state == 'on'
    # en overstået ferie (dag 3-5) springes over i historikken, også når kontakten er slået fra igen; dag 8-9 tager over
    await kald('input_boolean', 'turn_off', entity_id='input_boolean.wattlas_ferie')
    fra, til = t0 - 5 * 86400 - 900, t0 - 2 * 86400 - 900
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=dt_util.as_local(dt_util.utc_from_timestamp(fra)).strftime('%Y-%m-%d %H:%M:%S'))
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_til', datetime=dt_util.as_local(dt_util.utc_from_timestamp(til)).strftime('%Y-%m-%d %H:%M:%S'))
    r = hus.async_render(v)
    forventet = round((1100 + 1200 + 1600 + 1700 + 1800 + 1900) / 6)
    assert r['liste'][0] == forventet and r['ferie'] == 0, ('ferie-dagene udeladt', r, forventet)
    # en lang ferie (dag 2-8): kun dag 1 og 9 tilbage – for få, så bruges de sidste 7 som før
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 - 8 * 86400 - 900)).strftime('%Y-%m-%d %H:%M:%S'))
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_til', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 - 86400 - 900)).strftime('%Y-%m-%d %H:%M:%S'))
    assert hus.async_render(v)['liste'][0] == 1400, 'for få dage og ingen langtidsstatistik: som før'
    # … men med timerne fra før ferien i langtidsstatistikken (dag 10 og frem: 2000 + 10·k) fyldes der op til 7 dage
    S('sensor.wattlas_husforbrug_lang', '700', {'data': json.dumps([[(t0 + tt * 3600 - k * 86400) // 3600 * 3600, 2000 + 10 * k] for k in range(1, 31) for tt in range(4)])})
    assert hus.async_render(v)['liste'][0] == round((1100 + 1900 + 2100 + 2110 + 2120 + 2130 + 2140) / 7), ('før ferien', hus.async_render(v)['liste'])
    # næste ferie skrives ind (kontakten slås til, datoer om en måned): den overståede huskes stadig i historikken
    forrige = (hass.states.get('binary_sensor.wattlas_ferie').attributes['udeluk_fra'], hass.states.get('binary_sensor.wattlas_ferie').attributes['udeluk_til'])
    await kald('input_boolean', 'turn_on', entity_id='input_boolean.wattlas_ferie')
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 + 30 * 86400)).strftime('%Y-%m-%d %H:%M:%S'))
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_til', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 + 40 * 86400)).strftime('%Y-%m-%d %H:%M:%S'))
    a = hass.states.get('binary_sensor.wattlas_ferie').attributes
    assert forrige[1] and (a['udeluk_fra'], a['udeluk_til']) == forrige, ('den forrige ferie huskes', forrige, a)
    assert hus.async_render(v)['liste'][0] == round((1100 + 1900 + 2100 + 2110 + 2120 + 2130 + 2140) / 7), 'stadig uden ferie-dagene'
    await kald('input_boolean', 'turn_off', entity_id='input_boolean.wattlas_ferie')
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 - 8 * 86400 - 900)).strftime('%Y-%m-%d %H:%M:%S'))
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_til', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 - 86400 - 900)).strftime('%Y-%m-%d %H:%M:%S'))
    # en gammel ferie (sluttede for 20 dage siden) rører ikke historikken: en manglende dag giver de sidste 7 døgn som uden ferie
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 - 25 * 86400)).strftime('%Y-%m-%d %H:%M:%S'))
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_til', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 - 20 * 86400)).strftime('%Y-%m-%d %H:%M:%S'))
    S('sensor.emhass_husforbrug_historik', '53', {'data': json.dumps([x for x in hist if x[0] != t0 - 3 * 86400])})
    assert hus.async_render(v)['liste'][0] == round((1100 + 1200 + 1400 + 1500 + 1600 + 1700) / 6), 'gammel ferie'
    S('sensor.emhass_husforbrug_historik', '54', {'data': json.dumps(hist)})
    # ny installation (kun 2 dage): ferien gælder også, med det laveste af det, der er
    S('sensor.emhass_husforbrug_historik', '12', {'data': json.dumps([x for x in hist if x[0] >= t0 - 2 * 86400])})
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 + 3600)).strftime('%Y-%m-%d %H:%M:%S'))
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_til', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 + 7200)).strftime('%Y-%m-%d %H:%M:%S'))
    await kald('input_boolean', 'turn_on', entity_id='input_boolean.wattlas_ferie')
    r = hus.async_render(v)
    assert r['liste'] == [1150, 1150, 1100, 1100, 1150, 1150] and r['ferie'] == 2, ('kort historik – og en planlagt ferie henter ikke fra langtidsstatistikken', r)
    # en ferie, der lige er begyndt (for 2 timer siden): historikkens dage er endnu ikke ferie – heller ingen langtidsstatistik
    await kald('input_datetime', 'set_datetime', entity_id='input_datetime.wattlas_ferie_fra', datetime=dt_util.as_local(dt_util.utc_from_timestamp(t0 - 7200)).strftime('%Y-%m-%d %H:%M:%S'))
    r = hus.async_render(v)
    assert r['liste'] == [1100, 1100, 1100, 1100, 1150, 1150], ('lige begyndt', r)
    S('sensor.wattlas_husforbrug_lang', '0', {'data': '[]'})
    await kald('input_boolean', 'turn_off', entity_id='input_boolean.wattlas_ferie')
    S('sensor.emhass_husforbrug_historik', '54', {'data': json.dumps(hist)})
    # ingen hjemme i et døgn (kun når det er slået til): standby i hele planen, til nogen kommer hjem
    S('person.a', 'not_home', timestamp=time.time() - 25 * 3600); S('person.b', 'unknown')
    await hass.async_block_till_done()
    assert hus.async_render(v)['ferie'] == 0, 'slået fra'
    await kald('input_boolean', 'turn_on', entity_id='input_boolean.wattlas_ingen_hjemme')
    r = hus.async_render(v)
    assert r['ferie'] == n and set(r['liste']) == {1100} and hass.states.get('binary_sensor.wattlas_ferie').attributes['ingen_hjemme'] is True, r
    S('person.b', 'home'); await opdater()
    assert hus.async_render(v)['ferie'] == 0, 'en er kommet hjem'
    S('person.b', 'not_home', timestamp=time.time() - 3600); await opdater()
    assert hus.async_render(v)['ferie'] == 0, 'den sidste gik for under et døgn siden'
    await kald('input_boolean', 'turn_off', entity_id='input_boolean.wattlas_ingen_hjemme')
    print('Ferie og ingen hjemme i husprognosen: OK')

    # ---------------- stormvarsel ----------------
    svar = {}

    async def udsigt(call):
        return {e: {'forecast': svar.get(e, [])} for e in call.data['entity_id']} if isinstance(call.data['entity_id'], list) else {call.data['entity_id']: {'forecast': svar.get(call.data['entity_id'], [])}}
    hass.services.async_register('weather', 'get_forecasts', udsigt, supports_response=SupportsResponse.ONLY)
    S('weather.test', 'windy', {'temperature': 5, 'wind_speed_unit': 'km/h'})

    async def storm():
        await kald('input_boolean', 'turn_off', entity_id='input_boolean.wattlas_storm')
        await kald('input_boolean', 'turn_on', entity_id='input_boolean.wattlas_storm')
        return hass.states.get('binary_sensor.wattlas_storm')
    nu = dt_util.now()
    svar['weather.test'] = [{'datetime': (nu + timedelta(hours=h)).isoformat(), 'wind_gust_speed': 80} for h in range(48)]
    assert (await storm()).state == 'off', '80 km/h = 22 m/s er ikke storm'
    svar['weather.test'][30]['wind_gust_speed'] = 95
    s = await storm()
    assert s.state == 'on' and s.attributes['kilde'] == 'vejrudsigt' and '26 m/s' in s.attributes['tekst'], s
    svar['weather.test'][30]['wind_gust_speed'] = 80; svar['weather.test'][40]['wind_gust_speed'] = 120
    assert (await storm()).state == 'off', 'mere end 36 timer ude'
    S('weather.test', 'windy', {'temperature': 5}); svar['weather.test'][30]['wind_gust_speed'] = 95
    assert (await storm()).state == 'off', 'ukendt enhed: vindstød bruges ikke'
    S('weather.test', 'windy', {'temperature': 5, 'wind_speed_unit': 'km/h'}); svar['weather.test'][30]['wind_gust_speed'] = 80
    # Meteoalarm: kun orange/rødt om vind eller torden, med udløb, højst 3 døgn
    e = 'binary_sensor.meteoalarm_dk'
    entity_sources(hass)[e] = {'domain': 'meteoalarm', 'custom_component': False}  # som en rigtig Meteoalarm-platform (integration_entities)
    varsel = {'awareness_level': '3; orange; Severe', 'awareness_type': '1; Wind', 'headline': 'Orange varsel for storm', 'onset': (nu + timedelta(hours=10)).isoformat(),
              'expires': (nu + timedelta(hours=20)).isoformat()}
    S(e, 'on', varsel)
    s = await storm()
    assert s.state == 'on' and s.attributes['kilde'] == 'varsel' and s.attributes['tekst'] == 'Orange varsel for storm', s
    for ret, hvorfor in (({'awareness_level': '2; yellow; Moderate'}, 'gult'), ({'awareness_type': '10; Rain'}, 'regn'), ({'expires': None}, 'intet udløb'),
                         ({'onset': (nu + timedelta(hours=40)).isoformat()}, 'for langt ude'), ({'expires': (nu - timedelta(hours=1)).isoformat()}, 'udløbet')):
        S(e, 'on', {**varsel, **ret})
        assert (await storm()).state == 'off', hvorfor
    # et langt varsel tæller, men højst 3 døgn frem
    S(e, 'on', {**varsel, 'expires': (nu + timedelta(days=5)).isoformat()})
    s = await storm()
    assert s.state == 'on' and s.attributes['til_ts'] <= time.time() + 3 * 86400 + 60, ('højst 3 døgn', s)
    # en fundet storm holdes til sit slut, selv om varslet forsvinder, eller vejret ikke svarer et øjeblik – men ikke, når kontakten slås fra
    sv = Template(pakker['wattlas_storm.yaml']['template'][0]['actions'][-1]['variables']['storm'], hass)
    S(e, 'off', {})
    r = sv.async_render({'vejr_id': 'weather.test'})
    assert r['til'] == s.attributes['til_ts'] and r['kilde'] == 'varsel', ('holdes', r)
    S('binary_sensor.wattlas_storm', 'on', {**s.attributes, 'til_ts': time.time() - 60})
    assert sv.async_render({'vejr_id': 'weather.test'})['til'] is None, 'slut er passeret'
    S(e, 'on', varsel)
    await kald('input_boolean', 'turn_off', entity_id='input_boolean.wattlas_storm')
    assert hass.states.get('binary_sensor.wattlas_storm').state == 'off', 'slået fra'
    assert sv.async_render({'vejr_id': 'weather.test'})['til'] is None, 'slået fra: intet holdes'
    # planen: reserven løftes til 80 % (højst det, batteriet står på), og målet klippes til det, laderen kan nå
    se = Template(variabel('storm_ekstra'), hass)
    S('input_number.wattlas_reserve', '20'); S('input_number.wattlas_batteri_kwh', '10')
    p = {'hh': None, 'soc': 50, 'charge_limit': 5000, 'prognose': {'intervaller': 48}, 'beregning_basis': {'maximum_power_from_grid': 11000}, 'hus': {'ok': True, 'liste': [500, 900]}, 'maks_soc': 100}
    assert se.async_render(p) == {}, 'ingen storm'
    S('binary_sensor.wattlas_storm', 'on')
    assert se.async_render(p) == {'battery_minimum_state_of_charge': 0.5, 'soc_final': 1.0}, se.async_render(p)
    assert se.async_render({**p, 'maks_soc': 90})['soc_final'] == 0.9, 'Højeste batteriniveau gælder også under storm'
    assert se.async_render({**p, 'soc': 85, 'maks_soc': 70})['battery_minimum_state_of_charge'] == 0.7, 'aldrig holdt over Højeste batteriniveau'
    r = se.async_render({**p, 'soc': 90, 'charge_limit': 500, 'prognose': {'intervaller': 4}})
    assert r['battery_minimum_state_of_charge'] == 0.8 and abs(r['soc_final'] - 0.945) < 1e-9, ('klippet', r)
    assert se.async_render({**p, 'hh': {'reserve': 20}}) == {}, 'ikke i hvad-hvis'
    # genforsøget "hold niveauet": målet bliver det, batteriet holdes på
    hold = next(x['then'][0]['variables']['storm_ekstra'] for x in load_yaml(str(REPO / 'packages/wattlas/emhass_forbindelse.yaml'))['script']['emhass_test_helios']['sequence']
                if isinstance(x, dict) and 'then' in x and isinstance(x['then'][0], dict) and 'dict(storm_ekstra' in str(x['then'][0].get('variables', {}).get('storm_ekstra', '')))
    assert Template(hold, hass).async_render({'storm_ekstra': {'battery_minimum_state_of_charge': 0.8, 'soc_final': 1.0}}) == {'battery_minimum_state_of_charge': 0.8, 'soc_final': 0.8}
    # importloftet minus husets højeste forbrug begrænser også: 3680 − 1500 W i 5,5 time på 40 kWh fra 20 % = 48,5 % (−5)
    r = se.async_render({**p, 'soc': 20, 'charge_limit': 8000, 'prognose': {'intervaller': 11}, 'beregning_basis': {'maximum_power_from_grid': 3680}, 'hus': {'ok': True, 'liste': [1500]}})
    S('input_number.wattlas_batteri_kwh', '40')
    r = se.async_render({**p, 'soc': 20, 'charge_limit': 8000, 'prognose': {'intervaller': 11}, 'beregning_basis': {'maximum_power_from_grid': 3680}, 'hus': {'ok': True, 'liste': [1500]}})
    assert abs(r['soc_final'] - (20 + 2180 * 0.95 * 5.5 / 40000 * 100 - 5) / 100) < 1e-9, ('importloftet', r)
    S('input_number.wattlas_batteri_kwh', '10')
    # reguleringen: lad fra nettet nu, når planen ikke når 80 % før stormen; en tidsstyret "brug" springes over; manuel vinder
    reg = load_yaml(str(REPO / 'packages/wattlas/emhass_forbindelse.yaml'))['script']['emhass_reguler']['sequence']
    blok = [x['variables'] for x in reg if isinstance(x, dict) and 'variables' in x]
    i = next(n for n, b in enumerate(blok) if 'storm' in b)
    S('input_number.wattlas_maks_netladeeffekt_w', '5000'); S('binary_sensor.wattlas_tilsidesaettelse_aktiv', 'off')

    def reguler(soc, ts='ingen', ts_soc=60, fra_timer=10):
        S('binary_sensor.wattlas_storm', 'on', {'fra': (dt_util.now() + timedelta(hours=fra_timer)).isoformat()})
        vs = {'soc': soc, 'ts': ts, 'ts_soc': ts_soc}
        vs['storm'] = Template(blok[i]['storm'], hass).async_render(vs)
        return {k: Template(blok[i + 1][k], hass).async_render(vs) for k in ('ts', 'ts_soc')}
    # 10 kWh fra 30 til 80 % med 5 kW: ca. 1,05 t (+1 t luft) – stormen om 10 t: planen får lov; om 1,5 t: lad nu
    # 10 kWh fra 30 til 80 % med 80 % af 5 kW (importloftet ukendt): ca. 1,3 t (+1 t luft). Indtil da holdes batteriet (ingen afladning under 80 %)
    assert reguler(30) == {'ts': 'gem', 'ts_soc': 60} and reguler(30, fra_timer=1.5) == {'ts': 'lad', 'ts_soc': 80}, reguler(30, fra_timer=1.5)
    S('input_number.wattlas_import_graense_w', '3680'); S('sensor.emhass_m_load_w_totalpower', '1500')
    assert reguler(30, fra_timer=3.5)['ts'] == 'lad', 'importloftet minus huset: ca. 2,9 t + 1 t'
    S('input_number.wattlas_import_graense_w', '0'); S('sensor.emhass_m_load_w_totalpower', '0')
    S('input_number.wattlas_maks_soc', '70'); assert reguler(50, fra_timer=0.5)['ts_soc'] == 70, 'Højeste batteriniveau'; S('input_number.wattlas_maks_soc', '0')
    assert reguler(85, fra_timer=1) == {'ts': 'ingen', 'ts_soc': 60}, 'over 80 %: intet'
    assert reguler(30, fra_timer=-2) == {'ts': 'lad', 'ts_soc': 80}, 'stormen er i gang, og batteriet er lavt'
    assert reguler(80, 'brug', fra_timer=-2) == {'ts': 'gem', 'ts_soc': 60}, 'på 80 % under stormen: holdes, ingen afladning'
    assert reguler(80, 'lad', 85, fra_timer=-2) == {'ts': 'lad', 'ts_soc': 85}, 'en tidsstyret lad røres ikke'
    assert reguler(85, 'brug') == {'ts': 'ingen', 'ts_soc': 60}, 'en tidsstyret "brug" springes over'
    S('input_number.wattlas_reserve', '90'); assert reguler(85, fra_timer=1)['ts_soc'] == 90; S('input_number.wattlas_reserve', '20')
    S('binary_sensor.wattlas_tilsidesaettelse_aktiv', 'on')
    assert reguler(30, 'brug', fra_timer=1) == {'ts': 'brug', 'ts_soc': 60}, 'en manuel tilsidesættelse vinder'
    S('binary_sensor.wattlas_tilsidesaettelse_aktiv', 'off')
    # er ladningen i gang, fortsætter den til målet (ingen start/stop hvert par minutter)
    S('switch.wattlas_netladning', 'on'); assert reguler(70)['ts'] == 'lad', 'i gang: fortsætter'
    S('switch.wattlas_netladning', 'off'); assert reguler(70)['ts'] == 'gem', 'ikke i gang og god tid: hold'
    # fasegrænsen begrænser også farten: 3 × 10 A × 230 V − 2 kW huset ≈ 4,9 kW → 0,8 × 4,9 = 3,9 kW; 10 kWh fra 30 til 80 % ≈ 1,3 t + 1 t
    S('input_number.wattlas_fase_graense_a', '10'); S('sensor.emhass_m_load_w_totalpower', '2000'); S('input_number.wattlas_maks_netladeeffekt_w', '10000')
    assert reguler(30, fra_timer=2.2)['ts'] == 'lad', 'fasegrænsen'
    S('input_number.wattlas_fase_graense_a', '0'); S('sensor.emhass_m_load_w_totalpower', '0'); S('input_number.wattlas_maks_netladeeffekt_w', '5000')
    # nettet er faldet ud: batteriet skal forsyne huset – stormen holder ikke igen
    for fase in (1, 2, 3): S(f'sensor.emhass_m_grid_current_v_l{fase}', '0')
    assert reguler(50, 'brug', fra_timer=-1) == {'ts': 'brug', 'ts_soc': 60}, 'nettet er nede'
    S('sensor.emhass_m_grid_current_v_l2', '231'); assert reguler(50, fra_timer=-1)['ts'] == 'lad', 'én fase har spænding: nettet er der'
    for fase in (1, 2, 3): S(f'sensor.emhass_m_grid_current_v_l{fase}', '230')
    S('binary_sensor.wattlas_storm', 'off')
    assert reguler.__name__ and Template(blok[i]['storm'], hass).async_render({'soc': 30}) == {'paa': False, 'r': 0, 'lad': False}, 'ingen storm'
    print('Stormvarsel (vejrudsigt, Meteoalarm, plan): OK')

    # ---------------- prisniveau og Problem ----------------
    nul = dt_util.start_of_local_day()
    h = dt_util.now().hour
    pris = lambda j, nu: nu if j == h else ((j - h) % 24) / 10  # noqa: E731
    for nu, ventet in ((0.25, 'billig'), (1.2, 'normal'), (2.25, 'dyr')):
        S('sensor.wattlas_spotpris', '1', {'raw_today': [{'hour': (nul + timedelta(hours=j)).isoformat(), 'price': pris(j, nu)} for j in range(24)], 'raw_tomorrow': [] if nu != 1.2 else None})
        await hass.async_block_till_done()
        s = hass.states.get('sensor.wattlas_prisniveau')
        assert s.state == ventet, (nu, s)
    S('sensor.wattlas_spotpris', '1', {'raw_today': [{'hour': (nul + timedelta(hours=h)).isoformat(), 'price': 1.5} for h in range(24)], 'raw_tomorrow': [{'hour': nul.isoformat(), 'price': 1.5}]})
    await hass.async_block_till_done()
    assert hass.states.get('sensor.wattlas_prisniveau').state == 'normal', 'samme pris hele dagen er hverken billig eller dyr'
    assert hass.states.get('binary_sensor.wattlas_problem').state == 'off'
    S('binary_sensor.emhass_ui_planfejl', 'on', {'friendly_name': 'Mangler aktuel plan'}); await hass.async_block_till_done()
    s = hass.states.get('binary_sensor.wattlas_problem')
    assert s.state == 'on' and s.attributes['alarmer'] == ['Mangler aktuel plan'], s
    print('Prisniveau og Problem: OK')
    await hass.async_stop()


asyncio.run(main())
