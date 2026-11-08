import sys, io, csv, zipfile
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.led_state = True
assert c.get("/download/ecotaxa").status_code == 404          # sin recortes todavía
pc.RUIDO = 0.5; pc.CAPAS = [(pc.escena(15, 90.0, r=(8, 12)), 0)]; app.focus_step = 0
n1 = len(c.get("/api/capture/photo").json["objects"])
app.config["camara"]["um_por_px"] = 2.0
n2 = len(c.get("/api/capture/photo").json["objects"])
z = zipfile.ZipFile(io.BytesIO(c.get("/download/ecotaxa").data))
filas = list(csv.reader(io.StringIO(z.read("ecotaxa_planktoscope.tsv").decode()), delimiter="\t"))
cab, tipos, datos = filas[0], filas[1], filas[2:]
print(len(datos), "objetos;", cab[:6], tipos[:6])
assert set(tipos) <= {"[t]", "[f]"} and len(tipos) == len(cab) and len(datos) == n1 + n2
d = dict(zip(cab, datos[-1]))
assert d["img_file_name"] in z.namelist() and d["object_id"] and len(d["object_date"]) == 8 and float(d["acq_um_por_px_recorte"]) > 0
assert tipos[cab.index("object_area_px")] == "[f]" and tipos[cab.index("object_clase_modelo")] == "[t]"
assert all(dict(zip(cab, r))["img_file_name"] in z.namelist() for r in datos)
print("ECOTAXA OK")
