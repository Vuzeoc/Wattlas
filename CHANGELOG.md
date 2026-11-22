# Ændringer

Wattlas er i **alpha**: den kører dagligt hos udvikleren, men er ikke afprøvet i mange huse endnu.

## 0.2.2
- **Rettet:** på telefonen kunne siden hoppe op til toppen, mens man rullede, fordi appen byggede sig selv om hvert 5. sekund. Nu bygges den kun om, når noget faktisk er ændret, og rullepositionen holdes fast
- En ekstra inverter, der slukker om natten, vises som *Sover – for lidt lys* i stedet for en tabel med "unavailable". Svarer den ikke, mens der er sol på hovedanlægget, vises en advarsel
- Billeder fra telefonen på forsiden

## 0.2.1
Klar til Markedspladsens katalog. Ingen ændringer i styringen.
- Automatiske tjek på GitHub (HACS og hassfest)
- Licensfilen er ren MIT, så GitHub genkender den (ansvarsfraskrivelsen står i README og SIKKERHED.md)
- Kodeejer, land og rækkefølge for app-oversigten i manifestet

## 0.2.0
Første udgave med et rigtigt versionsnavn i Markedspladsen.
- Logo i Markedspladsen og under Integrationer
- Markedspladsen viser versionsnavnet og tilbyder kun en opdatering, når der kommer en ny udgave
- Beskrivelse af projektet ([docs/OM_WATTLAS.md](docs/OM_WATTLAS.md)) og kort beskrivelse øverst på forsiden
- Billedguiden forklarer, at Markedspladsen beder om en GitHub-forbindelse første gang
- Genstart-beskeden bliver stående, hvis Wattlas fjernes og tilføjes igen uden genstart
- Fjernes Wattlas, mens inverteren ikke svarer, siger beskeden det og beder dig tjekke tidsprogrammerne
- En ny standardværdi i en senere version når også dem, der allerede har sat Wattlas op

## 0.1.1-alpha
Første offentlige udgave (0.1.0-alpha var en intern testudgave).
- EMHASS-styring med plan-validering, reserveplan, fasegrænse og startspærre
- Tilsidesættelser, tidsstyrede regler, hvad-hvis og fleksibel forbruger
- Styrekanaler: Deye via Solarman, SunMate (ikke testet)
- App: Wattlas (live, økonomi, historik, elpris, solprognose) og Wattlas Styring (styring, regler, planens logik, overvågning, teknik)
- Økonomi, rekorder, ugerapport og besked ved mistet inverterforbindelse
- Integration til Markedspladsen: tjekker forudsætninger med knapper til det, der mangler, opsætning i skærmbilleder,
  installerer og opdaterer selv, genstart-knap under Reparationer, flytter filer til backup ved fjernelse
- `install.sh`: lægger integrationen ind uden Markedspladsen; alt andet (inverter, ekstra inverter, tjek) sker i opsætningen
- Fjernes integrationen, slås styringen fra først, og inverteren sættes til selvforbrug
- Batteriets slidpris spørges der om i opsætningen (forslag 0,25 kr./kWh); *Ugentlig fuldladning* husker dit valg efter genstart
- En opdatering, der fejler, vises under Reparationer; de 3 nyeste backup-mapper gemmes
- Én inverter uden GEN-port-sensor blokerer ikke længere netladning
- Første plan virker på en helt ny installation: husprognosen bruger det aktuelle forbrug, indtil der er 3 dages historik,
  og Wattlas sender selv `set_use_battery` og antal fleksible forbrugere til EMHASS (kun API-nøglen skal sættes i app'en)
- *Maks. køb fra elnettet* og hvad-hvis følger nu dit importloft (0 = ingen ekstra grænse); før kunne nye brugere starte på 1 kW
- Planens-logik-kortet hentes med samme version som app-kortet, så det også opdateres efter en ny version
- Brugsvejledning: [docs/BRUG.md](docs/BRUG.md)
- Alarmen for høj netbelastning følger fasegrænsen (+25 %), og husets kuldejustering er en indstilling
