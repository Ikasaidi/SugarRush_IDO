from picamera2 import Picamera2
import time

# Initialisation de la caméra
picam2 = Picamera2()

# Configurer la caméra pour la prise de photo
picam2.configure(picam2.create_still_configuration())

# Capture de l'image et enregistrement
picam2.start_preview()
time.sleep(2)  # Laisser à la caméra le temps de s'ajuster
picam2.capture_file('/home/pi/photo.jpg')  # Sauvegarder l'image sur le bureau
picam2.stop_preview()

print("Photo prise et enregistrée !")
