#!/usr/bin/env bash
# Deja UN solo entorno y UN solo arranque automático para la app. Se ejecuta EN LA RASPBERRY:
#   bash ~/PlanktoScope/sistema/arreglar_entorno.sh
# No necesita internet. Hace copia del venv y la restaura si algo falla.
set -euo pipefail
CODE=/home/alex/PlanktoScope/Code
VENV=$CODE/planktoscope-env
PY=$VENV/bin/python
SERVICIO=modular-planktoscope.service
DIR=$(cd "$(dirname "$0")" && pwd)

echo "== 1. El Python del sistema tiene lo que necesita la cámara y la web"
/usr/bin/python3 -c "import picamera2, libcamera, cv2, numpy, flask, RPi.GPIO; print('   sistema OK')" \
  || { echo "FALTA algo en el sistema (ver arriba). Instálalo con apt (python3-picamera2, python3-opencv, python3-flask) y vuelve a lanzar."; exit 1; }

echo "== 2. El venv tiene ai_edge_litert"
"$PY" -c "import ai_edge_litert" || { echo "El venv $VENV no tiene ai_edge_litert: no sigo."; exit 1; }

BAK="$VENV.bak-$(date +%Y%m%d-%H%M)"
echo "== 3. Copia de seguridad del venv en $BAK"
cp -a "$VENV" "$BAK"
restaurar() { echo "!! Falló: restauro el venv original"; rm -rf "$VENV"; mv "$BAK" "$VENV"; exit 1; }

echo "== 4. Venv con acceso a los paquetes del sistema"
sed -i 's/^include-system-site-packages *= *false/include-system-site-packages = true/' "$VENV/pyvenv.cfg"
grep include-system "$VENV/pyvenv.cfg"

echo "== 5. Quitar del venv lo que ya da el sistema (si no, tapa al del sistema y rompe la cámara)"
"$PY" -m pip uninstall -y picamera2 numpy opencv-python opencv-python-headless simplejpeg av pidng python-prctl 2>&1 | grep -v "not installed" || true

echo "== 6. Prueba completa con el intérprete del venv (incluye una inferencia real del modelo)"
cd "$CODE"
"$PY" - <<'PY' || restaurar
import picamera2, libcamera, cv2, numpy, flask, RPi.GPIO
from ai_edge_litert.interpreter import Interpreter
it = Interpreter("ml/plankton.tflite"); it.allocate_tensors()
i = it.get_input_details()[0]
it.set_tensor(i["index"], numpy.zeros(i["shape"], dtype=numpy.float32)); it.invoke()
print("   venv OK: picamera2", picamera2.__file__, "| numpy", numpy.__version__, "| cv2", cv2.__version__)
PY

echo "== 7. Buscar y desactivar otros arranques de app.py (todo reversible)"
pkill -f "python.*app.py" || true
if crontab -l 2>/dev/null | grep -q "app.py"; then
  crontab -l | sed '/app\.py/s/^\([^#]\)/# desactivado por arreglar_entorno.sh: \1/' | crontab -
  echo "   crontab: líneas con app.py comentadas"; fi
if [ -f /etc/rc.local ] && grep -q "app.py" /etc/rc.local; then
  sudo sed -i '/app\.py/s/^\([^#]\)/# \1/' /etc/rc.local; echo "   /etc/rc.local: línea comentada"; fi
for f in ~/.config/autostart/*.desktop; do
  if [ -f "$f" ] && grep -q "app.py" "$f"; then mv "$f" "$f.disabled"; echo "   autostart desactivado: $f"; fi
done
for u in $(systemctl --user list-unit-files 2>/dev/null | awk '/plankto/ {print $1}'); do
  systemctl --user disable --now "$u" || true; echo "   servicio de usuario desactivado: $u"
done

echo "== 8. Instalar y activar el servicio único"
sudo cp "$DIR/$SERVICIO" /etc/systemd/system/$SERVICIO
sudo systemctl daemon-reload
sudo systemctl enable --now $SERVICIO
sleep 15
systemctl is-active $SERVICIO
ps -o pid,args -C python3,python | grep app.py || true
curl -s -o /dev/null -w "   web: HTTP %{http_code}\n" http://localhost:5000/ || true
echo "LISTO. Si todo va bien, la copia $BAK se puede borrar más adelante."
