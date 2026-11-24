# Selvtjek af integrationens filhåndtering (custom_components/wattlas/installer.py).
# Kør: python tests/test_installer.py   (kræver kun PyYAML)
import pathlib, shutil, sys, tempfile, time
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
# Growatt (solax_modbus): én enhed – forbindelsens navn er prefixet; ingen ekstra enheder
g = ny('default_config:\n')
try:
    I.installer(str(g), 'growatt', 'growatt', None, 't', {'min_luna': 'x'}); raise SystemExit('Growatt må ikke tage ekstra prefixer')
except I.InstallFejl:
    pass
I.installer(str(g), 'growatt', 'mod_10k', None, 't8')
gk = ''.join(f.read_text(encoding='utf-8') for f in (g / 'packages/wattlas_kanal').glob('*.yaml'))
assert 'min_growatt' not in gk, 'en pladsholder blev ikke erstattet'
for e_id in ('sensor.mod_10k_battery_soc', 'sensor.mod_10k_total_import_power', 'number.mod_10k_vpp_power', 'number.mod_10k_vpp_time',
             'select.mod_10k_vpp_remote_control', 'number.mod_10k_vpp_ac_charge_max_power_2', 'sensor.mod_10k_today_s_battery_input_energy'):
    assert e_id in gk, e_id
alle = I.entiteter_i_kanal('growatt', 'mod_10k')
assert 'select.mod_10k_vpp_status' in alle and 'sensor.mod_10k_grid_voltage_l3' in alle and not [x for x in alle if 'min_' in x]
shutil.rmtree(g, ignore_errors=True)
# Deye via ESPHome (klatremis): prefix = ESPHome-konfigurationens device_type
x = ny('default_config:\n')
I.installer(str(x), 'deye_esphome', 'sun12k', None, 't10')
xk = ''.join(f.read_text(encoding='utf-8') for f in (x / 'packages/wattlas_kanal').glob('*.yaml'))
assert 'min_inverter' not in xk and 'select.' not in xk.replace('select.select_option', ''), 'pladsholder eller valgmenu tilbage'
for e_id in ('switch.sun12k_time_point_1_charge_enable', 'number.sun12k_maximum_battery_grid_charge_current', 'switch.sun12k_time_of_use',
             'sensor.sun12k_battery_capacity', 'sensor.sun12k_external_ct_l3_power', 'sensor.sun12k_pv2_power', 'switch.sun12k_solar_sell'):
    assert e_id in xk, e_id
alle = I.entiteter_i_kanal('deye_esphome', 'sun12k')
assert 'sensor.sun12k_total_charge_of_the_battery' in alle and not [e for e in alle if 'microinverter' in e or 'min_' in e], alle
shutil.rmtree(x, ignore_errors=True)
# To Deye i parallel: masteren er hoved-prefixet, slaven en ekstra enhed – alle skrivninger går til begge
pl = ny('default_config:\n')
try:
    I.installer(str(pl), 'deye_parallel', 'deye_m', None, 't'); raise SystemExit('parallel kræver en slave')
except I.InstallFejl:
    pass
I.installer(str(pl), 'deye_parallel', 'deye_m', None, 't11', {'min_slave': 'deye_s'})
pk = ''.join(f.read_text(encoding='utf-8') for f in (pl / 'packages/wattlas_kanal').glob('*.yaml'))
assert 'min_slave' not in pk and 'min_inverter' not in pk, 'en pladsholder blev ikke erstattet'
for e_id in ('number.deye_m_battery_grid_charging_current', 'number.deye_s_battery_grid_charging_current', 'select.deye_s_program_3_charging',
             'switch.deye_s_export_surplus', 'sensor.deye_s_battery_power', 'sensor.deye_s_pv_power'):
    assert e_id in pk, e_id
alle = I.entiteter_i_kanal('deye_parallel', 'deye_m', {'min_slave': 'deye_s'})
assert 'number.deye_s_program_6_power' in alle and 'binary_sensor.deye_s_connection' in alle and not [x for x in alle if 'min_' in x]
shutil.rmtree(pl, ignore_errors=True)
# Sonnen: adresse og token sættes ind i kanalfilerne; mangler de eller har farlige tegn (YAML), installeres der ikke
pl = ny('default_config:\n')
for sd in (None, {'host': 'http://10.0.0.5', 'token': ''}, {'host': 'http://10.0.0.5"', 'token': 'abcdefgh12'},
          {'host': 'http://10.0.0.5', 'token': 'abc defgh"12'}):
    try:
        I.installer(str(pl), 'sonnen', 'min_sonnen', None, 't', None, sd); raise SystemExit(f'Sonnen uden gyldig adresse/token: {sd}')
    except I.InstallFejl:
        pass
I.installer(str(pl), 'sonnen', 'min_sonnen', None, 't12', None, {'host': 'http://10.0.0.5:8080', 'token': 'Ab-12_x.y~z+/='})
pk = ''.join(f.read_text(encoding='utf-8') for f in (pl / 'packages/wattlas_kanal').glob('*.yaml'))
assert '__SONNEN_' not in pk and 'http://10.0.0.5:8080/api/v2/status' in pk and 'Auth-Token: "Ab-12_x.y~z+/="' in pk, 'Sonnen-pladsholder ikke erstattet'
# tokenet må ikke blive liggende i backup-mapperne: hverken efter en opdatering (når den er godkendt) eller efter fjernelse.
# Før godkendelsen skal det stå der endnu, så en tilbagerulning giver en virkende kanal.
def i_backup(mappe):
    return ''.join(f.read_text(encoding='utf-8') for f in pathlib.Path(mappe).rglob('*.yaml'))
time.sleep(1.1)  # backup-mappens navn har sekund-opløsning
kv = I.installer(str(pl), 'sonnen', 'min_sonnen', None, 't13', None, {'host': 'http://10.0.0.5:8080', 'token': 'Ab-12_x.y~z+/='})
assert 'Ab-12_x.y~z+/=' in i_backup(kv['backup']), 'før godkendelsen skal backuppen kunne lægges tilbage uændret'
I.skjul_token(kv['backup'])
assert 'Ab-12_x.y~z+/=' not in i_backup(kv['backup']) and 'Auth-Token: "__SONNEN_TOKEN__"' in i_backup(kv['backup'])
assert 'Auth-Token: "Ab-12_x.y~z+/="' in ''.join(f.read_text(encoding='utf-8') for f in (pl / 'packages/wattlas_kanal').glob('*.yaml'))
time.sleep(1.1)
assert 'Ab-12_x.y~z+/=' not in i_backup(I.afinstaller(str(pl))), 'tokenet blev liggende efter fjernelsen'
shutil.rmtree(pl, ignore_errors=True)
# to installationer i samme sekund får hver sin backup-mappe (ellers lægger en tilbagerulning de forkerte filer tilbage)
pl = ny('default_config:\n')
k1 =I.installer(str(pl), 'deye', 'min_inverter', None, 'a1'); k2 = I.installer(str(pl), 'deye', 'min_inverter', None, 'a2')
k3 = I.installer(str(pl), 'deye', 'min_inverter', None, 'a3')
assert k2['backup'] != k3['backup'], (k2['backup'], k3['backup'])  # k1 havde intet at flytte, så den lavede ingen mappe
I.rul_tilbage(k3)
assert '?v=a2' in (pl / 'packages/wattlas/wattlas_frontend.yaml').read_text(encoding='utf-8'), 'tilbagerulningen lagde ikke den forrige version tilbage'
shutil.rmtree(pl, ignore_errors=True)
# afinstallation flytter til backup
b = I.afinstaller(str(d))
assert b and not (d / 'packages/wattlas').exists() and (pathlib.Path(b) / 'packages_wattlas').exists()
print('installer: alle tjek OK')
for x in (d, e, h): shutil.rmtree(x, ignore_errors=True)
