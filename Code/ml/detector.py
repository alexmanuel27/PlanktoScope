"""Detector de objetos candidatos: el mismo que usa "Capture Photo" en el equipo.
Lo comparten la app y las pruebas locales, así que se mide exactamente lo que corre en la Raspberry."""
import math

import cv2
import numpy as np


def detectar(bgr, area_min=0.0005, area_max=0.01):
    """Cajas (x, y, w, h) de los objetos de una imagen BGR. Las áreas son fracción del área de la imagen."""
    return [caja for caja, _ in detectar_objetos(bgr, area_min, area_max)]


def detectar_objetos(bgr, area_min=0.0005, area_max=0.01):
    """[(caja (x, y, w, h), contorno)] de los objetos de una imagen BGR. Las áreas son fracción del área de la imagen."""
    H, W = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 3)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=2)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cajas = []
    for c in cnts:
        a = cv2.contourArea(c)
        if area_min * H * W <= a <= area_max * H * W and cv2.arcLength(c, True) > 0:
            cajas.append((cv2.boundingRect(c), c))
    return cajas


def estimar_fondo(bgr):
    """Fondo de la propia imagen (iluminación) cuando no hay foto en blanco: mediana muy grande sobre la imagen
    reducida a 1/8, que borra los objetos de hasta ~100 px y deja la variación lenta de la luz."""
    H, W = bgr.shape[:2]
    peq = cv2.medianBlur(cv2.resize(bgr, (W // 8, H // 8), interpolation=cv2.INTER_AREA), 15)
    return cv2.resize(peq, (W, H), interpolation=cv2.INTER_LINEAR)


def corregir_fondo(bgr, fondo=None):
    """Corrección de campo plano como el segmentador del PlanktoScope: divide la imagen entre el fondo y la
    reescala al brillo medio del fondo. Con fondo = foto en blanco (agua limpia) también desaparece la suciedad fija
    del capilar y del sensor; sin él solo se corrige la iluminación desigual."""
    if fondo is None or fondo.shape != bgr.shape:
        fondo = estimar_fondo(bgr)
    f = np.maximum(fondo.astype(np.float32), 1.0)
    return np.clip(bgr.astype(np.float32) / f * f.mean(axis=(0, 1)), 0, 255).astype(np.uint8)


def medidas_objeto(bgr, contorno, um_por_px=0.0):
    """Forma y color de un objeto, con los nombres en castellano de las medidas del segmentador del PlanktoScope.
    Longitudes en píxeles y, si um_por_px > 0, también en µm."""
    x, y, w, h = cv2.boundingRect(contorno)
    mascara = np.zeros((h, w), np.uint8)
    cv2.drawContours(mascara, [contorno - [x, y]], -1, 255, -1)
    area = float(np.count_nonzero(mascara))
    perimetro = cv2.arcLength(contorno, True)
    if len(contorno) >= 5:
        (_, _), (a, b), _ = cv2.fitEllipse(contorno)
    else:
        (_, _), (a, b), _ = cv2.minAreaRect(contorno)
    mayor, menor = max(a, b), max(min(a, b), 1e-6)
    casco = cv2.contourArea(cv2.convexHull(contorno))
    hsv = cv2.cvtColor(bgr[y:y + h, x:x + w], cv2.COLOR_BGR2HSV)[mascara > 0].astype(np.float32)
    m = {"area_px": area,
         "diametro_eq_px": math.sqrt(4 * area / math.pi),
         "eje_mayor_px": mayor, "eje_menor_px": menor,
         "alargamiento": mayor / menor,
         "circularidad": 4 * math.pi * area / perimetro ** 2 if perimetro else 0.0,
         "solidez": cv2.contourArea(contorno) / casco if casco else 0.0,  # mismo polígono en los dos: ≤ 1
         "tono_media": hsv[:, 0].mean(), "tono_std": hsv[:, 0].std(),
         "saturacion_media": hsv[:, 1].mean(), "saturacion_std": hsv[:, 1].std(),
         "brillo_media": hsv[:, 2].mean(), "brillo_std": hsv[:, 2].std()}
    if um_por_px > 0:
        m.update(area_um2=area * um_por_px ** 2, diametro_eq_um=m["diametro_eq_px"] * um_por_px,
                 eje_mayor_um=mayor * um_por_px, eje_menor_um=menor * um_por_px)
    return {k: round(float(v), 3) for k, v in m.items()}  # float de Python: numpy no pasa por jsonify


def limites_area(um_por_px, tamano_min_um, tamano_max_um, alto, ancho, por_defecto=(0.0005, 0.01)):
    """Áreas mínima y máxima (fracción de la imagen) a partir de diámetros en µm; sin calibrar, los valores por defecto."""
    if um_por_px <= 0:
        return por_defecto
    a = lambda d_um: math.pi * (d_um / um_por_px / 2) ** 2 / (alto * ancho)
    return a(tamano_min_um), a(tamano_max_um)
