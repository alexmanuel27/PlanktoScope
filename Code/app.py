# app.py
from flask import Flask, render_template, jsonify, send_file, Response, request
import time
import io
import os
import subprocess
import threading
import json
from datetime import datetime
from queue import Queue
from threading import Lock
import cv2
import numpy as np
import RPi.GPIO as GPIO
import math

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

# ========== Clasificador de plancton ==========
try:
    from ml.classifier import classify_image
    CLASSIFIER_AVAILABLE = True
    print("✅ Plankton classifier loaded")
except Exception as e:
    CLASSIFIER_AVAILABLE = False
    print(f"❌ Classifier error: {e}")

app = Flask(__name__)
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
FOCUS_STATE_JFILE = os.path.join(os.path.dirname(__file__), "focus_state.json")
COUNTER_FILE = os.path.join(SAMPLES_DIR, "counter.json")
os.makedirs(SAMPLES_DIR, exist_ok=True)

# ========== Variables globales ==========
last_annotated_frame = None
last_annotation_time = 0
last_classification = {"label": "unknown", "confidence": 0.0}
ignore_focus_limits = False

def should_clear_annotations():
    current_time = time.time()
    return current_time - last_annotation_time > 10.0

def annotate_frame(frame, classifications):
    for obj in classifications:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        label = obj["label"]
        confidence = obj["confidence"]
        color = (0, 255, 0) if label != "unknown" else (0, 0, 255)
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
        "stepper1": {"dir_pin": 26, "step_pin": 19, "enable_pin": 9, "steps_take_sample": 2000, "delay": 0.0005},
        "stepper2": {"dir_pin": 5, "step_pin": 6, "enable_pin": 13, "steps_focus": 100, "delay": 0.0005, "focus_min": 40, "focus_max": 60}
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            for key in ["stepper1", "stepper2"]:
                if key not in config:
                    config[key] = default_config[key]
    else:
        config = default_config
        save_config(config)
    return config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# ========== Cargar/guardar estado del foco ==========
def load_focus_state():
    default_state = {"step": 100}
    if os.path.exists(FOCUS_STATE_JFILE):
        try:
            with open(FOCUS_STATE_JFILE, "r") as f:
                return json.load(f)
        except:
            pass
    return default_state

def save_focus_state(state):
    with open(FOCUS_STATE_JFILE, "w") as f:
        json.dump(state, f)

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
    with open(COUNTER_FILE, "w") as f:
        json.dump(counter, f)

# ========== Rutas y funciones ==========
@app.route("/")
def index():
    files = []
    for f in os.listdir(SAMPLES_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.mp4', '.txt')):
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
            new_config = request.json
            for key in ["stepper1", "stepper2"]:
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
            
            GPIO.cleanup()
            GPIO.setmode(GPIO.BCM)
            
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
            
            log_to_console("Configuration updated")
            return jsonify(status="ok")
        except Exception as e:
            return jsonify(error=str(e)), 400
    return jsonify(config)

@app.route("/api/focus/current")
def get_focus_current():
    return jsonify(step=focus_step)

@app.route("/api/focus/ignore", methods=["POST"])
def toggle_ignore_limits():
    global ignore_focus_limits
    ignore_focus_limits = not ignore_focus_limits
    log_to_console(f"Focus limits ignored: {ignore_focus_limits}")
    return jsonify(status="ok", ignore=ignore_focus_limits)

@app.route("/api/led/toggle")
def toggle_led():
    global led_state
    led_state = not led_state
    gpio_value = GPIO.LOW if led_state else GPIO.HIGH
    GPIO.output(LED_PIN, gpio_value)
    status = "ON" if led_state else "OFF"
    log_to_console(f"LED turned {status}")
    return jsonify(state=led_state, status=status)

def move_stepper(stepper_key, direction, steps):
    pin_dir = config[stepper_key]["dir_pin"]
    pin_step = config[stepper_key]["step_pin"]
    pin_enable = config[stepper_key]["enable_pin"]
    delay = config[stepper_key]["delay"]
    
    GPIO.output(pin_enable, GPIO.LOW)
    time.sleep(0.01)
    GPIO.output(pin_dir, GPIO.HIGH if direction == "forward" else GPIO.LOW)
    
    for _ in range(steps):
        GPIO.output(pin_step, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(pin_step, GPIO.LOW)
        time.sleep(delay)
    
    GPIO.output(pin_enable, GPIO.HIGH)

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

@app.route("/api/sample/take")
def take_sample():
    try:
        steps = config["stepper1"]["steps_take_sample"]
        log_to_console(f"Moving stepper1 ({steps} steps)")
        move_stepper("stepper1", "forward", steps)
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

    @app.route("/api/capture/photo")
    def capture_photo():
        global counter, last_annotated_frame, last_annotation_time
        counter["photo"] += 1
        save_counter(counter)
        img_filename = f"photo_{counter['photo']}.jpg"
        img_path = os.path.join(SAMPLES_DIR, img_filename)
        
        try:
            yuv_frame = camera.capture_buffer("lores")
            yuv_array = np.frombuffer(yuv_frame, dtype=np.uint8)
            yuv_reshaped = yuv_array.reshape((480 * 3 // 2, 640))
            bgr_frame = cv2.cvtColor(yuv_reshaped, cv2.COLOR_YUV2BGR_I420)
            
            # Guardar imagen original
            cv2.imwrite(img_path, bgr_frame)
            log_to_console(f"Image captured: {img_filename}")
            
            H, W = bgr_frame.shape[:2]
            gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            gray = clahe.apply(gray)
            blur = cv2.GaussianBlur(gray, (5,5), 0)
            th = cv2.adaptiveThreshold(
                blur, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                31, 3
            )
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
            th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel, iterations=2)
            cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            min_area = 0.0005 * H * W
            max_area = 0.01 * H * W
            
            classifications = []
            for c in cnts:
                area = cv2.contourArea(c)
                if area < min_area or area > max_area:
                    continue
                
                peri = cv2.arcLength(c, True)
                if peri == 0:
                    continue
                    
                circularity = 4 * math.pi * area / (peri * peri)
                elongation = 1.0
                if len(c) >= 5:
                    (_, _), (MA, ma), _ = cv2.fitEllipse(c)
                    if MA > 0:
                        elongation = ma / MA
                
                x, y, w, h = cv2.boundingRect(c)
                obj_img = bgr_frame[y:y+h, x:x+w]
                obj_path = os.path.join(SAMPLES_DIR, f"temp_obj_{counter['photo']}_{len(classifications)}.jpg")
                cv2.imwrite(obj_path, obj_img)
                
                result = {"label": "unknown", "confidence": 0.0}
                if CLASSIFIER_AVAILABLE:
                    try:
                        result = classify_image(obj_path)
                        log_to_console(f"Object classification: {result['label']} ({result['confidence']:.1f}%)")
                    except Exception as e:
                        log_to_console(f"Classification error: {e}")
                        result = {"label": "error", "confidence": 0.0}
                
                classifications.append({
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "label": result["label"],
                    "confidence": result["confidence"]
                })
                os.remove(obj_path)
            
            # Generar resumen
            class_count = {}
            for obj in classifications:
                label = obj["label"]
                class_count[label] = class_count.get(label, 0) + 1
            
            if class_count:
                class_list = ", ".join([f"{k}: {v}" for k, v in class_count.items()])
                log_to_console(f"Classification summary: {class_list}")
            else:
                class_list = "No objects classified"
                log_to_console(class_list)
            
            # Dibujar anotaciones
            annotated_frame = bgr_frame.copy()
            for obj in classifications:
                x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
                label = obj["label"]
                confidence = obj["confidence"]
                color = (0, 255, 0) if label != "unknown" else (0, 0, 255)
                cv2.rectangle(annotated_frame, (x, y), (x+w, y+h), color, 2)
                label_text = f"{label} ({int(confidence)}%)" if confidence > 0 else "unknown"
                cv2.putText(annotated_frame, label_text, (x+5, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            # Actualizar la última imagen anotada
            last_annotated_frame = annotated_frame
            last_annotation_time = time.time()
            
            # ✅ Guardar la imagen ANOTADA con el nombre clasificado
            if classifications:
                first_class = classifications[0]["label"]
                first_conf = int(classifications[0]["confidence"])
                annotated_filename = f"plankton_{first_class}_{first_conf}_{counter['photo']}_annotated.jpg"
                annotated_path = os.path.join(SAMPLES_DIR, annotated_filename)
                cv2.imwrite(annotated_path, annotated_frame)
                log_to_console(f"Annotated image saved: {annotated_filename}")
                final_filename = annotated_filename
            else:
                final_filename = img_filename
            
            return jsonify({
                "status": "ok",
                "file": final_filename,
                "class": "multiple",
                "confidence": 0.0,
                "objects": classifications,
                "summary": class_list
            })
            
        except Exception as e:
            log_to_console(f"Photo capture error: {e}")
            return jsonify({"error": "Capture failed"}), 500

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
                    camera.stop_recording()
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
        if f.lower().endswith(('.jpg', '.jpeg', '.mp4', '.txt')):
            path = os.path.join(SAMPLES_DIR, f)
            files.append({
                "id": f,
                "time": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
                "type": "photo" if f.lower().endswith(('.jpg', '.jpeg')) else "video" if f.lower().endswith('.mp4') else "data"
            })
    files.sort(key=lambda x: x["time"], reverse=True)
    return jsonify(files)

@app.route("/download/<filename>")
def download_sample(filename):
    path = os.path.join(SAMPLES_DIR, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404

@app.route("/download/all")
def download_all():
    files = "\n".join(os.listdir(SAMPLES_DIR))
    return send_file(io.BytesIO(files.encode()), mimetype="text/plain", as_attachment=True, download_name="all_samples.txt")

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
        if f.lower().endswith(('.jpg', '.jpeg', '.mp4', '.txt')):
            path = os.path.join(SAMPLES_DIR, f)
            os.remove(path)
    global counter
    counter = {"photo": 0, "video": 0}
    save_counter(counter)
    log_to_console("All samples deleted")
    return jsonify(status="ok")

@app.route("/api/console/stream")
def console_stream():
    def generate():
        yield " Modular PlanktoScope console connected.\n\n"
        while True:
            if not log_queue.empty():
                with log_lock:
                    msg = log_queue.get()
                yield f" {msg}\n\n"
            time.sleep(0.3)
    return Response(generate(), mimetype="text/event-stream")

# ========== Inicialización final ==========
config = load_config()
focus_state = load_focus_state()
focus_step = focus_state["step"]
counter = load_counter()

# ========== GPIO ==========
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

camera = None
video_encoder = None
video_output = None
recording = False

log_queue = Queue()
log_lock = Lock()

def log_to_console(msg):
    with log_lock:
        log_queue.put(f"[{time.strftime('%H:%M:%S')}] {msg}")

if CAMERA_AVAILABLE:
    camera = Picamera2()
    cam_config = camera.create_preview_configuration(lores={"size": (640, 480), "format": "YUV420"})
    camera.configure(cam_config)
    camera.start()
    log_to_console("Camera started")

import atexit
atexit.register(GPIO.cleanup)

if __name__ == "__main__":
    log_to_console("Modular PlanktoScope started")
    ignore_focus_limits = False
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)