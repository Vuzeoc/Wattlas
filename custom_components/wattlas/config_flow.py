"""Opsætning af Wattlas: tjek forudsætninger, vælg inverter, udfyld indstillinger, installér."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector as sel
from homeassistant.helpers.check_config import async_check_ha_config_file

from . import installer
from .const import DOMAIN, EMHASS_SLUG, LINK, PAAKRAEVET, TAL, TRIN

VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))["version"]
SUFFIX = {"deye": ("sensor", "_pv_power"), "sunmate": ("number", "_timepoint_1_power")}


def _emhass(hass) -> tuple[str | None, str | None]:
    """(tilstand, adresse) for EMHASS-app'en. tilstand None = ikke HA OS/Supervised, så vi kan ikke se apps."""
    try:
        from homeassistant.components.hassio import get_addons_list
        apps = get_addons_list(hass)
    except Exception:  # ikke HA OS, eller Supervisor ikke klar
        return None, None
    for a in apps:
        if a.get("slug") == EMHASS_SLUG or str(a.get("slug", "")).endswith("_emhass"):
            return a.get("state") or "installed", f"http://{a['slug'].replace('_', '-')}:5000"
    return "mangler", None


def _prognose_fejl(hass, entity_id: str) -> str | None:
    s = hass.states.get(entity_id)
    fc = s.attributes.get("forecast") if s else None
    if not isinstance(fc, list) or len(fc) < 8 or not all(isinstance(r, dict) and "datetime" in r and "watts" in r for r in fc[:8]):
        return "prognose_format"
    try:
        t = [datetime.fromisoformat(str(r["datetime"])) for r in fc[:2]]
    except ValueError:
        return "prognose_format"
    return None if (t[1] - t[0]).total_seconds() == 900 else "prognose_kvarter"


class WattlasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Forløbet i Indstillinger → Enheder og tjenester → Tilføj integration → Wattlas."""

    VERSION = 1

    def __init__(self) -> None:
        self.d: dict[str, Any] = {}

    # 1 – styrekanal
    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        pkg = await self.hass.async_add_executor_job(installer.packages_mappe, self.hass.config.config_dir)
        anden = await self.hass.async_add_executor_job(installer.anden_styring, self.hass.config.config_dir, pkg)
        if anden:
            return self.async_abort(reason="anden_styring", description_placeholders={"sti": anden})
        if user_input is not None:
            self.d["kanal"] = user_input["kanal"]
            return await self.async_step_inverter()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("kanal", default="deye"): sel.SelectSelector(sel.SelectSelectorConfig(
                options=["deye", "sunmate"], translation_key="kanal", mode=sel.SelectSelectorMode.LIST))}))

    # 2 – vælg inverteren (og evt. en ekstra inverter uden batteri)
    async def async_step_inverter(self, user_input=None) -> ConfigFlowResult:
        dom, suf = SUFFIX[self.d["kanal"]]
        fejl: dict[str, str] = {}
        if user_input is not None:
            e = user_input["inverter"]
            if not e.endswith(suf):
                fejl["inverter"] = "forkert_entitet"
            inv2 = None
            if user_input.get("inverter2"):
                if self.d["kanal"] != "deye":
                    fejl["inverter2"] = "kun_deye"
                ac = user_input.get("inverter2_tilslutning") == "ac"
                if ac and not user_input.get("inverter2_effekt"):
                    fejl["inverter2_effekt"] = "mangler_effekt"
                eff = user_input.get("inverter2_effekt") or ""
                inv2 = {"navn": user_input.get("inverter2_navn") or "Inverter 2", "ac": ac, "effekt": eff,
                        "relae": user_input.get("inverter2_relae") or "",
                        "prefix": re.sub(r"_(output_ac_power|ac_power|power)$", "", eff.split(".", 1)[-1]) if eff else ""}
            if not fejl:
                self.d["prefix"] = e.split(".", 1)[1][: -len(suf)]
                self.d["inverter2"] = inv2
                return await self.async_step_tjek()
        return self.async_show_form(step_id="inverter", errors=fejl, data_schema=vol.Schema({
            vol.Required("inverter"): sel.EntitySelector(sel.EntitySelectorConfig(domain=dom)),
            vol.Optional("inverter2", default=False): sel.BooleanSelector(),
            vol.Optional("inverter2_navn"): sel.TextSelector(),
            vol.Optional("inverter2_tilslutning", default="gen"): sel.SelectSelector(sel.SelectSelectorConfig(
                options=["gen", "ac"], translation_key="tilslutning", mode=sel.SelectSelectorMode.LIST)),
            vol.Optional("inverter2_effekt"): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", device_class="power")),
            vol.Optional("inverter2_relae"): sel.EntitySelector(sel.EntitySelectorConfig(domain="switch")),
        }), description_placeholders={"suffix": suf})

    # 3 – tjek forudsætninger
    async def async_step_tjek(self, user_input=None) -> ConfigFlowResult:
        hass = self.hass
        blok, adv = [], []
        tilstand, adresse = _emhass(hass)
        self.d["emhass_adresse"] = adresse
        if tilstand == "mangler":
            blok.append(f"❌ **EMHASS-app'en** er ikke installeret – [installér den her]({LINK['emhass']}). Start den bagefter.")
        elif tilstand not in (None, "started"):
            blok.append(f"❌ **EMHASS-app'en** er installeret, men kører ikke – [åbn den]({LINK['emhass']}) og tryk Start.")
        elif tilstand is None:
            adv.append("⚠️ Kan ikke se apps på denne installation – sørg selv for, at EMHASS kører.")
        if hass.states.get("sensor.energi_data_service") is None:
            blok.append(f"❌ **Energi Data Service** (spotpriser) mangler – [installér den]({LINK['energidataservice']}), og opsæt den med priser inkl. moms.")
        if hass.states.get("binary_sensor.workday_sensor") is None:
            blok.append(f"❌ **Workday** (arbejdsdage/helligdage) mangler – [tilføj den]({LINK['workday']}), land Danmark.")
        mangler = [e for e in installer.entiteter_i_kanal(self.d["kanal"], self.d["prefix"])
                   if hass.states.get(e) is None and not e.endswith("_microinverter_power")]
        if mangler:
            vis = ", ".join(f"`{e}`" for e in mangler[:8]) + (f" og {len(mangler) - 8} til" if len(mangler) > 8 else "")
            adv.append(f"⚠️ Inverteren mangler {len(mangler)} entiteter, som Wattlas bruger: {vis}. "
                       "Har din inverter-integration slået nogle fra, så slå dem til. Ellers kan dele af styringen mangle.")
        prognoser = [s.entity_id for s in hass.states.async_all("sensor") if isinstance(s.attributes.get("forecast"), list)]
        if not prognoser:
            adv.append(f"⚠️ Ingen solprognose fundet – [Helios Forecast]({LINK['helios']}) anbefales (se SOLPROGNOSE.md).")
        if not hass.states.async_all("weather"):
            adv.append("⚠️ Ingen vejr-entitet fundet – tilføj fx Met.no.")
        pkg = await hass.async_add_executor_job(installer.packages_mappe, hass.config.config_dir)
        if not pkg:
            tekst = await hass.async_add_executor_job((Path(hass.config.config_dir) / "configuration.yaml").read_text, "utf-8")
            if installer.tilfoej_packages(tekst) is None:
                blok.append("❌ **configuration.yaml** kan ikke rettes automatisk. Tilføj `packages: !include_dir_named packages` "
                            "under `homeassistant:` med File editor, og tryk Tjek igen.")
            else:
                adv.append("ℹ️ Wattlas tilføjer `packages` til configuration.yaml (der tages en kopi af filen først).")
        if user_input is not None and not blok and (not adv or user_input.get("forstaaet")):
            return await self.async_step_forbindelser()
        liste = "\n".join(blok + adv) or "✅ Alt det nødvendige er på plads."
        schema = vol.Schema({vol.Optional("forstaaet", default=False): sel.BooleanSelector()} if adv and not blok else {})
        fejl = {}
        if user_input is not None:
            fejl = {"base": "mangler"} if blok else {"forstaaet": "bekraeft"}
        return self.async_show_form(step_id="tjek", data_schema=schema, errors=fejl, description_placeholders={"liste": liste})

    # 4 – forbindelser og prognoser
    async def async_step_forbindelser(self, user_input=None) -> ConfigFlowResult:
        fejl: dict[str, str] = {}
        if user_input is not None:
            if not re.match(r"https?://", user_input["emhass_adresse"]):
                fejl["emhass_adresse"] = "adresse"
            if len(user_input["emhass_noegle"]) < 8:
                fejl["emhass_noegle"] = "noegle"
            if (f := _prognose_fejl(self.hass, user_input["solprognose"])):
                fejl["solprognose"] = f
            if not fejl:
                self.d.update(user_input)
                return await self.async_step_batteri()
        return self.async_show_form(step_id="forbindelser", errors=fejl, data_schema=vol.Schema({
            vol.Required("emhass_adresse", default=self.d.get("emhass_adresse") or "http://homeassistant.local:5000"): sel.TextSelector(),
            vol.Required("emhass_noegle"): sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.PASSWORD)),
            vol.Required("solprognose"): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor")),
            vol.Required("vejr"): sel.EntitySelector(sel.EntitySelectorConfig(domain="weather")),
            vol.Optional("udetemperatur"): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", device_class="temperature")),
        }))

    def _tal_skema(self, trin: str) -> vol.Schema:
        felter = {}
        for k in TRIN[trin]:
            h = TAL[k]
            trin_ = h.get("step", 1)
            s = sel.NumberSelector(sel.NumberSelectorConfig(min=h.get("min", 0), max=h.get("max", 100000), step="any" if trin_ < 0.001 else trin_,
                                                            unit_of_measurement=h.get("unit_of_measurement"), mode=sel.NumberSelectorMode.BOX))
            felter[vol.Required(k) if k in PAAKRAEVET else vol.Optional(k)] = s
        return vol.Schema(felter)

    async def _tal_trin(self, trin: str, user_input, naeste) -> ConfigFlowResult:
        fejl = {}
        if user_input is not None:
            fejl = {k: "over_nul" for k in TRIN[trin] if k in PAAKRAEVET and not (user_input.get(k) or 0) > 0}
            if not fejl:
                self.d.setdefault("tal", {}).update({k: v for k, v in user_input.items() if v is not None})
                return await naeste()
        return self.async_show_form(step_id=trin, data_schema=self._tal_skema(trin), errors=fejl)

    async def async_step_batteri(self, user_input=None) -> ConfigFlowResult:
        return await self._tal_trin("batteri", user_input, self.async_step_elnet)

    async def async_step_elnet(self, user_input=None) -> ConfigFlowResult:
        return await self._tal_trin("elnet", user_input, self.async_step_priser)

    async def async_step_priser(self, user_input=None) -> ConfigFlowResult:
        return await self._tal_trin("priser", user_input, self.async_step_installer)

    # 5 – installér, tjek konfigurationen, rul tilbage ved fejl
    async def async_step_installer(self, user_input=None) -> ConfigFlowResult:
        hass = self.hass
        try:
            kvit = await hass.async_add_executor_job(installer.installer, hass.config.config_dir, self.d["kanal"],
                                                     self.d["prefix"], self.d.get("inverter2"), VERSION)
        except installer.InstallFejl as e:
            return self.async_abort(reason="install_fejl", description_placeholders={"fejl": str(e)})
        res = await async_check_ha_config_file(hass)
        if res.errors:
            await hass.async_add_executor_job(installer.rul_tilbage, kvit)
            return self.async_abort(reason="install_fejl", description_placeholders={
                "fejl": "Home Assistants konfigurationstjek fejlede, alt er rullet tilbage: " + "; ".join(str(e.message) for e in res.errors[:3])})
        ir.async_create_issue(hass, DOMAIN, "genstart", is_fixable=True, is_persistent=True,
                              severity=ir.IssueSeverity.WARNING, translation_key="genstart")
        data = {k: v for k, v in self.d.items() if k != "emhass_adresse_fundet"}
        data["version"] = VERSION
        return self.async_create_entry(title="Wattlas", data=data)
