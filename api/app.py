from flask import Flask, jsonify, request
import socket
import threading
import time
import datetime
from statistics import median
import pigpio


# -----------------------
# CONFIG GPIO / CAPTEUR
# -----------------------
TRIG = 19
ECHO = 26

SEUIL_CM = 9.0
MAX_CM = 400.0
MIN_CM = 2.0
TIMEOUT_S = 0.03
NB_ECH = 5
CONFIRM_N = 3

gate01 = 17
gate02 = 11
FREQ = 50

open_gates_pwm_01 = 12.5
open_gates_pwm_02 = 10
closed_gates_pwm_01 = 7.5
closed_gates_pwm_02 = 5


pi = pigpio.pi()


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


state = {
    "distance_cm": None,
    "train_present": False,
    "below_count": 0,
    "above_count": 0,
    "last_change_time": None,
    "gate_state": None,  # "open" / "closed"
}

lock = threading.Lock()

def read_distance_cm():
    """Retourne distance (cm) ou None si invalide/timeout."""
    pi.write(TRIG, 1)
    time.sleep(0.00001)
    pi.write(TRIG, 0)

    start_wait = time.time()
    while pi.read(ECHO) == 0:
        if time.time() - start_wait > TIMEOUT_S:
            return None

    echo_start = time.time()

    while pi.read(ECHO) == 1:
        if time.time() - echo_start > TIMEOUT_S:
            return None

    echo_end = time.time()

    duration = echo_end - echo_start
    distance = (duration * 34300) / 2

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
        time.sleep(0.02)

    if not vals:
        return None
    return median(vals)

def close_gates():
    pi.set_PWM_dutycycle(gate01, closed_gates_pwm_01)
    pi.set_PWM_dutycycle(gate02, closed_gates_pwm_02)
    with lock:
        state["gate_state"] = "closed"

def open_gates():
    pi.set_PWM_dutycycle(gate01, open_gates_pwm_01)
    pi.set_PWM_dutycycle(gate02, open_gates_pwm_02)
    with lock:
        state["gate_state"] = "open"


def sensor_loop():
    train_present = False
    below_count = 0
    above_count = 0

    while True:
        dist = read_filtered_cm()
        if dist is None:
            time.sleep(0.1)
            continue

        print(f"{dist:.1f} cm")

        # logique de détection (inchangée)
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
            close_gates()


            with lock:
                state["last_change_time"] = current_time

        # Train parti
        if train_present and above_count >= CONFIRM_N:
            train_present = False
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print("✅ Train parti (loin)")
            print(f"Current time: {current_time}")
            open_gates()
          

            with lock:
                state["last_change_time"] = current_time

        # update state (pour l'API)
        with lock:
            state["distance_cm"] = round(dist, 1)
            state["train_present"] = train_present
            state["below_count"] = below_count
            state["above_count"] = above_count

        time.sleep(0.1)

# -----------------------
# FLASK API
# -----------------------
app = Flask(__name__)

@app.route("/info", methods=["GET"])
def info_hote():
    date = datetime.datetime.now()
    return jsonify({
        "hote": socket.gethostname(),
        "date": date.strftime("%Y-%m-%d, %H:%M:%S")
    })

@app.route("/status", methods=["GET"])
def get_status():
    with lock:
        return jsonify(state)

# Optionnel: forcer ouverture/fermeture manuellement (si tu veux)
@app.route("/gates", methods=["POST"])
def set_gates():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")

    if mode == "open":
        open_gates()
        return jsonify({"ok": True, "gate_state": "open"})
    elif mode == "closed":
        close_gates()
        return jsonify({"ok": True, "gate_state": "closed"})
    else:
        return jsonify({"error": "mode must be 'open' or 'closed'"}), 400

if __name__ == "__main__":
    print(">>> MAIN STARTED")

    t = threading.Thread(target=sensor_loop, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=3001)
    print(">>> STARTING FLASK")
