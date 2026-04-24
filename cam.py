from picamera2 import Picamera2
import time

picam2 = Picamera2()

# Configuration photo
config = picam2.create_still_configuration()
picam2.configure(config)

picam2.start()
time.sleep(2)   # temps pour l’auto-exposition

picam2.capture_file("/home/pi/photo1.jpg")

picam2.stop()

print("Photo prise et enregistrée !")
