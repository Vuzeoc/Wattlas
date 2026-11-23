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

    await hass.async_stop(force=True)

asyncio.run(main())
