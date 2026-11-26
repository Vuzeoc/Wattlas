# Elbil-lader i Home Assistant: oversætterne, svar der ikke passer med målingen, skygge, frakobling, genstart og slip. En falsk lader adlyder (eller ej).
# Kør: python tests/test_lader_ha.py   (kræver: pip install homeassistant)
import asyncio, types
from datetime import timedelta

from test_flow import REPO, ny_hass
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml

KONF = {'slags': 'entiteter', 'effekt': 'sensor.lader_w', 'status': 'sensor.lader_status', 'strom': 'number.lader_a', 'til_fra': 'switch.lader', 'faser': 3}


async def main():
    hass, *_ = await ny_hass('')
    import custom_components.wattlas.lader as M
    f = load_yaml(str(REPO / 'packages/wattlas/wattlas_lader.yaml'))
    for dom in ('input_select', 'input_number', 'input_datetime', 'template'):
        assert await async_setup_component(hass, dom, {dom: f[dom]}), dom
    await hass.async_block_till_done()
    S = hass.states.async_set
    ur = [1000.0]
    M.monotonic = lambda: ur[0]
    M.SVAR_S = 0  # testens målinger kommer på samme tid som ordren
    fysik = {'a': 16, 'til': False, 'adlyd': True, 'adlyd_a': True, 'fejl': False, 'bil': True, 'hus': 500, 'maal': True, 'omvendt': False}
    kald = []

    async def tjeneste(call):
        e = call.data.get('entity_id')
        e = e[0] if isinstance(e, list) else e
        kald.append((call.domain, call.service, e, call.data.get('value', call.data.get('option'))))
        if fysik['fejl']:
            raise HomeAssistantError('nej')
        if call.domain == 'number':
            if fysik['adlyd_a']:
                fysik['a'] = call.data['value']
            S('number.lader_a', call.data['value'])
        elif call.service in ('turn_on', 'turn_off'):
            til = (call.service == 'turn_on') != fysik['omvendt']
            if fysik['adlyd'] or til:
                fysik['til'] = til
                if til and fysik.get('tx'):
                    hass.loop.call_later(.4, lambda: S('sensor.tx', '42'))  # nummeret står på det gamle et øjeblik
        elif call.domain == 'button':
            fysik['til'] = e == 'button.start'
        elif call.domain == 'select':
            fysik['til'] = call.data['option'] == '2'
        elif call.domain == 'easee':
            fysik.setdefault('easee', []).append((call.service, call.data.get('action_command', call.data.get('current'))))
        elif call.domain == 'ocpp':
            lim = call.data['custom_profile']['chargingSchedule']['chargingSchedulePeriod'][0]['limit']
            assert type(lim) is int and call.data['custom_profile']['transactionId'] == 42
            fysik['ocpp_lim'] = lim
            if fysik['til']:
                fysik['a'] = lim or fysik['a']
            if lim == 0:
                fysik['til'] = False
                S('sensor.tx', '0')
    for dom, tj in (('number', 'set_value'), ('homeassistant', 'turn_on'), ('homeassistant', 'turn_off'), ('button', 'press'),
                    ('select', 'select_option'), ('ocpp', 'set_charge_rate'), ('easee', 'set_charger_dynamic_limit'), ('easee', 'action_command')):
        hass.services.async_register(dom, tj, tjeneste)

    def verden(**k):
        fysik.update(k)
        w = fysik['a'] * 690 if fysik['til'] and fysik['bil'] else 0
        S('sensor.lader_w', round(w), {'unit_of_measurement': 'W'})
        S('sensor.lader_status', 'charging' if w else 'connected' if fysik['bil'] else 'disconnected')
        m = w if fysik['maal'] else 0
        S('sensor.wattlas_elbil_effekt', m)
        for i in (1, 2, 3):
            S(f'sensor.emhass_m_external_ct_w_l{i}', m / 3 + fysik['hus'])
            S(f'sensor.emhass_m_grid_current_v_l{i}', 230)
        S('sensor.emhass_m_grid_out_total_power', m + 3 * fysik['hus'])

    async def trin(n=1, **k):
        for _ in range(n):
            verden(**k)
            ur[0] += 10
            await hass.data[M.NOEGLE].trin()
            verden()
        await hass.async_block_till_done()
        return hass.states.get('sensor.wattlas_lader')

    async def trin_raa():
        ur[0] += 10
        await hass.data[M.NOEGLE].trin()
        await hass.async_block_till_done()
        return hass.states.get('sensor.wattlas_lader')

    async def saet(dom, e, **k):
        await hass.services.async_call(dom, {'input_select': 'select_option', 'input_number': 'set_value'}[dom], {'entity_id': e, **k}, blocking=True)

    async def til(o):
        await saet('input_select', 'input_select.wattlas_lader_tilstand', option=o)
    for e, s in {'binary_sensor.emhass_ui_data_frisk': 'on', 'binary_sensor.wattlas_konfigureret': 'on', 'input_number.wattlas_fase_graense_a': 23,
                 'input_number.wattlas_sikring_a': 25, 'input_number.wattlas_import_graense_w': 30000, 'sensor.emhass_solproduktion_samlet': 0,
                 'sensor.emhass_m_load_w_totalpower': 1500}.items():
        S(e, s)
    await saet('input_number', 'input_number.wattlas_lader_maks_a', value=16)
    await saet('input_number', 'input_number.wattlas_lader_kwh', value=20)

    async def ny(**konf):
        fysik.update(a=16, til=False, adlyd=True, adlyd_a=True, fejl=False, bil=True, hus=500, maal=True, omvendt=False)
        S('number.lader_a', 16)
        await til('fra')
        await M.aktiver(hass, types.SimpleNamespace(data={'lader': {**KONF, **konf}}))
        ur[0] += 1000
        await trin()
        kald.clear()

    def problem(p):
        return ir.async_get(hass).async_get_issue('wattlas', p) is not None

    # fra = laderen røres ikke, også når bilen lader
    await ny()
    await trin(5, til=True)
    assert kald == [], 'fra: ingen kald'
    # lad nu: strømmen først; derefter skrives kun ved ændring; ned straks, op langsomt
    await ny(); await til('lad_nu')
    assert (await trin()).state == 'starter' and [k[:3] for k in kald] == [('number', 'set_value', 'number.lader_a'), ('homeassistant', 'turn_on', 'switch.lader')], kald  # strømmen først, også når den står der
    kald.clear()
    assert (await trin(6)).state == 'lader' and kald == [] and fysik['til'], kald
    await trin(1, hus=2000)
    assert kald[-1] == ('number', 'set_value', 'number.lader_a', 14) and fysik['a'] == 14, kald  # 23 A − 2000 W / 230 V = 14,3 A
    await trin(1, hus=2400)
    assert fysik['a'] == 12, 'under sikringen: kun det, der mangler'
    await trin(1, hus=4000)
    assert fysik['a'] == 6, 'over sikringen: straks laveste strøm'
    n = len(kald)
    await trin(5, hus=500)
    assert len(kald) == n, 'op først efter et minut'
    await trin(3)
    assert fysik['a'] == 16
    await til('stop'); await trin()
    assert not fysik['til'] and kald[-1][:2] == ('homeassistant', 'turn_off')
    await ny(); fysik['a'] = 6; S('number.lader_a', 6); await til('lad_nu'); await trin()
    assert [k[0] for k in kald] == ['number', 'homeassistant'], ('strømmen før start', kald)
    print('Fra, lad nu, faserne, op langsomt, stop: OK')

    # laderen siger ja, men stopper ikke
    await ny(); await til('lad_nu'); await trin(2)
    fysik['adlyd'] = False
    await til('stop'); await trin(12)
    assert problem('lader_stopper_ikke') and sum(k[1] == 'turn_off' for k in kald) >= 3, kald
    fysik['adlyd'] = True
    await trin(5)
    assert not fysik['til']
    # grænsen accepteres, men holdes ikke
    await ny(); await til('lad_nu'); await trin(2)
    fysik['adlyd_a'] = False
    await trin(8, hus=2400)
    assert problem('lader_over_graense') and not fysik['til'], ('nødstop på det målte', fysik)
    # brugeren (eller bilen) starter selv, mens Wattlas siger stop
    await ny(); await til('stop'); await trin(2)
    await trin(1, til=True); await trin(5)
    assert not fysik['til'], 'det målte tæller'
    print('Accepteret er ikke udført (stop, strøm, start udefra): OK')

    # HA genstartet midt i ladning, og laderens effekt er ukendt: stop sendes alligevel (og laderen svarer stadig ikke på noget at måle)
    await ny(); await til('stop'); fysik['til'] = True
    for _ in range(3):
        verden(); S('sensor.lader_w', 'unavailable'); ur[0] += 10
        await hass.data[M.NOEGLE].trin()
    assert not fysik['til'] and ('homeassistant', 'turn_off', 'switch.lader', None) in kald, ('ukendt effekt er ikke "står stille"', kald)
    # Wallbox uden bil: Ready og Locked betyder ingen bil
    await ny(); await til('lad_nu')
    for status in ('Ready', 'Locked', 'Disconnected'):
        S('sensor.lader_status', status); assert hass.data[M.NOEGLE]._tilsluttet() is False, status
    S('sensor.lader_status', 'Locked, car connected'); assert hass.data[M.NOEGLE]._tilsluttet() is True
    # en måler, der kun melder en gang i minuttet: ingen falsk vagt, og ingen plads, der ikke findes
    await ny(); await til('lad_nu'); await trin(4)
    ægte = hass.data[M.NOEGLE]._ny_maaling
    hass.data[M.NOEGLE]._ny_maaling = lambda nu: False
    for _ in range(8):
        verden(hus=2600); S('sensor.lader_w', 16 * 690, {'unit_of_measurement': 'W'}); S('sensor.wattlas_elbil_effekt', 16 * 690); ur[0] += 10
        await hass.data[M.NOEGLE].trin()
    assert not problem('lader_over_graense') and fysik['a'] == 11, ('en gammel måling giver hverken falsk vagt eller plads, der ikke findes', fysik)
    hass.data[M.NOEGLE]._ny_maaling = ægte
    s, M.SVAR_S = hass.data[M.NOEGLE], 8
    s.sendt_nu, s.sendt_tid = ur[0], dt_util.utcnow()
    assert not s._ny_maaling(ur[0] + 50) and s._ny_maaling(ur[0] + 101), 'en måler, der intet melder, bruges alligevel til sidst'
    s.sendt_tid = dt_util.utcnow() - timedelta(seconds=60)
    verden()
    assert s._ny_maaling(ur[0] + 1)
    M.SVAR_S = 0
    print('Langsom måler: OK')

    # kan kun tændes og slukkes: aldrig startet uden plads til fuld strøm, og slukket efter et minut uden plads
    await ny(strom=None); await til('lad_nu'); await trin(3, hus=2000)
    assert kald == [], ('13 A plads er ikke 16 A', kald)
    await trin(3, hus=500)
    assert fysik['til'] and all(k[0] == 'homeassistant' for k in kald)
    await trin(3, hus=2000)
    assert fysik['til'] and not problem('lader_over_graense')
    await trin(6)
    assert not fysik['til'] and not problem('lader_over_graense'), 'slukket for faserne, ikke som en fejl'
    print('Kun tænd/sluk: OK')

    # kaldet fejler
    await ny(); fysik['fejl'] = True; await til('lad_nu'); await trin(40)
    assert problem('lader_svarer_ikke')
    fysik['fejl'] = False
    await trin(10)
    assert fysik['til'] and not problem('lader_svarer_ikke')
    # skygge og ikke konfigureret: intet kald
    await ny(); S('input_boolean.wattlas_skygge', 'on'); await til('lad_nu')
    st = await trin(3)
    assert kald == [] and st.attributes['ordre_a'] == 16 and st.attributes['skygge'] is True, st
    S('input_boolean.wattlas_skygge', 'off')
    await ny(); S('binary_sensor.wattlas_konfigureret', 'off'); await til('lad_nu'); await trin(3)
    assert kald == []
    S('binary_sensor.wattlas_konfigureret', 'on')
    # husets målinger forsvinder
    await ny(); await til('lad_nu'); await trin(2); S('binary_sensor.emhass_ui_data_frisk', 'off')
    await trin(11)
    assert fysik['til']
    await trin(3)
    assert not fysik['til'], 'stop efter to minutter uden målinger'
    S('binary_sensor.emhass_ui_data_frisk', 'on')
    # laderens egen effekt forsvinder
    await ny(); await til('lad_nu'); await trin(2)
    for _ in range(14):
        verden(); S('sensor.lader_w', 'unavailable'); ur[0] += 10
        await hass.data[M.NOEGLE].trin()
    assert not fysik['til']
    for _ in range(40):
        verden(); S('sensor.lader_w', 'unavailable'); ur[0] += 10; await hass.data[M.NOEGLE].trin()
    n = len(kald); st = await trin(5)
    assert not fysik['til'] and len(kald) == n and st.state == 'effekten mangler', ('ikke start og stop i ring', st)
    # OCPP: ukendt effekt er 0 W, men kun når laderens egen status siger, at den ikke lader
    await ny(slags='ocpp', strom=None, transaktion='sensor.tx', devid='lader')
    for status, svar in (('Available', 0.0), ('Preparing', 0.0), ('Finishing', 0.0), ('Charging', None), ('SuspendedEV', None), ('unavailable', None), ('Faulted', None)):
        S('sensor.lader_w', 'unavailable'); S('sensor.lader_status', status)
        assert hass.data[M.NOEGLE]._effekt() == svar, status
        S('sensor.lader_w', 4100, {'unit_of_measurement': 'W'})
        assert hass.data[M.NOEGLE]._effekt() == (0.0 if svar == 0.0 else 4100), ('en gammel effekt efter ladningen', status)
    await ny()
    S('sensor.lader_w', 'unavailable'); S('sensor.lader_status', 'available')
    assert hass.data[M.NOEGLE]._effekt() is None
    # laderen sidder uden for husets måling: stoppes og prøves først igen om en halv time (ikke hvert andet minut)
    await ny(); await til('lad_nu'); await trin(10, maal=False)
    assert problem('lader_udenfor') and not fysik['til']
    n = sum(k[1] == 'turn_on' for k in kald)
    st = await trin(30, maal=False)
    assert sum(k[1] == 'turn_on' for k in kald) == n and st.state == 'uden for målingen', ('ingen ny start i pausen', st)
    print('Fejl i kald, skygge, spærre, manglende målinger, uden for målingen: OK')

    # energien tælles og nulstilles ved frakobling
    await ny(); await saet('input_number', 'input_number.wattlas_lader_ladet', value=0); await til('lad_nu'); await trin(37)
    ladet = float(hass.states.get('input_number.wattlas_lader_ladet').state)
    assert 1.0 < ladet < 1.2, ladet  # 11 kW i godt 6 min
    assert (await trin(2, bil=False)).state == 'frakoblet' and float(hass.states.get('input_number.wattlas_lader_ladet').state) == 0
    # bilen tager ikke imod (fuld): pause i stedet for at blive ved, men nyt forsøg senere
    await ny(); await til('lad_nu'); await trin(3)
    S('sensor.lader_w', 0, {'unit_of_measurement': 'W'})
    fysik_a, fysik['a'] = fysik['a'], 0
    S('number.lader_a', 16)
    st = await trin(21)
    assert st.state == 'bilen tager ikke imod', st
    fysik['a'] = fysik_a
    # klar kl.: kun planen eller nød
    await ny(); await saet('input_number', 'input_number.wattlas_lader_ladet', value=0); await til('klar')
    S('input_datetime.wattlas_lader_klar', (dt_util.now() + timedelta(hours=12)).strftime('%H:%M:%S'))
    assert (await trin(2)).state == 'venter' and not fysik['til']
    S('sensor.wattlas_lader_plan', 11000); await trin(2)
    assert fysik['til']
    S('sensor.wattlas_lader_plan', 0); await trin(2)
    assert not fysik['til']
    S('sensor.wattlas_lader_plan', 11000); S('binary_sensor.emhass_ui_planfejl', 'on'); await trin(40)
    assert not fysik['til'], 'en plan med fejl starter intet'
    S('binary_sensor.emhass_ui_planfejl', 'off')
    S('input_datetime.wattlas_lader_klar', (dt_util.now() + timedelta(hours=1)).strftime('%H:%M:%S')); await trin(40)
    assert fysik['til'] and hass.states.get('sensor.wattlas_lader').attributes['noed'] is True, 'nødladning uden plan'
    # uden statusentitet: "ladet" nulstilles, når "klar kl." er passeret – ellers lader bilen kun én nat
    await ny(status=None); await saet('input_number', 'input_number.wattlas_lader_ladet', value=19.5); await til('klar')
    s = hass.data[M.NOEGLE]; await trin()
    assert float(hass.states.get('input_number.wattlas_lader_ladet').state) == 19.5, 'ikke før fristen'
    s.frist = dt_util.now() - timedelta(minutes=1); await trin()
    assert float(hass.states.get('input_number.wattlas_lader_ladet').state) == 0 and s.frist > dt_util.now(), 'ny periode'
    # batteriet viger ikke for en bil, der ikke tager imod
    S('switch.wattlas_netladning', 'on')
    await ny(); await til('lad_nu'); await trin(3)
    S('sensor.lader_w', 0, {'unit_of_measurement': 'W'}); fysik_a, fysik['a'] = fysik['a'], 0
    st = await trin(21)
    assert st.state == 'bilen tager ikke imod' and float(hass.states.get('input_number.wattlas_lader_reserve').state) == 0, (st, hass.states.get('input_number.wattlas_lader_reserve'))
    fysik['a'] = fysik_a
    S('switch.wattlas_netladning', 'off')
    print('Energi, frakobling, fuld bil, klar kl.: OK')

    # bilen i HA: procent i stedet for kWh – men kun når den sidder i laderen
    S('input_datetime.wattlas_lader_klar', (dt_util.now() + timedelta(hours=12)).strftime('%H:%M:%S')); S('sensor.wattlas_lader_plan', 11000)
    await saet('input_number', 'input_number.wattlas_lader_maal', value=80); await saet('input_number', 'input_number.wattlas_lader_ladet', value=0)
    S('sensor.bil_soc', 50); S('sensor.bil_km', 210); S('binary_sensor.bil_stik', 'on')
    BIL = {'bil_soc': 'sensor.bil_soc', 'bil_kwh': 60.0, 'bil_stik': 'binary_sensor.bil_stik', 'bil_km': 'sensor.bil_km'}
    await ny(**BIL); await til('klar'); st = await trin(2)
    assert (st.attributes['bil_soc'], st.attributes['bil_km'], st.attributes['rest_kwh']) == (50, 210, 20.0) and fysik['til'], st
    await trin(60)  # 10 min: 1,8 kWh, og bilens procent har ikke rørt sig
    rest = (await trin(6)).attributes['rest_kwh']
    assert 17.5 < rest < 18.5, rest
    S('sensor.bil_soc', 80); st = await trin(3)
    assert not fysik['til'] and st.state == 'færdig', st
    for e, s in (('binary_sensor.bil_stik', 'off'), ('sensor.bil_soc', 'unavailable'), ('sensor.bil_soc', 150)):
        S('binary_sensor.bil_stik', 'on'); S('sensor.bil_soc', 50); S(e, s)
        await ny(**BIL); await til('klar'); st = await trin(3)
        assert st.attributes['bil_soc'] is None and st.attributes['bil_km'] is None and st.attributes['rest_kwh'] > 15, (e, st)
    S('binary_sensor.bil_stik', 'on'); S('sensor.bil_soc', 50); st = await trin(8, bil=False)
    assert st.attributes['bil_soc'] is None, 'kun fremme, når den er koblet på'
    await ny(); await til('klar'); await saet('input_number', 'input_number.wattlas_lader_ladet', value=0)
    assert (await trin(7)).attributes['bil_soc'] is None, 'ingen bil valgt'
    S('sensor.wattlas_lader_plan', 0)
    print('Bilen i HA: OK')

    # knapper, valg, omvendt kontakt, kun 0 A og OCPP
    await ny(til_fra=None, start='button.start', stop='button.stop'); await til('lad_nu'); await trin(2)
    assert fysik['til']
    await til('stop'); await trin(2)
    assert not fysik['til']
    await ny(til_fra='select.frc', til_valg='2', fra_valg='1'); await til('lad_nu'); await trin(2)
    assert fysik['til']
    await til('stop'); await trin(2)
    assert not fysik['til']
    await ny(omvendt=True); fysik['omvendt'] = True; await til('lad_nu'); await trin(2)
    assert fysik['til'] and kald[-1][1] == 'turn_off', kald
    await til('stop'); await trin(2)
    assert not fysik['til']
    await ny(til_fra=None); fysik['til'] = True; await til('lad_nu'); await trin(3); await til('stop'); await trin(3)
    assert fysik['a'] == 0
    S('sensor.tx', '41'); fysik['tx'] = True  # HA viser stadig det gamle nummer, bilen lader ikke
    await ny(slags='ocpp', strom=None, transaktion='sensor.tx', devid='lader'); await til('lad_nu'); await trin(3)
    assert [k[:2] for k in kald] == [('homeassistant', 'turn_on'), ('ocpp', 'set_charge_rate')] and fysik['til'], kald
    S('sensor.tx', '0')  # HA glemmer nummeret (som efter RemoteStop), men laderen lader videre
    await til('stop'); await trin(3)
    assert not fysik['til'] and not any(k[1] == 'turn_off' for k in kald), 'stop = 0 A på det huskede nummer, aldrig stop-kontakten'
    S('sensor.tx', '42')  # en lader, hvor 0 A kun pauser: transaktionen fortsætter
    await til('fra'); await trin()
    assert kald[-1][0] == 'ocpp' and fysik['ocpp_lim'] == 16, ('fra: strømmen tilbage på transaktionen', kald[-1], fysik)
    n = len(kald); await trin(6)
    assert len(kald) == n, 'stoppet er stoppet'
    # en lader, der kun pauser ved 0 A: samme transaktion genoptages med grænsen, uden ny start
    await ny(slags='ocpp', strom=None, transaktion='sensor.tx', devid='lader'); S('sensor.tx', '42'); await til('lad_nu')
    hass.data[M.NOEGLE]._effekt, hass.data[M.NOEGLE].lader._status = (lambda: 0.0), (lambda: 'suspendedevse')
    await trin(2)
    assert [k[0] for k in kald] == ['ocpp'], kald
    fysik['tx'] = False
    print('Knapper, valg, omvendt, 0 A og OCPP: OK')

    # skygge slået til midt i en ladning: laderen slippes (brugerens egen strøm tilbage) og vises kun
    await ny(); S('number.lader_a', 13); fysik['a'] = 13; await til('lad_nu'); await trin(2)
    assert fysik['a'] == 16
    S('input_boolean.wattlas_skygge', 'on'); await trin(2)
    assert fysik['a'] == 13 and hass.data[M.NOEGLE].sendt is None, ('skygge slipper laderen', fysik)
    S('input_boolean.wattlas_skygge', 'off')
    # kan kun tændes og slukkes: opsætningens strøm gælder, ikke appens tal
    await ny(strom=None, maks_a=16); await saet('input_number', 'input_number.wattlas_lader_maks_a', value=10); await til('lad_nu')
    st = await trin(2, hus=2600)  # plads til 10 A, men ikke til de 16 A, laderen trækker
    assert not fysik['til'] and st.attributes['fast_a'] is True, st
    assert st.attributes['hold_kan'] is True, 'kontakten "Kun fra elnettet" vises'
    await saet('input_number', 'input_number.wattlas_lader_maks_a', value=16)
    # aldrig over opsætningens højeste, selv om appens tal står højere
    await ny(maks_a=13); await saet('input_number', 'input_number.wattlas_lader_maks_a', value=20); await til('lad_nu'); await trin(2)
    assert fysik['a'] == 13, fysik
    await saet('input_number', 'input_number.wattlas_lader_maks_a', value=16)
    # kun strøm-tal: tallet står allerede på 0, men laderen trækker – vagten skriver igen
    await ny(til_fra=None); await til('lad_nu'); await trin(2); await til('stop'); await trin(2)
    fysik['adlyd_a'] = False; fysik['a'] = 16; fysik['til'] = True; n = sum(k[0] == 'number' for k in kald)
    await trin(8)
    assert sum(k[0] == 'number' for k in kald) > n + 1, ('stop sendes igen, også når tallet står på 0', kald[-4:])
    fysik['adlyd_a'] = True
    # en sænkning, der ikke kommer igennem: stop straks
    await ny(); await til('lad_nu'); await trin(2); fysik['fejl'] = True
    await trin(1, hus=2400)
    fysik['fejl'] = False
    assert ('homeassistant', 'turn_off', 'switch.lader', None) in kald and hass.data[M.NOEGLE].sendt == 0, kald
    # én fase på en trefaset lader: "klar" regner ud fra det målte (11 A × 230 V, ikke × 3)
    await ny(); await til('lad_nu'); await trin(2)
    S('sensor.lader_w', 16 * 230, {'unit_of_measurement': 'W'}); st = await trin_raa()
    assert st.attributes['p_maks_w'] < 4000, ('én fase', st.attributes['p_maks_w'])
    # Easee: dynamisk grænse og pause/genoptag; slip giver grænsen tilbage
    await ny(slags='easee', enhed='dev1', strom=None, til_fra=None); fysik['easee'] = []
    await til('lad_nu'); await trin(); await til('stop'); await trin(); await til('fra'); await trin()
    assert fysik['easee'][:2] == [('set_charger_dynamic_limit', 16), ('action_command', 'resume')] and ('action_command', 'pause') in fysik['easee'] and fysik['easee'][-1] == ('set_charger_dynamic_limit', 32), fysik['easee']
    # brugerens egen strøm gives tilbage; HA lukker midt i ladning
    await ny(); S('number.lader_a', 13); fysik['a'] = 13; await til('lad_nu'); await trin(2)
    assert fysik['a'] == 16
    await til('fra'); await trin()
    assert fysik['a'] == 13
    await ny(); await til('lad_nu'); await trin(2)
    assert fysik['til']
    await hass.data[M.NOEGLE].luk()
    assert not fysik['til'], 'ingen ladning uden fasevagt'
    await M.afslut(hass)
    assert M.NOEGLE not in hass.data and not problem('lader_stopper_ikke')
    # HA lukker: en lader, der kun stoppes med 0 A, bliver på 0 A (men gives tilbage, når Wattlas fjernes)
    await ny(til_fra=None); S('number.lader_a', 13); fysik['a'] = 13; await til('lad_nu'); await trin(2); await til('stop'); await trin(2)
    assert fysik['a'] == 0
    await hass.data[M.NOEGLE].luk(object())
    assert fysik['a'] == 0, ('ingen fuld strøm uden fasevagt ved genstart', fysik)
    await ny(til_fra=None); S('number.lader_a', 13); fysik['a'] = 13; await til('lad_nu'); await trin(2); await til('stop'); await trin(2)
    await hass.data[M.NOEGLE].luk()
    assert fysik['a'] == 13, 'fjernet: brugerens strøm tilbage'
    # sommertid: lørdag 22:00 før skiftet til kl. 07 er 8 rigtige timer, ikke 9
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ægte_nu = M.dt_util.now
    M.dt_util.now = lambda: datetime(2027, 3, 27, 22, 0, tzinfo=ZoneInfo('Europe/Copenhagen'))
    try:
        S('input_datetime.wattlas_lader_klar', '07:00:00')
        assert abs(hass.data[M.NOEGLE]._timer()[0] - 8.0) < 1e-9, hass.data[M.NOEGLE]._timer()
    finally:
        M.dt_util.now = ægte_nu
    # genstart, mens fristen passerede: "ladet" nulstilles alligevel
    S('sensor.wattlas_lader', 'venter', {'tid': (dt_util.now() - timedelta(days=2)).isoformat()})
    await saet('input_number', 'input_number.wattlas_lader_ladet', value=19.5)
    s = M.Styring(hass, types.SimpleNamespace(data={'lader': {**KONF, 'status': None}}))
    assert s._timer()[2] is True
    S('sensor.wattlas_lader', 'venter', {'tid': dt_util.now().isoformat()})
    s = M.Styring(hass, types.SimpleNamespace(data={'lader': KONF}))
    assert s._timer()[2] is False, 'en kort genstart nulstiller ikke'
    # nedlukning: et trin efter luk() starter intet, heller ikke efter et afbrudt start-trin
    await ny(); await til('lad_nu'); await trin(2)
    s = hass.data[M.NOEGLE]; s.sendt = 0  # som hvis et trin blev afbrudt midt i en start
    await s.luk(object()); kald.clear()
    await trin(3)
    assert not fysik['til'] and not any(k[1] == 'turn_on' for k in kald), ('intet efter luk', kald)
    await M.aktiver(hass, types.SimpleNamespace(data={'lader': {**KONF}, 'kanal': 'sonnen'})); ur[0] += 1000
    assert (await trin()).attributes['hold_kan'] is False, 'Sonnen kan ikke holde batteriet: kontakten skjules'
    print('Egen strøm tilbage, luk og afslut: OK')
    await hass.async_stop(force=True)


asyncio.run(main())
