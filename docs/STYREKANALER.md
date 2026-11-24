# Styrekanaler

Kernen (`packages/wattlas/`) kender ikke din inverter. Den læser og skriver kun **Wattlas-entiteter**. En styrekanal er en
pakke, der oversætter dem til inverterens rigtige entiteter. Installér præcis én.

**Eksperimentel kanal eller nyt anlæg?** Kør først med **Skygge (vis kun)** slået til (Wattlas Styring → Styring): Wattlas
viser så, hvad den ville skrive til inverteren, uden at skrive det. Ser det rigtigt ud et døgn, så slå skyggen fra.

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
`SunMate`, `Huawei`, `Growatt`, `ESPHome`, `Sonnen`, `SolaX`, `Sofar`, `Solis` eller `SPF`). Hvert sæt kontrolleres for alder (højst 90 s), før det bruges.

## Deye via Solarman (`styrekanaler/deye_solarman`)

Til Deye SUN-xxK-SG0xLP3 (3-faset, 48 V-batteri) med [ha-solarman](https://github.com/davidrapan/ha-solarman). Prefix:
`min_inverter`. Netladning pr. program skrives som valget `Grid`/`Disabled` i `select.min_inverter_program_N_charging`.
Solarman genlæser først en skrivning efter et par minutter. Det er normalt.

Valgfrit: har du også en *Deye Home Monitor*-integration (`sensor.deye_home_monitor_*`), bruges den som hurtigste målekilde
med Solarman som reserve. Uden den bruges Solarman.

**Sunsynk / Sol-Ark og andre Deye-kloner** bruger typisk samme Modbus-registre. Hedder dine Solarman-entiteter det samme
(efter prefix), virker Deye-kanalen direkte. Ellers kopiér den og ret navnene.

**Ingen nedtælling.** Netladningen ligger i Deyes egne tidsprogrammer. Går Home Assistant ned under netladning, bliver
programmet stående: inverteren lader fra nettet i programmets tidsrum, også de næste nætter, til målet er nået – uden Wattlas'
fasegrænse. Sæt inverterens egen grænse for køb fra nettet, hvis din model har en, og slå netladningen fra i Deyes app, hvis HA er
nede længe. Det samme gælder de to andre Deye-kanaler og SunMate.

## To Deye i parallel (`styrekanaler/deye_parallel`) – eksperimentel

Til to ens Deye-hybrid-invertere i master/slave med fælles batteri, hver med sin egen Solarman-logger i ha-solarman.
Opsætningen spørger først efter masterens *PV power* (den, CT'erne/elmåleren sidder på) og derefter slavens.

- **Styring:** der skrives kun til masteren. Deye kopierer selv indstillingerne til slaven over parallelkablet (brugere
  fraråder at skrive til begge – det kan bringe dem ud af takt). Ladestrøm (A) og programmernes effekt (W) gælder pr. inverter,
  så masteren får halvdelen (rundet ned): summen bliver højst det, planen beder om.
- **Vagt:** følger slaven ikke masteren (tidsprogrammer, netladning, strøm) inden for 3 minutter, er styrekanalen ikke klar,
  og Wattlas holder op med at styre – så kan slaven ikke lade fra nettet på egen hånd uden fasegrænsen.
- **Målinger:** batteri og sol lægges sammen; SOC og spænding fra masteren (fælles batteri); nettet og de tre faser fra
  masterens CT'er (hele huset); husforbrug = net + sol + batteri. Køb/salg-tællere fra masteren.
- **Status:** kun *Normal*, når begge er det – en slave i fejl stopper styringen. Forbindelsen kræver begge.
- Grænserne (maks. ladestrøm, netladestrøm) er summen af begge inverteres – sæt opsætningens tal for hele anlægget.
- Ikke kørt på et rigtigt parallelanlæg endnu – kør et døgn i skygge først, og hold øje med den første nat med styring: at begge invertere får de samme programmer, og at
  købet holder sig under fasegrænsen.

## Deye via ESPHome (`styrekanaler/deye_esphome`) – eksperimentel

Til Deye 3-fasede lavvolt-invertere med en ESP32 + RS485-modul direkte på inverterens Modbus-port, sat op med
[klatremis/esphome-for-deye](https://github.com/klatremis/esphome-for-deye) (bekræftet af forfatteren på SUN-12K-SG04LP3; 5–12 kW
SG04LP3 nævnes). Samme registre og samme styring som Deye-kanalen – bare uden Solarman-loggeren. Opsætningen spørger efter
*PV1 Power*; ESPHome-konfigurationens `device_type` (fx `sun12k`) er prefixet.

- Navnene skal være dem fra klatremis' konfiguration. Har du omdøbt sensorer, viser opsætningens tjek, hvilke der mangler.
- Tidsprogrammernes *charge enable* og *Time of Use* er kontakter i ESPHome (i Solarman valgmenuer) – kanalen bruger kontakterne.
- Ingen mikroinverter/GEN-port og ingen ekstra inverter. PV = summen af de *PVn Power*-sensorer, der findes (klatremis har
  PV1–PV2; har din inverter 3–4 MPPT'er, så tilføj PV3/PV4 i ESPHome med samme navnemønster).
- Husforbrug = *Load totalpower* + *Out-of-grid–total power* (belastningsudgangen + forbruget på nettets side – som Solarmans *Load Power*).
- Dagstællere for forbrug og batteri findes ikke i konfigurationen – Wattlas laver dem ud fra totalerne.
- Inverterforbindelsen vurderes ud fra, hvornår *Running Status* sidst blev læst.
- Kræver hardware (ESP32 + RS485-modul). Testet med HA's konfigurationstjek – **ikke** på en rigtig inverter.

## SunMate (`styrekanaler/sunmate`) – ikke testet

Til dig, der i dag lader SunMate.IO pulse styre inverteren. Wattlas overtager styringen gennem SunMate-boksen. Prefix:
`min_sunmate`. Krav: SunMates *inverter control mode* = 2 (Home Assistant) og *Time of use* slået til.
SunMate har ikke dagstællere for køb, salg og forbrug. Dem laver kanalen selv med HA's `utility_meter` og `integration`.

Kanalen er bygget ud fra en SunMate-opsætning, der kørte med Wattlas' forgænger, men den **er ikke testet** med denne version.
Følg den nøje den første dag, og meld gerne tilbage.

**Ingen nedtælling:** som Deye (se ovenfor). Går Home Assistant ned under netladning, bliver SunMates tidsprogram stående.

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
Vælg *EMMA* i opsætningen og EMMA's **Feed in power**. Huawei Solar opretter to sæt målersensorer: den indbyggede måler
og en ekstern (DTSU) med `_2` bagpå. Sæt kun hak ved *ekstra elmåler*, hvis du faktisk har en DTSU – uden den viser de
to sæt det samme.

Forskelle fra udgaven uden EMMA:
- Fasetal og -spændinger, husforbrug, sol og salg til nettet læses på EMMA. Slå EMMA-målerens **Phase A/B/C active
  power** og **Phase A/B/C voltage** til – de er slået fra som standard.
- Salgsloftet sættes på EMMA. Kan din EMMA ikke begrænse salget, findes funktionen ikke i Huawei Solar, og *stop
  solsalg* er så ikke tilgængelig.
- EMMA's **ESS Control Mode** skal stå på *Maximum self consumption* eller *Third-party dispatch*. I TOU eller *Fully fed
  to grid* styrer Wattlas ikke.
- Batteriet styres som uden EMMA (tvungen opladning og afladeeffekt på batteriet).

**Regnestykke-tjek (begge udgaver):** fortegnene er ikke bekræftet på et rigtigt anlæg, så Wattlas regner efter hvert
10. sekund. Uden EMMA: sol ind − batteriets ladning ≈ inverterens AC-effekt. Med EMMA: køb fra nettet + sol − batteriets ladning ≈
husforbrug, og de tre faser ≈ købet (EMMA's *Feed in power* er positiv ved køb – bekræftet på en EMMA-A02). Passer det ikke i 2 minutter i træk (Huawei Solar læser inverter, batteri og måler hver for sig, så et enkelt
skævt øjeblik er normalt), bruges målingerne ikke, og Wattlas styrer ikke. Det fanger et forkert
fortegn på batteriet (og med EMMA også på salg og faser) inden for et par minutter – men det erstatter ikke, at du selv
ser efter den første dag. Se `balance_ok` på `sensor.emhass_maalekilde`.

## Growatt (`styrekanaler/growatt`) – eksperimentel, ikke kørt i drift

Til trefasede Growatt-hybrid-invertere af typen GEN4 (fx MOD 5–10K TL3-XH, MID 15–30K TL3-XH) med Growatt-elmåler og
højvoltbatteri (ARK/APX), tilsluttet **lokalt** via [solax_modbus](https://github.com/wills106/homeassistant-solax-modbus)
(Modbus TCP eller RS485-adapter). Opsætningen spørger efter batteriets SOC (`sensor.<navn>_battery_soc`); navnet på
solax_modbus-forbindelsen er prefixet for alle entiteter.

Forudsætninger:
- Lokal forbindelse. **Growatts sky virker ikke:** den opdaterer hvert 5. minut, og fasegrænsen kræver målinger, der
  højst er 90 sekunder gamle.
- *VPP Status* = *Enabled* i solax_modbus (Growatts tilladelse til fjernstyring, register 30100).
- Trefaset inverter (X3). Enfasede MIN TL-XH og ældre Growatt (GEN3/SPH) understøttes ikke; SPF har sin egen kanal (nedenfor).

Sådan styres:
- **Netladning** = Growatts VPP-fjernstyring (*VPP Remote Control*, *VPP Power* i %, *VPP Time*). Wattlas skriver en
  nedtælling på 10 minutter og fornyer den hvert minut – går Home Assistant ned, går inverteren selv tilbage til normal drift.
  *VPP AC Charge Max Power 2* sættes til den ønskede netladeeffekt som loft, og *VPP Power* rundes **ned** i trin på 5 %
  af din maks. ladeeffekt. Ingen af disse registre gemmes i inverterens hukommelse, så hyppige skrivninger slider ikke.
  *VPP Allow AC charging* slås til første gang (den gemmes i inverteren og bliver stående).
- **Gem batteriet** = *VPP Power* 0 % (batteriet hverken lader eller aflader). Det stopper også solladning, så med
  soloverskud (over 200 W) får inverteren lov at køre selv i stedet – overskuddet lades, intet aflades.
  Growatt kan ikke begrænse afladningen til et bestemt antal W: et program med effekt over 0 W betyder fri afladning.
- **Tidsprogrammer** findes ikke hos Growatt. Kanalen husker kernens seks programmer selv (som Huawei-kanalen).
- **Solsalg fra** = *Grid Export Limit* sættes til 0 %, din egen grænse huskes og sættes tilbage. Virker kun, hvis
  eksportbegrænsning (*Limit Grid Export*) allerede er slået til med måleren – ellers rører Wattlas den ikke.
- **Højvoltbatteri:** fast beregningsspænding 50 V som Huawei-kanalen. Growatt melder ikke batteriets maks. effekt, så
  kanalen bruger dine indstillinger for maks. lade- og afladeeffekt.
- **Fasegrænse uden fasetal:** Growatts elmåler giver kun summen. Kanalen melder den værste fase, der kan opstå – hele
  huset på én fase og inverteren fordelt ligeligt på tre: `(2 × husforbrug + net) / 3`. Netladningen holdes derved under
  `3 × (fasegrænse × V − husforbrug)`. Det er forsigtigt (der lades mindre, end der måske er plads til), men aldrig for
  meget, så længe inverteren er symmetrisk trefaset.
- **Kommando-tjek:** beder Wattlas om ladning, men batteriet aflader, lades der tydeligt fra nettet, uden at elmåleren
  viser køb (måler mangler eller sidder forkert), eller lades der mere fra nettet end bedt om (+25 % + 300 W – fx hvis
  loftet *VPP AC Charge Max Power 2* ikke virker på din model), bruges målingerne ikke efter 2 minutter i træk, og
  Wattlas styrer ikke.

Kanalen er bygget ud fra Growatts VPP-protokol (V2.05) og solax_modbus' kildekode og afprøvet med HA's
konfigurationstjek og regnestykke-tests – **ikke** på en rigtig Growatt. Hold øje med den første nat: at batteriet lader
ved netladning, at *VPP Remote Control* slås fra igen bagefter, og at købet ikke overstiger din fasegrænse.

## SolaX (`styrekanaler/solax`) – eksperimentel, ikke kørt i drift

Til trefasede SolaX-hybrider af generation 4 (X3-Hybrid G4) med SolaX-elmåler, tilsluttet **lokalt** via [solax_modbus](https://github.com/wills106/homeassistant-solax-modbus)
(Modbus TCP eller RS485). Opsætningen spørger efter batteriets SOC (`sensor.<navn>_battery_capacity`); navnet på
solax_modbus-forbindelsen er prefixet for alle entiteter.

Forudsætninger:
- *Grid Voltage L1–L3* skal slås til i solax_modbus (de er slået fra som standard). Uden dem mangler fasespændingerne.
- Fjernstyringen *Remotecontrol (mode 1)* skal findes i solax_modbus (G4 eller nyere).

Sådan styres:
- **Netladning** = *Remotecontrol Power Control (mode 1)* = *Enabled Power Control* med den ønskede effekt fra nettet
  (*Remotecontrol Active Power*, hele 100 W, aldrig over din maks. ladeeffekt). Kommandoen gentages af solax_modbus selv
  (*Autorepeat Duration* 10 min) og fornyes hvert minut – går Home Assistant ned, går SolaX tilbage til egen drift.
  Registrene gemmes ikke i inverterens hukommelse, så hyppige skrivninger slider ikke.
- **Gem batteriet** = *Enabled No Discharge*. solax_modbus lader med vilje batteriet aflade ca. 150 W i den tilstand. Bruges
  kun uden soloverskud (under 200 W) – med overskud kører inverteren selv, så solen kan lade.
- **Fri** = fjernstyringen *Disabled* (kun Wattlas' egen – har du selv slået den til, røres den ikke).
- **Solsalg fra** = *Export Control User Limit* 0 W; din egen grænse huskes og sættes tilbage.
- **Højvoltbatteri:** fast beregningsspænding 50 V som Huawei-kanalen.
- **Fortegn:** solax_modbus melder elmåleren positiv ved salg og *Battery Power Charge* positiv ved ladning; kanalen
  vender dem til kernens retning. Elmåleren giver hver fase, så fasegrænsen får rigtige tal.
- **Kommando-tjek:** som Growatt – aflader batteriet, mens der bedes om ladning, eller lades der mere fra nettet end bedt,
  bruges målingerne ikke efter 2 minutter, og kanalen spærres i 1 time.

Afprøvet i en test-Home Assistant med den rigtige solax_modbus (2026.11.04) mod en falsk inverter (hele kæden: priser, plan,
netladning, fasegrænse, genstart) – **ikke** på en rigtig SolaX.

## Sofar (`styrekanaler/sofar`) – eksperimentel, ikke kørt i drift

Til trefasede Sofar HYD-hybrider (fx HYD 5–20KTL-3PH) via [solax_modbus](https://github.com/wills106/homeassistant-solax-modbus). Opsætningen spørger efter
`sensor.<navn>_battery_capacity_total`.

Overtager Wattlas, sender den en timeout på 10 minutter (*Return to Previous Mode*) til inverteren, vælger *Passive Mode* og
fornyer sine tal hvert minut. Slippes styringen – eller går Home Assistant ned – løber timeouten ud, og Sofar går selv tilbage
til den tilstand, den stod i før (fx Self Use). Uden for styringen og i skygge skriver Wattlas intet. Har du din egen
Passive-timeout i inverteren, erstattes den.

Sådan styres (tre tal med *Passive: Update Battery Charge/Discharge*):
- **Netladning** = mindst den bedte effekt ind i batteriet (solen tæller med), højst din maks. ladeeffekt; net-mål 0 W.
- **Gem batteriet** = batteriet må lade, ikke aflade.
- **Fri** = som Self Use: lade og aflade frit inden for dine maks.-effekter.
- **Solsalg fra** = *FeedIn: Maximum Power* 0 W (med *FeedIn: Update*). Kræver, at du har valgt *FeedIn: Limitation Mode*
  og *FeedIn: Maximum Power* i solax_modbus (de er tomme i en ny installation) – ellers rører Wattlas den ikke.
- **Fortegn er antaget:** solax_modbus dokumenterer ikke retningen på *Active Power PCC* og *Battery Power Total* (kW).
  Kanalen antager salg og ladning positive og tjekker det: sol + afladning + køb skal give husets forbrug, og faserne skal
  summe til totalen. Passer det ikke i 2 minutter, bruges målingerne ikke, og Wattlas styrer ikke.

Afprøvet i en test-Home Assistant med den rigtige solax_modbus (2026.11.04) mod en falsk inverter (hele kæden,
forkerte fortegn, timeout, genstart) – **ikke** på en rigtig Sofar.

## Solis (`styrekanaler/solis`) – eksperimentel, ikke kørt i drift

Til trefasede Solis-hybrider med Solis-elmåler via [solax_modbus](https://github.com/wills106/homeassistant-solax-modbus), plugin *Solis FB00*, hvor inverteren kan
*Remote Dispatch* (*Remote Dispatch Function Version* 1 eller mere – den bruger opsætningen også til at finde prefixet).

Sådan styres (*Remote Dispatch*: registrene ligger kun i inverterens arbejdshukommelse, og hver kommando udløber efter
*Dispatch Failsafe Interval*, som kanalen sætter til 5 minutter):
- **Netladning** = *Battery Charge* med positiv effekt og netladning *Allow*.
- **Gem batteriet** = *Battery Hold* (hverken ladning eller afladning). Kun uden soloverskud – ellers egen drift.
- **Fri** = *Disable Remote Dispatch* (kun Wattlas' egen).
- Start: *Prepare Remote Dispatch*, 2 sekunder, så *Apply Remote Dispatch*. *Apply* fornyes hvert minut, *Prepare*
  hvert 10. minut, ved Home Assistant-start og når målingerne modsiger ordren (inverteren er genstartet). Går Home Assistant ned, udløber kommandoen, og Solis kører sin egen tilstand.
- Kun de tilstande, solax_modbus selv har set virke på en rigtig Solis (*Battery Charge*, *Battery Hold*, *Disable*).
  solax_modbus har kun prøvet Remote Dispatch på én enfaset Solis – om din model og firmware gør det samme, ses først i drift.
- **Solsalg fra** = *Backflow Power* 0 W (højst 9900 W); din egen grænse huskes. Kræver, at *Backflow Power Switch* står
  på *On …*. Grænsen gemmes i inverterens hukommelse og skrives kun ved skift.
- **Fortegn:** batteriet læses som to positive tal (*Battery Input/Output Energy*), så dets retning er sikker. Elmålerens
  retning (*Meter Active Power Total*, kW) er antaget og tjekkes med samme regnestykke som Sofar; husforbruget er *House
  Load* + *Bypass Load* (nødstrømsudgangen). Kommando-tjekket fra SolaX gælder også.

Afprøvet i en test-Home Assistant med den rigtige solax_modbus (2026.11.04) mod en falsk inverter (hele kæden,
forkerte fortegn, failsafe, genstart af inverter og Home Assistant) – **ikke** på en rigtig Solis.

## Growatt SPF (`styrekanaler/growatt_spf`) – eksperimentel, ikke kørt i drift

Til Growatts off-grid-invertere (enfaset, 48 V, fx SPF 5000 ES), der er koblet til **Solar Assistant**. Wattlas bruger Solar
Assistants MQTT-emner direkte (`solar_assistant/…`), så det er ligegyldigt, hvad entiteterne hedder i Home Assistant.

Forudsætninger:
- *MQTT*-integrationen i Home Assistant får Solar Assistants emner (forbundet til Solar Assistants MQTT eller til en broker, den
  sender til). Opsætningen lytter efter dem.
- I Solar Assistant: *Configuration → MQTT Broker → Allow setting changes* slået til. Ellers afvises alt, hvad Wattlas sender.
- Kun én inverter (`inverter_1`).

Sådan styres:
- **Netladning** = output *Utility first*, lader *Solar and utility simultaneously* og *Max grid charge current* i hele 10 A,
  aldrig over det, inverterens net-indgang har plads til (fasegrænse × V − forbruget).
- **Gem batteriet** = output *Utility first*, lader *Solar only*. Kun uden soloverskud (under 200 W).
- **Fri** = output *Solar/Battery/Utility*, lader *Solar only*.
- **Slippes styringen**, sættes dine egne tre værdier fra før tilbage.
- **Sjældne skrivninger:** SPF gemmer indstillingerne i hukommelsen, som slides. Strømmen hæves højst hvert 3. minut, gem og
  fri skifter højst hvert 10. minut, og efter 40 skrivninger på et døgn startes ingen ny netladning før midnat. Stop, lavere strøm og
  tilbagelevering er altid tilladt.

Begrænsninger – læs dem, før du slår styringen til:
- **Ingen nedtælling.** Går Home Assistant eller Solar Assistant ned under netladning, lader inverteren videre med den sidste strøm,
  til batteriet er fuldt.
- **Fasegrænsen gælder kun inverterens egen net-indgang.** Wattlas kan ikke se husets andre forbrug på samme fase. Sæt den derfor til
  det, den gruppe kan tåle.
- **Intet salg.** Off-grid sælger ikke, men planen regner stadig med salgspriser. Sæt *elselskabets gebyr ved salg* til fx 5 kr./kWh i
  opsætningen, så planen ikke sparer solen op til et salg, der ikke kan ske.
- **Valgteksterne er ikke bekræftet på en SPF.** Hedder de noget andet på din model, afviser Solar Assistant dem, og kanalen melder sig
  ikke klar efter 3 minutter (se `sensor.min_spf_svar`).

Afprøvet i en test-Home Assistant med en rigtig MQTT-broker mod en **falsk** Solar Assistant (hele kæden, fasegrænse, afviste ordrer,
død Solar Assistant, forkert fortegn, genstart) – **ikke** på en rigtig SPF eller Solar Assistant.

## SonnenBatterie (`styrekanaler/sonnen`) – eksperimentel, ikke kørt i drift

Bidrag fra [hornbech](https://github.com/hornbech). Til SonnenBatterie med det lokale API v2 (firmware 1.40 eller nyere) –
ingen HA-integration: kanalen læser batteriet med REST-sensorer og styrer det med `rest_command`. Kræver, at
**JSON API for Reading** og **JSON API for Writing** er slået til i batteriets dashboard under *Software-Integration*.
Adresse og token indtastes i opsætningen (den tjekker, at batteriet svarer) og sættes ind i kanalens filer – også ved
hver opdatering. Får batteriet en ny adresse eller et nyt token, rettes det under *Konfigurer → SonnenBatterie* (kræver genstart).

- **Netladning:** manual mode (`EM_OperatingMode=1`) med et ladnings-setpoint i W: Wattlas skriver strøm i A, kanalen ganger
  med batterispændingen (Ubat) og sender W til `POST /api/v2/setpoint/charge/{W}`. Når netladningen slås fra, ryddes
  setpointene, og batteriet får **sin egen driftstilstand tilbage** (`EM_OperatingMode` huskes første gang kanalen
  overtager – fx 10 for tidsplan, 6 for backup; ukendt eller ugyldig værdi giver 2 = selvforbrug). En fast
  `EM_OperatingMode=2` ville ellers slå en tidsplan fra, uden at nogen kunne se hvorfor.
- **Tidsprogrammer** p1–p6 findes ikke i Sonnens API: kontakterne og program-SOC/-effekt huskes kun i Home Assistant,
  og Wattlas stopper selv ladningen ved programmets mål-SOC. Derfor virker *gem batteriet* ikke – uden netladning kører
  batteriet altid selvforbrug.
- **Solsalg kan ikke styres** (fw 1.40.5 har ingen feed-in-nøgle). Kontakten skifter, men batteriet påvirkes ikke.
- **Fasegrænse:** batteriet måler kun husets forbrug pr. fase, ikke nettet, og Sonnen eco er enfaset (kernens fasebudget regner
  med en trefaset inverter). Kanalen sætter derfor netladestrømmens maks. til det, den værste fase har plads til:
  (fasegrænse × V − husets forbrug på fasen) × 0,95 / batterispændingen – uden fradrag for sol. Forsigtigt, men aldrig for meget.
- **Går Home Assistant ned under netladning,** bliver batteriet i manual mode og lader videre med det sidste setpoint,
  til det er fuldt. Sonnen har ingen nedtælling som Huawei og Growatt. *Nyere enheder har en:* API-dokumentationen
  beskriver `PUT /api/v2/site/setpoint` med en `duration` (standard `PT30S`), men den svarer
  `400 {"error":"Setpoint commands can only be set in EM2"}` på fw 1.40.5 — også i mode 2 — så den kræver en
  EM2-energimanager, som ældre enheder ikke har. Risikoen ved et nedbrud er derfor **økonomisk** (utilsigtet netkøb om
  natten), ikke en sikkerhedsrisiko: ladestrømmen er allerede begrænset af kanalens fasegrænse. Sæt batteriet i
  selvforbrug i dets app, hvis HA er nede længe.
- **Dagstællere og totaler** findes ikke i API'et og laves af kanalen med HA's `integration` og `utility_meter`.
- Læsningen er bygget mod en rigtig SonnenBatterie (fw 1.40.5); styringen er ikke kørt i drift. Kør et døgn i skygge først.

## Lav din egen

1. Kopiér `styrekanaler/deye_solarman/` til en ny mappe.
2. I `wattlas_kanal_*.yaml`: peg hver template-switch og -number på din inverters entiteter (`state`, `turn_on`/`turn_off`,
   `set_value`, `min`/`max`/`step`).
3. I `emhass_maalinger.yaml`: ret `smap` til dine sensorer (samme enheder: W, %, V, °C; net positiv = køb, batteri positiv = afladning).
4. Ret `binary_sensor.emhass_styrekanal_ok`, så den kun er on, når alle skrive-entiteter har en værdi.
5. Test først med styringen **slået fra**. Tjek i Udviklerværktøjer → Tilstande, at alle Wattlas-entiteter har værdier,
   og at fortegnene er rigtige.
