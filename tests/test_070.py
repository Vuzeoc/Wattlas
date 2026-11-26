# 0.7.0: hvad-hvis med et andet batteri (samme kWh nu, kun pladsen ændres; 0 = intet batteri), og intet ændres uden batteristørrelse.
# Kør: python tests/test_070.py   (kræver: pip install homeassistant)
import asyncio

from test_flow import REPO, ny_hass
from homeassistant.helpers.template import Template
from homeassistant.util.yaml import load_yaml


def variabel(navn):
    """Skabelonen for en variabel i planens script (som i den udgivne pakke)."""
    for trin in load_yaml(str(REPO / 'packages/wattlas/emhass_forbindelse.yaml'))['script']['emhass_test_helios']['sequence']:
        if isinstance(trin, dict) and navn in (trin.get('variables') or {}):
            return trin['variables'][navn]
    raise AssertionError(navn)


async def main():
    hass, _ = await ny_hass('')
    S = hass.states.async_set

    # ---------------- hvad-hvis: andet batteri ----------------
    hh = Template(variabel('hh_ekstra'), hass)
    S('input_number.wattlas_batteri_kwh', '10'); S('input_number.wattlas_maks_netimport_w', '11000')
    v = {'soc': 60, 'maks_soc': 100, 'hh': {'reserve': 20, 'slut_soc': 30, 'max_net_kw': 11, 'slid': 0.25}}
    r = hh.async_render(v)
    assert r['battery_minimum_state_of_charge'] == 0.2 and r['soc_final'] == 0.3 and 'soc_init' not in r and 'battery_nominal_energy_capacity' not in r, ('som før', r)
    assert hh.async_render({**v, 'hh': {**v['hh'], 'batteri_kwh': 10}}) == r, 'samme batteri = som før'
    r = hh.async_render({**v, 'hh': {**v['hh'], 'batteri_kwh': 20}})
    # 6 kWh nu, 2 kWh reserve og 3 kWh ved slut – i et 20 kWh-batteri
    assert r['battery_nominal_energy_capacity'] == 20000 and r['soc_init'] == 0.3 and r['battery_minimum_state_of_charge'] == 0.1 and r['soc_final'] == 0.15, ('større', r)
    assert r['publish_prefix'] == 'hh_' and r['weight_battery_discharge'] == 0.25, r
    r = hh.async_render({**v, 'hh': {**v['hh'], 'batteri_kwh': 5}})
    assert r['soc_init'] == 1.0 and r['soc_final'] == 0.6 and r['battery_minimum_state_of_charge'] == 0.4, ('mindre: fuldt, højst 100 %', r)
    r = hh.async_render({**v, 'hh': {**v['hh'], 'batteri_kwh': 0}})
    assert r['battery_charge_power_max'] == 0 and r['battery_discharge_power_max'] == 0 and r['soc_final'] == 0.6, ('intet batteri: slut = start', r)
    assert 'battery_nominal_energy_capacity' not in r, r
    # meget mindre batteri og et højeste niveau under 100 %: aldrig over det (ellers kan EMHASS ikke løse planen)
    r = hh.async_render({**v, 'maks_soc': 90, 'hh': {**v['hh'], 'reserve': 30, 'batteri_kwh': 2.5}})
    assert r['battery_minimum_state_of_charge'] == 0.85 and r['soc_init'] == 0.9 and r['soc_final'] == 0.9, ('lille batteri', r)
    assert hh.async_render({**v, 'hh': None}) == {}, 'den rigtige plan'
    # scriptet sender batteriet videre
    s = load_yaml(str(REPO / 'packages/wattlas/wattlas_styring.yaml'))['script']['wattlas_hvadhvis']
    assert 'batteri_kwh' in s['fields'] and 'batteri_kwh' in s['sequence'][-1]['data']['hvadhvis'], 'script'

    # ---------------- plan mod virkelighed: dagsplanen ----------------
    from datetime import timedelta
    from types import SimpleNamespace
    from homeassistant.util import dt as dt_util
    sensor = load_yaml(str(REPO / 'packages/wattlas/wattlas_dagsplan.yaml'))['template'][0]
    assert sensor['triggers'][0]['at'] == '23:50:00', sensor['triggers']
    a = sensor['sensor'][0]['attributes']
    i_morgen = (dt_util.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tider = [i_morgen + timedelta(minutes=30 * k) for k in range(-2, 3)]  # to halvtimer i dag (skal ikke med) og tre i morgen
    ts = [str(t) for t in tider]
    S('sensor.p_pv_forecast', '0', {'forecasts': [{'date': t, 'p_pv_forecast': 100 * k} for k, t in enumerate(ts)]})
    S('sensor.p_load_forecast', '0', {'forecasts': [{'date': t, 'p_load_forecast': 1000} for t in ts]})
    S('sensor.p_deferrable0', '0', {'deferrables_schedule': [{'date': ts[3], 'p_deferrable0': '500.0'}]})
    S('sensor.wattlas_lader_plan', '0', {'deferrables_schedule': [{'date': ts[4], 'wattlas_lader_plan': 1000}]})
    S('sensor.p_grid_forecast', '0', {'forecasts': [{'date': t, 'p_grid_forecast': -200} for t in ts]})
    S('sensor.unit_load_cost', '0', {'unit_load_cost_forecasts': [{'date': t, 'unit_load_cost': 2.5} for t in ts]})
    S('sensor.unit_prod_price', '0', {'unit_prod_price_forecasts': [{'date': t, 'unit_prod_price': 0.81234} for t in ts]})
    plan = Template(a['plan'], hass).async_render()
    sek = [int(t.timestamp()) for t in tider[2:]]
    assert plan == [[sek[0], 200, 1000, -200, 2.5, 0.812], [sek[1], 300, 1500, -200, 2.5, 0.812], [sek[2], 400, 2000, -200, 2.5, 0.812]], ('dagsplan', plan)
    # en last, der ikke kom med i den seneste plan, står på sin gamle plan: den tælles ikke
    import time as _t
    S('sensor.p_deferrable0', '0', {'deferrables_schedule': [{'date': ts[3], 'p_deferrable0': '500.0'}]}, timestamp=_t.time() - 3600)
    assert Template(a['plan'], hass).async_render()[1][2] == 1000, 'gammel plan for forbrugeren'
    this = SimpleNamespace(state='2026-01-01', attributes={'plan': [['00:00', 1, 2, 3, 4, 5]]})
    assert Template(a['forrige'], hass).async_render({'this': this}) == [['00:00', 1, 2, 3, 4, 5]] and Template(a['forrige_dag'], hass).async_render({'this': this}) == '2026-01-01'
    assert Template(a['forrige_dag'], hass).async_render({'this': SimpleNamespace(state='unknown', attributes={})}) is None, 'første gang'
    S('sensor.p_pv_forecast', 'unavailable', {})
    assert Template(a['plan'], hass).async_render() == [], 'ingen plan'

    await hass.async_stop()
    print('Hvad-hvis med andet batteri og dagsplan: OK')
    await vagt_test()
    await varmtvand_test()
    await systemtest_test()
    await sommertid_test()
    ladetid_test()
    # EMHASS' lastsensorer findes kun, mens lasten er i planen: står navnet helt i en skabelon, melder Spook "ukendt entitet" (skal deles: 'sensor.' ~ '…')
    import re
    for f in (REPO / 'packages/wattlas').glob('*.yaml'):
        fund = re.findall(r"sensor\.(?:p_deferrable\d|wattlas_lader_plan)\b", '\n'.join(x.split('#')[0] for x in f.read_text(encoding='utf-8').splitlines()))
        assert not fund, (f.name, fund)
    print('Spook: ingen hele lastnavne i skabeloner: OK')
    print('OK – 0.7.0')


AUT = """
automation:
  - id: wattlas_varmtvand  # et id fra Wattlas' egne filer
    alias: Wattlas kanal
    triggers: [{trigger: state, entity_id: sensor.inv_soc}]
    actions: [{action: number.set_value, target: {entity_id: number.inv_program_1_power}, data: {value: 1}}]
  - id: min_egen
    alias: Min egen batteristyring
    triggers: [{trigger: time, at: '01:00:00'}]
    actions: [{action: number.set_value, target: {entity_id: number.inv_program_2_power}, data: {value: 5000}}]
  - id: slaaet_fra
    alias: Slået fra
    initial_state: false
    triggers: [{trigger: time, at: '02:00:00'}]
    actions: [{action: number.set_value, target: {entity_id: number.inv_program_2_power}, data: {value: 1}}]
  - id: laeser_kun
    alias: Læser kun
    triggers: [{trigger: state, entity_id: sensor.inv_soc}]
    actions: [{action: switch.turn_on, target: {entity_id: switch.lampe}}]
script:
  wattlas_systemtest:  # et script fra Wattlas' egne filer
    sequence: [{action: switch.turn_on, target: {entity_id: switch.inv_netladning}}]
  mit_script:
    sequence: [{action: switch.turn_off, target: {entity_id: switch.inv_netladning}}]
  emhass_mit_gamle:  # brugerens eget fra en hjemmelavet EMHASS-opsætning – navnet gør det ikke til Wattlas'
    sequence: [{action: number.set_value, target: {entity_id: number.inv_program_1_power}, data: {value: 0}}]
"""


async def vagt_test():
    """Andre automationer/scripts, der rører inverterens indstillinger, vises under Reparationer – Wattlas' egne, slåede-fra og læsning ikke."""
    from homeassistant import config_entries
    from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
    from homeassistant.setup import async_setup_component
    hass, cfg = await ny_hass(AUT)
    from custom_components.wattlas import vagt  # noqa: E402 (indlæses fra testens config-mappe)
    e = config_entries.ConfigEntry(version=1, minor_version=1, domain='falsk_inverter', title='inv', data={}, options={}, source='user',
                                   unique_id='inv', discovery_keys={}, subentries_data=None)
    await hass.config_entries.async_add(e)
    dev = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, identifiers={('falsk_inverter', 'inv')})
    lampe = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, identifiers={('falsk_inverter', 'lampe')})
    hw = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, identifiers={('falsk_inverter', 'hw')})
    reg = er.async_get(hass)
    for dom, navn, d in (('sensor', 'inv_soc', dev), ('number', 'inv_program_1_power', dev), ('number', 'inv_program_2_power', dev),
                         ('switch', 'inv_netladning', dev), ('switch', 'lampe', lampe), ('number', 'hw_effekt', hw)):
        reg.async_get_or_create(dom, 'falsk_inverter', navn, device_id=d.id, suggested_object_id=navn)
    from homeassistant import config as ha_config
    conf = await ha_config.async_hass_config_yaml(hass)
    for dom in ('automation', 'script'):
        assert await async_setup_component(hass, dom, conf), dom
    await hass.async_block_till_done()
    assert await vagt.tjek(hass) == {}, 'i skygge må andre gerne styre'
    hass.states.async_set('input_boolean.emhass_har_overtaget', 'on')
    fund = await vagt.tjek(hass)
    assert fund == {'automation.min_egen_batteristyring': ['number.inv_program_2_power'], 'script.emhass_mit_gamle': ['number.inv_program_1_power'],
                    'script.mit_script': ['switch.inv_netladning']}, fund
    i = ir.async_get(hass).async_get_issue('wattlas', 'anden_styring')
    assert i and 'Min egen batteristyring' in i.translation_placeholders['liste'], i
    # fjernes de, forsvinder meddelelsen; en automation, der bruger selve enheden, ses også
    uden = (AUT.replace('number.inv_program_1_power}, data: {value: 0}', 'number.andet}, data: {value: 0}').replace('number.inv_program_2_power', 'number.andet')
            .replace('switch.turn_off, target: {entity_id: switch.inv_netladning}', 'switch.turn_off, target: {entity_id: switch.lampe}'))

    async def genindlaes(tekst):
        (cfg / 'configuration.yaml').write_text(tekst, encoding='utf-8')
        for dom in ('automation', 'script'):
            await hass.services.async_call(dom, 'reload', blocking=True)
        await hass.async_block_till_done()
    await genindlaes(uden.replace("    actions: [{action: number.set_value, target: {entity_id: number.andet}, data: {value: 5000}}]",
                                  f"    actions: [{{action: number.set_value, target: {{device_id: {dev.id}}}, data: {{value: 5000}}}}]"))
    assert await vagt.tjek(hass) == {'automation.min_egen_batteristyring': ['enheden']}, 'enheden'
    # Wattlas styrer enheden med device_id (som Huaweis tjenester): dens indstillinger vogtes også
    await genindlaes(uden.replace("    sequence: [{action: switch.turn_on, target: {entity_id: switch.inv_netladning}}]",
                                  f"    sequence: [{{action: number.set_value, target: {{device_id: {hw.id}}}, data: {{value: 1}}}}]")
                         .replace("    sequence: [{action: switch.turn_off, target: {entity_id: switch.lampe}}]",
                                  "    sequence: [{action: number.set_value, target: {entity_id: number.hw_effekt}, data: {value: 2}}]"))
    assert await vagt.tjek(hass) == {'script.mit_script': ['number.hw_effekt']}, 'device_id'
    await genindlaes(uden)
    assert await vagt.tjek(hass) == {} and ir.async_get(hass).async_get_issue('wattlas', 'anden_styring') is None, 'ryddet'
    await hass.async_stop()
    print('Vagt mod anden styring: OK')


async def varmtvand_test():
    """Målet hæves kun i billige timer/ved soloverskud, mens Wattlas styrer, højst til maksimum/75 °C, holdes mindst 30 min,
    og brugerens eget mål kommer altid tilbage – også med en beholder, der først viser det nye mål ved næste aflæsning."""
    import time
    from homeassistant.setup import async_setup_component
    hass, _ = await ny_hass('')
    S = hass.states.async_set
    pk = load_yaml(str(REPO / 'packages/wattlas/wattlas_varmtvand.yaml'))
    for dom in ('input_boolean', 'input_text', 'input_number', 'automation'):
        assert await async_setup_component(hass, dom, {dom: pk[dom]}), dom
    kald, langsom, ventende = [], [False], {}

    def vis(e, felt, x):
        st = hass.states.get(e)
        S(e, str(x) if felt is None else st.state, st.attributes if felt is None else {**st.attributes, felt: x})

    def skriv(e, felt, x):  # en langsom beholder viser først det nye mål ved næste aflæsning (poll)
        kald.append(x)
        if langsom[0]:
            ventende[e] = (felt, x)
        else:
            vis(e, felt, x)

    async def vh(call):
        e = call.data['entity_id']; skriv(e[0] if isinstance(e, list) else e, 'temperature', call.data['temperature'])

    async def nr(call):
        e = call.data['entity_id']; skriv(e[0] if isinstance(e, list) else e, None, call.data['value'])

    def poll():
        for e, (felt, x) in list(ventende.items()):
            vis(e, felt, x)
        ventende.clear()
    hass.services.async_register('water_heater', 'set_temperature', vh)
    hass.services.async_register('number', 'set_value', nr)
    aut = next(e for e in hass.states.async_entity_ids('automation') if hass.states.get(e).attributes.get('id') == 'wattlas_varmtvand')

    async def k(dom, tj, **d):
        await hass.services.async_call(dom, tj, d, blocking=True); await hass.async_block_till_done()

    async def koer():
        await k('automation', 'trigger', entity_id=aut, skip_condition=False, variables={'vent_s': 1})
        await asyncio.sleep(1.2); await hass.async_block_till_done()

    def aeld():  # som om der er gået en halv time, siden målet blev hævet eller sat tilbage
        st = hass.states.get('input_number.wattlas_varmtvand_brugerens')  # samme tilstand flytter ikke last_changed: skift frem og tilbage
        S(st.entity_id, '-1', st.attributes, timestamp=time.time() - 2000); S(st.entity_id, st.state, st.attributes, timestamp=time.time() - 2000)
    temp = lambda: hass.states.get('water_heater.vv').attributes['temperature']  # noqa: E731
    gemt = lambda: float(hass.states.get('input_number.wattlas_varmtvand_brugerens').state)  # noqa: E731
    S('water_heater.vv', 'eco', {'temperature': 50, 'max_temp': 65}); S('sensor.wattlas_prisniveau', 'billig'); S('binary_sensor.emhass_ui_data_frisk', 'on')
    S('sensor.emhass_m_grid_out_total_power', '500'); S('input_boolean.emhass_styring_aktiv', 'on'); S('input_boolean.emhass_har_overtaget', 'off')
    await k('input_text', 'set_value', entity_id='input_text.wattlas_varmtvand_entitet', value='water_heater.vv')
    await k('input_number', 'set_value', entity_id='input_number.wattlas_varmtvand_ekstra', value=10)
    aeld(); await koer(); assert temp() == 50 and not kald, 'slået fra: intet'
    await k('input_boolean', 'turn_on', entity_id='input_boolean.wattlas_varmtvand'); aeld(); await koer()
    assert temp() == 50 and not kald, 'skygge: intet'
    S('input_boolean.emhass_har_overtaget', 'on'); await koer()
    assert temp() == 60 and gemt() == 50, ('billig: hævet', temp(), gemt())
    await koer(); assert temp() == 60 and len(kald) == 1, 'hævet: intet nyt'
    S('sensor.wattlas_prisniveau', 'normal'); await koer()
    assert temp() == 60, 'holdes mindst 30 min'
    aeld(); await koer()
    assert temp() == 50 and gemt() == 0, ('normal: tilbage', temp(), gemt())
    S('sensor.wattlas_prisniveau', 'billig'); await koer(); assert temp() == 50, 'ikke straks igen'
    # højst beholderens maksimum
    S('water_heater.vv', 'eco', {'temperature': 58, 'max_temp': 65}); aeld(); await koer()
    assert temp() == 65 and gemt() == 58, 'klippet til maks'
    # ekstra grader ændres undervejs: stadig Wattlas' eget mål, så det sættes tilbage
    await k('input_number', 'set_value', entity_id='input_number.wattlas_varmtvand_ekstra', value=5); await koer()
    assert temp() == 65 and gemt() == 58, 'ekstra ændret: ikke brugerens'
    # gamle målinger og hovedafbryderen stopper straks (også under de 30 min)
    S('binary_sensor.emhass_ui_data_frisk', 'off'); await koer()
    assert temp() == 58 and gemt() == 0, 'gamle målinger: tilbage'
    S('binary_sensor.emhass_ui_data_frisk', 'on'); aeld(); await koer(); assert temp() == 63, 'hævet igen (5 grader)'
    S('input_boolean.emhass_styring_aktiv', 'off'); await koer(); assert temp() == 58 and gemt() == 0, 'hovedafbryder: tilbage'
    S('input_boolean.emhass_styring_aktiv', 'on'); aeld(); await koer(); assert temp() == 63, 'igen'
    aeld(); await koer(); assert temp() == 63 and gemt() == 58, ('stadig billigt efter en halv time: det hævede gemmes aldrig som brugerens', temp(), gemt())
    # brugeren ændrer selv målet: det nye ønske står, intet sættes tilbage
    S('water_heater.vv', 'eco', {'temperature': 55, 'max_temp': 65}); await koer()
    assert temp() == 55 and gemt() == 0, 'brugerens ændring'
    S('sensor.wattlas_prisniveau', 'normal'); await koer(); assert temp() == 55, 'brugerens ændring står'
    # soloverskud hæver; beholderen æder selv overskuddet, så det holdes; importloftet sætter tilbage
    S('sensor.emhass_m_grid_out_total_power', '-2000'); aeld(); await koer(); assert temp() == 60 and gemt() == 55, 'sol'
    S('sensor.emhass_m_grid_out_total_power', '1000'); await koer(); assert temp() == 60, 'beholderen æder overskuddet: holdes'
    S('input_number.wattlas_import_graense_w', '11000'); S('sensor.emhass_m_grid_out_total_power', '12000'); await koer()
    assert temp() == 55 and gemt() == 0, 'importloft'
    # en langsom beholder: målet kravler ikke op (den gamle visning er ikke brugerens ændring, og det hævede gemmes aldrig)
    S('sensor.emhass_m_grid_out_total_power', '500'); S('sensor.wattlas_prisniveau', 'billig'); langsom[0] = True; aeld(); await koer()  # ekstra er stadig 5
    assert temp() == 55 and gemt() == 55, 'langsom: hævet, ikke vist endnu'
    await koer(); poll(); await koer()
    assert temp() == 60 and gemt() == 55, ('langsom: vist', temp(), gemt())
    S('sensor.wattlas_prisniveau', 'normal'); aeld(); await koer()
    assert gemt() == 0 and temp() == 60, 'langsom: sat tilbage, ikke vist endnu'
    S('sensor.wattlas_prisniveau', 'billig'); await koer(); assert gemt() == 0, 'det gamle hævede mål gemmes ikke som brugerens'
    poll(); aeld(); await koer(); poll()
    assert temp() == 60 and gemt() == 55, ('igen fra brugerens', temp(), gemt())
    langsom[0] = False
    # beholderen svarer ikke: intet ændres, og når den er tilbage, sættes målet tilbage
    S('water_heater.vv', 'unavailable', {}); await k('input_boolean', 'turn_off', entity_id='input_boolean.wattlas_varmtvand'); await koer()
    assert gemt() == 55, 'utilgængelig: husket'
    S('water_heater.vv', 'eco', {'temperature': 60, 'max_temp': 65}); await koer()
    assert temp() == 55 and gemt() == 0, 'tilbage, når den svarer igen'
    # number-entitet uden rigtigt maksimum (HA's standard er 100): aldrig over 75 °C
    await k('input_number', 'set_value', entity_id='input_number.wattlas_varmtvand_ekstra', value=10)
    S('number.vv_maal', '70', {'max': 100, 'min': 30}); await k('input_text', 'set_value', entity_id='input_text.wattlas_varmtvand_entitet', value='number.vv_maal')
    await k('input_boolean', 'turn_on', entity_id='input_boolean.wattlas_varmtvand'); aeld(); await koer()
    assert float(hass.states.get('number.vv_maal').state) == 75 and gemt() == 70, ('number: højst 75 °C', hass.states.get('number.vv_maal'))
    # Wattlas fjernes, mens beholderen er offline: intet nulstilles, og brugeren får besked
    from custom_components.wattlas import _varmtvand_tilbage
    beskeder = []
    hass.services.async_register('persistent_notification', 'create', lambda call: beskeder.append(call.data))
    S('number.vv_maal', 'unavailable', {})
    await _varmtvand_tilbage(hass); await hass.async_block_till_done()
    assert gemt() == 70 and beskeder and '70' in beskeder[-1]['message'], ('offline ved fjernelse', beskeder)
    assert hass.states.get('input_boolean.wattlas_varmtvand').state == 'off', 'kontakten slukkes'
    # Wattlas fjernes: brugerens mål tilbage
    S('number.vv_maal', '75.0', {'max': 100, 'min': 30})
    await _varmtvand_tilbage(hass); await hass.async_block_till_done()
    assert float(hass.states.get('number.vv_maal').state) == 70 and gemt() == 0, 'fjernet'
    await hass.async_stop()
    print('Varmt vand på billig strøm: OK')


async def systemtest_test():
    """Systemtesten starter kun under de rigtige forhold, går gennem tilsidesættelsen og slutter altid med "ingen"."""
    from homeassistant.setup import async_setup_component
    hass, _ = await ny_hass('')
    S = hass.states.async_set
    pk = load_yaml(str(REPO / 'packages/wattlas/wattlas_systemtest.yaml'))
    for dom in ('input_text', 'script'):
        assert await async_setup_component(hass, dom, {dom: pk[dom]}), dom
    ordrer, svar = [], {}

    async def tilsidesaet(call):  # den rigtige tilsidesættelse er testet andetsteds; her svarer "batteriet" efter ordren
        ordrer.append((call.data['tilstand'], call.data.get('soc')))
        S('sensor.emhass_m_battery_output_w_power', str(svar.get(call.data['tilstand'], 0)))
    hass.services.async_register('script', 'wattlas_tilsidesaet', tilsidesaet)
    tekst = lambda: hass.states.get('input_text.wattlas_systemtest').state  # noqa: E731

    async def koer(**d):
        ordrer.clear()
        await hass.services.async_call('script', 'wattlas_systemtest', {'vent_s': 1, **d}, blocking=True); await hass.async_block_till_done()
    klar = {'input_boolean.emhass_styring_aktiv': 'on', 'input_boolean.emhass_har_overtaget': 'on', 'binary_sensor.wattlas_tilsidesaettelse_aktiv': 'off',
            'binary_sensor.emhass_ui_data_frisk': 'on', 'binary_sensor.emhass_styrekanal_ok': 'on', 'sensor.emhass_m_battery_soc': '52', 'sensor.wattlas_elbil_effekt': '0',
            'sensor.emhass_m_load_w_totalpower': '900', 'sensor.emhass_m_battery_output_w_power': '0'}
    for e, x in klar.items(): S(e, x)
    for e, x, hvorfor in (('input_boolean.emhass_har_overtaget', 'off', 'skygge'), ('binary_sensor.wattlas_tilsidesaettelse_aktiv', 'on', 'tilsidesættelse'),
                          ('binary_sensor.emhass_styrekanal_ok', 'off', 'styrekanal'), ('sensor.emhass_m_battery_soc', '90', 'fuldt'), ('sensor.emhass_m_battery_soc', '15', 'tomt'),
                          ('sensor.emhass_m_battery_soc', 'unavailable', 'ukendt'), ('sensor.wattlas_elbil_effekt', '7000', 'elbil')):
        S(e, x); await koer()
        assert not ordrer and tekst().startswith('Ikke startet'), (hvorfor, tekst(), ordrer)
        S(e, klar[e])
    S('input_number.wattlas_reserve', '50'); await koer()
    assert not ordrer and 'reserven' in tekst(), ('for tæt på reserven', tekst())
    S('input_number.wattlas_reserve', '20')
    svar.update(lad=-2500, brug=1200); await koer()
    assert ordrer == [('lad', 65), ('brug', None), ('ingen', None)] and 'Lader: OK' in tekst() and 'Aflader: OK' in tekst(), (ordrer, tekst())
    svar.update(lad=0, brug=50); await koer()
    assert ordrer[-1] == ('ingen', None) and 'Lader: NEJ' in tekst() and 'Aflader: NEJ' in tekst(), (ordrer, tekst())
    S('sensor.emhass_m_load_w_totalpower', '200'); await koer()
    assert 'Aflader: uafgjort' in tekst(), tekst()
    # solen lader allerede: netladningen kan ikke ses
    S('sensor.emhass_m_load_w_totalpower', '900'); S('sensor.emhass_m_battery_output_w_power', '-2000'); svar.update(lad=-2500, brug=1200); await koer()
    assert 'Lader: uafgjort' in tekst() and 'Aflader: OK' in tekst(), tekst()
    await hass.async_stop()
    print('Test dit system: OK')


async def sommertid_test():
    """Sommer-/vintertid (døgn på 25 og 23 timer): husprognosen tager samme klokkeslæt de forrige døgn, dagsplanen gemmer rigtige
    tidspunkter (kl. 02 to gange), og kortet lægger plan og målinger sammen pr. rigtig time."""
    import json, re, shutil, subprocess
    from datetime import datetime, timedelta
    from unittest.mock import patch
    from zoneinfo import ZoneInfo
    from homeassistant.util import dt as dt_util
    hass, _ = await ny_hass('')
    S = hass.states.async_set
    await hass.config.async_set_time_zone('Europe/Copenhagen')
    Z = ZoneInfo('Europe/Copenhagen')
    try:
        # husprognosen: forbruget er klokkeslættet (kl. 07:30 = 730 W) alle dage. To dage efter skiftet skal kl. 07 give 700 – ikke 800 eller 600
        hus = Template(variabel('hus'), hass)
        S('sensor.emhass_udetemperatur_historik', '0', {'data': '[]'}); S('input_text.wattlas_vejr_entitet', 'weather.test')
        for start in (datetime(2026, 10, 27, 7, tzinfo=Z), datetime(2026, 3, 31, 7, tzinfo=Z)):
            t0 = int(start.timestamp())
            hist = [[t, datetime.fromtimestamp(t, Z).hour * 100 + datetime.fromtimestamp(t, Z).minute] for t in range(t0 - 10 * 86400, t0, 1800)]
            S('sensor.emhass_husforbrug_historik', str(len(hist)), {'data': json.dumps(hist)})
            r = hus.async_render({'prognose': {'intervaller': 4}, 'start_ts': t0, 'kulde_w_pr_grad': 0})
            assert r['ok'] and r['liste'] == [700, 730, 800, 830], ('husprognose over tidsskiftet', start, r)
        # dagsplanen for tidsskiftets døgn: alle halve timer med hver sit tidspunkt (som EMHASS: "ÅÅÅÅ-MM-DD 02:00:00+02:00")
        a = load_yaml(str(REPO / 'packages/wattlas/wattlas_dagsplan.yaml'))['template'][0]['sensor'][0]['attributes']
        for aften, halve in ((datetime(2026, 10, 24, 23, 50, tzinfo=Z), 50), (datetime(2026, 3, 28, 23, 50, tzinfo=Z), 46)):
            m0 = (aften + timedelta(minutes=10)).timestamp()
            ts = [int(m0) + 1800 * i for i in range(halve)]
            ds = [str(datetime.fromtimestamp(t, Z)) for t in ts]
            for e, attr, key in (('sensor.p_pv_forecast', 'forecasts', 'p_pv_forecast'), ('sensor.p_load_forecast', 'forecasts', 'p_load_forecast'),
                                 ('sensor.p_grid_forecast', 'forecasts', 'p_grid_forecast'), ('sensor.unit_load_cost', 'unit_load_cost_forecasts', 'unit_load_cost'),
                                 ('sensor.unit_prod_price', 'unit_prod_price_forecasts', 'unit_prod_price')):
                S(e, '0', {attr: [{'date': d, key: 1000} for d in ds]})
            with patch.object(dt_util, 'now', return_value=aften):
                plan = Template(a['plan'], hass).async_render()
            assert [p[0] for p in plan] == ts and all(p[1:3] == [1000, 1000] for p in plan), ('dagsplan over tidsskiftet', aften, [p[0] for p in plan][:8])
    finally:
        await hass.async_stop()
    # kortet (node): planens halve timer og målingernes timer pr. rigtig time
    node = shutil.which('node')
    if not node:
        print('Sommer-/vintertid: OK (kortet ikke testet – node mangler)')
        return
    kort = (REPO / 'custom_components/wattlas/payload/www/energi-app-card.js').read_text(encoding='utf-8')
    fn = re.search(r"\n  const planMaal = .*?\n  };\n", kort, re.S)
    assert fn, 'planMaal findes ikke i kortet'
    js = "process.env.TZ = 'Europe/Copenhagen';" + fn.group(0) + r"""
const ids = ['sensor.emhass_solproduktion_samlet', 'sensor.emhass_m_load_w_totalpower', 'sensor.emhass_m_grid_out_total_power'], ud = {};
for (const [navn, y, m, d] of [['vinter', 2026, 9, 25], ['sommer', 2026, 2, 29], ['normal', 2026, 10, 26]]) {
  const a = new Date(y, m, d).getTime(), b = new Date(y, m, d + 1).getTime(), P = [], M = {};
  for (let t = a; t < b; t += 18e5) P.push([t / 1000, 2000, 1000, 500, 2, 1]);
  ids.forEach(id => { M[id] = []; for (let t = a; t < b; t += 36e5) M[id].push({start: t, mean: 1000}); });
  const R = planMaal(P, M, a, b);
  ud[navn] = [R.length, [...new Set(R.map(o => o.n))], R.reduce((s, o) => s + o.pv, 0), R[R.length - 1].x, (b - a) / 36e5];
}
const a = new Date(2026, 10, 26).getTime(), b = new Date(2026, 10, 27).getTime(), M = {};
ids.forEach(id => { M[id] = [{start: a, mean: 1}]; });
ud.gammel = planMaal([['00:00', 2000, 1000, 500, 2, 1], ['00:30', 2000, 1000, 500, 2, 1], ['23:30', 1, 1, 1, 1, 1]], M, a, b).map(o => [o.x, o.n]);
console.log(JSON.stringify(ud));
"""
    p = subprocess.run([node, '-'], input=js, capture_output=True, text=True, encoding='utf-8')
    assert p.returncode == 0, p.stderr
    ud = json.loads(p.stdout)
    assert ud['vinter'] == [25, [2], 50, 24.5, 25] and ud['sommer'] == [23, [2], 46, 22.5, 23] and ud['normal'] == [24, [2], 48, 23.5, 24], ('kortet', ud)
    assert ud['gammel'] == [[0.5, 2]], ('en ældre plan med klokkeslæt', ud)
    print('Sommer-/vintertid: OK')


def ladetid_test():
    """Elbil: kortets skøn over ladetiden (kWh ved laderens fulde effekt, rundet op til 10 min; intet skøn uden energi eller effekt)."""
    import json, re, shutil, subprocess
    node = shutil.which('node')
    if not node:
        print('Ladetid: ikke testet – node mangler')
        return
    kort = (REPO / 'custom_components/wattlas/payload/www/energi-app-card.js').read_text(encoding='utf-8')
    fn = re.search(r"\n  const ladetid = .*?\n", kort)
    assert fn, 'ladetid findes ikke i kortet'
    js = fn.group(0) + "console.log(JSON.stringify([ladetid(20, 11040), ladetid(5, 11040), ladetid(20, 10000), ladetid(0, 11040), ladetid(20, 0), ladetid(20, undefined), ladetid(4, 11040)]));"
    p = subprocess.run([node, '-'], input=js, capture_output=True, text=True, encoding='utf-8')
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == ['ca. 1 t 50 min', 'ca. 30 min', 'ca. 2 t', '', '', '', 'ca. 30 min'], p.stdout
    print('Ladetid: OK')


asyncio.run(main())
