import json
import numpy as np
from PIL import Image
try:
    from ai_edge_litert.interpreter import Interpreter
except ImportError:  # en el Mac de pruebas el mismo intérprete viene dentro de TensorFlow
    import tensorflow as tf
    Interpreter = tf.lite.Interpreter
import os

# Ruta absoluta al directorio actual
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Dos formatos de modelo:
#  - nuevo (src/ml/entrenar.py): modelo.tflite + modelo.json (clases, lado, preprocesado a_cuadrado, entrada 0-255)
#  - antiguo: plankton.tflite + labels.json (224, NEAREST, /255)
META_PATH = os.path.join(BASE_DIR, "modelo.json")
META = json.load(open(META_PATH)) if os.path.exists(META_PATH) else None
if META:
    from ml.preprocesado import a_cuadrado
    MODEL_PATH = os.path.join(BASE_DIR, "modelo.tflite")
    labels = dict(enumerate(META["clases"]))
    IMG_SIZE = META["lado"]
else:
    MODEL_PATH = os.path.join(BASE_DIR, "plankton.tflite")
    with open(os.path.join(BASE_DIR, "labels.json"), "r") as f:
        class_indices = json.load(f)
    labels = {v: k for k, v in class_indices.items()}
    IMG_SIZE = 224

# Load model once
interpreter = Interpreter(MODEL_PATH)
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()


def probabilidades(img):
    """img: PIL.Image. Vector de probabilidades, una por clase (orden de labels.json)."""
    # NEAREST como keras load_img en el entrenamiento: con la bicúbica por defecto de PIL la exactitud en el
    # subconjunto limpio baja de 0,84 a 0,74 (modelos/plankton_mobilenet_v1/calibracion_2026-11-01)
    if META:   # mismo preprocesado que en el entrenamiento: completar a cuadrado sin deformar, 0-255
        x = a_cuadrado(np.asarray(img.convert("RGB")), IMG_SIZE).astype(np.float32)[None]
    else:
        img = img.convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.NEAREST)
        x = np.expand_dims(np.array(img, dtype=np.float32) / 255.0, axis=0)
    interpreter.set_tensor(input_details[0]["index"], x)
    interpreter.invoke()
    return interpreter.get_tensor(output_details[0]["index"])[0]


def classify_image(image_path: str) -> dict:
    """{"label": str, "confidence": float en %} de la clase más probable."""
    p = probabilidades(Image.open(image_path))
    k = int(np.argmax(p))
    return {"label": labels[k], "confidence": round(float(p[k]) * 100, 2)}
