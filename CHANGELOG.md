# Ændringer

Wattlas er i **alpha**: den kører dagligt hos udvikleren, men er ikke afprøvet i mange huse endnu.

## 0.8.0
- **Ny: Wattlas' lette hjerne – Wattlas uden EMHASS-app'en.** Ved opsætningen (og senere under *Konfigurer → Hjerne*) vælger du, hvad
  der laver planen: *EMHASS* som før, eller Wattlas' egen lille optimering. Den kræver ingen app og bruger under 0,1 MB hukommelse og ca.
  0,02 sekunder pr. plan, så den kører på små maskiner, hvor EMHASS kan vælte Home Assistant. Den tager præcis samme bestilling og laver
  planen i samme form, så kontrollen af planen, reguleringen, alle grænser, skygge, kortet og hvad-hvis er uændrede. Fleksible forbrugere
  og elbilen lægges i deres billigste tidsrum. Sammenlignet med EMHASS 0.19 på de samme prognoser over 12 novemberdøgn kostede den ca.
  0,4 kr. pr. døgn mere (152,8 mod 152,4 kr.). Ikke afprøvet med sommerens sol og salg endnu
- Indeholder alt fra 0.7.4 (ikke udgivet særskilt):

### 0.7.4
- **Varmt vand: boost.** Har din beholder eller varmepumpe ikke et mål, Wattlas kan hæve, kan Wattlas nu i stedet starte dens boost:
  tænde en kontakt, vælge et valg i en valgliste (fx *engangsopvarmning*) eller trykke på en knap. Kontakten slukkes og valglisten sættes
  tilbage, når timen ikke længere er billig (mindst 30 min), men kun hvis den stadig står, som Wattlas satte den. Er boosten allerede i gang,
  startes den ikke. Højst én opvarmning pr. 3 timer (en kontakt, Wattlas selv har slukket, tidligst igen efter 10 min), så en
  engangsopvarmning ikke startes igen og igen. En kontakt slukkes altid ved stop, også hvis den endnu ikke viser, at den er tændt
- **Varmt vand: forslag i feltet.** Beholder-feltet foreslår nu beholdere, kontakter og boost-valglister (du kan stadig skrive selv),
  og valglistens valg vælges fra listen og gemmes ordret (nogle varmepumper har usynlige tegn i teksten, og valg som "1.50" forbliver tekst). Ingen kendt opsætning ændres: en `water_heater` eller `number` virker som før

- **Små maskiner.** Opsætningen advarer, hvis maskinen har under ca. 3,5 GB RAM eller under 3 GB fri plads (EMHASS bruger ca. 0,5 GB
  og kan gøre Home Assistant ustabil). Mangler EMHASS-app'en, kan du nu fortsætte og skrive adressen på en EMHASS, der kører på en anden
  maskine. INSTALLATION.md beskriver kravene og EMHASS på en anden maskine

**Rettet efter en gennemgang af hele Wattlas:**
- **Elbil-lader, stop.**
  - Et nødstop (laderen adlød ikke grænsen) holder nu en halv times pause i stedet for at starte igen efter få minutter.
  - Et stop sender nu også den laveste strøm til ladere med kontakt/knap og 0 A til Easee, så en lader, der svarer OK uden at stoppe,
    ikke kører videre på fuld strøm.
  - Kommer en sænkning ikke igennem (fx et kort OCPP-udfald), sendes stop igen hvert 10. sekund, til det lykkes.
  - Et OCPP-stop uden kendt transaktion, mens laderen lader (fx efter en genstart af HA), regnes ikke længere som udført.
  - Genindlæses Wattlas, får en lader, der kun stoppes med 0 A, ikke længere fuld strøm. Den gives tilbage, når Wattlas fjernes.
- **Elbil-lader, i øvrigt.**
  - Et kort udfald nulstiller ikke længere bilens udgangspunkt.
  - En målt effekt med omvendt fortegn ligner ikke "står stille".
  - Et kort effekt-udfald giver ikke en halv times pause.
- **Deye, Deye-kloner og SunMate.**
  - Hver hurtig måling (fasernes strøm, net, husforbrug) skal nu være højst 90 s gammel, ikke kun den nyeste. Før kunne én fastfrossen
    strømtang sætte fasegrænsen ud af kraft.
  - Et negativt husforbrug i over 2 minutter (typisk en omvendt strømtang) afviser målingerne, også for Sonnen.
  - Dokumentationen siger nu, at Deye og SunMate ikke selv går tilbage, hvis Home Assistant går ned under netladning.
- **Tilbage til selvforbrug** (når målinger, plan eller kanal svigter).
  - Brugerens reserve holdes nu i stedet for altid 15 %, og stormens 80 %, mens Wattlas styrer (ikke efter tilbagelevering).
  - En utilgængelig programkontakt blokerer ikke længere.
  - Mangler den målte batterispænding, bruges planens grænse.
  - Solsalget slås til igen, når Wattlas giver inverteren tilbage, hvis Wattlas havde slået det fra ved negativ pris.
- **Opdatering og installation.**
  - Går selve konfigurationstjekket i stykker, rulles der nu tilbage alle steder (også ved opstart og i *Konfigurer*).
  - *Konfigurer* afviser at lægge filer, når en nyere version er hentet, men ikke indlæst.
  - En tilbagerulning skriver ikke `configuration.yaml` tilbage, hvis installationen ikke rettede den.
  - En BOM (usynligt tegn i begyndelsen af filen) og en absolut packages-sti håndteres.
  - En forberedt opdatering beder stadig om genstart efter *Genindlæs*.
  - Vagten mod anden styring blokerer ikke længere Home Assistant i op til et par sekunder hver time.
- **App og pakker.**
  - Ny, slettet og tændt/slukket regel bliver nu faktisk gemt, og en fejl ved gem vises.
  - Hvad-hvis' *Brug disse indstillinger* skriver kun de beregnede tal, og kun dem, der er ændret.
  - Den fleksible forbruger tændes ikke i skyggedrift, og feltet er låst, mens den kører.
  - Ugerapporten sendes også uden investering, og kortet viser "ikke sat" i stedet for "1 kr.".
  - *Sparet i år* er nu i år.
  - *Nu*-prisen og tariffen følger husets tidszone og kvarterpriser.
  - "Ingen hjemme" starter ikke forfra ved en genstart.
  - Fejlbanneret forsvinder, når hentningen lykkes.

## 0.7.3
- **Rettet: to genstarter ved opdatering.** Wattlas lægger en ny versions filer på plads, før Home Assistant genstarter, men først når
  filerne har ligget stille i 20 sekunder. Genstartede du hurtigere, skulle der genstartes én gang til. Nu sker det også, mens Home Assistant
  lukker ned, så én genstart er nok. Det virker fra opdateringen *efter* 0.7.3, fordi det er den kørende version, der gør det
- **Rettet: genstartknappen i Reparationer.** Blev genstarten afvist (fx *Another job is running* lige efter en opstart), forsvandt
  reparationen alligevel, og de nye filer blev aldrig indlæst. Nu bliver den stående og siger, at du skal prøve igen om et minut
- **Rettet: elbilens *Højeste strøm* og skønnene på fanen Elbil.** + kunne stadig trykkes over laderens grænse fra opsætningen (fx 32 A
  med en 16 A-lader), og tallet sprang først tilbage efter op til 10 sekunder. Nu stopper + ved grænsen, og den står under feltet. Skønnene
  (*starter ved … · fuld strøm ved …* og ladetiden) regnes nu med det samme ud fra ampere, i stedet for at vente på laderens næste melding
- **Rettet: inverter 2 stod som *Svarer ikke* på Teknik**, selv om den kørte. Valgte man Deyes egen måling af GEN-porten som effekt,
  ledte Teknik efter inverterens målinger under Deyes navn, hvor de ikke findes. Nu bruges hovedinverterens sensorer ikke til det, og under
  *Konfigurer → Inverter 2* kan du vælge en af inverterens **egne** sensorer (så viser Teknik dens strenge og forbindelse) og relæet.
  Finder Teknik slet ingen målinger, står der det i stedet for *Svarer ikke*
- **Tydeligere: solanlæggene ved Sol på Live.** Der står nu kolon efter navnet (*Inverter 2: 174 W*), så navn og tal ikke læses som ét tal

## 0.7.2
- **Elbil: *Kun sol* hedder nu *Solladning*, og du vælger selv blandingen.** Ny indstilling *Tilskud fra net/batteri* (W): så meget
  må bilen tage oven i solens overskud. 0 W er kun sol, som før. Med fx 3 kW starter en trefaset 11 kW-lader på 6 A allerede ved ca. 1,1 kW
  overskud i stedet for 4,1 kW. Appen viser, ved hvilket overskud den starter og når fuld strøm. *Kun fra elnettet* afgør, om tilskuddet
  kommer fra nettet alene eller også fra husbatteriet. **Er tilskuddet større end laderens laveste effekt, lader den også uden sol**, til den pris,
  strømmen har – vil du have de billige timer, så brug *Klar til tid*. Dér er solen stadig kun gratis overskud
- **Rettet: sol til en bil, der kun lader på én fase.** Solens overskud blev delt på laderens tre faser, så en enfaset bil fik en tredjedel af
  den sol, den kunne bruge. Nu regnes der efter den fase, bilen faktisk lader på, når ladningen er i gang (starten regner stadig forsigtigt med tre)

## 0.7.1
- **Rettet: elbilens højeste strøm i appen.** *Højeste strøm* på fanen Elbil kunne trykkes op til 32 A, selv om laderen er sat op til
  fx 16 A. Wattlas har hele tiden brugt den laveste af de to, men nu sættes tallet tilbage, så appen viser den grænse, der gælder
- **Tydeligere: *Fra* hedder nu *Slip laderen*** på fanen Elbil. Den stopper ikke en ladning, der er i gang – Wattlas holder bare op
  med at styre. Vil du stoppe, så vælg *Stop* (prøvet på en rigtig lader: strømmen var væk efter ca. 10 sekunder)
- **Rettet: falsk advarsel fra Spook** om ukendte entiteter i *Wattlas dagsplan* (EMHASS' lastsensorer findes kun, mens lasten er i planen)

## 0.7.0
- **Hvad-hvis: et andet batteri.** Skriv en anden batteristørrelse (0 = intet batteri) og se, hvad planen for de næste timer ville koste.
  Strømmen i batteriet nu og reserven regnes i kWh, så det større batteri ikke får gratis strøm. Batteriets pris er ikke med, og et døgn i
  november siger ikke meget om et helt år
- **Ny: plan mod virkelighed** (Solprognose, avanceret). Kl. 23:50 gemmes planen for næste døgn (`sensor.wattlas_dagsplan`). Dagen efter
  holdes den op mod de målte timer: sol, forbrug og regning, så du kan se, om det er prognosen eller styringen, der rammer ved siden af
- **Ny: varmt vand på billig strøm** (Styring, avanceret, slået fra som standard). Hæver en varmtvandsbeholders mål (`water_heater` eller
  `number`) med op til 10 °C i de billigste timer eller ved soloverskud, højst til beholderens maksimum. Dit eget mål sættes altid tilbage,
  også efter en genstart og når Wattlas fjernes
- **Ny: vagt mod anden styring.** Andre automationer og scripts, der rører de samme indstillinger i inverteren eller laderen som Wattlas,
  vises under Reparationer
- **Ny (eksperimentel): test dit system** (Overvågning, avanceret). Lader og aflader et par minutter gennem den almindelige tilsidesættelse og
  fortæller ud fra den målte batterieffekt, om inverteren gør, hvad Wattlas beder om. Kun når Wattlas styrer
- **Elbil: skøn over ladetiden.** I *Klar til tid* står der ved *Energi* (og ved *lad til*, når bilen er i Home Assistant), hvor længe det
  cirka tager ved laderens fulde strøm, fx *ca. 1 t 50 min ved 11,2 kW*. Skønnet følger med, mens du trykker kWh op og ned. Skrues
  strømmen ned for faserne eller husets forbrug, tager det længere
- **Prøvet og fravalgt: skygger i solprognosen.** Vi byggede og testede en funktion, der hver nat lærte, hvordan solprognosen rammer time
  for time (fx skygge fra træer ved lav sol), og rettede planens prognose derefter. På et anlæg i oktober-november gav det kun ca. 2 % mindre
  fejl time for time og ca. 7 % pr. døgn. Den er taget ud igen: den krævede mere vedligehold og gav ikke den ønskede besparelse. Helios og
  Solcast regner prognosen godt nok, når de har lært anlægget at kende og er sat korrekt op (se [SOLPROGNOSE.md](docs/SOLPROGNOSE.md))
- **Rettet: sommer- og vintertid i husprognosen.** Forbruget tages fra samme klokkeslæt de forrige døgn – før ramte den en time ved siden af
  i op til en uge efter et tidsskift (også i langtidsstatistikken efter en lang ferie). Plan mod virkelighed regner med rigtige tidspunkter,
  så døgn med 23 og 25 timer sammenlignes rigtigt

## 0.6.0
- **Ny: ferie.** Slå *Ferie* til (Styring → *Ferie og storm*) og skriv, hvornår I tager af sted og kommer hjem. I ferien regner planen kun med husets
  standby-forbrug, så den ikke køber strøm til en tom bolig, og fra hjemkomsten med det normale igen, så batteriet er klar. Bagefter tælles
  ferie-dagene ikke med i forbrugshistorikken (efter en lang ferie hentes dagene før ferien i langtidsstatistikken). Husets korttidshistorik rækker nu
  10 døgn tilbage (før 8)
- **Ny: når alle er væk et døgn** (personerne i Home Assistant) regnes der også med standby, til den første kommer hjem
- **Ny: stormvarsel.** Ved et orange eller rødt varsel om storm eller torden fra Meteoalarm (dækker DMI) eller vindstød over 25 m/s i vejrudsigten
  fylder planen batteriet i de billigste timer og tømmer det ikke under 80 %. Kan de billige timer ikke nå det, før stormen begynder, lades der fra
  nettet i god tid, og en tidsstyret *brug batteriet* springes over. En fundet storm holdes til sit slut (højst 3 døgn). Falder nettet ud, holder stormen ikke batteriet tilbage. Kan planen ikke regnes med
  stormen, regnes den med "hold niveauet" og ellers uden (med en besked)
- **Ny: forsigtig solprognose** med Solcast: regn med mindre sol, når Solcast er usikker (mod `pv_estimate10`)
- **Elbil:** *Klar til tid* lader også på gratis sol mellem de planlagte timer – det, huset ikke bruger, og som planen ikke lader husbatteriet med.
  To grænser – *Lad til* fra nettet og *Sol op til* på sol – og *100 % til næste tur*, der slår fra af sig selv, når bilen er fuld eller kobles fra.
  *Kun sol* er uændret
- **Ny: enkel eller avanceret visning.** Appen viser som standard kun det, de fleste bruger. Slå *Avanceret* til (Styring → Indstillinger) for regler,
  hvad-hvis, fleksibel forbruger, ferie og storm, batterislid og elbilens ekstra grænser. Det, der er slået til, vises og virker altid
- **Nye sensorer til egne automationer:** `sensor.wattlas_prisniveau` (billig, normal, dyr) og `binary_sensor.wattlas_problem`
- Alt nyt er slået fra, indtil du slår det til (undtagen solen i *Klar til tid*). Idéerne er inspireret af Energy Pilot (MIT)

## 0.5.1
- **Ny kontakt på fanen Elbil: *Kun fra elnettet*.** Så aflader husbatteriet ikke, mens bilen lader; bilen får strøm fra nettet (og solen), og batteriet må stadig
  lades. Det er den samme indstilling som *Elbil: hold batteriet* under Konfigurer, nu lige ved hånden. Vises ikke for SonnenBatterie, som ikke kan holdes

## 0.5.0
- **Ny, eksperimentel: styring af elbil-laderen.** Vælg din lader under Konfigurer, lad Wattlas prøve den af, og brug den nye fane *Elbil*: lad nu, klar til
  et klokkeslæt, kun sol, stop. Bilen behøver ikke være i Home Assistant. Se [docs/ELBIL.md](docs/ELBIL.md)
- Fuld strøm eller slet ikke; skrues kun ned for faserne og importloftet. Batteriets netladning viger for bilen
- Wattlas ser på, hvad laderen **måler**: stop sendes igen, hvis den ikke stopper, og den stoppes, hvis den trækker mere, end der er bedt om
- EMHASS planlægger bilen sammen med batteriet (som endnu en last). Har du ingen lader valgt, er planen uændret
- Ingen lader valgt = præcis som før
- **Afprøvet** på udviklerens egen 11 kW-lader over OCPP (start, op og ned i strøm, stop, start igen) og i en test-installation gennem Home Assistants
  OCPP-integration mod en falsk lader. Andre mærker kun i de automatiske tests. Se [docs/ELBIL.md](docs/ELBIL.md#hvad-er-afprøvet)
- **Ny: Nordpool og Solcast.** Vælg dem i opsætningen (Forbindelser og prognoser) i stedet for Energi Data Service og Helios. Wattlas omregner selv øre, MWh og moms og deler Solcasts halve timer op i kvarterer

## 0.4.5
- **Ny: to grænser pr. fase.** Sæt *hovedsikringen* (valgfri) under Konfigurer → *Elnet og sikringer*. Så er den eksisterende grænse kun den, der
  *reguleres* efter (fx 23 A), og først sikringen (fx 25 A) stopper noget og giver alarm. En fleksibel forbruger slukkes efter 1 minut over sikringen
  eller 10 minutter over reguleringsgrænsen. Ikke sat = præcis som før
- Alarmen *Høj netbelastning* bruger hovedsikringen, når den er sat. Teksten nævner ikke længere et fast tal

## 0.4.4
- **Ny: automatiske nettariffer.** Vælg dit netselskab (i opsætningen eller under Konfigurer → *Netselskab*), så henter Wattlas nettarif, elafgift og
  Energinets tariffer én gang om dagen, også når de skifter ved sommer, vinter og nytår. Du ser tallene, før de gemmes, og får besked, når de
  ændres. Det gælder husholdninger (*Nettarif C*); elselskabets tillæg og gebyrer taster du stadig selv. Slået fra, indtil du vælger
- Tal, der ikke ser rigtige ud (0, mangler, dobbelt eller andre tidsrum end Wattlas bruger), skrives aldrig: de gamle bliver stående, og du får en reparation
- Påmindelsen 1. januar, 1. april og 1. oktober kommer kun, hvis tarifferne ikke hentes selv
- Data: Energinet (www.energidataservice.dk), CC BY 4.0
- **Ny: hold batteriet, mens elbilen lader.** Vælg laderens effekt under Konfigurer → *Elbil-lader*, så aflader husbatteriet ikke, mens bilen lader (det må
  gerne lades). *Brug batteriet* vinder. Holdet slippes 5 min. efter, at bilen er færdig. Laderen læses kun. Slået fra, indtil du vælger; uden lader er
  reguleringen uændret
- **Husprognosen regner uden elbilen**, når laderen er valgt

## 0.4.3
- **Rettet: ingen plan på solrige dage.** EMHASS' standard tillader højst 9 kW salg og ingen nedregulering. Var der mere sol i overskud, kunne
  opgaven ikke løses, og batteriet fik ingen plan. Wattlas sender nu din grænse for salg og lader EMHASS regne med nedregulering
- **Rettet: planen brugte kun 90 % af batteriet**, medmindre du selv havde ændret EMHASS. Nu 100 %, eller det, du vælger i *Højeste batteriniveau*
  (Wattlas Styring → Styring). Vil du blive på 90 %, så sæt den dér
- **Rettet: en fleksibel forbruger kunne koste hele planen.** Kunne dens timer ikke nås før fristen, fandt EMHASS ingen løsning, og batteriet fik
  ingen plan. Timerne klippes nu til det, der kan nås, og kan opgaven alligevel ikke løses, regnes planen uden forbrugeren. Den tændes
  heller ikke længere på en gammel plan
- **Ny: fasevagt på den fleksible forbruger.** Den tændes kun, når faserne og importloftet har plads; batteriets netladning viger for den, og den
  slukkes, hvis en fase er overskredet i et minut. Så kan den også bruges til en **lader med tænd/sluk** – læs *docs/BRUG.md* først. Ikke
  prøvet på en rigtig lader. **Nyt felt: Faser** (står på 1, som holder mest plads fri – sæt 3 til en trefaset forbruger)
- **Ny: prisvagt.** Er tariffer, øre eller MWh slået til i Energi Data Service, blev tarifferne talt to gange. Opsætningen spærrer nu, og en
  kørende Wattlas viser en reparation
- **Ny: påmindelse om nettariffer** 1. januar, 1. april og 1. oktober
- **Ny: diagnostik-download** til fejlrapporter, uden adresser, nøgler, navne og dine egne entiteter
- **Besked, når startspærren falder**, mens Wattlas styrer. Et udfald af vejr, udetemperatur eller Workday sænker den ikke længere
- **Rettet:** med kvarterpriser fik planen en opdigtet halvtime til sidst. En fasesensor, der slet ikke findes, stopper ikke længere reguleringen med en fejl
- **Rettet:** Spook meldte *Ukendte entiteter* (`sensor.p_deferrable0`), når den fleksible forbruger ikke var i brug
- Reguleringen af batteriet er ellers uændret

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
