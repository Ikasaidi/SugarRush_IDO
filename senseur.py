import pigpio
import time

# Connexions
# VCC   5V
# Trig  GPIO 19
# Echo  GPIO 26
# Gnd   GND

### Si il est en dessous de 9  il s'arrete 
## filtrer les zeros 

TRIG = 19
ECHO = 26

pi = pigpio.pi()

pi.set_mode(TRIG, pigpio.OUTPUT)
pi.set_mode(ECHO, pigpio.INPUT)

try:
    while True:
        
        # Envoyer un son
        pi.write(TRIG, 1)
        time.sleep(0.00001)
        pi.write(TRIG, 0)

        # Attendre l'echo
        debut = time.time()
        while pi.read(ECHO) == 0:
            # Break si on attend le debut de l'echo plus que 1 seconde
            if time.time() - debut > 1: 
                break

        # Echo arrive
        echo = time.time()
        while pi.read(ECHO) == 1:
            # Break si on attend la fin de l'écho plus que 1 seconde
            if time.time() - echo > 1: 
                break

        # Duree de l'echo
        duree = time.time() - echo

        # Calculer la distance
        distance = (duree * 34300) / 2
        if distance is not None:
            print(distance)
        else:
            print("erreur")

except KeyboardInterrupt:
    pi.stop()
