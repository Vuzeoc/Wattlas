# Om Wattlas

**Wattlas er en åben styring til solceller og batteri i Home Assistant. Den lader, når strømmen er billig, bruger
batteriet, når den er dyr, og passer på dine sikringer imens.**

> Wattlas er i **alpha**. Den kører dagligt hos udvikleren, men er ikke afprøvet i mange huse endnu.
> Læs [SIKKERHED.md](SIKKERHED.md), før du lader den styre din inverter.

## Hvorfor Wattlas findes

Mange anlæg bliver leveret med en færdig AI-styring fra leverandøren. Den er nem at komme i gang med, men udvikleren af
Wattlas oplevede tre ting, der blev ved med at irritere:

- **Udfald.** Når styringen eller dens forbindelse faldt ud, stod batteriet stille, og man opdagede det først bagefter.
- **Beslutninger, man ikke kunne forstå.** Batteriet blev ladet eller afladet på tidspunkter, der ikke gav mening,
  og der var ingen forklaring at finde.
- **Ingen plads til resten af huset.** Varmepumpen, varmtvandsbeholderen, ladestanderen og opvaskeren kunne ikke
  kobles på, selv om det er dem, der bruger strømmen.

Wattlas er svaret på de tre ting: en styring, der kører lokalt i dit eget Home Assistant, som viser hvorfor den gør,
som den gør, og som kan arbejde sammen med alt det udstyr, Home Assistant kender.

## Wattlas mod en færdig AI-styring

| | Færdig AI-styring fra leverandøren | Wattlas |
|---|---|---|
| **Hvor den kører** | Typisk i leverandørens sky. Falder forbindelsen ud, står styringen | Lokalt i dit eget Home Assistant |
| **Når noget går galt** | Du opdager det ofte først bagefter | Skifter selv til selvforbrug, sender besked og genoptager |
| **Hvorfor gør den sådan?** | Sjældent en forklaring | Hver beslutning vises med priser og regnestykke, plus 7 automatiske tjek |
| **Sikringerne** | Lader ofte uden at se på, hvad huset bruger imens | Grænse pr. fase og samlet loft, som du selv sætter |
| **Resten af huset** | Kun det udstyr, leverandøren har valgt | Alt, Home Assistant kender, kan kobles på: varmepumper, termostater, ladestander, hvidevarer |
| **Din kontrol** | Få indstillinger | Tilsidesættelser med ét tryk, faste regler og hvad-hvis-beregning |
| **Dine data** | Typisk hos leverandøren | Bliver i dit hus |
| **Koden** | Lukket | Open source – du kan se og ændre alt |
| **Nye ønsker** | Du venter på leverandøren | Opret et issue – gode forslag bygges ind |

Venstre kolonne er udviklerens erfaring og det typiske billede, ikke en dom over en bestemt leverandør. Tjek, hvad din
egen løsning kan.

**Hvad en færdig løsning er bedre til:** den virker ud af kassen, kræver ikke Home Assistant, og der er en leverandør
at ringe til. Wattlas kræver, at du selv sætter dine grænser og holder øje den første tid. Til gengæld bestemmer du selv.

## Hvad Wattlas gør

- **Lægger en plan for de næste 24–48 timer.** Planen regnes af [EMHASS](https://emhass.readthedocs.io/) ud fra
  spotpriser, nettarif, solprognose og husets forbrug. Den regnes om hvert 5. minut.
- **Lader billigt, bruger dyrt.** Batteriet lades fra nettet i de billigste timer og dækker huset i de dyre. Overskydende
  sol gemmes, og sælges kun, når salgsprisen efter gebyrer er positiv.
- **Forklarer sig selv.** Fanen *Planens logik* viser hver beslutning med priser og regnestykke, og syv automatiske tjek
  fortæller, om planen holder.
- **Klarer udfald selv.** Mister Wattlas målinger, plan eller forbindelse, stopper den netladningen, sætter inverteren til
  selvforbrug, sender en besked og prøver igen af sig selv. En gemt reserveplan dækker korte udfald.
- **Lader dig bestemme.** *Lad nu*, *Gem batteriet*, *Brug batteriet*, *Ingen netopladning* og *Stop solsalg* virker med
  ét tryk og udløber altid af sig selv. Faste regler klarer det, der gentager sig, fx "hverdage 16–21: gem batteriet".
- **Viser økonomien.** Sparet i dag, i denne uge og i alt, tilbagebetalingstid og en ugerapport.

## Sikringerne først

En billig time er en god grund til at lade batteriet. Men hvis ovnen, kogepladerne og varmepumpen kører samtidig, kan
opladningen lægge så meget oveni, at hovedsikringen bliver overbelastet. Mange styringer tager ikke højde for det.

Wattlas måler strømmen på hver fase og holder **husets forbrug plus opladning under en grænse, du selv sætter**:

- en grænse pr. fase i ampere, fx 16 A på en 20 A hovedsikring
- et loft over den samlede effekt fra elnettet

Laver du mad, mens batteriet lader, skruer Wattlas ned for opladningen eller holder pause, og fortsætter, når der er
plads igen. Grænserne gælder altid, også når du selv trykker *Lad nu*.

## Kobl resten af huset på

Wattlas kører i Home Assistant. Alt, hvad Home Assistant kan tænde, slukke eller indstille, kan derfor arbejde sammen
med planen: luft til luft-varmepumper, luft til vand-varmepumper, radiatortermostater, varmtvandsbeholdere, ladestandere,
pool og hvidevarer.

**Indbygget i alpha:**

- **Fleksibel forbruger.** Vælg en kontakt, en effekt og hvor mange timer den skal køre inden et tidspunkt. Så lægger
  planen den i de bedste timer. God til varmtvandsbeholder, elbil eller pool.
- **Wattlas' tal er almindelige sensorer.** Elprisen lige nu, hvad strømmen i batteriet har kostet, batteriniveau,
  soloverskud og planens næste skridt kan bruges i dine egne automationer.
- **Eksempler** til at komme i gang ligger i mappen [`eksempler/`](../eksempler).

**Ikke indbygget endnu:** færdige opsætninger til bestemte varmepumper, termostater og ladestandere. Dem bygger du i dag
som almindelige automationer oven på Wattlas' tal, sådan som eksemplet nedenfor viser. Flere fleksible forbrugere og
færdige koblinger står højt på ønskelisten.

## Eksempel: udviklerens eget hus

Et parcelhus med solceller på taget, en 20 kW hybrid-inverter, ca. 30 kWh batteri, luft til vand-varmepumpe og
luft til luft-varmepumper. Alt styres fra Home Assistant.

**Sådan arbejder huset sammen med Wattlas:**

- **Varmt vand på solen.** Når der sælges meget sol, batteriet er fuldt, og planen også regner med at sælge, bedes
  varmepumpen om en ekstra opvarmning af det varme vand. El-patronen er spærret imens, så det kun er kompressoren,
  der bruger solstrømmen.
- **Varme, når strømmen er billig.** Termostaterne hæver temperaturen lidt i de billigste timer, så huset er varmt, før
  de dyre timer kommer.
- **Opvaskeren flyttes** til de billigste timer, og huset siger besked om, hvornår den vasker.
- **En ældre inverter uden batteri** holder op med at sælge, når salgsprisen er negativ.

**Tal fra en måned i efteråret** (midt oktober til midt november, ca. 59 kWh forbrug og 14 kWh sol pr. dag):

| | |
|---|---|
| Ladet fra nettet om natten | ca. 17 kWh pr. dag |
| Leveret fra batteriet til huset | ca. 23 kWh pr. dag |
| Andel af købet, der lå i de dyre timer kl. 17–21 | 2 % |
| Udnyttelse af batteriet | 87 % af det, der var muligt med perfekt kendskab til fremtiden |
| Besparelse mod almindelig selvforbrug | 20–27 kr. pr. dag, eller 15–22 kr. efter slid på batteriet |

"Almindelig selvforbrug" er den styring, enhver hybrid-inverter kan selv: gem solen, brug den om aftenen. Den er
simuleret på de samme dage med de samme priser.

Om sommeren er forskellen lille. Da fylder solen batteriet, og der er ikke meget at vinde ved at lade fra nettet.
Gevinsten ligger i efterår, vinter og forår, hvor batteriet ellers står næsten stille.

Tallene er fra ét hus og regnet af udvikleren selv. Dit forbrug, din tarif og dit anlæg giver andre tal.

## Hvilke invertere

Wattlas taler med inverteren gennem en *styrekanal*, en lille fil, der oversætter planen til netop din inverter.
Resten af Wattlas er det samme for alle.

- **Deye, direkte.** Det er den inverter, udvikleren selv har, og den eneste direkte kobling, der kan testes i
  hverdagen. Den kører via integrationen Solarman.
- **Gennem en SunMate-boks.** Styrer en SunMate din inverter, kan Wattlas styre gennem den. Det åbner for de mange
  invertere, boksen understøtter. Styrekanalen er med, men er ikke afprøvet med denne udgave endnu.
- **Andre invertere.** Flere kan tilføjes. Vi har kun en Deye at teste på, så en direkte kobling til et andet mærke
  kræver en, der har inverteren. **Har du en anden inverter, hjælper vi gerne med at bygge og teste koblingen sammen
  med dig** – opret et issue og fortæl, hvilken inverter du har. Se også [STYREKANALER.md](STYREKANALER.md).

## Hvem Wattlas passer til

- Du har en hybrid-inverter med batteri, som Home Assistant kan både læse og styre.
- Du bor i Danmark og har timepriser. Tarifferne er sat op til den danske model.
- Du er ikke bange for Home Assistant. Installationen sker i skærmbilleder uden kommandoer
  (se [BILLEDGUIDE.md](BILLEDGUIDE.md)), men du skal kende dine egne sikringer og batteriets grænser.

## Åben kildekode – vær med

Wattlas er open source under MIT-licensen. Den er bygget til ét hus og skal nu lære at passe til mange.

- **Har du en idé eller et ønske?** Opret et issue på GitHub. Fortæl, hvad du gerne vil styre, og hvilket udstyr du har.
- **Virker noget ikke hos dig?** Opret et issue med din inverter-type og hvad der skete. Skriv aldrig nøgler eller
  adresser i issuet.
- **Har du en anden inverter?** Skriv til os i et issue, så bygger og tester vi koblingen sammen med dig.

Gode forslag bliver bygget ind.
