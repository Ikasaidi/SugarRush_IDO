import RPi.GPIO as GPIO
import time

RELAY_PIN = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)

print("Tape :")
print("  o = ouvrir le solénoïde")
print("  f = fermer le solénoïde")
print("  q = quitter")

try:
    while True:
        cmd = input("> ")

        if cmd == "o":
            GPIO.output(RELAY_PIN, GPIO.HIGH)  # ouvre
            print("🔓 Solénoïde ouvert")

        elif cmd == "f":
            GPIO.output(RELAY_PIN, GPIO.LOW)   # ferme
            print("🔒 Solénoïde fermé")

        elif cmd == "q":
            break

        else:
            print("Commande inconnue")

finally:
    GPIO.cleanup()
    print("Bye 👋")
