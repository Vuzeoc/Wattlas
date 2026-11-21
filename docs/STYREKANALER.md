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

## Lav din egen

1. Kopiér `styrekanaler/deye_solarman/` til en ny mappe.
2. I `wattlas_kanal_*.yaml`: peg hver template-switch og -number på din inverters entiteter (`state`, `turn_on`/`turn_off`,
   `set_value`, `min`/`max`/`step`).
3. I `emhass_maalinger.yaml`: ret `smap` til dine sensorer (samme enheder: W, %, V, °C; net positiv = køb, batteri positiv = afladning).
4. Ret `binary_sensor.emhass_styrekanal_ok`, så den kun er on, når alle skrive-entiteter har en værdi.
5. Test først med styringen **slået fra**. Tjek i Udviklerværktøjer → Tilstande, at alle Wattlas-entiteter har værdier,
   og at fortegnene er rigtige.
