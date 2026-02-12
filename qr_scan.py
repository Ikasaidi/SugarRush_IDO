from picamera2 import Picamera2
from pyzbar.pyzbar import decode
import time

picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (640, 480), "format": "RGB888"})
picam2.configure(config)
picam2.start()

time.sleep(1)

print("###QR scanner ready. Show a QR code to the camera.")

last = None

try:
    while True:
        frame = picam2.capture_array()  # numpy RGB image
        decoded = decode(frame)

        for obj in decoded:
            data = obj.data.decode("utf-8")
            if data != last:   # évite spam
                print("📦 QR:", data)
                last = data

        time.sleep(0.1)

except KeyboardInterrupt:
    pass
finally:
    picam2.stop()
    print("Bye")

