"""Vagt mod anden styring: andre automationer og scripts, der rører de samme indstillinger i inverteren (eller laderen) som Wattlas.

To styringer på ét batteri skriver oven i hinanden, og så gør inverteren hverken det ene eller det andet. Wattlas finder
enhederne ud fra sine egne automationer og scripts og ser, hvem der ellers bruger enhedernes indstillinger (number, select,
switch, button, time) eller selve enheden. Kun det, der står fast i automationen, kan ses – ikke navne, der bygges i en skabelon.
"""
from __future__ import annotations

import re
from functools import lru_cache

from homeassistant.components import automation, script
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from . import installer
from .const import DOMAIN

EGEN = ("emhass_", "wattlas_")  # Wattlas' egne entiteter (brugerens egne "emhass_"-scripts afgøres af filerne, ikke navnet)
SKRIV = ("number", "select", "switch", "button", "time")
ISSUE = "anden_styring"


@lru_cache(maxsize=2)
def _navne(kendt: str) -> tuple[frozenset[str], frozenset[str]]:
    """(scriptnavne, automations-id'er) i Wattlas' filer – læst én gang, ikke én søgning i ~800 KB pr. automation (blokerede HA)."""
    return (frozenset(re.findall(r"^  ([^\s:#]+):", kendt, re.M)),
            frozenset(re.findall(r"^\s*-?\s*id: (\S+)\s*$", kendt, re.M)))  # ikke unique_id


def _egen(hass: HomeAssistant, entity_id: str, kendt: str) -> bool:
    """Wattlas' egne: står i Wattlas' installerede filer – scripts efter navn, automationer efter id (navnet følger aliasset)."""
    scripts, ids = _navne(kendt)
    dom, navn = entity_id.split(".", 1)
    if dom == "script":
        return navn in scripts
    s = hass.states.get(entity_id)
    aid = str(s.attributes.get("id") or "") if s else ""
    return bool(aid) and aid in ids


@callback
def find(hass: HomeAssistant, kendt: str) -> dict[str, list[str]]:
    """{automation/script: [det, den rører]} for alt, der ikke er Wattlas' eget. Slåede-fra automationer tæller ikke."""
    reg = er.async_get(hass)
    egne = [e for e in hass.states.async_entity_ids(("automation", "script")) if _egen(hass, e, kendt)]
    enheder = set()
    for e in egne:
        aut = e.startswith("automation.")
        ref = automation.entities_in_automation(hass, e) if aut else script.entities_in_script(hass, e)
        enheder |= {r.device_id for x in ref if (r := reg.async_get(x)) and r.device_id}
        enheder |= set(automation.devices_in_automation(hass, e) if aut else script.devices_in_script(hass, e))  # fx Huaweis tjenester med device_id
    fund: dict[str, set[str]] = {}
    for d in enheder:
        for a in automation.automations_with_device(hass, d) + script.scripts_with_device(hass, d):
            fund.setdefault(a, set()).add("enheden")
        for r in er.async_entries_for_device(reg, d):
            if r.domain in SKRIV and r.disabled_by is None and not r.entity_id.split(".", 1)[1].startswith(EGEN):
                for a in automation.automations_with_entity(hass, r.entity_id) + script.scripts_with_entity(hass, r.entity_id):
                    fund.setdefault(a, set()).add(r.entity_id)
    return {a: sorted(x) for a, x in sorted(fund.items()) if not (a.startswith("automation.") and hass.states.is_state(a, "off")) and not _egen(hass, a, kendt)}


async def tjek(hass: HomeAssistant) -> dict[str, list[str]]:
    """Viser fundet under Reparationer (eller fjerner meddelelsen, når der intet er). I skygge må andre gerne styre."""
    if not hass.states.is_state("input_boolean.emhass_har_overtaget", "on"):
        ir.async_delete_issue(hass, DOMAIN, ISSUE)
        return {}
    fund = find(hass, await hass.async_add_executor_job(installer.kendt_tekst))
    if not fund:
        ir.async_delete_issue(hass, DOMAIN, ISSUE)
        return fund
    navn = lambda e: (s.name if (s := hass.states.get(e)) else e)  # noqa: E731
    liste = "\n".join(f"- **{navn(a)}** (`{a}`): {', '.join(x)}" for a, x in list(fund.items())[:10])
    ir.async_create_issue(hass, DOMAIN, ISSUE, is_fixable=False, is_persistent=False, severity=ir.IssueSeverity.WARNING,
                          translation_key=ISSUE, translation_placeholders={"liste": liste})
    return fund
