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

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

app = Flask(__name__)
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
os.makedirs(SAMPLES_DIR, exist_ok=True)

# ========== Cargar configuración ==========
def load_config():
    default_config = {
        "stepper1": {
            "dir_pin": 26,
            "step_pin": 19,
            "steps_take_sample": 2000,
            "delay": 0.0005
        },
        "stepper2": {
            "dir_pin": 5,
            "step_pin": 6,
            "steps_focus": 100,
            "delay": 0.0005
        }
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

config = load_config()

# ========== GPIO ==========
GPIO.setmode(GPIO.BCM)
GPIO.setup(config["stepper1"]["dir_pin"], GPIO.OUT)
GPIO.setup(config["stepper1"]["step_pin"], GPIO.OUT)
GPIO.setup(config["stepper2"]["dir_pin"], GPIO.OUT)
GPIO.setup(config["stepper2"]["step_pin"], GPIO.OUT)

# ========== Estado ==========
focus_step = 50
camera = None
video_encoder = None
video_output = None
recording = False

log_queue = Queue()
log_lock = Lock()

def log_to_console(msg):
    with log_lock:
        log_queue.put(f"[{time.strftime('%H:%M:%S')}] {msg}")

# ========== Cámara ==========
if CAMERA_AVAILABLE:
    camera = Picamera2()
    cam_config = camera.create_preview_configuration(lores={"size": (640, 480), "format": "YUV420"})
    camera.configure(cam_config)
    camera.start()
    log_to_console("Camera started")

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
                new_config[key]["steps_take_sample"] = int(new_config[key].get("steps_take_sample", 2000))
                new_config[key]["steps_focus"] = int(new_config[key].get("steps_focus", 100))
                new_config[key]["delay"] = float(new_config[key].get("delay", 0.0005))
            save_config(new_config)
            config = new_config
            GPIO.cleanup()
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(config["stepper1"]["dir_pin"], GPIO.OUT)
            GPIO.setup(config["stepper1"]["step_pin"], GPIO.OUT)
            GPIO.setup(config["stepper2"]["dir_pin"], GPIO.OUT)
            GPIO.setup(config["stepper2"]["step_pin"], GPIO.OUT)
            log_to_console("Configuration updated")
            return jsonify(status="ok")
        except Exception as e:
            return jsonify(error=str(e)), 400
    return jsonify(config)

def move_stepper(stepper_key, direction, steps):
    pin_dir = config[stepper_key]["dir_pin"]
    pin_step = config[stepper_key]["step_pin"]
    delay = config[stepper_key]["delay"]
    GPIO.output(pin_dir, GPIO.HIGH if direction == "forward" else GPIO.LOW)
    for _ in range(steps):
        GPIO.output(pin_step, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(pin_step, GPIO.LOW)
        time.sleep(delay)

@app.route("/api/focus/<direction>")
def focus(direction):
    global focus_step
    steps = config["stepper2"]["steps_focus"]
    if direction == "in":
        move_stepper("stepper2", "forward", steps)
        focus_step += 1
        log_to_console(f"Focus IN: {steps} steps")
    elif direction == "out":
        move_stepper("stepper2", "backward", steps)
        focus_step -= 1
        log_to_console(f"Focus OUT: {steps} steps")
    return jsonify(step=focus_step)

@app.route("/api/sample/take")
def take_sample():
    try:
        steps = config["stepper1"]["steps_take_sample"]
        log_to_console(f"Moving stepper1 ({steps} steps)")
        move_stepper("stepper1", "forward", steps)
        filename = f"sample_{int(time.time())}.txt"
        path = os.path.join(SAMPLES_DIR, filename)
        with open(path, "w") as f:
            f.write(f"Chlorophyll-a: 4.2 µg/L\nTimestamp: {datetime.now()}\nSteps: {steps}")
        log_to_console(f"Sample saved: {filename}")
        return jsonify(sample={"id": filename, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "type": "data"})
    except Exception as e:
        log_to_console(f"Sample error: {str(e)}")
        return jsonify(error="Sample failed"), 500

# ========== Cámara ==========
if CAMERA_AVAILABLE:
    @app.route("/video_feed")
    def video_feed():
        def generate_frames():
            while True:
                yuv_frame = camera.capture_buffer("lores")
                yuv_array = np.frombuffer(yuv_frame, dtype=np.uint8)
                yuv_reshaped = yuv_array.reshape((480 * 3 // 2, 640))
                bgr_frame = cv2.cvtColor(yuv_reshaped, cv2.COLOR_YUV2BGR_I420)
                ret, buffer = cv2.imencode('.jpg', bgr_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                time.sleep(0.05)
        return Response(generate_frames(),
                        mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route("/api/capture/photo")
    def capture_photo():
        yuv_frame = camera.capture_buffer("lores")
        yuv_array = np.frombuffer(yuv_frame, dtype=np.uint8)
        yuv_reshaped = yuv_array.reshape((480 * 3 // 2, 640))
        bgr_frame = cv2.cvtColor(yuv_reshaped, cv2.COLOR_YUV2BGR_I420)
        filename = f"photo_{int(time.time())}.jpg"
        path = os.path.join(SAMPLES_DIR, filename)
        cv2.imwrite(path, bgr_frame)
        log_to_console(f"Photo saved: {filename}")
        return jsonify(status="ok", file=filename)

    @app.route("/api/capture/video/<action>")
    def capture_video(action):
        global recording, video_encoder, video_output
        if action == "start" and not recording:
            filename = f"video_{int(time.time())}.h264"
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

@app.route("/api/console/stream")
def console_stream():
    def generate():
        yield " PlanktoScope console connected.\n\n"
        while True:
            if not log_queue.empty():
                with log_lock:
                    msg = log_queue.get()
                yield f" {msg}\n\n"
            time.sleep(0.3)
    return Response(generate(), mimetype="text/event-stream")

# ========== Cleanup ==========
import atexit
atexit.register(GPIO.cleanup)

if __name__ == "__main__":
    try:
        log_to_console("PlanktoScope started")
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        if CAMERA_AVAILABLE and camera:
            if recording:
                camera.stop_recording()
            camera.stop()
