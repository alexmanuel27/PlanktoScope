import sys, os, csv, time
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
pc.RUIDO = 0.5
suciedad = pc.escena(4, 120.0, 0, 640, 0, 480, r=(9, 12))          # pegada al capilar: siempre en el mismo sitio
def nueva_muestra():
    pc.CAPAS = [(suciedad + pc.escena(12, 90.0, r=(8, 12)), -205)]  # las algas cambian de sitio al bombear
nueva_muestra()
g = app.capture_layers.__globals__
real = g["bombear"]; g["bombear"] = lambda: (real(), nueva_muestra())
q = __import__("queue").Queue(); app.log_clients[:] = [q]
c.post("/api/series/start", json={"modo": "muestras", "valor": 6, "intervalo": 1, "espera": 0})
while c.get("/api/series/state").json["activa"]: time.sleep(0.5)
s = c.get("/api/series/state").json
print([(f["muestra"], f["objetos"], f["fijos"]) for f in s["filas"]], s["error"])
logs = []
while not q.empty(): logs.append(q.get())
print([l.split("] ")[1] for l in logs if l.split("] ")[1].startswith("Objetos")])
assert s["filas"][0]["fijos"] == 0 and s["filas"][1]["fijos"] == 0          # hacen falta 2 muestras previas
assert all(f["fijos"] >= 3 for f in s["filas"][2:5]), "la suciedad debe salir como fija desde la 3.ª muestra"
assert all(f["fijos"] <= 6 for f in s["filas"]), "las algas nuevas no deben salir como fijas"
# desde la 6.ª hay 5 fotos para la mediana: la suciedad queda en el fondo y ya ni se detecta (como en el PlanktoScope)
obj = [l for l in logs if l.split("] ")[1].startswith("Objetos")]
assert "mediana de la serie" in obj[5] and s["filas"][5]["fijos"] == 0
fila = list(csv.DictReader(open(os.path.join(app.SAMPLES_DIR, s["fichero"]))))[-1]; assert "fijos" in fila
print("FIJOS OK")
