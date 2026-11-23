"""Opsætning af Wattlas: tjek forudsætninger, vælg inverter, udfyld indstillinger, installér."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector as sel
from homeassistant.helpers.check_config import async_check_ha_config_file
from homeassistant.loader import async_get_integration

from . import installer
from .const import DOMAIN, EMHASS_SLUG, GENSTART, LINK, NAVN_RE, PAAKRAEVET, STANDARD, TAL, TRIN

VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))["version"]
SUFFIX = {"deye": ("sensor", "_pv_power"), "sunmate": ("number", "_timepoint_1_power"), "huawei": ("sensor", "_input_power"),
          "growatt": ("sensor", "_battery_soc"),
          "deye_esphome": ("sensor", "_pv1_power")}
# Huawei (LUNA2000) og Growatt (ARK/APX) er højvoltbatterier; kernen regner i A ved et lavvoltbatteri. Kanalerne bruger derfor
# en fast beregningsspænding, og A-indstillingerne udregnes fra W. Samme tal står i styrekanalerne (styrekanaler/huawei, growatt).
HUAWEI_V = 50
HOEJVOLT = ("huawei", "huawei_emma", "growatt")
A_FRA_W = {"maks_ladestroem_a": "maks_ladeeffekt_w", "maks_afladestroem_a": "maks_afladeeffekt_w",
           "maks_netladestroem_a": "maks_netladeeffekt_w"}


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


def _database(hass) -> str | None:
    """Recorderens databasetype ("sqlite", "mysql", "postgresql"), eller None hvis den ikke kendes."""
    try:
        from homeassistant.components.recorder import get_instance
        return str(get_instance(hass).dialect_name or "") or None
    except Exception:  # recorderen er ikke sat op (endnu) eller slået fra
        return None


def _platform_entitet(hass, domæne: str, platform: str) -> str | None:
    """Første entitet i domænet fra integrationen `platform`, fx Workday's binary_sensor."""
    for e in er.async_get(hass).entities.values():
        if e.domain == domæne and e.platform == platform and not e.disabled:
            s = hass.states.get(e.entity_id)
            if platform != "energidataservice" or (s and "raw_today" in s.attributes):
                return e.entity_id
    return None


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
        # Opdateret uden genstart: HA kører den nye kode med de gamle tekster (rå feltnavne på skærmen). Teksten her er derfor
        # en, der også fandtes i den gamle version.
        if str((await async_get_integration(self.hass, DOMAIN)).version) != VERSION:
            return self.async_abort(reason="install_fejl", description_placeholders={
                "fejl": f"Wattlas er lige blevet opdateret til {VERSION}. Genstart Home Assistant, og sæt Wattlas op bagefter."})
        if user_input is not None:
            self.d["kanal"] = user_input["kanal"]
            return await self.async_step_inverter()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("kanal", default="deye"): sel.SelectSelector(sel.SelectSelectorConfig(
                options=["deye", "deye_esphome", "sunmate", "huawei", "growatt"], translation_key="kanal", mode=sel.SelectSelectorMode.LIST))}))

    # 2 – vælg inverteren (de fleste har kun én)
    async def async_step_inverter(self, user_input=None) -> ConfigFlowResult:
        dom, suf = SUFFIX[self.d["kanal"]]
        fejl: dict[str, str] = {}
        if user_input is not None:
            e = user_input["inverter"]
            if not e.endswith(suf):
                fejl["inverter"] = "forkert_entitet"
            elif user_input.get("inverter2") and self.d["kanal"] != "deye":
                fejl["inverter2"] = "kun_deye"
            else:
                self.d["prefix"] = e.split(".", 1)[1][: -len(suf)]
                self.d["inverter2"] = None
                if self.d["kanal"] == "huawei":
                    return await self.async_step_huawei()
                return await (self.async_step_inverter2() if user_input.get("inverter2") else self.async_step_tjek())
        return self.async_show_form(step_id="inverter", errors=fejl, data_schema=vol.Schema({
            vol.Required("inverter"): sel.EntitySelector(sel.EntitySelectorConfig(domain=dom)),
            vol.Optional("inverter2", default=False): sel.BooleanSelector(),
        }), description_placeholders={"suffix": suf})

    # 2a – kun Huawei: batteriet og elmåleren er egne enheder i Huawei Solar-integrationen. Elmåleren sidder enten på
    # inverteren ("Power meter", vælg dens Active power) eller på en EMMA (vælg EMMA's Feed in power – den er slået til som
    # standard; målerens fasetal er det ikke, dem melder tjekket bagefter). En ekstern måler på EMMA hedder som den
    # indbyggede + "_2", som Wattlas så bruger på alle målerens sensorer.
    async def async_step_huawei(self, user_input=None) -> ConfigFlowResult:
        fejl: dict[str, str] = {}
        if user_input is not None:
            bat, maaler, emma = user_input["batteri"], user_input["maaler"], user_input.get("elmaaler") == "emma"
            mb = re.fullmatch(r"sensor\.([a-z0-9_]+)_state_of_capacity", bat)
            mm = re.fullmatch(r"sensor\.([a-z0-9_]+)_feed_in_power" if emma else r"sensor\.([a-z0-9_]+)_active_power", maaler)
            if not mb:
                fejl["batteri"] = "forkert_entitet"
            if not mm:
                fejl["maaler"] = "forkert_emma" if emma else "forkert_maaler"
            if not fejl:
                self.d["ekstra"] = {"min_luna": mb.group(1), "min_hmaaler": mm.group(1)}
                if emma:
                    self.d["kanal"] = "huawei_emma"
                    self.d["ekstra"]["min_emma"] = mm.group(1)
                    if user_input.get("ekstern_maaler"):
                        self.d["ekstra"]["min_hmaaler"] += "|_2"
                return await self.async_step_tjek()
        har = lambda e: (s := self.hass.states.get(e)) is not None and s.state not in ("unknown", "unavailable")  # noqa: E731
        std_emma = not har("sensor.power_meter_active_power") and har("sensor.emma_feed_in_power")
        std = {"batteri": "sensor.batteries_state_of_capacity",
               "maaler": "sensor.emma_feed_in_power" if std_emma else "sensor.power_meter_active_power"}
        skema = {vol.Required("elmaaler", default="emma" if std_emma else "huawei"): sel.SelectSelector(sel.SelectSelectorConfig(
            options=["huawei", "emma"], translation_key="elmaaler", mode=sel.SelectSelectorMode.LIST))}
        for felt in ("batteri", "maaler"):
            skema[vol.Required(felt, **({"default": std[felt]} if self.hass.states.get(std[felt]) else {}))] = sel.EntitySelector(
                sel.EntitySelectorConfig(domain="sensor"))
        skema[vol.Optional("ekstern_maaler", default=False)] = sel.BooleanSelector()
        return self.async_show_form(step_id="huawei", errors=fejl, data_schema=vol.Schema(skema))

    # 2b – kun hvis der også er en inverter uden batteri
    async def async_step_inverter2(self, user_input=None) -> ConfigFlowResult:
        fejl: dict[str, str] = {}
        if user_input is not None:
            ac = user_input.get("inverter2_tilslutning") == "ac"
            eff = user_input.get("inverter2_effekt") or ""
            if ac and not eff:
                fejl["inverter2_effekt"] = "mangler_effekt"
            elif not re.fullmatch(NAVN_RE, user_input.get("inverter2_navn") or ""):
                fejl["inverter2_navn"] = "navn_tegn"
            else:
                self.d["inverter2"] = {"navn": user_input.get("inverter2_navn") or "Inverter 2", "ac": ac, "effekt": eff,
                                       "relae": user_input.get("inverter2_relae") or "",
                                       "prefix": re.sub(r"_(output_ac_power|ac_power|power)$", "", eff.split(".", 1)[-1]) if eff else ""}
                return await self.async_step_tjek()
        return self.async_show_form(step_id="inverter2", errors=fejl, data_schema=vol.Schema({
            vol.Optional("inverter2_navn"): sel.TextSelector(),
            vol.Required("inverter2_tilslutning", default="gen"): sel.SelectSelector(sel.SelectSelectorConfig(
                options=["gen", "ac"], translation_key="tilslutning", mode=sel.SelectSelectorMode.LIST)),
            vol.Optional("inverter2_effekt"): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", device_class="power")),
            vol.Optional("inverter2_relae"): sel.EntitySelector(sel.EntitySelectorConfig(domain="switch")),
        }))

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
        info = []
        self.d["omdoeb"] = {}
        for ønsket, platform, navn, link, hjælp in [
                ("sensor.energi_data_service", "energidataservice", "Energi Data Service", None, "Indstillinger → Markedsplads → søg *Energi Data Service* → Installér, genstart og tilføj den med priser inkl. moms."),
                ("binary_sensor.workday_sensor", "workday", "Workday", LINK["workday"], "vælg Danmark.")]:
            if hass.states.get(ønsket) is not None:
                continue
            fundet = _platform_entitet(hass, ønsket.split(".")[0], platform)
            if fundet:  # findes under et andet navn (fx binary_sensor.workday_sensor_dk) – Wattlas giver den det navn, pakkerne bruger
                self.d["omdoeb"][fundet] = ønsket
                info.append(f"ℹ️ **{navn}** findes som `{fundet}` – Wattlas omdøber den til `{ønsket}`. "
                            "Bruger dine egne automationer det gamle navn, så ret dem bagefter.")
            else:
                blok.append(f"❌ **{navn}** mangler – " + (f"[tilføj den]({link}), {hjælp}" if link else hjælp))
        alle = await hass.async_add_executor_job(installer.entiteter_i_kanal, self.d["kanal"], self.d["prefix"], self.d.get("ekstra"))
        mangler = [e for e in alle if hass.states.get(e) is None and not e.endswith("_microinverter_power")]
        if mangler:
            vis = ", ".join(f"`{e}`" for e in mangler[:8]) + (f" og {len(mangler) - 8} til" if len(mangler) > 8 else "")
            adv.append(f"⚠️ Inverteren mangler {len(mangler)} entiteter, som Wattlas bruger: {vis}. "
                       "Har din inverter-integration slået nogle fra, så slå dem til. Ellers kan dele af styringen mangle.")
        prognoser = [s.entity_id for s in hass.states.async_all("sensor") if isinstance(s.attributes.get("forecast"), list)]
        if not prognoser:
            adv.append("⚠️ Ingen solprognose fundet – *Helios Forecast* fra Markedspladsen anbefales (se SOLPROGNOSE.md).")
        if not hass.states.async_all("weather"):
            adv.append("⚠️ Ingen vejr-entitet fundet – tilføj fx Met.no.")
        if _database(hass) not in (None, "sqlite"):
            adv.append("⚠️ Home Assistant bruger ikke standarddatabasen (SQLite). Husprognosen og appens daghistorik henter data med "
                       "SQL, der kun virker med SQLite – de dele mangler. Resten af Wattlas virker.")
        pkg = await hass.async_add_executor_job(installer.packages_mappe, hass.config.config_dir)
        if not pkg:
            tekst = await hass.async_add_executor_job((Path(hass.config.config_dir) / "configuration.yaml").read_text, "utf-8")
            if installer.tilfoej_packages(tekst) is None:
                blok.append("❌ **configuration.yaml** kan ikke rettes automatisk. Tilføj `packages: !include_dir_named packages` "
                            "under `homeassistant:` med File editor, og tryk Tjek igen.")
            else:
                info.append("ℹ️ Wattlas tilføjer `packages` til configuration.yaml (der tages en kopi af filen først).")
        if user_input is not None and not blok and (not adv or user_input.get("forstaaet")):
            return await self.async_step_forbindelser()
        if blok or adv:
            liste = "\n\n".join(blok + adv + info)
            if blok:
                liste += "\n\nNår alt med ❌ er klaret, så tryk **Send** for at tjekke igen."
        else:
            liste = "✅ Alt det nødvendige er på plads.\n\n" + "\n\n".join(info)
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

    def _felter(self, trin: str) -> list[str]:
        """Indstillingerne i trinnet. Huawei: A-grænserne udregnes fra W (se HUAWEI_V) og spørges ikke om."""
        return [k for k in TRIN[trin] if not (self.d.get("kanal") in HOEJVOLT and k in A_FRA_W)]

    def _tal_skema(self, trin: str) -> vol.Schema:
        felter = {}
        for k in self._felter(trin):
            h = TAL[k]
            trin_ = h.get("step", 1)
            s = sel.NumberSelector(sel.NumberSelectorConfig(min=h.get("min", 0), max=h.get("max", 100000), step="any" if trin_ < 0.001 else trin_,
                                                            unit_of_measurement=h.get("unit_of_measurement"), mode=sel.NumberSelectorMode.BOX))
            felter[vol.Required(k) if k in PAAKRAEVET else vol.Optional(k, **({"default": STANDARD[k]} if k in STANDARD else {}))] = s
        return vol.Schema(felter)

    async def _tal_trin(self, trin: str, user_input, naeste) -> ConfigFlowResult:
        fejl = {}
        if user_input is not None:
            fejl = {k: "over_nul" for k in self._felter(trin) if k in PAAKRAEVET and not (user_input.get(k) or 0) > 0}
            if not fejl:
                tal = self.d.setdefault("tal", {})
                tal.update({k: v for k, v in user_input.items() if v is not None})
                if self.d.get("kanal") in HOEJVOLT:
                    tal.update({a: round(tal[w] / HUAWEI_V) for a, w in A_FRA_W.items() if (tal.get(w) or 0) > 0})
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
        omdoeb = self.d.pop("omdoeb", None) or {}
        try:
            kvit = await hass.async_add_executor_job(installer.installer, hass.config.config_dir, self.d["kanal"],
                                                     self.d["prefix"], self.d.get("inverter2"), VERSION, self.d.get("ekstra"))
        except installer.InstallFejl as e:
            return self.async_abort(reason="install_fejl", description_placeholders={"fejl": str(e)})
        res = await async_check_ha_config_file(hass)
        if res.errors:
            await hass.async_add_executor_job(installer.rul_tilbage, kvit)
            return self.async_abort(reason="install_fejl", description_placeholders={
                "fejl": "Home Assistants konfigurationstjek fejlede, alt er rullet tilbage: " + "; ".join(str(e.message) for e in res.errors[:3])})
        reg = er.async_get(hass)
        for gammel, ny in omdoeb.items():
            if reg.async_get(gammel) and not reg.async_get(ny):
                reg.async_update_entity(gammel, new_entity_id=ny)
        hass.data[GENSTART] = True
        ir.async_create_issue(hass, DOMAIN, "genstart", is_fixable=True, is_persistent=True,
                              severity=ir.IssueSeverity.WARNING, translation_key="genstart")
        data = {k: v for k, v in self.d.items() if k != "emhass_adresse_fundet"}
        data["version"] = VERSION
        return self.async_create_entry(title="Wattlas", data=data)
