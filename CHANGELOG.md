# Ændringer

## 0.1.0-alpha
Første offentlige udgave.
- EMHASS-styring med plan-validering, reserveplan, fasegrænse og startspærre
- Tilsidesættelser, tidsstyrede regler, hvad-hvis og fleksibel forbruger
- Styrekanaler: Deye via Solarman, SunMate (ikke testet)
- App: Wattlas (live, økonomi, historik, elpris, solprognose) og Wattlas Styring (styring, regler, planens logik, overvågning, teknik)
- Økonomi, rekorder, ugerapport og besked ved mistet inverterforbindelse
- `install.sh`: installerer packages, styrekanal, kort og begge dashboards med én kommando; valgfri ekstra inverter
  uden batteri (`--inverter2`, GEN-port eller AC-koblet)
- Én inverter uden GEN-port-sensor blokerer ikke længere netladning
- Brugsvejledning: [docs/BRUG.md](docs/BRUG.md)
- Alarmen for høj netbelastning følger fasegrænsen (+25 %), og husets kuldejustering er en indstilling
