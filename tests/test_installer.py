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
# afinstallation flytter til backup
b = I.afinstaller(str(d))
assert b and not (d / 'packages/wattlas').exists() and (pathlib.Path(b) / 'packages_wattlas').exists()
print('installer: alle tjek OK')
for x in (d, e): shutil.rmtree(x, ignore_errors=True)
