# Wattlas' lette hjerne (lethjerne.py): optimeringen som tal, og tjenesten wattlas.emhass med den lette hjerne – at den udgiver præcis de
# sensorer, Wattlas' egen kontrol af planen (emhass_forbindelse.yaml: resultater_ok og candidate) godkender.
# Kør: python tests/test_lethjerne.py
import asyncio, pathlib, sys, time, types
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'custom_components/wattlas'))
import lethjerne as L

N = 48


def bestil(**k):
    d = dict(prediction_horizon=N, optimization_time_step=30, load_forecast_method='list', pv_power_forecast=[0] * N, load_power_forecast=[1000] * N,
             load_cost_forecast=[2.0] * N, prod_price_forecast=[0.5] * N, soc_init=0.5, battery_minimum_state_of_charge=0.15,
             battery_maximum_state_of_charge=1.0, soc_final=0.3, battery_nominal_energy_capacity=10000, battery_charge_power_max=5000,
             battery_discharge_power_max=5000, maximum_power_from_grid=11000, maximum_power_to_grid=9000, set_use_battery=True,
             set_nodischarge_to_grid=True, battery_charge_efficiency=0.95, battery_discharge_efficiency=0.95, weight_battery_discharge=0.25,
             number_of_deferrable_loads=0)
    d.update(k)
    return d


def tjek_graenser(p, d):
    """Det, Wattlas' kontrol af planen kræver: SOC i grænserne, effekterne inden for grænserne, ingen batterisalg."""
    for i in range(len(p['p_batt'])):
        assert 15 - 1e-6 <= p['soc'][i] <= 100 + 1e-6, ('SOC', i, p['soc'][i])
        assert -d['battery_charge_power_max'] - 1 <= p['p_batt'][i] <= d['battery_discharge_power_max'] + 1, ('batteri', i, p['p_batt'][i])
        assert -d['maximum_power_to_grid'] - 1 <= p['p_grid'][i], ('eksport', i, p['p_grid'][i])
        netto = d['load_power_forecast'][i] + sum(lp[i] for lp in p['laster']) - d['pv_power_forecast'][i]
        assert p['p_batt'][i] <= max(0, netto) + 1, ('batteriet sælger', i, p['p_batt'][i], netto)


def rent():
    # 1) billig nat, dyr aften: lad i det billige, aflad i det dyre, slut mindst på 30 %
    d = bestil(load_cost_forecast=[1.0] * 16 + [4.0] * 16 + [2.0] * 16, soc_init=0.2)
    p = L.optimer(d, 0)
    tjek_graenser(p, d)
    assert sum(1 for x in p['p_batt'][:16] if x < -100) >= 4 and sum(1 for x in p['p_batt'][16:32] if x > 100) >= 12, p['p_batt']
    assert p['soc'][-1] >= 29.9 and len(p['p_batt']) == N, p['soc'][-1]
    # 2) samme pris hele døgnet: ingen netladning (slid og tab gør det dyrere)
    p = L.optimer(bestil(), 0)
    assert all(x >= -1 for x in p['p_batt']), ('ingen grund til netladning', p['p_batt'])
    # 3) fuldt batteri og mere sol, end der må sælges: planen kan løses (resten skæres fra), og eksportloftet holdes
    d = bestil(pv_power_forecast=[15000] * N, load_power_forecast=[500] * N, maximum_power_to_grid=5000, soc_init=1.0, soc_final=0.3)
    p = L.optimer(d, 0)
    tjek_graenser(p, d)
    assert min(p['p_grid']) >= -5000 - 1, min(p['p_grid'])
    # 4) negativ salgspris: intet salg
    d = bestil(pv_power_forecast=[6000] * N, load_power_forecast=[500] * N, prod_price_forecast=[-0.3] * N, soc_init=1.0)
    p = L.optimer(d, 0)
    assert min(p['p_grid']) >= -1, ('salg ved negativ pris', min(p['p_grid']))
    # 5) intet batteri (hvad-hvis med 0 kWh): ingen batteri-effekt, SOC uændret
    d = bestil(battery_charge_power_max=0, battery_discharge_power_max=0, soc_final=0.5)
    p = L.optimer(d, 0)
    assert all(abs(x) < 1e-6 for x in p['p_batt']) and all(abs(s - 50) < 1e-6 for s in p['soc']), p['p_batt'][:4]
    # 6) uløselig: et slut-niveau, der ikke kan nås
    try:
        L.optimer(bestil(battery_charge_power_max=0, soc_final=1.0), 0); raise AssertionError('uløselig plan skal give PlanFejl')
    except L.PlanFejl as e:
        assert 'Infeasible' in str(e)
    # 7) fleksibel last (3 kW, 1 time, inden for de første 12 halvtimer): i de billigste halvtimer
    pris = [3.0] * N; pris[5] = pris[6] = 0.5
    d = bestil(load_cost_forecast=pris, number_of_deferrable_loads=1, nominal_power_of_deferrable_loads=[3000], operating_hours_of_each_deferrable_load=[1],
               start_timesteps_of_each_deferrable_load=[0], end_timesteps_of_each_deferrable_load=[12])
    p = L.optimer(d, 0)
    assert [i for i, x in enumerate(p['laster'][0]) if x > 0] == [5, 6], p['laster'][0][:12]
    tjek_graenser(p, d)
    try:
        L.optimer(bestil(number_of_deferrable_loads=1, nominal_power_of_deferrable_loads=[3000], operating_hours_of_each_deferrable_load=[9],
                         end_timesteps_of_each_deferrable_load=[4]), 0); raise AssertionError('en last, der ikke kan nås, skal give PlanFejl')
    except L.PlanFejl:
        pass
    # 8) lille hus (200 W) og lille batteri: der aflades stadig i de dyre timer (ét gittertrin må ikke spærre for små laster)
    d = bestil(load_power_forecast=[200] * N, battery_nominal_energy_capacity=5000, load_cost_forecast=[4.0] * N, soc_init=0.9)
    p = L.optimer(d, 0)
    assert sum(p['p_batt']) > 200 * N * 0.5, ('lille hus aflader ikke', p['p_batt'][:6])
    tjek_graenser(p, d)
    # 8b) stort batteri, lille forbrug og høj salgspris: ét gittertrin (375 Wh) er mere end husets halve time – batteriet må stadig ikke sælge
    d = bestil(load_power_forecast=[200] * N, battery_nominal_energy_capacity=30000, load_cost_forecast=[4.0] * N, prod_price_forecast=[3.0] * N, soc_init=0.9)
    tjek_graenser(L.optimer(d, 0), d)
    # 8c) lige over minimum (afrundes op i gitteret): planen må aldrig gå under minimum (Wattlas' kontrol kræver SOC >= 15 %)
    d = bestil(soc_init=0.158, soc_final=0.15, load_cost_forecast=[4.0] * N, load_power_forecast=[2000] * N)
    tjek_graenser(L.optimer(d, 0), d)
    # 9) importloftet: netladning kun op til loftet
    d = bestil(load_cost_forecast=[0.5] * 8 + [4.0] * 40, load_power_forecast=[3000] * N, maximum_power_from_grid=5000, soc_init=0.15, soc_final=0.15)
    p = L.optimer(d, 0)
    assert max(p['p_grid'][:8]) <= 5000 + 1, max(p['p_grid'][:8])
    # 10) en bestilling, der mangler noget, eller ikke er tal
    for k in (dict(pv_power_forecast=None), dict(load_power_forecast=[1] * 3), dict(load_cost_forecast=['x'] * N), dict(prediction_horizon=2)):
        try:
            L.optimer(bestil(**k), 0); raise AssertionError(('ufuldstændig bestilling', k))
        except L.PlanFejl:
            pass
    # 11) ny installation uden forbrugsprognose ("naive"): reserven bruges
    p = L.optimer(bestil(load_forecast_method='naive', load_power_forecast=None), 0, 1500)
    assert p['p_load'] == [1500] * N
    # 11b) to laster (3 kW + 8 kW) og et hus på 1 kW under et importloft på 11 kW: de lægges aldrig oven i hinanden over loftet
    pris = [3.0] * N; pris[4:8] = [0.5] * 4
    d = bestil(load_cost_forecast=pris, maximum_power_from_grid=11000, number_of_deferrable_loads=2, nominal_power_of_deferrable_loads=[3000, 8000],
               operating_hours_of_each_deferrable_load=[1, 1], start_timesteps_of_each_deferrable_load=[0, 0], end_timesteps_of_each_deferrable_load=[N, N])
    p = L.optimer(d, 0)
    assert max(p['p_grid']) <= 11000 + 1 and not any(p['laster'][0][i] and p['laster'][1][i] for i in range(N)), (max(p['p_grid']), p['laster'])
    # 11c) lav ladeeffekt (koldt batteri: 450 W på et 20 kWh batteri): planen kan stadig lade op til slut-niveauet, og en ladegrænse på 1 kW udnyttes
    p = L.optimer(bestil(battery_nominal_energy_capacity=20000, battery_charge_power_max=450, soc_init=0.2, soc_final=0.3), 0)
    assert p['soc'][-1] >= 29.9, p['soc'][-1]
    p = L.optimer(bestil(battery_nominal_energy_capacity=30000, battery_charge_power_max=1000, load_cost_forecast=[0.5] * 8 + [4.0] * 40, soc_init=0.2), 0)
    assert min(p['p_batt']) <= -990, ('ladegrænsen udnyttes', min(p['p_batt']))
    # 11d) "hold niveauet" (hvad-hvis uden batteri, reserve = SOC): ingen fejl og ingen unødig netladning, uanset hvordan SOC rundes
    for s in (0.37, 0.43, 0.44, 0.48, 0.61):
        L.optimer(bestil(battery_charge_power_max=0, battery_discharge_power_max=0, soc_init=s, soc_final=s), 0)
        p = L.optimer(bestil(soc_init=s, battery_minimum_state_of_charge=s, soc_final=s), 0)
        assert all(x >= -1 for x in p['p_batt']) and min(p['soc']) >= s * 100 - 1e-6, (s, min(p['p_batt']), min(p['soc']))
    # 12) tiden: 96 halvtimer (to døgn med kvarterpriser regnet om), stort batteri – også på en lille maskine skal det være hurtigt
    d = dict(bestil(), prediction_horizon=96, battery_nominal_energy_capacity=30000, battery_charge_power_max=9000, battery_discharge_power_max=20000,
             **{k: (bestil()[k] * 2) for k in ('pv_power_forecast', 'load_power_forecast', 'prod_price_forecast')},
             load_cost_forecast=([1.0] * 12 + [4.0] * 12) * 4)
    t0 = time.perf_counter(); L.optimer(d, 0); tid = time.perf_counter() - t0
    assert tid < 2, tid
    print(f'Let hjerne som tal: OK ({tid * 1000:.0f} ms for 96 halvtimer)')


async def ha():
    """Tjenesten med den lette hjerne og Wattlas' egen kontrol af den udgivne plan."""
    from homeassistant import core
    from homeassistant.helpers.template import Template
    from homeassistant.util import dt as dt_util
    from homeassistant.util.yaml import load_yaml
    import tempfile, importlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    E = importlib.import_module('custom_components.wattlas.emhass')
    hass = core.HomeAssistant(tempfile.mkdtemp())
    await hass.async_start()
    hass.config_entries = types.SimpleNamespace(async_entries=lambda d: [types.SimpleNamespace(data={'hjerne': 'let'})])
    E.opret(hass)
    S = hass.states.async_set
    for e, v in {'sensor.emhass_m_load_w_totalpower': 900, 'input_number.wattlas_maks_eksport_w': 9000, 'input_number.wattlas_maks_netimport_w': 11000,
                 'input_number.wattlas_maks_ladeeffekt_w': 5000, 'input_number.wattlas_maks_afladeeffekt_w': 5000}.items():
        S(e, str(v))

    async def kald(handling, data):
        return (await hass.services.async_call('wattlas', 'emhass', {'handling': handling, 'data': data}, blocking=True, return_response=True))
    cid = [dict(entity_id='sensor.p_deferrable0', unit_of_measurement='W', friendly_name='Wattlas fleksibel forbruger'),
           dict(entity_id='sensor.wattlas_lader_plan', unit_of_measurement='W', friendly_name='Wattlas elbil')]
    d = bestil(load_cost_forecast=[1.0] * 16 + [4.0] * 16 + [2.0] * 16, number_of_deferrable_loads=2, nominal_power_of_deferrable_loads=[2000, 3000],
               operating_hours_of_each_deferrable_load=[1, 1], start_timesteps_of_each_deferrable_load=[0, 0], end_timesteps_of_each_deferrable_load=[N, N],
               custom_deferrable_forecast_id=cid)
    t_foer = time.time()
    r = await kald('publish-data', dict(publish_prefix=''))
    assert r['status'] == 400, ('ingen plan endnu', r)
    r = await kald('naive-mpc-optim', d)
    assert r['status'] == 200, r
    r = await kald('publish-data', dict(method_ts_round='first', continual_publish=False, set_use_battery=True, number_of_deferrable_loads=2, custom_deferrable_forecast_id=cid))
    assert r['status'] == 200, r
    st = hass.states.get('sensor.p_batt_forecast')
    liste = st.attributes['battery_scheduled_power']
    start_ts = (time.time() // 1800) * 1800
    assert len(liste) == N and set(liste[0]) == {'date', 'p_batt_forecast'} and dt_util.parse_datetime(liste[0]['date']).timestamp() == start_ts, liste[0]
    assert hass.states.get('sensor.optim_status').state == 'Optimal' and st.attributes['unit_of_measurement'] == 'W'
    lp = hass.states.get('sensor.wattlas_lader_plan')
    assert lp.attributes['friendly_name'] == 'Wattlas elbil' and 'wattlas_lader_plan' in lp.attributes['deferrables_schedule'][0], lp.attributes
    assert 'p_deferrable0' in hass.states.get('sensor.p_deferrable0').attributes['deferrables_schedule'][0]
    # Wattlas' egen kontrol (samme skabeloner som emhass_forbindelse.yaml): resultater_ok og candidate skal godkende planen
    seq = load_yaml(str(pathlib.Path(__file__).parent.parent / 'packages/wattlas/emhass_forbindelse.yaml'))['script']['emhass_test_helios']['sequence']
    var = {k: v for blok in seq if 'variables' in blok for k, v in blok['variables'].items()}
    v = dict(publiceret_fra=t_foer, publicering={'status': 200}, charge_limit=5000, discharge_limit=5000, start_ts=start_ts)
    assert Template(var['resultater_ok'], hass).async_render(v) is True, 'Wattlas\' kontrol (resultater_ok) afviste planen'
    v['candidate_event'] = {'time': dt_util.now().isoformat(), 'input': {'start_ts': start_ts},
                            'output': Template(var['candidate_event']['output'], hass).async_render(v)}
    c = Template(var['candidate'], hass).async_render(v)
    assert c['ok'] is True and len(c['rows']) == N, ('Wattlas\' kontrol (candidate) afviste planen', c)
    # hvad-hvis (hh_): egne sensorer, den rigtige plan røres ikke
    gl = hass.states.get('sensor.p_batt_forecast').last_updated
    assert (await kald('naive-mpc-optim', dict(d, battery_charge_power_max=0, battery_discharge_power_max=0, soc_final=0.5)))['status'] == 200
    assert (await kald('publish-data', dict(publish_prefix='hh_', number_of_deferrable_loads=0)))['status'] == 200
    hh = hass.states.get('sensor.hh_p_batt_forecast')
    assert 'hh_p_batt_forecast' in hh.attributes['battery_scheduled_power'][0] and hass.states.get('sensor.p_batt_forecast').last_updated == gl
    # ny installation uden forbrugsprognose: husets forbrug nu, uden en kørende fleksibel forbruger (den planlægges for sig)
    S('sensor.emhass_m_load_w_totalpower', '4000'); S('switch.vand', 'on'); S('input_boolean.wattlas_forbruger1_aktiv', 'on')
    S('input_text.wattlas_forbruger1_entitet', 'switch.vand'); S('input_number.wattlas_forbruger1_effekt', '3000')
    assert (await kald('naive-mpc-optim', dict(d, load_forecast_method='naive', load_power_forecast=None, number_of_deferrable_loads=0)))['status'] == 200
    assert (await kald('publish-data', dict(publish_prefix='hh_')))['status'] == 200
    assert float(hass.states.get('sensor.hh_p_load_forecast').state) == 1000, hass.states.get('sensor.hh_p_load_forecast')
    # en uløselig opgave: fejlkode som fra EMHASS (Wattlas beholder den gamle plan)
    r = await kald('naive-mpc-optim', dict(d, battery_charge_power_max=0, soc_final=1.0))
    assert r['status'] == 400 and 'Infeasible' in r['content'], r
    await hass.async_stop(force=True)
    print('Let hjerne bag wattlas.emhass og Wattlas\' kontrol af planen: OK')


rent()
asyncio.run(ha())
