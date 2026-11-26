"""Finder elbil-ladere i Home Assistant og gætter deres roller, så brugeren kun skal vælge sin lader – og prøver dem af med målt effekt."""
from __future__ import annotations

import asyncio
import re

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .lader import Styring

# platform → navn. Kun ladere, der kan mere end at blive læst
MAERKER = {"easee": "Easee", "zaptec": "Zaptec", "goecharger_api2": "go-e", "wallbox": "Wallbox", "ocpp": "OCPP", "garo_wallbox": "Garo", "chargeamps": "Charge Amps",
           "abb_terra_ac": "ABB", "nexblue": "NexBlue", "nexblue_hass": "NexBlue", "ohme": "Ohme", "openevse": "OpenEVSE", "peblar": "Peblar", "alfen_wallbox": "Alfen",
           "v2c": "V2C", "webasto_next_modbus": "Webasto", "mennekes_amtron": "Mennekes"}
SKY = {"easee", "zaptec", "wallbox", "chargeamps", "nexblue", "nexblue_hass", "ohme"}  # skrives sjældent op, men altid straks ned
# (til, fra) i en valgliste
VALG = [("2", "1"), ("max_charge", "paused"), ("active", "disabled"), ("ALWAYS_ON", "ALWAYS_OFF"), ("always_on", "always_off")]
ORD = {
    "effekt": (r"total_charge_power\b|charging_power|charge_power|power_total|total_power|active_power|power", r"phase|fase|_l[123]\b|(?<!active_)import|export|equali[sz]er|offered|reactive|factor|max|min|session"),
    "strom": (r"dynamic|charger_max_current|max_charging_current|charge_current_limit|charging_current|current_limit|hems_current|charge_rate|max_current|intensity|\bamp\b|_amp\b|current",
              r"min_current|phase|fase|fallback|fuse|sikring|default|solar|available_current|circuit|offline|installation|session|maximum_current"),
    "kontakt": (r"charger_operation_mode|charge_control|start_charging|pause_charging|paused|charging|charge|enable|lad", r"lock|light|led|schedul|access|smart|solar|guest|availab|authori|reboot|random|phase|dynamic"),
    "valg": (r"frc|charge_mode|override_state|mode|sensor|force", r"phase|led|language|logic"),
    "start": (r"start_charg|start_session|resume_charg|resume|start", r"restart|reboot|authori"),
    "stop": (r"stop_charg|stop_session|pause|stop", r"deauthori|final_reset"),
    "status": (r"charger_operation_mode|car_status|session_state|status_socket|status_description|status_connector|easee_status|charging_state|status|state|\bcar\b|_car\b", r"firmware|wifi|network|connect(ion|ivity)|cloud|update|error|led|heartbeat"),
}
BIL = re.compile(r"charg|lad|connect|tilslut|prepar|suspend|finish|(?<!un)avail|unplug|plug|idle|pause|not_connected|ready|wait|^[abc1-5]$", re.I)


def _noegle(e) -> str:
    return " ".join(str(x) for x in (e.entity_id, e.unique_id, e.translation_key, e.original_name) if x).lower().replace(" ", "_")


def _bedst(kandidater: list, rolle: str):
    ja, nej = (re.compile(x) for x in ORD[rolle])
    ord_ = ORD[rolle][0].split("|")
    rest = [(min(i for i, o in enumerate(ord_) if re.search(o, n)), e.entity_id) for e in kandidater if ja.search(n := _noegle(e)) and not nej.search(n)]
    return min(rest)[1] if rest else None


def gaet(hass: HomeAssistant, entiteter: list) -> dict:
    """Roller for én lader ud fra dens entiteter. Det, der ikke kan ses, gættes ikke."""
    st = {e.entity_id: s for e in entiteter if not e.disabled and (s := hass.states.get(e.entity_id)) is not None}
    levende = [e for e in entiteter if e.entity_id in st]
    enhed = lambda e: st[e.entity_id].attributes.get("unit_of_measurement")  # noqa: E731
    dom = lambda d: [e for e in levende if e.domain == d]  # noqa: E731
    platform = levende[0].platform if levende else ""
    d = {"slags": "entiteter", "maerke": MAERKER.get(platform, ""), "langsom": platform in SKY,
         "effekt": _bedst([e for e in dom("sensor") if enhed(e) in ("W", "kW")], "effekt"),
         "strom": _bedst([e for e in dom("number") if enhed(e) == "A"], "strom"),
         "status": _bedst([e for e in dom("sensor") if enhed(e) is None and BIL.search(st[e.entity_id].state)], "status"),
         "til_fra": _bedst(dom("switch"), "kontakt")}
    if d["status"] is None:
        stik = [e for e in dom("binary_sensor") if st[e.entity_id].attributes.get("device_class") == "plug" or re.search(r"(car|vehicle|cable|plug)\w*connected|connected$", _noegle(e))]
        d["status"] = stik[0].entity_id if stik else None
    if d["til_fra"]:
        d["omvendt"] = "pause" in _noegle(next(e for e in levende if e.entity_id == d["til_fra"])) and platform != "wallbox"  # Wallbox: til = lader
    else:
        for e in dom("select"):
            muligt = st[e.entity_id].attributes.get("options") or []
            par = next(((t, f) for t, f in VALG if t in muligt and f in muligt), None)
            if par and _bedst([e], "valg"):
                d.update(til_fra=e.entity_id, til_valg=par[0], fra_valg=par[1])
                break
        else:
            d.update(start=_bedst(dom("button"), "start"), stop=_bedst(dom("button"), "stop"))
    if platform == "easee":
        d.update(slags="easee", enhed=levende[0].device_id, strom=None, til_fra=None, start=None, stop=None)
    elif platform == "ocpp":
        tx = next((e.entity_id for e in dom("sensor") if "transaction_id" in _noegle(e)), None)
        dev = next((i[1] for i in getattr(dr.async_get(hass).async_get(levende[0].device_id), "identifiers", ()) if i[0] == "ocpp"), None)
        d.update(slags="ocpp" if tx and dev else "entiteter", transaktion=tx, devid=dev, strom=None)
    return {k: v for k, v in d.items() if v not in (None, "")}


def kan(hass: HomeAssistant, d: dict) -> tuple[bool, bool]:
    """(kan startes og stoppes, kan styres i strøm). Et strøm-tal alene kan kun stoppe laderen, hvis det kan sættes til 0 A."""
    til = bool(d.get("til_fra") or (d.get("start") and d.get("stop")) or d.get("slags") in ("easee", "ocpp"))
    s = hass.states.get(d.get("strom") or "")
    try:
        nul = s is not None and float(s.attributes.get("min", 1)) <= 0
    except (TypeError, ValueError):
        nul = False
    return til or nul, bool(d.get("strom") or d.get("slags") in ("easee", "ocpp"))


def fundne(hass: HomeAssistant) -> dict[str, tuple[str, dict]]:
    """enhed → (navn, roller) for de kendte ladere, der kan styres."""
    pr_enhed: dict[str, list] = {}
    for e in er.async_get(hass).entities.values():
        if e.platform in MAERKER and e.device_id:
            pr_enhed.setdefault(e.device_id, []).append(e)
    ud = {}
    for enhed, liste in pr_enhed.items():
        d = gaet(hass, liste)
        if d.get("effekt") and kan(hass, d)[0]:
            enh = dr.async_get(hass).async_get(enhed)
            ud[enhed] = (f"{d['maerke']} – {(enh and (enh.name_by_user or enh.name)) or enhed}", d)
    return ud


def fra_enhed(hass: HomeAssistant, enhed: str) -> dict:
    return gaet(hass, er.async_entries_for_device(er.async_get(hass), enhed))


def bil_fra(hass: HomeAssistant, soc: str) -> dict:
    """Ud fra bilens batteri-sensor findes stikket og rækkevidden på samme enhed."""
    reg = er.async_get(hass)
    e = reg.async_get(soc)
    andre = er.async_entries_for_device(reg, e.device_id) if e and e.device_id else []
    st = lambda x: hass.states.get(x.entity_id)  # noqa: E731
    stik = [x for x in andre if x.domain == "binary_sensor" and st(x) is not None and not re.search(r"lock|door|window|charging$", _noegle(x))
            and (st(x).attributes.get("device_class") == "plug" or re.search(r"plug|cable|charger_connected|stik", _noegle(x)))]
    km = [x for x in andre if x.domain == "sensor" and st(x) is not None and st(x).attributes.get("unit_of_measurement") in ("km", "mi")
          and re.search(r"range|r.kkevidde|remaining_distance", _noegle(x))]
    return {"bil_soc": soc, **({"bil_stik": stik[0].entity_id} if stik else {}), **({"bil_km": km[0].entity_id} if km else {})}


# --- prøven ---
PROEV_A, PROEV_OP_A = 6, 8
VENT_S, STOP_S = 110, 110  # nogle ladere måler kun en gang i minuttet


async def proev(hass: HomeAssistant, d: dict, sov=asyncio.sleep) -> dict:
    """Starter på 6 A, prøver 8 A og stopper igen. Svarene er det, laderen måler – ikke det, den siger. Stopper altid til sidst."""
    s = Styring(hass, type("E", (), {"data": {"lader": d}})())
    antal = 3 if int(d.get("faser") or 3) == 3 else 1
    volt = 230
    rum, over, _ = s._plads(0.0, antal)
    if rum is None:
        return {"fejl": "maalinger"}
    if s._effekt() is None:
        return {"fejl": "effekt"}
    if s._effekt() > 300:
        return {"fejl": "lader_allerede"}
    if s._tilsluttet() is False:
        return {"fejl": "frakoblet"}
    # strømmen sættes før start; holder laderen den ikke, ses det på hovedsikringen nedenfor. Kan den ikke skrues ned, skal der være plads til det hele
    if over or rum < (PROEV_OP_A + 2 if kan(hass, d)[1] else int(d.get("maks_a") or 16)):
        return {"fejl": "plads"}

    async def vent(opfyldt, sek) -> bool:
        for _ in range(sek // 3):
            w = s._effekt()
            if w is not None and opfyldt(w):
                return True
            if (p := s._plads(0.0, antal))[1]:  # hovedsikringen er overskredet
                return False
            await sov(3)
        return False
    ampere = lambda w: w / (antal * volt)  # noqa: E731
    r = {"start": False, "strom": False, "stop": False}
    try:
        await s.lader.lad(PROEV_A, True)
        r["start"] = await vent(lambda w: ampere(w) > 2, VENT_S)
        if not r["start"] and s._effekt() is None:
            r["fejl"] = "effekt_ingen"
        if r["start"] and kan(hass, d)[1]:
            await sov(20)  # bilen når op i strøm
            if await vent(lambda w: 4 <= ampere(w) <= PROEV_A + 1.5, VENT_S):
                await s.lader.lad(PROEV_OP_A, False)
                r["strom"] = await vent(lambda w: PROEV_OP_A - 1.5 <= ampere(w) <= PROEV_OP_A + 1.5, VENT_S)
    except (HomeAssistantError, TimeoutError, KeyError, ValueError, TypeError) as e:
        r["fejl"] = f"{type(e).__name__}: {str(e)[:120]}"
    finally:
        for _ in range(3):
            try:
                await asyncio.wait_for(s.lader.stop(), 30)
            except (HomeAssistantError, TimeoutError, KeyError, ValueError, TypeError):
                pass
            if await vent(lambda w: w < 300, STOP_S):
                r["stop"] = r["start"]  # et stop tæller kun, hvis den først ladede
                if d.get("til_fra") or d.get("stop") or d.get("slags") == "easee":
                    try:  # brugerens egen strøm tilbage (en lader, der kun stoppes med 0 A, bliver på 0 A)
                        await asyncio.wait_for(s.lader.slip(), 30)
                    except (HomeAssistantError, TimeoutError, KeyError, ValueError, TypeError):
                        pass
                break
    return r

