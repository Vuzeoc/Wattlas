# Ændringer

Wattlas er i **alpha**: den kører dagligt hos udvikleren, men er ikke afprøvet i mange huse endnu.

## 0.4.0
- **Ny styrekanal: Growatt** (eksperimentel) – trefasede hybrid-invertere (MOD/MID TL3-XH) via *solax_modbus* med lokal
  forbindelse. Styrer gennem Growatts VPP-fjernstyring med 10 minutters nedtælling, så inverteren selv går tilbage til normal
  drift, hvis Home Assistant stopper. Growatts elmåler giver ikke fasetal, så fasegrænsen regner med den værste fordeling
  (hele huset på én fase). Ikke kørt på et rigtigt anlæg endnu
- **Ny styrekanal: Deye via ESPHome** (eksperimentel) – til dem, der læser Deye direkte med en ESP32 + RS485
  (klatremis/esphome-for-deye) i stedet for Solarman-loggeren. Samme styring som Deye-kanalen
- **Skift af styrekanal** (fx fra Deye eller Huawei til Growatt) efterlod de gamle registreringer, så nogle sensorer fik "_2" i
  navnet, og køb/salg holdt op med at tælle i appen. Wattlas rydder nu selv op efter genstart (gælder også, hvis man har
  fjernet Wattlas og sat det op igen)
- **Spotpriser pr. kvarter:** planen og besparelsesregnskabet kræver ikke længere præcis én pris pr. time. Med kvarterpriser
  bruges halvtimens gennemsnit (før faldt planen ud). Med timepriser er alt som før
- Batteriets slid i strømpris-tallene følger nu din indstilling (før altid 0,25 kr./kWh)
- Opsætningen advarer, hvis Home Assistant ikke bruger standarddatabasen (SQLite) – husprognosen og appens historik kræver den
- "Selvforsyning i alt" kan ikke længere blive negativ
- Huawei: kun én stop-kommando, når netladning slås fra (før to)
- Ingen andre ændringer i styringen for Deye, SunMate og Huawei

## 0.3.1
- **Huawei med EMMA:** fortegnet på EMMA's målinger var vendt forkert (EMMA's *Feed in power* er positiv ved køb – nu bekræftet
  med data fra en rigtig EMMA-A02). I 0.3.0 fik det regnestykke-tjekket til at afvise målingerne, så Wattlas ikke styrede
  et EMMA-anlæg. Stadig eksperimentel: fasetallene og selve batteristyringen under EMMA er ikke bekræftet endnu
- Opsætning med EMMA: du vælger nu EMMA's *Feed in power* (før en fasesensor, der er slået fra som standard og derfor ikke kunne vælges)
- Er Wattlas opdateret uden at Home Assistant er genstartet, siger opsætningen det – i stedet for at vise felter uden tekst
- Ingen ændringer for Deye, SunMate og Huawei uden EMMA

## 0.3.0
- **Ny styrekanal: Huawei** – SUN2000 (hybrid) med LUNA2000-batteri og Huawei-elmåler via [Huawei Solar](https://github.com/wlcrs/huawei_solar).
  Netladning i de billige timer (i 10 minutter ad gangen, så ladningen stopper af sig selv, hvis Home Assistant går ned),
  *gem batteriet* via batteriets afladeeffekt, stop af solsalg og fasegrænse fra elmåleren. Testet mod en simuleret Huawei,
  **ikke kørt i drift endnu** – se [STYREKANALER.md](docs/STYREKANALER.md)
- Opsætningen spørger efter batteri og elmåler for Huawei og regner selv strømgrænserne ud fra effekterne
- **Huawei med EMMA:** elmåler, husforbrug og salgsloft fra EMMA (indbygget eller ekstern måler). Eksperimentel, ikke kørt i drift endnu
- **Regnestykke-tjek for Huawei:** passer sol, batteri, salg og forbrug ikke sammen i 2 minutter (fx et forkert fortegn), styrer Wattlas ikke
- Huawei: når Wattlas holder op med at styre, får batteriet din egen afladeeffekt tilbage, og et stoppet solsalg startes igen. Strømgrænserne følger effekt-indstillingerne
- App: batteriets tekst i live-billedet ligger ikke længere oven i strømkurven; knapperne under *Fleksibel forbruger*
  (og andre +/− og kontakter) viser den nye værdi med det samme; effekt og timer er forklaret; "Push til mobilen"
- **Styring (alle invertere):** netladestrømmen sænkes nu med det samme, når fasegrænsen eller importloftet kræver det.
  Før kunne den blive liggende op til 5 A (ca. 250 W) over for at spare skrivninger til inverteren
- `install.sh` henter seneste udgivelse i stedet for den nyeste kode
- Wattlas' egne tests kører nu automatisk på GitHub, også en ny test af fasegrænse, importloft og ladestrøm

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
