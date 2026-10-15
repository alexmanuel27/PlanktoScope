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

# Paths
MODEL_PATH = os.path.join(BASE_DIR, "plankton.tflite")
LABELS_PATH = os.path.join(BASE_DIR, "labels.json")
IMG_SIZE = 224

# Load labels once
with open(LABELS_PATH, "r") as f:
    class_indices = json.load(f)

# Reverse index -> label
labels = {v: k for k, v in class_indices.items()}

# Load model once
interpreter = Interpreter(MODEL_PATH)
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()


def probabilidades(img):
    """img: PIL.Image. Vector de probabilidades, una por clase (orden de labels.json)."""
    img = img.convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    x = np.expand_dims(np.array(img, dtype=np.float32) / 255.0, axis=0)
    interpreter.set_tensor(input_details[0]["index"], x)
    interpreter.invoke()
    return interpreter.get_tensor(output_details[0]["index"])[0]


def classify_image(image_path: str) -> dict:
    """{"label": str, "confidence": float en %} de la clase más probable."""
    p = probabilidades(Image.open(image_path))
    k = int(np.argmax(p))
    return {"label": labels[k], "confidence": round(float(p[k]) * 100, 2)}
