"""Wattlas – batteri- og solcellestyring med EMHASS.

Integrationen installerer Wattlas' pakker, kort og dashboards og overfører indstillingerne fra opsætningen til
Wattlas' hjælpere, når Home Assistant er genstartet. Selve styringen ligger i pakkerne (YAML), ikke her.
"""
from __future__ import annotations

import asyncio
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.check_config import async_check_ha_config_file
from homeassistant.helpers.start import async_at_started

from . import installer
from .config_flow import VERSION
from .const import DOMAIN, GENSTART, STANDARD

_LOGGER = logging.getLogger(__name__)
TEKST = {"emhass_adresse": "emhass_adresse", "emhass_noegle": "emhass_noegle", "solprognose": "solprognose_entitet",
         "vejr": "vejr_entitet", "udetemperatur": "udetemperatur_entitet"}
STYRING = "input_boolean.emhass_styring_aktiv"
FULD = "input_boolean.emhass_fuld_opladning"
VENT_S = 60  # så længe ventes der ved fjernelse på, at inverteren er sat til selvforbrug
# platforme, Wattlas' YAML-pakker opretter entiteter med (deres registreringer bliver liggende, når filerne skifter)
YAML_PLATFORME = {"template", "integration", "utility_meter", "automation", "script", "input_boolean", "input_number",
                  "input_datetime", "input_text", "input_select"}


def _ryd_efterladte(hass: HomeAssistant, tekst: str, kendt: str) -> list[str]:
    """Rydder Wattlas-registreringer, som en tidligere styrekanal har efterladt (fx efter skift fra Huawei til Growatt).

    Kanalerne laver de samme entiteter på forskellige platforme (sensor.wattlas_total_koebt er en template-sensor hos
    Huawei og en integration-sensor hos Growatt). Den gamle registrering beholder navnet, og den nye får "_2" – så tæller
    kort og økonomi ikke længere. En registrering fjernes kun, hvis den ikke har en levende entitet, OG enten en levende
    "tvilling" med samme unique_id på en anden platform findes, eller dens unique_id ikke står i de installerede filer
    (så en midlertidig YAML-fejl aldrig fjerner noget). Tvillingen får derefter det oprindelige navn tilbage.
    Kun unique_id'er fra Wattlas' egne filer (`kendt`) røres – brugerens egne "emhass_…"-entiteter aldrig."""
    reg = er.async_get(hass)
    lever = lambda e: (s := hass.states.get(e.entity_id)) is not None and not s.attributes.get("restored")  # noqa: E731
    wattlas = [e for e in reg.entities.values()
               if e.platform in YAML_PLATFORME and str(e.unique_id).startswith(("wattlas_", "emhass_"))]
    står_i = lambda t, uid: re.search(rf"\b{re.escape(uid)}\b", t) is not None  # noqa: E731
    ryddet = []
    for e in wattlas:
        s = hass.states.get(e.entity_id)
        if s is None or not s.attributes.get("restored"):  # lever, eller er slået fra (så har den ingen tilstand) – rør den ikke
            continue
        if not står_i(kendt, str(e.unique_id)):  # ikke Wattlas' egen
            continue
        tvilling = next((t for t in wattlas if t.unique_id == e.unique_id and t.platform != e.platform and lever(t)), None)
        if tvilling is None and (not tekst or står_i(tekst, str(e.unique_id))):
            continue
        reg.async_remove(e.entity_id)
        ryddet.append(e.entity_id)
        if tvilling is not None and tvilling.entity_id == f"{e.entity_id}_2":
            reg.async_update_entity(tvilling.entity_id, new_entity_id=e.entity_id)
    return ryddet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    d = entry.data
    if d.get("version") != VERSION:  # ny version fra markedspladsen: læg de nye filer på plads
        try:
            kvit = await hass.async_add_executor_job(installer.installer, hass.config.config_dir, d["kanal"], d["prefix"],
                                                     d.get("inverter2"), VERSION, d.get("ekstra"))
            res = await async_check_ha_config_file(hass)
            if res.errors:  # den nye version passer ikke til denne HA: læg den gamle tilbage
                await hass.async_add_executor_job(installer.rul_tilbage, kvit)
                raise RuntimeError("; ".join(str(e.message) for e in res.errors[:3]))
            hass.config_entries.async_update_entry(entry, data={**d, "version": VERSION})
            ir.async_delete_issue(hass, DOMAIN, "opdatering_fejlede")
            hass.data[GENSTART] = True
            ir.async_create_issue(hass, DOMAIN, "genstart", is_fixable=True, is_persistent=True,
                                  severity=ir.IssueSeverity.WARNING, translation_key="genstart")
        except Exception as e:  # filerne er rullet tilbage; den gamle version kører videre
            _LOGGER.error("Wattlas: opdatering til %s fejlede: %s", VERSION, e)
            # ikke gemt: forsøget gentages ved næste genstart og opretter den igen, hvis det stadig fejler
            ir.async_create_issue(hass, DOMAIN, "opdatering_fejlede", is_fixable=False, is_persistent=False,
                                  severity=ir.IssueSeverity.ERROR, translation_key="opdatering_fejlede",
                                  translation_placeholders={"version": VERSION, "fejl": str(e)[:300]})

    async def overfoer(_hass: HomeAssistant) -> None:
        """Sætter indstillingerne fra opsætningen i hjælperne – hver indstilling én gang, og kun hvis den står tom (0/tekst mangler)."""
        s = hass.states.get("binary_sensor.wattlas_konfigureret")
        if s is None or s.state in ("unavailable", "unknown"):
            return  # pakkerne er ikke indlæst endnu (genstart mangler); efter en afinstallation står den som "unavailable"
        if hass.data.get(GENSTART):
            return  # sensoren kommer fra de gamle pakker i hukommelsen (opdatering, eller fjernet og tilføjet uden genstart)
        ir.async_delete_issue(hass, DOMAIN, "genstart")
        tekst = await hass.async_add_executor_job(installer.installeret_tekst, hass.config.config_dir)
        kendt = await hass.async_add_executor_job(installer.kendt_tekst)
        if ryddet := _ryd_efterladte(hass, tekst, kendt):
            _LOGGER.info("Wattlas: fjernede %d efterladte registreringer fra en tidligere styrekanal: %s", len(ryddet), ", ".join(ryddet))
        d = entry.data  # frisk: opdateringen ovenfor kan have skrevet en ny version
        foer = d.get("overfoert")
        sat = set(foer) if isinstance(foer, list) else set()  # navne, der er overført – så et 0, brugeren selv sætter, får lov at stå
        for k, v in {**STANDARD, **(d.get("tal") or {})}.items():  # en ny standardværdi i en senere version når også ældre opsætninger
            s = hass.states.get(f"input_number.wattlas_{k}")
            if k in sat or s is None:
                continue
            if v is not None and _tal(s.state) == 0:
                await hass.services.async_call("input_number", "set_value", {"entity_id": s.entity_id, "value": v}, blocking=True)
            sat.add(k)
        for k, h in TEKST.items():
            s = hass.states.get(f"input_text.wattlas_{h}")
            if k in sat or s is None:
                continue
            if d.get(k) and s.state in ("", "unknown", "unavailable"):
                await hass.services.async_call("input_text", "set_value", {"entity_id": s.entity_id, "value": d[k]}, blocking=True)
            sat.add(k)
        if "fuld_opladning" not in sat and hass.states.get(FULD) is not None:  # ugentlig fuldladning: til fra start, derefter huskes brugerens valg
            await hass.services.async_call("input_boolean", "turn_on", {"entity_id": FULD}, blocking=True)
            sat.add("fuld_opladning")
        if sorted(sat) != foer:
            # når nøglen ligger i hjælperen, skal integrationen ikke gemme en kopi
            hass.config_entries.async_update_entry(entry, data={
                **{k: v for k, v in entry.data.items() if k != "emhass_noegle" or k not in sat}, "overfoert": sorted(sat)})

    entry.async_on_unload(async_at_started(hass, overfoer))
    return True


def _tal(v: str) -> float:
    try:
        return float(v)
    except ValueError:
        return 0.0


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Slår styringen fra og flytter Wattlas' filer til en backup-mappe. Resten forsvinder ved næste genstart."""
    if hass.states.is_state(STYRING, "on"):
        # hovedafbryderen (automation) sætter inverteren til selvforbrug; vent på den, så en genstart ikke afbryder skrivningen
        await hass.services.async_call("input_boolean", "turn_off", {"entity_id": STYRING}, blocking=True)
        for _ in range(VENT_S):
            if not hass.states.is_state("input_boolean.emhass_har_overtaget", "on"):
                break
            await asyncio.sleep(1)
    # stadig "overtaget": inverteren svarede ikke (fx offline), så den står i det sidste program
    selvforbrug = not hass.states.is_state("input_boolean.emhass_har_overtaget", "on")
    backup = await hass.async_add_executor_job(installer.afinstaller, hass.config.config_dir)
    for i in ("genstart", "opdatering_fejlede"):
        ir.async_delete_issue(hass, DOMAIN, i)
    if backup:
        _LOGGER.warning("Wattlas er fjernet. Filerne ligger i %s. Genstart Home Assistant.", backup)
        ir.async_create_issue(hass, DOMAIN, "fjernet", is_fixable=True, is_persistent=False,  # ikke gemt: væk efter genstarten
                              severity=ir.IssueSeverity.WARNING if selvforbrug else ir.IssueSeverity.ERROR,
                              translation_key="fjernet" if selvforbrug else "fjernet_tjek",
                              translation_placeholders={"backup": backup})
