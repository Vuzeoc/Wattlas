# Selvtjek af integrationens filhåndtering (custom_components/wattlas/installer.py).
# Kør: python tests/test_installer.py   (kræver kun PyYAML)
import pathlib, shutil, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'custom_components' / 'wattlas'))
import installer as I  # kun denne fil – uden at indlæse Home Assistant

# configuration.yaml-former
assert I.tilfoej_packages('default_config:\n').endswith('homeassistant:\n  packages: !include_dir_named packages\n')
assert I.tilfoej_packages('homeassistant:\n  name: Hjem\n  unit_system: metric\nhttp:\n') == \
    'homeassistant:\n  packages: !include_dir_named packages\n  name: Hjem\n  unit_system: metric\nhttp:\n'
assert I.tilfoej_packages('homeassistant:\n    name: Hjem\n') == 'homeassistant:\n    packages: !include_dir_named packages\n    name: Hjem\n'
assert I.tilfoej_packages('homeassistant: !include ha.yaml\n') is None
assert I.tilfoej_packages('homeassistant:\n  packages: !include pk.yaml\n') is None
crlf = I.tilfoej_packages('homeassistant:\r\n  name: Hjem\r\n')
assert crlf == 'homeassistant:\r\n  packages: !include_dir_named packages\r\n  name: Hjem\r\n', repr(crlf)
assert I.tilfoej_packages('homeassistant:\nhttp:\n') == 'homeassistant:\n  packages: !include_dir_named packages\nhttp:\n'


def ny(conf):
    d = pathlib.Path(tempfile.mkdtemp()); (d / 'configuration.yaml').write_text(conf, encoding='utf-8'); return d


# frisk installation uden packages → linjen tilføjes, filer kopieres
d = ny('default_config:\n')
for n in ('20200101-000001', '20200101-000002', '20200101-000003', '20200101-000004', 'mine_egne'):
    (d / f'wattlas_backup_{n}').mkdir()
k = I.installer(str(d), 'deye', 'min_inverter', None, 't1')
assert I.packages_mappe(str(d)) == 'packages'
for p in ['packages/wattlas/emhass_forbindelse.yaml', 'packages/wattlas/wattlas_frontend.yaml', 'packages/wattlas_kanal/wattlas_kanal_deye.yaml',
          'www/wattlas/energi-app-card.js', 'wattlas/dashboards/wattlas.yaml']:
    assert (d / p).exists(), p
assert list(d.glob('configuration.yaml.wattlas_*')), 'kopi af configuration.yaml mangler'
# kun de 3 nyeste backups beholdes; en mappe uden Wattlas' tidsstempel røres aldrig
assert not (d / 'wattlas_backup_20200101-000001').exists() and (d / 'wattlas_backup_20200101-000002').exists()
assert (d / 'wattlas_backup_mine_egne').exists()
# geninstallation (opdatering) med prefix + AC-inverter → backup og ændringer
k2 = I.installer(str(d), 'deye', 'mit_deye', {'navn': 'SMA', 'ac': True, 'effekt': 'sensor.sma_power', 'relae': '', 'prefix': 'sma'}, 't2')
kanal = (d / 'packages/wattlas_kanal/wattlas_kanal_deye.yaml').read_text(encoding='utf-8')
assert 'min_inverter_' not in kanal and "states('sensor.sma_power')" in kanal
assert 'inverter2_prefix: sma_' in (d / 'wattlas/dashboards/wattlas_styring.yaml').read_text(encoding='utf-8')
assert pathlib.Path(k2['backup'], 'packages_wattlas').exists(), 'den nye backup må ikke ryddes væk'
assert I.anden_styring(str(d), 'packages') is None, 'egen installation må ikke tælle som anden styring'
# en løs kopi uden for packages indlæses ikke af HA og må ikke blokere
(d / 'gammelt').mkdir(); shutil.copy(d / 'packages/wattlas/emhass_forbindelse.yaml', d / 'gammelt')
assert I.anden_styring(str(d), 'packages') is None
# tilbagerulning genskaber forrige installation
I.rul_tilbage(k2)
assert 'min_inverter_' in (d / 'packages/wattlas_kanal/wattlas_kanal_deye.yaml').read_text(encoding='utf-8')
# en fremmed styring i packages stopper installationen uden at røre noget
e = ny('homeassistant:\n  packages: !include_dir_named config/packages\n')
(e / 'config/packages').mkdir(parents=True); shutil.copy(d / 'packages/wattlas/emhass_forbindelse.yaml', e / 'config/packages/')
assert I.anden_styring(str(e), 'config/packages') == str(pathlib.Path('config/packages/emhass_forbindelse.yaml'))
try:
    I.installer(str(e), 'deye', 'min_inverter', None, 't'); raise SystemExit('burde være stoppet')
except I.InstallFejl:
    pass
assert not (e / 'config/packages/wattlas').exists()
# Huawei: tre enheder (inverter, batterier, elmåler) – uden batteri/elmåler stoppes installationen uden at efterlade filer
h = ny('default_config:\n')
for forkert in (None, {'min_luna': 'batteries'}, {'min_luna': 'batteries', 'min_hmaaler': 'x"y'}):
    try:
        I.installer(str(h), 'huawei', 'inverter', None, 't', forkert); raise SystemExit(f'burde kræve batteri og elmåler: {forkert}')
    except I.InstallFejl:
        pass
    assert not (h / 'packages/wattlas').exists(), 'fejl må ikke efterlade filer'
try:  # Deye har ingen ekstra enheder
    I.installer(str(h), 'deye', 'min_inverter', None, 't', {'min_luna': 'batteries'}); raise SystemExit('Deye må ikke tage ekstra prefixer')
except I.InstallFejl:
    pass
hx = {'min_luna': 'batteries', 'min_hmaaler': 'power_meter'}
I.installer(str(h), 'huawei', 'inverter', None, 't5', hx)
hk = ''.join(f.read_text(encoding='utf-8') for f in (h / 'packages/wattlas_kanal').glob('*.yaml'))
assert not any(p in hk for p in ('min_huawei_', 'min_luna_', 'min_hmaaler_')), 'en pladsholder blev ikke erstattet'
for e_id in ('sensor.inverter_input_power', 'sensor.batteries_state_of_capacity', 'number.batteries_maximum_discharging_power',
             'sensor.power_meter_phase_a_active_power', 'sensor.power_meter_phase_c_voltage'):
    assert e_id in hk, e_id
alle = I.entiteter_i_kanal('huawei', 'inverter', hx)
assert 'sensor.inverter_input_power' in alle and 'sensor.batteries_charge_discharge_power' in alle and 'sensor.power_meter_active_power' in alle
assert not [x for x in alle if 'min_' in x], 'entitetstjekket skal kende alle tre enheder'
# andre enhedsnavne (fx en omdøbt inverter) erstattes også
I.installer(str(h), 'huawei', 'sun2000_10ktl_m1', None, 't6', {'min_luna': 'luna', 'min_hmaaler': 'maaler'})
hk = ''.join(f.read_text(encoding='utf-8') for f in (h / 'packages/wattlas_kanal').glob('*.yaml'))
assert 'sensor.sun2000_10ktl_m1_input_power' in hk and 'sensor.luna_state_of_capacity' in hk and 'sensor.maaler_active_power' in hk
assert 'sensor.inverter_input_power' not in hk
# Huawei med EMMA: EMMA-enheden (min_emma) + dens måler; den eksterne måler hedder som den indbyggede + "_2"
ex = {'min_luna': 'batteries', 'min_hmaaler': 'emma|_2', 'min_emma': 'emma'}
I.installer(str(h), 'huawei_emma', 'inverter', None, 't7', ex)
hk = ''.join(f.read_text(encoding='utf-8') for f in (h / 'packages/wattlas_kanal').glob('*.yaml'))
assert not any(p in hk for p in ('min_huawei_', 'min_luna_', 'min_hmaaler_', 'min_emma_')), 'en pladsholder blev ikke erstattet'
for e_id in ('sensor.emma_phase_a_active_power_2', 'sensor.emma_phase_c_voltage_2', 'sensor.emma_feed_in_power',
             'sensor.emma_total_supply_from_grid', "device_id('sensor.emma_feed_in_power')", 'select.emma_ess_control_mode',
             'number.batteries_maximum_discharging_power', 'balance_ok'):
    assert e_id in hk, e_id
assert 'sensor.emma_feed_in_power_2' not in hk and 'sensor.power_meter_' not in hk
alle = I.entiteter_i_kanal('huawei_emma', 'inverter', ex)
assert 'sensor.emma_phase_b_active_power_2' in alle and 'sensor.emma_load_power' in alle and not [x for x in alle if 'min_' in x]
for forkert in ({'min_luna': 'b', 'min_hmaaler': 'emma|2', 'min_emma': 'emma'}, {'min_luna': 'b', 'min_hmaaler': 'emma'}):
    try:
        I.installer(str(h), 'huawei_emma', 'inverter', None, 't', forkert); raise SystemExit(f'burde afvises: {forkert}')
    except I.InstallFejl:
        pass
# afinstallation flytter til backup
b = I.afinstaller(str(d))
assert b and not (d / 'packages/wattlas').exists() and (pathlib.Path(b) / 'packages_wattlas').exists()
print('installer: alle tjek OK')
for x in (d, e, h): shutil.rmtree(x, ignore_errors=True)
