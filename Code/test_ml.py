#!/usr/bin/env python3
"""
Test script for plankton image classification.
Tests the classify_image function from ml.classifier.
"""
from flask import Flask, render_template, jsonify, send_file, Response, request
import time
import io
import os
import subprocess
import threading
import json
from datetime import datetime
from queue import Queue
from threading import Lock
import cv2
import numpy as np
import RPi.GPIO as GPIO

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False






import os
import sys
from datetime import datetime

# Asegurar que estamos en el directorio correcto
os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    from ml.classifier import classify_image
    print("✅ Classifier imported successfully")
except Exception as e:
    print(f"❌ Failed to import classifier: {e}")
    sys.exit(1)

# Crear carpeta samples si no existe
os.makedirs("samples", exist_ok=True)

# Ruta de prueba
test_image = "samples/photo_1765688364.jpg"

# Si no existe, crear una imagen de prueba simple
if not os.path.exists(test_image):
    print("📸 Creating test image...")
    import cv2
    import numpy as np
    # Crear una imagen negra de 640x480
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.imwrite(test_image, img)
    print(f"✅ Test image created: {test_image}")

# Probar la clasificación
print(f"\n🔍 Testing classification on: {test_image}")
print("-" * 50)

try:
    result = classify_image(test_image)
    print(f"✅ Classification successful!")
    print(f"   Label: {result['label']}")
    print(f"   Confidence: {result['confidence']:.2f}%")
except Exception as e:
    print(f"❌ Classification failed: {e}")
    import traceback
    traceback.print_exc()

print("\n🧪 Test completed.")
