import sys, time
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.config["stepper1"].update(steps_take_sample=50, delay=0.0005, led_delay_after_pump=0.0)
pc.RUIDO = 0.5; pc.CAPAS = [(pc.escena(40, 90.0, r=(8, 12)), -205)]
led = []
orig = app.GPIO.output
app.GPIO.output = lambda pin, v: (led.append((time.time(), v)) if pin == app.LED_PIN else None, orig(pin, v))
def esperar():
    while c.get("/api/series/state").json["activa"]: time.sleep(0.3)
def cambios(seg):
    led.clear(); time.sleep(seg); return len(led)
# termina bien -> parpadeo lento
c.post("/api/series/start", json={"modo": "muestras", "valor": 1, "intervalo": 5, "espera": 0}); esperar()
s = c.get("/api/series/state").json; n = cambios(4.1)
print("fin:", s["estado"], s["parpadeo"], "cambios en 4 s:", n); assert s["parpadeo"] and 3 <= n <= 6
r = c.get("/api/led/toggle").json; n = cambios(2)
print("tras LED:", r, c.get("/api/series/state").json["parpadeo"], n); assert r["state"] is False and n == 0 and not app.parpadeo["activo"]
# parada manual -> sin parpadeo
c.post("/api/series/start", json={"modo": "muestras", "valor": 3, "intervalo": 30, "espera": 0}); time.sleep(1); c.post("/api/series/stop"); esperar()
print("parada:", c.get("/api/series/state").json["parpadeo"]); assert not app.parpadeo["activo"] and app.led_state is False
# error -> parpadeo rápido; una captura lo apaga
g = app.capture_layers.__globals__; real = g["capturar_capas"]; g["capturar_capas"] = lambda: {"error": "simulado"}
c.post("/api/series/start", json={"modo": "muestras", "valor": 2, "intervalo": 5, "espera": 0}); esperar()
n = cambios(2.1); s = c.get("/api/series/state").json
print("error:", s["estado"], s["parpadeo"], "cambios en 2 s:", n); assert s["estado"] == "error" and n >= 10
g["capturar_capas"] = real
c.get("/api/capture/photo"); print("tras captura:", app.parpadeo["activo"]); assert not app.parpadeo["activo"]
print("PARPADEO OK")
