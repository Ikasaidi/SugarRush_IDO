import pigpio
import time

R, G = 2, 3  # Définition des broches pour les LED

pi = pigpio.pi()  # Connexion avec le GPIO
pi.set_mode(R, pigpio.OUTPUT)
pi.set_mode(G, pigpio.OUTPUT)

# Allumer la LED verte et laisser allumée
pi.write(G, 1)  # Allume la LED verte
pi.write(R, 0)  # Éteindre la LED rouge

# Clignotement de la LED rouge
try:
    while True:
        # Allumer R (rouge)
        pi.write(R, 1)
        time.sleep(0.5)  # Clignotement, ici 0.5 seconde

        # Éteindre R (rouge)
        pi.write(R, 0)
        time.sleep(0.5)  # Clignotement, ici 0.5 seconde

except KeyboardInterrupt:
    # Arrêter proprement en cas d'interruption (Ctrl+C)
    pi.write(R, 0)
    pi.write(G, 0)
    pi.stop()