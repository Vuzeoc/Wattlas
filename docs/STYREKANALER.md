# Styrekanaler

Kernen (`packages/wattlas/`) kender ikke din inverter. Den læser og skriver kun **Wattlas-entiteter**. En styrekanal er en
pakke, der oversætter dem til inverterens rigtige entiteter. Installér præcis én.

## Kontrakten

En styrekanal skal definere:

**Styring (skrives af Wattlas)**

| Entitet | Type | Betydning |
|---|---|---|
| `switch.wattlas_netladning` | switch | netladning generelt til/fra |
| `switch.emhass_netladning_p1` … `p6` | switch | netladning i tidsprogram 1–6 |
| `number.wattlas_netladestroem` | number (A) | netladestrøm; `min`/`max`/`step` som inverteren |
| `number.wattlas_program_1_soc` … `6_soc` | number (%) | mål-SOC pr. tidsprogram |
| `number.wattlas_program_1_power` … `6_power` | number (W) | maks. effekt pr. tidsprogram |
| `switch.wattlas_solsalg` | switch | salg af overskudssol til/fra |

Tidsprogrammerne skifter kl. 01, 05, 09, 13, 17 og 21 (program 1 = 01–05 … program 6 = 21–01).

**Aflæsning**

| Entitet | Betydning |
|---|---|
| `sensor.wattlas_maks_ladestroem` / `_afladestroem` | inverterens indstillede batterigrænser (A) |
| `binary_sensor.wattlas_tidsprogram_aktiv` | inverterens tidsprogrammer er slået til |
| `binary_sensor.wattlas_forbindelse` | inverteren svarer |
| `binary_sensor.wattlas_pv_maaling_ok` | PV-effekten kan læses |
| `binary_sensor.emhass_styrekanal_ok` | alt ovenstående er klar (Wattlas overtager kun, når den er on) |
| `sensor.emhass_solproduktion_samlet` | samlet PV-effekt (W) |
| `sensor.wattlas_i_dag_produktion` / `_koebt` / `_solgt` / `_forbrug` / `_ladet` / `_afladet` | dagstællere (kWh, `total_increasing`) |
| `sensor.wattlas_total_produktion` / `_koebt` / `_solgt` / `_forbrug` | totaler (kWh) |

**Målinger** (`emhass_maalinger.yaml`): `sensor.emhass_m_*` for last, net, batteri (W, SOC, V, °C), inverter-status og
temperatur, eksterne CT pr. fase (W) og netspænding pr. fase (V), plus `sensor.emhass_maalekilde` (`Deye`, `Solarman` eller
`SunMate`). Hvert sæt kontrolleres for alder (højst 90 s), før det bruges.

## Deye via Solarman (`styrekanaler/deye_solarman`)

Til Deye SUN-xxK-SG0xLP3 (3-faset, 48 V-batteri) med [ha-solarman](https://github.com/davidrapan/ha-solarman). Prefix:
`min_inverter`. Netladning pr. program skrives som valget `Grid`/`Disabled` i `select.min_inverter_program_N_charging`.
Solarman genlæser først en skrivning efter et par minutter. Det er normalt.

Valgfrit: har du også en *Deye Home Monitor*-integration (`sensor.deye_home_monitor_*`), bruges den som hurtigste målekilde
med Solarman som reserve. Uden den bruges Solarman.

**Sunsynk / Sol-Ark og andre Deye-kloner** bruger typisk samme Modbus-registre. Hedder dine Solarman-entiteter det samme
(efter prefix), virker Deye-kanalen direkte. Ellers kopiér den og ret navnene.

## SunMate (`styrekanaler/sunmate`) – ikke testet

Til dig, der i dag lader SunMate.IO pulse styre inverteren. Wattlas overtager styringen gennem SunMate-boksen. Prefix:
`min_sunmate`. Krav: SunMates *inverter control mode* = 2 (Home Assistant) og *Time of use* slået til.
SunMate har ikke dagstællere for køb, salg og forbrug. Dem laver kanalen selv med HA's `utility_meter` og `integration`.

Kanalen er bygget ud fra en SunMate-opsætning, der kørte med Wattlas' forgænger, men den **er ikke testet** med denne version.
Følg den nøje den første dag, og meld gerne tilbage.

## SonnenBatterie (`styrekanaler/sonnen`) – alpha

Til SonnenBatterie med det lokale API v2 (firmware 1.40 eller nyere). Kræver, at **JSON API for Reading** og
**JSON API for Writing** er slået til i batteriets dashboard under Software-Integration. Adresse og token indtastes
i opsætningen (den tjekker, at batteriet svarer) og sættes ind i kanalens filer under installationen.

Netladning styres som manual mode (`EM_OperatingMode=1`) med et ladnings-setpoint i W: Wattlas skriver strøm i A,
kanalen ganger med batterispændingen (Ubat) og sender W til `POST /api/v2/setpoint/charge/{W}`. Når netladningen
slås fra, ryddes begge setpoints, og batteriet går i selvforbrug (`EM_OperatingMode=2`), så det aflader til huset.
Programvinduerne p1–p6 findes ikke i Sonnens API: switchene er optimistiske, og det er Wattlas selv, der stopper
ladningen ved programmets mål-SOC. Program-SOC og -effekt accepteres uden at skrive til batteriet.

Begrænsninger:

- **Solssalg kan ikke styres via API'et** – fw 1.40.5 har ingen feed-in-nøgle (EM_US_GEN_POWER_SET_POINT er et
  generator-setpoint, ikke feed-in). Skiftet registreres, men påvirker ikke batteriet; kontrollér eksport i
  batteriets eget dashboard.
- **Netudveksling pr. fase kan ikke aflæses.** CT-feltet er husets forbrug pr. fase fra batteriets egen måler,
  og spændingerne pr. fase er læst samme sted. Fase-tjekket i kernen bruger kun tallene og spændingsvinduet.
- **Dagstællere og totaler** findes ikke i API'et og laves af kanalen med HA's `integration` og `utility_meter`.
- Bygget og testet mod én SonnenBatterie (fw 1.40.5); valideret med HA's config-check, men **ikke kørt i drift
  endnu**. Følg den nøje den første dag, og meld gerne tilbage.

## Lav din egen

1. Kopiér `styrekanaler/deye_solarman/` til en ny mappe.
2. I `wattlas_kanal_*.yaml`: peg hver template-switch og -number på din inverters entiteter (`state`, `turn_on`/`turn_off`,
   `set_value`, `min`/`max`/`step`).
3. I `emhass_maalinger.yaml`: ret `smap` til dine sensorer (samme enheder: W, %, V, °C; net positiv = køb, batteri positiv = afladning).
4. Ret `binary_sensor.emhass_styrekanal_ok`, så den kun er on, når alle skrive-entiteter har en værdi.
5. Test først med styringen **slået fra**. Tjek i Udviklerværktøjer → Tilstande, at alle Wattlas-entiteter har værdier,
   og at fortegnene er rigtige.
