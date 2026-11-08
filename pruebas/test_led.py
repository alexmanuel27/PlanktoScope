import sys, time
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.config["stepper1"].update(steps_take_sample=50, delay=0.0005, led_delay_after_pump=0.0)
pc.RUIDO = 0.5
pc.CAPAS = [(pc.escena(40, 90.0, r=(8, 12)), -205)]
d = c.get("/api/disk").json; print("disk", d); assert d["total"] > d["free"] > 0
app.led_state = False
r = c.post("/api/series/start", json={"modo": "muestras", "valor": 2, "intervalo": 25, "espera": 0}).json; print(r)
assert app.led_state is True
vistos = []
while c.get("/api/series/state").json["activa"]:
    s = c.get("/api/series/state").json
    vistos.append((s["estado"].split(":")[-1].strip()[:20], s["led"])); time.sleep(0.5)
print(sorted(set(vistos)))
assert ("esperando la muestra", False) in set(vistos)
assert app.led_state is False and c.get("/api/series/state").json["estado"] == "terminada"
print("LED OK")
