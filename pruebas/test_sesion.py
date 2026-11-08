import sys, os, csv, io, zipfile
sys.path[:0] = ["/tmp/ptest", "/tmp/ptest/Code"]
import app, picamera2 as pc
c = app.app.test_client()
app.config["stepper2"].update(focus_min=-1000, focus_max=350, delay=0.0005, af_delay_fine=0.004)
app.led_state = True
pc.RUIDO = 0.5; pc.CAPAS = [(pc.escena(10, 90.0, r=(8, 12)), 0)]; app.focus_step = 0
assert c.get("/api/session").json["sesion"] is None
assert c.post("/api/session/start", json={"especie_cultivo": " "}).status_code == 400
c.get("/api/capture/photo")                                   # foto sin sesión
s = c.post("/api/session/start", json={"especie_cultivo": "chlorella_vulgaris", "origen": "cultivo", "dilucion": "1:10",
                                       "edad_cultivo_dias": "7", "operador": "Daniela"}).json["sesion"]
print("abierta:", s["sesion"], s["fotos_desde"])
assert s["fotos_desde"] == app.counter["photo"] + 1
r = c.get("/api/capture/photo").json; r2 = c.get("/api/capture/photo").json
fila = list(csv.DictReader(open(os.path.join(app.SAMPLES_DIR, r["table"]))))[0]; assert fila["sesion"] == s["sesion"]
s2 = c.post("/api/session/start", json={"especie_cultivo": "acutodesmus_obliquus"}).json["sesion"]   # cierra la anterior
filas = list(csv.DictReader(open(app.SESIONES_CSV)))
print("sesiones.csv:", [(f["sesion"], f["fotos_desde"], f["fotos_hasta"], f["especie_cultivo"]) for f in filas])
assert len(filas) == 1 and int(filas[0]["fotos_hasta"]) == int(filas[0]["fotos_desde"]) + 1 and "particion" in filas[0]
c.get("/api/capture/photo")
z = zipfile.ZipFile(io.BytesIO(c.get("/download/ecotaxa").data))
tsv = list(csv.reader(io.StringIO(z.read("ecotaxa_planktoscope.tsv").decode()), delimiter="\t"))
ids = {dict(zip(tsv[0], f))["sample_id"] for f in tsv[2:]}; print("sample_id:", ids)
assert {s["sesion"], s2["sesion"]} <= ids
n = app.counter["photo"]; c.delete("/api/samples/delete/all")
assert app.counter["photo"] == n and os.path.exists(app.SESIONES_CSV)          # ni contador a 0 ni registro borrado
# durante una serie no se abren ni cierran sesiones
c.post("/api/series/start", json={"modo": "muestras", "valor": 1, "intervalo": 5, "espera": 0})
assert c.post("/api/session/end").status_code == 409
import time
while c.get("/api/series/state").json["activa"]: time.sleep(0.5)
end = c.post("/api/session/end").json["sesion"]; print("cerrada:", end["sesion"], end["series"])
assert end["series"] and list(csv.DictReader(open(app.SESIONES_CSV)))[-1]["serie"].startswith("serie_")
assert c.post("/api/session/end").status_code == 400
print("SESION OK")
