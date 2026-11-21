# Sikkerhed

Wattlas skriver til en inverter, der er koblet til husets el og et batteri med meget energi. Fejl kan koste penge, slide
batteriet eller udløse sikringer. **Du har selv ansvaret** for din installation, dine indstillinger og at overholde
reglerne hos dit netselskab. Er du i tvivl om dine grænser, så spørg din elinstallatør.

## Hvad Wattlas gør for at være sikker

- **Startspærre:** intet skrives til inverteren og EMHASS kaldes ikke, før alle påkrævede indstillinger er sat
  (`binary_sensor.wattlas_konfigureret`).
- **Hårde grænser efter planen:** fasegrænse pr. fase, importloft, batteriets strøm- og effektgrænser og batterispænding
  45–58 V gælder altid, også ved tilsidesættelser og regler.
- **Plan-validering:** en plan bruges kun, hvis den er optimal, frisk, har rigtig længde og ligger inden for grænserne.
  Ellers bruges den gemte reserveplan (højst 2 timer gammel) eller selvforbrug.
- **Friske målinger:** målinger ældre end 90 sekunder eller uden for gyldigt område stopper styringen.
- **Fejl → selvforbrug:** mistes målinger, plan eller styrekanal, stoppes netladning, og inverteren sættes til selvforbrug.
  Der kommer en besked, og Wattlas prøver automatisk igen.
- **Få skrivninger:** der skrives kun, når en værdi faktisk ændres (afrundet), for at skåne inverterens hukommelse.
- **Tilsidesættelser udløber** altid (højst 24 timer).

## Hvad du selv skal sørge for

- Sæt grænserne efter din installation. Hent dem fra datablade og sikringer, ikke fra eksemplerne.
- Følg den første dag med styringen slået til, mens du er hjemme.
- Hold Home Assistant, EMHASS og inverter-integrationen opdateret, men læs ændringslogs før opdateringer.

## Fejl og sårbarheder

Opret et issue på GitHub. Skriv aldrig nøgler, adresser eller andre personlige oplysninger i issuet.
