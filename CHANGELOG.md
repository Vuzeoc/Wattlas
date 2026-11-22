# Ændringer

## 0.1.0-alpha
Første offentlige udgave.
- EMHASS-styring med plan-validering, reserveplan, fasegrænse og startspærre
- Tilsidesættelser, tidsstyrede regler, hvad-hvis og fleksibel forbruger
- Styrekanaler: Deye via Solarman, SunMate (ikke testet)
- App: Wattlas (live, økonomi, historik, elpris, solprognose) og Wattlas Styring (styring, regler, planens logik, overvågning, teknik)
- Økonomi, rekorder, ugerapport og besked ved mistet inverterforbindelse
- Integration til Markedspladsen: tjekker forudsætninger med knapper til det, der mangler, opsætning i skærmbilleder,
  installerer og opdaterer selv, genstart-knap under Reparationer, flytter filer til backup ved fjernelse
- `install.sh` (avanceret): installerer packages, styrekanal, kort og begge dashboards med én kommando; valgfri ekstra inverter
  uden batteri (`--inverter2`, GEN-port eller AC-koblet)
- Én inverter uden GEN-port-sensor blokerer ikke længere netladning
- Brugsvejledning: [docs/BRUG.md](docs/BRUG.md)
- Alarmen for høj netbelastning følger fasegrænsen (+25 %), og husets kuldejustering er en indstilling
