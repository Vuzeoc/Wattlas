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
Ret de tre nettarif-helpers, når netselskabet skifter. Automatisk skift er ikke med i alpha.

**Min inverter er ikke Deye.**
Se [STYREKANALER.md](STYREKANALER.md). Kan den styres fra HA med lade-/afladegrænser og tidsprogrammer, kan der skrives
en styrekanal til den.

**Kan jeg bruge et højvolt-batteri?**
Ikke i alpha. Spændingsvinduet 45–58 V er bygget ind som sikkerhedsgrænse.

**Hvor ser jeg, hvad Wattlas har gjort?**
*Overvågning* viser alarmer og de seneste beskeder. Logbogen viser hver skrivning (`emhass.solsalg`, diagnoselog).
Traces på `script.emhass_reguler` viser hver regulering.

**Kan Wattlas styre min varmepumpe, mine radiatorer eller min ladestander?**
Ikke med en færdig opsætning endnu. I alpha er der én *fleksibel forbruger* (en kontakt, som planen lægger i de bedste
timer), og Wattlas' priser, plan og soloverskud er almindelige sensorer, du kan bruge i dine egne automationer.
[OM_WATTLAS.md](OM_WATTLAS.md) viser, hvordan udviklerens eget hus gør. Færdige koblinger står højt på ønskelisten –
skriv gerne, hvad du har.
