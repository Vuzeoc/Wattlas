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
temperatur, eksterne CT pr. fase (W) og netspænding pr. fase (V), plus `sensor.emhass_maalekilde` (`Deye`, `Solarman`,
`SunMate` eller `Huawei`). Hvert sæt kontrolleres for alder (højst 90 s), før det bruges.

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

## Huawei (`styrekanaler/huawei`) – ikke kørt i drift

Til Huawei SUN2000 hybrid-invertere (fx SUN2000-10KTL-M1) med LUNA2000-batteri og Huawei-elmåler (fx DTSU666-H),
tilsluttet direkte via [Huawei Solar](https://github.com/wlcrs/huawei_solar). Opsætningen spørger efter tre enheder:
inverteren (`…_input_power`), batterierne (`…_state_of_capacity`) og elmåleren (`…_active_power`). Standardnavnene
(`inverter`, `batteries`, `power_meter`) er udfyldt.

Krav:
- Huawei Solar sat op med *elevate permissions* (installatør-adgangskoden), så Wattlas kan skrive.
- Elmålerens **Phase A/B/C voltage** slået til under enheden *Power meter* – de er slået fra som standard.
- Valgfrit, men anbefalet: **BMS temperature** slået til under *Battery 1* (og *Battery 2*). Uden den kan Wattlas
  ikke advare om et for varmt batteri eller opladning i frost.
- Batteriets **Working Mode** = *Maximise self consumption*. I TOU eller *Fully fed to grid* følger batteriet ikke
  planen, og Wattlas styrer ikke (styrekanalen melder ikke klar).
- Kun én Modbus-forbindelse ad gangen: brug ikke andre værktøjer på inverteren samtidig.

Sådan styres anlægget:
- **Netladning:** `huawei_solar.forcible_charge` i 10 minutter ad gangen, fornyet hvert 5. minut, med *Charge from grid*
  slået til imens. Går Home Assistant ned, stopper ladningen af sig selv inden for 10 minutter.
- **Tidsprogrammer** findes ikke hos Huawei. Kanalen husker kernens seks programmer selv og bruger det aktive programs
  værdier: SOC er bundgrænse og mål for netladning, effekten er batteriets højeste afladeeffekt
  (`number.…_maximum_discharging_power`, 0 W = gem batteriet). Huaweis egen *End-of-discharge SOC* kan kun være 0–20 %,
  derfor bruges effekten.
- **Solsalg fra:** højst 0 W til nettet (`set_maximum_feed_grid_power`); **til:** den eksport, du har lov til (indstillingen
  *maks. eksport*).
- **Højvoltbatteri:** kernen regner i ampere ved et lavvoltbatteri. Kanalen bruger en fast beregningsspænding på 50 V
  (A × 50 = W), og strømgrænserne følger selv effekt-indstillingerne (W ÷ 50) – også når du ændrer dem senere. Appen viser derfor ikke batteriets spænding for Huawei.
- **Fortegn:** Huaweis elmåler er positiv ved salg og batteriet positivt ved ladning. Kanalen vender dem, så kernen får
  net positiv = køb og batteri positiv = afladning. Fasetallene er elmålerens udveksling pr. fase (inkl. batteriets ladning).
- Batteriets afladeeffekt ændres kun, mens Wattlas styrer. Din egen indstilling huskes første gang og sættes tilbage,
  når Wattlas holder op med at styre (styringen slået fra eller Wattlas fjernet). Har Wattlas selv stoppet salget (negativ pris), sættes det også tilbage til den tilladte eksport. Indtil Wattlas første gang
  stopper salget, røres inverterens salgsindstilling ikke.

Kanalen er bygget ud fra Huawei Solars kildekode og Huaweis Modbus-dokumentation og testet mod en simuleret Huawei.
Den **er ikke kørt på et rigtigt anlæg endnu**. Følg den nøje den første dag – især at batteriets fortegn passer
(lader det, skal *Charge/Discharge power* være positiv) – og meld gerne tilbage. Ikke understøttet endnu: SmartLogger,
1-fasede invertere og flere invertere.

### Med EMMA (`styrekanaler/huawei_emma`) – eksperimentel, ikke kørt i drift

Har du en **EMMA** (Huawei Energy Management Assistant), sidder elmåleren på den, og EMMA bestemmer over batteriet.
Vælg *EMMA* i opsætningen, og vælg EMMA-målerens **Phase A active power** – den indbyggede måler, eller den eksterne
(DTSU), der hedder det samme med `_2` bagpå. Wattlas finder selv resten af målerens sensorer.

Forskelle fra udgaven uden EMMA:
- Fasetal og -spændinger, husforbrug, sol og salg til nettet læses på EMMA. Slå EMMA-målerens **Phase A/B/C active
  power** og **Phase A/B/C voltage** til – de er slået fra som standard.
- Salgsloftet sættes på EMMA. Kan din EMMA ikke begrænse salget, findes funktionen ikke i Huawei Solar, og *stop
  solsalg* er så ikke tilgængelig.
- EMMA's **ESS Control Mode** skal stå på *Maximum self consumption* eller *Third-party dispatch*. I TOU eller *Fully fed
  to grid* styrer Wattlas ikke.
- Batteriet styres som uden EMMA (tvungen opladning og afladeeffekt på batteriet).

**Regnestykke-tjek (begge udgaver):** fortegnene er ikke bekræftet på et rigtigt anlæg, så Wattlas regner efter hvert
10. sekund. Uden EMMA: sol ind − batteriets ladning ≈ inverterens AC-effekt. Med EMMA: sol − batteriets ladning − salg ≈
husforbrug, og de tre faser ≈ salget. Passer det ikke i 2 minutter i træk (Huawei Solar læser inverter, batteri og måler hver for sig, så et enkelt
skævt øjeblik er normalt), bruges målingerne ikke, og Wattlas styrer ikke. Det fanger et forkert
fortegn på batteriet (og med EMMA også på salg og faser) inden for et par minutter – men det erstatter ikke, at du selv
ser efter den første dag. Se `balance_ok` på `sensor.emhass_maalekilde`.

## Lav din egen

1. Kopiér `styrekanaler/deye_solarman/` til en ny mappe.
2. I `wattlas_kanal_*.yaml`: peg hver template-switch og -number på din inverters entiteter (`state`, `turn_on`/`turn_off`,
   `set_value`, `min`/`max`/`step`).
3. I `emhass_maalinger.yaml`: ret `smap` til dine sensorer (samme enheder: W, %, V, °C; net positiv = køb, batteri positiv = afladning).
4. Ret `binary_sensor.emhass_styrekanal_ok`, så den kun er on, når alle skrive-entiteter har en værdi.
5. Test først med styringen **slået fra**. Tjek i Udviklerværktøjer → Tilstande, at alle Wattlas-entiteter har værdier,
   og at fortegnene er rigtige.
