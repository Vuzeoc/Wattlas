"""Elbil-laderens beslutning: hvor mange ampere må og skal laderen have lige nu. Ingen Home Assistant her – kun tal ind og ud, så alt kan testes."""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite

TILSTANDE = ("fra", "stop", "lad_nu", "klar", "sol")
VENT_FASE_S = 60     # så længe holdes laveste strøm, hvis der er for lidt plads, før ladningen pauses
VENT_DATA_S = 120    # så længe tåles manglende målinger af huset
VENT_OP_S = 60       # der skal være plads så længe, før strømmen hæves
HVILE_S = 300        # pause efter et stop, så en kontaktor eller bil ikke klapper
HVILE_NU_S = 60      # … dog kun så længe, når brugeren selv har bedt om "lad nu"
AFVIG_A = 2          # så meget over grænsen må laderen måle
VAGT_S = 20          # … så længe, før grænsen sendes igen
VAGT_STOP_S = 45     # … og så længe, før der stoppes
TOMGANG_W = 300      # under dette lader bilen ikke
STOP_S = 30          # så længe må der gå fra stop til målt stop, før der sendes igen
STOP_FORSOEG = 3     # … og så mange forsøg, før brugeren får besked


def plads(faser_w: list, faser_v: list, graense_a: float, import_w: float, importloft_w: float, egen_w: float, antal: int) -> float | None:
    """Ampere pr. fase, laderen kan trække uden at en fase eller importloftet overskrides. None = målingerne kan ikke bruges.

    Laderens egen strøm ligger allerede i målingen og lægges til igen. Det holder også, når laderens fase er ukendt: den mindste
    plads + egen strøm er aldrig mere end pladsen på laderens egen fase + egen strøm."""
    if len(faser_w) != 3 or len(faser_v) != 3 or antal not in (1, 3):
        return None
    if not all(isinstance(x, (int, float)) and isfinite(x) for x in (*faser_w, *faser_v, graense_a, import_w, importloft_w, egen_w)):
        return None
    if graense_a <= 0 or importloft_w <= 0 or egen_w < 0 or not all(210 <= v <= 250 for v in faser_v):
        return None
    egen_a = egen_w / (antal * max(faser_v))
    fase = min(graense_a - w / v for w, v in zip(faser_w, faser_v)) + egen_a
    loft = (importloft_w - import_w) / (antal * max(faser_v)) + egen_a
    return min(fase, loft)


@dataclass
class Ind:
    nu: float                  # sekunder, kun stigende
    tilstand: str
    tilsluttet: bool | None    # None = ukendt
    maks_a: int
    min_a: int = 6
    plads_a: float | None = None
    over_sikring: bool = False
    plan: bool = False         # planen vil lade nu
    noed: bool = False         # nås kun, hvis der lades fra nu af
    faerdig: bool = False
    vent_op_s: float = VENT_OP_S
    sol_a: float = 0.0         # solens overskud i ampere pr. fase, laderens egen strøm talt med
    sol_faerdig: bool = False  # bilen har nået det, solen må lade den op til


@dataclass
class Husk:
    sat: int = 0               # den strøm, Wattlas har bedt om (0 = stop)
    stoppet: float = -1e9      # hvornår ladningen sidst blev stoppet
    trang: float | None = None  # siden hvornår pladsen har været under laveste strøm
    blind: float | None = None  # siden hvornår målingerne har manglet
    over: float | None = None   # siden hvornår hovedsikringen har været overskredet
    rum: float | None = None    # siden hvornår der har været plads til mere


def _oensket(i: Ind) -> int:
    """Det, brugeren og planen vil have, uden hensyn til pladsen. Fuld strøm eller ingenting (sol: det, solen rækker til).
    "Klar til tid" tager også gratis sol uden for de planlagte timer, til bilen har nået solens grænse."""
    if i.tilsluttet is False or i.tilstand not in ("lad_nu", "klar", "sol"):
        return 0
    if i.tilstand == "lad_nu":
        return i.maks_a
    sol = floor(i.sol_a) if isfinite(i.sol_a) else 0
    paa_sol = min(i.maks_a, sol) if sol >= i.min_a else 0
    if i.tilstand == "sol":
        return paa_sol  # "Kun sol": til bilen selv stopper, som før
    if not i.faerdig and (i.plan or i.noed):
        return i.maks_a
    return 0 if i.sol_faerdig else paa_sol


def beslut(i: Ind, h: Husk) -> tuple[int | None, str]:
    """(ampere, grund). 0 = stop, None = rør ikke laderen. Retter h. Ned går det straks, op går det langsomt."""
    if i.tilstand not in TILSTANDE or i.tilstand == "fra":
        h.sat, h.trang, h.blind, h.over, h.rum = 0, None, None, None, None
        return None, "fra"
    rum = i.plads_a if i.plads_a is not None and isfinite(i.plads_a) else None
    if not 0 < i.min_a <= i.maks_a:
        return _stop(i, h, "grænser")
    vil = _oensket(i)
    h.blind = None if rum is not None else (i.nu if h.blind is None else h.blind)
    h.over = None if not i.over_sikring else (i.nu if h.over is None else h.over)
    if vil == 0:
        return _stop(i, h, "frakoblet" if i.tilsluttet is False else i.tilstand if i.tilstand in ("stop", "sol") else "færdig" if i.faerdig else "venter")
    if h.sat == 0:
        hvile = HVILE_NU_S if i.tilstand == "lad_nu" else HVILE_S
        if rum is None:
            return 0, "målinger mangler"
        if i.over_sikring or i.tilsluttet is None:
            return 0, "over sikring" if i.over_sikring else "status ukendt"
        if rum < min(vil, i.min_a + 1):  # 1 A luft over laveste, så den ikke starter og stopper
            return 0, "ingen plads"
        if i.nu - h.stoppet < hvile:
            return 0, "hviler"
        h.trang = h.rum = None
        h.sat = floor(min(vil, rum))
        return h.sat, "starter"
    if i.over_sikring and i.nu - h.over >= VENT_FASE_S:
        return _stop(i, h, "over sikring")
    if rum is None:
        if i.nu - h.blind >= VENT_DATA_S:
            return _stop(i, h, "målinger mangler")
        if i.over_sikring:
            h.sat = i.min_a
        return h.sat, "målinger mangler"
    ny = floor(min(vil, rum, i.min_a if i.over_sikring else vil))
    if ny < i.min_a:
        h.rum = None
        h.trang = i.nu if h.trang is None else h.trang
        if i.nu - h.trang >= VENT_FASE_S:
            return _stop(i, h, "ingen plads")
        h.sat = min(h.sat, i.min_a)
        return h.sat, "lidt plads"
    h.trang = None
    if ny <= h.sat:
        h.rum = None
        h.sat = ny
        return ny, "lader" if ny == vil else "faserne"
    h.rum = i.nu if h.rum is None else h.rum
    if i.nu - h.rum >= i.vent_op_s and (ny == vil or ny - h.sat >= 2):
        h.rum, h.sat = None, ny
    return h.sat, "lader" if h.sat == vil else "faserne"


def _stop(i: Ind, h: Husk, grund: str) -> tuple[int, str]:
    if h.sat:
        h.stoppet = i.nu
    h.sat, h.trang, h.rum = 0, None, None
    return 0, grund


@dataclass
class Vagt:
    """Ser på det, laderen måler – ikke på det, den svarer."""
    over: float | None = None
    stop: float | None = None
    forsoeg: int = 0


def vagt(nu: float, sat: int, effekt_w: float | None, antal: int, volt: float, v: Vagt) -> str | None:
    """None, 'send' (grænsen igen), 'nødstop' (over grænsen), 'stop' (igen) eller 'stopper ikke'. Kaldes kun, mens Wattlas styrer laderen."""
    if effekt_w is None or not isfinite(effekt_w):
        return None
    if sat == 0:
        v.over = None
        if effekt_w < TOMGANG_W:
            v.stop, v.forsoeg = None, 0
            return None
        v.stop = nu if v.stop is None else v.stop
        if nu - v.stop < STOP_S:
            return None
        v.stop, v.forsoeg = nu, v.forsoeg + 1
        return "stopper ikke" if v.forsoeg >= STOP_FORSOEG else "stop"
    v.stop, v.forsoeg = None, 0
    if effekt_w / (antal * volt) <= sat + AFVIG_A:
        v.over = None
        return None
    v.over = nu if v.over is None else v.over
    if nu - v.over >= VAGT_STOP_S:
        return "nødstop"
    return "send" if nu - v.over >= VAGT_S else None


TAB = 0.9  # fra laderen til bilens batteri


def bil_rest(soc: float, maal: float, bil_kwh: float, ladet_siden: float) -> float:
    """kWh fra laderen, før bilen når målet. Bilens tal kan være timer gammelt: det, der er ladet, siden det sidst ændrede sig, trækkes fra."""
    return max(0.0, (maal - soc) / 100 * bil_kwh / TAB - max(0.0, ladet_siden))


def noedvendig(rest: float, maks_a: int, antal: int, volt: float, timer: float) -> tuple[bool, bool]:
    """(færdig, nød): nød = resten (kWh) nås kun ved at lade fuldt fra nu af, med en halv times og 10 % luft."""
    if rest <= 0.05:
        return True, False
    return False, timer <= rest / (maks_a * antal * volt / 1000) * 1.1 + 0.5
