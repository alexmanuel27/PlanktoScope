import sys, os, csv, json
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
r = list(app.rampa(10, 0.016, 0.006, 20)); assert all(d == 0.016 for d in r), r
r = list(app.rampa(100, 0.003, 0.006, 20)); assert len(r) == 100 and r[0] == 0.006 and r[50] == 0.003 and r[-1] == 0.006, (r[0], r[50], r[-1])
assert len(list(app.rampa(5, 0.003, 0.006, 20))) == 5
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.led_state = True
pc.CAPAS = [(pc.escena(40, 90.0, r=(6, 12)), 0)]; app.focus_step = 0
r = c.get("/api/capture/photo").json
o = r["objects"][0]; print(len(r["objects"]), "objetos;", {k: o[k] for k in ("w", "h", "area_px", "diametro_eq_px", "alargamiento", "circularidad", "solidez", "tono_media")})
assert "diametro_eq_px" in o and "diametro_eq_um" not in o and 0.5 < o["circularidad"] <= 1.3, o
rows = list(csv.DictReader(open(os.path.join(app.SAMPLES_DIR, r["table"]))))
assert len(rows) == len(r["objects"]) and rows[0]["diametro_eq_um"] == "", rows[0]
# calibración
assert c.post("/api/calibration", json={"um_por_px": -1}).status_code == 400
assert c.post("/api/calibration", json={"um_por_px": 2.0}).json["um_por_px"] == 2.0
assert json.load(open(app.CONFIG_FILE))["camara"]["um_por_px"] == 2.0
r2 = c.get("/api/capture/photo").json; o2 = r2["objects"][0]
assert abs(o2["diametro_eq_um"] - 2 * o2["diametro_eq_px"]) < 0.01, o2
# límites en µm: con mínimo 30 µm (15 px de diámetro) desaparecen los pequeños
app.config["camara"]["tamano_min_um"] = 30.0
r3 = c.get("/api/capture/photo").json
assert all(o["diametro_eq_um"] >= 29 for o in r3["objects"]) and len(r3["objects"]) <= len(r2["objects"]), [o["diametro_eq_um"] for o in r3["objects"]]
print("calibrado:", len(r2["objects"]), "objetos; con mínimo 30 µm:", len(r3["objects"]))
app.config["camara"].update(um_por_px=0.0, tamano_min_um=3.0)
# config: guardar ajustes desde la web no borra la sección de cámara
web = {k: dict(v) for k, v in app.config.items() if k.startswith("stepper")}
assert c.post("/api/config", json=web).json["status"] == "ok" and "camara" in json.load(open(app.CONFIG_FILE))
# fondo
assert c.post("/api/background").json["background"] is True and os.path.exists(app.FONDO_FILE)
r4 = c.get("/api/capture/photo").json; assert "error" not in r4
assert c.delete("/api/background").json["background"] is False and not os.path.exists(app.FONDO_FILE)
print("MEJORAS OK")
