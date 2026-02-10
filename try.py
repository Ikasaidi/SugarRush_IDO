import pigpio
import time
import datetime
from statistics import median


### Conditions
#### Quand 
TRIG = 19
ECHO = 26

SEUIL_CM = 9.0           # en dessous => train détecté
MAX_CM = 400.0           # limites réalistes HC-SR04-ish
MIN_CM = 2.0
TIMEOUT_S = 0.03         # 30 ms ~ > 500 cm (large)
NB_ECH = 5               # échantillons pour médiane
CONFIRM_N = 3            # nb de lectures consécutives pour confirmer
gate01 = 17
gate02 = 11
FREQ = 50  # Fréquence en Hz de la période

pi = pigpio.pi()
pi.set_mode(gate01, pigpio.OUTPUT)
pi.set_PWM_frequency(gate01, FREQ)
pi.set_PWM_range(gate01, 100)

pi.set_mode(gate02, pigpio.OUTPUT)
pi.set_PWM_frequency(gate02, FREQ)
pi.set_PWM_range(gate02, 100)

pi.set_mode(TRIG, pigpio.OUTPUT)
pi.set_mode(ECHO, pigpio.INPUT)

pi.write(TRIG, 0)
time.sleep(0.05)


# Valeurs de PWM pour ouvrir et fermer les barrières
open_gates_pwm_01 = 12.5  # Pour gate01
open_gates_pwm_02 = 10    # Pour gate02
closed_gates_pwm_01 = 7.5
closed_gates_pwm_02 = 5   # Inversée pour gate02

def read_distance_cm():
    """Retourne distance (cm) ou None si invalide/timeout."""
    # pulse TRIG 10us
    pi.write(TRIG, 1)
    time.sleep(0.00001)
    pi.write(TRIG, 0)

    # attendre front montant (ECHO passe à 1)
    start_wait = time.time()
    while pi.read(ECHO) == 0:
        if time.time() - start_wait > TIMEOUT_S:
            return None

    echo_start = time.time()

    # attendre front descendant (ECHO revient à 0)
    while pi.read(ECHO) == 1:
        if time.time() - echo_start > TIMEOUT_S:
            return None

    echo_end = time.time()

    # durée du signal ECHO
    duration = echo_end - echo_start

    # distance en cm (vitesse son ~34300 cm/s)
    distance = (duration * 34300) / 2

    # filtrage valeurs absurdes / zéros
    if distance <= 0:
        return None
    if distance < MIN_CM or distance > MAX_CM:
        return None

    return distance

def read_filtered_cm():
    """Médiane sur NB_ECH lectures valides."""
    vals = []
    for _ in range(NB_ECH):
        d = read_distance_cm()
        if d is not None:
            vals.append(d)
        time.sleep(0.02)  # petit délai entre mesures

    if not vals:
        return None
    return median(vals)

try:
    train_present = False
    below_count = 0
    above_count = 0

    while True:
        dist = read_filtered_cm()

        if dist is None:
            time.sleep(0.1)
            continue

        print(f"{dist:.1f} cm")

        # logique de détection avec anti-bruit
        if dist < SEUIL_CM:
            below_count += 1
            above_count = 0
        else:
            above_count += 1
            below_count = 0

        # Train détecté
        if not train_present and below_count >= CONFIRM_N:
            train_present = True
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print("✅ Train détecté (proche)")
            print(f"Current time: {current_time}")

            pi.set_PWM_dutycycle(gate01, closed_gates_pwm_01)
            pi.set_PWM_dutycycle(gate02, closed_gates_pwm_02)
            
        # Train parti (on met un petit hystérésis simple)
        if train_present and above_count >= CONFIRM_N:
            train_present = False

            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print("✅ Train parti (loin)")

            pi.set_PWM_dutycycle(gate01, open_gates_pwm_01)
            pi.set_PWM_dutycycle(gate02, open_gates_pwm_02)
            
        time.sleep(0.1)

except KeyboardInterrupt:
    pass
finally:
    pi.stop()
