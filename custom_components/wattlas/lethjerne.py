"""Wattlas' lette hjerne: en lille optimering i stedet for EMHASS-app'en (til maskiner, der ikke kan bære EMHASS).

Tager præcis den samme bestilling, som Wattlas sender til EMHASS (naive-mpc-optim: prognoser, priser, batteri, grænser, fleksible laster), og
giver en plan i samme form. Batteriet planlægges med dynamisk programmering på et SOC-gitter (billigste vej gennem tidstrinnene, inkl. slid);
fleksible laster lægges først i deres billigste tidstrin. Ingen Home Assistant-importer: rene tal ind og ud, så det kan testes og måles alene.
Planen er et forslag – reguleringen, grænserne og kontrollen af planen i Wattlas gælder uændret bagefter (også mod denne plan).
Målt mod EMHASS 0.19 på samme prognoser (12 novemberdøgn, analyse_25-11/hjerne.py): 152,8 mod 152,4 kr./døgn."""
from __future__ import annotations

import math

GITTER = 80        # SOC-trin: flere = mere præcist og langsommere (tiden vokser ca. med kvadratet)
MAKS_TRIN = 400    # loftet, når trinnet gøres mindre for at følge en lav effekt
INF = float("inf")


class PlanFejl(Exception):
    """Opgaven kan ikke løses (fx et slut-niveau, der ikke kan nås) eller bestillingen mangler noget."""


def _liste(d: dict, navn: str, n: int, std: float | None = None) -> list[float]:
    v = d.get(navn)
    if v is None:
        if std is None:
            raise PlanFejl(f"{navn} mangler")
        return [float(std)] * n
    if not isinstance(v, (list, tuple)) or len(v) < n:
        raise PlanFejl(f"{navn} har {len(v) if isinstance(v, (list, tuple)) else 0} værdier, {n} kræves")
    try:
        ud = [float(x) for x in v[:n]]
    except (TypeError, ValueError):
        raise PlanFejl(f"{navn} har en værdi, der ikke er et tal") from None
    if not all(math.isfinite(x) for x in ud):
        raise PlanFejl(f"{navn} har en værdi, der ikke er et tal")
    return ud


def _laster(d: dict, n: int, h: float, last: list[float], pv: list[float], koeb: list[float], salg: list[float], imp: float) -> list[list[float]]:
    """Fleksible laster (tænd/sluk med fast effekt): hver lægges i sine billigste tidstrin inden for vinduet. Prisen pr. trin er købsprisen –
    eller salgsprisen, når solens overskud dækker lasten (så bruges sol, der ellers blev solgt). Kun trin med plads under importloftet: ellers
    ville planen overskride loftet og blive afvist af Wattlas' kontrol (så hellere en fejl, så Wattlas prøver igen uden lasten)."""
    antal = int(d.get("number_of_deferrable_loads") or 0)
    plan = []
    rest = [p - l for p, l in zip(pv, last)]  # soloverskud, der er tilbage (negativ: det, nettet skal levere)
    for k in range(antal):
        try:
            p = float(d["nominal_power_of_deferrable_loads"][k])
            timer = float(d["operating_hours_of_each_deferrable_load"][k])
            fra = int((d.get("start_timesteps_of_each_deferrable_load") or [0] * antal)[k] or 0)
            til = int((d.get("end_timesteps_of_each_deferrable_load") or [n] * antal)[k] or n)
        except (KeyError, IndexError, TypeError, ValueError):
            raise PlanFejl(f"fleksibel last {k} er ikke beskrevet helt") from None
        til = min(n, til if til > 0 else n)
        trin = math.ceil(timer / h - 1e-9)
        if p <= 0 or trin <= 0:
            plan.append([0.0] * n)
            continue
        mulige = [i for i in range(max(0, fra), til) if p - rest[i] <= imp + 1e-6]  # med lasten: nettet leverer højst importloftet
        if trin > len(mulige):
            raise PlanFejl(f"fleksibel last {k}: {timer} timer kan ikke nås inden for vinduet og under importloftet")
        pris = {i: (salg[i] if rest[i] >= p else koeb[i]) for i in mulige}
        valgt = set(sorted(mulige, key=lambda i: (pris[i], i))[:trin])
        rk = [p if i in valgt else 0.0 for i in range(n)]
        for i in valgt:
            rest[i] -= p
        plan.append(rk)
    return plan


def optimer(d: dict, start_ts: float, last_reserve: float = 1000.0) -> dict:
    """d: EMHASS' runtime-parametre (som Wattlas sender dem). start_ts: begyndelsen af det første tidstrin (sekunder).
    last_reserve: forbruget (W), hvis bestillingen ikke har en forbrugsprognose (ny installation uden historik).
    Returnerer planen: lister pr. tidstrin (W og %) – eller kaster PlanFejl."""
    try:
        n = int(d.get("prediction_horizon") or 0)
        trin_min = float(d.get("optimization_time_step") or 30)
    except (TypeError, ValueError):
        raise PlanFejl("horisonten er ikke et tal") from None
    if not 4 <= n <= 400 or not 5 <= trin_min <= 60:
        raise PlanFejl(f"horisont {n} trin à {trin_min} min kan ikke planlægges")
    h = trin_min / 60
    pv = [max(0.0, x) for x in _liste(d, "pv_power_forecast", n)]
    last = ([max(0.0, x) for x in _liste(d, "load_power_forecast", n)] if d.get("load_forecast_method") == "list"
            else [max(0.0, float(last_reserve))] * n)
    koeb, salg = _liste(d, "load_cost_forecast", n), _liste(d, "prod_price_forecast", n)
    tal = lambda k, std: float(d[k]) if d.get(k) is not None else float(std)  # noqa: E731
    kap = tal("battery_nominal_energy_capacity", 5000)                    # Wh
    smin, smax = tal("battery_minimum_state_of_charge", 0.3), tal("battery_maximum_state_of_charge", 0.9)  # EMHASS' egne standarder
    s0, sslut = tal("soc_init", smin), tal("soc_final", smin)
    pch, pdis = max(0.0, tal("battery_charge_power_max", 1000)), max(0.0, tal("battery_discharge_power_max", 1000))
    eta_c, eta_d = tal("battery_charge_efficiency", 0.95), tal("battery_discharge_efficiency", 0.95)
    imp, eks = tal("maximum_power_from_grid", 9000), tal("maximum_power_to_grid", 9000)
    slid = max(0.0, tal("weight_battery_discharge", 0))
    ingen_eksport_fra_batteri = bool(d.get("set_nodischarge_to_grid", True))
    if d.get("set_use_battery") is False:
        pch = pdis = 0.0
    if not (kap > 0 and 0 <= smin <= smax <= 1 and 0 < eta_c <= 1 and 0 < eta_d <= 1):
        raise PlanFejl("batteriets tal er ugyldige")

    laster = _laster(d, n, h, last, pv, koeb, salg, imp)
    netto = [last[i] + sum(lp[i] for lp in laster) - pv[i] for i in range(n)]  # W: + = huset mangler, - = soloverskud

    # SOC-gitter (Wh i batteriet). Start og slut afrundes til gitteret; startniveauet må ligge uden for [smin, smax] (fx efter en ny reserve)
    # Trinnet er højst kap/GITTER og går op i laderens energi pr. tidstrin (så ladningen kan planlægges præcist, også ved lav effekt, fx et
    # koldt batteri). Højst MAKS_TRIN trin; ved endnu lavere effekt kan der ikke lades i planen (reguleringen gør det alligevel ikke hurtigere)
    lad_wh, aflad_wh = pch * h * eta_c, pdis * h / eta_d
    G = kap / GITTER
    if lad_wh > 0:
        G = lad_wh / math.ceil(lad_wh / G - 1e-9)
    if 0 < aflad_wh < G:
        G = aflad_wh
    G = max(G, kap / MAKS_TRIN)
    M = int(round(kap / G))
    lo, hi = math.ceil(smin * kap / G - 1e-9), math.floor(smax * kap / G + 1e-9)
    s_start = min(M, max(0, round(s0 * kap / G)))
    s_slut = min(hi, max(lo, math.ceil(sslut * kap / G - 1e-9)))
    # 7) "hold niveauet": er minimum eller slut lig start (reserve = SOC, stormens hold, hvad-hvis uden batteri), gælder start – ellers ville
    # afrundingen kræve en unødig netladning eller gøre opgaven uløselig. Den rigtige SOC holdes over minimum i fremregningen
    if smin <= s0 + 1e-9:
        lo = min(lo, s_start)
    if sslut <= s0 + 1e-9:
        s_slut = min(s_slut, max(s_start, lo))
    op, ned = int(lad_wh / G + 1e-9), int(aflad_wh / G + 1e-9)

    def flyt(i: int, e_wh: float) -> tuple[float, float, float] | None:
        """Ét trin med e_wh ind i (+) eller ud af (-) batteriet: (net W, batteri W (+ = afladning), pris) – eller None, hvis det ikke må."""
        b = e_wh / eta_c if e_wh > 0 else e_wh * eta_d          # Wh på AC-siden ind i batteriet
        nl = netto[i]
        if e_wh < 0 and ingen_eksport_fra_batteri and -b > max(0.0, nl) * h + G * eta_d:  # højst ét gittertrin over husets behov
            return None
        g = nl + b / h                                          # W fra nettet
        if e_wh > 0 and g > max(imp, nl):
            return None
        if g < -eks or (g < 0 and salg[i] < 0):                 # mere sol end der må/kan betale sig at sælge: resten skæres fra
            g = 0.0 if salg[i] < 0 and nl + b / h < 0 else max(g, -eks)
        pris = (max(g, 0) * koeb[i] - max(-g, 0) * salg[i]) * h / 1000 + (slid * -b / 1000 if b < 0 else 0)
        return g, -b / h, pris

    V = [INF] * (M + 1)
    for s in range(s_slut, hi + 1):
        V[s] = 0.0
    valg: list[list[int]] = []
    for i in range(n - 1, -1, -1):
        pris = {dd: r[2] for dd in range(-ned, op + 1) if (r := flyt(i, dd * G)) is not None}  # afhænger ikke af SOC: én gang pr. trin
        W, A = [INF] * (M + 1), [0] * (M + 1)
        for s in range(M + 1):
            for dd in range(-min(ned, max(0, s - lo)), min(op, max(0, hi - s)) + 1):
                fv = V[s + dd]
                if fv == INF or dd not in pris:
                    continue
                if pris[dd] + fv < W[s]:
                    W[s], A[s] = pris[dd] + fv, dd
        V = W
        valg.append(A)
    valg.reverse()
    if V[s_start] == INF:
        raise PlanFejl("Infeasible: slut-niveauet kan ikke nås med de grænser, der er sat")

    # frem igen med de rigtige (ikke afrundede) tal: afladning klippes til husets behov, så batteriet aldrig sælger, og SOC holdes i grænserne
    e = s0 * kap
    ud = dict(p_batt=[], p_grid=[], soc=[], p_pv=[], p_load=[], laster=laster, koeb=koeb, salg=salg, start_ts=start_ts, trin_s=trin_min * 60)
    total = 0.0
    for i in range(n):
        s = min(M, max(0, round(e / G)))
        e_wh = valg[i][s] * G
        if e_wh < 0 and ingen_eksport_fra_batteri:
            e_wh = max(e_wh, -max(0.0, netto[i]) * h / eta_d)
        e_wh = min(max(e_wh, min(0.0, smin * kap - e)), max(0.0, smax * kap - e))
        r = flyt(i, e_wh)
        if r is None:  # fx netladning, der nu ville gå over importloftet: intet
            e_wh, r = 0.0, flyt(i, 0.0)
        e += e_wh
        g, pb, pris = r
        total += pris
        ud["p_batt"].append(round(pb, 2))
        ud["p_grid"].append(round(g, 2))
        ud["soc"].append(round(100 * e / kap, 2))
        ud["p_pv"].append(round(pv[i], 2))
        ud["p_load"].append(round(last[i], 2))
    ud["total"] = -round(total, 2)  # som EMHASS: værdien, der maksimeres
    return ud
