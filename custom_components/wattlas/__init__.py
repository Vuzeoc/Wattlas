"""Wattlas – batteri- og solcellestyring med EMHASS.

Integrationen installerer Wattlas' pakker, kort og dashboards og overfører indstillingerne fra opsætningen til
Wattlas' hjælpere, når Home Assistant er genstartet. Selve styringen ligger i pakkerne (YAML), ikke her.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.start import async_at_started

from . import installer
from .config_flow import VERSION
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
TEKST = {"emhass_adresse": "emhass_adresse", "emhass_noegle": "emhass_noegle", "solprognose": "solprognose_entitet",
         "vejr": "vejr_entitet", "udetemperatur": "udetemperatur_entitet"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    d = entry.data
    if d.get("version") != VERSION:  # ny version fra markedspladsen: læg de nye filer på plads
        try:
            await hass.async_add_executor_job(installer.installer, hass.config.config_dir, d["kanal"], d["prefix"],
                                              d.get("inverter2"), VERSION)
            hass.config_entries.async_update_entry(entry, data={**d, "version": VERSION})
            ir.async_create_issue(hass, DOMAIN, "genstart", is_fixable=True, is_persistent=True,
                                  severity=ir.IssueSeverity.WARNING, translation_key="genstart")
        except Exception as e:  # filerne er rullet tilbage; den gamle version kører videre
            _LOGGER.error("Wattlas: opdatering til %s fejlede: %s", VERSION, e)

    async def overfoer(_hass: HomeAssistant) -> None:
        """Sætter indstillingerne fra opsætningen i hjælperne – kun dem, der stadig står tomme (0/tekst mangler)."""
        s = hass.states.get("binary_sensor.wattlas_konfigureret")
        if s is None or s.state in ("unavailable", "unknown"):
            return  # pakkerne er ikke indlæst endnu (genstart mangler); efter en afinstallation står den som "unavailable"
        ir.async_delete_issue(hass, DOMAIN, "genstart")
        for k, v in (d.get("tal") or {}).items():
            s = hass.states.get(f"input_number.wattlas_{k}")
            if s is not None and v is not None and _tal(s.state) == 0:
                await hass.services.async_call("input_number", "set_value", {"entity_id": s.entity_id, "value": v}, blocking=True)
        for k, h in TEKST.items():
            s = hass.states.get(f"input_text.wattlas_{h}")
            if s is not None and d.get(k) and s.state in ("", "unknown", "unavailable"):
                await hass.services.async_call("input_text", "set_value", {"entity_id": s.entity_id, "value": d[k]}, blocking=True)

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
    """Flytter Wattlas' filer til en backup-mappe. Styringen stopper efter næste genstart."""
    backup = await hass.async_add_executor_job(installer.afinstaller, hass.config.config_dir)
    ir.async_delete_issue(hass, DOMAIN, "genstart")
    if backup:
        _LOGGER.warning("Wattlas er fjernet. Filerne ligger i %s. Genstart Home Assistant.", backup)
