# Den fleksible forbruger kørt i en rigtig (minimal) Home Assistant: plads på faserne, netladningen viger, frisk plan, overbelastning.
# Kør: python tests/test_forbruger.py   (kræver: pip install homeassistant)
import asyncio, pathlib, sys, tempfile, time, types
if sys.platform == 'win32':  # Home Assistant importerer to moduler, der kun findes på Linux
    for m in ('fcntl', 'resource'):
        mod = types.ModuleType(m); mod.__getattr__ = lambda n: (lambda *a, **k: (0, 0)); sys.modules[m] = mod
from homeassistant import bootstrap, config_entries, core, loader
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

PK = pathlib.Path(__file__).parent.parent / 'packages/wattlas'
VAND, PLAN, RES = 'input_boolean.vand', 'sensor.p_deferrable0', 'input_number.wattlas_forbruger1_reserve'
AUTO = 'automation.wattlas_fleksibel_forbruger_folger_planen'


def find(o, key):
    if isinstance(o, dict) and key in o:
        return o
    for v in (o.values() if isinstance(o, dict) else o if isinstance(o, list) else []):
        if (r := find(v, key)) is not None:
            return r
    return None


async def main():
    hass = core.HomeAssistant(tempfile.mkdtemp())
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    assert await bootstrap.async_load_base_functionality(hass)
    await hass.config.async_set_time_zone('Europe/Copenhagen')
    hass.set_state(core.CoreState.running)
    f, st = load_yaml(str(PK / 'wattlas_forbruger.yaml')), load_yaml(str(PK / 'wattlas_styring.yaml'))
    for dom, conf in {'input_number': {**f['input_number'], **st['input_number']}, 'input_boolean': {'vand': None},
                      'input_text': st['input_text'], 'template': f['template'], 'automation': f['automation'], 'logbook': {}, 'homeassistant': {}}.items():
        assert await async_setup_component(hass, dom, {dom: conf}) or dom == 'logbook', dom
    await hass.async_block_till_done()

    def sæt(e, s, gammel=0, **attr):  # gammel = sekunder siden, tilstanden sidst skiftede/blev meldt
        hass.states.async_remove(e)
        hass.states.async_set(e, str(s), attr, timestamp=time.time() - gammel)

    async def tal(navn, v):
        await hass.services.async_call('input_number', 'set_value', {'entity_id': f'input_number.wattlas_forbruger1_{navn}', 'value': v}, blocking=True)

    def hus(faser=(500, 500, 500), batteri=0, lader=False):
        for i in range(3):
            sæt(f'sensor.emhass_m_external_ct_w_l{i + 1}', faser[i]); sæt(f'sensor.emhass_m_grid_current_v_l{i + 1}', 230)
        sæt('sensor.emhass_m_grid_out_total_power', sum(faser)); sæt('sensor.emhass_m_battery_output_w_power', batteri)
        sæt('switch.wattlas_netladning', 'on' if lader else 'off')

    async def kør():
        await hass.services.async_call('automation', 'trigger', {'entity_id': AUTO, 'skip_condition': False}, blocking=True)
        await hass.async_block_till_done()
        return hass.states.get(VAND).state, float(hass.states.get(RES).state)

    async def forfra(tændt=False, plan=3000, plan_alder=5, siden=700):
        sæt(VAND, 'on' if tændt else 'off', siden); sæt(PLAN, plan, plan_alder); await tal('koert', 0); await tal('reserve', 0)
        sæt('binary_sensor.emhass_ui_datafejl', 'off'); sæt('binary_sensor.emhass_ui_data_frisk', 'on')
        hus()

    assert hass.states.get(AUTO), [s.entity_id for s in hass.states.async_all('automation')]
    for e in ('input_boolean.wattlas_forbruger1_aktiv', 'input_boolean.emhass_styring_aktiv'):
        sæt(e, 'on')
    sæt('binary_sensor.emhass_ui_planfejl', 'off')
    for e, v in (('fase_graense_a', 20), ('import_graense_w', 13000)):
        sæt(f'input_number.wattlas_{e}', v)
    sæt('sensor.emhass_solproduktion_samlet', 0); sæt('sensor.emhass_m_load_w_totalpower', 1500)
    await hass.services.async_call('input_text', 'set_value', {'entity_id': 'input_text.wattlas_forbruger1_entitet', 'value': VAND}, blocking=True)
    await tal('effekt', 3000); await tal('timer', 2); await tal('faser', 1)

    # 1) plads: tændes, og timerne tæller
    await forfra()
    assert await kør() == ('on', 3000 * 3)
    assert 0 < float(hass.states.get('input_number.wattlas_forbruger1_koert').state) < .02
    # 2) én fase har ikke plads (2000 + 3000 > 20 A × 230 V), og batteriet lader ikke: forbliver slukket, netladningen røres ikke
    await forfra(); hus((500, 2000, 500))
    assert await kør() == ('off', 0)
    # 3) samme, men trefaset 3000 W = 1000 W pr. fase: der er plads
    await forfra(); hus((500, 2000, 500)); await tal('faser', 3)
    assert await kør() == ('on', 3000)
    await tal('faser', 1)
    # … og mere, end én fase kan bære (6000 W > 20 A × 230 V), regnes som trefaset – ellers kunne den aldrig starte
    await forfra(); await tal('effekt', 6000)
    assert await kør() == ('on', 6000)
    await tal('effekt', 3000)
    # 4) netladningen fylder fasen: pladsen holdes fri, og kernens ladebudget falder med præcis det
    await forfra(); hus((4000, 3000, 3000), batteri=-7600, lader=True)
    V = find(load_yaml(str(PK / 'emhass_forbindelse.yaml')), 'ladebudget_w')['ladebudget_w']
    for e, v in (('input_number.wattlas_maks_ladestroem_a', 300), ('sensor.wattlas_maks_ladestroem', 300), ('sensor.emhass_m_battery_voltage', 52)):
        sæt(e, v)
    budget = lambda: Template(V, hass).async_render({'p_batt': -20000})  # noqa: E731
    før = budget()
    assert await kør() == ('off', 9000)
    # (9800 W budget: fasen giver 3 × 600 + det, batteriet selv lader)
    assert (før, budget()) == (9800, 800), (før, budget())
    # … men ikke, når kontakten er tændt, utilgængelig eller ryddet, eller reserven har stået i 5 min. (ellers udsultes netladningen)
    for e, s, a in ((VAND, 'on', 0), (VAND, 'unavailable', 0), (RES, 9000, 301)):
        gemt = hass.states.get(e).state
        sæt(e, s, a)
        assert budget() == 9800, (e, s, budget())
        sæt(e, gemt, 700 if e == VAND else 0)
    assert budget() == 800
    # … batteriet er veget: forbrugeren tændes, og pladsen holdes fri, til den har kørt et minut
    hus((1000, 500, 500))
    assert await kør() == ('on', 9000)
    assert budget() > 0 and await kør() == ('on', 0)
    # 5) importloftet (13 kW) er brugt: ikke tændt, selv om hver fase har plads
    await forfra(); hus((1500, 1500, 1500)); sæt('sensor.emhass_m_grid_out_total_power', 11000)
    assert (await kør())[0] == 'off'
    # 6) en fase uden måling, eller gamle målinger: ikke tændt
    await forfra(); sæt('sensor.emhass_m_external_ct_w_l2', 'unavailable')
    assert (await kør())[0] == 'off'
    await forfra(); sæt('binary_sensor.emhass_ui_data_frisk', 'off')
    assert (await kør())[0] == 'off'
    # 7) planen er gammel (forbrugeren er taget ud af planen): slukkes/tændes ikke
    await forfra(plan_alder=800)
    assert await kør() == ('off', 0)
    await forfra(tændt=True, plan_alder=800)
    assert await kør() == ('off', 0)
    # … men "planen er frisk" blinker ved hvert halvtimeskift og må ikke få kontakten til at klappe; en rigtig planfejl (3 min.) slukker
    await forfra(tændt=True); sæt('binary_sensor.emhass_ui_plan_frisk', 'off')
    assert await kør() == ('on', 0)
    sæt('binary_sensor.emhass_ui_planfejl', 'on')
    assert await kør() == ('off', 0)
    sæt('binary_sensor.emhass_ui_planfejl', 'off')
    # 8) 10 min. pause efter en slukning
    await forfra(siden=300)
    assert await kør() == ('off', 0)
    # 9) kører: kort måleudfald slukker ikke, men datafejl gør
    await forfra(tændt=True); sæt('binary_sensor.emhass_ui_data_frisk', 'off')
    assert (await kør())[0] == 'on'
    sæt('binary_sensor.emhass_ui_datafejl', 'on')
    assert (await kør())[0] == 'off'
    # 10) overbelastet: føleren skal have stået på i et minut, og så slukkes der
    await forfra(tændt=True); hus((5000, 500, 500))
    await asyncio.sleep(.2); await hass.async_block_till_done()
    assert hass.states.get('binary_sensor.wattlas_forbruger1_overbelaster').state == 'off', 'skal vente et minut'
    over = Template(f['template'][0]['binary_sensor'][0]['state'], hass)
    assert over.async_render() is True
    hus((4500, 500, 500)); assert over.async_render() is False
    sæt('sensor.emhass_m_grid_out_total_power', 13500); assert over.async_render() is True
    sæt(VAND, 'off'); assert over.async_render() is False
    sæt(VAND, 'on', 700); sæt('binary_sensor.emhass_ui_data_frisk', 'off'); assert over.async_render() is False
    sæt('binary_sensor.emhass_ui_data_frisk', 'on')
    assert (await kør())[0] == 'on'
    sæt('binary_sensor.wattlas_forbruger1_overbelaster', 'on')
    assert (await kør())[0] == 'off'
    # 11) timerne er brugt, eller styringen er slukket
    await forfra(tændt=True); await tal('koert', 2)
    assert (await kør())[0] == 'off'
    await forfra(tændt=True); sæt('input_boolean.emhass_styring_aktiv', 'off')
    assert (await kør())[0] == 'off'
    sæt('input_boolean.emhass_styring_aktiv', 'on')
    # 12) slås forbrugeren fra, røres kontakten ikke, men reserven ryddes
    await forfra(tændt=True); await tal('reserve', 9000); sæt('input_boolean.wattlas_forbruger1_aktiv', 'off')
    assert await kør() == ('on', 0)
    sæt('input_boolean.wattlas_forbruger1_aktiv', 'on')
    print('Fleksibel forbruger: plads, reserve, frisk plan, pause og overbelastning: OK')

    # 13) timerne klippes til det, der kan nås inden fristen (ellers kan EMHASS ikke løse opgaven, og batteriet får ingen plan)
    fb = find(load_yaml(str(PK / 'emhass_forbindelse.yaml')), 'fb_ekstra')['fb_ekstra']
    from homeassistant.util import dt as dt_util
    from datetime import timedelta
    for minutter, timer, forventet in ((65, 5, 1.0), (600, 2, 2.0), (25, 3, .5)):
        await tal('koert', 0); await tal('timer', timer)
        sæt('input_datetime.wattlas_forbruger1_faerdig', (dt_util.now() + timedelta(minutes=minutter)).strftime('%H:%M:%S'))
        r = Template(fb, hass).async_render({'hh': None, 'prognose': {'intervaller': 48}})
        assert r['operating_hours_of_each_deferrable_load'] == [forventet], (minutter, timer, r)
        assert r['end_timesteps_of_each_deferrable_load'][0] >= forventet * 2
    print('Timerne klippes til fristen: OK')
    await hass.async_stop(force=True)


asyncio.run(main())
