# Ændringer

Wattlas er i **alpha**: den kører dagligt hos udvikleren, men er ikke afprøvet i mange huse endnu.

## 0.4.2
- **Nye styrekanaler (eksperimentelle, ikke kørt på rigtige anlæg):** SolaX X3-Hybrid G4, Sofar HYD og Solis-hybrider –
  alle trefasede og lokalt via solax_modbus. Vælg dem i opsætningen; krav og begrænsninger står i *docs/STYREKANALER.md*.
  Prøv dem gerne først med *Skygge (vis kun)*
- **Ny styrekanal (eksperimentel):** Growatt SPF off-grid (fx SPF 5000 ES) via Solar Assistants MQTT. Enfaset, ingen nedtælling og intet
  salg – læs begrænsningerne i *docs/STYREKANALER.md*, før styringen slås til
- **Rettet (Growatt):** svarede inverteren langsomt, kunne en ladeordre, der lå i kø, blive sendt, efter at netladningen var stoppet
  (til næste minut). En ny ordre afbryder nu den gamle
- **Én genstart ved opdatering** (før to): når du har hentet en ny version i Markedspladsen, lægger Wattlas dens filer på plads
  med det samme og viser reparationen *Genstart for at fuldføre Wattlas* – typisk inden for et minut. Genstarter du, før den
  er kommet, sker det efter genstarten som før (to genstarter). Gælder fra næste opdatering efter denne
- **Rettet (Deye med ekstra inverter på GEN-porten):** produktionstællerne kunne få falske hop i langtidsstatistikken, når
  GEN-inverterens tæller kom senere end hovedinverterens efter en genstart. Wattlas' egen økonomi var ikke berørt
- Hvad-hvis-beregningens sensorer (`sensor.hh_…`) gemmes ikke længere i databasen. De forsvinder ved hver genstart, og deres
  efterladte langtidsstatistik gav advarslen *Forældreløse langtidsstatistikker* hos dem, der bruger Spook. Har du
  allerede advarslen, så vælg *Ryd disse statistikker* én gang
- **Sikkerhed – EMHASS API-nøglen er ikke længere en tilstand.** Til og med 0.4.1 lå den i `input_text.wattlas_emhass_noegle`. Feltet var
  skjult på skærmen, men alle med adgang til din Home Assistant (også skabeloner og API) kunne læse nøglen. Nu ligger den kun i
  integrationens opsætning sammen med EMHASS-adressen, og integrationen laver selv kaldene. Begge flyttes af sig selv ved opdateringen.
  **Lav gerne en ny nøgle bagefter:** skriv en ny kode i EMHASS-app'ens *emhass_api_token*, genstart app'en, og skriv samme kode under
  Wattlas → *Konfigurer* → Forbindelser og prognoser. Den gamle kan stadig ligge i Home Assistants backupper
- **Ændret:** `rest_command.emhass_…`, `input_text.wattlas_emhass_noegle` og `input_text.wattlas_emhass_adresse` findes ikke mere. Bruger du dem i egne automationer, så kald
  `wattlas.emhass` (*handling* og *data*) i stedet
- **Nyt logo:** en halv sol med et W over et batteri. Skærmbillederne i dokumentationen viser stadig det gamle
- **Rettet (alle invertere): startspærren kunne forhindre stop.** Forsvandt noget påkrævet (fx elprisen eller vejret), mens Wattlas
  netladede, stoppede reguleringen, og netladningen kunne hverken stoppes eller gives tilbage – heller ikke efter en genstart. Har
  Wattlas overtaget, giver den nu inverteren tilbage (selvforbrug) og genoptager selv, når alt er på plads igen
- Ingen andre ændringer i kernens styring

## 0.4.1
- **Konfigurer-knap:** under Indstillinger → Enheder og tjenester → Wattlas → *Konfigurer* kan du rette opsætningens tal
  (batteri, strømme i A, fasegrænse, importloft, priser) og forbindelser (EMHASS, solprognose, vejr). Felterne er udfyldt med de
  nuværende værdier, og ændringerne bruges med det samme
- **Ny styrekanal: to Deye i parallel** (eksperimentel) – master + slave med fælles batteri. Wattlas skriver kun til masteren (Deye kopierer selv til
  slaven) og halverer ladestrøm og effekt, så summen højst er det, planen beder om; nettet og faserne måles på masteren.
  Styringen stopper, hvis slaven ikke følger masteren
- **Skygge-tilstand:** *Skygge (vis kun)* i Wattlas Styring. Wattlas planlægger og regulerer som normalt og viser, hvad den
  ville sende til inverteren, men skriver intet – til nye anlæg, eksperimentelle styrekanaler eller ved siden af den
  styring, du bruger i dag. Slået fra (standard) ændrer den intet
- **Fremad** i appen: hvor længe batteriet rækker efter planen, og den billigste time fra nu af. Begge er også sensorer til
  egne automationer (`sensor.wattlas_batteri_raekker_til`, `sensor.wattlas_billigste_time`)
- **Ny styrekanal: SonnenBatterie** (eksperimentel, bidrag fra hornbech) – lokalt API v2 (fw 1.40+), ingen integration skal
  installeres: adresse og token indtastes i opsætningen. Netladning i de billige timer; solsalg og *gem batteriet* kan ikke
  styres via Sonnens API. Ladestrømmen holdes under det, husets værste fase har plads til (batteriet er enfaset)
- **Rettet (alle invertere):** svarede inverteren ikke, da styringen blev slået fra, glemte Wattlas, at den stadig skyldte at
  sætte den tilbage til selvforbrug. Nu prøver den igen hvert minut, til det lykkes, og fjerner du Wattlas imens, får du
  beskeden om at tjekke inverteren
- Ingen andre ændringer i styringen for de eksisterende kanaler

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
- **Beskeder til telefonen:** sæt modtageren i Wattlas Styring → Overvågning (*Send også til*: `notify.mobile_app_…` eller dit eget
  `script.…`). Før skulle man rette i en fil, som hver opdatering overskrev
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
