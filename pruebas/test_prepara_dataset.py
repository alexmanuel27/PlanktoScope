# Particiones por sesión del dataset propio (src/ml/prepara_dataset.py). No usa la app ni la cámara.
import os, sys, tempfile, subprocess
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
t = tempfile.mkdtemp()
rec, carp = os.path.join(t, "recortes"), os.path.join(t, "etiquetados")
for clase, fotos in {"chlorella_vulgaris": [1, 2, 5, 9], "no_alga_burbuja": [2, 9], "duda": [5]}.items():
    os.makedirs(os.path.join(carp, clase), exist_ok=True)
    for n in fotos:
        for i in range(2):
            open(os.path.join(carp, clase, f"{n}_capa-10_{i}.png"), "wb").write(b"x")
open(os.path.join(t, "sesiones.csv"), "w").write(
    "sesion,fecha,origen,especie_cultivo,edad_cultivo_dias,dilucion,operador,fotos_desde,fotos_hasta,serie,um_por_px,particion,notas\n"
    "S1,,cultivo,chlorella_vulgaris,,,,1,3,,,train,\nS2,,cultivo,chlorella_vulgaris,,,,4,6,,,val,\nS3,,cultivo,chlorella_vulgaris,,,,7,9,,,test,\n")
dest = os.path.join(t, "ds")
out = subprocess.run([sys.executable, os.path.join(REPO, "src/ml/prepara_dataset.py"), "--recortes", rec, "--carpetas", carp,
                      "--sesiones", os.path.join(t, "sesiones.csv"), "--destino", dest], capture_output=True, text=True)
print(out.stdout, out.stderr)
n = lambda p, c: len(os.listdir(os.path.join(dest, p, c))) if os.path.isdir(os.path.join(dest, p, c)) else 0
assert (n("train", "chlorella_vulgaris"), n("val", "chlorella_vulgaris"), n("test", "chlorella_vulgaris")) == (4, 2, 2)
assert (n("train", "no_alga_burbuja"), n("test", "no_alga_burbuja")) == (2, 2) and not os.path.exists(os.path.join(dest, "train", "duda"))
assert "AVISO: sin recortes en no_alga_burbuja/val" in out.stdout
print("PREPARA OK")
