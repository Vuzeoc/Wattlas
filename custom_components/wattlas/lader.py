"""Styring af en elbil-lader gennem den integration, brugeren allerede har i Home Assistant.

Laderen kendes kun ved sine roller (status, effekt, til/fra, strøm); en oversætter pr. slags gør resten. Beslutningen og vagterne er rene tal i
lader_logik.py. Wattlas tror ikke på svaret fra en lader, kun på den effekt, den måler."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from math import isfinite
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import lader_logik as logik
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
TRIN_S = 10
KALD_S = 20          # så længe må ét kald til laderen tage
IKKE_LADER_S = 180   # tager bilen ikke imod i så lang tid, holdes pause (fuld, sover eller venter på sin egen tidsplan)
PROEV_IGEN_S = 1800
MAALER_S = 100       # så længe ventes der på en måling, der er nyere end ordren
SVAR_S = 8           # bilens reaktionstid
UDENFOR_S = 60       # så længe må laderen trække, uden at husets måling viser det
LANGSOM_S = 900      # sky-ladere hæves højst hvert kvarter (sænkes altid straks)
PLAN_S = 720         # planens højeste alder
TUR = "input_boolean.wattlas_lader_tur"  # "100 % til næste tur"
PROBLEMER = ("lader_stopper_ikke", "lader_over_graense", "lader_udenfor", "lader_svarer_ikke")
FRI = {"disconnected", "not_connected", "no_ev_connected", "unplugged", "available", "idle", "charger_free", "a_not_connected", "free", "ready", "locked", "a", "1"}  # Wallbox: Ready/Locked uden bil ("Locked, car connected" med)
MAAL_V = 230.0
I_GANG = {"charging", "suspendedev", "suspendedevse"}
HVILER = {"available", "preparing", "finishing"}
NOEGLE = f"{DOMAIN}_lader"  # hass.data: den kørende styring


def _tal(s) -> float | None:
    try:
        v = float(s.state)
    except (AttributeError, TypeError, ValueError):
        return None
    return v if isfinite(v) else None


class Entiteter:
    """Lader med almindelige entiteter: kontakt, knapper eller valg til start/stop, og evt. et tal til strømmen."""

    def __init__(self, hass: HomeAssistant, d: dict) -> None:
        self.hass, self.d, self.egen = hass, d, None  # egen = brugerens egen strøm, før Wattlas ændrede den

    async def _kald(self, domain: str, service: str, data: dict) -> None:
        await asyncio.wait_for(self.hass.services.async_call(domain, service, data, blocking=True), KALD_S)

    async def _kontakt(self, til: bool) -> None:
        d = self.d
        if e := d.get("til_fra"):
            if e.startswith("select."):
                await self._kald("select", "select_option", {"entity_id": e, "option": d["til_valg" if til else "fra_valg"]})
            else:
                await self._kald("homeassistant", "turn_on" if til != bool(d.get("omvendt")) else "turn_off", {"entity_id": e})
        elif knap := d.get("start" if til else "stop"):
            await self._kald("button", "press", {"entity_id": knap})

    async def graense(self, a: int) -> None:
        if not (e := self.d.get("strom")):
            return
        nu = _tal(self.hass.states.get(e))
        if self.egen is None and nu:
            self.egen = nu  # shortcut: kun i hukommelsen; efter en genstart kendes brugerens egen strøm ikke
        await self._kald("number", "set_value", {"entity_id": e, "value": a})

    async def lad(self, a: int, start: bool) -> None:
        await self.graense(a)  # strømmen først, så den aldrig starter for højt
        if start:
            await self._kontakt(True)

    async def stop(self) -> None:
        if any(self.d.get(k) for k in ("til_fra", "stop")):
            await self._kontakt(False)
        else:
            await self.graense(0)  # opsætningen tillader det kun, når tallet kan sættes til 0

    async def slip(self) -> None:
        if self.egen is not None and self.d.get("strom"):
            await self._kald("number", "set_value", {"entity_id": self.d["strom"], "value": self.egen})
            self.egen = None


class Ocpp(Entiteter):
    """OCPP 1.6-J gennem HA's OCPP-integration. Strømmen og stoppet sendes som en profil for den igangværende transaktion (hele tal): mange ladere
    ignorerer en grænse i startbeskeden og kan ikke de faste grænser. Integrationens egen stop-kontakt (RemoteStop) bruges aldrig: den kan lade bilen
    fortsætte på 6 A, mens HA viser 0 W. Stop = 0 A på transaktionen."""

    def __init__(self, hass: HomeAssistant, d: dict) -> None:
        super().__init__(hass, d)
        self.tx = 0  # HA glemmer nummeret, når en transaktion meldes slut – laderen kan stadig lade på det

    def _status(self) -> str:
        s = self.hass.states.get(self.d.get("status") or "")
        return s.state.lower() if s else "charging"  # ingen status: nummeret alene afgør det

    def _transaktion(self) -> int:
        if nu := int(_tal(self.hass.states.get(self.d["transaktion"])) or 0):
            self.tx = nu
        return nu

    async def graense(self, a: int) -> None:
        self._transaktion()
        if not self.tx:
            raise HomeAssistantError("ingen transaktion")
        await self._kald("ocpp", "set_charge_rate", {"devid": self.d["devid"], "conn_id": 1, "custom_profile": {  # hele tal: 8.0 afvises af nogle
            "chargingProfileId": 1, "stackLevel": 0, "chargingProfilePurpose": "TxProfile", "chargingProfileKind": "Relative", "transactionId": self.tx,
            "chargingSchedule": {"chargingRateUnit": "A", "chargingSchedulePeriod": [{"startPeriod": 0, "limit": int(a)}]}}})

    async def lad(self, a: int, start: bool) -> None:
        foer = self._transaktion() or self.tx
        # i gang (eller kun pauset af en grænse på 0 A): så er grænsen nok. HA kan vise et gammelt nummer, derfor ses der også på status
        if start and not (self._transaktion() and self._status() in I_GANG):
            await self._kontakt(True)
            for _ in range(KALD_S * 4):  # grænsen skal være der, før bilen når op i strøm
                if (nu := self._transaktion()) and (nu != foer or self._status() in I_GANG):
                    break
                await asyncio.sleep(.25)
            else:
                raise HomeAssistantError("ingen ny transaktion")
        await self.graense(a)

    async def stop(self) -> None:
        self._transaktion()
        if self.tx:
            await self.graense(0)

    async def slip(self) -> None:
        if self._transaktion():  # en 0 A-grænse gælder resten af transaktionen: giv laderen dens strøm tilbage
            await self.graense(int(self.d.get("maks_a") or 16))


class Easee(Entiteter):
    """Kun den dynamiske grænse (flygtig): de andre gemmes i laderens flash og slides."""

    async def graense(self, a: int) -> None:
        await self._kald("easee", "set_charger_dynamic_limit", {"device_id": self.d["enhed"], "current": int(a)})

    async def _kontakt(self, til: bool) -> None:
        await self._kald("easee", "action_command", {"device_id": self.d["enhed"], "action_command": "resume" if til else "pause"})

    async def stop(self) -> None:
        await self._kontakt(False)

    async def slip(self) -> None:
        await self.graense(32)  # tjenestens højeste: laderens egne faste grænser gælder så igen


SLAGS = {"entiteter": Entiteter, "ocpp": Ocpp, "easee": Easee}


class Styring:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass, self.d = hass, entry.data["lader"]
        self.hold_kan = entry.data.get("kanal") != "sonnen"  # Sonnen kan ikke holde batteriet
        self.lader = SLAGS[self.d["slags"]](hass, self.d)
        self.husk, self.vagt, self.laas = logik.Husk(), logik.Vagt(), asyncio.Lock()
        self.sendt: int | None = None       # det, laderen sidst fik besked om (None = Wattlas styrer den ikke)
        self.fejl, self.tom, self.pause, self.udenfor = 0, None, None, None
        self.rest, self.foer, self.tilstand, self.meldt = 0.0, None, None, None
        self.tilsluttet_foer: bool | None = None
        self.af: list = []
        self.soc: tuple = (None, 0.0)  # bilens seneste procent og det, der var ladet, da den kom
        self.pause_grund = ""
        self.lukket = False
        self.sendt_nu, self.sendt_tid = -1e9, dt_util.utcnow()
        self.frist = None  # den seneste "klar kl."

    # --- aflæsning ---
    def _v(self, e: str, std: float | None = None) -> float | None:
        v = _tal(self.hass.states.get(e))
        return std if v is None else v

    def _ny_maaling(self, nu: float) -> bool:
        """Er laderens måling kommet efter den seneste ordre? Nogle melder kun hvert minut, og en gammel måling må ikke udløse vagten. Melder den
        slet ikke (kun ved ændring, og intet ændrer sig), bruges den alligevel efter MAALER_S."""
        if nu - self.sendt_nu >= MAALER_S:
            return True
        s = self.hass.states.get(self.d["effekt"])
        return s is not None and (s.last_reported - self.sendt_tid).total_seconds() >= SVAR_S

    def _effekt(self) -> float | None:
        s = self.hass.states.get(self.d["effekt"])
        v = _tal(s)
        # OCPP: effekten meldes kun under ladning, og HA viser den sidste værdi videre bagefter. Siger laderen selv, at den ikke lader, er det 0 W
        st = self.hass.states.get(self.d.get("status") or "")
        if self.d["slags"] == "ocpp" and st is not None and st.state.lower() in HVILER:
            return 0.0
        if v is None:
            return None
        return v * (1000 if s.attributes.get("unit_of_measurement") == "kW" else 1)

    def _tilsluttet(self) -> bool | None:
        if not (e := self.d.get("status")):
            return True  # ingen status: laderen finder selv ud af det
        s = self.hass.states.get(e)
        if s is None or s.state in ("unknown", "unavailable", ""):
            return None
        if e.startswith("binary_sensor."):
            return s.state == "on"
        return s.state.strip().lower().replace(" ", "_") not in FRI

    def _plads(self, egen: float, antal: int) -> tuple[float | None, bool, float]:
        """(plads pr. fase, over hovedsikringen, spænding)"""
        if not self.hass.states.is_state("binary_sensor.emhass_ui_data_frisk", "on"):
            return None, False, MAAL_V
        w = [self._v(f"sensor.emhass_m_external_ct_w_l{i}") for i in (1, 2, 3)]
        v = [self._v(f"sensor.emhass_m_grid_current_v_l{i}") for i in (1, 2, 3)]
        g, loft = self._v("input_number.wattlas_fase_graense_a"), self._v("input_number.wattlas_import_graense_w")
        rum = logik.plads(w, v, g, self._v("sensor.emhass_m_grid_out_total_power"), loft, egen, antal)
        if rum is None:
            return None, False, MAAL_V
        sikring = max(self._v("input_number.wattlas_sikring_a", 0), g)
        return rum, any(p > sikring * u for p, u in zip(w, v)), max(v)

    def _plan(self) -> bool:
        s = self.hass.states.get("sensor.wattlas_lader_plan")
        return (_tal(s) or 0) > 50 and (dt_util.utcnow() - s.last_reported).total_seconds() < PLAN_S \
            and not self.hass.states.is_state("binary_sensor.emhass_ui_planfejl", "on")

    def _bil(self, tilsluttet, ladet: float) -> tuple[float | None, float | None, float | None]:
        """(bilens procent, kWh der mangler til målet, kWh der mangler til solens grænse). Kun når bilen er i HA og sidder i laderen – ellers
        None, og så gælder det valgte antal kWh (og solen lader, til bilen selv stopper)."""
        d = self.d
        v = self._v(d.get("bil_soc") or "")
        hjemme = not d.get("bil_stik") or self.hass.states.is_state(d["bil_stik"], "on")  # en gæst i laderen er ikke brugerens bil
        if v is None or not 0 <= v <= 100 or not d.get("bil_kwh") or tilsluttet is not True or not hjemme:
            self.soc = (None, 0.0)
            return None, None, None
        if self.soc[0] != v:
            self.soc = (v, ladet)
        # "100 % til næste tur" løfter målet, til bilen kobles fra. Solen må lade op til sin egen grænse, dog aldrig under målet
        maal = 100.0 if self.hass.states.is_state(TUR, "on") else self._v("input_number.wattlas_lader_maal", 80.0)
        sol = max(maal, self._v("input_number.wattlas_lader_sol_maal", 100.0))
        kwh, siden = float(d["bil_kwh"]), ladet - self.soc[1]
        return v, logik.bil_rest(v, maal, kwh, siden), logik.bil_rest(v, sol, kwh, siden)

    def _timer(self) -> tuple[float, str, bool]:
        """Timer til "klar kl.", klokkeslættet, og om fristen lige er passeret (så begynder en ny periode)."""
        s = self.hass.states.get("input_datetime.wattlas_lader_klar")
        t = dt_util.parse_time(s.state) if s else None
        if t is None:
            return 24.0, "", False
        nu = dt_util.now()
        dl = nu.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if dl <= nu:
            dl += timedelta(days=1)
        if self.frist is None:  # efter en genstart: sidste melding før den seneste frist = HA var nede, da fristen passerede
            s0 = self.hass.states.get("sensor.wattlas_lader")
            sidst = dt_util.parse_datetime(str(s0.attributes.get("tid"))) if s0 is not None else None
            passeret = sidst is not None and sidst < dl - timedelta(days=1)
        else:
            passeret = nu >= self.frist
        self.frist = dl
        return (dl.timestamp() - nu.timestamp()) / 3600, t.strftime("%H:%M"), passeret  # timestamp: rigtige timer, også ved sommertid

    # --- kørsel ---
    async def trin(self, _nu=None) -> None:
        if self.laas.locked() or self.lukket:  # en langsom lader: ét kald ad gangen. Lukket: aldrig igen
            return
        async with self.laas:
            try:
                await self._trin()
            except Exception:  # en fejl her må ikke stoppe vagten næste gang
                _LOGGER.exception("Wattlas: elbil-lader")

    async def _trin(self) -> None:
        nu = monotonic()
        tilstand = getattr(self.hass.states.get("input_select.wattlas_lader_tilstand"), "state", "fra")
        if tilstand != self.tilstand:
            self.pause = self.tom = None
            self.tilstand = tilstand
        effekt, tilsluttet = self._effekt(), self._tilsluttet()
        antal = 3 if int(self.d.get("faser") or 3) == 3 else 1
        egen = max(0.0, self._v("sensor.wattlas_elbil_effekt", 0.0))  # 0, når laderen sidder uden for husets måling
        # højst det, Wattlas har bedt om: en gammel måling fra før en sænkning ville ellers give plads, der ikke findes
        rum, over, volt = self._plads(egen if self.sendt is None else min(egen, self.sendt * antal * MAAL_V), antal)
        timer, klar, ny_periode = self._timer()
        ladet = await self._tael(nu, effekt, tilsluttet, ny_periode)
        maks = min(int(self._v("input_number.wattlas_lader_maks_a", 0)), int(self.d.get("maks_a") or 32))  # aldrig over opsætningens (laderens) grænse
        mini = max(6, int(self.d.get("min_a") or 6))
        fast = self.d["slags"] == "entiteter" and not self.d.get("strom")
        if fast:  # kan ikke skrues ned: den trækker sin egen strøm, fuld eller ingenting
            mini = maks = int(self.d.get("maks_a") or maks)
        kwh = self._v("input_number.wattlas_lader_kwh", 0.0)
        soc, rest, rest_sol = self._bil(tilsluttet, ladet)
        rest = max(0.0, kwh - ladet) if rest is None else rest
        # "100 % til næste tur" slår fra af sig selv: bilen er kørt (laderen eller bilens eget stik siger det), eller den er fuld
        stik_ud = bool(self.d.get("bil_stik")) and self.hass.states.is_state(self.d["bil_stik"], "off")
        if self.hass.states.is_state(TUR, "on") and (tilsluttet is False or stik_ud or (soc is not None and soc >= 99)):
            await self.hass.services.async_call("input_boolean", "turn_off", {"entity_id": TUR})
        # lader bilen kun på én fase (mange biler), regnes tiden ud fra det målte, ikke fra opsætningens faser
        antal_e = 1 if antal == 3 and self.sendt and effekt is not None and logik.TOMGANG_W < effekt < 1.5 * self.sendt * volt else antal
        faerdig, noed = logik.noedvendig(rest, maks, antal_e, volt, timer) if maks > 0 else (False, False)
        # solens overskud: det, huset ikke selv bruger, og som planen ikke lader husbatteriet med (planens tal, ikke det målte – bilen ændrer det målte)
        styrer = all(self.hass.states.is_state(e, "on") for e in ("input_boolean.emhass_styring_aktiv", "input_boolean.emhass_har_overtaget", "input_boolean.emhass_plan_gyldig"))
        batt = max(0.0, -self._v("input_number.emhass_plan_batteri_w", 0.0)) if styrer else 0.0  # en gammel planværdi tæller ikke
        sol = (self._v("sensor.emhass_solproduktion_samlet", 0.0) - self._v("sensor.emhass_m_load_w_totalpower", 1e9) + egen - batt) / (antal * volt)
        ind = logik.Ind(nu=nu, tilstand=tilstand, tilsluttet=tilsluttet, maks_a=maks, min_a=mini, plads_a=rum, over_sikring=over,
                        plan=self._plan(), noed=noed, faerdig=faerdig, sol_a=sol, sol_faerdig=rest_sol is not None and rest_sol <= 0.05, vent_op_s=LANGSOM_S if self.d.get("langsom") else logik.VENT_OP_S)
        if effekt is None or not self.hass.states.is_state("binary_sensor.wattlas_konfigureret", "on"):
            ind.plads_a = None  # ingen måling af laderen, eller Wattlas er ikke klar: ingen start, og stop efter to minutter
        ordre, grund = logik.beslut(ind, self.husk)
        ordre, grund = self._undtagelser(nu, ordre, grund, effekt, egen, tilsluttet)
        skygge = self.hass.states.is_state("input_boolean.wattlas_skygge", "on")
        await self._udfoer(nu, None if skygge else ordre, effekt, antal, volt)  # skygge: laderen slippes (som "fra") og vises kun
        await self._reserve(0 if skygge or ordre is None or grund in ("bilen tager ikke imod", "effekten mangler", "hviler") else logik._oensket(ind), ordre or 0)
        self._meld({"grund": grund, "ordre_a": ordre, "effekt_w": None if effekt is None else round(effekt), "plads_a": None if rum is None else round(rum, 1),
                    "tilsluttet": tilsluttet, "rest_kwh": round(rest, 1), "bil_soc": soc, "bil_km": self._v(self.d.get("bil_km") or "") if soc is not None else None, "klar": klar, "p_maks_w": round(maks * antal_e * volt), "noed": noed and tilstand == "klar",
                    "skygge": skygge, "fejl": self.fejl, "fast_a": fast, "hold_kan": self.hold_kan})

    def _undtagelser(self, nu: float, ordre, grund, effekt, egen, tilsluttet):
        """Laderen trækker uden for husets måling, eller bilen tager ikke imod."""
        if ordre is None:
            self.udenfor = self.tom = self.pause = None
            return ordre, grund
        if effekt is not None and effekt > 1000 and egen <= 0:
            self.udenfor = nu if self.udenfor is None else self.udenfor
            if nu - self.udenfor >= UDENFOR_S:  # faserne passes ikke: strømmen ses ikke i husets måling
                self._problem("lader_udenfor")
                self._nulstil(nu)
                self.pause, self.pause_grund = nu, "uden for målingen"  # prøv først igen om en halv time
                return 0, "uden for målingen"
        else:
            self.udenfor = None
        if tilsluttet is False:
            self.pause = None
        if effekt is None and self.sendt and ordre == 0:
            self.pause, self.pause_grund = nu, "effekten mangler"
        if ordre and effekt is not None and effekt < logik.TOMGANG_W and self.sendt:
            self.tom = nu if self.tom is None else self.tom
            if nu - self.tom >= IKKE_LADER_S:
                self.pause, self.tom, self.pause_grund = nu, None, "bilen tager ikke imod"
        else:
            self.tom = None
        if self.pause is not None:
            if nu - self.pause < PROEV_IGEN_S and (ordre or grund == "hviler"):
                if ordre:
                    self._nulstil(nu)
                return 0, self.pause_grund
            if nu - self.pause >= PROEV_IGEN_S:
                self.pause = None
        return ordre, grund

    def _nulstil(self, nu: float) -> None:
        self.husk.sat, self.husk.stoppet = 0, nu

    async def _udfoer(self, nu: float, ordre: int | None, effekt, antal: int, volt: float) -> None:
        if ordre is None:
            if self.sendt is not None:
                self.sendt = None
                self.vagt = logik.Vagt()
                await self._proev(self.lader.slip())
            return
        besked = logik.vagt(nu, self.sendt or 0, effekt, antal, volt, self.vagt) if self.sendt is not None and self._ny_maaling(nu) else None
        if besked == "nødstop":
            self._problem("lader_over_graense")
            self._nulstil(nu)
            ordre = 0
        elif besked == "stopper ikke":
            self._problem("lader_stopper_ikke")
        if ordre == self.sendt and besked is None:
            return
        if ordre == 0 and self.sendt is None and effekt is not None and effekt < logik.TOMGANG_W:
            self.sendt = 0  # står beviseligt stille: ingen grund til at skrive (ukendt effekt = stop sendes)
            return
        start = ordre > 0 and not self.sendt
        self.sendt_nu, self.sendt_tid = nu, dt_util.utcnow()
        if await self._proev(self.lader.lad(ordre, start) if ordre else self.lader.stop()):
            self.sendt = ordre
        elif ordre:
            if self.sendt and ordre < self.sendt:  # en sænkning, der ikke kom igennem: stop i stedet for at vente på vagten
                await self._proev(self.lader.stop())
            self._nulstil(nu)  # kunne ikke sættes: så regnes den som stoppet, og vagten holder øje med det målte
            self.sendt = 0

    async def _proev(self, kald) -> bool:
        try:
            await asyncio.wait_for(kald, 3 * KALD_S)
        except (HomeAssistantError, TimeoutError, KeyError, ValueError, TypeError) as e:
            self.fejl += 1
            _LOGGER.warning("Wattlas: laderen tog ikke imod (%s: %s)", type(e).__name__, str(e)[:200])
            if self.fejl >= 3:
                self._problem("lader_svarer_ikke")
            return False
        self.fejl = 0
        ir.async_delete_issue(self.hass, DOMAIN, "lader_svarer_ikke")
        return True

    async def _tael(self, nu: float, effekt, tilsluttet, ny_periode: bool = False) -> float:
        """Energi siden bilen blev tilsluttet, eller siden sidste "klar kl." (hjælperen, så den overlever en genstart)."""
        e = "input_number.wattlas_lader_ladet"
        ladet = self._v(e, 0.0)
        if ny_periode or tilsluttet is False and self.tilsluttet_foer is not False:
            self.rest, self.soc = 0.0, (None, 0.0)
            if ladet:
                await self.hass.services.async_call("input_number", "set_value", {"entity_id": e, "value": 0}, blocking=True)
                ladet = 0.0
        if tilsluttet is not None:
            self.tilsluttet_foer = tilsluttet
        if self.foer is not None and effekt is not None and effekt > 0:
            self.rest += effekt * min(nu - self.foer, 60) / 3.6e6
        self.foer = nu
        if self.rest >= .05:
            ladet = min(500.0, ladet + self.rest)
            self.rest = 0.0
            await self.hass.services.async_call("input_number", "set_value", {"entity_id": e, "value": round(ladet, 2)}, blocking=True)
        return ladet + self.rest

    async def _reserve(self, vil: int, ordre: int) -> None:
        """Netladning af batteriet viger for bilen (emhass_reguler læser reserven, højst i fem minutter)."""
        e = "input_number.wattlas_lader_reserve"
        w = round(3 * max(0, vil - ordre) * MAAL_V) if vil and self.hass.states.is_state("switch.wattlas_netladning", "on") else 0
        if (nu := self._v(e)) is not None and nu != w:
            await self.hass.services.async_call("input_number", "set_value", {"entity_id": e, "value": w}, blocking=True)

    def _problem(self, navn: str) -> None:
        ir.async_create_issue(self.hass, DOMAIN, navn, is_fixable=False, is_persistent=False, severity=ir.IssueSeverity.ERROR, translation_key=navn)

    def _meld(self, d: dict) -> None:
        minut = int(monotonic() // 60)
        if self.meldt != (noegle := (d["grund"], d["ordre_a"], d["tilsluttet"], minut)):
            self.meldt = noegle
            self.hass.bus.async_fire("wattlas_lader", d)

    async def luk(self, _ev=None) -> None:
        """Home Assistant lukker, eller Wattlas fjernes: en bil må ikke lade uden fasevagt. Når HA lukker, når det ikke altid frem (OCPP lukker
        forbindelsen først – set i test-VM'en). Laderens egen maksstrøm er bagstopper."""
        kun_strom = self.d["slags"] == "ocpp" or self.d["slags"] == "entiteter" and not (self.d.get("til_fra") or self.d.get("stop"))
        self.lukket = True
        async with self.laas:
            if self.sendt or self.husk.sat:  # også et trin, der blev afbrudt midt i en start
                await self._proev(self.lader.stop())
            # HA lukker: en lader, der kun stoppes med 0 A, ville starte på brugerens strøm uden fasevagt. Når Wattlas fjernes, gives den tilbage
            if self.sendt is not None and not (_ev is not None and kun_strom):
                await self._proev(self.lader.slip())
            self.sendt = None


async def aktiver(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """(Gen)starter styringen efter opsætningen. Den gamle slipper laderen først."""
    await afslut(hass)
    if (entry.data.get("lader") or {}).get("slags") not in SLAGS:
        return
    s = Styring(hass, entry)
    s.af = [async_track_time_interval(hass, s.trin, timedelta(seconds=TRIN_S), cancel_on_shutdown=True), hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, s.luk)]
    hass.data[NOEGLE] = s


async def afslut(hass: HomeAssistant) -> None:
    for p in PROBLEMER:
        ir.async_delete_issue(hass, DOMAIN, p)
    if s := hass.data.pop(NOEGLE, None):
        for af in s.af:
            af()
        await s.luk()
