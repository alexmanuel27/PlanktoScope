import tensorflow as tf

model = tf.keras.models.load_model("plankton_mobilenet_v1.h5")

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]

tflite_model = converter.convert()

with open("plankton_mobilenet_v1.tflite", "wb") as f:
    f.write(tflite_model)

print("Modelo exportado: plankton_mobilenet_v1.tflite")
