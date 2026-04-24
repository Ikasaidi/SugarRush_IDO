from flask import Flask, jsonify
from picamera2 import Picamera2
from pyzbar.pyzbar import decode
import threading
import time
 
app = Flask(__name__)
 

last_qr_data = None
qr_lock = threading.Lock()
 
# Camera setup
picam2 = Picamera2()

config = picam2.create_still_configuration(
    main={"size": (640, 480), "format": "RGB888"}
)

picam2.configure(config)
picam2.start()
time.sleep(1)
 
print("QR scanner ready.")

def scan_loop():
    global last_qr_data
    last_seen = None
 
    while True:
        frame = picam2.capture_array()
        decoded = decode(frame)
        for obj in decoded:

            data = obj.data.decode("utf-8")
            if data != last_seen:
                print("QR:", data)
                with qr_lock:
                    last_qr_data = data
                last_seen = data
        time.sleep(0.1)
 
 
# scanning in background
scanner_thread = threading.Thread(target=scan_loop)
scanner_thread.daemon = True
scanner_thread.start()
 
@app.route("/qr-status", methods=["GET"])
def qr_status():

    with qr_lock:
        if last_qr_data:
            return jsonify({
                "status": "scanned",
                "data": last_qr_data
            })
 
    return jsonify({
        "status": "idle"
    })
 
 
@app.route("/qr-clear", methods=["POST"])
def qr_clear():
    global last_qr_data
    with qr_lock:
        last_qr_data = None
 
    return jsonify({
        "status": "cleared"
    })
 
 
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False
    )
 