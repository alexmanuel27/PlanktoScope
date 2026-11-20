# app.py
from flask import Flask, render_template, jsonify, send_file, send_from_directory, Response, request
import time
import os
import subprocess
import threading
import json
from datetime import datetime
from queue import Queue, Empty
from collections import deque
from threading import Lock
import cv2
import numpy as np
import RPi.GPIO as GPIO
import math
import tempfile
import zipfile
import atexit
import shutil
import io
import csv

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

from ml.detector import detectar, detectar_objetos, corregir_fondo, medidas_objeto, limites_area  # solo necesita OpenCV: la detección funciona aunque falle el clasificador

# ========== Clasificador de plancton ==========
try:
    from ml.classifier import classify_image, META as CLASIFICADOR_META
    CLASSIFIER_AVAILABLE = True
    print("✅ Plankton classifier loaded")
except Exception as e:
    CLASSIFIER_AVAILABLE = False
    CLASIFICADOR_META = None
    print(f"❌ Classifier error: {e}")

app = Flask(__name__)
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
SESION_FILE = os.path.join(SAMPLES_DIR, "sesion_actual.json")  # sesión abierta (sobrevive a un reinicio)
SESIONES_CSV = os.path.join(SAMPLES_DIR, "sesiones.csv")       # mismas columnas que datos/sesiones.csv del repo
CAMPOS_SESION = ["sesion", "fecha", "origen", "especie_cultivo", "edad_cultivo_dias", "dilucion", "operador",
                 "fotos_desde", "fotos_hasta", "serie", "um_por_px", "particion", "notas"]
RECORTES_DIR = os.path.join(SAMPLES_DIR, "recortes")  # un PNG por objeto, de la foto completa (para el dataset)
FONDO_FILE = os.path.join(os.path.dirname(__file__), "fondo.png")  # foto en blanco (agua limpia) para el campo plano
FOCUS_STATE_JFILE = os.path.join(os.path.dirname(__file__), "focus_state.json")
COUNTER_FILE = os.path.join(SAMPLES_DIR, "counter.json")
os.makedirs(SAMPLES_DIR, exist_ok=True)

# ========== Variables globales ==========
last_annotated_frame = None
last_annotation_time = 0
last_classification = {"label": "unknown", "confidence": 0.0}
ignore_focus_limits = False
# Serie temporal en marcha (la lleva un hilo en la Raspberry: sigue aunque se cierre el navegador)
serie = {"activa": False, "parar": False, "n": 0, "intervalo": 0, "espera": 0, "inicio": 0.0, "estado": "",
         "filas": [], "fichero": None, "error": None}
# Memoria de la serie (como el segmentador del PlanktoScope, que necesita que la muestra cambie entre fotos):
# fondo = mediana de las últimas fotos; cajas = objetos de las últimas muestras, para reconocer lo que no se mueve
fondo_serie = deque(maxlen=10)
cajas_serie = deque(maxlen=3)
# Aviso de fin de serie con el LED parpadeando, hasta que alguien toque el equipo
parpadeo = {"activo": False, "hilo": None}

def should_clear_annotations():
    current_time = time.time()
    return current_time - last_annotation_time > 10.0

def annotate_frame(frame, classifications):
    for obj in classifications:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        label = obj["label"]
        confidence = obj["confidence"]
        color = (0, 0, 0)  # ✅ Siempre negro
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        label_text = f"{label} ({int(confidence)}%)" if confidence > 0 else "unknown"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        text_x = x + 5
        text_y = y - 10 if y - 10 > 10 else y + h + 20
        cv2.putText(frame, label_text, (text_x, text_y), font, font_scale, color, thickness)
    return frame

# ========== Cargar configuración ==========
def load_config():
    default_config = {
        "stepper1": {"dir_pin": 26, "step_pin": 19, "enable_pin": 13, "steps_take_sample": 2000, "delay": 0.002,
                     "ramp_steps": 200, "led_delay_after_pump": 1.0,
                     "pasos_por_ml": 0.0},   # 0 = bomba sin calibrar (Settings → Calibration)
        "stepper2": {"dir_pin": 5, "step_pin": 6, "enable_pin": 9, "steps_focus": 100, "delay": 0.003, "ramp_steps": 20,
                     "delay_start": 0.006, "focus_min": 40, "focus_max": 60},
        # um_por_px = 0: sin calibrar (se usan los límites de área por defecto del detector)
        # nitidez_min: recortes más borrosos no se clasifican (manchas, desenfocados).
        # confianza_min: por debajo, "desconocido"; 55 = umbral que conserva el 95 % de las clases conocidas
        #   (modelos/plankton_mobilenet_v1/calibracion_2026-11-01).
        # mostrar_especie: False = la foto y el conteo dicen "objeto"; la clase del modelo (19 géneros marinos, no
        #   validado en nuestras algas) queda solo en el CSV como clase_modelo/confianza_modelo.
        "camara": {"um_por_px": 0.0, "tamano_min_um": 3.0, "tamano_max_um": 300.0, "nitidez_min": 15.0, "confianza_min": 55.0,
                   "mostrar_especie": False,
                   # foto a más resolución tomada a la vez que la de 640×480 (mismo campo): de ella salen los recortes
                   # y la foto _full. [0, 0] = desactivada. 2028×1520 = sensor completo con binning 2×2
                   "foto_completa": [2028, 1520],
                   # en las series: fondo = mediana de las últimas fotos (mín. 5); un objeto en el mismo sitio en
                   # fijo_muestras de las 3 muestras anteriores es suciedad o algo pegado al capilar ("fijo")
                   "fijo_muestras": 2,
                   # grosor interior del capilar en µm (0 = sin dato): con um_por_px da el volumen de cada foto
                   "profundidad_um": 0.0}
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            for key in default_config:
                config[key] = {**default_config[key], **config.get(key, {})}  # rellena solo lo que falte
    else:
        config = default_config
        save_config(config)
    return config

def guardar_json(path, data):
    """Escritura atómica: o queda el fichero viejo entero o el nuevo entero, nunca uno a medias."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=4)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def save_config(config):
    guardar_json(CONFIG_FILE, config)

# ========== Cargar/guardar estado del foco ==========
def load_focus_state():
    try:
        with open(FOCUS_STATE_JFILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ focus_state.json no se pudo leer ({e}); el foco arranca en 100 y NO es su posición real")
        return {"step": 100}

def save_focus_state(state):
    guardar_json(FOCUS_STATE_JFILE, state)

# ========== Cargar/guardar contador ==========
def load_counter():
    default = {"photo": 0, "video": 0}
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return default

def save_counter(counter):
    guardar_json(COUNTER_FILE, counter)

# ========== Rutas y funciones ==========
@app.route("/")
def index():
    files = []
    for f in os.listdir(SAMPLES_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.mp4', '.txt', '.csv')):
            path = os.path.join(SAMPLES_DIR, f)
            files.append({
                "id": f,
                "time": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
                "type": "photo" if f.lower().endswith(('.jpg', '.jpeg')) else "video" if f.lower().endswith('.mp4') else "data"
            })
    files.sort(key=lambda x: x["time"], reverse=True)
    return render_template("index.html", initial_samples=files)

@app.route("/api/config", methods=["GET", "POST"])
def handle_config():
    global config
    if request.method == "POST":
        try:
            new_config = {**config, **request.json}  # conservar las secciones que la web no envía (camara)
            for key in ["stepper1", "stepper2"]:
                new_config[key] = {**config.get(key, {}), **new_config[key]}  # conservar lo que la web no envía (delay, rampa)
                new_config[key]["dir_pin"] = int(new_config[key]["dir_pin"])
                new_config[key]["step_pin"] = int(new_config[key]["step_pin"])
                new_config[key]["enable_pin"] = int(new_config[key]["enable_pin"])
                new_config[key]["steps_take_sample"] = int(new_config[key].get("steps_take_sample", 2000))
                new_config[key]["steps_focus"] = int(new_config[key].get("steps_focus", 100))
                new_config[key]["delay"] = float(new_config[key].get("delay", 0.0005))
                if key == "stepper2":
                    new_config[key]["focus_min"] = int(new_config[key].get("focus_min", 40))
                    new_config[key]["focus_max"] = int(new_config[key].get("focus_max", 60))
            save_config(new_config)
            config = new_config
            
            _motor_lock.acquire()  # esperar a que termine cualquier movimiento
            try:
                # sin GPIO.cleanup(): soltar los pines dejaría EN a GND y activaría los motores
            
                GPIO.setup(config["stepper1"]["dir_pin"], GPIO.OUT)
                GPIO.setup(config["stepper1"]["step_pin"], GPIO.OUT)
                GPIO.setup(config["stepper1"]["enable_pin"], GPIO.OUT)
                GPIO.output(config["stepper1"]["enable_pin"], GPIO.HIGH)
            
                GPIO.setup(config["stepper2"]["dir_pin"], GPIO.OUT)
                GPIO.setup(config["stepper2"]["step_pin"], GPIO.OUT)
                GPIO.setup(config["stepper2"]["enable_pin"], GPIO.OUT)
                GPIO.output(config["stepper2"]["enable_pin"], GPIO.HIGH)
            
                GPIO.setup(LED_PIN, GPIO.OUT)
                GPIO.output(LED_PIN, GPIO.HIGH if not led_state else GPIO.LOW)
            finally:
                _motor_lock.release()
            
            log_to_console("Configuration updated")
            return jsonify(status="ok")
        except Exception as e:
            return jsonify(error=str(e)), 400
    return jsonify(config)

def volumen_foto_ml():
    """Volumen de muestra que cubre una foto con todas sus capas: campo (640×480 px × µm/px) × grosor del capilar.
    None si falta alguna calibración. 1 mL = 1e12 µm³."""
    cam = config["camara"]
    um, prof = cam.get("um_por_px", 0.0), cam.get("profundidad_um", 0.0)
    return (640 * um) * (480 * um) * prof / 1e12 if um > 0 and prof > 0 else None

def volumen_bombeado_ml():
    ppm = config["stepper1"].get("pasos_por_ml", 0.0)
    return config["stepper1"]["steps_take_sample"] / ppm if ppm > 0 else None

@app.route("/api/calibration/pump", methods=["POST"])
def calibration_pump():
    """Calibración de la bomba: pasos dados (p. ej. 10 × Take Sample) y mL medidos en una probeta."""
    try:
        pasos, ml = float(request.json["pasos"]), float(request.json["ml"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Valores no válidos"), 400
    if not (pasos > 0 and ml > 0):
        return jsonify(error="Pasos y mL deben ser mayores que 0"), 400
    config["stepper1"]["pasos_por_ml"] = pasos / ml
    save_config(config)
    log_to_console(f"Bomba: {pasos / ml:.1f} pasos/mL ({volumen_bombeado_ml():.4f} mL por Take Sample)")
    return jsonify(status="ok", pasos_por_ml=pasos / ml, ml_por_muestra=volumen_bombeado_ml())

@app.route("/api/calibration/depth", methods=["POST"])
def calibration_depth():
    """Grosor interior del capilar plano, en µm (dato del fabricante o medido)."""
    try:
        um = float(request.json["profundidad_um"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Valor no válido"), 400
    if not 0 < um < 10000:
        return jsonify(error="Fuera de rango (0–10000 µm)"), 400
    config["camara"]["profundidad_um"] = um
    save_config(config)
    log_to_console(f"Capilar: {um:g} µm de grosor interior")
    return jsonify(status="ok", profundidad_um=um, volumen_foto_ml=volumen_foto_ml())

def sesion_activa():
    try:
        return json.load(open(SESION_FILE)) if os.path.exists(SESION_FILE) else None
    except Exception:
        return None

def cerrar_sesion():
    """Escribe la fila de la sesión abierta en samples/sesiones.csv (si hizo alguna foto) y la cierra."""
    s = sesion_activa()
    if not s:
        return None
    s["fotos_hasta"] = counter["photo"]
    if s["fotos_hasta"] >= s["fotos_desde"]:
        nuevo = not os.path.exists(SESIONES_CSV)
        with open(SESIONES_CSV, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS_SESION, extrasaction="ignore")
            if nuevo:
                w.writeheader()
            w.writerow({**s, "serie": " ".join(s.get("series", []))})
        log_to_console(f"Sesión {s['sesion']} cerrada: fotos {s['fotos_desde']}–{s['fotos_hasta']}")
    else:
        log_to_console(f"Sesión {s['sesion']} cerrada sin fotos: no se guarda")
    os.remove(SESION_FILE)
    return s

@app.route("/api/session", methods=["GET"])
def session_state():
    return jsonify(sesion=sesion_activa(), siguiente_foto=counter["photo"] + 1)

@app.route("/api/session/start", methods=["POST"])
def session_start():
    """Abre una sesión (protocolo del dataset: un cultivo o una muestra, un día). Cierra la anterior si quedó abierta."""
    global counter
    d = request.json or {}
    if not str(d.get("especie_cultivo", "")).strip():
        return jsonify(error="Indica la especie o cultivo (o 'lago' / 'mezcla')"), 400
    cerrar_sesion()
    counter["sesion"] = counter.get("sesion", 0) + 1
    save_counter(counter)
    s = {"sesion": f"S{counter['sesion']:03d}", "fecha": datetime.now().strftime("%Y-%m-%d"),
         "fotos_desde": counter["photo"] + 1, "um_por_px": config["camara"].get("um_por_px", 0.0), "particion": "",
         "series": [], **{k: str(d.get(k, "")).strip() for k in ("origen", "especie_cultivo", "edad_cultivo_dias",
                                                                  "dilucion", "operador", "notas")}}
    guardar_json(SESION_FILE, s)
    log_to_console(f"Sesión {s['sesion']} abierta: {s['especie_cultivo']} (desde la foto {s['fotos_desde']})")
    return jsonify(sesion=s)

@app.route("/api/session/end", methods=["POST"])
def session_end():
    s = cerrar_sesion()
    return jsonify(sesion=s) if s else (jsonify(error="No hay sesión abierta"), 400)

@app.route("/api/calibration", methods=["POST"])
def calibration():
    """µm por píxel de las fotos de la app (640×480), medido con un portaobjetos micrométrico desde el visor."""
    um = float(request.json["um_por_px"])
    if not 0 < um < 1000:
        return jsonify(error="Valor fuera de rango"), 400
    config["camara"]["um_por_px"] = um
    save_config(config)
    log_to_console(f"Calibración: {um:.4f} µm/px")
    return jsonify(status="ok", um_por_px=um)

@app.route("/api/focus/current")
def get_focus_current():
    return jsonify(step=focus_step)

@app.route("/api/focus/ignore", methods=["POST"])
def toggle_ignore_limits():
    global ignore_focus_limits
    data = request.get_json(silent=True) or {}
    ignore_focus_limits = bool(data["ignore"]) if "ignore" in data else not ignore_focus_limits
    log_to_console(f"Focus limits ignored: {ignore_focus_limits}")
    return jsonify(status="ok", ignore=ignore_focus_limits)

def led_hw(on, suave=False):
    """Enciende/apaga el LED (lógica invertida: LOW = encendido). suave=True sube en ~0,5 s con PWM
    para que el pico de corriente del encendido no llegue de golpe."""
    if on and suave:
        try:
            p = GPIO.PWM(LED_PIN, 200)
            p.start(100)                        # 100 % en alto = apagado
            for d in range(100, -1, -5):
                p.ChangeDutyCycle(d)
                time.sleep(0.025)
            p.stop()
            del p
        except Exception as e:
            log_to_console(f"LED soft-start error: {e}")
    GPIO.output(LED_PIN, GPIO.LOW if on else GPIO.HIGH)

@app.route("/api/time", methods=["POST"])
def sync_time():
    """La Raspberry no tiene internet ni reloj con pila: si su hora se desvía más de 1 min de la del
    navegador que se conecta, la corrige (el servicio corre como alex, que tiene sudo sin contraseña)."""
    try:
        t = float((request.get_json(silent=True) or {})["epoch"])
    except Exception:
        return jsonify(error="epoch requerido"), 400
    if t < 1.7e9:                                   # hora del navegador absurda (antes de 2023): no tocar
        return jsonify(error="hora del navegador no válida"), 400
    diff = t - time.time()
    if abs(diff) > 60:
        r = subprocess.run(["sudo", "-n", "date", "-s", f"@{int(t)}"], capture_output=True, text=True)
        if r.returncode != 0:
            log_to_console(f"No se pudo poner la hora: {r.stderr.strip()}")
            return jsonify(error="sudo date falló"), 500
        log_to_console(f"Hora corregida desde el navegador ({diff:+.0f} s)")
    return jsonify(status="ok", diff=round(diff))

@app.route("/api/state")
def get_state():
    """Lo que cada navegador debe mostrar al abrir la página, venga de donde venga."""
    return jsonify(focus_step=focus_step, led=led_state, ignore_focus_limits=ignore_focus_limits)

def hilo_parpadeo(rapido):
    # shortcut: encendido directo, sin la rampa PWM: con los motores parados el pico no molesta y crear un PWM
    # cada segundo durante horas es frágil en RPi.GPIO. Si el LED o la fuente lo notan, poner la rampa.
    encendido, apagado = (0.15, 0.15) if rapido else (0.5, 1.5)
    while parpadeo["activo"]:
        GPIO.output(LED_PIN, GPIO.LOW)
        time.sleep(encendido)
        GPIO.output(LED_PIN, GPIO.HIGH)
        time.sleep(apagado)

def iniciar_parpadeo(rapido=False):
    """Fin de serie: lento si terminó bien, rápido si se cortó por un error."""
    parar_parpadeo()
    parpadeo["activo"] = True
    parpadeo["hilo"] = threading.Thread(target=hilo_parpadeo, args=(rapido,), daemon=True)
    parpadeo["hilo"].start()
    log_to_console(f"LED parpadeando ({'error' if rapido else 'serie terminada'}): pulsa LED para apagarlo")

def parar_parpadeo():
    if parpadeo["activo"]:
        parpadeo["activo"] = False
        parpadeo["hilo"].join()
        GPIO.output(LED_PIN, GPIO.LOW if led_state else GPIO.HIGH)  # volver al estado real del LED

def poner_led(on):
    """Enciende (suave) o apaga el LED y deja led_state al día; no hace nada si ya está así."""
    global led_state
    parar_parpadeo()
    if led_state != on:
        led_state = on
        led_hw(on, suave=on)
        log_to_console(f"LED turned {'ON' if on else 'OFF'}")

@app.route("/api/disk")
def disk():
    """Ocupación de la tarjeta SD (el sistema de ficheros donde se guardan las muestras)."""
    u = shutil.disk_usage(SAMPLES_DIR)
    return jsonify(total=u.total, used=u.used, free=u.free)

@app.route("/api/led/toggle")
def toggle_led():
    global led_state
    if parpadeo["activo"]:          # pulsar LED con el aviso de fin de serie solo lo apaga
        parar_parpadeo()
        log_to_console("Aviso de fin de serie apagado")
        return jsonify(state=led_state, status="ON" if led_state else "OFF")
    led_state = not led_state
    led_hw(led_state, suave=True)
    status = "ON" if led_state else "OFF"
    log_to_console(f"LED turned {status}")
    return jsonify(state=led_state, status=status)

_motor_lock = Lock()  # un motor cada vez: no se cruzan pulsos ni se suman picos de corriente

def rampa(steps, t_min, t_start, ramp):
    """Semiperiodo de cada paso: arranca a t_start, crucero a t_min y frena simétrico."""
    ramp = min(ramp, steps // 2)
    t_start = max(t_start, t_min)  # la rampa nunca arranca más rápido que el crucero (barrido fino lento)
    for i in range(steps):
        k = min(i, steps - 1 - i, ramp)
        yield t_min if ramp == 0 else t_start - (t_start - t_min) * k / ramp

def move_stepper(stepper_key, direction, steps, delay=None, al_paso=None):
    c = config[stepper_key]
    with _motor_lock:
        GPIO.output(c["dir_pin"], GPIO.HIGH if direction == "forward" else GPIO.LOW)
        GPIO.output(c["enable_pin"], GPIO.LOW)
        time.sleep(0.01)
        try:
            for d in rampa(steps, delay or c["delay"], c.get("delay_start", 0.002), c.get("ramp_steps", 200)):
                GPIO.output(c["step_pin"], GPIO.HIGH)
                time.sleep(d)
                GPIO.output(c["step_pin"], GPIO.LOW)
                time.sleep(d)
                if al_paso:
                    al_paso()
        finally:
            GPIO.output(c["enable_pin"], GPIO.HIGH)  # desactivar siempre, aunque falle a mitad

@app.route("/api/focus/<direction>")
def focus(direction):
    global focus_step, ignore_focus_limits
    steps = config["stepper2"]["steps_focus"]
    
    if direction == "in":
        if not ignore_focus_limits and focus_step + steps > config["stepper2"]["focus_max"]:
            return jsonify(error=f"Focus limit exceeded (max: {config['stepper2']['focus_max']})"), 400
        move_stepper("stepper2", "forward", steps)
        focus_step += steps
        log_to_console(f"Focus IN: +{steps} steps (total: {focus_step})")
    elif direction == "out":
        if not ignore_focus_limits and focus_step - steps < config["stepper2"]["focus_min"]:
            return jsonify(error=f"Focus limit exceeded (min: {config['stepper2']['focus_min']})"), 400
        move_stepper("stepper2", "backward", steps)
        focus_step -= steps
        log_to_console(f"Focus OUT: -{steps} steps (total: {focus_step})")
    
    focus_state["step"] = focus_step
    save_focus_state(focus_state)
    return jsonify(step=focus_step)

@app.before_request
def bloquear_durante_serie():
    """Con una serie en marcha no se acepta nada que mueva motores, cambie el LED o capture: se cruzarían.
    Cualquiera de esas acciones (o empezar otra serie) apaga el aviso de fin de serie."""
    if parpadeo["activo"] and request.path.startswith(("/api/sample/take", "/api/focus/in", "/api/focus/out",
                                                         "/api/focus/auto", "/api/capture/", "/api/background",
                                                         "/api/series/start")):
        parar_parpadeo()
    if serie["activa"] and request.path.startswith(("/api/sample/take", "/api/focus/in", "/api/focus/out",
                                                     "/api/focus/auto", "/api/capture/", "/api/background", "/api/led/",
                                                     "/api/session/")):
        return jsonify(error="Serie temporal en marcha: espera a que termine o párala"), 409

def bombear():
    """Muestra nueva: gira la bomba con el LED apagado y lo reenciende suave."""
    steps = config["stepper1"]["steps_take_sample"]
    log_to_console(f"Moving stepper1 ({steps} steps)")
    if led_state:
        led_hw(False)                       # ahorrar: LED apagado mientras gira la bomba
    try:
        move_stepper("stepper1", "forward", steps)
    finally:
        if led_state:
            time.sleep(config["stepper1"].get("led_delay_after_pump", 1.0))
            led_hw(True, suave=True)

@app.route("/api/sample/take")
def take_sample():
    try:
        bombear()
        return jsonify(sample={"id": "sample_taken", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "type": "data"})
    except Exception as e:
        log_to_console(f"Sample error: {str(e)}")
        return jsonify(error="Sample failed"), 500

# ========== Cámara ==========
if CAMERA_AVAILABLE:
    @app.route("/video_feed")
    def video_feed():
        def generate_frames():
            while True:
                if should_clear_annotations():
                    global last_annotated_frame, last_annotation_time
                    last_annotated_frame = None
                    last_annotation_time = 0
                
                if last_annotated_frame is not None:
                    frame = last_annotated_frame
                else:
                    yuv_frame = camera.capture_buffer("lores")
                    yuv_array = np.frombuffer(yuv_frame, dtype=np.uint8)
                    yuv_reshaped = yuv_array.reshape((480 * 3 // 2, 640))
                    frame = cv2.cvtColor(yuv_reshaped, cv2.COLOR_YUV2BGR_I420)
                
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                time.sleep(0.05)
        return Response(generate_frames(),
                        mimetype='multipart/x-mixed-replace; boundary=frame')

    # ---------- Autofoco por software ----------
    # La cámara HQ (IMX477) no tiene autofoco: se mueve el motor de foco y se mide la nitidez de cada posición.
    MOSAICO = 4  # la imagen se parte en 4×4 zonas y cada zona busca su propio foco

    def nitidez():
        """Varianza del laplaciano por zona (4×4) de la luminancia del flujo lores reducida a 1/4; más alta = más enfocado.
        Reducida, el pico es más ancho y el ruido del sensor pesa menos. Por zonas, un objeto grande y muy contrastado
        no tapa a las algas pequeñas que están a otra profundidad (pasó en el equipo: partícula a −563, algas a −533)."""
        y = np.frombuffer(camera.capture_buffer("lores"), dtype=np.uint8)[:640 * 480].reshape(480, 640)
        lap = cv2.Laplacian(cv2.resize(y, (160, 120), interpolation=cv2.INTER_AREA), cv2.CV_64F)
        return lap.reshape(MOSAICO, 120 // MOSAICO, MOSAICO, 160 // MOSAICO).var(axis=(1, 3)).ravel()

    def curva(medidas, zonas=None):
        """[(nitidez, posición)] a partir de las medidas por zona: media de todas (zonas=None) o MEDIANA de las zonas
        de una capa, para que una zona con un objeto grande y contrastado en otro plano no arrastre el foco de la capa
        (en la simulación lo movía 12 pasos)."""
        return [(float(t.mean() if zonas is None else np.median(t[zonas])), p) for t, p in medidas]

    def ir_a_foco(paso):
        global focus_step
        d = paso - focus_step
        if d:
            move_stepper("stepper2", "forward" if d > 0 else "backward", abs(d))
            focus_step = paso

    def barrido_foco(desde, hasta, delay):
        """Sube de forma continua de desde a hasta midiendo la nitidez en cada fotograma; devuelve la posición más nítida.
        Siempre subiendo: la holgura del husillo queda siempre del mismo lado."""
        ir_a_foco(max(config["stepper2"]["focus_min"], desde - 20))  # llegar a 'desde' ya subiendo
        ir_a_foco(desde)
        def avanza():
            global focus_step
            focus_step += 1  # al día en cada paso: la medida usa la posición real y, si algo falla, la cuenta no se pierde
        motor = threading.Thread(target=move_stepper, args=("stepper2", "forward", hasta - desde, delay, avanza))
        motor.start()
        medidas = []
        while not medidas or motor.is_alive():  # al menos una medida, aunque el tramo sea corto
            # shortcut: posición de cuando se pide el fotograma; el que llega se expuso algo antes (en el barrido rápido,
            # unos pasos). Si el foco final queda corrido siempre hacia el mismo lado, usar SensorTimestamp
            p = focus_step
            medidas.append((nitidez(), p))
        motor.join()
        total = curva(medidas)
        n, mejor = max(total)
        log_to_console(f"AF {desde}..{hasta}: {len(medidas)} medidas, mejor {mejor} (nitidez {n:.1f}, fondo {mediana(total):.1f})")
        return medidas

    def pico(medidas):
        """Centro del pico: media de las posiciones por encima de media altura, pesada por la nitidez. Con la imagen a 1/4
        la cima es plana unos pasos y el máximo puro cae en cualquier punto de ella por el ruido."""
        fondo = mediana(medidas)
        corte = (max(medidas)[0] + fondo) / 2
        sobre = [(n - fondo, p) for n, p in medidas if n >= corte]
        return round(sum(w * p for w, p in sobre) / sum(w for w, _ in sobre))

    def mediana(medidas):
        return sorted(m for m, _ in medidas)[len(medidas) // 2]

    def picos_zona(pos, nit, factor, separacion):
        """Picos de la curva de una zona: superan factor × su fondo, son el máximo en ±separacion/2 y, si ya hay otro
        pico, entre los dos la curva baja al menos a mitad de altura (si no, es la ladera del otro, no otra capa)."""
        fondo, picos = np.median(nit), []
        for k in np.argsort(-nit):
            n, p = nit[k], pos[k]
            if n < factor * fondo:
                break
            if n < nit[np.abs(pos - p) <= separacion / 2].max():
                continue
            def valle(q):  # entre p y q la curva baja a menos de mitad de altura
                entre = nit[(pos > min(p, q)) & (pos < max(p, q))]
                return entre.size > 0 and entre.min() - fondo < (n - fondo) / 2
            if all(abs(p - q) >= separacion and valle(q) for q, _ in picos):
                picos.append((int(p), n))
        return [p for p, _ in picos]

    def buscar_capas(medidas, factor, separacion, maximo):
        """Cada zona vota por las posiciones donde está nítida (puede tener objetos a varias profundidades). Los votos a
        menos de 'separacion' pasos del primero del grupo forman una capa. Devuelve [(posición, zonas)], de la capa con
        más zonas a la de menos."""
        pos = np.array([p for _, p in medidas])
        nit = np.stack([t for t, _ in medidas])
        votos = sorted((p, z) for z in range(nit.shape[1]) for p in picos_zona(pos, nit[:, z], factor, separacion))
        grupos = []
        for p, z in votos:
            if grupos and p - grupos[-1][0][0] <= separacion:
                grupos[-1].append((p, z))
            else:
                grupos.append([(p, z)])
        capas = [(int(np.median([p for p, _ in g])), sorted(set(z for _, z in g))) for g in grupos]
        return sorted(capas, key=lambda c: -len(c[1]))[:maximo]

    def apilar(fotos):
        """Apilado de foco: donde hay algo nítido, cada píxel sale de la capa más nítida; en el fondo liso, media de las capas.
        Antes se elegía capa en todo el fondo y, como cada capa tiene distinto brillo, salían manchas grises (20/11)."""
        alto, ancho = fotos[0].shape[:2]
        ref = np.median(fotos[0].reshape(-1, 3), 0)
        fotos = np.stack([np.clip(f * (ref / np.maximum(np.median(f.reshape(-1, 3), 0), 1)), 0, 255)
                          for f in fotos]).astype(np.float32)          # mismo brillo de fondo en todas las capas
        # nitidez a escala 640×480 también para la foto grande, para que el mapa de capas no dependa de la resolución
        nit = np.stack([cv2.GaussianBlur(np.abs(cv2.Laplacian(cv2.cvtColor(cv2.resize(f, (640, 480), interpolation=cv2.INTER_AREA),
                                                                      cv2.COLOR_BGR2GRAY), cv2.CV_32F, ksize=3)), (0, 0), 4)
                        for f in fotos])
        mx = nit.max(0)
        peso = cv2.GaussianBlur(np.clip(mx / max(float(np.median(mx)), 1e-6) - 1.5, 0, 1), (0, 0), 3)  # 0 en fondo (≈ ruido), 1 con detalle
        capa = cv2.resize(nit.argmax(0).astype(np.uint8), (ancho, alto), interpolation=cv2.INTER_NEAREST).astype(np.intp)
        peso = cv2.resize(peso, (ancho, alto))[..., None]
        elegida = np.take_along_axis(fotos, capa[None, :, :, None], 0)[0]
        return (peso * elegida + (1 - peso) * fotos.mean(0)).astype(np.uint8)

    def mismo_lugar(a, b):
        """El centro de una caja cae dentro de la otra."""
        def dentro(o, caja):
            cx, cy = o["x"] + o["w"] / 2, o["y"] + o["h"] / 2
            return caja["x"] <= cx <= caja["x"] + caja["w"] and caja["y"] <= cy <= caja["y"] + caja["h"]
        return dentro(a, b) or dentro(b, a)

    def mismo_objeto(a, b):
        """Mismo objeto visto en dos capas."""
        return a["capa"] != b["capa"] and mismo_lugar(a, b)

    def sin_repetidas(capas, fotos, resultados):
        """Junta los objetos de todas las capas y, si un objeto sale en varias, se queda con la capa donde está más nítido.
        Dos objetos distintos en la misma x,y a distinta profundidad se cuentan como uno (raro con muestras diluidas)."""
        objetos = [{**o, "capa": capa} for capa, r in zip(capas, resultados)
                   for o in r.get("objects", []) if o["label"] != "descartado"]  # la nitidez viene de procesar_foto
        unicos = []
        for o in sorted(objetos, key=lambda o: -o["nitidez"]):
            if not any(mismo_objeto(o, u) for u in unicos):
                unicos.append(o)
        return objetos, unicos

    CAMPOS_TABLA = ["sesion", "capa", "recorte", "x", "y", "w", "h", "label", "confidence", "clase_modelo", "confianza_modelo", "nitidez", "area_px", "diametro_eq_px",
                    "eje_mayor_px", "eje_menor_px", "alargamiento", "circularidad", "solidez", "tono_media", "tono_std",
                    "saturacion_media", "saturacion_std", "brillo_media", "brillo_std",
                    "area_um2", "diametro_eq_um", "eje_mayor_um", "eje_menor_um"]

    def quitar_fijo_atrasado(foto, b):
        """Un objeto contado en una muestra anterior resulta estar pegado al capilar: se pasa a «fijo» en su fila de la
        serie y en su objetos_<foto>.csv. Solo llega a las últimas muestras que guarda cajas_serie (memoria acotada)."""
        clase, b["label"] = b["label"], "fijo"
        for fila in serie["filas"]:
            if fila["foto"] == foto:
                fila["objetos"] -= 1
                fila["fijos"] += 1
                fila["conteo"][clase] = fila["conteo"].get(clase, 1) - 1
                if fila["conteo"][clase] <= 0:
                    del fila["conteo"][clase]
        ruta = os.path.join(SAMPLES_DIR, f"objetos_{foto}.csv")
        if os.path.exists(ruta):
            with open(ruta, newline="") as f:
                filas = list(csv.DictReader(f))
            for r in filas:
                if [r["capa"], r["x"], r["y"], r["w"], r["h"]] == [str(b[k]) for k in ("capa", "x", "y", "w", "h")]:
                    r["label"] = "fijo"
            with open(ruta, "w", newline="") as f:
                w_csv = csv.DictWriter(f, fieldnames=CAMPOS_TABLA, extrasaction="ignore", restval="")
                w_csv.writeheader()
                w_csv.writerows(filas)
        log_to_console(f"Fijo también en la foto {foto} ({clase} en x={b['x']}, y={b['y']}): descontado")

    def guardar_tabla(numero, objetos):
        """objetos_<n>.csv: un objeto por fila con caja, clase y medidas (las de µm vacías si no hay calibración)."""
        nombre = f"objetos_{numero}.csv"
        with open(os.path.join(SAMPLES_DIR, nombre), "w", newline="") as f:
            w_csv = csv.DictWriter(f, fieldnames=CAMPOS_TABLA, extrasaction="ignore", restval="")
            w_csv.writeheader()
            w_csv.writerows(sorted(objetos, key=lambda o: (o.get("capa", 0), o["y"], o["x"])))
        return nombre

    def foto_lores():
        yuv = np.frombuffer(camera.capture_buffer("lores"), dtype=np.uint8).reshape((480 * 3 // 2, 640))
        return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)

    def foto_doble():
        """(640×480 BGR, foto completa BGR o None) del MISMO fotograma: la detección va en la pequeña y los recortes
        salen de la grande con las mismas cajas escaladas."""
        if not FOTO_COMPLETA:
            return foto_lores(), None
        req = camera.capture_request()
        try:
            yuv = np.frombuffer(req.make_buffer("lores"), dtype=np.uint8).reshape((480 * 3 // 2, 640))
            grande = req.make_array("main")     # RGB888 de picamera2 = orden B, G, R: listo para OpenCV
        finally:
            req.release()
        return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420), grande

    def guardar_recortes(grande, objetos, nombre_base):
        """Un PNG por objeto en samples/recortes/, de la foto completa, con un margen del 10 % (mín. 4 px de 640).
        Añade a cada objeto la columna 'recorte' del CSV."""
        os.makedirs(RECORTES_DIR, exist_ok=True)
        H, W = grande.shape[:2]
        esc = W / 640.0
        for i, o in enumerate(objetos):
            m = max(4, 0.1 * max(o["w"], o["h"]))
            x0, y0 = int(max(0, (o["x"] - m) * esc)), int(max(0, (o["y"] - m) * esc))
            x1, y1 = int(min(W, (o["x"] + o["w"] + m) * esc)), int(min(H, (o["y"] + o["h"] + m) * esc))
            o["recorte"] = f"recortes/{nombre_base}_{i}.png"
            cv2.imwrite(os.path.join(SAMPLES_DIR, o["recorte"]), grande[y0:y1, x0:x1])

    @app.route("/api/focus/auto")
    def autofocus():
        if not led_state:
            return jsonify(error="Enciende el LED antes del autofoco"), 400
        c = config["stepper2"]
        lo, hi = c["focus_min"], c["focus_max"]
        margen = c.get("af_margin", 60)
        log_to_console(f"Autofocus: barrido continuo {lo}..{hi}")
        medidas = barrido_foco(lo, hi, c["delay"])                    # rápido, todo el rango
        # la capa donde se enfoca la mayor parte de la imagen; si ninguna zona destaca, la nitidez global
        capas = buscar_capas(medidas, c.get("af_layer_factor", 2.0), c.get("af_layer_sep", 20), 1)
        centro, zonas = capas[0] if capas else (max(curva(medidas))[1], None)
        log_to_console(f"Autofocus: capa en {centro} ({len(zonas) if zonas else 'sin'} zonas de {MOSAICO * MOSAICO})")
        mejor = pico(curva(barrido_foco(max(lo, centro - margen), min(hi, centro + margen), c.get("af_delay_fine", 0.016)), zonas))  # lento
        ir_a_foco(max(lo, mejor - margen))  # volver subiendo, como en el barrido
        ir_a_foco(mejor)
        focus_state["step"] = focus_step
        save_focus_state(focus_state)
        log_to_console(f"Autofocus: listo en {focus_step}")
        return jsonify(step=focus_step)

    @app.route("/api/capture/layers")
    def capture_layers():
        r = capturar_capas()
        return jsonify(r), (400 if "error" in r else 200)

    def capturar_capas():
        """Una foto clasificada en cada capa de foco del capilar y, si hay más de una, la imagen apilada."""
        global counter
        if not led_state:
            return {"error": "Enciende el LED antes de capturar capas"}
        c = config["stepper2"]
        lo, hi = c["focus_min"], c["focus_max"]
        log_to_console(f"Capas: barrido continuo {lo}..{hi}")
        medidas = barrido_foco(lo, hi, c["delay"])
        w, fino, sep = c.get("af_layer_window", 25), c.get("af_delay_fine", 0.016), c.get("af_layer_sep", 20)
        candidatas = sorted(buscar_capas(medidas, c.get("af_layer_factor", 2.0), sep, c.get("af_layer_max", 6)))
        log_to_console("Capas candidatas: " + (", ".join(f"{p} ({len(z)} zonas)" for p, z in candidatas) or "ninguna"))
        capas = []
        for p, zonas in candidatas:
            p = pico(curva(barrido_foco(max(lo, p - w), min(hi, p + w), fino), zonas))  # afinar cada capa en lento, con sus zonas
            if all(abs(p - q) >= sep / 2 for q in capas):  # dos candidatas que afinan al mismo pico
                capas.append(p)
        capas.sort()
        log_to_console(f"Capas encontradas: {capas}")
        counter["photo"] += 1
        save_counter(counter)
        fotos, grandes, ficheros, resultados = [], [], [], []
        en_serie = serie["activa"]
        fondo = (np.median(np.stack(fondo_serie), axis=0).astype(np.uint8)
                 if en_serie and len(fondo_serie) >= 5 else None)   # sin bastantes fotos: foto en blanco o estimado
        for p in capas:                           # de abajo arriba: siempre llegando subiendo
            ir_a_foco(max(lo, p - w))
            ir_a_foco(p)
            time.sleep(0.3)
            camera.capture_buffer("lores")        # descartar un fotograma de antes de pararse
            pequena, grande = foto_doble()
            fotos.append(pequena)
            grandes.append(grande)
            resultados.append(procesar_foto(pequena, f"_capa{p}", counter["photo"], grande=grande, fondo=fondo))
            ficheros.append(resultados[-1].get("file"))
        objetos, unicos = sin_repetidas(capas, fotos, resultados)
        descartados = [{**o, "capa": capa} for capa, r in zip(capas, resultados)
                       for o in r.get("objects", []) if o["label"] == "descartado"]
        fijos = 0
        if en_serie:
            for o in unicos:
                if sum(any(mismo_lugar(o, b) for b in e["cajas"]) for e in cajas_serie) >= config["camara"].get("fijo_muestras", 2):
                    o["label"], fijos = "fijo", fijos + 1   # no se mueve al bombear: no es muestra nueva
                    for e in cajas_serie:                   # y en las muestras anteriores, donde aún se contó como objeto
                        for b in e["cajas"]:
                            if b["label"] not in ("fijo", "descartado") and mismo_lugar(o, b):
                                quitar_fijo_atrasado(e["foto"], b)
            cajas_serie.append({"foto": counter["photo"],
                                "cajas": [{k: o[k] for k in ("x", "y", "w", "h", "label", "capa")} for o in unicos]})
            fondo_serie.extend(fotos)
        ficheros.append(guardar_tabla(counter["photo"], unicos + descartados))  # descartados y fijos, para revisar
        nuevos = [o for o in unicos if o["label"] != "fijo"]
        conteo = {}
        for o in nuevos:
            conteo[o["label"]] = conteo.get(o["label"], 0) + 1
        log_to_console(f"Objetos: {len(objetos)} en las capas, {len(nuevos)} sin repetidas ({len(objetos) - len(unicos)} repetidas, "
                       f"{fijos} fijos, {len(descartados)} descartados por nitidez)" + (" · fondo: mediana de la serie" if fondo is not None else ""))
        log_to_console("Conteo sin repetidas: " + (", ".join(f"{k}: {v}" for k, v in conteo.items()) or "ninguno"))
        if len(fotos) > 1:
            grande = apilar(grandes) if all(g is not None for g in grandes) else None
            ficheros.append(procesar_foto(apilar(fotos), "_apilada", counter["photo"], grande=grande, recortes=False, fondo=fondo).get("file"))
        focus_state["step"] = focus_step
        save_focus_state(focus_state)
        return dict(capas=capas, files=ficheros, step=focus_step, objetos=len(objetos), unicos=len(nuevos), conteo=conteo,
                    foto=counter["photo"], descartados=len(descartados), fijos=fijos, volumen_ml=volumen_foto_ml())

    def guardar_serie():
        """serie_<n>.csv: una fila por muestra; se reescribe tras cada muestra para no perder nada si algo falla."""
        clases = sorted({k for f in serie["filas"] for k in f["conteo"]})
        campos = (["sesion", "muestra", "hora", "t_s", "retraso_s", "foto", "capas", "objetos", "descartados", "fijos",
                   "volumen_ml", "volumen_bombeado_ml", "total_por_ml"] + clases + [f"{c}_por_ml" for c in clases])
        with open(os.path.join(SAMPLES_DIR, serie["fichero"]), "w", newline="") as f:
            w_csv = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore", restval=0)
            w_csv.writeheader()
            for fila in serie["filas"]:
                v = fila.get("volumen_ml")
                conc = {f"{c}_por_ml": round(fila["conteo"].get(c, 0) / v, 1) for c in clases} if v else {}
                w_csv.writerow({**fila, **fila["conteo"], **conc, "capas": " ".join(map(str, fila["capas"])),
                                "sesion": serie.get("sesion", ""), "total_por_ml": round(fila["objetos"] / v, 1) if v else "",
                                "volumen_ml": f"{v:.3e}" if v else "", "volumen_bombeado_ml": fila.get("volumen_bombeado_ml") or ""})

    def hilo_serie():
        t0 = serie["inicio"]
        try:
            for i in range(serie["n"]):
                objetivo = t0 + i * serie["intervalo"]
                while time.time() < objetivo and not serie["parar"]:
                    serie["estado"] = f"esperando la muestra {i + 1}/{serie['n']}"
                    time.sleep(0.2)
                if serie["parar"]:
                    break
                inicio_muestra = time.time()
                poner_led(True)                 # en reposo está apagado; se enciende solo para la muestra
                serie["estado"] = f"muestra {i + 1}/{serie['n']}: bomba"
                log_to_console(f"Serie: muestra {i + 1}/{serie['n']}")
                bombear()
                time.sleep(serie["espera"])     # que la muestra se asiente antes de fotografiar
                serie["estado"] = f"muestra {i + 1}/{serie['n']}: capas"
                r = capturar_capas()
                if "error" in r:
                    raise RuntimeError(r["error"])
                serie["filas"].append({"muestra": i + 1, "hora": datetime.fromtimestamp(inicio_muestra).strftime("%Y-%m-%d %H:%M:%S"),
                                       "t_s": round(inicio_muestra - t0, 1), "retraso_s": round(inicio_muestra - objetivo, 1),
                                       "foto": r["foto"], "capas": r["capas"], "objetos": r["unicos"],
                                       "descartados": r["descartados"], "fijos": r["fijos"], "conteo": r["conteo"],
                                       "volumen_ml": r["volumen_ml"], "volumen_bombeado_ml": volumen_bombeado_ml()})
                guardar_serie()
                poner_led(False)
        except Exception as e:
            serie["error"] = str(e)
            log_to_console(f"Serie interrumpida: {e}")
        finally:
            poner_led(False)
            serie["activa"] = False
            serie["estado"] = "parada" if serie["parar"] else ("error" if serie["error"] else "terminada")
            log_to_console(f"Serie {serie['estado']}: {len(serie['filas'])} muestras en {serie['fichero']}")
            if not serie["parar"]:          # si la paró alguien, ya está delante del equipo
                iniciar_parpadeo(rapido=bool(serie["error"]))

    @app.route("/api/series/start", methods=["POST"])
    def series_start():
        global counter
        if serie["activa"]:
            return jsonify(error="Ya hay una serie en marcha"), 409
        d = request.json or {}
        try:
            intervalo, espera, valor = float(d["intervalo"]), float(d.get("espera", 5)), float(d["valor"])
        except (KeyError, TypeError, ValueError):
            return jsonify(error="Valores no válidos"), 400
        n = int(valor) if d.get("modo") == "muestras" else math.ceil(valor / intervalo) if intervalo > 0 else 0
        if not (intervalo > 0 and 0 <= espera <= 300 and 1 <= n <= 1000):
            return jsonify(error="Revisa los valores: intervalo > 0, espera 0–300 s, entre 1 y 1000 muestras"), 400
        counter["serie"] = counter.get("serie", 0) + 1
        save_counter(counter)
        fondo_serie.clear(); cajas_serie.clear()
        vf, vb = volumen_foto_ml(), volumen_bombeado_ml()
        if vf and vb and vb < vf:
            log_to_console(f"Aviso: cada muestra bombea {vb:.2e} mL y cada foto cubre {vf:.2e} mL: las muestras se solapan")
        serie.update(activa=True, parar=False, n=n, intervalo=intervalo, espera=espera, inicio=time.time(),
                     estado="empezando", filas=[], fichero=f"serie_{counter['serie']}.csv", error=None)
        ses = sesion_activa()
        if ses:
            ses.setdefault("series", []).append(serie["fichero"])
            guardar_json(SESION_FILE, ses)
        serie["sesion"] = (ses or {}).get("sesion", "")
        log_to_console(f"Serie {counter['serie']}: {n} muestras cada {intervalo:g} s (espera tras bombear {espera:g} s)")
        poner_led(True)
        threading.Thread(target=hilo_serie, daemon=True).start()
        return jsonify(status="ok", n=n, fichero=serie["fichero"])

    @app.route("/api/series/stop", methods=["POST"])
    def series_stop():
        serie["parar"] = True
        log_to_console("Serie: se para al terminar la muestra en curso")
        return jsonify(status="ok")

    @app.route("/api/series/state")
    def series_state():
        siguiente = serie["inicio"] + len(serie["filas"]) * serie["intervalo"] - time.time() if serie["activa"] else None
        estado = {k: serie[k] for k in ("activa", "n", "intervalo", "espera", "estado", "filas", "fichero", "error")}
        return jsonify({**estado, "led": led_state, "parpadeo": parpadeo["activo"], "siguiente_s": None if siguiente is None else max(0.0, round(siguiente, 1))})

    @app.route("/api/capture/photo")
    def capture_photo():
        r = procesar_foto()
        if "error" not in r:
            r["table"] = guardar_tabla(counter["photo"], r["objects"])
        return jsonify(r), (500 if "error" in r else 200)

    @app.route("/api/background", methods=["POST", "DELETE"])
    def background():
        """POST: guarda como fondo la mediana de 10 fotogramas con el capilar lleno de agua limpia. DELETE: lo borra
        (se vuelve a estimar el fondo de cada foto)."""
        global fondo_blanco
        if request.method == "DELETE":
            fondo_blanco = None
            if os.path.exists(FONDO_FILE):
                os.remove(FONDO_FILE)
            log_to_console("Fondo borrado: se estima en cada foto")
            return jsonify(status="ok", background=False)
        if not led_state:
            return jsonify(error="Enciende el LED antes de tomar el fondo"), 400
        fondo_blanco = np.median(np.stack([foto_lores() for _ in range(10)]), axis=0).astype(np.uint8)
        cv2.imwrite(FONDO_FILE, fondo_blanco)
        log_to_console("Fondo guardado (mediana de 10 fotogramas)")
        return jsonify(status="ok", background=True)

    def procesar_foto(bgr_frame=None, sufijo="", numero=None, grande=None, recortes=True, fondo=None):
        """Guarda la foto, detecta y clasifica los objetos y guarda la anotada (+ _raw). Sin bgr_frame, la toma ahora."""
        global counter, last_annotated_frame, last_annotation_time
        if numero is None:
            counter["photo"] += 1
            save_counter(counter)
            numero = counter["photo"]
        img_filename = f"photo_{numero}{sufijo}.jpg"
        img_path = os.path.join(SAMPLES_DIR, img_filename)
        
        try:
            if bgr_frame is None:
                bgr_frame, grande = foto_doble()
            
            cv2.imwrite(img_path, bgr_frame)
            log_to_console(f"Image captured: {img_filename}")
            
            classifications = []
            cam = config["camara"]
            corregida = corregir_fondo(bgr_frame, fondo if fondo is not None else fondo_blanco)  # detección y medidas sobre la imagen con campo plano
            limites = limites_area(cam["um_por_px"], cam["tamano_min_um"], cam["tamano_max_um"], *bgr_frame.shape[:2])
            gris = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
            sesion_id = (sesion_activa() or {}).get("sesion", "")
            for (x, y, w, h), contorno in detectar_objetos(corregida, *limites):   # ml/detector.py
                medidas = medidas_objeto(corregida, contorno, cam["um_por_px"])
                nitidez = round(float(cv2.Laplacian(gris[y:y+h, x:x+w], cv2.CV_64F).var()), 3)
                if nitidez < cam["nitidez_min"]:  # mancha o desenfocado: no se clasifica, pero queda en la tabla
                    classifications.append({"x": x, "y": y, "w": w, "h": h, "label": "descartado", "confidence": 0.0,
                                            "nitidez": nitidez, "sesion": sesion_id, **medidas})
                    continue
                obj_img = bgr_frame[y:y+h, x:x+w]
                if CLASIFICADOR_META and grande is not None:   # los modelos nuevos se entrenan con recortes de la foto completa
                    e = grande.shape[1] / bgr_frame.shape[1]
                    obj_img = grande[int(y * e):int((y + h) * e), int(x * e):int((x + w) * e)]
                obj_path = os.path.join(SAMPLES_DIR, f"temp_obj_{numero}{sufijo}_{len(classifications)}.jpg")
                cv2.imwrite(obj_path, obj_img)
                
                result = {"label": "unknown", "confidence": 0.0}
                if CLASSIFIER_AVAILABLE:
                    try:
                        result = classify_image(obj_path)
                        log_to_console(f"Object classification (modelo, experimental): {result['label']} ({result['confidence']:.1f}%)")
                    except Exception as e:
                        log_to_console(f"Classification error: {e}")
                        result = {"label": "error", "confidence": 0.0}
                modelo = dict(result)
                if result["label"] not in ("unknown", "error") and result["confidence"] < cam["confianza_min"]:
                    result = {"label": "desconocido", "confidence": result["confidence"]}
                if not cam.get("mostrar_especie", False):
                    result = {"label": "objeto", "confidence": 0.0}
                
                classifications.append({
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "label": result["label"],
                    "confidence": result["confidence"],
                    "clase_modelo": modelo["label"], "confianza_modelo": modelo["confidence"],
                    "sesion": sesion_id,
                    "nitidez": nitidez,
                    **medidas
                })
                os.remove(obj_path)
            
            validos = [o for o in classifications if o["label"] != "descartado"]
            if len(validos) < len(classifications):
                log_to_console(f"Descartados por nitidez < {cam['nitidez_min']}: {len(classifications) - len(validos)}")
            # Generar resumen
            class_count = {}
            for obj in validos:
                label = obj["label"]
                class_count[label] = class_count.get(label, 0) + 1
            
            if class_count:
                class_list = ", ".join([f"{k}: {v}" for k, v in class_count.items()])
                log_to_console(f"Classification summary: {class_list}")
            else:
                class_list = "No objects classified"
                log_to_console(class_list)
            
            # Dibujar anotaciones (siempre en negro)
            annotated_frame = bgr_frame.copy()
            for obj in validos:
                x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
                label = obj["label"]
                confidence = obj["confidence"]
                color = (0, 0, 0)  # Negro
                cv2.rectangle(annotated_frame, (x, y), (x+w, y+h), color, 2)
                label_text = f"{label} ({int(confidence)}%)" if confidence > 0 else label
                if "diametro_eq_um" in obj:
                    label_text += f" {obj['diametro_eq_um']:.0f} um"
                cv2.putText(annotated_frame, label_text, (x+5, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            last_annotated_frame = annotated_frame
            last_annotation_time = time.time()
            
            # Guardar la anotada y renombrar la cruda con el mismo nombre + _raw
            if validos:
                first_class = validos[0]["label"]
                stem = f"plankton_{first_class}_{numero}{sufijo}"  # el número evita sobrescribir
                annotated_filename = f"{stem}.jpg"
                annotated_path = os.path.join(SAMPLES_DIR, annotated_filename)
                cv2.imwrite(annotated_path, annotated_frame)
                os.replace(img_path, os.path.join(SAMPLES_DIR, f"{stem}_raw.jpg"))  # la cruda pasa a llamarse como la clasificada
                log_to_console(f"Annotated image saved: {annotated_filename} (+ {stem}_raw.jpg)")
                final_filename = annotated_filename
            else:
                stem = f"photo_{numero}{sufijo}"
                final_filename = img_filename
            if grande is not None:
                cv2.imwrite(os.path.join(SAMPLES_DIR, f"{stem}_full.jpg"), grande, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if recortes and classifications:
                    guardar_recortes(grande, classifications, f"{numero}{sufijo}")
            
            return {
                "status": "ok",
                "file": final_filename,
                "class": "multiple",
                "confidence": 0.0,
                "objects": classifications,
                "summary": class_list
            }
            
        except Exception as e:
            log_to_console(f"Photo capture error: {e}")
            return {"error": "Capture failed"}

    @app.route("/api/capture/video/<action>")
    def capture_video(action):
        global recording, video_encoder, video_output
        if action == "start" and not recording:
            global counter
            counter["video"] += 1
            save_counter(counter)
            filename = f"video_{counter['video']}.h264"
            path = os.path.join(SAMPLES_DIR, filename)
            video_encoder = H264Encoder(5000000)
            video_output = FileOutput(path)
            camera.start_recording(video_encoder, video_output, name="lores")
            recording = True
            app.h264_path = path
            app.mp4_path = path.replace(".h264", ".mp4")
            log_to_console(f"Video started: {filename}")
            return jsonify(status="ok", file=filename)
            
        elif action == "stop" and recording:
            def stop_and_convert():
                try:
                    camera.stop_recording()     # en picamera2 esto también PARA la cámara
                    camera.start()              # sin esto, la vista en vivo y las fotos se quedaban colgadas
                    log_to_console("Recording stopped.")
                except Exception as e:
                    log_to_console(f"Stop error: {e}")
                h264_path = getattr(app, 'h264_path', None)
                mp4_path = getattr(app, 'mp4_path', None)
                if h264_path and mp4_path and os.path.exists(h264_path):
                    log_to_console("Converting to MP4...")
                    try:
                        subprocess.run([
                            "ffmpeg", "-r", "30", "-i", h264_path,
                            "-c:v", "copy", mp4_path
                        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        os.remove(h264_path)
                        log_to_console(f"Video saved: {os.path.basename(mp4_path)}")
                    except Exception as e:
                        log_to_console(f"MP4 failed: {str(e)}")

            convert_thread = threading.Thread(target=stop_and_convert)
            convert_thread.start()
            recording = False
            return jsonify(status="ok")
        return jsonify(status="error"), 400

@app.route("/api/samples")
def list_samples():
    files = []
    for f in os.listdir(SAMPLES_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.mp4', '.txt', '.csv')):
            path = os.path.join(SAMPLES_DIR, f)
            files.append({
                "id": f,
                "time": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
                "type": "photo" if f.lower().endswith(('.jpg', '.jpeg')) else "video" if f.lower().endswith('.mp4') else "data"
            })
    files.sort(key=lambda x: x["time"], reverse=True)
    return jsonify(files)

@app.route("/samples/<filename>")
def view_sample(filename):
    """Para verla en el navegador (sin descargar)."""
    return send_from_directory(SAMPLES_DIR, filename)

@app.route("/download/<filename>")
def download_sample(filename):
    path = os.path.join(SAMPLES_DIR, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404

@app.route("/download/all")
def download_all():
    zpath = os.path.join(tempfile.gettempdir(), "planktoscope_samples.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:   # jpg/mp4 ya van comprimidos
        for f in sorted(os.listdir(SAMPLES_DIR)):
            if f.lower().endswith(('.jpg', '.jpeg', '.mp4', '.txt', '.csv')):
                z.write(os.path.join(SAMPLES_DIR, f), f)
        if os.path.isdir(RECORTES_DIR):
            for f in sorted(os.listdir(RECORTES_DIR)):
                z.write(os.path.join(RECORTES_DIR, f), f"recortes/{f}")
    return send_file(zpath, as_attachment=True, download_name="planktoscope_samples.zip")

@app.route("/download/ecotaxa")
def download_ecotaxa():
    """Zip para importar en EcoTaxa: todos los recortes + ecotaxa_planktoscope.tsv (cabecera, fila de tipos [t]/[f] y una
    fila por objeto, imágenes junto al TSV). Sin categoría: la clase del modelo va como columna informativa, no como
    anotación, para que nadie la confunda con una identificación."""
    numericos = ["capa", "x", "y", "w", "h", "nitidez", "area_px", "diametro_eq_px", "eje_mayor_px", "eje_menor_px",
                 "alargamiento", "circularidad", "solidez", "tono_media", "tono_std", "saturacion_media", "saturacion_std",
                 "brillo_media", "brillo_std", "area_um2", "diametro_eq_um", "eje_mayor_um", "eje_menor_um", "confianza_modelo"]
    um = config["camara"].get("um_por_px", 0.0)
    ancho = (config["camara"].get("foto_completa") or [640])[0] or 640
    filas = []
    for f in sorted(os.listdir(SAMPLES_DIR)):
        if not (f.startswith("objetos_") and f.endswith(".csv")):
            continue
        t = datetime.fromtimestamp(os.path.getmtime(os.path.join(SAMPLES_DIR, f)))
        foto = f[len("objetos_"):-len(".csv")]
        with open(os.path.join(SAMPLES_DIR, f), newline="") as fh:
            for r in csv.DictReader(fh):
                if (r.get("label") in ("fijo", "descartado") or not r.get("recorte")
                        or not os.path.exists(os.path.join(SAMPLES_DIR, r["recorte"]))):
                    continue                    # pegados al capilar (se repetirían en cada muestra) y borrosos, fuera
                fila = {"img_file_name": os.path.basename(r["recorte"]), "img_rank": 1,
                        "object_id": os.path.splitext(os.path.basename(r["recorte"]))[0],
                        "object_date": t.strftime("%Y%m%d"), "object_time": t.strftime("%H%M%S"),
                        "object_etiqueta_app": r.get("label", ""), "object_clase_modelo": r.get("clase_modelo", ""),
                        "sample_id": r.get("sesion") or f"foto_{foto}", "object_foto": foto, "acq_id": "modular_planktoscope",
                        "acq_um_por_px_recorte": um * 640 / ancho if um > 0 else ""}
                fila.update({f"object_{k}": r.get(k, "") for k in numericos})
                filas.append(fila)
    if not filas:
        return jsonify(error="No hay recortes: haz fotos con la foto completa activada"), 404
    columnas = list(filas[0])
    tipos = ["[f]" if c in ("img_rank", "acq_um_por_px_recorte") or c[len("object_"):] in numericos else "[t]" for c in columnas]
    zpath = os.path.join(tempfile.gettempdir(), "planktoscope_ecotaxa.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        tsv = io.StringIO()
        w = csv.writer(tsv, delimiter="\t", lineterminator="\n")
        w.writerow(columnas); w.writerow(tipos)
        for fila in filas:
            w.writerow([fila[c] for c in columnas])
        z.writestr("ecotaxa_planktoscope.tsv", tsv.getvalue())
        for fila in filas:
            z.write(os.path.join(RECORTES_DIR, fila["img_file_name"]), fila["img_file_name"])
    log_to_console(f"EcoTaxa: {len(filas)} objetos")
    return send_file(zpath, as_attachment=True, download_name="planktoscope_ecotaxa.zip")

@app.route("/api/samples/delete/<filename>", methods=["DELETE"])
def delete_sample(filename):
    path = os.path.join(SAMPLES_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        log_to_console(f"File deleted: {filename}")
        return jsonify(status="ok")
    return "File not found", 404

@app.route("/api/samples/delete/all", methods=["DELETE"])
def delete_all_samples():
    for f in os.listdir(SAMPLES_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.mp4', '.txt', '.csv')) and f != "sesiones.csv":
            path = os.path.join(SAMPLES_DIR, f)
            os.remove(path)
    if os.path.isdir(RECORTES_DIR):
        for f in os.listdir(RECORTES_DIR):
            os.remove(os.path.join(RECORTES_DIR, f))
    # los contadores NO vuelven a 0: sesiones.csv identifica las fotos por número y no puede haber dos fotos 12
    log_to_console("All samples deleted (sesiones.csv se conserva)")
    return jsonify(status="ok")

@app.route("/api/console/stream")
def console_stream():
    def generate():
        yield "data: Modular PlanktoScope console connected.\n\n"
        q = Queue()
        with log_lock:
            log_clients.append(q)
        try:
            while True:
                try:
                    yield f"data: {q.get(timeout=15)}\n\n"  # SSE exige "data:"
                except Empty:
                    yield ": ping\n\n"  # al escribir se detecta la pestaña cerrada y se libera su cola
        finally:
            with log_lock:
                log_clients.remove(q)
    return Response(generate(), mimetype="text/event-stream")

# ========== Inicialización final ==========
config = load_config()
focus_state = load_focus_state()
focus_step = focus_state["step"]
counter = load_counter()

# ========== GPIO ==========
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(config["stepper1"]["dir_pin"], GPIO.OUT)
GPIO.setup(config["stepper1"]["step_pin"], GPIO.OUT)
GPIO.setup(config["stepper1"]["enable_pin"], GPIO.OUT)
GPIO.output(config["stepper1"]["enable_pin"], GPIO.HIGH)

GPIO.setup(config["stepper2"]["dir_pin"], GPIO.OUT)
GPIO.setup(config["stepper2"]["step_pin"], GPIO.OUT)
GPIO.setup(config["stepper2"]["enable_pin"], GPIO.OUT)
GPIO.output(config["stepper2"]["enable_pin"], GPIO.HIGH)

LED_PIN = 11
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.HIGH)
led_state = False

fondo_blanco = cv2.imread(FONDO_FILE) if os.path.exists(FONDO_FILE) else None

camera = None
video_encoder = None
video_output = None
recording = False

log_clients = []  # una cola por pestaña: con una sola compartida, las pestañas viejas se quedaban mensajes
log_lock = Lock()

def log_to_console(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with log_lock:
        for q in log_clients:
            q.put(line)

if CAMERA_AVAILABLE:
    camera = Picamera2()
    ancho, alto = config["camara"].get("foto_completa", [0, 0])
    FOTO_COMPLETA = False
    if ancho and alto:
        try:
            # sensor = mismo tamaño: modo de sensor completo (binning), así las dos fotos ven el campo entero
            camera.configure(camera.create_preview_configuration(
                main={"size": (ancho, alto), "format": "RGB888"}, lores={"size": (640, 480), "format": "YUV420"},
                sensor={"output_size": (ancho, alto)}))
            FOTO_COMPLETA = True
            log_to_console(f"Foto completa: {ancho}×{alto}")
        except Exception as e:
            log_to_console(f"Foto completa desactivada ({e}); solo 640×480")
    if not FOTO_COMPLETA:
        camera.configure(camera.create_preview_configuration(lores={"size": (640, 480), "format": "YUV420"}))
    camera.start()
    log_to_console("Camera started")

def _motores_off():
    for k in ("stepper1", "stepper2"):
        GPIO.output(config[k]["enable_pin"], GPIO.HIGH)

atexit.register(_motores_off)  # al salir, motores desactivados y pines sin soltar (nada de GPIO.cleanup)

if __name__ == "__main__":
    log_to_console("Modular PlanktoScope started")
    ignore_focus_limits = False
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
