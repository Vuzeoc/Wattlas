"""Kald til EMHASS. API-nøglen ligger kun i integrationens opsætning (entry.data) – aldrig i en tilstand, en pakke eller loggen."""
from __future__ import annotations

import aiohttp
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

TIMEOUT_S = {"naive-mpc-optim": 120, "publish-data": 60}  # de eneste kald, tjenesten kan lave


async def _kald(call: ServiceCall) -> dict:
    """Samme svar som rest_command: status og content – også ved 401 og andre fejlkoder."""
    hass = call.hass
    # begge fra opsætningen: en adresse i en hjælper kunne enhver bruger rette og få nøglen sendt til sin egen server
    d = next((e.data for e in hass.config_entries.async_entries(DOMAIN)), {})
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


def opret(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "emhass", _kald, supports_response=SupportsResponse.OPTIONAL,
                                 schema=vol.Schema({vol.Required("handling"): vol.In(TIMEOUT_S), vol.Required("data"): dict}))
