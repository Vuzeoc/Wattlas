# Regner Wattlas' sikkerhedsregnestykker igennem med faste tal – direkte fra de filer, der bliver installeret:
# fasegrænse/importloft/ladestrøm (packages/wattlas/emhass_forbindelse.yaml) og Huawei-kanalernes regnestykke-tjek.
# Kør: python tests/test_sikkerhed.py   (kræver: pip install homeassistant)
import asyncio, pathlib, re, sys, tempfile, types
if sys.platform == 'win32':  # Home Assistant importerer to moduler, der kun findes på Linux
    for m in ('fcntl', 'resource'):
        mod = types.ModuleType(m); mod.__getattr__ = lambda n: (lambda *a, **k: (0, 0)); sys.modules[m] = mod
import yaml
from homeassistant import core
from homeassistant.helpers.template import Template

REPO = pathlib.Path(__file__).parent.parent


def find(o, key):
    """Første dict i YAML-træet, der har nøglen."""
    if isinstance(o, dict):
        if key in o:
            return o
        o = list(o.values())
    for v in o if isinstance(o, list) else []:
        if (r := find(v, key)) is not None:
            return r
    return None


V = find(yaml.safe_load((REPO / 'packages/wattlas/emhass_forbindelse.yaml').read_text(encoding='utf-8')), 'ladebudget_w')


async def main():
    hass = core.HomeAssistant(tempfile.mkdtemp())
    sæt = hass.states.async_set

    def anlaeg(*, v_bat=52, lader_a=0, faser=(200, 200, 200), volt=(230, 230, 230), net=None):
        """Et 3-faset hus om natten: 16 A fasegrænse, 11 kW importloft, batteri må lade 200 A (100 A fra nettet)."""
        for e, s in {'binary_sensor.emhass_ui_data_frisk': 'on', 'sensor.emhass_solproduktion_samlet': 0,
                     'sensor.emhass_m_load_w_totalpower': 600, 'sensor.emhass_m_battery_voltage': v_bat,
                     'sensor.emhass_m_battery_output_w_power': -lader_a * v_bat,
                     'sensor.emhass_m_grid_out_total_power': sum(faser) if net is None else net,
                     'input_number.wattlas_maks_ladestroem_a': 200, 'input_number.wattlas_maks_netladestroem_a': 100,
                     'input_number.wattlas_fase_graense_a': 16, 'input_number.wattlas_import_graense_w': 11000,
                     'sensor.wattlas_maks_ladestroem': 200, 'switch.wattlas_netladning': 'on' if lader_a else 'off'}.items():
            sæt(e, str(s))
        sæt('number.wattlas_netladestroem', str(lader_a), {'min': 0, 'max': 200, 'step': 1})
        for i in range(3):
            sæt(f'sensor.emhass_m_external_ct_w_l{i + 1}', str(faser[i]))
            sæt(f'sensor.emhass_m_grid_current_v_l{i + 1}', str(volt[i]))

    def regn(navn, **var):
        return Template(V[navn], hass).async_render(var)

    def ladeamp(p_batt=-5000):
        return regn('ladeamp', ladebudget_w=regn('ladebudget_w', p_batt=p_batt))

    # 1) god plads: der startes blødt med højst +10 A pr. runde
    anlaeg()
    assert regn('fase_ok') is True and regn('ladebudget_w', p_batt=-5000) == 5000, regn('ladebudget_w', p_batt=-5000)
    assert ladeamp() == 10, ladeamp()
    # 2) lader 60 A, fase 1 har kun lidt plads: grænsen giver 64 A – de 60 A holdes (færre skrivninger på vej OP)
    anlaeg(lader_a=60, faser=(3600, 1300, 1300))
    assert ladeamp() == 60, ladeamp()
    # 3) fase 1 kommer 20 W OVER fasegrænsen (16 A × 230 V = 3680 W): strømmen skal ned med det samme, også for 2 A
    anlaeg(lader_a=60, faser=(3700, 1300, 1300))
    assert ladeamp() == 58, f'fasegrænsen holdes ikke: {ladeamp()} A (skulle være 58)'
    # 4) importloftet: huset trækker allerede 10,9 kW i alt – kun 100 W + det, batteriet selv lader, er tilbage
    anlaeg(lader_a=60, faser=(3600, 3600, 3600), net=10900)
    budget = regn('ladebudget_w', p_batt=-5000)
    assert abs(budget - (11000 - 10900 + 60 * 52 / 0.95)) < 1, budget
    # 5) batterispænding uden for 45–58 V: ingen netladning
    anlaeg(v_bat=60)
    assert ladeamp() == 0, ladeamp()
    # 6) en fase med forkert spænding eller manglende måling: fasetjekket siger nej
    anlaeg(volt=(230, 205, 230))
    assert regn('fase_ok') is False
    anlaeg()
    sæt('sensor.emhass_m_external_ct_w_l2', 'unavailable')
    assert regn('fase_ok') is False
    print('faseloft og ladestrøm: OK')

    # Huawei: et omvendt fortegn må aldrig få regnestykket til at gå op (ellers er fasegrænsen sat ud af kraft)
    def balance(kanal, **tal):
        tekst = (REPO / 'styrekanaler' / kanal / 'emhass_maalinger.yaml').read_text(encoding='utf-8')
        linje = re.search(r'\{% set balance_ok = .*? %\}', tekst).group(0)
        return Template(''.join(f'{{% set {k} = {v} %}}' for k, v in tal.items()) + linje + '{{ balance_ok }}', hass).async_render()

    for forventet, tal in [(True, dict(pv=0, b=2500, ac=-2500)), (False, dict(pv=0, b=-2500, ac=-2500)),
                           (True, dict(pv=6000, b=2000, ac=3900)), (False, dict(pv=6000, b=-2000, ac=3900))]:
        assert balance('huawei', **tal) is forventet, ('huawei', tal)
    # EMMA: "Feed in power" (f) er positiv ved køb. De tre første er målt på en rigtig EMMA-A02: køb, netladning og salg
    for forventet, tal in [(True, dict(pv=0, b=0, hus=3559, f=3559, fs=3559)), (True, dict(pv=0, b=9674, hus=1123, f=10797, fs=10797)),
                           (True, dict(pv=0, b=-2805, hus=1584, f=-1221, fs=-1221)), (True, dict(pv=6000, b=2400, hus=600, f=-3000, fs=-3000)),
                           (False, dict(pv=0, b=9674, hus=1123, f=-10797, fs=-10797)), (False, dict(pv=0, b=-9674, hus=1123, f=10797, fs=10797)),
                           (False, dict(pv=0, b=9674, hus=1123, f=10797, fs=-10797))]:
        assert balance('huawei_emma', **tal) is forventet, ('huawei_emma', tal)
    print('Huawei regnestykke-tjek: OK')

    # Growatt: ingen fasetal fra elmåleren – kanalen melder den værste fase (hele huset på én fase). Netladning må aldrig
    # kunne løfte den værste fase over grænsen, og sol ind i batteriet må ikke give mere plads end uden sol.
    def gw(navn, **tal):
        tekst = (REPO / 'styrekanaler/growatt/emhass_maalinger.yaml').read_text(encoding='utf-8')
        linje = re.search(r'\{% set ' + navn + r' = .*? %\}', tekst).group(0)
        return Template(''.join(f'{{% set {k} = {v} %}}' for k, v in tal.items()) + linje + '{{ ' + navn + ' }}', hass).async_render()

    def gw_budget(load, imp, exp=0, lader_w=0, pv=0):
        f = gw('fase', load=load, imp=imp, exp=exp)
        anlaeg(lader_a=lader_w / 52, faser=(f, f, f), net=imp - exp)
        sæt('sensor.emhass_m_load_w_totalpower', str(load)); sæt('sensor.emhass_solproduktion_samlet', str(pv))
        return regn('ladebudget_w', p_batt=-20000)

    # huset trækker 3 kW, alt på L1, intet lader: L1 = 3000 + netladning/3 ≤ 16 A × 230 V → højst 3 × 680 = 2040 W
    assert abs(gw_budget(3000, 3000) - 2040) < 1, gw_budget(3000, 3000)
    # samme hus, men 6 kW sol går i batteriet (intet køb): ikke mere plads end uden sol (kun kernens egne 5 % for ladetab)
    assert gw_budget(1000, 0, pv=7000, lader_w=6000) <= gw_budget(1000, 0) + 6000 * 0.06, (gw_budget(1000, 0, pv=7000, lader_w=6000), gw_budget(1000, 0))
    # under netladning (huset 1 kW, 2 kW fra nettet til batteriet) må budgettet ikke vokse ud over det uden ladning (+ ladningens eget)
    assert gw_budget(1000, 3000, lader_w=2000) <= gw_budget(1000, 1000) + 2000 * 0.06, (gw_budget(1000, 3000, lader_w=2000), gw_budget(1000, 1000))
    # kommando-tjek: Wattlas beder om ladning, men batteriet aflader, eller nettet viser intet køb under netladning
    for forventet, tal in [(True, dict(lader=True, dis=0, fra_net=3000, imp=3500, bedt=3000)),
                           (True, dict(lader=True, dis=0, fra_net=0, imp=0, bedt=3000)),          # solen dækker ladningen
                           (True, dict(lader=False, dis=2500, fra_net=0, imp=0, bedt=0)),
                           (False, dict(lader=True, dis=2500, fra_net=0, imp=0, bedt=3000)),      # aflader i stedet
                           (False, dict(lader=True, dis=0, fra_net=3000, imp=0, bedt=3000)),      # måleren viser intet køb
                           (False, dict(lader=True, dis=0, fra_net=6000, imp=6500, bedt=3000))]:  # lader dobbelt så meget som bedt
        assert gw('balance_ok', **tal) is forventet, ('growatt', tal)
    print('Growatt fasegrænse uden fasetal og kommando-tjek: OK')

    # Growatt-styringens valg (lad/gem/fri) og VPP-procenten: rundes altid NED, så Growatt aldrig beder om mere end kernen
    kanal = yaml.safe_load((REPO / 'styrekanaler/growatt/wattlas_kanal_growatt.yaml').read_text(encoding='utf-8'))
    VAR = next(a for a in kanal['automation'] if a['id'] == 'wattlas_growatt_styring')['variables']

    def styring(*, a=40, loft=10000, soc=50, maal=80, effekt=0, netlad='on', prog='on', styrer='on', pv=0, last=500):
        for e, s in {'sensor.min_growatt_pv_power_total': pv, 'sensor.min_growatt_total_load_power': last, 'input_number.wattlas_growatt_netladestroem': a, 'input_number.wattlas_maks_ladeeffekt_w': loft,
                     'sensor.min_growatt_battery_soc': soc, 'input_boolean.wattlas_growatt_netladning': netlad,
                     'input_boolean.emhass_styring_aktiv': styrer, 'input_boolean.emhass_har_overtaget': styrer}.items():
            sæt(e, str(s))
        for p in range(1, 7):
            sæt(f'input_number.wattlas_growatt_p{p}_soc', str(maal)); sæt(f'input_number.wattlas_growatt_p{p}_power', str(effekt))
            sæt(f'input_boolean.wattlas_growatt_p{p}', prog)
        v = {}
        for k, t in VAR.items():
            v[k] = Template(str(t), hass).async_render(v)
        return v['tilstand'].strip(), v['procent'], v['kw']

    assert styring() == ('lad', 20, 2.0), styring()                          # 40 A × 50 V = 2000 W af 10 kW → 20 %, loft 2,0 kW
    assert styring(a=47) == ('lad', 20, 2.3), styring(a=47)                  # 2350 W → 23,5 % rundes NED til 20 %
    assert styring(a=400) == ('lad', 100, 10.0), styring(a=400)              # aldrig over batteriets maks. ladeeffekt
    assert styring(a=5)[0] == 'gem', styring(a=5)                           # 250 W < 5 %: ingen netladning, batteriet gemmes
    assert styring(soc=80)[0] == 'gem', styring(soc=80)                     # målet er nået: lad ikke mere
    assert styring(netlad='off', soc=90, effekt=3000)[0] == 'fri'            # over programmets SOC og effekt > 0: egen drift
    assert styring(netlad='off', soc=90, effekt=0)[0] == 'gem'               # program med 0 W: gem batteriet
    assert styring(netlad='off', soc=50, effekt=0, pv=3000)[0] == 'fri'      # men med soloverskud: egen drift, så solen kan lade
    assert styring(netlad='off', styrer='off')[0] == 'fri'                   # Wattlas styrer ikke: Growatt kører selv
    assert styring(soc='unavailable')[0] != 'lad'                            # ukendt SOC: aldrig netladning
    print('Growatt styringsvalg og VPP-procent: OK')


    # Hele målelaget (sample-skabelonen) gengives med HA's egen motor, som triggeren gør hvert 10. sekund
    def sample(kanal):
        doc = yaml.safe_load((REPO / 'styrekanaler' / kanal / 'emhass_maalinger.yaml').read_text(encoding='utf-8'))
        var = {}
        for blok in doc['template'][0]['actions']:
            for k, v in blok['variables'].items():
                var[k] = Template(v, hass).async_render({**var, 'trigger': {'platform': 'time_pattern'}}) if isinstance(v, str) else v
        return var['sample']

    def maalekilde(**attr):
        sæt('sensor.emhass_maalekilde', 'x', attr)

    # Growatt-spærren: en kommando-fejl i 2 min spærrer kanalen i 1 time – også når målingerne bagefter ser normale ud
    def growatt(chg, imp):
        for e, s in {'machine_status': 'Normal', 'total_import_power': imp, 'total_export_power': 0, 'total_load_power': 600,
                     'battery_charge_power': chg, 'battery_discharge_power': 0, 'battery_soc': 50, 'pv_power_total': 0,
                     'grid_voltage_l1': 230, 'grid_voltage_l2': 230, 'grid_voltage_l3': 230, 'inverter_temperature': 35}.items():
            sæt(f'sensor.min_growatt_{e}', str(s))
        sæt('input_boolean.wattlas_growatt_vpp_styret', 'on'); sæt('number.min_growatt_vpp_power', '40')
        sæt('input_number.wattlas_growatt_netladestroem', '40')  # bedt om 2000 W
        return sample('growatt')

    maalekilde()
    s = growatt(2000, 2600)
    assert s['growatt_ok'] is True and s['balance_ok'] is True, s
    s = growatt(6000, 6600)                                           # lader 3× det bedte: fejl, men under 2 min endnu
    assert s['balance_ok'] is False and s['growatt_ok'] is True, s
    maalekilde(balance_fejl_siden=s['time'] - 130)                    # fejlen har nu stået i over 2 min
    s = growatt(6000, 6600)
    assert s['growatt_ok'] is False and s['spaerret_til'] > s['time'] + 3500, s
    maalekilde(balance_fejl_siden=0, spaerret_til=s['spaerret_til'])  # kernen har stoppet ladningen – alt ser normalt ud
    s = growatt(0, 600)
    assert s['balance_ok'] is True and s['growatt_ok'] is False, 'spærren skal holde, selv om målingerne er normale igen'
    maalekilde(balance_fejl_siden=0, spaerret_til=s['time'] - 1)      # timen er gået
    assert growatt(0, 600)['growatt_ok'] is True
    print('Growatt-spærre efter kommando-fejl: OK')

    # Deye via ESPHome: husforbrug = belastningsudgang + nettets side; status "normal" → "Normal"; PV = alle strenge, der findes
    for e, s in {'load_totalpower': 1000, 'out_of_grid_total_power': 500, 'total_grid_power': 1500, 'battery_output_power': 0,
                 'battery_capacity': 50, 'battery_voltage': 52, 'running_status': 'normal', 'battery_temperature': 20,
                 'heat_sink_temperature': 30, 'external_ct_l1_power': 500, 'external_ct_l2_power': 500, 'external_ct_l3_power': 500,
                 'grid_voltage_l1': 230, 'grid_voltage_l2': 230, 'grid_voltage_l3': 230, 'pv1_power': 2000, 'pv2_power': 1500}.items():
        sæt(f'sensor.min_inverter_{e}', str(s))
    s = sample('deye_esphome')
    assert s['source'] == 'ESPHome' and s['values']['load_w_totalpower'] == 1500 and s['values']['inverter_status'] == 'Normal', s
    ek = yaml.safe_load((REPO / 'styrekanaler/deye_esphome/wattlas_kanal_deye.yaml').read_text(encoding='utf-8'))
    sol = next(x for blok in ek['template'] for x in blok.get('sensor', []) if x['unique_id'] == 'emhass_solproduktion_samlet')
    assert float(Template(sol['state'], hass).async_render()) == 3500
    sæt('sensor.min_inverter_pv3_power', '700')                       # en 3-MPPT-model tæller den tredje streng med
    assert float(Template(sol['state'], hass).async_render()) == 4200
    print('Deye via ESPHome: husforbrug, status og PV: OK')

    # EMHASS-prisprognosen: timepriser giver begge halvtimer timens pris; kvarterpriser giver halvtimens gennemsnit.
    # (Før krævedes præcis én timepris pr. halvtime – med 96 kvarterpriser faldt hele planen ud.)
    from datetime import datetime, timedelta
    PROG = find(yaml.safe_load((REPO / 'packages/wattlas/emhass_forbindelse.yaml').read_text(encoding='utf-8')), 'prognose')['prognose']
    t0 = (datetime.now().astimezone() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    for k in ('nettarif_lav', 'nettarif_hoej', 'nettarif_spids', 'elafgift', 'tillaeg', 'salg_nettarif', 'salg_gebyr'):
        sæt(f'input_number.wattlas_{k}', '0')
    sæt('input_text.wattlas_solprognose_entitet', 'sensor.sol')
    sæt('sensor.sol', '0', {'forecast': [{'datetime': (t0 + timedelta(minutes=15 * i)).isoformat(), 'watts': 100} for i in range(16)]})

    def koeb(priser):
        sæt('sensor.energi_data_service', '1', {'raw_today': [{'hour': (t0 + timedelta(seconds=s)).isoformat(), 'price': v} for s, v in priser],
                                                'raw_tomorrow': []})
        r = Template(PROG, hass).async_render({'start_ts': t0.timestamp()})
        assert not r['fejl'] and r['intervaller'] == 8, r
        return r['koeb']

    assert koeb([(h * 3600, h + 1.0) for h in range(4)]) == [1, 1, 2, 2, 3, 3, 4, 4]
    assert koeb([(q * 900, float(q)) for q in range(16)]) == [0.5, 2.5, 4.5, 6.5, 8.5, 10.5, 12.5, 14.5]
    print('EMHASS-prisprognose med time- og kvarterpriser: OK')

    # Beskeder: kun notify.… og script.… fra indstillingen udføres – alt andet i feltet ignoreres
    ind = yaml.safe_load((REPO / 'packages/wattlas/wattlas_indstillinger.yaml').read_text(encoding='utf-8'))
    hvis = next(s for s in ind['script']['wattlas_besked']['sequence'] if 'if' in s)['if']
    for felt, ok in [('notify.mobile_app_min_telefon', True), ('script.mine_beskeder', True), ('light.turn_on', False),
                     ('notify.x y', False), ('', False), ('unknown', False)]:
        sæt('input_text.wattlas_besked_handling', felt)
        assert Template(hvis, hass).async_render() is ok, felt
    print('Beskedmodtager fra indstillingen: OK')

    # To Deye i parallel: strøm og effekt deles, så summen er det bedte (også ulige tal); batteri summeres; husforbrug fra balancen
    pk = yaml.safe_load((REPO / 'styrekanaler/deye_parallel/wattlas_kanal_deye.yaml').read_text(encoding='utf-8'))
    netstr = next(x for blok in pk['template'] for x in blok.get('number', []) if x['unique_id'] == 'wattlas_netladestroem')
    assert len(netstr['set_value']) == 1 and 'min_inverter' in str(netstr['set_value'][0]['target']), 'der skrives kun til masteren'
    # det skrevne vises som 2 × masteren med trin 2 × masterens, så kernens skrivning kan ramme tallet (ulige tal findes ikke)
    sæt('number.min_inverter_battery_grid_charging_current', '5', {'step': 1}); sæt('number.min_slave_battery_grid_charging_current', '0')
    assert float(Template(netstr['state'], hass).async_render()) == 10 and float(Template(netstr['step'], hass).async_render()) == 2, netstr
    for bedt in (100, 101, 7, 0):  # Deye giver slaven samme værdi: 2 × masterens må aldrig overstige det bedte
        m = float(Template(str(netstr['set_value'][0]['data']['value']), hass).async_render({'value': bedt}))
        assert 2 * m <= bedt and bedt - 2 * m <= 1, (bedt, m)
    for e, v in {'grid_power': 1500, 'battery_power': 2000, 'pv_power': 0, 'device_state': 'Normal', 'temperature': 40, 'load_power': 900,
                 'battery_state_of_charge': 60, 'battery': 60, 'battery_voltage': 52, 'battery_temperature': 20,
                 'external_ct1_power': 500, 'external_ct2_power': 500, 'external_ct3_power': 500,
                 'grid_l1_voltage': 230, 'grid_l2_voltage': 230, 'grid_l3_voltage': 230}.items():
        sæt(f'sensor.min_inverter_{e}', str(v))
    for e, v in {'battery_power': 1000, 'device_state': 'Normal', 'temperature': 45}.items():
        sæt(f'sensor.min_slave_{e}', str(v))
    sæt('sensor.emhass_solproduktion_samlet', '0')
    s = sample('deye_parallel')
    v = s['values']
    assert s['source'] == 'Solarman' and v['battery_output_w_power'] == 3000 and v['load_w_totalpower'] == 4500, s
    assert v['inverter_temperature'] == 45 and v['inverter_status'] == 'Normal', v
    sæt('sensor.min_slave_device_state', 'Fault')
    assert sample('deye_parallel')['values']['inverter_status'] == 'Slave: Fault', 'en slave i fejl må ikke se normal ud'
    # vagten: følger slaven ikke masteren i over 3 min, er styrekanalen ikke klar
    pm = yaml.safe_load((REPO / 'styrekanaler/deye_parallel/emhass_maalinger.yaml').read_text(encoding='utf-8'))
    ok_tpl = next(b for blok in pm['template'] for b in blok.get('binary_sensor', []) if b['unique_id'] == 'emhass_styrekanal_ok')['state']
    vagt = ok_tpl[:ok_tpl.index('{% set ns=namespace(ok=true) %}')] + '{{ par.ok }}'
    sæt('switch.min_inverter_battery_grid_charging', 'on'); sæt('switch.min_slave_battery_grid_charging', 'on')
    assert Template(vagt, hass).async_render() is True
    sæt('switch.min_slave_battery_grid_charging', 'off')
    assert Template(vagt, hass).async_render() is True, 'lige efter en ændring får slaven 3 min'
    hass.states.async_set('switch.min_inverter_battery_grid_charging', 'on', force_update=True)
    hass.states.get('switch.min_inverter_battery_grid_charging').last_changed = __import__('datetime').datetime.now(__import__('datetime').timezone.utc) - __import__('datetime').timedelta(minutes=5)
    assert Template(vagt, hass).async_render() is False, 'slaven følger ikke masteren – styringen skal stoppe'
    print('Deye i parallel: deling, summer og status: OK')

    # SolaX: elmålerens tal er POSITIVT ved salg (solax_modbus regner husforbrug = inverter − målt) og batteriets positivt ved
    # ladning. Til kernen: net og fasetal positive ved køb, batteri positivt ved afladning – ellers er fasegrænsen sat ud af kraft.
    def solax(maalt, batt_lad, faser, last=900, pv=0, styret='off', valg='Disabled', bedt=0, status='Normal Mode'):
        for e, v in {'grid_feed_in_power': maalt, 'house_load': last, 'battery_power_charge': batt_lad, 'battery_capacity': 55,
                     'pv_power_total': pv, 'run_mode': status, 'battery_temperature': 21, 'inverter_temperature': 40,
                     'grid_voltage_l1': 231, 'grid_voltage_l2': 230, 'grid_voltage_l3': 232}.items():
            sæt(f'sensor.min_solax_{e}', str(v))
        for i, f in enumerate(faser, 1):
            sæt(f'sensor.min_solax_measured_power_l{i}', str(f))
        sæt('input_boolean.wattlas_solax_fjern_styret', styret); sæt('select.min_solax_remotecontrol_power_control_mode_1', valg)
        sæt('number.min_solax_remotecontrol_active_power_mode_1', str(bedt))
        sæt('sensor.emhass_maalekilde', 'x', {})
        return sample('solax')
    s = solax(-4000, 3000, (-2000, -1000, -1000), styret='on', valg='Enabled Power Control', bedt=3000)  # køber 4 kW, lader 3 kW
    v = s['values']
    assert s['source'] == 'SolaX' and v['grid_out_total_power'] == 4000 and v['battery_output_w_power'] == -3000, s
    assert (v['external_ct_w_l1'], v['external_ct_w_l2']) == (2000, 1000) and v['inverter_status'] == 'Normal' and v['battery_voltage'] == 50, v
    v = solax(2500, -1000, (800, 800, 900), pv=4000)['values']                                         # sælger 2,5 kW, aflader 1 kW
    assert v['grid_out_total_power'] == -2500 and v['battery_output_w_power'] == 1000 and v['external_ct_w_l3'] == -900, v
    assert solax(0, 0, (0, 0, 0), status='Idle Mode')['values']['inverter_status'] == 'Normal'           # nat-hvile er normal drift
    assert solax(0, 0, (0, 0, 0), status='Permanent Fault Mode')['values']['inverter_status'] == 'Permanent Fault Mode'
    # kommando-tjek: Wattlas beder om 3 kW fra nettet, men batteriet aflader → målingerne afvises
    assert solax(-1000, -2000, (-300, -300, -400), styret='on', valg='Enabled Power Control', bedt=3000)['balance_ok'] is False
    assert solax(-1000, -2000, (-300, -300, -400))['balance_ok'] is True                                  # uden ladeordre: normal afladning
    # styringen: lad med effekt i hele 100 W og aldrig over loftet; gem kun uden soloverskud; fri, når Wattlas ikke styrer
    kanal = yaml.safe_load((REPO / 'styrekanaler/solax/wattlas_kanal_solax.yaml').read_text(encoding='utf-8'))
    VAR = next(a for a in kanal['automation'] if a['id'] == 'wattlas_solax_styring')['variables']

    def solax_styring(*, a=40, loft=10000, soc=50, maal=80, effekt=0, netlad='on', prog='on', styrer='on', pv=0, last=500):
        for e, s in {'sensor.min_solax_pv_power_total': pv, 'sensor.min_solax_house_load': last, 'input_number.wattlas_solax_netladestroem': a,
                     'input_number.wattlas_maks_ladeeffekt_w': loft, 'sensor.min_solax_battery_capacity': soc, 'input_boolean.wattlas_solax_netladning': netlad,
                     'input_boolean.emhass_styring_aktiv': styrer, 'input_boolean.emhass_har_overtaget': styrer}.items():
            sæt(e, str(s))
        for p in range(1, 7):
            sæt(f'input_number.wattlas_solax_p{p}_soc', str(maal)); sæt(f'input_number.wattlas_solax_p{p}_power', str(effekt))
            sæt(f'input_boolean.wattlas_solax_p{p}', prog)
        v = {}
        for k, t in VAR.items():
            v[k] = Template(str(t), hass).async_render(v)
        return v['tilstand'].strip(), v['watt'], v['valg']

    assert solax_styring() == ('lad', 2000, 'Enabled Power Control'), solax_styring()     # 40 A × 50 V = 2000 W fra nettet
    assert solax_styring(a=47)[1] == 2300, solax_styring(a=47)                            # 2350 W rundes NED til hele 100 W
    assert solax_styring(a=400)[1] == 10000                                                # aldrig over batteriets maks. ladeeffekt
    assert solax_styring(a=900, loft=45000)[1] == 30000                                    # solax_modbus tager højst 30 kW
    assert solax_styring(a=1)[0] == 'gem'                                                  # under 100 W: ingen netladning
    assert solax_styring(soc=80)[0] == 'gem' and solax_styring(soc=80)[2] == 'Enabled No Discharge'
    assert solax_styring(netlad='off', soc=90, effekt=3000)[0] == 'fri'
    assert solax_styring(netlad='off', soc=50, effekt=0, pv=3000)[0] == 'fri'              # soloverskud: egen drift, ikke køb til huset
    assert solax_styring(netlad='off', styrer='off')[0] == 'fri'
    assert solax_styring(soc='unavailable')[0] != 'lad'
    print('SolaX fortegn, kommando-tjek og styringsvalg: OK')

    # Sofar: effekter i kW; fortegnene er ANTAGET (elmåler positiv ved salg, batteri positiv ved ladning). Er de forkerte, skal
    # regnestykke-tjekket (sol + afladning + køb = hus, faserne = total) fange det – ellers ville fasegrænsen være sat ud af kraft.
    def sofar(pcc, batt, faser, last, pv=0, status='Grid-connected'):
        for e, v in {'active_power_pcc_total': pcc, 'active_power_load_sys': last, 'battery_power_total': batt, 'battery_capacity_total': 55,
                     'pv_power_total': pv, 'system_state': status, 'battery_temperature_1': 21, 'inverter_temperature_1': 40,
                     'voltage_l1': 231, 'voltage_l2': 230, 'voltage_l3': 232}.items():
            sæt(f'sensor.min_sofar_{e}', str(v))
        for i, f in enumerate(faser, 1):
            sæt(f'sensor.min_sofar_active_power_pcc_l{i}', str(f))
        sæt('sensor.emhass_maalekilde', 'x', {})
        return sample('sofar')
    s = sofar(-4.0, 3.0, (-2.0, -1.0, -1.0), last=1.0)                       # køber 4 kW, lader 3 kW, huset 1 kW
    v = s['values']
    assert s['source'] == 'Sofar' and s['balance_ok'] and v['grid_out_total_power'] == 4000 and v['battery_output_w_power'] == -3000, s
    assert (v['external_ct_w_l1'], v['external_ct_w_l3']) == (2000, 1000) and v['load_w_totalpower'] == 1000 and v['inverter_status'] == 'Normal', v
    assert sofar(2.0, -1.0, (0.7, 0.7, 0.6), last=3.0, pv=4.0)['balance_ok'] is True     # sælger 2 kW, aflader 1 kW, sol 4 kW
    # forkert fortegn på batteriet (melder +ladning, men aflader): regnestykket passer ikke
    assert sofar(0.0, 2.0, (0.0, 0.0, 0.0), last=2.0)['balance_ok'] is False
    # forkert fortegn på nettet (melder +salg, men køber): regnestykket passer ikke
    assert sofar(3.0, 0.0, (1.0, 1.0, 1.0), last=3.0)['balance_ok'] is False
    # faserne med modsat fortegn af totalen: fanges også
    assert sofar(-3.0, 0.0, (1.0, 1.0, 1.0), last=3.0)['balance_ok'] is False
    assert sofar(0, 0, (0, 0, 0), last=0, status='Permanent fault')['values']['inverter_status'] == 'Permanent fault'
    # styringens tre tal [net-mål, mindste, største batterieffekt]: nettet giver aldrig mere end bedt; gem = ingen afladning
    kanal = yaml.safe_load((REPO / 'styrekanaler/sofar/wattlas_kanal_sofar.yaml').read_text(encoding='utf-8'))
    VAR = next(a for a in kanal['automation'] if a['id'] == 'wattlas_sofar_styring')['variables']

    def sofar_styring(*, a=40, loft=10000, aflad=9000, soc=50, maal=80, effekt=0, netlad='on', prog='on', styrer='on'):
        for e, s in {'input_number.wattlas_sofar_netladestroem': a, 'input_number.wattlas_maks_ladeeffekt_w': loft,
                     'input_number.wattlas_maks_afladeeffekt_w': aflad, 'sensor.min_sofar_battery_capacity_total': soc,
                     'input_boolean.wattlas_sofar_netladning': netlad, 'input_boolean.emhass_styring_aktiv': styrer,
                     'input_boolean.emhass_har_overtaget': styrer}.items():
            sæt(e, str(s))
        for p in range(1, 7):
            sæt(f'input_number.wattlas_sofar_p{p}_soc', str(maal)); sæt(f'input_number.wattlas_sofar_p{p}_power', str(effekt))
            sæt(f'input_boolean.wattlas_sofar_p{p}', prog)
        v = {}
        for k, t in VAR.items():
            v[k] = Template(str(t), hass).async_render(v)
        return v['tilstand'].strip(), list(v['tal'])

    assert sofar_styring() == ('lad', [0, 2000, 10000]), sofar_styring()             # mindst 2000 W ind i batteriet
    assert sofar_styring(a=400)[1][1] == 10000                                         # aldrig over batteriets maks.
    assert sofar_styring(a=900, loft=45000, aflad=45000)[1] == [0, 20000, 20000]        # solax_modbus tager højst 20 kW
    assert sofar_styring(soc=80) == ('gem', [0, 0, 10000])                             # målet nået: ingen afladning
    assert sofar_styring(netlad='off', soc=90, effekt=3000) == ('fri', [0, -9000, 10000])
    assert sofar_styring(netlad='off', styrer='off')[0] == 'fri'
    assert sofar_styring(soc='unavailable')[0] != 'lad'
    print('Sofar fortegn, regnestykke-tjek og styringens tal: OK')

    # Solis: elmåleren (kW) ANTAGES positiv ved salg – regnestykket fanger et forkert fortegn; batteriet læses som to positive
    # W-tal (Battery Input/Output Energy), så dets retning er sikker. Husforbrug = House Load + Bypass Load (nødstrømsudgangen).
    def solis(meter, ind, ud, faser, last, bypass=0, pv=0, styret='off', valg='Battery Hold', bedt=0, status='Normal Running'):
        for e, v in {'meter_active_power_total': meter, 'house_load': last, 'bypass_load': bypass, 'battery_input_energy': ind,
                     'battery_output_energy': ud, 'battery_soc': 55, 'pv_total_power': pv, 'inverter_status': status,
                     'inverter_temperature': 40, 'meter_ac_voltage_l1': 231, 'meter_ac_voltage_l2': 230, 'meter_ac_voltage_l3': 232}.items():
            sæt(f'sensor.min_solis_{e}', str(v))
        for i, f in enumerate(faser, 1):
            sæt(f'sensor.min_solis_meter_active_power_l{i}', str(f))
        sæt('input_boolean.wattlas_solis_fjern_styret', styret); sæt('select.min_solis_dispatch_control_mode', valg)
        sæt('number.min_solis_dispatch_power', str(bedt))
        sæt('sensor.emhass_maalekilde', 'x', {})
        return sample('solis')
    s = solis(-4.0, 3000, 0, (-2.0, -1.0, -1.0), last=800, bypass=200, styret='on', valg='Battery Charge', bedt=3000)  # køber 4 kW, lader 3 kW
    v = s['values']
    assert s['source'] == 'Solis' and s['balance_ok'] and v['grid_out_total_power'] == 4000 and v['battery_output_w_power'] == -3000, s
    assert (v['external_ct_w_l1'], v['external_ct_w_l3']) == (2000, 1000) and v['load_w_totalpower'] == 1000 and v['inverter_status'] == 'Normal', v
    v = solis(2.0, 0, 1000, (0.7, 0.7, 0.6), last=3000, pv=4000)['values']                       # sælger 2 kW, aflader 1 kW
    assert v['grid_out_total_power'] == -2000 and v['battery_output_w_power'] == 1000, v
    assert solis(3.0, 0, 0, (1.0, 1.0, 1.0), last=3000)['balance_ok'] is False                    # forkert fortegn på elmåleren
    assert solis(-3.0, 0, 0, (1.0, 1.0, 1.0), last=3000)['balance_ok'] is False                   # faserne modsat totalen
    assert solis(-3.0, 0, 0, (-1.0, -1.0, -1.0), last=2000, bypass=1000)['balance_ok'] is True    # nødstrømsudgangen tæller med
    # kommando-tjek: Wattlas beder om 3 kW ladning, men batteriet aflader → afvist (også når regnestykket passer)
    assert solis(-1.0, 0, 2000, (-0.3, -0.3, -0.4), last=3000, styret='on', valg='Battery Charge', bedt=3000)['balance_ok'] is False
    assert solis(-1.0, 0, 2000, (-0.3, -0.3, -0.4), last=3000)['balance_ok'] is True                # uden ladeordre: normal afladning
    assert solis(0, 0, 0, (0, 0, 0), last=0, status='Grid Off')['values']['inverter_status'] == 'Grid Off'
    print('Solis fortegn, regnestykke- og kommando-tjek: OK')

    # Growatt SPF via Solar Assistant: net + ved køb, batteri + ved ladning; enfaset på fase 1; forkert fortegn og afviste ordrer fanges
    def spf(net, batt, last, pv=0, styret='off', tilstand='slip', oensket='', output='Utility first', lader='Solar only', mode='Grid mode', v=231):
        for e, x in {'net': net, 'batteri': batt, 'forbrug': last, 'sol': pv, 'soc': 55, 'netspaending': v, 'batterispaending': 52.4,
                     'temperatur': 35, 'tilstand': mode, 'output': output, 'lader': lader}.items():
            sæt(f'sensor.min_spf_{e}', str(x))
        sæt('input_boolean.wattlas_spf_styret', styret); sæt('input_text.wattlas_spf_tilstand_nu', tilstand); sæt('input_text.wattlas_spf_oensket', oensket)
        sæt('sensor.emhass_maalekilde', 'x', {})
        return sample('growatt_spf')
    s = spf(3700, 3000, 600); v = s['values']
    assert s['source'] == 'SPF' and s['balance_ok'] and v['grid_out_total_power'] == 3700 and v['battery_output_w_power'] == -3000, s
    assert (v['external_ct_w_l1'], v['external_ct_w_l2'], v['battery_voltage']) == (3700, 0, '52.4') and v['inverter_status'] == 'Normal', v
    assert spf(0, -1400, 1300)['balance_ok'] and spf(0, 1000, 1900, pv=3000)['balance_ok']              # afladning; sol lader
    assert spf(3700, -3000, 600)['balance_ok'] is False and spf(-3700, 3000, 600)['balance_ok'] is False   # forkert fortegn
    assert spf(600, -1500, 2000, styret='on', tilstand='lad', lader='Solar and utility simultaneously')['balance_ok'] is False  # lader ikke
    sæt('input_number.wattlas_spf_sat_stroem', '20'); sæt('sensor.min_spf_netstroem', '50')
    for alder, ok in ((10, True), (200, False)):                                    # en lavere strøm, der ikke blev taget imod
        n = hass.states.get('input_number.wattlas_spf_sat_stroem')
        hass.states._states[n.entity_id] = type(n)(n.entity_id, n.state, n.attributes, last_changed=n.last_changed - timedelta(seconds=alder))
        assert spf(3200, 2600, 600, styret='on', tilstand='lad', lader='Solar and utility simultaneously')['balance_ok'] is ok, alder
    assert spf(0, 0, 0, mode='Fault mode')['values']['inverter_status'] == 'Fault mode'
    # trækkes kablet, gentager Solar Assistant de sidste tal: de meldes stadig, men ændrer sig ikke – så tæller de ikke som friske
    from homeassistant.util import dt as dt_util
    for sek, kilde in ((60, 'SPF'), (200, 'Ingen')):
        spf(3700, 3000, 600)
        gl = dt_util.utcnow() - timedelta(seconds=sek)
        for s in [s for s in hass.states.async_all('sensor') if s.entity_id.startswith('sensor.min_spf_')]:
            hass.states._states[s.entity_id] = type(s)(s.entity_id, s.state, s.attributes, last_changed=gl, last_updated=gl, last_reported=dt_util.utcnow())
        assert sample('growatt_spf')['source'] == kilde, sek
    print('SPF fortegn, enfaset, regnestykke-tjek og frosne tal: OK')

    # Sonnen: kun husets forbrug pr. fase kendes, og batteriet er enfaset. Kernens fasebudget regner med 3 faser, så kanalen
    # holder selv grænsen: netladestrømmens maks. = den værste fases plads. Hver runde af kernen skal holde sig under den.
    sk = yaml.safe_load((REPO / 'styrekanaler/sonnen/wattlas_kanal_sonnen.yaml').read_text(encoding='utf-8'))
    maks_tpl = next(x for blok in sk['template'] for x in blok.get('number', []) if x['unique_id'] == 'wattlas_netladestroem')['max']
    def sonnen(lader_w, huset=(3000, 500, 500)):
        sæt('sensor.min_sonnen_status', str(sum(huset)), {'Production_W': 0, 'Consumption_W': sum(huset), 'Pac_total_W': -lader_w,
            'GridFeedIn_W': -(sum(huset) + lader_w), 'USOC': 50, 'Ubat': 52, 'OperatingMode': 1, 'SystemStatus': 'OnGrid'})
        for i in range(3):
            sæt(f'sensor.min_sonnen_maaler_w_l{i + 1}', str(huset[i])); sæt(f'sensor.min_sonnen_maaler_v_l{i + 1}', '230')
        return sample('sonnen')
    s = sonnen(2000)
    v = s['values']
    assert s['source'] == 'Sonnen' and v['inverter_status'] == 'Normal' and v['grid_out_total_power'] == 6000 and v['battery_output_w_power'] == -2000, s
    for huset in ((3000, 500, 500), (500, 3500, 200), (3700, 0, 0)):
        lad_a = 0
        for runde in range(8):
            v = sonnen(lad_a * 52, huset)['values']
            anlaeg(lader_a=lad_a, faser=(int(v['external_ct_w_l1']), int(v['external_ct_w_l2']), int(v['external_ct_w_l3'])), net=v['grid_out_total_power'])
            maks = float(Template(maks_tpl, hass).async_render())
            sæt('number.wattlas_netladestroem', str(lad_a), {'min': 0, 'max': maks, 'step': 1})
            lad_a = ladeamp(-9000)
            plads = 16 * 230 - max(huset)
            assert lad_a * 52 / 0.95 <= max(plads, 0) + 1, f'Sonnen runde {runde}, hus {huset}: {lad_a} A = {lad_a * 52 / 0.95:.0f} W fra nettet, plads {plads} W'
        assert lad_a >= 5 or plads < 300, f'Sonnen lader slet ikke ({huset})'
    sæt('sensor.min_sonnen_status', '4000', {**hass.states.get('sensor.min_sonnen_status').attributes, 'SystemStatus': 'OffGrid'})
    assert sample('sonnen')['values']['inverter_status'] == 'OffGrid'
    print('Sonnen: fasegrænse (enfaset), fortegn og status: OK')

    await hass.async_stop(force=True)

asyncio.run(main())
