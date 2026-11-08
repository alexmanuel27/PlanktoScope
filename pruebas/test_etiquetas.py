import sys, os, csv
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.led_state = True
pc.RUIDO = 0.5; pc.CAPAS = [(pc.escena(40, 90.0, r=(8, 12)), 0)]; app.focus_step = 0
g = app.capture_photo.__globals__
g["classify_image"] = lambda p: {"label": "Nitzschia", "confidence": 88.0}
assert app.config["camara"]["confianza_min"] == 55.0 and app.config["camara"]["mostrar_especie"] is False
r = c.get("/api/capture/photo").json
o = [x for x in r["objects"] if x["label"] != "descartado"][0]
print("por defecto:", r["summary"], r["file"], o["label"], o["clase_modelo"], o["confianza_modelo"])
assert o["label"] == "objeto" and o["clase_modelo"] == "Nitzschia" and r["summary"].startswith("objeto:")
row = list(csv.DictReader(open(os.path.join(app.SAMPLES_DIR, r["table"]))))[0]
assert "clase_modelo" in row and "confianza_modelo" in row
app.config["camara"]["mostrar_especie"] = True
r = c.get("/api/capture/photo").json; print("con especie 88%:", r["summary"])
assert r["summary"].startswith("Nitzschia")
g["classify_image"] = lambda p: {"label": "Nitzschia", "confidence": 52.0}
r = c.get("/api/capture/photo").json; print("con especie 52%:", r["summary"])
assert r["summary"].startswith("desconocido")
print("ETIQUETAS OK")
