import sys, os, csv
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.led_state = True
pc.RUIDO = 0.5  # el ISP de la cámara real deja el fondo con nitidez 2-6
pc.CAPAS = [(pc.escena(40, 90.0, r=(8, 12)), 0)]
# desenfocado: todo descartado, nada clasificado, sin anotada
app.focus_step = 120
r = c.get("/api/capture/photo").json
print("borrosa:", r["summary"], r["file"], [round(o["nitidez"], 1) for o in r["objects"]][:6])
assert r["objects"] and all(o["label"] == "descartado" for o in r["objects"]) and r["file"].startswith("photo_"), r["file"]
assert r["summary"] == "No objects classified"
rows = list(csv.DictReader(open(os.path.join(app.SAMPLES_DIR, r["table"]))))
assert rows and all(x["label"] == "descartado" for x in rows)
# enfocado: se clasifican; con confianza baja -> desconocido
app.focus_step = 0
g = app.capture_photo.__globals__
app.config["camara"]["mostrar_especie"] = True
orig = g["classify_image"]
g["classify_image"] = lambda p: {"label": "Nitzschia", "confidence": 38.0}
r = c.get("/api/capture/photo").json
print("nitida, conf 38:", r["summary"], r["file"])
assert any(o["label"] == "desconocido" for o in r["objects"]) and not any(o["label"] == "Nitzschia" for o in r["objects"])
g["classify_image"] = lambda p: {"label": "Nitzschia", "confidence": 88.0}
r = c.get("/api/capture/photo").json
print("nitida, conf 88:", r["summary"], r["file"])
assert any(o["label"] == "Nitzschia" for o in r["objects"]) and r["file"].startswith("plankton_Nitzschia")
g["classify_image"] = orig
# capas con una capa nítida y objetos descartados en el CSV
pc.CAPAS = [(pc.escena(40, 90.0, 0, 320, r=(8, 12)), -205), (pc.escena(20, 25.0, 320, 640, r=(8, 12)), -56)]
app.focus_step = 0
r = c.get("/api/capture/layers").json
print("capas:", r["capas"], r["objetos"], r["unicos"], r["conteo"])
print("UMBRAL OK")
