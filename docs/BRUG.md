# Sådan bruger du Wattlas

Wattlas kører af sig selv, når det er sat op: EMHASS lægger en ny plan hvert 5. minut, og Wattlas følger den hvert
30. sekund. Det meste af tiden skal du intet gøre. Denne side forklarer, hvad du kan skrue på, og hvornår det giver mening.

Rækkefølgen, Wattlas følger: **manuel tilsidesættelse → første aktive regel → planen**. Sikkerhedsgrænserne (sikringer,
faser, spænding, batteriets strømme og reserve) gælder altid, uanset hvad du vælger.

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
| **Maks. køb fra elnettet** | højeste import, planen må bruge (kW) | under din sikringsgrænse; kan ikke sættes over `wattlas_maks_netimport_w` |
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

## Gode vaner
- Følg **Overvågning** den første uge.
- Ret de tre nettarif-helpers, når netselskabet skifter mellem sommer- og vintertarif.
- Slå **Wattlas styrer batteriet** fra, før du arbejder på inverteren eller batteriet.
