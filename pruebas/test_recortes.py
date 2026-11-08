import sys, os, csv, zipfile, io, cv2
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
assert app.FOTO_COMPLETA, "foto completa no activada"
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.led_state = True
pc.RUIDO = 0.5; pc.CAPAS = [(pc.escena(25, 90.0, r=(8, 12)), 0)]; app.focus_step = 0
r = c.get("/api/capture/photo").json
objs = r["objects"]; o = objs[0]
print(r["file"], len(objs), o["recorte"], (o["x"], o["y"], o["w"], o["h"]))
full = [f for f in os.listdir(app.SAMPLES_DIR) if f.endswith("_full.jpg")]; print("full:", full)
assert full and cv2.imread(os.path.join(app.SAMPLES_DIR, full[0])).shape == (1520, 2028, 3)
im = cv2.imread(os.path.join(app.SAMPLES_DIR, o["recorte"]))
print("recorte", im.shape, "≈", round((o["w"] + 2 * max(4, .1 * max(o["w"], o["h"]))) * 2028 / 640))
assert im.shape[1] >= o["w"] * 3 and all(os.path.exists(os.path.join(app.SAMPLES_DIR, x["recorte"])) for x in objs)
rows = list(csv.DictReader(open(os.path.join(app.SAMPLES_DIR, r["table"])))); assert rows[0]["recorte"].startswith("recortes/")
# capas: recortes por capa, sin recortes de la apilada
pc.CAPAS = [(pc.escena(20, 90.0, 0, 320, r=(8, 12)), -205), (pc.escena(20, 90.0, 320, 640, r=(8, 12)), -56)]
r = c.get("/api/capture/layers").json; n = r["foto"]
rec = sorted(f for f in os.listdir(app.RECORTES_DIR) if f.startswith(f"{n}_"))
print("capas", r["capas"], "recortes", len(rec), rec[:2], any("apilada" in f for f in rec))
assert rec and not any("apilada" in f for f in rec)
assert any(f.endswith("apilada_full.jpg") or "apilada" in f and f.endswith("_full.jpg") for f in os.listdir(app.SAMPLES_DIR))
z = zipfile.ZipFile(io.BytesIO(c.get("/download/all").data)); assert any(x.startswith("recortes/") for x in z.namelist())
c.delete("/api/samples/delete/all"); assert os.listdir(app.RECORTES_DIR) == []
print("RECORTES OK")
