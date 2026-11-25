"""Nettarif, elafgift og Energinets tariffer fra Energinets åbne liste (valgfrit – ellers taster brugeren dem selv).

Kilde: Energinet (www.energidataservice.dk), datasættet DatahubPricelist, CC BY 4.0. Priserne er uden moms, som Wattlas' hjælpere.
Ét lille kald om dagen. Alt, der ikke ser rigtigt ud, afvises: så bliver de gamle tal stående, og brugeren får besked.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
URL = "https://api.energidataservice.dk/dataset/DatahubPricelist"
ENERGINET = "5790000432752"
FAELLES = ("40000", "41000", "EA-001")  # transmissionsnettarif, systemtarif, elafgift
FELTER = ("nettarif_lav", "nettarif_hoej", "nettarif_spids", "elafgift")
HENTET = "input_text.wattlas_tarif_hentet"
SIDST = f"{DOMAIN}_tarif_sidst"  # hass.data: (selskab, dato) for den seneste vellykkede hentning
TAAL = timedelta(days=3)  # så længe må listen være utilgængelig, før brugeren får en reparation
MANUEL = "manuel"
# GLN-nummer → (navn, kode for "Nettarif C", evt. koder for rabatter, der trækkes fra). Selskaber, der ikke står her, tastes selv.
SELSKABER: dict[str, tuple[str, ...]] = {
    "5790001095451": ("Aal El-Net", "AAL-NT-05"),
    "5790000705184": ("Cerius", "30TR_C_ET", "30RE_C_ET"),
    "5790000610099": ("Dinel", "TCL<100_02"),
    "5790000836239": ("Elektrus", "6000091"),
    "5790001100520": ("Elnet Midt", "T3001"),
    "5790000392551": ("FLOW Elnet", "FE1 NT-01"),
    "5790000681105": ("Grindsted Elnet (GEV)", "GEV-NT-01"),
    "5790001090166": ("Hammel Elforsyning Net", "C-Tarif"),
    "5790001095376": ("Hjerting Transformatorforening", "C-Tarif"),
    "5790000610839": ("Hurup Elværk Net", "HEV-NT-01T"),
    "5790000682102": ("Ikast El Net", "IEV-NT-01"),
    "5790001095239": ("Kimbrer Elnet", "C-Tarif"),
    "5790000704842": ("Konstant Net (151)", "C_FBTNTR_B", "C_FBTNTR_R"),
    "5790000683345": ("Konstant Net (245)", "C_FBTNTR_B", "C_FBTNTR_R"),
    "5790001090111": ("L-Net", "3000"),
    "5790001089023": ("Midtfyns Elforsyning", "TNT15000"),
    "5790002502699": ("N1 (016)", "C-Tarif"),
    "5790001089030": ("N1 (131)", "CD"),
    "5790000611003": ("N1 (344)", "T-C-F-F-TD"),
    "5790000681358": ("Netselskabet Elværk", "5NCFF"),
    "5790000395620": ("NOE Net", "30030"),
    "5790000610877": ("Nord Energi Net", "TAC"),
    "5790000681327": ("RAH Net", "RAH-C"),
    "5790000705689": ("Radius Elnet", "DT_C_01"),
    "5790000836727": ("Ravdex", "NT-C"),
    "5790001095444": ("Sunds Net", "SEF-NT-05"),
    "5790000706419": ("Tarm Elværk Net", "TEV-NT-01T"),
    "5790000392261": ("TREFOR El-net", "C"),
    "5790000706686": ("TREFOR El-net Øst", "46"),
    "5790001088217": ("Veksel", "NT-01"),
    "5790000610976": ("Vores Elnet", "TNT1009"),
    "5790001089375": ("Zeanet", "43110"),
}


class TarifFejl(Exception):
    """Tallene kan ikke bruges (teksten vises for brugeren). `svar`: listen kunne ikke hentes – det går som regel over."""

    def __init__(self, tekst: str, svar: bool = False) -> None:
        super().__init__(tekst)
        self.svar = svar


def beregn(raekker: list[dict], gln: str, dato: str) -> dict[str, float]:
    """De fire tal, der gælder på datoen (kr./kWh uden moms)."""
    _, kode, *rabatter = SELSKABER[gln]
    gyldige = [r for r in raekker if r["ValidFrom"][:10] <= dato and (not r["ValidTo"] or r["ValidTo"][:10] > dato)]

    def timer(ejer: str, k: str) -> list[float]:
        fundet = [r for r in gyldige if r["GLN_Number"] == ejer and r["ChargeTypeCode"] == k]
        if len(fundet) != 1:
            raise TarifFejl(f"der er {len(fundet)} priser for {k} på listen i dag")
        r = fundet[0]  # et tomt felt betyder samme pris som den første time
        return [float(r["Price1"] if r[f"Price{i}"] is None else r[f"Price{i}"]) for i in range(1, 25)]

    rabat = [timer(gln, k) for k in rabatter]  # negative tal; mangler en, afvises tallene – ellers ville prisen stille blive for høj
    if any(v > 0 for t in rabat for v in t):
        raise TarifFejl("en rabat på listen er ikke en rabat")
    net = [round(sum(t), 6) for t in zip(timer(gln, kode), *rabat, strict=True)]
    if any(len({net[h] for h in periode}) != 1 for periode in (range(6), [*range(6, 17), 21, 22, 23], range(17, 21))):
        raise TarifFejl("netselskabets tarif har i dag andre tidsrum end kl. 0–6, 6–17/21–24 og 17–21")
    faelles = [timer(ENERGINET, k) for k in FAELLES]
    if any(len(set(t)) != 1 for t in faelles):
        raise TarifFejl("elafgiften eller Energinets tariffer er ikke ens hele døgnet")
    tal = {"nettarif_lav": net[0], "nettarif_hoej": net[6], "nettarif_spids": net[17], "elafgift": round(sum(t[0] for t in faelles), 6)}
    if not all(0 < v <= 5 for v in tal.values()):  # 0 ville sænke startspærren
        raise TarifFejl("en af priserne er 0 eller urimelig")
    return tal


async def hent(hass: HomeAssistant, gln: str) -> dict[str, float]:
    """Dagens tal for netselskabet."""
    if gln not in SELSKABER:
        raise TarifFejl("netselskabet findes ikke længere på Wattlas' liste")
    param = {"filter": json.dumps({"GLN_Number": [gln, ENERGINET], "ChargeType": ["D03"], "ChargeTypeCode": [*SELSKABER[gln][1:], *FAELLES]}),
             "columns": ",".join(["GLN_Number", "ChargeTypeCode", "ValidFrom", "ValidTo", *(f"Price{i}" for i in range(1, 25))]),
             "sort": "ValidFrom DESC", "limit": "500"}
    try:
        async with async_get_clientsession(hass).get(URL, params=param, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                raise TarifFejl(f"Energinets liste svarede {r.status}", svar=True)
            data = await r.json(content_type=None)
    except (TimeoutError, aiohttp.ClientError, ValueError) as e:
        raise TarifFejl(f"Energinets liste svarede ikke ({type(e).__name__})", svar=True) from None
    try:
        return beregn(data["records"], gln, dt_util.now().date().isoformat())
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise TarifFejl(f"Energinets liste har et ukendt format ({type(e).__name__})") from None


def vis(tal: dict[str, float]) -> str:
    """Tallene til en formular eller besked."""
    n = lambda k: f"{tal[k]:.4f}".replace(".", ",")  # noqa: E731
    return (f"nettarif kl. 0–6: {n('nettarif_lav')}, kl. 6–17 og 21–24: {n('nettarif_hoej')}, kl. 17–21: {n('nettarif_spids')}; "
            f"elafgift og Energinet: {n('elafgift')} kr./kWh uden moms")


async def anvend(hass: HomeAssistant, tal: dict[str, float]) -> dict[str, float]:
    """Skriver tallene i hjælperne. Giver de gamle værdier, hvis noget blev ændret."""
    gamle = {}
    for k in tal:
        try:
            gamle[k] = float(hass.states.get(f"input_number.wattlas_{k}").state)
        except (AttributeError, ValueError):
            gamle[k] = 0.0
    nye = {k: v for k, v in tal.items() if abs(gamle[k] - v) > 5e-7}
    for k, v in nye.items():
        await hass.services.async_call("input_number", "set_value", {"entity_id": f"input_number.wattlas_{k}", "value": v}, blocking=True)
    if hass.states.get(HENTET):  # påmindelsen om nettariffer tier, når de hentes selv
        await hass.services.async_call("input_text", "set_value", {"entity_id": HENTET, "value": dt_util.now().isoformat(timespec="seconds")}, blocking=True)
    return gamle if nye else {}


async def opdater(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Én vellykket hentning om dagen; mislykkes den, prøves der igen næste time."""
    gln, dato = entry.data.get("netselskab"), dt_util.now().date().isoformat()
    if not gln or hass.data.get(SIDST) == (gln, dato):
        return
    s = hass.states.get("input_number.wattlas_elafgift")
    if s is None or s.state == "unavailable":
        return  # pakkerne er ikke indlæst (endnu)

    def uaktuel() -> bool:  # skiftet i Konfigurer, eller Wattlas er fjernet, mens der blev hentet
        return entry.data.get("netselskab") != gln or hass.config_entries.async_get_entry(entry.entry_id) is not entry
    try:
        tal = await hent(hass, gln)
    except TarifFejl as e:
        if uaktuel():
            return
        _LOGGER.info("Wattlas: nettarifferne blev ikke opdateret: %s", e)
        sidst = dt_util.parse_datetime(h.state) if (h := hass.states.get(HENTET)) else None
        if not e.svar or sidst is None or sidst.tzinfo is None or dt_util.now() - sidst > TAAL:
            ir.async_create_issue(hass, DOMAIN, "tarif_fejl", is_fixable=False, is_persistent=False, severity=ir.IssueSeverity.WARNING,
                                  translation_key="tarif_fejl", translation_placeholders={"fejl": str(e)})
        return
    if uaktuel():
        return
    gamle = await anvend(hass, tal)
    hass.data[SIDST] = (gln, dato)
    ir.async_delete_issue(hass, DOMAIN, "tarif_fejl")
    if any(gamle.values()) and hass.services.has_service("script", "wattlas_besked"):
        await hass.services.async_call("script", "wattlas_besked", {
            "title": "Wattlas · nye nettariffer", "message": f"Nu: {vis(tal)}.\n\nFør: {vis(gamle)}.\n\nKilde: Energinet (www.energidataservice.dk)",
            "data": {"tag": "wattlas_tarif"}})
