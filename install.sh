#!/bin/sh
# Wattlas – installationsscript til Home Assistant OS (app'en "Terminal & SSH").
#
#   sh install.sh deye                      Deye/Solarman-styrekanal
#   sh install.sh sunmate                   SunMate-styrekanal
#   sh install.sh deye --prefix mit_deye    inverterens entiteter starter med mit_deye_ i stedet for min_inverter_
#
# Valg: --kilde <mappe|fil.tar.gz> (installér fra en lokal kopi), --config <mappe> (standard /config).
# Miljø: WATTLAS_VERSION (standard v0.1.0-alpha).
#
# Scriptet kopierer kun filer. Det genstarter ikke HA, beder ikke om nøgler og rører ikke .storage.
# Det kan køres igen for at opdatere: gamle filer flyttes til /config/wattlas_backup_<tidspunkt>/,
# og dine indstillinger (hjælperne) bevares, fordi HA husker deres værdier.
set -eu

VERSION="${WATTLAS_VERSION:-v0.1.0-alpha}"
REPO="Vuzeoc/wattlas"
CONFIG="/config"
KANAL=""
PREFIX=""
KILDE=""

fejl() { echo "FEJL: $*" >&2; exit 1; }
brug() { sed -n '2,13p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    deye|sunmate) KANAL="$1" ;;
    --prefix) [ $# -ge 2 ] || brug; PREFIX="$2"; shift ;;
    --kilde) [ $# -ge 2 ] || brug; KILDE="$2"; shift ;;
    --config) [ $# -ge 2 ] || brug; CONFIG="$2"; shift ;;
    -h|--help) brug ;;
    *) echo "Ukendt valg: $1" >&2; brug ;;
  esac
  shift
done

case "$KANAL" in
  deye) KDIR=deye_solarman; STD=min_inverter ;;
  sunmate) KDIR=sunmate; STD=min_sunmate ;;
  *) echo "Vælg styrekanal: deye eller sunmate." >&2; brug ;;
esac
case "$PREFIX" in
  ""|*[!a-z0-9_]*) [ -z "$PREFIX" ] || fejl "--prefix må kun indeholde små bogstaver, tal og _ (fx mit_deye)." ;;
esac

CFG="$CONFIG/configuration.yaml"
[ -f "$CFG" ] || fejl "Fandt ikke $CFG. Kør scriptet i Terminal & SSH-app'en, eller angiv --config."

# --- packages-mappen læses fra configuration.yaml
REL=$(grep -E '^[[:space:]]*packages:[[:space:]]*!include_dir_(merge_)?named[[:space:]]+' "$CFG" | head -n 1 \
  | sed -E 's/.*!include_dir_(merge_)?named[[:space:]]+//; s/[[:space:]]+#.*$//; s/[[:space:]]*$//; s/^["'"'"']//; s/["'"'"']$//' || true)
if [ -z "$REL" ]; then
  cat >&2 <<EOF
FEJL: configuration.yaml bruger ikke packages endnu. Tilføj dette øverst i $CFG
(har du allerede en 'homeassistant:'-linje, så tilføj kun den indrykkede linje under den):

homeassistant:
  packages: !include_dir_named packages

Kør derefter scriptet igen.
EOF
  exit 1
fi
PKG="$CONFIG/$REL"
mkdir -p "$PKG"

# --- stop, hvis der allerede ligger en EMHASS/Wattlas-styring et andet sted (to styringer på én inverter er farligt)
ANDEN=$(find "$CONFIG" -name emhass_forbindelse.yaml ! -path "$PKG/wattlas/*" ! -path "$CONFIG/wattlas_backup_*" 2>/dev/null | head -n 1 || true)
[ -z "$ANDEN" ] || fejl "Der findes allerede en styring i $ANDEN. Fjern den først – to styringer må ikke køre samtidig."

# --- hent kilden
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if [ -n "$KILDE" ] && [ -d "$KILDE" ]; then
  SRC="$KILDE"
else
  ARKIV="$TMP/wattlas.tar.gz"
  if [ -n "$KILDE" ]; then
    [ -f "$KILDE" ] || fejl "Fandt ikke $KILDE."
    cp "$KILDE" "$ARKIV"
  else
    URL="https://github.com/$REPO/archive/refs/tags/$VERSION.tar.gz"
    echo "Henter $URL"
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$URL" -o "$ARKIV" || fejl "Kunne ikke hente $URL"
    else wget -q "$URL" -O "$ARKIV" || fejl "Kunne ikke hente $URL"; fi
  fi
  tar -xzf "$ARKIV" -C "$TMP" || fejl "Kunne ikke pakke arkivet ud."
  SRC=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)
fi
[ -f "$SRC/packages/wattlas/emhass_forbindelse.yaml" ] && [ -d "$SRC/styrekanaler/$KDIR" ] && [ -f "$SRC/dist/energi-app-card.js" ] \
  || fejl "$SRC ligner ikke en Wattlas-udgave."

# --- backup af en tidligere installation
STAMP=$(date +%Y%m%d-%H%M%S)
BK="$CONFIG/wattlas_backup_$STAMP"
flyt() { if [ -e "$1" ]; then mkdir -p "$BK"; mv "$1" "$BK/$2"; echo "Gammel version flyttet: $1 → $BK/$2"; fi; }
flyt "$PKG/wattlas" packages_wattlas
flyt "$PKG/wattlas_kanal" packages_wattlas_kanal
flyt "$CONFIG/www/wattlas" www_wattlas
flyt "$CONFIG/wattlas" wattlas

# --- kopiér
cp -R "$SRC/packages/wattlas" "$PKG/wattlas"
cp -R "$SRC/styrekanaler/$KDIR" "$PKG/wattlas_kanal"
if [ -n "$PREFIX" ] && [ "$PREFIX" != "$STD" ]; then
  for f in "$PKG"/wattlas_kanal/*.yaml; do sed -i "s/${STD}_/${PREFIX}_/g" "$f"; done
  echo "Styrekanalen bruger nu ${PREFIX}_… i stedet for ${STD}_…"
fi
mkdir -p "$CONFIG/www/wattlas" "$CONFIG/wattlas/dashboards"
cp "$SRC"/dist/* "$CONFIG/www/wattlas/"
cp "$SRC"/dashboards/*.yaml "$CONFIG/wattlas/dashboards/"

# --- dashboards og kort via en package (YAML-dashboards, kortet indlæses som frontend-modul)
cat > "$PKG/wattlas/wattlas_frontend.yaml" <<EOF
# Lavet af install.sh ($VERSION). Dashboards i YAML-tilstand – opdatér ved at køre install.sh igen.
lovelace:
  dashboards:
    wattlas-energi:
      mode: yaml
      title: Wattlas
      icon: mdi:solar-power-variant
      show_in_sidebar: true
      filename: wattlas/dashboards/wattlas.yaml
    wattlas-styring:
      mode: yaml
      title: Wattlas Styring
      icon: mdi:tune-variant
      show_in_sidebar: true
      filename: wattlas/dashboards/wattlas_styring.yaml
frontend:
  extra_module_url:
    - /local/wattlas/energi-app-card.js?v=$VERSION
EOF

echo
echo "Wattlas $VERSION er kopieret (styrekanal: $KANAL, packages: $PKG)."
if [ "$CONFIG" = /config ] && command -v ha >/dev/null 2>&1; then
  echo "Tjekker konfigurationen …"
  ha core check || echo "ADVARSEL: konfigurationstjekket fejlede – se fejlen ovenfor, før du genstarter."
fi
cat <<EOF

Næste skridt (se docs/INSTALLATION.md):
  1. Genstart Home Assistant (Indstillinger → System → Genstart).
  2. Udfyld Wattlas-indstillingerne (Indstillinger → Enheder og tjenester → Hjælpere, søg "Wattlas").
     Appen viser øverst, hvad der mangler. Styringen er spærret, til alt er sat.
EOF
[ "$KANAL" = deye ] && echo "  3. Deye: sæt de 6 tidsprogrammer til 01, 05, 09, 13, 17 og 21, og slå 'Time of use' til."
echo
echo "Har du tidligere oprettet dashboards eller kort-ressourcen i hånden, så slet dem, før du genstarter."
