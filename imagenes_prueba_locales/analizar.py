"""Analiza con el modelo del equipo las imágenes que pongas en esta carpeta.

Uso (en el Mac, dentro de esta carpeta):
    ~/miniforge3/envs/plankton-audit/bin/python analizar.py                  # mismos ajustes que el equipo
    ~/miniforge3/envs/plankton-audit/bin/python analizar.py --area-min 0.003 # ignorar lo pequeño
    ... --sin-clase   # recuadros numerados sin nombre de especie

--area-min / --area-max: tamaño de objeto aceptado, como fracción del área de la imagen
(por defecto 0.0005 y 0.01, los del equipo: con eso los objetos grandes, como filamentos, se descartan).

Para cada imagen hace dos cosas:
  1. Clasifica la imagen completa (útil si la foto es de un solo organismo, p. ej. microscopio normal).
  2. Pasa el detector del equipo y clasifica cada objeto recortado: lo mismo que hace "Capture Photo".
Deja en resultados/: resultados.csv (top-3 por imagen y por objeto) y una copia anotada de cada imagen.
"""
import argparse
import csv
import os
import sys

import cv2
import numpy as np
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "Code"))
from ml.classifier import labels, probabilidades  # noqa: E402  (mismo modelo y preprocesado que la Raspberry)
from ml.detector import detectar  # noqa: E402

EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
OUT = os.path.join(AQUI, "resultados")


def top3(p):
    return [(labels[int(i)], float(p[i])) for i in np.argsort(p)[::-1][:3]]


def plano(t):
    return [v for clase, conf in t for v in (clase, f"{conf:.3f}")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area-min", type=float, default=0.0005)
    ap.add_argument("--area-max", type=float, default=0.01)
    ap.add_argument("--sin-clase", action="store_true", help="recuadros numerados, sin nombre de especie")
    a = ap.parse_args()
    imagenes = sorted(f for f in os.listdir(AQUI) if f.lower().endswith(EXT))
    if not imagenes:
        sys.exit("No hay imágenes en esta carpeta (jpg, png, tif, bmp).")
    os.makedirs(OUT, exist_ok=True)
    filas = []
    for f in imagenes:
        bgr = cv2.imread(os.path.join(AQUI, f))
        if bgr is None:
            print(f"{f}: no se pudo leer, la salto")
            continue
        rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        entera = top3(probabilidades(rgb))
        filas.append([f, "imagen_completa", "", "", "", "", *plano(entera)])

        cajas = detectar(bgr, a.area_min, a.area_max)
        anotada = bgr.copy()
        g = max(2, bgr.shape[1] // 320)            # grosor de línea proporcional al tamaño de la imagen
        for n, (x, y, w, h) in enumerate(cajas, 1):
            t = top3(probabilidades(rgb.crop((x, y, x + w, y + h))))
            filas.append([f, n, x, y, w, h, *plano(t)])
            cv2.rectangle(anotada, (x, y), (x + w, y + h), (0, 0, 255), g)
            texto = f"{n}" if a.sin_clase else f"{n} {t[0][0]} {t[0][1]:.0%}"
            (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.3 * g, g)
            ty = y + h - 5                                                   # abajo, dentro del recuadro: no se pisan entre sí
            cv2.rectangle(anotada, (x, ty - th - 4), (x + tw + 6, ty + 3), (255, 255, 255), -1)  # fondo legible
            cv2.putText(anotada, texto, (x + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.3 * g, (0, 0, 255), g)
        cv2.imwrite(os.path.join(OUT, os.path.splitext(f)[0] + "_anotada.jpg"), anotada)
        print(f"{f}: imagen completa -> {entera[0][0]} ({entera[0][1]:.0%}) | {len(cajas)} objetos detectados")

    with open(os.path.join(OUT, "resultados.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["imagen", "objeto", "x", "y", "w", "h", "clase1", "conf1", "clase2", "conf2", "clase3", "conf3"])
        w.writerows(filas)
    print("\nDetalle en resultados/resultados.csv y fotos anotadas en resultados/.")
    print("Ojo: el modelo solo conoce 19 géneros (casi todos marinos). Cualquier cosa que le enseñes, incluidas "
          "Acutodesmus y Chlorella, la llamará como uno de esos 19, y la confianza alta no garantiza que acierte.")


if __name__ == "__main__":
    main()
