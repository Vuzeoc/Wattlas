# Installation

Regn med ca. en time. Styringen kan ikke starte, før trin 6 er gjort færdigt. Den har en startspærre.

## 0. Krav

- Home Assistant 2026.11 (testet). Ældre versioner kan mangle `default_entity_id` i template-entiteter.
- En hybrid-inverter med batteri, som HA kan **både læse og skrive** (se [STYREKANALER.md](STYREKANALER.md)).
- Adgang til `/config` (fx app'en *File editor*, *Studio Code Server* eller *Terminal & SSH*).
- **Tag en backup af HA først** (Indstillinger → System → Sikkerhedskopier).

## 1. Integrationer og apps

| Hvad | Hvorfor | Hvor |
|---|---|---|
| **EMHASS** (app/add-on, version 0.18 eller nyere) | laver planen | Indstillinger → Apps → Butik → tilføj `https://github.com/davidusb-geek/emhass-add-on` |
| **Energi Data Service** (HACS) | spotpriser → `sensor.energi_data_service` | HACS → søg "Energi Data Service". Sæt pris **inkl. moms**, uden tariffer |
| **Workday** (indbygget) | hverdage/fridage i regler → `binary_sensor.workday_sensor` | Indstillinger → Enheder og tjenester → Tilføj → Workday, land Danmark |
| **SQL** (indbygget) | husprognose og historik fra HA's database | aktiveres automatisk af pakken |
| En **solprognose** med attributten `forecast` (liste af `{datetime, watts}`) | solen i planen | **Helios Forecast** (HACS) anbefales, Wattlas er bygget til den. Andre kræver samme format med kvarterstal, se [SOLPROGNOSE.md](SOLPROGNOSE.md) |
| En **vejr-entitet** (`weather.…`) med timeprognose | temperatur-justeret husforbrug | fx Met.no (indbygget) |
| En **udetemperatur-sensor** | samme | hvilken som helst `sensor.…` i °C |
| Inverterens integration | styrekanal | Deye: [ha-solarman](https://github.com/davidrapan/ha-solarman) (HACS). SunMate: SunMate-integrationen |

## 2. EMHASS-app

I EMHASS-app'ens indstillinger:

- Sæt en **API-nøgle** (`emhass_api_token` eller tilsvarende). Gem den. Du skal bruge den i trin 6.
- Slå **brug af batteri** til (`set_use_battery`).
- Sæt **antal fleksible forbrugere** (`number_of_deferrable_loads`) til 0. Wattlas sender selv sin fleksible forbruger med,
  når den er slået til. Afviser din EMHASS-version 0, så sæt 1 med effekt 0 W.
- Lad resten stå. Wattlas sender batteri, priser, prognoser og grænser med hvert kald.

Notér adressen: normalt `http://<din-HA-ip>:5000`. Tjek, at du kan åbne EMHASS' webside på den adresse.

## 3. Packages

Har du ikke packages i forvejen, så tilføj det i `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Kopiér derefter:

- `packages/wattlas/` → `/config/packages/wattlas/` (alle filer)
- **én** styrekanal-mappe, fx `styrekanaler/deye_solarman/` → `/config/packages/wattlas_kanal/`

> Brug aldrig to styrekanaler på én gang. Begge definerer de samme entiteter.

## 4. Styrekanalens navne

Styrekanalen forventer, at inverterens entiteter starter med `min_inverter_` (Deye) eller `min_sunmate_` (SunMate).
Du kan gøre det på én af to måder:

- **A (nemmest):** omdøb enheden i HA (Indstillinger → Enheder → inverteren → ✏️) til `min_inverter`, og sig **ja** til
  at omdøbe entitets-ID'erne.
- **B:** søg og erstat `min_inverter` med dit eget prefix i de to filer i `/config/packages/wattlas_kanal/`.

**Kun Deye:** Wattlas bruger Deyes 6 tidsprogrammer med faste skift kl. **01, 05, 09, 13, 17 og 21**. Sæt programtiderne i
inverteren (eller via Solarman) til de tider. Wattlas skriver kun SOC, effekt og netladning pr. program, ikke tiderne.
"Time of use" skal være slået til.

## 5. Genstart og kort

1. Indstillinger → System → Genstart (fuld genstart første gang, fordi SQL og nye helpers kræver det).
2. Kopiér `dist/` → `/config/www/wattlas/` (alle tre filer).
3. Indstillinger → Dashboards → ⋮ → Ressourcer → Tilføj: `/local/wattlas/energi-app-card.js?v=1`, type **JavaScript-modul**.
   (Planens-logik-kortet hentes automatisk fra samme mappe.)
4. Opret to dashboards med URL'erne `wattlas-energi` og `wattlas-styring` (navne: *Wattlas* og *Wattlas Styring*). Indsæt konfigurationen fra
   `dashboards/wattlas.yaml` og `dashboards/wattlas_styring.yaml` (⋮ → Rediger → ⋮ → Rå konfigurationseditor).

## 6. Indstillinger (påkrævet)

Øverst i Wattlas-appen står en gul linje med, hvad der mangler, så længe styringen er spærret
(attributten `mangler` på `binary_sensor.wattlas_konfigureret`). Alle tal er forklaret i
[KONFIGURATION.md](KONFIGURATION.md). Sæt dem under Indstillinger → Enheder og tjenester → Hjælpere (søg "Wattlas"):

- batteri, effekter og strømme (fra inverterens og batteriets datablad)
- sikringer: strøm pr. fase og importloft
- nettarif og afgifter (fra din netselskabs- og elregning)
- EMHASS-adresse og API-nøgle
- solprognose-, vejr- og temperatur-entitet

Når `binary_sensor.wattlas_konfigureret` er **on**, er spærren væk.

## 7. Beskeder

Åbn `script.wattlas_besked` (Indstillinger → Automationer → Scripts) og skift handlingen til din telefon,
fx `notify.mobile_app_din_telefon`. Som standard laver den en meddelelse i HA. Test med *EMHASS – testbesked*.

## 8. Første start

1. Kør *EMHASS – beregn og publicer Helios-plan* (`script.emhass_test_helios`) én gang manuelt. Tjek **Planens logik**:
   er tallene rimelige? Består de 7 tjek?
2. Slå `input_boolean.emhass_styring_aktiv` (**Wattlas styrer**) til **mens du er hjemme og kan se inverteren**.
3. Følg **Overvågning** den første dag. Slå styringen fra, hvis noget ser forkert ud. Wattlas går så tilbage til selvforbrug.

## Afinstallation

Slå styringen fra og vent 1 minut (selvforbrug sættes). Slet derefter mapperne fra trin 3 og 5 og genstart.
Tjek bagefter inverterens tidsprogrammer, og sæt dem som du vil have dem.
