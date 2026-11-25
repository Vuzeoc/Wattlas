"""Diagnostik-download (Indstillinger → Enheder og tjenester → Wattlas → ⋮ → Download diagnostik) til fejlrapporter.

Kun det, der står her, kommer med: ingen adresse, nøgle, token, placering, navne eller brugerens egne entiteter (de kan rumme stednavne).
Nettarif og afgifter vises kun som "sat": de præcise tal kan slås op og peger på netselskabet.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import installer, tariffer
from .config_flow import VERSION, _database, priser_fejl

DOMAENER = ("sensor", "binary_sensor", "input_boolean", "input_number", "input_select", "input_datetime", "switch", "number", "script", "automation")
EMHASS = ("p_batt_", "p_grid_", "p_load_", "p_pv_", "p_deferrable", "soc_batt_", "optim_status")  # dem, EMHASS publicerer
ATTRIBUTTER = ("mangler", "forklaring", "kilde", "min", "max", "step")  # resten kan rumme brugerens egne tekster (fx regler)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    nu = dt_util.utcnow()
    kendt = await hass.async_add_executor_job(installer.kendt_tekst)  # kun navne fra Wattlas' egne filer
    tilstande = {s.entity_id: {"tilstand": s.state[:80], "alder_s": round((nu - s.last_reported).total_seconds()),
                               **{k: s.attributes[k] for k in ATTRIBUTTER if k in s.attributes}}
                 if s.entity_id.removeprefix("input_number.wattlas_") not in tariffer.FELTER else {"sat": s.state not in ("0", "0.0", "unknown", "unavailable")}
                 for s in sorted(hass.states.async_all(DOMAENER), key=lambda s: s.entity_id)
                 if s.object_id.startswith(EMHASS) or (s.object_id.startswith(("wattlas_", "emhass_", "min_sonnen_", "min_spf_")) and s.object_id in kendt)}
    d = entry.data
    return {"wattlas": VERSION, "installeret": d.get("version"), "home_assistant": __version__, "database": _database(hass),
            "kanal": d.get("kanal"), "ekstra_inverter": bool(d.get("inverter2")), "tal": {k: v for k, v in (d.get("tal") or {}).items() if k not in tariffer.FELTER},
            "emhass_sat": bool(d.get("emhass_adresse") and d.get("emhass_noegle")), "priser_fejl": priser_fejl(hass), "tariffer_hentes": bool(d.get("netselskab")), "tilstande": tilstande}
