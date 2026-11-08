import sys, os, csv, time
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.config["stepper1"].update(steps_take_sample=50, delay=0.0005, led_delay_after_pump=0.0)
pc.RUIDO = 0.5
pc.CAPAS = [(pc.escena(40, 90.0, 0, 320, r=(8, 12)), -205), (pc.escena(30, 70.0, 320, 640, r=(8, 12)), -56)]
app.led_state = False
# (Start ya enciende el LED: no se rechaza con el LED apagado)
app.led_state = True
assert c.post("/api/series/start", json={"modo": "muestras", "valor": 0, "intervalo": 5}).status_code == 400
assert c.post("/api/series/start", json={"modo": "tiempo", "valor": "x", "intervalo": 5}).status_code == 400
r = c.post("/api/series/start", json={"modo": "tiempo", "valor": 10, "intervalo": 5, "espera": 0}).json
print("start:", r); assert r["n"] == 2
assert c.get("/api/sample/take").status_code == 409 and c.get("/api/capture/photo").status_code == 409 and c.get("/api/focus/in").status_code == 409
assert c.get("/api/focus/current").status_code == 200 and c.get("/api/series/state").status_code == 200
assert c.post("/api/series/start", json={"modo": "muestras", "valor": 1, "intervalo": 5}).status_code == 409
t0 = time.time()
while c.get("/api/series/state").json["activa"] and time.time() - t0 < 150: time.sleep(1)
s = c.get("/api/series/state").json
print("estado:", s["estado"], s["fichero"], [(f["muestra"], f["t_s"], f["capas"], f["objetos"]) for f in s["filas"]], s["error"])
assert s["estado"] == "terminada" and len(s["filas"]) == 2 and s["filas"][1]["t_s"] >= 5
rows = list(csv.DictReader(open(os.path.join(app.SAMPLES_DIR, s["fichero"]))))
print(list(rows[0].keys())[:9], rows[0]["capas"]); assert len(rows) == 2
assert c.get("/api/sample/take").status_code == 200   # desbloqueado al terminar
# parar a mitad
r = c.post("/api/series/start", json={"modo": "muestras", "valor": 5, "intervalo": 3, "espera": 0}).json
time.sleep(1); c.post("/api/series/stop")
while c.get("/api/series/state").json["activa"]: time.sleep(1)
s = c.get("/api/series/state").json; print("parada:", s["estado"], len(s["filas"])); assert s["estado"] == "parada" and len(s["filas"]) < 5
print("SERIE OK")
