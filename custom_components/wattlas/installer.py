"""Filhåndtering for Wattlas: kopierer pakker, kort og dashboards ind i /config.

Alt her er almindelig, blokerende Python og køres i HA's executor. Samme trin som install.sh.
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

PAYLOAD = Path(__file__).parent / "payload"
KANALER = {"deye": ("deye_solarman", "min_inverter"), "sunmate": ("sunmate", "min_sunmate")}
PKG_RE = re.compile(r"^[ \t]*packages:[ \t]*!include_dir_(?:merge_)?named[ \t]+[\"']?([^\"'#\s]+)", re.M)
PACKAGES_LINJE = "packages: !include_dir_named packages"


class InstallFejl(Exception):
    """Installationen kunne ikke gennemføres; teksten vises for brugeren."""


def packages_mappe(config_dir: str) -> str | None:
    """Relativ sti til packages-mappen, hvis configuration.yaml allerede bruger packages."""
    tekst = (Path(config_dir) / "configuration.yaml").read_text(encoding="utf-8")
    m = PKG_RE.search(tekst)
    return m.group(1).strip("/") if m else None


def tilfoej_packages(tekst: str) -> str | None:
    """Ny configuration.yaml med packages-linjen, eller None hvis filens form er usikker at rette i."""
    nl = "\r\n" if "\r\n" in tekst else "\n"
    linjer = tekst.split(nl)
    top = [i for i, l in enumerate(linjer) if re.match(r"homeassistant:", l)]
    if not top:  # ingen homeassistant:-nøgle – tilføj en ny blok nederst
        return tekst.rstrip(nl) + nl + nl + "homeassistant:" + nl + "  " + PACKAGES_LINJE + nl
    if len(top) > 1 or linjer[top[0]].split("#")[0].strip() != "homeassistant:":
        return None  # flere nøgler eller fx "homeassistant: !include ..." – lad brugeren gøre det
    i = top[0]
    indryk = "  "
    for l in linjer[i + 1:]:
        if not l.strip() or l.lstrip().startswith("#"):
            continue
        m = re.match(r"([ \t]+)\S", l)
        if not m:
            break  # næste top-nøgle: blokken er tom
        if l.strip().startswith("packages:"):
            return None  # packages i en anden form end !include_dir_named
        indryk = m.group(1)
        break
    linjer.insert(i + 1, indryk + PACKAGES_LINJE)
    return nl.join(linjer)


def anden_styring(config_dir: str, pkg_rel: str | None) -> str | None:
    """Sti til en anden EMHASS/Wattlas-styring, som ikke er Wattlas' egen – to styringer på én inverter er farligt."""
    cfg = Path(config_dir)
    egen = (cfg / pkg_rel / "wattlas").resolve() if pkg_rel else None
    for p in cfg.rglob("emhass_forbindelse.yaml"):
        dele = p.relative_to(cfg).parts
        if dele and (dele[0].startswith("wattlas_backup_") or dele[0] in ("custom_components", ".storage", "deps")):
            continue
        if egen and p.resolve().parent == egen:
            continue
        return str(p.relative_to(cfg))
    return None


def entiteter_i_kanal(kanal: str, prefix: str) -> list[str]:
    """Alle inverter-entiteter, som styrekanalen (efter prefix) læser eller skriver."""
    mappe, std = KANALER[kanal]
    ids: set[str] = set()
    for f in (PAYLOAD / "styrekanaler" / mappe).glob("*.yaml"):
        for m in re.finditer(rf"\b(sensor|binary_sensor|switch|number|select|button)\.{std}_([a-z0-9_]+)", f.read_text(encoding="utf-8")):
            ids.add(f"{m.group(1)}.{prefix}_{m.group(2)}")
    return sorted(ids)


def _flyt(src: Path, backup: Path, navn: str, flyttet: list) -> None:
    if src.exists():
        backup.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(backup / navn))
        flyttet.append((backup / navn, src))


def installer(config_dir: str, kanal: str, prefix: str, inv2: dict | None, version: str) -> dict:
    """Kopierer alt på plads. Returnerer en kvittering, som rul_tilbage() kan bruge."""
    cfg = Path(config_dir)
    conf = cfg / "configuration.yaml"
    gammel_conf = conf.read_text(encoding="utf-8")
    pkg_rel = packages_mappe(config_dir)
    ny_conf = None
    if not pkg_rel:
        ny_conf = tilfoej_packages(gammel_conf)
        if ny_conf is None:
            raise InstallFejl("configuration.yaml kunne ikke rettes automatisk")
        pkg_rel = "packages"
    anden = anden_styring(config_dir, pkg_rel)
    if anden:
        raise InstallFejl(f"der findes allerede en styring i {anden}")

    mappe, std = KANALER[kanal]
    pkg = cfg / pkg_rel
    backup = cfg / f"wattlas_backup_{time.strftime('%Y%m%d-%H%M%S')}"
    flyttet: list = []
    nye = [pkg / "wattlas", pkg / "wattlas_kanal", cfg / "www" / "wattlas", cfg / "wattlas"]
    kvit = {"conf": str(conf), "gammel_conf": gammel_conf, "nye": [str(p) for p in nye], "flyttet": flyttet, "backup": str(backup)}
    try:
        for p, navn in zip(nye, ["packages_wattlas", "packages_wattlas_kanal", "www_wattlas", "wattlas"]):
            _flyt(p, backup, navn, flyttet)
        shutil.copytree(PAYLOAD / "packages" / "wattlas", pkg / "wattlas")
        shutil.copytree(PAYLOAD / "styrekanaler" / mappe, pkg / "wattlas_kanal")
        shutil.copytree(PAYLOAD / "www", cfg / "www" / "wattlas")
        shutil.copytree(PAYLOAD / "dashboards", cfg / "wattlas" / "dashboards")

        if prefix != std:
            for f in (pkg / "wattlas_kanal").glob("*.yaml"):
                f.write_text(f.read_text(encoding="utf-8").replace(f"{std}_", f"{prefix}_"), encoding="utf-8")
        ds = cfg / "wattlas" / "dashboards"
        styr = (ds / "wattlas_styring.yaml").read_text(encoding="utf-8")
        energi = (ds / "wattlas.yaml").read_text(encoding="utf-8")
        if kanal == "deye" and prefix != std:
            styr = re.sub(r"(?m)^        # inverter_prefix: .*$", f"        inverter_prefix: {prefix}_", styr)
        if inv2:
            effekt = inv2.get("effekt") or f"sensor.{prefix}_microinverter_power"
            navn = inv2.get("navn") or "Inverter 2"
            if inv2.get("prefix"):
                styr = re.sub(r"(?m)^        # inverter2_prefix: .*$", f"        inverter2_prefix: {inv2['prefix']}_", styr)
            styr = re.sub(r"(?m)^        # inverter2_navn: .*$", f'        inverter2_navn: "{navn}"', styr)
            if inv2.get("relae"):
                styr = re.sub(r"(?m)^        # inverter2_relae: .*$", f"        inverter2_relae: {inv2['relae']}", styr)
            energi = re.sub(r"(?m)^        # pv_anlaeg: .*$",
                            f'        pv_anlaeg: [{{navn: Hybrid, entitet: sensor.{prefix}_pv_power}}, {{navn: "{navn}", entitet: {effekt}}}]', energi)
            if inv2.get("ac") and inv2.get("effekt"):
                f = pkg / "wattlas_kanal" / "wattlas_kanal_deye.yaml"
                t = f.read_text(encoding="utf-8")
                gl = f"states('sensor.{prefix}_microinverter_power') | float(0)] | max) | round(0)"
                if gl not in t:
                    raise InstallFejl("fandt ikke solproduktionen i styrekanalen")
                f.write_text(t.replace(gl, gl[:-len(") | round(0)")] + f" + [0, states('{inv2['effekt']}') | float(0)] | max) | round(0)"), encoding="utf-8")
        (ds / "wattlas_styring.yaml").write_text(styr, encoding="utf-8")
        (ds / "wattlas.yaml").write_text(energi, encoding="utf-8")

        (pkg / "wattlas" / "wattlas_frontend.yaml").write_text(
            f"# Lavet af Wattlas-integrationen ({version}). Dashboards i YAML-tilstand.\n"
            "lovelace:\n  dashboards:\n"
            "    wattlas-energi:\n      mode: yaml\n      title: Wattlas\n      icon: mdi:solar-power-variant\n"
            "      show_in_sidebar: true\n      filename: wattlas/dashboards/wattlas.yaml\n"
            "    wattlas-styring:\n      mode: yaml\n      title: Wattlas Styring\n      icon: mdi:tune-variant\n"
            "      show_in_sidebar: true\n      filename: wattlas/dashboards/wattlas_styring.yaml\n"
            f"frontend:\n  extra_module_url:\n    - /local/wattlas/energi-app-card.js?v={version}\n", encoding="utf-8")
        if ny_conf is not None:
            shutil.copy2(conf, cfg / f"configuration.yaml.wattlas_{time.strftime('%Y%m%d-%H%M%S')}")
            conf.write_text(ny_conf, encoding="utf-8", newline="")
    except Exception:
        rul_tilbage(kvit)
        raise
    return kvit


def rul_tilbage(kvit: dict) -> None:
    """Fjerner det nye og lægger det gamle tilbage, som det var før installationen."""
    for p in kvit["nye"]:
        shutil.rmtree(p, ignore_errors=True)
    for fra, til in reversed(kvit["flyttet"]):
        Path(til).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(fra), str(til))
    Path(kvit["conf"]).write_text(kvit["gammel_conf"], encoding="utf-8", newline="")
    b = Path(kvit["backup"])
    if b.exists() and not any(b.iterdir()):
        b.rmdir()


def afinstaller(config_dir: str) -> str | None:
    """Flytter Wattlas' filer til en backup-mappe (sletter intet). packages-linjen bliver stående."""
    cfg = Path(config_dir)
    pkg_rel = packages_mappe(config_dir) or "packages"
    backup = cfg / f"wattlas_backup_{time.strftime('%Y%m%d-%H%M%S')}"
    flyttet: list = []
    for p, navn in [(cfg / pkg_rel / "wattlas", "packages_wattlas"), (cfg / pkg_rel / "wattlas_kanal", "packages_wattlas_kanal"),
                    (cfg / "www" / "wattlas", "www_wattlas"), (cfg / "wattlas", "wattlas")]:
        _flyt(p, backup, navn, flyttet)
    return str(backup) if flyttet else None
