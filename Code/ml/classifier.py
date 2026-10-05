import json
import numpy as np
from PIL import Image
from ai_edge_litert.interpreter import Interpreter
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


def classify_image(image_path: str) -> dict:
    """
    Classify a plankton image.

    Returns:
        {
            "label": str,
            "confidence": float
        }
    """

    # Load and preprocess image
    img = Image.open(image_path).convert("RGB")
    img = img.resize((IMG_SIZE, IMG_SIZE))
    img_array = np.array(img, dtype=np.float32) / 255.0
    img_array = np.expand_dims(img_array, axis=0)

    # Run inference
    interpreter.set_tensor(input_details[0]["index"], img_array)
    interpreter.invoke()

    predictions = interpreter.get_tensor(output_details[0]["index"])[0]

    class_id = int(np.argmax(predictions))
    confidence = float(predictions[class_id])

    return {
        "label": labels[class_id],
        "confidence": round(confidence * 100, 2)
    }
