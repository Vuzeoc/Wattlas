# Nettariffer fra Energinets åbne liste: beregning, hentning, opdatering og opsætning – uden netværk (listen efterlignes).
# Kør: python tests/test_tariffer.py   (kræver: pip install homeassistant)
import asyncio, json
from datetime import timedelta
from unittest.mock import patch

import aiohttp
import yaml
from test_flow import REPO, TAL, fang_kald, genindlaes, issue, ny_hass, opsaet

A, EN = '5790000705689', '5790000432752'  # Radius (én kode) og Energinet
K = '5790000704842'                       # Konstant (kode + rabat)
TID = [.1] * 6 + [.3] * 11 + [.9] * 4 + [.3] * 3
D = '2031-01-15'
HENTET = 'input_text.wattlas_tarif_hentet'
NAVNE = ('nettarif_lav', 'nettarif_hoej', 'nettarif_spids', 'elafgift')


def række(gln, kode, priser, fra='2031-01-01', til='2031-04-01'):
    p = priser if isinstance(priser, list) else [priser] + [None] * 23  # døgnpris: kun den første er udfyldt
    return {'GLN_Number': gln, 'ChargeTypeCode': kode, 'ValidFrom': fra + 'T00:00:00', 'ValidTo': til and til + 'T00:00:00',
            **{f'Price{i + 1}': v for i, v in enumerate(p)}}


FÆLLES = [række(EN, '40000', .043), række(EN, '41000', .072), række(EN, 'EA-001', .008, til=None)]
LISTE = [række(A, 'DT_C_01', TID), *FÆLLES]


class Svar:
    """Efterligner aiohttp: status og indhold, eller en fejl. Husker kaldene."""

    def __init__(self, data=None, status=200, fejl=None):
        self.data, self.status, self.fejl, self.kald = data, status, fejl, []

    def get(self, url, params, timeout):
        self.kald.append((url, params))
        return self

    async def __aenter__(self):
        if self.fejl:
            raise self.fejl
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return json.loads(self.data) if isinstance(self.data, str) else self.data


async def main():
    hass, _ = await ny_hass('default_config:\n')
    await opsaet(hass, 'deye', 'sensor.deye_pv_power')  # så integrationens modul er indlæst
    from custom_components.wattlas import tariffer as T

    # --- beregning ---
    def afvist(liste, gln=A, dato=D):
        try:
            T.beregn(liste, gln, dato)
        except T.TarifFejl as e:
            assert not e.svar
            return str(e)
        raise AssertionError('skulle være afvist')

    ud = lambda l, gln=A, dato=D: tuple(T.beregn(l, gln, dato)[k] for k in NAVNE)  # noqa: E731,E741
    assert ud(LISTE) == (.1, .3, .9, .123)
    # grænserne: den gamle pris gælder til og med dagen før, den nye fra og med dagen
    skift = [*LISTE, række(A, 'DT_C_01', [v / 2 for v in TID], '2031-04-01', None)]
    skift += [række(EN, k, .01, '2031-04-01') | {'ValidTo': None} for k in ('40000', '41000')]
    assert ud(skift, dato='2031-03-31') == (.1, .3, .9, .123) and ud(skift, dato='2031-04-01') == (.05, .15, .45, .028)
    # andre selskabers priser på samme kode, og Energinets koder hos netselskabet, tæller ikke med
    assert ud([*LISTE, række(K, 'DT_C_01', 4), række(A, '40000', 4), række(EN, 'DT_C_01', 4)]) == (.1, .3, .9, .123)
    # rabat trækkes fra; mangler rækken, eller er den positiv, afvises tallene
    rabat = række(K, 'C_FBTNTR_R', [-v / 10 for v in TID])
    konst = [række(K, 'C_FBTNTR_B', TID), *FÆLLES]
    assert ud([*konst, rabat], K) == (.09, .27, .81, .123) and ud([*konst, række(K, 'C_FBTNTR_R', 0)], K) == (.1, .3, .9, .123)
    assert '0 priser' in afvist(konst, K) and '2 priser' in afvist([*konst, rabat, rabat], K)
    assert 'ikke en rabat' in afvist([*konst, række(K, 'C_FBTNTR_R', .05)], K)
    assert 'urimelig' in afvist([*konst, række(K, 'C_FBTNTR_R', [-.1] * 24)], K)  # rabatten æder hele prisen
    # samme pris hele døgnet (kun første felt udfyldt)
    assert ud([række(A, 'DT_C_01', .4), *FÆLLES]) == (.4, .4, .4, .123)
    # alt det, der ikke må ske i stilhed
    assert '0 priser' in afvist(LISTE[1:]) and '0 priser' in afvist(LISTE, dato='2031-05-01') and '2 priser' in afvist([*LISTE, LISTE[0]])
    for i in (1, 2, 3):
        assert '0 priser' in afvist([r for j, r in enumerate(LISTE) if j != i])  # uden elafgift mv. ville prisen blive for lav
    for k in range(3):  # elafgift og Energinets tariffer skal være ens hele døgnet
        assert 'hele døgnet' in afvist([LISTE[0], *[r | ({'Price9': .5} if j == k else {}) for j, r in enumerate(FÆLLES)]])
    for time in (0, 5, 6, 16, 17, 20, 21, 23):  # én time udenfor sin periode
        assert 'tidsrum' in afvist([række(A, 'DT_C_01', [v + (.01 if h == time else 0) for h, v in enumerate(TID)]), *FÆLLES]), time
    aften = [.1] * 6 + [.3] * 11 + [.9] * 4 + [.2] * 3
    assert 'tidsrum' in afvist([række(A, 'DT_C_01', aften), *FÆLLES])
    for dårlig in (0, -.1, 5.1, float('nan'), float('inf')):
        assert afvist([række(A, 'DT_C_01', [dårlig] * 24), *FÆLLES]), dårlig
        assert 'urimelig' in afvist([LISTE[0], *[række(EN, k, dårlig / 3 if dårlig == dårlig else dårlig) for k in T.FAELLES]]), dårlig
    for gln, s in T.SELSKABER.items():
        assert len(gln) == 13 and gln.isdigit() and gln != EN and len(s) in (2, 3) and all(s), (gln, s)
    print('Beregning af dagens tariffer: OK')

    # --- hentning ---
    rigtig_dag = T.dt_util.now

    def svar(**k):
        s = Svar(**k)
        T.async_get_clientsession = lambda _h: s
        return s

    def idag(tekst):
        T.dt_util.now = lambda *a: rigtig_dag().replace(year=int(tekst[:4]), month=int(tekst[5:7]), day=int(tekst[8:]), hour=10)
    idag(D)
    s = svar(data={'records': LISTE})
    assert (await T.hent(hass, A))['nettarif_spids'] == .9
    filter_ = json.loads(s.kald[0][1]['filter'])
    assert filter_ == {'GLN_Number': [A, EN], 'ChargeType': ['D03'], 'ChargeTypeCode': ['DT_C_01', '40000', '41000', 'EA-001']}, filter_
    p = s.kald[0][1]
    assert set(p['columns'].split(',')) == set(LISTE[0]) and p['sort'] == 'ValidFrom DESC' and int(p['limit']) >= 500, p
    assert len(s.kald) == 1 and s.kald[0][0].startswith('https://api.energidataservice.dk/')

    async def fejler(forbigående, gln=A, **k):
        svar(**k)
        try:
            await T.hent(hass, gln)
        except T.TarifFejl as e:
            assert e.svar is forbigående, (k, e)
            return
        raise AssertionError(k)
    for k in ({'status': 429}, {'status': 500}, {'fejl': aiohttp.ClientError()}, {'fejl': TimeoutError()}, {'data': '<html>'}):
        await fejler(True, **k)
    for data in ({}, [], None, {'records': None}, {'records': 'x'}, {'records': [{}]}, {'records': []},
                 {'records': [række(A, 'DT_C_01', ['x'] * 24), *FÆLLES]}, {'records': [LISTE[0] | {'ValidFrom': None}]}):
        await fejler(False, data=data)
    await fejler(False, gln='ukendt', data={'records': LISTE})
    print('Hentning afviser alt, der ikke ser rigtigt ud: OK')

    # --- daglig opdatering ---
    kald = fang_kald(hass)
    beskeder = []

    async def besked(call):
        beskeder.append(call.data['message'])
    hass.services.async_register('script', 'wattlas_besked', besked)
    entry = hass.config_entries.async_entries('wattlas')[0]
    sat = lambda: {k[2].removeprefix('input_number.wattlas_'): k[3] for k in kald if k[0] == 'input_number'}  # noqa: E731

    def nu(*v, hentet=''):
        for n, x in zip(NAVNE, v, strict=True):
            hass.states.async_set(f'input_number.wattlas_{n}', str(x))
        hass.states.async_set(HENTET, hentet)

    async def kør(ny_dag=True):
        kald.clear(); beskeder.clear()
        if ny_dag:
            hass.data.pop(T.SIDST, None)
        await T.opdater(hass, entry)
        await hass.async_block_till_done()
        return sat()
    from custom_components.wattlas.const import GENSTART
    hass.data.pop(GENSTART, None)  # som efter genstarten

    def vælg(gln):
        hass.config_entries.async_update_entry(entry, data={**{k: v for k, v in entry.data.items() if k != 'netselskab'}, **({'netselskab': gln} if gln else {})})
    # slået fra: intet kald
    s = svar(data={'records': LISTE}); nu(.2, .3, .9, .123)
    assert await kør() == {} and not s.kald and not issue(hass, 'tarif_fejl')
    # slået til: kun det, der er ændret, skrives; tidspunktet huskes; besked om ændringen
    vælg(A)
    assert await kør() == {'nettarif_lav': .1} and len(s.kald) == 1
    assert [k for k in kald if k[2] == HENTET and k[3].startswith(D)], kald
    assert len(beskeder) == 1 and 'kl. 0–6: 0,1000' in beskeder[0] and 'kl. 0–6: 0,2000' in beskeder[0], beskeder
    # kun ét vellykket kald om dagen – men igen dagen efter, og ingen besked, når intet er ændret
    nu(.1, .3, .9, .123)
    assert await kør(ny_dag=False) == {} and len(s.kald) == 1
    idag('2031-01-16')
    assert await kør(ny_dag=False) == {} and len(s.kald) == 2 and not beskeder
    # et andet selskab samme dag hentes straks
    hass.data[T.SIDST] = (K, '2031-01-16')
    assert await kør(ny_dag=False) == {} and len(s.kald) == 3
    # pakkerne er ikke indlæst: rør intet
    for tilstand in (None, 'unavailable'):
        nu(.2, .3, .9, .123); hass.states.async_remove('input_number.wattlas_elafgift')
        if tilstand:
            hass.states.async_set('input_number.wattlas_elafgift', tilstand)
        assert await kør() == {} and len(s.kald) == 3
    # ældre pakker uden tidspunktet (en opdatering, der blev rullet tilbage, eller mangler genstart): tallene hentes alligevel
    nu(.2, .3, .9, .123); hass.states.async_remove(HENTET); hass.data[GENSTART] = True
    assert await kør() == {'nettarif_lav': .1} and not [k for k in kald if k[2] == HENTET]
    hass.data.pop(GENSTART); svar(status=500)
    assert await kør() == {} and issue(hass, 'tarif_fejl')
    ir_slet(hass)
    # nul i hjælperne (ny installation): ingen besked om "nye" tariffer
    svar(data={'records': LISTE}); nu(0, 0, 0, 0)
    assert await kør() == {'nettarif_lav': .1, 'nettarif_hoej': .3, 'nettarif_spids': .9, 'elafgift': .123} and not beskeder
    # listen svarer ikke: de gamle tal bliver stående; først efter tre døgn kommer en reparation – og der prøves igen næste time
    frisk = (T.dt_util.now() - timedelta(days=2, hours=23)).isoformat()
    gammel = (T.dt_util.now() - timedelta(days=3, hours=1)).isoformat()
    s = svar(status=429)
    nu(.2, .3, .9, .123, hentet=frisk)
    assert await kør() == {} and not issue(hass, 'tarif_fejl') and not beskeder
    assert await kør(ny_dag=False) == {} and len(s.kald) == 2
    for h in (gammel, '', 'noget andet', '2031-01-16 09:00:00'):  # også uden tidszone
        ir_slet(hass)
        nu(.2, .3, .9, .123, hentet=h)
        assert await kør() == {} and issue(hass, 'tarif_fejl'), h
    # tal, der ikke kan bruges, siges med det samme
    ir_slet(hass)
    nu(.2, .3, .9, .123, hentet=frisk); svar(data={'records': [række(A, 'DT_C_01', aften), *FÆLLES]})
    assert await kør() == {} and 'tidsrum' in issue(hass, 'tarif_fejl').translation_placeholders['fejl']
    assert not issue(hass, 'tarif_fejl').is_persistent, 'gemte reparationer kommer med i HAs diagnostik med deres pladsholdere'
    # … og forsvinder, når det virker igen
    svar(data={'records': LISTE})
    assert await kør() == {'nettarif_lav': .1} and not issue(hass, 'tarif_fejl')
    # netselskabet skiftes i Konfigurer, mens der hentes: det gamle svar bruges ikke
    for k in ({'data': {'records': LISTE}}, {'data': {}}):
        s = svar(**k); nu(.2, .3, .9, .123, hentet=frisk); vælg(A)
        rigtig = s.json

        async def skift_imens(content_type=None):
            vælg(K)
            return await rigtig()
        s.json = skift_imens
        assert await kør() == {} and not issue(hass, 'tarif_fejl')
    # integrationen fjernes, mens der hentes: intet skrives, og der efterlades ingen reparation
    vælg(A); nu(.2, .3, .9, .123, hentet='')
    for k in ({'data': {'records': LISTE}}, {'data': {}}):
        svar(**k)
        with patch.object(hass.config_entries, 'async_get_entry', return_value=None):
            assert await kør() == {} and not issue(hass, 'tarif_fejl')
    # integrationen kører det selv ved opstart og hver time
    vælg(A); s = svar(data={'records': LISTE}); nu(.2, .3, .9, .123); kald.clear(); hass.data.pop(T.SIDST, None)
    await genindlaes(hass)
    entry = hass.config_entries.async_entries('wattlas')[0]
    await hass.async_block_till_done()
    assert len(s.kald) == 1 and sat().get('nettarif_lav') == .1, (s.kald, kald)
    from custom_components import wattlas as W
    planlagt = []
    with patch.object(W, 'async_track_time_interval', side_effect=lambda h, f, i: planlagt.append((f, i)) or (lambda: None)):
        await genindlaes(hass)
    entry = hass.config_entries.async_entries('wattlas')[0]
    idag('2031-01-17')
    for f, i in planlagt:
        if i == timedelta(hours=1):
            await f(None)
    assert len(s.kald) == 2, 'skal prøves hver time'
    idag('2031-01-16')
    print('Daglig opdatering: OK')

    # --- Konfigurer ---
    om = hass.config_entries.options

    async def menu(trin):
        r = await om.async_init(entry.entry_id)
        return await om.async_configure(r['flow_id'], {'next_step_id': trin})
    data = lambda: hass.config_entries.async_entries('wattlas')[0].data  # noqa: E731
    felter = lambda r: {str(k) for k in r['data_schema'].schema}  # noqa: E731
    r = await menu('priser')
    assert not felter(r) & set(NAVNE) and 'tillaeg' in felter(r) and 'Radius' in r['description_placeholders']['tariffer'] and '0,3000' in r['description_placeholders']['tariffer'], r
    r = await om.async_configure(r['flow_id'], {'tillaeg': .05, 'slid': .25})  # gemmes uden de fire felter
    assert r['type'] == 'create_entry' and data()['netselskab'] == A
    # listen svarer ikke: intet gemmes, grunden vises, og man kan prøve igen
    vælg(None); nu(.2, .3, .9, .123); svar(status=429); kald.clear()
    r = await menu('netselskab')
    assert next(k for k in r['data_schema'].schema).default() == 'manuel'
    r = await om.async_configure(r['flow_id'], {'netselskab': A})
    assert r['errors'] == {'base': 'tarif'} and '429' in r['description_placeholders']['grund'] and not kald and 'netselskab' not in data()
    svar(data={'records': LISTE})
    r = await om.async_configure(r['flow_id'], {'netselskab': A})
    assert r['step_id'] == 'netselskab_vis' and '0,2000' in r['description_placeholders']['nu'] and '0,1000' in r['description_placeholders']['ny'], r
    assert not kald and 'netselskab' not in data(), 'intet må gemmes, før tallene er set'
    hass.data[T.SIDST] = (A, '2031-01-16')  # timejobbet nåede at hente, mens vinduet stod åbent
    T.ir.async_create_issue(hass, 'wattlas', 'tarif_fejl', is_fixable=False, severity=T.ir.IssueSeverity.WARNING, translation_key='tarif_fejl')
    kapacitet = data()['tal']['batteri_kwh']
    rigtig_anvend = T.anvend

    async def anvend_og_ny_version(h, tal):  # opdateringen kan skrive opsætningen imens
        ud_ = await rigtig_anvend(h, tal)
        hass.config_entries.async_update_entry(entry, data={**entry.data, 'version': '9.9.9'})
        return ud_
    T.anvend = anvend_og_ny_version
    r = await om.async_configure(r['flow_id'], {})
    T.anvend = rigtig_anvend
    assert r['type'] == 'create_entry' and data()['netselskab'] == A and sat() == {'nettarif_lav': .1} and data()['tal']['nettarif_lav'] == .1
    assert data()['tal']['batteri_kwh'] == kapacitet and data()['version'] == '9.9.9' and not issue(hass, 'tarif_fejl')
    s = svar(data={'records': LISTE}); await T.opdater(hass, hass.config_entries.async_entries('wattlas')[0])
    assert len(s.kald) == 1, 'et gammelt vindue må ikke låse gårsdagens tal fast resten af dagen'
    r = await menu('netselskab')
    assert next(k for k in r['data_schema'].schema).default() == A
    # tilbage til egne tal: felterne kommer igen, og reparationen forsvinder
    svar(status=500); hass.data.pop(T.SIDST, None); hass.states.async_set(HENTET, '')
    await T.opdater(hass, hass.config_entries.async_entries('wattlas')[0])
    assert issue(hass, 'tarif_fejl')
    r = await menu('netselskab')
    kald.clear()
    r = await om.async_configure(r['flow_id'], {'netselskab': 'manuel'})
    assert r['type'] == 'create_entry' and 'netselskab' not in data() and not issue(hass, 'tarif_fejl')
    assert ('input_text', 'set_value', HENTET, '') in kald, 'ellers tier påmindelsen i tre døgn'
    assert set(NAVNE) <= felter(await menu('priser'))
    # diagnostik: hverken selskab eller de præcise tal (de kan slås op)
    from custom_components.wattlas import diagnostics
    vælg(A); nu(.106175, .318524, .955573, .123)
    hass.config_entries.async_update_entry(entry, data={**entry.data, 'tal': {**entry.data['tal'], 'nettarif_spids': .955573}})
    d = json.dumps(await diagnostics.async_get_config_entry_diagnostics(hass, entry))
    assert '"tariffer_hentes": true' in d and '"input_number.wattlas_nettarif_spids": {"sat": true}' in d and 'batteri_kwh' in d, d[:900]
    assert not any(x in d for x in (A, 'Radius', 'DT_C_01', '0.955573', '0.106175', '0.318524')), d[:900]
    # fjernelse: reparationen forsvinder
    svar(status=500); hass.data.pop(T.SIDST, None); hass.states.async_set(HENTET, ''); await T.opdater(hass, entry)
    assert issue(hass, 'tarif_fejl')
    await hass.config_entries.async_remove(entry.entry_id)
    assert not issue(hass, 'tarif_fejl')
    await hass.async_stop(force=True)
    print('Konfigurer → Netselskab: OK')

    # --- opsætning ---
    hass, _ = await ny_hass('default_config:\n')
    svar(data={'records': LISTE}); idag(D)
    hass.states.async_set('sensor.deye_pv_power', '0')
    fm = hass.config_entries.flow
    r = await fm.async_init('wattlas', context={'source': 'user'})
    for svar_ in ({'kanal': 'deye'}, {'inverter': 'sensor.deye_pv_power', 'inverter2': False}, {'forstaaet': True},
                  {'emhass_adresse': 'http://emhass:5000', 'emhass_noegle': 'hemmelig123', 'solprognose': 'sensor.helios_power_now', 'vejr': 'weather.test'},
                  TAL['batteri'], TAL['elnet']):
        r = await fm.async_configure(r['flow_id'], svar_)
    assert r['step_id'] == 'netselskab', r
    fejl = await fm.async_configure(r['flow_id'], {'netselskab': K})  # findes ikke på listen i dag
    assert fejl['errors'] == {'base': 'tarif'} and '0 priser' in fejl['description_placeholders']['grund'], fejl
    r = await fm.async_configure(r['flow_id'], {'netselskab': A})
    assert r['step_id'] == 'priser' and not felter(r) & set(NAVNE) and '0,9000' in r['description_placeholders']['tariffer'], r
    r = await fm.async_configure(r['flow_id'], {})
    d = r['result'].data
    assert d['netselskab'] == A and {k: d['tal'][k] for k in NAVNE} == {'nettarif_lav': .1, 'nettarif_hoej': .3, 'nettarif_spids': .9, 'elafgift': .123}, d['tal']
    await hass.async_stop(force=True)
    T.dt_util.now = rigtig_dag
    print('Opsætning med netselskab: OK')

    # --- påmindelsen om at taste nye tariffer: kun, når de ikke hentes selv ---
    from homeassistant.helpers.template import Template
    ind = yaml.safe_load((REPO / 'packages/wattlas/wattlas_indstillinger.yaml').read_text(encoding='utf-8'))
    skabelon = next(a for a in ind['automation'] if a['id'] == 'wattlas_tarif_paamindelse')['conditions'][0]['value_template']
    for dag, hentet, ok in (('2031-01-01', '', True), ('2031-04-01', 'unknown', True), ('2031-10-01', '2031-09-20T08:00:00+02:00', True),
                            ('2031-10-01', '2031-09-30T08:00:00+02:00', False), ('2031-01-02', '', False), ('2031-02-01', '', False)):
        t = skabelon.replace('now()', f"as_datetime('{dag}T09:00:00+01:00')")
        hass.states.async_set(HENTET, hentet)
        assert Template(t, hass).async_render() is ok, (dag, hentet)
    print('Påmindelsen tier, når tarifferne hentes selv: OK')


def ir_slet(hass):
    from homeassistant.helpers import issue_registry as ir
    ir.async_delete_issue(hass, 'wattlas', 'tarif_fejl')


asyncio.run(main())
