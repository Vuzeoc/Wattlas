#!/bin/sh
# Wattlas – lægger integrationen i Home Assistant uden Markedspladsen (app'en "Terminal & SSH").
#
#   sh install.sh
#
# Scriptet kopierer kun mappen custom_components/wattlas. Genstart derefter Home Assistant, og tilføj
# integrationen: Indstillinger → Enheder og tjenester → Tilføj integration → Wattlas.
# Opsætningen dér vælger inverter (også en ekstra uden batteri), tjekker hvad der mangler og
# installerer resten. Kør scriptet igen for at opdatere til en nyere udgave.
#
# Valg: --kilde <mappe|fil.tar.gz> (installér fra en lokal kopi), --config <mappe> (standard /config).
# Miljø: WATTLAS_VERSION (et tag, fx v0.1.1-alpha). Uden den hentes nyeste udgave fra main.
set -eu

VERSION="${WATTLAS_VERSION:-}"
REPO="Vuzeoc/wattlas"
CONFIG="/config"
KILDE=""

fejl() { echo "FEJL: $*" >&2; exit 1; }
brug() { sed -n '2,12p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --kilde) [ $# -ge 2 ] || brug; KILDE="$2"; shift ;;
    --config) [ $# -ge 2 ] || brug; CONFIG="$2"; shift ;;
    deye|sunmate|--prefix|--inverter2*)
      fejl "Inverter, prefix og ekstra inverter vælges nu i opsætningen (Tilføj integration → Wattlas). Kør scriptet uden de valg." ;;
    -h|--help) brug ;;
    *) echo "Ukendt valg: $1" >&2; brug ;;
  esac
  shift
done

[ -f "$CONFIG/configuration.yaml" ] || fejl "Fandt ikke $CONFIG/configuration.yaml. Kør scriptet på Home Assistant."

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
    if [ -n "$VERSION" ]; then URL="https://github.com/$REPO/archive/refs/tags/$VERSION.tar.gz"
    else URL="https://github.com/$REPO/archive/refs/heads/main.tar.gz"; fi
    echo "Henter $URL"
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$URL" -o "$ARKIV" || fejl "Kunne ikke hente $URL"
    else wget -q "$URL" -O "$ARKIV" || fejl "Kunne ikke hente $URL"; fi
  fi
  tar -xzf "$ARKIV" -C "$TMP" || fejl "Kunne ikke pakke arkivet ud."
  SRC=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)
fi
[ -f "$SRC/custom_components/wattlas/manifest.json" ] && [ -f "$SRC/custom_components/wattlas/payload/packages/wattlas/emhass_forbindelse.yaml" ] \
  || fejl "$SRC ligner ikke en Wattlas-udgave."

# --- læg integrationen på plads (kun kode; dine indstillinger og Wattlas' filer i /config røres ikke her)
MAAL="$CONFIG/custom_components/wattlas"
mkdir -p "$CONFIG/custom_components"
rm -rf "$MAAL.ny"
cp -R "$SRC/custom_components/wattlas" "$MAAL.ny"
rm -rf "$MAAL"
mv "$MAAL.ny" "$MAAL"

NY=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$MAAL/manifest.json")
cat <<EOF

Wattlas-integrationen ($NY) ligger i $MAAL.

Næste trin:
  1. Genstart Home Assistant (Indstillinger → System → Genstart).
  2. Første gang: Indstillinger → Enheder og tjenester → Tilføj integration → Wattlas.
     Ved opdatering: Wattlas lægger selv de nye filer på plads og beder om én genstart mere under Reparationer.
EOF
