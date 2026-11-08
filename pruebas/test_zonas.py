import sys, time
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.002, af_delay_fine=0.004)  # como en el equipo: con 0,0005 el barrido grueso toma ~1 muestra cada 50 pasos y no separa planos a 30
app.led_state = True
q = __import__("queue").Queue(); app.log_clients[:] = [q]
def run(nombre, capas, inicio=0):
    pc.CAPAS = capas; app.focus_step = inicio
    af = c.get("/api/focus/auto").json["step"]
    r = c.get("/api/capture/layers").json
    log = []
    while not q.empty():
        m = q.get()
        if "candidatas" in m or "capa en" in m: log.append(m.split("] ")[1])
    print(nombre, "AF", af, "capas", r["capas"], log)
    return af, r["capas"]
# el caso del equipo: partícula grande y contrastada (una zona) a -563, algas pequeñas repartidas a -533
af, capas = run("particula+algas", [(pc.escena(1, 140.0, 380, 420, 0, 40, (35, 45)), -563), (pc.escena(60, 45.0, 0, 640, 130, 480, (3, 7)), -533)])
assert abs(af + 533) <= 5, af
assert len(capas) == 2 and abs(capas[0] + 563) <= 5 and abs(capas[1] + 533) <= 5, capas
af, capas = run("dos mitades", [(pc.escena(80, 70.0, 0, 320), -205), (pc.escena(80, 50.0, 320, 640), -56)], 300)
assert len(capas) == 2 and abs(capas[0] + 205) <= 5 and abs(capas[1] + 56) <= 5, capas
af, capas = run("una capa", [(pc.escena(150, 70.0), -237)], -900)
assert abs(af + 237) <= 5 and len(capas) == 1 and abs(capas[0] + 237) <= 5, (af, capas)
af, capas = run("vacio", [], 0)
assert capas == [], capas
af, capas = run("dos profundidades en todas las zonas", [(pc.escena(100, 70.0), -205), (pc.escena(100, 50.0), -56)], 0)
assert len(capas) == 2 and abs(capas[0] + 205) <= 5 and abs(capas[1] + 56) <= 5, capas
print("ZONAS OK")
