# Konfiguration

Alle tal er helpers (`input_number.wattlas_…` / `input_text.wattlas_…`) fra `packages/wattlas/wattlas_indstillinger.yaml`.
De nemmeste at rette er i **Indstillinger → Enheder og tjenester → Wattlas → Konfigurer** (samme felter som opsætningen, udfyldt med de nuværende værdier).
0 eller tom betyder "ikke sat". Så længe et påkrævet felt mangler, er `binary_sensor.wattlas_konfigureret` **off**, og
Wattlas skriver intet til inverteren og kalder ikke EMHASS.

> Vælg hellere for lavt end for højt. Grænserne er det, der beskytter sikringer og batteri, når planen tager fejl.

## Batteri og inverter (påkrævet)

| Helper | Betydning | Hvor finder jeg det |
|---|---|---|
| `wattlas_batteri_kwh` | brugbar kapacitet i kWh (alle moduler) | batteriets datablad, fx 2 × 10 kWh = 20 |
| `wattlas_maks_ladeeffekt_w` | højeste ladeeffekt EMHASS må planlægge | inverterens datablad (DC-ladeeffekt), højst batteriets |
| `wattlas_maks_afladeeffekt_w` | højeste afladeeffekt | inverterens AC-udgangseffekt / batteriets maks. |
| `wattlas_maks_ladestroem_a` | loft for DC-ladestrøm | batteriets maks. ladestrøm (BMS) |
| `wattlas_maks_afladestroem_a` | loft for DC-afladestrøm | batteriets maks. afladestrøm |
| `wattlas_maks_netladestroem_a` | loft for netladestrøm (DC) | typisk ≤ ladestrømmen; start lavt, fx 100 A |
| `wattlas_maks_netladeeffekt_w` | effekt ved tvungen netladning (fuldladning, "Lad nu") | fx 2/3 af importloftet |

Wattlas læser også inverterens egne lade- og afladegrænser (`sensor.wattlas_maks_ladestroem`/`_afladestroem`) og bruger
altid den laveste af de to.

## Elnet og sikringer (påkrævet)

| Helper | Betydning | Eksempel |
|---|---|---|
| `wattlas_fase_graense_a` | strøm pr. fase, som husets forbrug + netladning ikke må overstige | 3 × 20 A hovedsikring → 16 A |
| `wattlas_import_graense_w` | samlet import under netladning | 3 × 16 A × 230 V ≈ 11 000 W |
| `wattlas_maks_netimport_w` | højeste import i EMHASS-planen | ≤ importgrænsen, fx 9 000 W |
| `wattlas_maks_eksport_w` | højeste eksport i EMHASS-planen | din tilladte eksport, fx 6 000 W |

Netladning skrues ned, så **hver fase** holder sig under fasegrænsen, også når komfuret og varmepumpen kører.
Målingen kommer fra inverterens eksterne CT'er.

## Priser (påkrævet: de fire første)

Købspris = spot (inkl. moms) + (nettarif + elafgift) × 1,25 + tillæg. Salgspris = spot / 1,25 − indfødningstarif × 1,25 − gebyr.

| Helper | Betydning |
|---|---|
| `wattlas_nettarif_lav` / `_hoej` / `_spids` | netselskabets tarif uden moms for kl. 0–6 / 6–17 og 21–24 / 17–21 |
| `wattlas_elafgift` | elafgift + Energinets net- og systemtarif, uden moms |
| `wattlas_tillaeg` | elselskabets tillæg pr. kWh **inkl.** moms |
| `wattlas_salg_nettarif` | indfødningstarif (uden moms) |
| `wattlas_salg_gebyr` | elselskabets gebyr pr. solgt kWh |
| `wattlas_solcelle_slid` | hvad du regner en kWh solstrøm koster i slid (bruges i "strømmen koster nu"), fx 0,10 |

Tarifferne står på din elregning eller netselskabets hjemmeside. Sommer- og vintertarif skal du selv skifte. Det er en
alpha-begrænsning.

## Forbindelser og prognoser (påkrævet)

| Helper | Eksempel |
|---|---|
| `wattlas_emhass_adresse` | `http://homeassistant.local:5000` (din HA-adresse + EMHASS-port) |
| `wattlas_emhass_noegle` | API-nøglen fra EMHASS-app'en (vises skjult) |
| `wattlas_solprognose_entitet` | `sensor.…_power_now` fra Helios Forecast, eller en anden sensor i samme format ([SOLPROGNOSE.md](SOLPROGNOSE.md)) |
| `wattlas_vejr_entitet` | `weather.forecast_hjem` |
| `wattlas_udetemperatur_entitet` | `sensor.udetemperatur` – **valgfri**. Tom = vejr-entitetens aktuelle temperatur bruges. En egen sensor er lidt mere præcis, men det er ikke nødvendigt |

> API-nøglen ligger i HA's database som en helper-værdi. Alle med adgang til din HA kan læse den. Det er samme niveau som
> resten af HA. Del aldrig skærmbilleder af Indstillinger → Hjælpere.

## Husprognose (valgfri)

| Helper | Betydning |
|---|---|
| `wattlas_kulde_w_pr_grad` | ekstra husforbrug i W pr. grad, det er koldere end ugens gennemsnit. Har du varmepumpe, er 50–150 W typisk. 0 = ingen justering |

Alarmen *Høj netbelastning* går, når en fase under netladning bruger mere end `wattlas_fase_graense_a` + 25 %.

## Styring (sættes i appen)

> Efter installationen står skyderne på deres laveste værdi (fx net-loft 1 kW). **Sæt dem, før du slår styringen til**,
> ellers kan EMHASS ikke lægge en brugbar plan.

Reserve, slut-SOC, net-loft til planen, batteriets slidpris og fleksibel forbruger sættes på **Wattlas Styring → Styring**.
Batteriets slidpris (`wattlas_slid`) = batteriets pris / (kapacitet × cykler), fx 40 000 kr. / (20 kWh × 6000) ≈ 0,33 kr./kWh.
Planen bruger kun batteriet, når prisforskellen er større end tab og slid.

## Økonomi (valgfrit)

| Helper | |
|---|---|
| `input_number.solcelle_investering` | samlet pris for anlægget (tilbagebetaling, ROI) |
| `input_datetime.solcelle_start_dato` | dagen anlægget startede |
| `input_number.solcelle_sparet_bogfoert` | har du sparet penge før Wattlas, så sæt beløbet her ved start |

Kortet kan også vise en startsaldo i grafen:

```yaml
type: custom:energi-app-card
startsaldo: 5000            # kr. sparet før Wattlas
startsaldo_dato: 2025-12-31 # til og med denne dag
```

## Kortets øvrige valg

| Nøgle | |
|---|---|
| `tabs` | hvilke faner, fx `[live, okonomi, historik, elpris, sol]` eller `[styring, regler, plan, overvaagning, teknik]` |
| `link` | knap til det andet dashboard: `{navn: Styring, url: /wattlas-styring/app}` |
| `undertitel` | teksten under logoet |
| `pv_anlaeg` | op til to anlæg i energiflowet: `[{navn: Tag, entitet: sensor.min_inverter_pv_power}]` |
| `inverter_prefix` | Teknik-fanen: inverterens prefix (standard `min_inverter_`) |
| `inverter_navn` | Teknik-fanen: overskrift for inverter 1 |
| `inverter2_prefix`, `inverter2_navn`, `inverter2_relae` | Teknik-fanen: valgfri inverter 2 (fx streng-inverter på GEN-porten) og dens relæ |
