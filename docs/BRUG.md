# Sådan bruger du Wattlas

Wattlas kører af sig selv, når det er sat op: EMHASS lægger en ny plan hvert 5. minut, og Wattlas følger den hvert
30. sekund. Det meste af tiden skal du intet gøre. Denne side forklarer, hvad du kan skrue på, og hvornår det giver mening.

Rækkefølgen, Wattlas følger: **manuel tilsidesættelse → første aktive regel → planen**. Sikkerhedsgrænserne (sikringer,
faser, spænding, batteriets strømme og reserve) gælder altid, uanset hvad du vælger.

**Indhold:** [De første dage](#de-første-dage) · [Hverdagen](#hverdagen) · [Styring](#wattlas-styring--styring) ·
[Regler](#wattlas-styring--regler) · [Planens logik](#wattlas-styring--planens-logik) ·
[Overvågning](#wattlas-styring--overvågning) · [Teknik](#wattlas-styring--teknik) · [Appen](#wattlas-appen) ·
[Når noget går galt](#når-noget-går-galt) · [Én eller flere invertere](#én-eller-flere-invertere)

## De første dage

1. **Se planen an, før den styrer.** Når indstillingerne er sat, laver EMHASS planer, og appen virker, men inverteren
   røres først, når du slår **Wattlas styrer batteriet** til. Kig på *Planens logik* et døgn eller to: giver
   beslutningerne mening, og består de 7 tjek?
   De første 3 dage kender Wattlas ikke husets forbrugsmønster endnu og regner med forbruget lige nu (eller de dage,
   der er gået). Derefter bruger den gennemsnittet af den sidste uge, justeret efter udetemperaturen.
2. **Slå styringen til, mens du er hjemme.** Hold øje med *Overvågning* og med inverterens egen app den første dag.
   Ser noget forkert ud, så slå styringen fra – inverteren går tilbage til selvforbrug.
3. **Sæt beskeder op.** Ret `script.wattlas_besked` til din telefon, og tryk *Send testbesked* i *Overvågning*.
4. **Tjek økonomien efter en uge.** *Økonomi* viser, hvad Wattlas har sparet i forhold til ikke at have batteri.

## Hverdagen

Normalt skal du ingenting. Det, folk typisk bruger:

| Situation | Gør dette |
|---|---|
| Storm eller varslet strømsvigt | **Lad nu** til 100 % og hæv **Reserve** et par dage |
| Gæster, ferie eller et dyrt apparat skal køre i aften | **Gem batteriet** nogle timer i forvejen, eller en regel |
| Strømmen er dyr nu, men planen venter | **Brug batteriet** |
| Vinter (lidt sol, kolde nætter) | hæv **Reserve** til 20–30 % |
| Netselskabet skifter tarif (sommer/vinter) | ret de tre nettarif-helpers (se [KONFIGURATION.md](KONFIGURATION.md)) |
| Arbejde på inverter eller batteri | slå **Wattlas styrer batteriet** fra først |
| Ny version af Wattlas | opdatér *Wattlas* i Markedspladsen, og tryk *Genstart* under Reparationer; dine indstillinger bevares |

## Wattlas Styring → Styring

### Øverst: hvad sker der nu
Den store linje fortæller, hvad batteriet gør lige nu (lader fra sol eller net, forsyner huset eller hviler), og om planen
er frisk. *Planens logik ›* forklarer hvorfor.

### Manuel tilsidesættelse
Til de gange, hvor du ved noget, planen ikke ved. Vælg først **varighed** (30 min, 1, 2 eller 4 timer eller til midnat),
og tryk så **Start** på en af knapperne. Tryk **Stop** for at afbryde. En tilsidesættelse udløber altid af sig selv.

| Knap | Hvad den gør | Brug den når |
|---|---|---|
| **Lad nu** | køber strøm og lader til det valgte niveau (60, 80 eller 100 %) | der er varslet storm eller strømsvigt |
| **Ingen netopladning** | batteriet må kun lades af solen | du ikke vil købe strøm til batteriet, fx fordi du venter sol |
| **Gem batteriet** | batteriet aflader ikke; huset bruger nettet | du vil gemme strømmen til senere, fx en dyr aften |
| **Brug batteriet** | batteriet forsyner huset ned til reserven | strømmen er dyr nu, og planen vil vente |
| **Stop solsalg** | overskudssol sælges ikke | salgsprisen er lav, eller du vil holde eksporten nede. *Automatisk igen* slår det fra |

*Seneste tilsidesættelser* viser de sidste 7 dage.

### Indstillinger til optimeringen
Disse tal sendes med til EMHASS ved hver beregning. Planen tager altså højde for dem i stedet for at kæmpe imod dem.

| Indstilling | Betydning | Tommelfingerregel |
|---|---|---|
| **Reserve** | laveste batteriniveau i planen | 15–20 % til daglig; hæv den om vinteren eller ved stormvarsel |
| **Batteri ved planens slutning** | hvor meget der skal være tilbage, når planens horisont slutter | 20–30 %, så planen ikke tømmer batteriet lige før en dyr morgen |
| **Maks. køb fra elnettet** | højeste import, planen må bruge (kW) | under din sikringsgrænse; kan ikke sættes over `wattlas_maks_netimport_w`. **0 = ingen ekstra grænse** (standard) |
| **Batterislid** | hvad en afladet kWh koster i slid | batteriets pris / (kapacitet × cykler). Højere = færre små runder |
| **Ugentlig fuldladning** | lader til 100 % mindst én gang om ugen | lad den være slået til; LiFePO4-celler skal balanceres |
| **Wattlas styrer batteriet** | hovedafbryderen | slå fra = inverteren kører selvforbrug med 15 % reserve |

Er du i tvivl om en ændring, så prøv den i **Hvad-hvis** først.

### Hvad-hvis
Prøv andre indstillinger uden at røre den rigtige styring.

1. Skru på reserve, slut-niveau, maks. køb og slid. Slå evt. **Med fleksibel forbruger** til.
2. Tryk **Beregn**. EMHASS laver en ekstra plan ved siden af den rigtige.
3. Sammenlign: regning for hele horisonten, køb fra nettet, batteri afladet og laveste batteriniveau, plus en graf over
   batteriniveauet med og uden ændringen.
4. Er du tilfreds, tryk **Brug disse indstillinger**. Så kopieres tallene over i den rigtige styring.

Et plus i *Forskel* betyder, at ændringen koster penge. Det kan være fint, hvis du får det, du bad om, fx mere reserve.

### Fleksibel forbruger
Lad EMHASS vælge de bedste timer til et apparat, der bare skal køre et vist antal timer pr. døgn: varmtvandsbeholder,
pool, affugter eller elbil.

| Felt | Betydning |
|---|---|
| **Navn** | det, appen kalder den |
| **Kontakt** | den entitet, Wattlas tænder og slukker: `switch.…`, `light.…` eller `input_boolean.…` |
| **Effekt** | hvad apparatet bruger, når det kører (W) |
| **Timer pr. døgn** | hvor mange timer det skal køre i hver periode |
| **Skal være færdig kl.** | periodens slut; en ny periode starter her |
| **Wattlas styrer forbrugeren** | slår styringen til. Kan først slås til, når kontakten findes |

Wattlas tænder kun kontakten, når planen er frisk og har lagt en kørsel i dette tidsrum, og slukker den, når timerne er
brugt. Uden frisk plan er kontakten slukket, så sørg for, at apparatet har sin egen termostat eller sikring.
Prøv den i Hvad-hvis først, så du kan se, hvornår den vil køre.

## Wattlas Styring → Regler
Faste regler for bestemte tidsrum, fx "hverdage 16–21: gem batteriet".

1. Tryk **+ Ny regel**, giv den et navn, og vælg type, dage og tidsrum.
2. Slå den til med kontakten til venstre.
3. Tryk **Gem regler**. Intet ændres, før du har gemt.

Typerne er de samme som de manuelle tilsidesættelser, plus **Lad fra elnettet til …** med et valgfrit niveau.
Dagene kan være alle, hverdage (arbejdsdage), fridage/helligdage eller weekend; hverdage og fridage kommer fra Workday,
så helligdage tæller med.

Reglerne ændrer kun det, styringen udfører. EMHASS kender dem ikke, så *Planens logik* kan vise noget andet i de tidsrum.
Brug hellere **Indstillinger til optimeringen**, hvis det, du vil, kan siges som et tal. Så regner planen med det.

## Wattlas Styring → Planens logik
Viser, hvad EMHASS har planlagt for de næste 24–48 timer, og hvorfor:

- nøgletal for perioden: forventet regning, køb, sol, batteri og prisspænd
- **Pris og batteriniveau**: én søjle pr. halve time, farvet efter hvad batteriet gør
- **Energi pr. halvtime**: sol, net, batteri og salg
- **Hvorfor gør planen sådan?**: hver periode forklaret med priser og regnestykke
- **Tjek – er planen fornuftig?**: 7 automatiske tjek, fx at reserven holdes, at netopladning ligger i de billigste
  timer, og at solstrøm først sælges, når batteriet er fuldt

Står et tjek gult, så læs forklaringen under det. Det er ikke nødvendigvis en fejl, men et sted at kigge.

## Wattlas Styring → Overvågning
- **Advarsler**: alt grønt = alt i orden. En gul linje fortæller, hvad der er galt (fx manglende plan, gamle målinger,
  høj netbelastning, batteritemperatur).
- **Forbindelser og plan**: målekilde, styrekanal, planens alder og EMHASS-status.
- **Beskeder til telefonen**: slå push og "normalt igen"-beskeder til eller fra. *Send testbesked* tjekker, at
  `script.wattlas_besked` når frem.
- **Beregn ny plan nu**: hvis du har ændret noget og ikke vil vente 5 minutter.

## Wattlas Styring → Teknik
Rå tal fra inverteren: strenge (PV) med spænding og strøm, udgang, net og husets last pr. fase, batteriets spænding,
temperatur og sundhed, inverterens egne indstillinger og de 6 tidsprogrammer, som Wattlas skriver løbende.
Kun til aflæsning. Inverterens indstillinger ændres i inverteren eller Solarman, ikke her.

## Wattlas (appen)
| Fane | Indhold |
|---|---|
| **Live** | energiflowet lige nu, hvad strømmen koster, sparet i dag og dagen time for time |
| **Økonomi** | sparet pr. dag, uge, måned og år, mål, tilbagebetalingstid og resultater pr. dag |
| **Historik** | produktion, forbrug, salg, køb og batteri pr. måned, 30 dage eller år |
| **Elpris** | købs- og salgspris time for time i dag og i morgen, inkl. tariffer |
| **Solprognose** | prognose mod målt produktion i dag og de næste dage |

Søndag aften kommer der en ugerapport som besked.

## Når noget går galt

Wattlas falder altid tilbage til noget sikkert: mangler planen, bruges den gemte reserveplan (højst 2 timer gammel), og
derefter selvforbrug. Mistes målinger eller forbindelsen til inverteren, stoppes netladning, og inverteren sættes til
selvforbrug. Du får en besked, og Wattlas prøver selv igen.

| Du ser | Betyder | Gør dette |
|---|---|---|
| Gul linje øverst: *ikke færdigindstillet* | startspærren er aktiv | sæt de indstillinger, linjen nævner |
| *Inverteren svarer ikke* | ingen nye målinger i 10 min | tjek loggeren/WiFi og inverter-integrationen |
| *Mangler aktuel plan* | EMHASS har ikke lavet en brugbar plan | se beskeden *EMHASS – beregning fejlede* under Notifikationer; tjek EMHASS-app'en, nøglen og at priser og solprognose har data |
| *EMHASS – prognosedata mangler* | solprognosen har huller | se [SOLPROGNOSE.md](SOLPROGNOSE.md) |
| *Høj netbelastning* | en fase bruger mere end fasegrænsen + 25 % under netladning | Wattlas skruer selv ned; sker det tit, så sænk `wattlas_fase_graense_a` |
| *Periode følger ikke planen* | inverterens tidsprogram svarer ikke til det, Wattlas skrev | tjek at "Time of use" er slået til, og at programtiderne er 01, 05, 09, 13, 17 og 21 |
| Et tjek i *Planens logik* er gult | planen ser mærkelig ud | læs forklaringen; ofte er det ok (fx små prisforskelle) |

Er du i tvivl: slå **Wattlas styrer batteriet** fra. Så kører inverteren almindeligt selvforbrug, og intet går i stykker.

## Én eller flere invertere

### Én inverter (det normale)
Wattlas er bygget til **én hybrid-inverter med batteri**, og det er det, de fleste har. Du skal ikke gøre noget
særligt: styrekanalen læser solproduktion, batteri, net og hus fra den ene inverter, og appens energiflow viser
den samlede sol. Lad `pv_anlaeg` og `inverter2_…` være udkommenteret i dashboards.

Vil du se dine to strenge (MPPT 1 og 2) hver for sig i energiflowet, så tilføj fx i `dashboards/wattlas.yaml`:

```yaml
pv_anlaeg:
  - {navn: Syd, entitet: sensor.min_inverter_pv1_power}
  - {navn: Vest, entitet: sensor.min_inverter_pv2_power}
```

### En ekstra inverter uden batteri
Har du også en almindelig streng-inverter (fx et ældre anlæg), afhænger det af, hvor den sidder:

| Tilslutning | Hvad Wattlas gør | Hvad du skal gøre |
|---|---|---|
| **På Deyes GEN-/mikroinverter-port** | tæller den automatisk med i solproduktionen (`…_microinverter_power`) og i planen | intet. Valgfrit: vis den i *Teknik* og i energiflowet (se nedenfor) |
| **Direkte i husets eltavle** (AC-koblet) | Deyes CT ser den som lavere husforbrug. Styringen virker, men uden mere ved Wattlas ikke, at det er sol | vælg *I eltavlen* og dens effekt-sensor i opsætningen (eller læg den til `sensor.emhass_solproduktion_samlet` i styrekanal-filen), og sørg for at solprognosen dækker begge anlæg |

**Nemmest:** slå *Jeg har også en ekstra inverter uden batteri* til i opsætningen (trinnet *Din inverter*), så klarer
Wattlas det hele. Se [BILLEDGUIDE.md](BILLEDGUIDE.md).

Eller i hånden i `dashboards/wattlas_styring.yaml` og `dashboards/wattlas.yaml`:

```yaml
inverter2_prefix: min_strenginverter_      # Teknik-fanen: inverter 2's entiteter
inverter2_navn: streng-inverter
inverter2_relae: switch.min_strenginverter_relae   # valgfri: relæ der kan afbryde den
pv_anlaeg:
  - {navn: Hybrid, entitet: sensor.min_inverter_pv_power}
  - {navn: Streng, entitet: sensor.min_inverter_microinverter_power}
```

Kan streng-inverteren ikke selv begrænse eksport, så kan den afbrydes med et relæ ved negativ salgspris. Se
[eksempler/strenginverter_negativ_pris.yaml](../eksempler/strenginverter_negativ_pris.yaml).

**Solprognose med flere tagflader:** prognosen skal dække al sol, Wattlas kan bruge. Har du én Helios-sensor pr.
tagflade, så læg dem sammen til én sensor i samme format (se [SOLPROGNOSE.md](SOLPROGNOSE.md)).

### To hybrid-invertere med hver sit batteri
Understøttes **ikke** i denne version. Styrekanalen skriver til én inverters tidsprogrammer, og grænserne regnes for
ét batteri. Kører dine invertere i parallel som ét system, hvor den ene er master og styrer begge, kan det virke at
pege styrekanalen på master-inverteren. Det er ikke testet.

## Gode vaner
- Følg **Overvågning** den første uge.
- Ret de tre nettarif-helpers, når netselskabet skifter mellem sommer- og vintertarif.
- Slå **Wattlas styrer batteriet** fra, før du arbejder på inverteren eller batteriet.
