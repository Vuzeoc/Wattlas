# Elbil-lader: plads på faserne, beslutningen, vagten og nødladningen – som tal (ingen Home Assistant), plus tusindvis af tilfældige forløb.
# Kør: python tests/test_lader.py
import pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'custom_components/wattlas'))
import lader_logik as L
from lader_logik import Husk, Ind, Vagt, beslut, noedvendig, plads, vagt

V3 = [230, 230, 230]


def ind(nu=0, tilstand='lad_nu', tilsluttet=True, maks_a=16, **k):
    return Ind(nu=nu, tilstand=tilstand, tilsluttet=tilsluttet, maks_a=maks_a, **{'plads_a': 30.0, **k})


def koer(h, sek, **k):
    """Beslutningen hvert 10. sekund i så længe; giver den sidste."""
    r = None
    for t in range(koer.t, koer.t + sek + 1, 10):
        r = beslut(ind(nu=t, **k), h)
    koer.t += sek + 10
    return r


koer.t = 1000


# --- plads ---
assert plads([2300, 2300, 2300], V3, 20, 6900, 99999, 0, 3) == 10  # faserne giver 10 A
assert plads([2300, 0, 0], V3, 20, 2300, 99999, 0, 3) == 10  # værste fase bestemmer
assert plads([9200, 6900, 6900], V3, 20, 23000, 999999, 11040, 3) == -20 + 0 + 16  # egen strøm lægges til igen (11040 W = 16 A)
assert plads([3680, 0, 0], V3, 20, 3680, 99999, 3680, 1) == 20  # enfaset på den værste fase
assert plads([0, 3680, 0], V3, 20, 3680, 99999, 3680, 1) == 20  # på en anden fase: aldrig mere end den rigtige plads
assert plads([-2300, 0, 0], V3, 20, -2300, 99999, 0, 3) == 20  # salg på én fase giver ikke ekstra på de andre
assert plads([0, 0, 0], V3, 99, 10000, 12000, 0, 3) == 2000 / 690  # importloftet
for daarlig in ({'faser_w': [1, 2]}, {'faser_v': [230, 230, 0]}, {'faser_v': [230, 230, 260]}, {'faser_w': [1, 2, float('nan')]}, {'graense_a': 0},
                {'importloft_w': 0}, {'import_w': float('inf')}, {'egen_w': -1}, {'egen_w': None}, {'antal': 2}, {'faser_w': ['1', '2', '3']}, {'graense_a': None}):
    assert plads(**{'faser_w': [0, 0, 0], 'faser_v': V3, 'graense_a': 20, 'import_w': 0, 'importloft_w': 12000, 'egen_w': 0, 'antal': 3, **daarlig}) is None, daarlig
print('Plads på faserne og under importloftet: OK')

# --- tilstande ---
for til, kw, svar in (('fra', {}, None), ('vrøvl', {}, None), ('stop', {}, 0), ('lad_nu', {}, 16), ('klar', {}, 0), ('klar', {'plan': True}, 16), ('klar', {'noed': True}, 16),
                      ('klar', {'plan': True, 'noed': True, 'faerdig': True}, 0), ('sol', {}, 0), ('sol', {'sol_a': 5.9}, 0), ('sol', {'sol_a': 9.7}, 9), ('sol', {'sol_a': 40}, 16),
                      ('sol', {'sol_a': float('nan')}, 0),
                      # "klar til tid": gratis sol uden for planens timer, også når målet er nået – men ikke over solens grænse
                      ('klar', {'sol_a': 9.7}, 9), ('klar', {'sol_a': 5.9}, 0), ('klar', {'faerdig': True, 'sol_a': 9.7}, 9), ('klar', {'sol_a': 9.7, 'sol_faerdig': True}, 0),
                      ('klar', {'plan': True, 'sol_a': 9.7, 'sol_faerdig': True}, 16), ('sol', {'sol_a': 40, 'sol_faerdig': True}, 16), ('lad_nu', {'sol_faerdig': True}, 16)):
    assert beslut(ind(tilstand=til, **kw), Husk())[0] == svar, (til, kw)
assert beslut(ind(tilsluttet=False), Husk()) == (0, 'frakoblet') and beslut(ind(tilsluttet=None), Husk()) == (0, 'status ukendt')
assert beslut(ind(maks_a=5), Husk())[0] == 0 and beslut(ind(maks_a=0, min_a=0), Husk())[0] == 0  # grænserne giver ikke mening
assert beslut(ind(plads_a=None), Husk())[0] == 0 and beslut(ind(plads_a=float('nan')), Husk())[0] == 0 and beslut(ind(over_sikring=True), Husk())[0] == 0
assert beslut(ind(plads_a=6.9), Husk())[0] == 0 and beslut(ind(plads_a=7), Husk())[0] == 7 and beslut(ind(plads_a=6, maks_a=6), Husk())[0] == 6
h = Husk(sat=10); beslut(ind(tilstand='fra'), h)
assert h.sat == 0, 'slippes laderen, glemmes strømmen'
print('Tilstande og start: OK')

# --- ned straks, op langsomt ---
h = Husk()
assert koer(h, 0)[0] == 16
assert koer(h, 0, plads_a=11.8)[0] == 11, 'ned med det samme'
assert koer(h, 50)[0] == 11 and koer(h, 20)[0] == 16, 'op efter et minut med plads'
assert koer(h, 0, plads_a=14.5) == (14, 'faserne')
for _ in range(20):  # pladsen blinker: aldrig op
    assert koer(h, 0, plads_a=30)[0] == 14 and koer(h, 0, plads_a=14)[0] == 14
assert koer(h, 120, plads_a=15.2)[0] == 14, 'ét trin er ikke en skrivning værd, når det ikke er fuld strøm'
# for lidt plads: laveste strøm i et minut, så pause – og hvil før næste start
assert koer(h, 50, plads_a=3)[0] == 6 and koer(h, 10, plads_a=3) == (0, 'ingen plads')
assert koer(h, 30) == (0, 'hviler') and koer(h, 0)[0] == 16, 'hviler i et minut ved lad nu'
h = Husk(sat=16)
assert koer(h, 0, tilstand='klar', plan=True, plads_a=3)[0] == 6 and koer(h, 70, tilstand='klar', plan=True, plads_a=3)[0] == 0
assert koer(h, 260, tilstand='klar', plan=True) == (0, 'hviler') and koer(h, 0, tilstand='klar', plan=True)[0] == 16, 'hviler i fem minutter'
h = Husk(sat=16)
assert koer(h, 50, over_sikring=True)[0] == 6 and koer(h, 10, over_sikring=True) == (0, 'over sikring')
h = Husk(sat=16)
assert koer(h, 0, over_sikring=True, plads_a=None)[0] == 6, 'over sikringen uden målinger: laveste strøm'
h = Husk(sat=16)
assert koer(h, 110, plads_a=None) == (16, 'målinger mangler') and koer(h, 10, plads_a=None)[0] == 0
h = Husk(sat=10)
assert koer(h, 90, plads_a=None)[0] == 10, 'aldrig op uden målinger'
assert koer(h, 0)[0] == 10 and koer(h, 90, plads_a=None)[0] == 10, 'et godt øjeblik nulstiller uret'
for slut in ({'tilstand': 'stop'}, {'tilsluttet': False}, {'tilstand': 'klar', 'faerdig': True}):
    h = Husk(sat=16); assert koer(h, 0, **slut)[0] == 0 and h.sat == 0, slut
print('Ned straks, op langsomt, pause, hvile og manglende målinger: OK')

# --- vagten ---
v = Vagt()
assert vagt(0, 10, 12 * 690, 3, 230, v) is None and v.over is None, '2 A over tåles'
assert [vagt(t, 10, 13 * 690, 3, 230, v) for t in (0, 10, 20, 40, 45)] == [None, None, 'send', 'send', 'nødstop']
assert vagt(50, 10, 10 * 690, 3, 230, v) is None and v.over is None
v = Vagt()
assert [vagt(t, 0, 4100, 3, 230, v) for t in (0, 20, 30, 50, 60, 90)] == [None, None, 'stop', None, 'stop', 'stopper ikke'], 'accepteret er ikke stoppet'
assert vagt(95, 0, 100, 3, 230, v) is None and v.forsoeg == 0
assert vagt(0, 0, None, 3, 230, Vagt()) is None and vagt(0, 10, float('nan'), 3, 230, Vagt()) is None
v = Vagt(); vagt(0, 0, 4100, 3, 230, v); vagt(5, 10, 4100, 3, 230, v)
assert v.stop is None, 'en ny start nulstiller stop-uret'
print('Overstrømsvagt og målt stop: OK')

# --- nødladning ---
assert noedvendig(0, 16, 3, 230, 9) == (True, False) and noedvendig(20, 16, 3, 230, 9) == (False, False)
assert noedvendig(20, 16, 3, 230, 2.4) == (False, True) and noedvendig(10, 16, 3, 230, 2.4) == (False, False)
assert noedvendig(20, 16, 3, 230, -1) == (False, True)
assert abs(L.bil_rest(50, 80, 60, 0) - 20) < 1e-9 and abs(L.bil_rest(50, 80, 60, 5) - 15) < 1e-9 and L.bil_rest(90, 80, 60, 0) == 0 and L.bil_rest(50, 80, 60, 99) == 0
assert abs(L.bil_rest(50, 80, 60, -3) - 20) < 1e-9
print('Færdig, nødladning og bilens procent: OK')

# --- tilfældige forløb: det, der aldrig må ske ---
rnd = random.Random(1)
for forloeb in range(3000):
    maks, mini = rnd.choice([6, 8, 10, 13, 16, 32]), 6
    h, t, sidst, smal, blind, over = Husk(), 0.0, 0, None, None, None
    antal = rnd.choice([1, 3])
    for _ in range(rnd.randint(5, 60)):
        t += rnd.choice([10, 10, 10, 30, 90])
        rum = rnd.choice([None, float('nan'), float('inf'), rnd.uniform(-20, 40), rnd.uniform(5, 18), rnd.uniform(5, 18)])
        i = Ind(nu=t, tilstand=rnd.choice(L.TILSTANDE + ('lad_nu', 'lad_nu', 'vrøvl')), tilsluttet=rnd.choice([True, True, True, False, None]), maks_a=maks, min_a=mini,
                plads_a=rum, over_sikring=rnd.random() < .05, plan=rnd.random() < .5, noed=rnd.random() < .1, faerdig=rnd.random() < .1, sol_a=rnd.uniform(-5, 25))
        god = rum is not None and L.isfinite(rum)
        a, grund = beslut(i, h)
        assert a is None or (isinstance(a, int) and (a == 0 or mini <= a <= maks)), (a, grund, i)
        assert (a or 0) == h.sat or a is None, (a, h)
        blind = None if god else (t if blind is None else blind)
        smal = None if not god or rum >= mini else (t if smal is None else smal)
        if i.tilstand in ('fra', 'vrøvl'):
            assert a is None
        elif i.tilstand == 'stop' or i.tilsluttet is False:
            assert a == 0, i
        elif a:
            if not god:
                assert a <= sidst, ('op uden målinger', i)
            else:
                assert a <= max(rum, mini), ('over pladsen', a, rum)
                assert a <= rum or a == mini, (a, rum)
            assert not (i.over_sikring and a > mini and a >= sidst), 'sikringen er overskredet: kun laveste strøm eller ned'
            assert not (sidst == 0 and not god), 'start uden målinger'
            assert not (blind is not None and t - blind > L.VENT_DATA_S + 90 and sidst == 0)
        sidst = a or 0
print('3000 tilfældige forløb, ingen brudte grænser: OK')
