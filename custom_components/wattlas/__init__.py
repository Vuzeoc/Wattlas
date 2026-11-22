"""Wattlas – batteri- og solcellestyring med EMHASS.

Integrationen installerer Wattlas' pakker, kort og dashboards og overfører indstillingerne fra opsætningen til
Wattlas' hjælpere, når Home Assistant er genstartet. Selve styringen ligger i pakkerne (YAML), ikke her.
"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.check_config import async_check_ha_config_file
from homeassistant.helpers.start import async_at_started

from . import installer
from .config_flow import VERSION
from .const import DOMAIN, STANDARD

_LOGGER = logging.getLogger(__name__)
TEKST = {"emhass_adresse": "emhass_adresse", "emhass_noegle": "emhass_noegle", "solprognose": "solprognose_entitet",
         "vejr": "vejr_entitet", "udetemperatur": "udetemperatur_entitet"}
STYRING = "input_boolean.emhass_styring_aktiv"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    d = entry.data
    if d.get("version") != VERSION:  # ny version fra markedspladsen: læg de nye filer på plads
        try:
            kvit = await hass.async_add_executor_job(installer.installer, hass.config.config_dir, d["kanal"], d["prefix"],
                                                     d.get("inverter2"), VERSION)
            res = await async_check_ha_config_file(hass)
            if res.errors:  # den nye version passer ikke til denne HA: læg den gamle tilbage
                await hass.async_add_executor_job(installer.rul_tilbage, kvit)
                raise RuntimeError("; ".join(str(e.message) for e in res.errors[:3]))
            hass.config_entries.async_update_entry(entry, data={**d, "version": VERSION})
            ir.async_delete_issue(hass, DOMAIN, "opdatering_fejlede")
            ir.async_create_issue(hass, DOMAIN, "genstart", is_fixable=True, is_persistent=True,
                                  severity=ir.IssueSeverity.WARNING, translation_key="genstart")
        except Exception as e:  # filerne er rullet tilbage; den gamle version kører videre
            _LOGGER.error("Wattlas: opdatering til %s fejlede: %s", VERSION, e)
            # ikke gemt: forsøget gentages ved næste genstart og opretter den igen, hvis det stadig fejler
            ir.async_create_issue(hass, DOMAIN, "opdatering_fejlede", is_fixable=False, is_persistent=False,
                                  severity=ir.IssueSeverity.ERROR, translation_key="opdatering_fejlede",
                                  translation_placeholders={"version": VERSION, "fejl": str(e)[:300]})

    async def overfoer(_hass: HomeAssistant) -> None:
        """Sætter indstillingerne fra opsætningen i hjælperne – én gang, og kun dem, der stadig står tomme (0/tekst mangler)."""
        s = hass.states.get("binary_sensor.wattlas_konfigureret")
        if s is None or s.state in ("unavailable", "unknown"):
            return  # pakkerne er ikke indlæst endnu (genstart mangler); efter en afinstallation står den som "unavailable"
        ir.async_delete_issue(hass, DOMAIN, "genstart")
        d = entry.data  # frisk: opdateringen ovenfor kan have skrevet en ny version
        if d.get("overfoert"):
            return  # ellers ville en indstilling, brugeren selv sætter til 0, blive sat tilbage ved hver genstart
        for k, v in {**STANDARD, **(d.get("tal") or {})}.items():  # STANDARD: også for opsætninger fra før feltet fandtes
            s = hass.states.get(f"input_number.wattlas_{k}")
            if s is not None and v is not None and _tal(s.state) == 0:
                await hass.services.async_call("input_number", "set_value", {"entity_id": s.entity_id, "value": v}, blocking=True)
        for k, h in TEKST.items():
            s = hass.states.get(f"input_text.wattlas_{h}")
            if s is not None and d.get(k) and s.state in ("", "unknown", "unavailable"):
                await hass.services.async_call("input_text", "set_value", {"entity_id": s.entity_id, "value": d[k]}, blocking=True)
        if hass.states.get("input_boolean.emhass_fuld_opladning") is not None:  # ugentlig fuldladning: til fra start, derefter huskes brugerens valg
            await hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.emhass_fuld_opladning"}, blocking=True)
        # nøglen ligger nu i hjælperen; integrationen skal ikke gemme en kopi
        hass.config_entries.async_update_entry(entry, data={**{k: v for k, v in entry.data.items() if k != "emhass_noegle"}, "overfoert": True})

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
        for _ in range(60):
            if not hass.states.is_state("input_boolean.emhass_har_overtaget", "on"):
                break
            await asyncio.sleep(1)
    backup = await hass.async_add_executor_job(installer.afinstaller, hass.config.config_dir)
    for i in ("genstart", "opdatering_fejlede"):
        ir.async_delete_issue(hass, DOMAIN, i)
    if backup:
        _LOGGER.warning("Wattlas er fjernet. Filerne ligger i %s. Genstart Home Assistant.", backup)
        ir.async_create_issue(hass, DOMAIN, "fjernet", is_fixable=True, is_persistent=False,  # ikke gemt: væk efter genstarten
                              severity=ir.IssueSeverity.WARNING, translation_key="fjernet",
                              translation_placeholders={"backup": backup})
