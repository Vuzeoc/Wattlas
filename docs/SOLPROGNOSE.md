# Solprognose

Du kan bruge den solprognose, du vil. Wattlas er dog bygget og testet med **Helios Forecast**, og det er den, vi anbefaler.
Resten af Wattlas forventer det format, Helios leverer.

## Hvorfor Helios

- **Kvarterstal:** attributten `forecast` på `…_power_now` er en liste med en værdi pr. 15 minutter, i op til 7 dage.
  Wattlas lægger to kvarterer sammen til hver halve time i EMHASS-planen.
- **Lærer selv:** Helios sammenligner prognosen med det, anlægget faktisk producerer, og justerer sig efter det.
  Skygger, snavs og anlæggets egne tab kommer derfor med over tid.
- **Én sensor er nok:** Wattlas skal kun bruge én entitet. Appen henter dagens rest og morgendagen fra Helios'
  søstersensorer med samme navn.
- **Testet:** skift til vintertid, hvor Helios springer den gentagne nattetime over, håndteres i Wattlas.

## Sådan sætter du Helios op

1. HACS → søg **Helios Forecast** → installér → genstart HA.
2. Indstillinger → Enheder og tjenester → Tilføj integration → **Helios Forecast**. Følg guiden: placering, hældning,
   retning og anlæggets størrelse.
3. Vent, til `sensor.<navn>_power_now` har attributten `forecast` (Udviklerværktøjer → Tilstande).
4. Skriv entitets-ID'et i `input_text.wattlas_solprognose_entitet`, fx `sensor.mit_anlaeg_power_now`.

Prognosen er ret grov de første dage og bliver bedre, efterhånden som Helios har lært anlægget at kende.

Appen bruger også disse søstersensorer, hvis de findes. Styringen virker uden dem:

| Sensor | Bruges til | Mangler den |
|---|---|---|
| `sensor.<navn>_energy_today_remaining` | "Dagens prognose" (Sol-fanen og energiflowet) | prognosen viser kun det, der allerede er produceret |
| `sensor.<navn>_energy_day_2` | "Prognose i morgen", hvis prognoselisten ikke rækker | feltet er tomt |

## Solcast
Har du **Solcast PV Forecast** (HACS, BJReplay/ha-solcast-solar), så vælg dens *prognose i dag* i opsætningen (Forbindelser og prognoser).
Wattlas finder selv i morgen og dag 3 og deler Solcasts halve timer op i kvarterer. Planen bruger Solcasts mest sandsynlige tal (`pv_estimate`).
Vil du hellere regne med lidt mindre sol på usikre dage, så skru op for **Forsigtig solprognose** (Styring → Ferie og storm): 50 % ligger halvvejs
mod Solcasts forsigtige bud (`pv_estimate10`). På klare dage er buddene næsten ens, så det koster mest på dage, hvor Solcast er i tvivl.

## Skygger i solprognosen (prøvet og fravalgt)
Vi har bygget og testet en indlæring af skygger: Wattlas sammenlignede hver nat prognosen med den målte sol time for time over de sidste
21 dage og rettede planens prognose derefter. På et anlæg i oktober-november gav det kun ca. 2 % mindre fejl time for time og ca. 7 % pr.
døgn, så den er taget ud igen – den krævede mere vedligehold, end besparelsen var værd. Helios og Solcast regner prognosen godt nok, når de
har lært anlægget at kende og er sat korrekt op.

## Vil du bruge en anden prognose

Sensoren skal have præcis samme format som Helios, ellers laver Wattlas ingen plan:

```yaml
forecast:
  - datetime: "2026-06-01T12:00:00+02:00"   # ISO-tid med tidszone
    watts: 4200                              # forventet effekt i W
  - datetime: "2026-06-01T12:15:00+02:00"
    watts: 4350
```

- Der skal være **præcis to værdier pr. halve time** (kvarterstal). Mangler en halv time data, stopper beregningen med
  beskeden *"EMHASS – prognosedata mangler"*, og Wattlas kører videre på reserveplanen eller selvforbrug.
- Listen skal række mindst 2 timer frem. Planen bliver aldrig længere end prognosen.
- Har din prognose timetal eller halvtimetal (fx Forecast.Solar), skal du selv lave en template-sensor, der deler dem op i kvarterer.
  Solcast klarer Wattlas selv (se ovenfor).
- Har du flere tagflader som hver sin sensor, skal de lægges sammen til én sensor med samme format.
