"""Opsætning af Wattlas: tjek forudsætninger, vælg inverter, udfyld indstillinger, installér."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector as sel
from homeassistant.helpers.check_config import async_check_ha_config_file
from homeassistant.loader import async_get_integration

from . import installer, lader, lader_find, tariffer
from .const import DOMAIN, EMHASS_SLUG, GAMLE, GENSTART, LINK, NAVN_RE, PAAKRAEVET, STANDARD, TAL, TEKST, TRIN

VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))["version"]
SUFFIX = {"deye": ("sensor", "_pv_power"), "sunmate": ("number", "_timepoint_1_power"), "huawei": ("sensor", "_input_power"),
          "growatt": ("sensor", "_battery_soc"), "solax": ("sensor", "_battery_capacity"), "sofar": ("sensor", "_battery_capacity_total"),
          "solis": ("sensor", "_remote_dispatch_function_version"),
          "deye_esphome": ("sensor", "_pv1_power"), "deye_parallel": ("sensor", "_pv_power")}
# Huawei (LUNA2000) og Growatt (ARK/APX) er højvoltbatterier; kernen regner i A ved et lavvoltbatteri. Kanalerne bruger derfor
# en fast beregningsspænding, og A-indstillingerne udregnes fra W. Samme tal står i styrekanalerne (styrekanaler/huawei, growatt).
HUAWEI_V = 50
# kanaler, der selv laver inverterens entiteter (findes først efter installationen, ingen inverter-entitet at vælge)
EGNE = ("sonnen", "spf")
HOEJVOLT = ("huawei", "huawei_emma", "growatt", "solax", "sofar", "solis")
SA_VENT_S = 30  # så længe ventes der på Solar Assistants emner
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


def priser_fejl(hass, entity_id: str = "sensor.energi_data_service") -> bool:
    """Energi Data Service giver noget andet end ren spotpris i kr./kWh: så ville Wattlas lægge tarifferne på to gange og regne forkert salgspris."""
    s = hass.states.get(entity_id)
    return s is not None and bool(s.attributes.get("tariffs") or s.attributes.get("use_cent") or s.attributes.get("unit", "kWh") != "kWh")


# kendte ladere: integrationens navn i Home Assistant → navn. Kun for at foreslå laderens effekt-sensor; alle andre vælges selv
LADERE = {**lader_find.MAERKER, "keba": "Keba", "tesla_wall_connector": "Tesla Wall Connector", "besen": "Besen"}
ELBIL, ELBIL_HOLD = "input_text.wattlas_elbil_entitet", "input_boolean.wattlas_elbil_hold"
LADER_FEJL = {"maalinger": "Wattlas kan ikke se husets faser lige nu. Prøv igen, når Wattlas har friske målinger.",
              "plads": "Der er for lidt plads på faserne til en sikker prøve. Prøv igen, når der bruges mindre strøm (fx når varmepumpen holder pause, og batteriet ikke lader).",
              "frakoblet": "Laderen melder, at bilen ikke er tilsluttet. Sæt stikket i bilen, og prøv igen.",
              "effekt": "Laderens effekt kan ikke læses lige nu.", "effekt_ingen": "Laderen melder ikke sin effekt, mens den lader, så Wattlas kan ikke se, om den adlyder. Bruger du OCPP: genindlæs integrationen, eller vælg målingerne selv (Power.Active.Import).",
              "lader_allerede": "Bilen lader allerede. Stop den i laderens app, og prøv igen."}
LADER_TILSTAND, LADER_MAKS, LADER_MAAL = "input_select.wattlas_lader_tilstand", "input_number.wattlas_lader_maks_a", "input_number.wattlas_lader_maal"
LADER_SOL = "input_number.wattlas_lader_sol_maal"


def _fundne_ladere(hass) -> list[tuple[str, str]]:
    """(entitet, navn) for kendte laderes samlede effekt."""
    fundet = []
    for e in er.async_get(hass).entities.values():
        if e.domain == "sensor" and e.platform in LADERE and not e.disabled and (s := hass.states.get(e.entity_id)) is not None:
            if s.attributes.get("device_class") == "power" and not re.search(r"phase|fase|_l[123]\b|import|export|equali[sz]er|offered", f"{e.entity_id} {e.unique_id}"):
                fundet.append((e.entity_id, f"{LADERE[e.platform]}: {s.attributes.get('friendly_name') or e.entity_id} (`{e.entity_id}`)"))
    return sorted(fundet)


def _elbil_fejl(hass, entity_id: str, d) -> bool:
    """Kan sensoren ikke bruges som laderens effekt? Husets forbrug (Wattlas' egne, EMHASS' prognoser og inverterens) ville holde batteriet hele tiden."""
    s = hass.states.get(entity_id)
    prefixer = tuple(f"sensor.{p.partition('|')[0]}_" for p in (d.get("prefix"), *(d.get("ekstra") or {}).values()) if p)
    if entity_id.startswith(("sensor.wattlas_", "sensor.emhass_", "sensor.p_", "sensor.hh_", *prefixer)):
        return True
    reg = er.async_get(hass)
    e = reg.async_get(entity_id)
    if e and e.device_id and any(x.device_id == e.device_id for x in reg.entities.values() if x.entity_id.startswith(prefixer)):
        return True  # inverterens egen sensor, omdøbt
    if s is None or s.attributes.get("unit_of_measurement") not in ("W", "kW"):
        return True
    try:
        float(s.state)
    except ValueError:
        return s.state not in ("unknown", "unavailable")  # laderen er offline lige nu
    return False


def _platform_entitet(hass, domæne: str, platform: str) -> str | None:
    """Første entitet i domænet fra integrationen `platform`, fx Workday's binary_sensor."""
    for e in er.async_get(hass).entities.values():
        if e.domain == domæne and e.platform == platform and not e.disabled:
            s = hass.states.get(e.entity_id)
            if platform != "energidataservice" or (s and "raw_today" in s.attributes):
                return e.entity_id
    return None


def _faktor_med_moms(pris: str) -> bool:
    """Indeholder Nordpool-faktoren de 25 % moms, Wattlas selv lagde på? (så står fluebenet, når Konfigurer åbnes igen)"""
    try:
        f = float(pris.split("|")[1])
    except (IndexError, ValueError):
        return False
    return any(abs(f - e * c * 1.25) < 1e-9 * max(1, f) for e in NORDPOOL_ENHED.values() for c in (1, 0.01))


def _nordpool(hass) -> str | None:
    """Første Nordpool-sensor (HACS), hvis Energi Data Service ikke findes – så er den foreslået i opsætningen."""
    if hass.states.get("sensor.energi_data_service") is not None:
        return None
    return next((e.entity_id for e in er.async_get(hass).entities.values() if e.platform == "nordpool" and e.domain == "sensor" and not e.disabled), None)


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


SOLCAST = "sensor.wattlas_solprognose_solcast"
NORDPOOL_ENHED = {"kWh": 1, "MWh": 0.001, "Wh": 1000}


def _kilde_filter(hass, slags: str, valgt: str | None = None) -> dict:
    """Kun sensorer, der kan bruges som solprognose (Helios' forecast, Solcasts detailedForecast) eller spotpris (raw_today), plus det valgte.
    Findes ingen, vises alle sensorer som før – så ingen låses ude."""
    nøgler = ("forecast", "detailedForecast") if slags == "sol" else ("raw_today",)
    ok = {s.entity_id for s in hass.states.async_all("sensor")
          if not s.entity_id.startswith("sensor.wattlas_") and any(isinstance(s.attributes.get(k), list) for k in nøgler)}
    if ok and valgt and hass.states.get(valgt) is not None:
        ok.add(valgt)
    return {"include_entities": sorted(ok)} if ok else {}


def _kilder(hass, ui: dict) -> dict[str, str]:
    """Priser og solprognose fra andre kilder (Nordpool, Solcast) oversættes til det, resten af Wattlas læser. Retter ui; giver fejlene."""
    fejl: dict[str, str] = {}
    ui["pris"] = ""
    if p := ui.get("priser"):
        s = hass.states.get(p)
        r = (s.attributes.get("raw_today") or [None])[0] if s else None
        if not isinstance(r, dict):
            fejl["priser"] = "priser_format"
        elif "value" in r and "start" in r:  # Nordpool (HACS): priser i den valgte enhed, evt. i øre og uden moms
            enhed = NORDPOOL_ENHED.get(str(s.attributes.get("unit") or "kWh"))
            try:
                tillaeg = float(s.attributes.get("additional_costs_current_hour") or 0)
            except (TypeError, ValueError):
                tillaeg = 1.0
            if enhed is None or s.attributes.get("currency") not in (None, "DKK"):  # euro læst som kroner ville give 7,5 gange for lave priser
                fejl["priser"] = "priser_format"
            elif tillaeg:  # tariffer lagt på i Nordpool: Wattlas lægger dem selv på og ville tælle dem to gange
                fejl["priser"] = "priser_tillaeg"
            else:
                f = enhed * (0.01 if s.attributes.get("price_in_cents") else 1) * (1.25 if ui.get("priser_uden_moms") else 1)
                ui["pris"] = f"{p}|{f:g}"
        elif "hour" in r and "price" in r:
            if priser_fejl(hass, p):
                fejl["priser"] = "priser_tillaeg"
            ui["pris"] = p
        else:
            fejl["priser"] = "priser_format"
    ui["solcast"] = ""
    e = ui.get("solprognose") or ""
    s = hass.states.get(e)
    if s is not None and isinstance(s.attributes.get("detailedForecast"), list):
        d = s.attributes["detailedForecast"]
        try:
            ok = len(d) >= 4 and all(isinstance(x, dict) and "pv_estimate" in x for x in d[:4]) and \
                (datetime.fromisoformat(str(d[1]["period_start"])) - datetime.fromisoformat(str(d[0]["period_start"]))).total_seconds() == 1800
        except (KeyError, ValueError, TypeError):
            ok = False
        if not ok:
            fejl["solprognose"] = "prognose_format"
        else:  # i dag, i morgen og dag 3 fra samme Solcast-opsætning
            reg = er.async_get(hass)
            me = reg.async_get(e)
            dage = {x.translation_key: x.entity_id for x in reg.entities.values() if me and x.config_entry_id == me.config_entry_id and x.domain == "sensor"}
            # Solcasts egne nøgler (BJReplay/ha-solcast-solar); i dag først, også hvis brugeren valgte i morgen
            ui["solcast"] = ",".join(dict.fromkeys(x for x in (dage.get("total_kwh_forecast_today", e), dage.get("total_kwh_forecast_tomorrow"), dage.get("total_kwh_forecast_d3")) if x))
            ui["solprognose"] = SOLCAST
    elif e == SOLCAST:  # Wattlas' egen Solcast-sensor: de valgte dage beholdes
        ui["solcast"] = getattr(hass.states.get("input_text.wattlas_solcast_entiteter"), "state", "")
        if ui["solcast"] in ("", "unknown", "unavailable"):
            fejl["solprognose"] = "prognose_format"
    elif (f := _prognose_fejl(hass, e)):
        fejl["solprognose"] = f
    return fejl


def _forbindelse_fejl(hass, ui: dict, kraev_noegle: bool) -> dict[str, str]:
    fejl = _kilder(hass, ui)
    if not re.match(r"https?://", ui.get("emhass_adresse") or ""):
        fejl["emhass_adresse"] = "adresse"
    noegle = ui.get("emhass_noegle") or ""
    if (kraev_noegle or noegle) and (len(noegle) < 8 or not noegle.isprintable()):  # linjeskift mv. kan ikke stå i en HTTP-header
        fejl["emhass_noegle"] = "noegle"
    return fejl


def _tal_felter(d, trin: str) -> list[str]:
    """Indstillingerne i trinnet. Højvolt: A-grænserne udregnes fra W (se HUAWEI_V) og spørges ikke om – det gør hentede tariffer heller ikke."""
    return [k for k in TRIN[trin] if not (d.get("kanal") in HOEJVOLT and k in A_FRA_W) and not (d.get("netselskab") and k in tariffer.FELTER)]


def _pris_tekst(d, tal: dict) -> dict[str, str]:
    if not (gln := d.get("netselskab")):
        return {"tariffer": "Tallene står på din elregning eller netselskabets hjemmeside. Sommer- og vintertarif retter du selv senere."}
    return {"tariffer": f"Nettarif, elafgift og Energinets tariffer hentes hver dag fra Energinet ({tariffer.SELSKABER.get(gln, (gln,))[0]}). "
                        f"Lige nu {tariffer.vis({k: tal.get(k) or 0.0 for k in tariffer.FELTER})}."}


def _netselskab_skema(valgt: str | None) -> vol.Schema:
    valg = [sel.SelectOptionDict(value=tariffer.MANUEL, label="Jeg taster selv tallene"),
            *(sel.SelectOptionDict(value=g, label=s[0]) for g, s in tariffer.SELSKABER.items())]
    return vol.Schema({vol.Required("netselskab", default=valgt if valgt in tariffer.SELSKABER else tariffer.MANUEL):
                       sel.SelectSelector(sel.SelectSelectorConfig(options=valg, mode=sel.SelectSelectorMode.DROPDOWN))})


def _tal_skema(felter: list[str], std: dict) -> vol.Schema:
    skema = {}
    for k in felter:
        h = TAL[k]
        trin_ = h.get("step", 1)
        s = sel.NumberSelector(sel.NumberSelectorConfig(min=h.get("min", 0), max=h.get("max", 100000), step="any" if trin_ < 0.001 else trin_,
                                                        unit_of_measurement=h.get("unit_of_measurement"), mode=sel.NumberSelectorMode.BOX))
        d = {"default": std[k]} if std.get(k) is not None else {}
        skema[vol.Required(k, **d) if k in PAAKRAEVET else vol.Optional(k, **d)] = s
    return vol.Schema(skema)


def _tal_fejl(felter: list[str], ui: dict) -> dict[str, str]:
    fejl = {k: "over_nul" for k in felter if k in PAAKRAEVET and not (ui.get(k) or 0) > 0}
    if 0 < (ui.get("sikring_a") or 0) < (ui.get("fase_graense_a") or 0):
        fejl["sikring_a"] = "sikring_lav"
    return fejl


def _med_a(kanal, tal: dict) -> dict:
    """Højvolt: A-grænserne følger W-indstillingerne (W ÷ HUAWEI_V)."""
    if kanal in HOEJVOLT:
        tal = {**tal, **{a: round(tal[w] / HUAWEI_V) for a, w in A_FRA_W.items() if (tal.get(w) or 0) > 0}}
    return tal


async def _sa_svarer(hass) -> str | None:
    """Kommer Solar Assistants emner over MQTT? None = ja, ellers fejlkoden (venter højst SA_VENT_S)."""
    if not hass.services.has_service("mqtt", "publish"):
        return "mqtt_mangler"
    from homeassistant.components import mqtt
    set_ = {e: asyncio.Event() for e in ("total/battery_state_of_charge", "inverter_1/output_source_priority")}
    af = []
    try:
        for emne, e in set_.items():
            @callback  # i HA's egen tråd: asyncio.Event må ikke sættes fra en anden
            def kom(_besked, e=e) -> None:
                e.set()
            af.append(await mqtt.async_subscribe(hass, f"solar_assistant/{emne}/state", kom))
        async with asyncio.timeout(SA_VENT_S):
            await asyncio.gather(*(e.wait() for e in set_.values()))
    except (TimeoutError, HomeAssistantError):
        return "sa_svarer_ikke"
    finally:
        for a in af:
            a()
    return None


async def _sonnen_svarer(hass, host: str, token: str) -> str | None:
    """Læser batteriets status med tokenet. None = svarer; ellers en fejlkode."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    try:
        async with async_get_clientsession(hass).get(f"{host}/api/v2/status", headers={"Auth-Token": token},
                                                     timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status in (401, 403):
                return "sonnen_afvist"
            data = await r.json(content_type=None) if r.status == 200 else None
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return "sonnen_svarer_ikke"
    return None if isinstance(data, dict) and "USOC" in data else "sonnen_svarer_ikke"


async def _sonnen_fejl(hass, host: str, token: str) -> dict[str, str]:
    """Fejl ved Sonnen-batteriets adresse og token (tegn, der må stå i YAML, og at batteriet svarer)."""
    if not installer.SONNEN_HOST_RE.fullmatch(host):
        return {"sonnen_host": "sonnen_adresse"}
    if not installer.SONNEN_TOKEN_RE.fullmatch(token):
        return {"sonnen_token": "sonnen_token"}
    f = await _sonnen_svarer(hass, host, token)
    return {"base": f} if f else {}


def _inverter2(u: dict, hovedprefix: str) -> tuple[dict | None, dict[str, str]]:
    """Inverter 2 fra formularen (opsætning og Konfigurer). Teknik finder dens målinger ud fra navnet på en af dens egne sensorer:
    den valgte (inverter2_egen), ellers effekt-sensoren – men ikke, hvis den hører til hovedinverteren (fx Deyes GEN-port-måling)."""
    ac = u.get("inverter2_tilslutning") == "ac"
    eff, egen = u.get("inverter2_effekt") or "", u.get("inverter2_egen") or ""
    if ac and not eff:
        return None, {"inverter2_effekt": "mangler_effekt"}
    if not re.fullmatch(NAVN_RE, u.get("inverter2_navn") or ""):
        return None, {"inverter2_navn": "navn_tegn"}
    kilde = egen or ("" if eff.startswith(f"sensor.{hovedprefix}_") else eff)
    return {"navn": u.get("inverter2_navn") or "Inverter 2", "ac": ac, "effekt": eff, "relae": u.get("inverter2_relae") or "", "egen": egen,
            "prefix": re.sub(r"_(output_ac_power|ac_power|power)$", "", kilde.split(".", 1)[-1]) if kilde else ""}, {}


def _inverter2_skema(g: dict) -> vol.Schema:
    """g: den gemte inverter 2 (tom ved opsætning). Valgfrie entiteter som forslag, så de kan ryddes igen."""
    forslag = lambda v: {"suggested_value": v} if v else {}  # noqa: E731
    return vol.Schema({
        vol.Optional("inverter2_navn", description=forslag(g.get("navn"))): sel.TextSelector(),
        vol.Required("inverter2_tilslutning", default="ac" if g.get("ac") else "gen"): sel.SelectSelector(sel.SelectSelectorConfig(
            options=["gen", "ac"], translation_key="tilslutning", mode=sel.SelectSelectorMode.LIST)),
        vol.Optional("inverter2_effekt", description=forslag(g.get("effekt"))): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", device_class="power")),
        vol.Optional("inverter2_egen", description=forslag(g.get("egen"))): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor")),
        vol.Optional("inverter2_relae", description=forslag(g.get("relae"))): sel.EntitySelector(sel.EntitySelectorConfig(domain="switch")),
    })


async def _laeg_filer(hass, d: dict) -> str | None:
    """Lægger Wattlas' filer på plads for opsætningen d og tjekker konfigurationen (rulles tilbage ved fejl).
    Returnerer en fejltekst – eller None: filerne ligger der, og Home Assistant skal genstartes (reparationen oprettes)."""
    try:
        kvit = await hass.async_add_executor_job(installer.opdater, hass.config.config_dir, dict(d), VERSION)
    except installer.InstallFejl as e:
        return str(e)
    res = await async_check_ha_config_file(hass)
    if res.errors:
        await hass.async_add_executor_job(installer.rul_tilbage, kvit)
        return "Home Assistants konfigurationstjek fejlede, alt er rullet tilbage: " + "; ".join(str(e.message) for e in res.errors[:3])
    await hass.async_add_executor_job(installer.skjul_token, kvit["backup"])
    hass.data[GENSTART] = True
    ir.async_create_issue(hass, DOMAIN, "genstart", is_fixable=True, is_persistent=True,
                          severity=ir.IssueSeverity.WARNING, translation_key="genstart")
    return None


class WattlasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Forløbet i Indstillinger → Enheder og tjenester → Tilføj integration → Wattlas."""

    VERSION = 1

    def __init__(self) -> None:
        self.d: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return WattlasOptionsFlow()

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
            if self.d["kanal"] in EGNE:
                return await getattr(self, f"async_step_{self.d['kanal']}")()
            return await self.async_step_inverter()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("kanal", default="deye"): sel.SelectSelector(sel.SelectSelectorConfig(
                options=["deye", "deye_parallel", "deye_esphome", "sunmate", "huawei", "growatt", "solax", "sofar", "solis", "spf", "sonnen"], translation_key="kanal", mode=sel.SelectSelectorMode.LIST))}))

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
                if self.d["kanal"] == "deye_parallel":
                    return await self.async_step_slave()
                return await (self.async_step_inverter2() if user_input.get("inverter2") else self.async_step_tjek())
        return self.async_show_form(step_id="inverter", errors=fejl, data_schema=vol.Schema({
            vol.Required("inverter"): sel.EntitySelector(sel.EntitySelectorConfig(domain=dom)),
            vol.Optional("inverter2", default=False): sel.BooleanSelector(),
        }), description_placeholders={"suffix": suf})

    # 2 (Sonnen) – batteriet har ingen HA-integration: kanalen læser og styrer det selv via det lokale API v2 (fw 1.40+)
    async def async_step_sonnen(self, user_input=None) -> ConfigFlowResult:
        fejl: dict[str, str] = {}
        if user_input is not None:
            host = user_input["sonnen_host"].strip().rstrip("/")
            token = user_input["sonnen_token"].strip()
            fejl = await _sonnen_fejl(self.hass, host, token)
            if not fejl:
                self.d.update(prefix="min_sonnen", inverter2=None, sonnen={"host": host, "token": token})
                return await self.async_step_tjek()
        return self.async_show_form(step_id="sonnen", errors=fejl, data_schema=vol.Schema({
            vol.Required("sonnen_host", default=(user_input or {}).get("sonnen_host", "http://")): sel.TextSelector(),
            vol.Required("sonnen_token"): sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.PASSWORD))}))

    # 2 (SPF) – kanalen laver selv sensorerne af Solar Assistants MQTT-emner; her tjekkes kun, at emnerne kommer
    async def async_step_spf(self, user_input=None) -> ConfigFlowResult:
        fejl: dict[str, str] = {}
        if user_input is not None:
            if f := await _sa_svarer(self.hass):
                fejl["base"] = f
            else:
                self.d.update(prefix="min_spf", inverter2=None)
                return await self.async_step_tjek()
        return self.async_show_form(step_id="spf", errors=fejl, data_schema=vol.Schema({}))

    # 2a – kun Deye i parallel: slaven er sin egen enhed i ha-solarman (sin egen logger); masteren er den, CT'erne sidder på
    async def async_step_slave(self, user_input=None) -> ConfigFlowResult:
        fejl: dict[str, str] = {}
        if user_input is not None:
            e = user_input["slave"]
            prefix = e.split(".", 1)[1][: -len("_pv_power")] if e.endswith("_pv_power") else ""
            if not prefix:
                fejl["slave"] = "forkert_entitet"
            elif prefix == self.d["prefix"]:
                fejl["slave"] = "samme_inverter"
            else:
                self.d["ekstra"] = {"min_slave": prefix}
                return await self.async_step_tjek()
        return self.async_show_form(step_id="slave", errors=fejl, data_schema=vol.Schema({
            vol.Required("slave"): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor"))}))

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
            inv2, fejl = _inverter2(user_input, self.d["prefix"])
            if inv2:
                self.d["inverter2"] = inv2
                return await self.async_step_tjek()
        return self.async_show_form(step_id="inverter2", errors=fejl, data_schema=_inverter2_skema({}))

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
                ("sensor.energi_data_service", "energidataservice", "Energi Data Service", None, "Indstillinger → Markedsplads → søg *Energi Data Service* (eller *Nordpool*) → Installér, genstart og tilføj den med priser inkl. moms."),
                ("binary_sensor.workday_sensor", "workday", "Workday", LINK["workday"], "vælg Danmark.")]:
            if hass.states.get(ønsket) is not None:
                continue
            if platform == "energidataservice" and (np := _nordpool(hass)):
                info.append(f"ℹ️ Priserne kommer fra **Nordpool** (`{np}`). Vælg den i næste trin.")
                continue
            fundet = _platform_entitet(hass, ønsket.split(".")[0], platform)
            if fundet:  # findes under et andet navn (fx binary_sensor.workday_sensor_dk) – Wattlas giver den det navn, pakkerne bruger
                self.d["omdoeb"][fundet] = ønsket
                info.append(f"ℹ️ **{navn}** findes som `{fundet}` – Wattlas omdøber den til `{ønsket}`. "
                            "Bruger dine egne automationer det gamle navn, så ret dem bagefter.")
            else:
                blok.append(f"❌ **{navn}** mangler – " + (f"[tilføj den]({link}), {hjælp}" if link else hjælp))
        if priser_fejl(hass):
            blok.append("❌ **Energi Data Service** skal give ren spotpris pr. kWh: slå *tariffer* og *vis i øre* fra, og vælg *kWh*, i dens indstillinger. Wattlas lægger selv tarifferne på.")
        alle = await hass.async_add_executor_job(installer.entiteter_i_kanal, self.d["kanal"], self.d["prefix"], self.d.get("ekstra"))
        mangler = [e for e in alle if hass.states.get(e) is None and not e.endswith("_microinverter_power")] if self.d["kanal"] not in EGNE else []
        if mangler:
            vis = ", ".join(f"`{e}`" for e in mangler[:8]) + (f" og {len(mangler) - 8} til" if len(mangler) > 8 else "")
            adv.append(f"⚠️ Inverteren mangler {len(mangler)} entiteter, som Wattlas bruger: {vis}. "
                       "Har din inverter-integration slået nogle fra, så slå dem til. Ellers kan dele af styringen mangle.")
        prognoser = [s.entity_id for s in hass.states.async_all("sensor") if isinstance(s.attributes.get("forecast"), list) or isinstance(s.attributes.get("detailedForecast"), list)]
        if not prognoser:
            adv.append("⚠️ Ingen solprognose fundet – *Helios Forecast* eller *Solcast* fra Markedspladsen (se SOLPROGNOSE.md).")
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
            fejl = _forbindelse_fejl(self.hass, user_input, kraev_noegle=True)
            if not fejl:
                self.d.update(user_input)
                return await self.async_step_batteri()
        return self.async_show_form(step_id="forbindelser", errors=fejl, data_schema=vol.Schema({
            vol.Required("emhass_adresse", default=self.d.get("emhass_adresse") or "http://homeassistant.local:5000"): sel.TextSelector(),
            vol.Required("emhass_noegle"): sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.PASSWORD)),
            vol.Required("solprognose"): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", **_kilde_filter(self.hass, "sol", self.d.get("solprognose")))),
            vol.Optional("priser", description={"suggested_value": self.d.get("priser") or _nordpool(self.hass)}): sel.EntitySelector(
                sel.EntitySelectorConfig(domain="sensor", **_kilde_filter(self.hass, "pris", self.d.get("priser")))),
            vol.Required("priser_uden_moms", default=False): sel.BooleanSelector(),
            vol.Required("vejr"): sel.EntitySelector(sel.EntitySelectorConfig(domain="weather")),
            vol.Optional("udetemperatur"): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", device_class="temperature")),
        }))

    async def _tal_trin(self, trin: str, user_input, naeste) -> ConfigFlowResult:
        felter = _tal_felter(self.d, trin)
        fejl = {}
        if user_input is not None:
            fejl = _tal_fejl(felter, user_input)
            if not fejl:
                self.d["tal"] = _med_a(self.d.get("kanal"), {**self.d.get("tal", {}), **{k: v for k, v in user_input.items() if v is not None}})
                return await naeste()
        return self.async_show_form(step_id=trin, data_schema=_tal_skema(felter, STANDARD), errors=fejl, description_placeholders=_pris_tekst(self.d, self.d.get("tal", {})))

    async def async_step_batteri(self, user_input=None) -> ConfigFlowResult:
        return await self._tal_trin("batteri", user_input, self.async_step_elnet)

    async def async_step_elnet(self, user_input=None) -> ConfigFlowResult:
        return await self._tal_trin("elnet", user_input, self.async_step_netselskab)

    async def async_step_netselskab(self, user_input=None) -> ConfigFlowResult:
        fejl, grund = {}, ""
        if user_input is not None:
            if (gln := user_input["netselskab"]) == tariffer.MANUEL:
                return await self.async_step_priser()
            try:
                self.d["tal"] = {**self.d.get("tal", {}), **await tariffer.hent(self.hass, gln)}
                self.d["netselskab"] = gln
                return await self.async_step_priser()
            except tariffer.TarifFejl as e:
                fejl, grund = {"base": "tarif"}, str(e)
        return self.async_show_form(step_id="netselskab", errors=fejl, data_schema=_netselskab_skema((user_input or {}).get("netselskab")),
                                    description_placeholders={"grund": grund})

    async def async_step_priser(self, user_input=None) -> ConfigFlowResult:
        return await self._tal_trin("priser", user_input, self.async_step_installer)

    # 5 – installér, tjek konfigurationen, rul tilbage ved fejl
    async def async_step_installer(self, user_input=None) -> ConfigFlowResult:
        hass = self.hass
        omdoeb = self.d.pop("omdoeb", None) or {}
        if fejl := await _laeg_filer(hass, self.d):
            return self.async_abort(reason="install_fejl", description_placeholders={"fejl": fejl})
        reg = er.async_get(hass)
        for gammel, ny in omdoeb.items():
            if reg.async_get(gammel) and not reg.async_get(ny):
                reg.async_update_entity(gammel, new_entity_id=ny)
        data = {k: v for k, v in self.d.items() if k != "emhass_adresse_fundet"}
        data["version"] = VERSION
        return self.async_create_entry(title="Wattlas", data=data)


class WattlasOptionsFlow(OptionsFlow):
    """Konfigurer: ret opsætningens tal og forbindelser – udfyldt med de nuværende værdier, gemt med det samme.
    Inverteren (styrekanalen) skiftes ved at fjerne Wattlas og tilføje den igen."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["forbindelser", "batteri", "elnet", "netselskab", "priser", "elbil", "lader"]
                                    + (["sonnen"] if self.config_entry.data.get("kanal") == "sonnen" else [])
                                    + (["inverter2"] if self.config_entry.data.get("inverter2") else []))

    async def async_step_inverter2(self, user_input=None) -> ConfigFlowResult:
        """Inverter 2: navn, effekt, dens egen sensor (til Teknik) og relæ. Filerne skrives igen, og HA skal genstartes."""
        d = self.config_entry.data
        fejl: dict[str, str] = {}
        if user_input is not None:
            inv2, fejl = _inverter2(user_input, d.get("prefix") or "")
            if inv2:
                ny = {**d, "inverter2": inv2}
                if tekst := await _laeg_filer(self.hass, ny):
                    return self.async_abort(reason="install_fejl", description_placeholders={"fejl": tekst})
                self.hass.config_entries.async_update_entry(self.config_entry, data=ny)
                return self.async_create_entry(data={})
        return self.async_show_form(step_id="inverter2", errors=fejl, data_schema=_inverter2_skema(d.get("inverter2") or {}))

    async def async_step_sonnen(self, user_input=None) -> ConfigFlowResult:
        """Sonnen: ny adresse (fx ny IP fra routeren) eller nyt token. Kanalens filer skrives igen, og HA skal genstartes."""
        d = self.config_entry.data
        gammel = d.get("sonnen") or {}
        fejl: dict[str, str] = {}
        if user_input is not None:
            host = user_input["sonnen_host"].strip().rstrip("/")
            token = (user_input.get("sonnen_token") or "").strip() or gammel.get("token", "")  # tom = behold det nuværende
            fejl = await _sonnen_fejl(self.hass, host, token)
            if not fejl:
                ny = {**d, "sonnen": {"host": host, "token": token}}
                if tekst := await _laeg_filer(self.hass, ny):
                    return self.async_abort(reason="install_fejl", description_placeholders={"fejl": tekst})
                self.hass.config_entries.async_update_entry(self.config_entry, data=ny)
                return self.async_create_entry(data={})
        return self.async_show_form(step_id="sonnen", errors=fejl, data_schema=vol.Schema({
            vol.Required("sonnen_host", default=(user_input or {}).get("sonnen_host") or gammel.get("host", "http://")): sel.TextSelector(),
            vol.Optional("sonnen_token"): sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.PASSWORD))}))

    def _hjaelper(self, dom: str, navn: str):
        s = self.hass.states.get(f"{dom}.wattlas_{navn}")
        if s is None or s.state in ("unknown", "unavailable", ""):
            return None
        if dom == "input_text":
            return s.state
        try:
            return float(s.state)
        except ValueError:
            return None

    def _tariffer(self) -> dict[str, float]:
        return {k: self._hjaelper("input_number", k) or 0.0 for k in tariffer.FELTER}

    async def async_step_forbindelser(self, user_input=None) -> ConfigFlowResult:
        fejl: dict[str, str] = {}
        if user_input is not None:
            fejl = _forbindelse_fejl(self.hass, user_input, kraev_noegle=False)
            if not fejl:
                for k, h in TEKST.items():
                    await self.hass.services.async_call("input_text", "set_value",
                                                        {"entity_id": f"input_text.wattlas_{h}", "value": user_input.get(k) or ""}, blocking=True)
                ny = {k: user_input[k] for k in GAMLE if user_input.get(k)}  # tom = behold den nuværende nøgle
                self.hass.config_entries.async_update_entry(self.config_entry, data={**self.config_entry.data, **ny})
                if self.config_entry.data.get("emhass_noegle"):
                    ir.async_delete_issue(self.hass, DOMAIN, "noegle_mangler")
                for k, v in ny.items():  # pakker fra før 0.4.2 kører endnu (genstart mangler) og læser værdierne her
                    if self.hass.states.get(GAMLE[k]):
                        await self.hass.services.async_call("input_text", "set_value", {"entity_id": GAMLE[k], "value": v}, blocking=True)
                return self.async_create_entry(data={})
        nu = {**{k: self._hjaelper("input_text", h) for k, h in TEKST.items()}, "emhass_adresse": self.config_entry.data.get("emhass_adresse")}
        if nu.get("solprognose") == SOLCAST and nu.get("solcast"):
            nu["solprognose"] = nu["solcast"].split(",")[0]  # vis den Solcast-sensor, brugeren valgte
        moms = _faktor_med_moms(nu.get("pris") or "")
        d = lambda k: {"default": nu[k]} if nu.get(k) else {}  # noqa: E731
        return self.async_show_form(step_id="forbindelser", errors=fejl, data_schema=vol.Schema({
            vol.Required("emhass_adresse", **d("emhass_adresse")): sel.TextSelector(),
            vol.Optional("emhass_noegle"): sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.PASSWORD)),
            vol.Required("solprognose", **d("solprognose")): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", **_kilde_filter(self.hass, "sol", nu.get("solprognose")))),
            vol.Optional("priser", description={"suggested_value": (nu.get("pris") or "").split("|")[0] or None}): sel.EntitySelector(
                sel.EntitySelectorConfig(domain="sensor", **_kilde_filter(self.hass, "pris", (nu.get("pris") or "").split("|")[0] or None))),
            vol.Required("priser_uden_moms", default=moms): sel.BooleanSelector(),
            vol.Required("vejr", **d("vejr")): sel.EntitySelector(sel.EntitySelectorConfig(domain="weather")),
            vol.Optional("udetemperatur", **d("udetemperatur")): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", device_class="temperature")),
        }))

    async def _tal(self, trin: str, user_input) -> ConfigFlowResult:
        kanal = self.config_entry.data.get("kanal")
        felter = _tal_felter(self.config_entry.data, trin)
        fejl: dict[str, str] = {}
        if user_input is not None:
            fejl = _tal_fejl(felter, user_input)
            if not fejl:
                tal = _med_a(kanal, {**(self.config_entry.data.get("tal") or {}), **{k: v for k, v in user_input.items() if v is not None}})
                for k in set(felter) | (set(A_FRA_W) if kanal in HOEJVOLT else set()):
                    if tal.get(k) is not None:
                        await self.hass.services.async_call("input_number", "set_value",
                                                            {"entity_id": f"input_number.wattlas_{k}", "value": tal[k]}, blocking=True)
                # gemmes også i opsætningen, så en geninstallation (fjern + tilføj) husker dem
                self.hass.config_entries.async_update_entry(self.config_entry, data={**self.config_entry.data, "tal": tal})
                return self.async_create_entry(data={})
        nu = {k: self._hjaelper("input_number", k) for k in felter}
        return self.async_show_form(step_id=trin, data_schema=_tal_skema(felter, nu), errors=fejl,
                                    description_placeholders=_pris_tekst(self.config_entry.data, self._tariffer()))

    async def async_step_netselskab(self, user_input=None) -> ConfigFlowResult:
        d = self.config_entry.data
        fejl, grund = {}, ""
        if user_input is not None:
            if (gln := user_input["netselskab"]) == tariffer.MANUEL:
                ir.async_delete_issue(self.hass, DOMAIN, "tarif_fejl")
                if self.hass.states.get(tariffer.HENTET):  # så minder Wattlas om nettarifferne igen
                    await self.hass.services.async_call("input_text", "set_value", {"entity_id": tariffer.HENTET, "value": ""}, blocking=True)
                self.hass.config_entries.async_update_entry(self.config_entry, data={k: v for k, v in self.config_entry.data.items() if k != "netselskab"})
                return self.async_create_entry(data={})
            try:
                self._valgt = gln, await tariffer.hent(self.hass, gln)
                return await self.async_step_netselskab_vis()
            except tariffer.TarifFejl as e:
                fejl, grund = {"base": "tarif"}, str(e)
        return self.async_show_form(step_id="netselskab", errors=fejl, description_placeholders={"grund": grund},
                                    data_schema=_netselskab_skema((user_input or d).get("netselskab")))

    async def async_step_elbil(self, user_input=None) -> ConfigFlowResult:
        """Laderens måling, når Wattlas ikke selv styrer laderen. "Kun fra elnettet" (holdet) slås til og fra i appen."""
        nu, til = self.hass.states.get(ELBIL), self.hass.states.get(ELBIL_HOLD)
        if nu is None or til is None:
            return self.async_abort(reason="genstart_foerst")
        if (self.config_entry.data.get("lader") or {}).get("effekt"):
            return self.async_abort(reason="lader_styret")  # styret lader: målingen er dens, og kontakten ligger på fanen Elbil
        fejl = {}
        kan = self.config_entry.data.get("kanal") != "sonnen"  # Sonnen kan ikke holdes; prognosen uden bilen virker stadig
        valgt = nu.state if nu.state.startswith("sensor.") else None
        if user_input is not None:
            lader = user_input.get("elbil_sensor") or ""
            if lader and _elbil_fejl(self.hass, lader, self.config_entry.data):
                fejl = {"elbil_sensor": "elbil_sensor"}
            else:
                await self.hass.services.async_call("input_text", "set_value", {"entity_id": ELBIL, "value": lader}, blocking=True)
                # en ny lader: "Kun fra elnettet" slås til (som før); bagefter bestemmer brugeren i appen. Ryddet (eller Sonnen) = slået fra
                if not lader or not kan or not valgt:
                    await self.hass.services.async_call("input_boolean", "turn_on" if lader and kan else "turn_off", {"entity_id": ELBIL_HOLD}, blocking=True)
                return self.async_create_entry(data={})
        fundet = _fundne_ladere(self.hass)
        foreslag = (user_input or {}).get("elbil_sensor") or valgt or (fundet[0][0] if len(fundet) == 1 else None)
        # kendte ladere: kun dem (og det valgte). Ellers alle effekter undtagen husets egne (inverter, Wattlas, EMHASS), der aldrig er bilen
        if fundet:
            filt = {"include_entities": sorted({e for e, _ in fundet} | ({valgt} if valgt else set()))}
        else:
            filt = {"exclude_entities": sorted(s.entity_id for s in self.hass.states.async_all("sensor")
                                               if s.attributes.get("device_class") == "power" and _elbil_fejl(self.hass, s.entity_id, self.config_entry.data))}
        return self.async_show_form(step_id="elbil", errors=fejl, data_schema=vol.Schema({
            vol.Optional("elbil_sensor", description={"suggested_value": foreslag}): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", device_class="power", **filt)),
        }), description_placeholders={"fundet": "; ".join(n for _, n in fundet) or "Ingen kendt lader fundet"})

    # --- elbil-laderen: vælg den på listen → se, hvad Wattlas fandt → prøv den ---
    async def async_step_lader(self, user_input=None) -> ConfigFlowResult:
        if self.hass.states.get(LADER_TILSTAND) is None:
            return self.async_abort(reason="genstart_foerst")
        fundet = lader_find.fundne(self.hass)
        if user_input is not None:
            valg = user_input["lader"]
            if valg == "ingen":
                return await self._gem_lader(None)
            if valg == "anden":
                return await self.async_step_lader_enhed()
            self._lader = dict(fundet[valg][1])
            return await self.async_step_lader_ok()
        valg = [sel.SelectOptionDict(value=k, label=n) for k, (n, _) in sorted(fundet.items(), key=lambda x: x[1][0])]
        valg += [sel.SelectOptionDict(value="anden", label="Min lader er ikke på listen"), sel.SelectOptionDict(value="ingen", label="Wattlas skal ikke styre en lader")]
        return self.async_show_form(step_id="lader", data_schema=vol.Schema({
            vol.Required("lader", default=next(iter(fundet), "anden")): sel.SelectSelector(sel.SelectSelectorConfig(options=valg, mode=sel.SelectSelectorMode.LIST))}))

    async def async_step_lader_enhed(self, user_input=None) -> ConfigFlowResult:
        """Laderen er ikke på listen: vælg dens enhed (eller ingen, så peges der på hver ting for sig)."""
        if user_input is not None:
            self._lader = lader_find.fra_enhed(self.hass, user_input["enhed"]) if user_input.get("enhed") else {"slags": "entiteter"}
            return await self.async_step_lader_roller()
        # kun enheder med en effektmåler: en lader skal kunne vise, hvad den trækker (ellers står tv, router og kort også på listen)
        return self.async_show_form(step_id="lader_enhed", data_schema=vol.Schema({
            vol.Optional("enhed"): sel.DeviceSelector(sel.DeviceSelectorConfig(entity=sel.EntityFilterSelectorConfig(domain="sensor", device_class="power")))}))

    async def async_step_lader_ok(self, user_input=None) -> ConfigFlowResult:
        d, fejl = self._lader, {}
        til, strom = lader_find.kan(self.hass, d)
        if user_input is not None:
            d["faser"], d["maks_a"] = int(user_input["faser"]), int(user_input["maks_a"])
            for k in ("bil_soc", "bil_stik", "bil_km", "bil_kwh"):
                d.pop(k, None)
            if soc := user_input.get("bil_soc"):
                d.update(lader_find.bil_fra(self.hass, soc), bil_kwh=float(user_input.get("bil_kwh") or 0))
                if not 5 <= d["bil_kwh"] <= 250:
                    fejl = {"bil_kwh": "bil_kwh"}
            if not fejl:
                return await (self.async_step_lader_roller() if user_input.get("ret") else self.async_step_lader_proev())
        s = self.hass.states.get(d.get("strom", ""))
        loft = int(min(32, max(6, float((s and s.attributes.get("max")) or (32 if d.get("slags") in ("easee", "ocpp") else 16)))))
        ja = lambda x: "✓" if x else "–"  # noqa: E731
        return self.async_show_form(step_id="lader_ok", errors=fejl, data_schema=vol.Schema({
            vol.Required("faser", default=str(d.get("faser") or 3)): sel.SelectSelector(sel.SelectSelectorConfig(options=["3", "1"], translation_key="faser")),
            vol.Required("maks_a", default=d.get("maks_a") or min(16, loft)): sel.NumberSelector(sel.NumberSelectorConfig(min=6, max=loft, step=1, unit_of_measurement="A", mode=sel.NumberSelectorMode.BOX)),
            vol.Optional("bil_soc", description={"suggested_value": d.get("bil_soc")}): sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor", device_class="battery")),
            vol.Optional("bil_kwh", description={"suggested_value": d.get("bil_kwh")}): sel.NumberSelector(sel.NumberSelectorConfig(min=5, max=250, step=1, unit_of_measurement="kWh", mode=sel.NumberSelectorMode.BOX)),
            vol.Required("ret", default=False): sel.BooleanSelector()}),
            description_placeholders={"effekt": ja(d.get("effekt")), "status": ja(d.get("status")), "til": ja(til), "strom": ja(strom)})

    async def async_step_lader_roller(self, user_input=None) -> ConfigFlowResult:
        d, fejl = self._lader, {}
        if user_input is not None:
            ny = {**{k: v for k, v in d.items() if k not in ("effekt", "status", "til_fra", "strom", "start", "stop", "omvendt", "til_valg", "fra_valg")}, **user_input}
            if _elbil_fejl(self.hass, ny["effekt"], self.config_entry.data):
                fejl["effekt"] = "elbil_sensor"
            elif not lader_find.kan(self.hass, ny)[0]:
                fejl["base"] = "lader_ingen_styring"
            elif (ny.get("til_fra") or "").startswith("select."):
                muligt = getattr(self.hass.states.get(ny["til_fra"]), "attributes", {}).get("options") or []
                par = next(((t, f) for t, f in lader_find.VALG if t in muligt and f in muligt), None)
                if par is None:
                    fejl["til_fra"] = "lader_valg"
                else:
                    ny["til_valg"], ny["fra_valg"] = par
            if not fejl:
                self._lader = ny
                return await self.async_step_lader_ok()
            d = ny
        felt = lambda k, dom, **x: (vol.Required(k) if k == "effekt" and not d.get(k) else (vol.Required if k == "effekt" else vol.Optional)(k, description={"suggested_value": d.get(k)}),  # noqa: E731
                                    sel.EntitySelector(sel.EntitySelectorConfig(domain=dom, **x)))
        felter = [felt("effekt", "sensor", device_class="power"), felt("status", ["sensor", "binary_sensor"])]
        if d.get("slags") == "entiteter":
            felter += [felt("til_fra", ["switch", "input_boolean", "select"]), (vol.Optional("omvendt", default=bool(d.get("omvendt"))), sel.BooleanSelector()),
                       felt("strom", "number"), felt("start", "button"), felt("stop", "button")]
        return self.async_show_form(step_id="lader_roller", errors=fejl, data_schema=vol.Schema(dict(felter)))

    async def async_step_lader_proev(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input["proev"]:
                return await self.async_step_lader_koer()
            return await self._gem_lader({**self._lader, "proevet": False})
        return self.async_show_form(step_id="lader_proev", data_schema=vol.Schema({vol.Required("proev", default=True): sel.BooleanSelector()}))

    async def async_step_lader_koer(self, user_input=None) -> ConfigFlowResult:
        if getattr(self, "_opgave", None) is None:
            async def koer() -> dict:
                await lader.afslut(self.hass)  # kun én styrer laderen ad gangen
                try:
                    return await lader_find.proev(self.hass, self._lader)
                finally:
                    await lader.aktiver(self.hass, self.config_entry)
            self._opgave = self.hass.async_create_task(koer())
        if not self._opgave.done():
            return self.async_show_progress(step_id="lader_koer", progress_action="lader_proev", progress_task=self._opgave)
        return self.async_show_progress_done(next_step_id="lader_resultat")

    async def async_step_lader_resultat(self, user_input=None) -> ConfigFlowResult:
        r, self._opgave = (self._opgave.result(), None) if getattr(self, "_opgave", None) else (self._svar, None)
        self._svar = r
        if r.get("fejl"):
            tekst = LADER_FEJL.get(r["fejl"], f"Laderen tog ikke imod: {r['fejl']}")
            kan = False
        else:
            kan = r["start"] and r["stop"]
            ja = lambda x: "✓ virker" if x else "✗ virker ikke"  # noqa: E731
            styrer_strom = lader_find.kan(self.hass, self._lader)[1]
            tekst = f"Start: {ja(r['start'])} · Strøm: {ja(r['strom']) if styrer_strom else 'kan laderen ikke'} · Stop: {ja(r['stop'])}"
        if kan and user_input is None:
            return self.async_show_form(step_id="lader_resultat", data_schema=vol.Schema({}), description_placeholders={"svar": tekst, "raad": "Tryk *Send* for at gemme."})
        if kan:
            d = {**self._lader, "proevet": True}
            if lader_find.kan(self.hass, d)[1] and not r["strom"]:  # strømmen kunne ikke bekræftes: kun tænd/sluk
                if d["slags"] != "entiteter" or not (d.get("til_fra") or d.get("start")):
                    return self.async_abort(reason="lader_ikke_styret", description_placeholders={"svar": tekst})
                d.pop("strom", None)
            return await self._gem_lader(d)
        return self.async_abort(reason="lader_ikke_styret", description_placeholders={"svar": tekst})

    async def _gem_lader(self, d: dict | None) -> ConfigFlowResult:
        data = {k: v for k, v in self.config_entry.data.items() if k != "lader"}
        if d:
            data["lader"] = d
            await self.hass.services.async_call("input_number", "set_value", {"entity_id": LADER_MAKS, "value": d.get("maks_a") or 16}, blocking=True)
            await self.hass.services.async_call("input_text", "set_value", {"entity_id": ELBIL, "value": d["effekt"]}, blocking=True)
            maal = self.hass.states.get(LADER_MAAL)
            if d.get("bil_soc") and maal is not None and maal.state in ("50", "50.0"):  # aldrig sat: 80 % er et godt sted at begynde
                await self.hass.services.async_call("input_number", "set_value", {"entity_id": LADER_MAAL, "value": 80}, blocking=True)
            sol = self.hass.states.get(LADER_SOL)
            if d.get("bil_soc") and not self.config_entry.data.get("lader") and sol is not None and sol.state in ("50", "50.0"):  # ny lader: gratis sol må fylde bilen
                await self.hass.services.async_call("input_number", "set_value", {"entity_id": LADER_SOL, "value": 100}, blocking=True)
        await self.hass.services.async_call("input_select", "select_option", {"entity_id": LADER_TILSTAND, "option": "fra"}, blocking=True)
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        await lader.aktiver(self.hass, self.config_entry)
        return self.async_create_entry(data={})

    async def async_step_netselskab_vis(self, user_input=None) -> ConfigFlowResult:
        """Vis de nye tal, før de gemmes."""
        gln, ny = self._valgt
        if user_input is None:
            return self.async_show_form(step_id="netselskab_vis", data_schema=vol.Schema({}), description_placeholders={
                "navn": tariffer.SELSKABER[gln][0], "nu": tariffer.vis(self._tariffer()), "ny": tariffer.vis(ny)})
        await tariffer.anvend(self.hass, ny)
        self.hass.data.pop(tariffer.SIDST, None)  # vinduet kan have stået åbent over midnat: hent igen i næste time
        d = self.config_entry.data
        ir.async_delete_issue(self.hass, DOMAIN, "tarif_fejl")
        self.hass.config_entries.async_update_entry(self.config_entry, data={**d, "netselskab": gln, "tal": {**(d.get("tal") or {}), **ny}})
        return self.async_create_entry(data={})

    async def async_step_batteri(self, user_input=None) -> ConfigFlowResult:
        return await self._tal("batteri", user_input)

    async def async_step_elnet(self, user_input=None) -> ConfigFlowResult:
        return await self._tal("elnet", user_input)

    async def async_step_priser(self, user_input=None) -> ConfigFlowResult:
        return await self._tal("priser", user_input)
