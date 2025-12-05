from picamera2 import Picamera2
print("Iniciando cámara...")
cam = Picamera2()
cam.start()
print("¡Cámara iniciada correctamente!")
cam.stop()
