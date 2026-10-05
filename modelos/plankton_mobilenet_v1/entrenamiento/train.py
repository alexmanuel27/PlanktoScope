import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.preprocessing.image import ImageDataGenerator
import json
import os

# ================= CONFIG =================
IMG_SIZE = 224
BATCH_SIZE = 32
EPOCHS = 20

DATASET_DIR = "dataset_pm"
TRAIN_DIR = os.path.join(DATASET_DIR, "training")
VAL_DIR = os.path.join(DATASET_DIR, "validation")

# ================= DATA GENERATORS =================
train_datagen = ImageDataGenerator(
    rescale=1.0 / 255.0,
    rotation_range=20,
    zoom_range=0.2,
    width_shift_range=0.1,
    height_shift_range=0.1,
    horizontal_flip=True,
    fill_mode="nearest"
)

val_datagen = ImageDataGenerator(
    rescale=1.0 / 255.0
)

# ================= DATASETS =================
train_ds = train_datagen.flow_from_directory(
    TRAIN_DIR,
    target_size=(IMG_SIZE, IMG_SIZE),
    batch_size=BATCH_SIZE,
    class_mode="categorical",
    shuffle=True
)

val_ds = val_datagen.flow_from_directory(
    VAL_DIR,
    target_size=(IMG_SIZE, IMG_SIZE),
    batch_size=BATCH_SIZE,
    class_mode="categorical",
    shuffle=False
)

# ================= CLASSES =================
class_indices = train_ds.class_indices
num_classes = train_ds.num_classes

print("\n===== CLASES DETECTADAS =====")
for name, idx in class_indices.items():
    print(f"{idx}: {name}")

# Guardar labels.json (OBLIGATORIO)
with open("labels.json", "w") as f:
    json.dump(class_indices, f, indent=2)

print("\nlabels.json guardado correctamente")

# ================= MODEL =================
base_model = MobileNetV2(
    input_shape=(IMG_SIZE, IMG_SIZE, 3),
    include_top=False,
    weights="imagenet"
)

base_model.trainable = False  # Transfer learning puro

model = models.Sequential([
    base_model,
    layers.GlobalAveragePooling2D(),
    layers.Dense(256, activation="relu"),
    layers.Dropout(0.4),
    layers.Dense(num_classes, activation="softmax")
])

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
    loss="categorical_crossentropy",
    metrics=["accuracy"]
)

model.summary()

# ================= TRAIN =================
history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS
)

# ================= SAVE =================
model.save("plankton_mobilenet_v1.h5")

print("\nModelo guardado como plankton_mobilenet_v1.h5")
print("Entrenamiento finalizado correctamente")
