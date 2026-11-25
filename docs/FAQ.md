# FAQ

**Hvorfor lader den fra nettet midt på eftermiddagen?**
Fordi strømmen er billigere nu end i spidslasten kl. 17–21, og forskellen er større end tab og slid. Se *Planens logik*.
Fanen viser hver beslutning med priser og regnestykke.

**Hvorfor sælger den ikke fra batteriet?**
Det er fravalgt (`set_nodischarge_to_grid`). Kun overskudssol sælges, og kun når salgsprisen efter gebyrer er positiv.

**Kan jeg bruge Wattlas uden at den styrer?**
Ja. Lad `Wattlas styrer` være slået fra. App, økonomi, historik og planens logik virker stadig, når
`binary_sensor.wattlas_konfigureret` er on. Det er en god måde at se planen an på i nogle dage.

**Hvad sker der, hvis Home Assistant genstarter eller går ned?**
Inverteren kører videre med de sidst skrevne tidsprogrammer. Efter genstart rydder Wattlas op og sætter selvforbrug,
indtil målinger og plan er friske igen. Derefter genoptager den automatisk.

**Hvad med sommer- og vintertarif?**
Vælg dit netselskab under Indstillinger → Enheder og tjenester → Wattlas → Konfigurer → *Netselskab*. Så henter Wattlas nettarif,
elafgift og Energinets tariffer hver dag fra Energinets åbne liste, også når de skifter. Ellers retter du selv de tre
nettarif-helpers og elafgiften; Wattlas minder dig om det 1. januar, 1. april og 1. oktober.

**Hvad sender Wattlas, når den henter tariffer?**
Normalt ét kald om dagen til `api.energidataservice.dk` med netselskabets nummer og tarifkoder (også efter en genstart, hver time hvis det
mislykkes, og når du vælger netselskab). Ingen adresse, målernummer eller nøgle. Energinet
gemmer den IP-adresse, kaldet kommer fra, i 3 måneder. Vælger du at taste selv, sendes intet.
Data: Energinet (www.energidataservice.dk), CC BY 4.0.

**Hvorfor kan Wattlas ikke hente mit netselskabs tarif?**
Den skal være *Nettarif C* (husholdninger) med de tre tidsrum 0–6, 6–17/21–24 og 17–21. Er der fejl på listen, er prisen 0, eller står
selskabet der ikke, beholder Wattlas de seneste tal og viser en reparation, hvis hentning er slået til. Tast dem selv imens.

**Min inverter er ikke Deye.**
Se [STYREKANALER.md](STYREKANALER.md). Kan den styres fra HA med lade-/afladegrænser og tidsprogrammer, kan der skrives
en styrekanal til den.

**Kan jeg bruge et højvolt-batteri?**
Ikke i alpha. Spændingsvinduet 45–58 V er bygget ind som sikkerhedsgrænse.

**Hvor ser jeg, hvad Wattlas har gjort?**
*Overvågning* viser alarmer og de seneste beskeder. Logbogen viser hver skrivning (`emhass.solsalg`, diagnoselog).
Traces på `script.emhass_reguler` viser hver regulering.

**Kan Wattlas styre min varmepumpe, mine radiatorer eller min ladestander?**
Kun med tænd/sluk: der er én *fleksibel forbruger* (en kontakt, fx en lader eller varmtvand, som planen lægger i de bedste
timer), og Wattlas' priser, plan og soloverskud er almindelige sensorer, du kan bruge i dine egne automationer.
[OM_WATTLAS.md](OM_WATTLAS.md) viser, hvordan udviklerens eget hus gør. Færdige koblinger står højt på ønskelisten –
skriv gerne, hvad du har.

**Hvordan melder jeg en fejl?** Hent *Download diagnostik* under Indstillinger → Enheder og tjenester → Wattlas → ⋮, og vedhæft filen
til et issue på Wattlas' GitHub-side. Den rummer styrekanalen, dine tal og Wattlas' egne tilstande – ikke adresse,
nøgle, token, placering, navne eller dine egne entiteter. Kig den gerne igennem, før du sender den.
