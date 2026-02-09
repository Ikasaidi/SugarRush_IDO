import pigpio
from time import sleep

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

# Valeurs de PWM pour ouvrir et fermer les barrières
open_gates_pwm_01 = 12.5  # Pour gate01
open_gates_pwm_02 = 10    # Pour gate02
closed_gates_pwm_01 = 7.5
closed_gates_pwm_02 = 5   # Inversée pour gate02

while True:
    # Fermer les deux barrières (gate01 et gate02)
    pi.set_PWM_dutycycle(gate01, closed_gates_pwm_01)
    pi.set_PWM_dutycycle(gate02, closed_gates_pwm_02)
    sleep(2)  # Attendre 2 secondes

    # Ouvrir les deux barrières (gate01 et gate02)
    pi.set_PWM_dutycycle(gate01, open_gates_pwm_01)
    pi.set_PWM_dutycycle(gate02, open_gates_pwm_02)
    sleep(2)  # Attendre 2 secondes
