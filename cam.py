import cv2
from pyzbar.pyzbar import decode

# Ouvre la caméra (index 0 pour la première caméra connectée)
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()  # Capture une image
    if not ret:
        break

    # Décodage des QR codes présents dans l'image
    decoded_objects = decode(frame)

    for obj in decoded_objects:
        # Dessiner un rectangle autour du QR code
        points = obj.polygon
        if len(points) == 4:
            pts = points
        else:
            pts = cv2.convexHull(np.array([point for point in points], dtype=np.float32))

        # Dessine le contour
        cv2.polylines(frame, [np.int32(pts)], True, (0, 0, 255), 3)

        # Afficher les données du QR code
        qr_data = obj.data.decode('utf-8')
        print(f"QR Code: {qr_data}")

        # Affichage du texte sur l'image
        cv2.putText(frame, qr_data, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    # Afficher l'image
    cv2.imshow("QR Code Scanner", frame)

    # Quitter avec 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Libérer les ressources
cap.release()
cv2.destroyAllWindows()

