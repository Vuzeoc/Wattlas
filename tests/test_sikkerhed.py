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
    await hass.async_stop(force=True)

asyncio.run(main())
