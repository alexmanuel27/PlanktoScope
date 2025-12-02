# app.py — PlanktoScope final estable

from flask import Flask, render_template, jsonify, send_file, Response
import time
import io
import os
import subprocess
import threading
from datetime import datetime
from queue import Queue
from threading import Lock
import cv2
import numpy as np

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

app = Flask(__name__)
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
os.makedirs(SAMPLES_DIR, exist_ok=True)

# ========== Estado global ==========
focus_step = 50
camera = None
video_encoder = None
video_output = None
recording = False

# Cola para logs
log_queue = Queue()
log_lock = Lock()

def log_to_console(msg):
    with log_lock:
        log_queue.put(f"[{time.strftime('%H:%M:%S')}] {msg}")

# ========== Inicializar cámara ==========
if CAMERA_AVAILABLE:
    camera = Picamera2()
    config = camera.create_preview_configuration(
        main={"size": (1280, 720), "format": "RGB888"},
        lores={"size": (640, 480), "format": "YUV420"},
        display="lores"
    )
    camera.configure(config)
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

@app.route("/api/focus/<direction>")
def focus(direction):
    global focus_step
    if direction == "in" and focus_step < 100:
        focus_step += 1
    elif direction == "out" and focus_step > 0:
        focus_step -= 1
    log_to_console(f"Focus step: {focus_step}")
    return jsonify(step=focus_step)

# ========== Rutas de cámara ==========
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
        filename = f"photo_{int(time.time())}.jpg"
        path = os.path.join(SAMPLES_DIR, filename)
        request = camera.capture_request()
        request.save("main", path)
        request.release()
        log_to_console(f"Photo saved: {filename}")
        return jsonify(status="ok", file=filename)

    @app.route("/api/capture/video/<action>")
    def capture_video(action):
        global recording, video_encoder, video_output
        if action == "start" and not recording:
            filename = f"video_{int(time.time())}.h264"
            path = os.path.join(SAMPLES_DIR, filename)
            video_encoder = H264Encoder(10000000)
            video_output = FileOutput(path)
            camera.start_recording(video_encoder, video_output, name="main")
            recording = True
            app.h264_path = path
            app.mp4_path = path.replace(".h264", ".mp4")
            log_to_console(f"Video recording started: {filename}")
            return jsonify(status="ok", file=filename)
            
        elif action == "stop" and recording:
            # Detener grabación de forma segura
            def stop_recording_safely():
                try:
                    camera.stop_recording()
                    log_to_console("Recording stopped.")
                except Exception as e:
                    log_to_console(f"Stop recording error: {e}")
                finally:
                    # Reiniciar cámara para evitar congelamiento
                    try:
                        camera.stop()
                        camera.configure(camera.create_preview_configuration(
                            main={"size": (1280, 720), "format": "RGB888"},
                            lores={"size": (640, 480), "format": "YUV420"},
                            display="lores"
                        ))
                        camera.start()
                        log_to_console("Camera reinitialized.")
                    except Exception as e:
                        log_to_console(f"Camera reinit error: {e}")

            # Ejecutar en hilo separado
            stop_thread = threading.Thread(target=stop_recording_safely)
            stop_thread.start()
            stop_thread.join(timeout=10)  # Esperar máximo 10 segundos

            recording = False
            video_encoder = None
            video_output = None

            # Convertir a MP4 en segundo plano
            def convert_to_mp4():
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
                        log_to_console(f"Video saved as MP4: {os.path.basename(mp4_path)}")
                    except Exception as e:
                        log_to_console(f"MP4 conversion failed: {str(e)}")

            convert_thread = threading.Thread(target=convert_to_mp4)
            convert_thread.start()

            return jsonify(status="ok")
        return jsonify(status="error"), 400

    @app.route("/api/sample/take")
    def take_sample():
        filename = f"sample_{int(time.time())}.txt"
        path = os.path.join(SAMPLES_DIR, filename)
        with open(path, "w") as f:
            f.write(f"Chlorophyll-a: 4.2 µg/L\nTimestamp: {datetime.now()}")
        log_to_console(f"Sample data saved: {filename}")
        return jsonify(sample={"id": filename, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "type": "data"})

if __name__ == "__main__":
    try:
        log_to_console("PlanktoScope started")
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        if CAMERA_AVAILABLE and camera:
            if recording:
                camera.stop_recording()
            camera.stop()