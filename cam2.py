import cv2
import numpy as np
from pyzbar.pyzbar import decode

cap = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)


while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera error")
        break

    decoded_objects = decode(frame)

    for obj in decoded_objects:
        qr_data = obj.data.decode("utf-8")
        print("QR Code:", qr_data)

        points = obj.polygon
        pts = np.array([(p.x, p.y) for p in points], np.int32)
        cv2.polylines(frame, [pts], True, (0, 255, 0), 2)

        cv2.putText(
            frame,
            qr_data,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

    cv2.imshow("QR Scanner", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
