import tensorflow as tf
import numpy as np
import cv2
import sys

IMG_SIZE = 224
MODEL_PATH = "plankton_mobilenet_v1.tflite"

interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

class_names = list(sorted([
    "Ceratium",
    "Chaetoceros",
    "Nitzschia",
    "Noctiluca",
    "Thalassiosira"
]))

img = cv2.imread(sys.argv[1])
img = cv2.resize(img, (IMG_SIZE, IMG_SIZE))
img = img / 255.0
img = np.expand_dims(img, axis=0).astype(np.float32)

interpreter.set_tensor(input_details[0]['index'], img)
interpreter.invoke()

pred = interpreter.get_tensor(output_details[0]['index'])[0]
idx = np.argmax(pred)

print("Predicción:", class_names[idx])
print("Confidence:", round(pred[idx]*100, 2), "%")
