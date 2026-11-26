# Elbil-lader

Wattlas kan styre din lader gennem den integration, du allerede har i Home Assistant. Du behøver ikke have bilen i Home Assistant.
**Eksperimentel:** afprøvet på udviklerens egen lader og med falske ladere – se [Hvad er afprøvet](#hvad-er-afprøvet). Navnene på mærkerne er læst i
integrationernes kode, ikke prøvet på hver lader.

## Kom i gang
1. **Sæt laderen op i Home Assistant** (Indstillinger → Enheder og tjenester), så du kan se dens effekt.
2. **Wattlas → Konfigurer → *Elbil-lader: lad Wattlas styre den*.** Vælg din lader på listen. Wattlas finder selv resten.
3. **Skriv antal faser og højeste strøm.** Er du i tvivl: lidt under laderens egen sikring (16 A-gruppe → 15 A).
4. **Prøv laderen.** Sæt stikket i bilen, og lad Wattlas starte, justere og stoppe. Det tager 2–4 minutter. Bliv i nærheden: virker stop ikke,
   så tag stikket ud.
5. Åbn appen: der er kommet en fane, **Elbil**. Den vises kun, når en lader er valgt.

Er laderen ikke på listen, så vælg *Min lader er ikke på listen* og peg på den. Du skal bruge dens effekt og **én** af disse: en kontakt, to knapper (start og
stop) eller et tal for strømmen.

## Bilen i Home Assistant (valgfrit)
Har du bilen i Home Assistant, så vælg dens **batteri i %** i samme vindue, og skriv batteriets størrelse i kWh. Wattlas finder selv stikket og rækkevidden.
Så vælger du *lad til 80 %* i stedet for kWh. Bilens tal vises kun, når den sidder i laderen; sidder en gæst i laderen, bruges kWh. Er bilens tal
gamle, regner Wattlas det ladede med.

**To grænser i *Klar til tid*** (når bilen er i Home Assistant): *Lad til* gælder strøm fra nettet, *Sol op til* gratis sol – fx 80 % fra nettet og
100 % på sol. *Sol op til* er aldrig lavere end *Lad til*. Gratis sol er det, huset ikke selv bruger, og som planen ikke lader husbatteriet med.
**100 % til næste tur** løfter målet til 100 % og slår fra af sig selv, når bilen er fuld eller kobles fra. *Kun sol* lader som før, til bilen selv stopper.

## Tilstande
| Tilstand | Hvad den gør |
|---|---|
| **Lad nu** | fuld strøm med det samme |
| **Klar til tid** | så mange kWh, du vælger, i de billigste timer og færdig til klokkeslættet. Nås det ikke ellers, lades der uanset prisen. Imellem lader den på gratis sol (overskud, der ellers sælges), når der er nok til laveste strøm. Ved *Energi* står, hvor længe det cirka tager ved fuld strøm |
| **Kun sol** | kun strøm, huset ikke selv bruger. Kræver overskud til laderens laveste strøm (6 A: ca. 1,4 kW på én fase, 4,1 kW på tre) |
| **Stop** | stopper ladningen og holder laderen stoppet – også hvis den startes et andet sted |
| **Slip laderen** | Wattlas slipper laderen og sender intet. **En ladning, der er i gang, kører videre** – vælg *Stop* for at stoppe. Brug laderens eller bilens egen app |

**Kun fra elnettet** (kontakt på fanen Elbil): husbatteriet aflader ikke, mens bilen lader. Bilen får strøm fra nettet og solen, og batteriet må stadig lades.
Imens køber hele huset fra nettet, også i dyre timer. Slået fra følger batteriet planen som ellers og kan også dække bilen.

Wattlas lader med **fuld strøm eller slet ikke**. Strømmen skrues kun ned, når faserne eller importloftet kræver det (eller solen i *Kun sol*). Lader batteriet
fra nettet, viger det for bilen.

## Hvad skal laderen kunne?
| Laderen kan | Wattlas kan |
|---|---|
| kun vise sin effekt | holde husbatteriet, mens bilen lader (*Kun fra elnettet*, også under Konfigurer → *Elbil: hold batteriet*) |
| starte og stoppe | alle tilstande, men ikke skrue ned: der skal være plads til laderens fulde strøm |
| starte, stoppe og få en strøm i ampere | det hele |

- **Laderen skal sidde bag den måler, Wattlas bruger.** Ellers kan Wattlas ikke passe på faserne, og ladningen stoppes.
- Wattlas' målinger skal være friske. Mangler de i to minutter, stoppes ladningen.
- **Kun én må styre.** Slå laderens tidsplan, smart-opladning og solstyring fra, også i bilen.
- Sky-ladere (fx Easee, Zaptec, Wallbox) hæves højst hvert kvarter og sænkes med det samme, men skyen kan være langsom eller nede.
- **OCPP:** sæt laderen til HA's OCPP-integration (vælg 10–20 s som måleinterval). Stop sendes som 0 A. Brug **ikke** integrationens egen *Charge Control* til at stoppe:
  nogle ladere lader videre på 6 A, mens Home Assistant viser 0 W.

## Hvad er afprøvet
- **En rigtig 11 kW-lader (OCPP 1.6-J, tre faser) med en rigtig bil, hos udvikleren.** Laderen blev styret direkte over OCPP: start på 1–2 sekunder,
  strømmen skruet op og ned under ladning (på ca. 5 sekunder), stop med 0 A (4 af 4), og start igen uden at tage stikket ud (3 af 3). Det er de fund, Wattlas'
  OCPP-styring er bygget på:
  - En grænse sendt sammen med starten blev ignoreret, så laderen gik op på fuld strøm. Wattlas sender derfor grænsen igen, så snart ladningen er startet.
  - Kun hele ampere: 8.0 blev afvist, 8 blev taget imod.
  - *RemoteStop* stoppede ikke bilen (den ladede videre på 6 A). Wattlas stopper derfor med 0 A.
  - Samme lader over Modbus kunne starte og skrue på strømmen, men ikke stoppe. Brug OCPP, hvis din lader kan begge dele.
- **Home Assistants OCPP-integration** er prøvet i en test-installation mod en falsk OCPP-lader: prøven, lad nu, stop, start igen, skygge og genstart af Home Assistant.
  Den rigtige lader er endnu ikke kørt gennem Home Assistants OCPP-integration.
- **Easee, Zaptec, Wallbox og de andre på listen** er kun prøvet i de automatiske tests med falske ladere.

## Sikkerhed
- **Wattlas tror på målingen, ikke på svaret.** Stopper bilen ikke, sendes stop igen, og du får besked. Trækker den mere, end Wattlas bad om, stoppes den.
- Over hovedsikringen sænkes strømmen straks til laveste trin, og efter et minut stoppes der. Uden hovedsikring i opsætningen bruges fasegrænsen.
- **Genstarter eller går Home Assistant ned, kører laderen videre på den sidste strøm**, til Wattlas er tilbage (ved en genstart typisk 1–2 minutter). Wattlas prøver at
  stoppe den, når Home Assistant lukker, men med OCPP når det ikke frem. Sæt derfor altid laderens egen maksstrøm til det, gruppen tåler.
- I skygge vises kun, hvad Wattlas ville gøre.
- Wattlas erstatter ikke sikringer, HPFI eller laderens egne værn. Spørg din elinstallatør, hvis du er i tvivl.

## Virker det ikke?
| Besked | Prøv |
|---|---|
| *For lidt plads på faserne* ved prøven | vent, til der bruges mindre strøm, eller stop batteriladningen imens |
| *Elbil-laderen stopper ikke* | stop den i laderens app, eller tag stikket ud. Kør prøven igen |
| *Elbil-laderen ses ikke i husets måling* | laderen sidder på en anden måler end den, Wattlas bruger |
| *Elbil-laderen tager ikke imod* | tjek laderens integration. Wattlas prøver igen |
| *Bilen tager ikke imod* | bilen er fuld eller venter på sin egen tidsplan. Wattlas prøver igen efter en halv time |
