#!/usr/bin/env bash
# Diagnóstico del Modular PlanktoScope — se ejecuta EN LA RASPBERRY, como el usuario que corre la app.
#
#   bash estado_equipo.sh                 solo lectura: no toca GPIO, no graba, no reinicia nada
#   bash estado_equipo.sh --prueba-video  además, vía la API de la app: 1 vídeo de 5 s y 1 foto
#                                         (crea ficheros en samples/ y puede dejar la app colgada:
#                                          es justo lo que se quiere medir)
#
# Salida: ~/diagnostico-<host>-<fecha>/ y ~/diagnostico-<host>-<fecha>.tgz  (estado.txt + copia del código)
# Traer al Mac:  scp alex@192.168.4.1:~/diagnostico-*.tgz <repo>/diagnostico/
set -u

CODE_DIR="${CODE_DIR:-$HOME/PlanktoScope/Code}"
PORT="${PORT:-5000}"
SERVICIO="modular-planktoscope.service"
MD5_MODELO_PORTATIL="6596e444cb921de26ba7ed1a0e7d09c0"   # doctorado/Planktoscope/ml_plankton/plankton_mobilenet_v1.tflite (salida 19 clases)
PRUEBA_VIDEO=0; [ "${1:-}" = "--prueba-video" ] && PRUEBA_VIDEO=1

TS=$(date +%Y%m%dT%H%M%S)
OUT="$HOME/diagnostico-$(hostname)-$TS"
mkdir -p "$OUT"
exec > >(tee "$OUT/estado.txt") 2>&1

sec(){ printf '\n\n===== %s =====\n' "$*"; }
run(){ printf '\n$ %s\n' "$1"; timeout "${T:-30}" bash -c "$1" 2>&1 | head -n "${MAXL:-80}"; }

echo "Diagnóstico Modular PlanktoScope — $(date -Is) — usuario $(id -un) — prueba_video=$PRUEBA_VIDEO"
echo "OJO: la hora de arriba es la del sistema; comprobar contra un reloj real y anotarlo en ESTADO.md."

sec "1. Sistema"
run "cat /proc/device-tree/model; echo"
run "grep -E '^(PRETTY_NAME|VERSION_CODENAME)=' /etc/os-release; uname -a"
run "uptime; free -h; df -h / \"$HOME\""
run "timedatectl 2>/dev/null || date"
run "vcgencmd get_throttled; vcgencmd measure_temp; vcgencmd measure_volts core"
echo "  (get_throttled: 0x0 = nada; bit0 subtensión AHORA, bit16 subtensión desde el arranque, bit2/18 throttling)"
run "id"

sec "2. Cámara y paquetes del sistema"
T=20 run "rpicam-hello --list-cameras 2>&1 || libcamera-hello --list-cameras 2>&1"
MAXL=40 run "dpkg -l | awk '/^ii/ && \$2 ~ /picamera2|libcamera|rpicam|python3-opencv|python3-numpy|python3-flask|rpi-lgpio|python3-rpi|hostapd|dnsmasq|ffmpeg/ {print \$2, \$3}'"

sec "3. Intérpretes de Python y módulos"
cat > "$OUT/check_mods.py" <<'PY'
import importlib, sys
from importlib import metadata
dist = {"cv2": "opencv-python", "RPi.GPIO": "RPi.GPIO", "PIL": "Pillow", "ai_edge_litert": "ai-edge-litert",
        "tflite_runtime": "tflite-runtime", "flask": "Flask"}
print(sys.executable, sys.version.split()[0], "prefix=", sys.prefix)
for m in ["picamera2", "libcamera", "ai_edge_litert", "tflite_runtime", "cv2", "numpy", "flask", "RPi.GPIO", "lgpio", "PIL", "av"]:
    try:
        mod = importlib.import_module(m)
        v = getattr(mod, "__version__", None) or getattr(mod, "VERSION", None)
        if v is None:
            try: v = metadata.version(dist.get(m, m))
            except Exception: v = "?"
        print(f"  OK     {m:15s} {v}  {getattr(mod, '__file__', '')}")
    except Exception as e:
        print(f"  FALLA  {m:15s} {type(e).__name__}: {e}")
PY
PYS=("/usr/bin/python3")
while IFS= read -r cfg; do PYS+=("$(dirname "$cfg")/bin/python"); done < <(find "$HOME" -maxdepth 5 -name pyvenv.cfg 2>/dev/null)
for py in "${PYS[@]}"; do
  sec "3.x $py"
  [ -f "$(dirname "$(dirname "$py")")/pyvenv.cfg" ] && run "cat '$(dirname "$(dirname "$py")")/pyvenv.cfg'"
  T=60 run "'$py' '$OUT/check_mods.py'"
  [ "$py" != "/usr/bin/python3" ] && MAXL=200 run "'$py' -m pip freeze"
done

sec "4. picamera2: ¿stop_recording() para también la cámara? (código de la versión instalada)"
for py in "${PYS[@]}"; do
  if timeout 30 "$py" -c "import picamera2" 2>/dev/null; then
    run "'$py' -c 'import inspect, picamera2; from picamera2 import Picamera2 as P; print(picamera2.__file__); print(inspect.getsource(P.stop_recording)); print(inspect.getsource(P.start_recording))'"
    break
  fi
done

sec "5. Arranque automático"
run "systemctl cat $SERVICIO"
run "systemctl is-enabled $SERVICIO; systemctl is-active $SERVICIO"
run "systemctl --user cat $SERVICIO"
run "systemctl --user is-enabled $SERVICIO; systemctl --user is-active $SERVICIO"
run "loginctl show-user \"\$(id -un)\" -p Linger"
echo "  (servicio de usuario sin Linger=yes => no arranca hasta que alguien inicia sesión)"
run "systemctl list-unit-files | grep -i plankto; systemctl --user list-unit-files | grep -i plankto"
run "crontab -l; grep -v '^#' /etc/rc.local"
run "ps -eo pid,user,etime,args | grep '[a]pp.py'"
for pid in $(pgrep -f 'app.py'); do
  run "readlink /proc/$pid/exe; readlink /proc/$pid/cwd; tr '\0' '\n' < /proc/$pid/environ | grep -E '^(VIRTUAL_ENV|PATH|PYTHONPATH)='"
done
run "journalctl --list-boots --no-pager | tail -n 3"
MAXL=80 run "journalctl -b -u $SERVICIO --no-pager -n 60"
MAXL=80 run "journalctl --user -b -u $SERVICIO --no-pager -n 60"

sec "6. Red / punto de acceso"
run "ip -br addr; iw dev"
run "nmcli -t -f NAME,TYPE,DEVICE,AUTOCONNECT con show"
nmcli -t -f NAME,TYPE con show 2>/dev/null | awk -F: '$2 ~ /wireless/ {print $1}' | while IFS= read -r c; do
  run "nmcli -f 802-11-wireless.ssid,802-11-wireless.mode,802-11-wireless.band,802-11-wireless-security.key-mgmt,ipv4.method,ipv4.addresses con show '$c'"
done
for s in NetworkManager hostapd dnsmasq systemd-networkd; do printf '  %-18s enabled=%-10s active=%s\n' "$s" "$(systemctl is-enabled $s 2>&1)" "$(systemctl is-active $s 2>&1)"; done
run "ls /etc/systemd/network/ 2>/dev/null && cat /etc/systemd/network/*.network"
run "sed -E 's/^(wpa_passphrase=).*/\1***/' /etc/hostapd/hostapd.conf"

sec "7. Código desplegado ($CODE_DIR)"
run "ls -la '$CODE_DIR' '$CODE_DIR/ml' '$CODE_DIR/models'"
run "cd '$CODE_DIR' && wc -l app.py ml/*.py static/* templates/* && md5sum app.py ml/*.py ml/*.json static/* templates/*"
run "cd '$CODE_DIR' && git status -sb && git log -3 --oneline"
run "cd '$CODE_DIR' && grep -nE 'app\.run|water_quality|species_info|from ml|MODEL_PATH|Interpreter' app.py ml/*.py"
MAXL=60 run "cd '$CODE_DIR' && grep -n -A 25 -E '^ *LABELS *=' ml/*.py *.py"
run "cat '$CODE_DIR/config.json'; echo; cat '$CODE_DIR/focus_state.json'"
run "ls '$CODE_DIR/samples' | wc -l; du -sh '$CODE_DIR/samples'"
echo; echo "Modelos .tflite encontrados (md5 del modelo de 19 clases del portátil: $MD5_MODELO_PORTATIL):"
find "$HOME" -name '*.tflite' -not -path '*/site-packages/*' 2>/dev/null | while IFS= read -r f; do
  m=$(md5sum "$f" | cut -d' ' -f1); [ "$m" = "$MD5_MODELO_PORTATIL" ] && tag="== MODELO DEL PORTÁTIL (19 clases)" || tag="distinto"
  printf '  %s  %s  %s  %s\n' "$m" "$(stat -c '%y' "$f" | cut -d. -f1)" "$f" "$tag"
done

sec "8. Modelo: forma de entrada/salida y tiempo de inferencia"
cat > "$OUT/check_model.py" <<'PY'
import sys, time, glob, os
import numpy as np
try:
    from ai_edge_litert.interpreter import Interpreter; rt = "ai_edge_litert"
except Exception:
    from tflite_runtime.interpreter import Interpreter; rt = "tflite_runtime"
print("runtime:", rt)
for f in sys.argv[1:]:
    it = Interpreter(model_path=f); it.allocate_tensors()
    i = it.get_input_details()[0]; o = it.get_output_details()[0]
    print(f"{f}\n  entrada {list(i['shape'])} {i['dtype'].__name__}  salida {list(o['shape'])} {o['dtype'].__name__}")
    x = np.random.rand(*i["shape"]).astype(i["dtype"])
    it.set_tensor(i["index"], x); it.invoke()
    t = []
    for _ in range(10):
        t0 = time.perf_counter(); it.set_tensor(i["index"], x); it.invoke(); t.append(time.perf_counter() - t0)
    print(f"  inferencia (10 rep., 1 recorte): media {1000*np.mean(t):.0f} ms, máx {1000*np.max(t):.0f} ms")
PY
MODELOS=$(find "$HOME" -name '*.tflite' -not -path '*/site-packages/*' 2>/dev/null | tr '\n' ' ')
for py in "${PYS[@]}"; do
  if timeout 30 "$py" -c "import ai_edge_litert" 2>/dev/null || timeout 30 "$py" -c "import tflite_runtime" 2>/dev/null; then
    [ -n "$MODELOS" ] && T=120 run "'$py' '$OUT/check_model.py' $MODELOS"; break
  fi
done

sec "9. La app responde (HTTP en localhost:$PORT)"
for p in / /api/samples /api/config /api/focus/current; do
  printf '  %-22s ' "$p"; curl -s -o /dev/null -w '%{http_code}  %{time_total}s\n' --max-time 10 "http://localhost:$PORT$p" || echo "sin respuesta"
done
feed(){ curl -s --max-time 5 "http://localhost:$PORT/video_feed" | wc -c; }
echo "  /video_feed: $(feed) bytes en 5 s (0 = no hay imagen)"

if [ "$PRUEBA_VIDEO" = 1 ]; then
  sec "10. Prueba de congelamiento tras vídeo"
  echo "  video_feed antes:           $(feed) bytes/5 s"
  echo "  start: $(curl -s --max-time 10 "http://localhost:$PORT/api/capture/video/start")"
  sleep 5
  echo "  stop:  $(curl -s --max-time 10 "http://localhost:$PORT/api/capture/video/stop")"
  sleep 8
  echo "  video_feed después (8 s):   $(feed) bytes/5 s"
  printf '  foto después del vídeo:    '; curl -s -o /dev/null -w '%{http_code}  %{time_total}s\n' --max-time 30 "http://localhost:$PORT/api/capture/photo" || echo "sin respuesta en 30 s"
  echo "  /api/samples después:       $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://localhost:$PORT/api/samples")"
  run "ls -lt '$CODE_DIR/samples' | head -5"
  echo "  Si quedó colgada: systemctl --user restart $SERVICIO  (o systemctl restart, según el punto 5)"
fi

sec "11. Copia del código tal como está en la tarjeta"
RAIZ="$(dirname "$CODE_DIR")"
tar czf "$OUT/codigo_raspberry.tgz" -C "$(dirname "$RAIZ")" --exclude='*env*/lib' --exclude='*env*/bin' --exclude='*/samples' --exclude='__pycache__' "$(basename "$RAIZ")" 2>&1 | tail -3
cp -f "$HOME/.config/systemd/user/$SERVICIO" "$OUT/" 2>/dev/null; cp -f "/etc/systemd/system/$SERVICIO" "$OUT/${SERVICIO}.system" 2>/dev/null
ls -la "$OUT"
tar czf "$OUT.tgz" -C "$HOME" "$(basename "$OUT")"
echo; echo "LISTO: $OUT.tgz"
echo "En el Mac:  scp $(id -un)@<ip>:$OUT.tgz <repo>/diagnostico/"
