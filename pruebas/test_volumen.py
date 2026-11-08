import sys, os, csv, time
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.config["stepper1"].update(steps_take_sample=50, delay=0.0005, led_delay_after_pump=0.0)
pc.RUIDO = 0.5; pc.CAPAS = [(pc.escena(20, 90.0, r=(8, 12)), -205)]
assert c.post("/api/calibration/pump", json={"pasos": 1000, "ml": 0}).status_code == 400
assert c.post("/api/calibration/depth", json={"profundidad_um": -3}).status_code == 400
r = c.post("/api/calibration/pump", json={"pasos": 20000, "ml": 10}).json; print("bomba:", r)
assert r["pasos_por_ml"] == 2000 and abs(r["ml_por_muestra"] - 0.025) < 1e-9
assert c.post("/api/calibration/depth", json={"profundidad_um": 200}).json["volumen_foto_ml"] is None   # falta µm/px
c.post("/api/calibration", json={"um_por_px": 2.0})
v = c.post("/api/calibration/depth", json={"profundidad_um": 200}).json["volumen_foto_ml"]; print("volumen foto:", v)
assert abs(v - 640 * 2 * 480 * 2 * 200 / 1e12) < 1e-15
q = __import__("queue").Queue(); app.log_clients[:] = [q]
c.post("/api/series/start", json={"modo": "muestras", "valor": 1, "intervalo": 1, "espera": 0})
while c.get("/api/series/state").json["activa"]: time.sleep(0.5)
s = c.get("/api/series/state").json
fila = list(csv.DictReader(open(os.path.join(app.SAMPLES_DIR, s["fichero"]))))[0]
print({k: fila[k] for k in ("objetos", "volumen_ml", "volumen_bombeado_ml", "total_por_ml")})
assert abs(float(fila["total_por_ml"]) - int(fila["objetos"]) / v) < 1
logs = []
while not q.empty(): logs.append(q.get())
assert not any("se solapan" in l for l in logs)
c.post("/api/calibration/pump", json={"pasos": 50, "ml": 1e-5})        # bombea menos de lo que se fotografía
c.post("/api/series/start", json={"modo": "muestras", "valor": 1, "intervalo": 1, "espera": 0})
while c.get("/api/series/state").json["activa"]: time.sleep(0.5)
logs = []
while not q.empty(): logs.append(q.get())
assert any("se solapan" in l for l in logs)
print("VOLUMEN OK")
