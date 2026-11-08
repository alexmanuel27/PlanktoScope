#!/bin/bash
# Pruebas de la app en el Mac, sin la Raspberry: RPi.GPIO y picamera2 falsos (cámara simulada con capas de foco).
# Copia Code/ a /tmp/ptest para no tocar config.json ni samples/ del repo.  Uso: pruebas/correr.sh [test_x.py ...]
REPO="$(cd "$(dirname "$0")/.." && pwd)"
P=/tmp/ptest
PY="${PY:-$HOME/miniforge3/envs/plankton-audit/bin/python}"
mkdir -p "$P"
rsync -a --delete --exclude 'planktoscope-env*/' --exclude samples/ --exclude __pycache__/ --exclude config.json \
      --exclude focus_state.json --exclude fondo.png "$REPO/Code/" "$P/Code/"
rsync -a --delete "$REPO/pruebas/RPi" "$REPO/pruebas/picamera2" "$P/"
cd "$REPO/pruebas"
TESTS=("$@"); [ ${#TESTS[@]} -eq 0 ] && TESTS=(test_*.py)
fallos=0
for t in "${TESTS[@]}"; do
  rm -f "$P/Code/config.json"; rm -rf "$P/Code/samples"
  if (cd "$P" && "$PY" "$REPO/pruebas/$t" > "$P/$t.log" 2>&1); then echo "OK    $t"; else echo "FALLO $t (ver $P/$t.log)"; fallos=$((fallos+1)); fi
done
exit $fallos
