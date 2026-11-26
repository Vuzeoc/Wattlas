"""Konstanter for Wattlas-integrationen."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

DOMAIN = "wattlas"
GENSTART = "wattlas_genstart_mangler"  # hass.data: nye filer ligger på disken, men HA kører stadig de gamle (væk ved genstart)
EMHASS_SLUG = "5b918bf2_emhass"
EMHASS_REPO = "https://github.com/davidusb-geek/emhass-add-on"

# Knapper til det, der mangler (my.home-assistant.io åbner den rigtige side i brugerens egen HA)
LINK = {
    "emhass": "https://my.home-assistant.io/redirect/supervisor_addon/?addon=5b918bf2_emhass&repository_url=https%3A%2F%2Fgithub.com%2Fdavidusb-geek%2Femhass-add-on",
    "workday": "https://my.home-assistant.io/redirect/config_flow_start/?domain=workday",
}

# Hvilke indstillinger der vises i hvilket trin (samme navne som input_number.wattlas_…)
TRIN = {
    "batteri": ["batteri_kwh", "maks_ladeeffekt_w", "maks_afladeeffekt_w", "maks_ladestroem_a", "maks_afladestroem_a",
                "maks_netladestroem_a", "maks_netladeeffekt_w"],
    "elnet": ["sikring_a", "fase_graense_a", "import_graense_w", "maks_netimport_w", "maks_eksport_w"],
    "priser": ["nettarif_lav", "nettarif_hoej", "nettarif_spids", "elafgift", "tillaeg", "salg_nettarif", "salg_gebyr",
               "solcelle_slid", "slid", "kulde_w_pr_grad"],
}
# opsætningens tekstfelter → input_text.wattlas_<navn>
TEKST = {"solprognose": "solprognose_entitet", "vejr": "vejr_entitet", "udetemperatur": "udetemperatur_entitet", "pris": "pris_entitet", "solcast": "solcast_entiteter"}
# til og med 0.4.1 lå EMHASS' adresse og nøgle i hjælpere: nøglen kunne læses, og adressen (hvor nøglen sendes hen) rettes, af alle
GAMLE = {"emhass_adresse": "input_text.wattlas_emhass_adresse", "emhass_noegle": "input_text.wattlas_emhass_noegle"}
GYLDIG = {"emhass_adresse": re.compile(r"https?://.+"), "emhass_noegle": re.compile(r"(?!unavailable$).{8,}")}
STANDARD = {"slid": 0.25, "maks_soc": 100}  # slid: forudfyldt i opsætningen: uden en slidpris regner planen batteriet som gratis at bruge
NAVN_RE = r"[A-Za-z0-9 ._æøåÆØÅ-]*"  # navnet skrives ind i dashboardets YAML

_INDST = Path(__file__).parent / "payload" / "packages" / "wattlas" / "wattlas_indstillinger.yaml"


def _laes_indstillinger() -> tuple[dict, list[str]]:
    """input_number-definitionerne og listen over påkrævede tal – direkte fra pakken, så de aldrig kommer ud af trit."""
    tekst = _INDST.read_text(encoding="utf-8")
    tal = {k.removeprefix("wattlas_"): v for k, v in (yaml.safe_load(tekst.split("\ninput_text:")[0]) or {})["input_number"].items()}
    m = re.search(r"\{% set tal = \[(.*?)\] %\}", tekst, re.S)
    paakraevet = re.findall(r"'([a-z0-9_]+)'", m.group(1)) if m else []
    return tal, paakraevet


TAL, PAAKRAEVET = _laes_indstillinger()
assert set(PAAKRAEVET) <= {k for v in TRIN.values() for k in v}, "et påkrævet tal mangler i opsætningen"
