"""Preprocesado de un recorte para los clasificadores nuevos. Lo comparten el entrenamiento (src/ml/entrenar.py) y la
app, así que lo que ve el modelo en la Raspberry es exactamente lo que vio al entrenar."""
import cv2
import numpy as np


def a_cuadrado(img, lado=224):
    """Recorte RGB (o BGR, el orden se conserva) → lado×lado uint8, SIN deformar: se completa a cuadrado con el color
    mediano del borde (el fondo del capilar) y luego se escala. Así un cenobio alargado sigue siendo alargado."""
    h, w = img.shape[:2]
    s = max(h, w)
    borde = np.concatenate([img[0], img[-1], img[:, 0], img[:, -1]])
    lienzo = np.empty((s, s, 3), np.uint8)
    lienzo[:] = np.median(borde, axis=0).astype(np.uint8)
    y0, x0 = (s - h) // 2, (s - w) // 2
    lienzo[y0:y0 + h, x0:x0 + w] = img
    return cv2.resize(lienzo, (lado, lado), interpolation=cv2.INTER_AREA if s > lado else cv2.INTER_LINEAR)
