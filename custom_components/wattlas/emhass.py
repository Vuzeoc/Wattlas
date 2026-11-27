"""Kald til EMHASS – eller til Wattlas' lette hjerne (lethjerne.py), når den er valgt i opsætningen.

API-nøglen ligger kun i integrationens opsætning (entry.data) – aldrig i en tilstand, en pakke eller loggen. Den lette hjerne tager den samme
bestilling og udgiver de samme sensorer (samme navne og form som EMHASS' publish-data), så resten af Wattlas – kontrollen af planen,
reguleringen, grænserne, kortet og hvad-hvis – er uændret."""
from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import lethjerne
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
TIMEOUT_S = {"naive-mpc-optim": 120, "publish-data": 60}  # de eneste kald, tjenesten kan lave
LET = f"{DOMAIN}_let_plan"  # hass.data: den lette hjernes seneste plan (publish-data udgiver den, som EMHASS udgiver sin seneste)


async def _kald(call: ServiceCall) -> dict:
    """Samme svar som rest_command: status og content – også ved 401 og andre fejlkoder."""
    hass = call.hass
    d = next((e.data for e in hass.config_entries.async_entries(DOMAIN)), {})
    if d.get("hjerne") == "let":
        return await _let(hass, call.data["handling"], call.data["data"])
    # begge fra opsætningen: en adresse i en hjælper kunne enhver bruger rette og få nøglen sendt til sin egen server
    noegle, adresse = d.get("emhass_noegle"), (d.get("emhass_adresse") or "").strip().rstrip("/")
    if not noegle or not adresse:
        raise HomeAssistantError("Wattlas: EMHASS-nøglen eller -adressen mangler (Enheder og tjenester → Wattlas → Konfigurer)")
    handling = call.data["handling"]
    try:
        async with async_get_clientsession(hass).post(f"{adresse}/action/{handling}", json=call.data["data"],
                                                      headers={"Authorization": f"Bearer {noegle}"},
                                                      timeout=aiohttp.ClientTimeout(total=TIMEOUT_S[handling])) as r:
            return {"status": r.status, "content": await r.text(errors="replace")}
    except (TimeoutError, aiohttp.ClientError, ValueError) as e:  # kun fejlens type: teksten kan rumme kaldets indhold
        raise HomeAssistantError(f"Wattlas: EMHASS svarede ikke ({type(e).__name__})") from None


def _tal(hass: HomeAssistant, e: str) -> float | None:
    try:
        return float(hass.states.get(e).state)
    except (AttributeError, TypeError, ValueError):
        return None


async def _let(hass: HomeAssistant, handling: str, data: dict) -> dict:
    """Den lette hjerne. Svarer som EMHASS: 200 og en tekst – eller en fejlkode (400: kan ikke løses; 500: uventet), som Wattlas håndterer
    præcis som en fejl fra EMHASS (den seneste godkendte plan bruges, ellers selvforbrug)."""
    if handling == "naive-mpc-optim":
        trin = float(data.get("optimization_time_step") or 30) * 60
        start = (dt_util.utcnow().timestamp() // trin) * trin  # som EMHASS (method_ts_round: first): begyndelsen af det igangværende trin
        # ny installation uden forbrugshistorik: husets forbrug nu – uden elbilen og en kørende fleksibel forbruger (de planlægges for sig)
        fb = hass.states.get(str(getattr(hass.states.get("input_text.wattlas_forbruger1_entitet"), "state", "")))
        fb_w = (_tal(hass, "input_number.wattlas_forbruger1_effekt") or 0.0) if fb is not None and fb.state == "on" \
            and hass.states.is_state("input_boolean.wattlas_forbruger1_aktiv", "on") else 0.0
        last = max(300.0, (_tal(hass, "sensor.emhass_m_load_w_totalpower") or 1000.0) - (_tal(hass, "sensor.wattlas_elbil_effekt") or 0.0) - fb_w)
        try:
            plan = await hass.async_add_executor_job(lethjerne.optimer, dict(data), start, last)  # aldrig i event-loopen
        except lethjerne.PlanFejl as e:
            return {"status": 400, "content": f"Wattlas' lette hjerne: {e}"}
        except Exception as e:  # noqa: BLE001 – en fejl her må ikke stoppe styringen; Wattlas falder tilbage som ved en EMHASS-fejl
            _LOGGER.exception("Wattlas' lette hjerne fejlede")
            return {"status": 500, "content": f"Wattlas' lette hjerne fejlede ({type(e).__name__})"}
        hass.data[LET] = plan
        return {"status": 200, "content": "Wattlas' lette hjerne >> naive-mpc-optim executed"}
    plan = hass.data.get(LET)
    if plan is None:
        return {"status": 400, "content": "Wattlas' lette hjerne: ingen plan at udgive"}
    _udgiv(hass, plan, data.get("publish_prefix") or "", data.get("custom_deferrable_forecast_id") or [],
           int(data.get("number_of_deferrable_loads") or 0))
    return {"status": 200, "content": "Wattlas' lette hjerne >> publish-data executed"}


def _udgiv(hass: HomeAssistant, plan: dict, pre: str, egne: list, antal: int) -> None:
    """Samme sensorer som EMHASS' publish-data (målt på EMHASS 0.19): tilstand = det igangværende trin, listen i en attribut med datoer."""
    t0, dt = plan["start_ts"], plan["trin_s"]
    datoer = [dt_util.as_local(dt_util.utc_from_timestamp(t0 + i * dt)).isoformat() for i in range(len(plan["p_batt"]))]

    def saet(navn: str, vaerdier: list, liste: str, venlig: str, enhed: str, klasse: str) -> None:
        nøgle = pre + navn
        hass.states.async_set(f"sensor.{nøgle}", f"{float(vaerdier[0]):.2f}", {
            "device_class": klasse, "unit_of_measurement": enhed, "friendly_name": venlig,
            liste: [{"date": d, nøgle: str(round(float(v), 4))} for d, v in zip(datoer, vaerdier)], "state_class": "measurement"})
    saet("p_pv_forecast", plan["p_pv"], "forecasts", "PV Power Forecast", "W", "power")
    saet("p_load_forecast", plan["p_load"], "forecasts", "Load Power Forecast", "W", "power")
    saet("p_batt_forecast", plan["p_batt"], "battery_scheduled_power", "Battery Power Forecast", "W", "power")
    saet("soc_batt_forecast", plan["soc"], "battery_scheduled_soc", "Battery SOC Forecast", "%", "battery")
    saet("p_grid_forecast", plan["p_grid"], "forecasts", "Grid Power Forecast", "W", "power")
    saet("unit_load_cost", plan["koeb"], "unit_load_cost_forecasts", "Unit Load Cost", "kr/kWh", "monetary")
    saet("unit_prod_price", plan["salg"], "unit_prod_price_forecasts", "Unit Prod Price", "kr/kWh", "monetary")
    for k, rk in enumerate(plan["laster"][:antal]):
        e = (egne[k] or {}) if k < len(egne) else {}
        navn = str(e.get("entity_id") or f"sensor.p_deferrable{k}").split(".", 1)[-1]
        saet(navn, rk, "deferrables_schedule", e.get("friendly_name") or f"Deferrable Load {k}", "W", "power")
    hass.states.async_set(f"sensor.{pre}total_cost_fun_value", f"{plan['total']:.2f}", {
        "device_class": "monetary", "unit_of_measurement": "kr", "friendly_name": "Total cost function value", "state_class": "measurement"})
    hass.states.async_set(f"sensor.{pre}optim_status", "Optimal", {"friendly_name": "EMHASS optimization status"})


def opret(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "emhass", _kald, supports_response=SupportsResponse.OPTIONAL,
                                 schema=vol.Schema({vol.Required("handling"): vol.In(TIMEOUT_S), vol.Required("data"): dict}))
