"""Detector de objetos candidatos: el mismo que usa "Capture Photo" en el equipo.
Lo comparten la app y las pruebas locales, así que se mide exactamente lo que corre en la Raspberry."""
import cv2


def detectar(bgr, area_min=0.0005, area_max=0.01):
    """Cajas (x, y, w, h) de los objetos de una imagen BGR. Las áreas son fracción del área de la imagen."""
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
            cajas.append(cv2.boundingRect(c))
    return cajas
