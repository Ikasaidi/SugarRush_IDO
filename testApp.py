# ---------------------------
# IMPORTS
# ---------------------------
import pigpio
import time
import vlc
import threading
from flask import Flask, jsonify, request
import datetime
import socket
from statistics import median

# ---------------------------
# CONFIG
# ---------------------------
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

OPEN_DURATION = 10  # seconds
sensor_lock = threading.Lock()
sensor2_lock = threading.Lock()

# ---------------------------
# INIT pigpio
# ---------------------------
pi = pigpio.pi()
if not pi.connected:
    print("Erreur de connexion à pigpio")
    exit(1)

pi.set_mode(gate01, pigpio.OUTPUT)
pi.set_PWM_frequency(gate01, FREQ)
pi.set_PWM_range(gate01, 100)

pi.set_mode(gate02, pigpio.OUTPUT)
pi.set_PWM_frequency(gate02, FREQ)
pi.set_PWM_range(gate02, 100)

#GATE 01
pi.set_mode(TRIG, pigpio.OUTPUT)
pi.set_mode(ECHO, pigpio.INPUT)
pi.write(TRIG, 0)
time.sleep(0.05)

#GATE 02
TRIG2 = 5
ECHO2 = 6

pi.set_mode(TRIG2, pigpio.OUTPUT)
pi.set_mode(ECHO2, pigpio.INPUT)
pi.write(TRIG2, 0)


# ---------------------------
# LED & SOUND
# ---------------------------
R, G = 3, 2
pi.set_mode(R, pigpio.OUTPUT)
pi.set_mode(G, pigpio.OUTPUT)

player = vlc.MediaPlayer("/home/pi/SugarRush_IDO/son2.mp3")

# ---------------------------
# STATE MANAGEMENT
# ---------------------------
state = {
    "distance_cm": None,
    "train_present": False,
    "below_count": 0,
    "above_count": 0,
    "last_change_time": None,
    "gate_state": "closed",
    "station2_detected": False,
    "station2_time": None,
}

lock = threading.Lock()
blink_thread = None
stop_blink = threading.Event()
auto_close_timer = None   # Pour gérer la fermeture automatique

# ---------------------------
# DISTANCE
# ---------------------------
def read_distance_cm():
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

    if distance <= 0 or distance < MIN_CM or distance > MAX_CM:
        return None
    return distance

def read_distance_cm_2():
    with sensor2_lock:
        pi.write(TRIG2, 1)
        time.sleep(0.00001)
        pi.write(TRIG2, 0)

        start_wait = time.time()
        while pi.read(ECHO2) == 0:
            if time.time() - start_wait > TIMEOUT_S:
                return None

        echo_start = time.time()
        while pi.read(ECHO2) == 1:
            if time.time() - echo_start > TIMEOUT_S:
                return None

        echo_end = time.time()

        duration = echo_end - echo_start
        distance = (duration * 34300) / 2

        if distance <= 0 or distance < MIN_CM or distance > MAX_CM:
            return None

        return distance

def read_filtered_cm():
    with sensor_lock:
        vals = []
        for _ in range(NB_ECH):
            d = read_distance_cm()
            if d is not None:
                vals.append(d)
            time.sleep(0.02)
    return median(vals) if vals else None

def read_filtered_cm_2():
    vals = []

    for _ in range(NB_ECH):
        d = read_distance_cm_2()
        if d is not None:
            vals.append(d)
        time.sleep(0.02)

    if not vals:
        return None

    return median(vals)

# ---------------------------
# SON
# ---------------------------
def play_sound():
    player.stop()          # stop le son actuel
    time.sleep(0.1)        # petit délai pour éviter bug VLC
    player.play()          # relance depuis le début

# ---------------------------
# CLIGNOTEMENT ROUGE
# ---------------------------
def blink_red():
    while not stop_blink.is_set():
        pi.write(R, 1)
        time.sleep(0.25)
        pi.write(R, 0)
        time.sleep(0.25)

def start_blinking():
    global blink_thread
    stop_blink.clear()
    if blink_thread is None or not blink_thread.is_alive():
        blink_thread = threading.Thread(target=blink_red, daemon=True)
        blink_thread.start()

def stop_blinking():
    stop_blink.set()
    pi.write(R, 0)

# ---------------------------
# GATES (ILS SONT SWITCHED/MIXED)
# ---------------------------

# open_gates
def close_gates():
    """ Fermeture des gates + Rouge clignotant """
    global auto_close_timer

    # Annuler le timer si il existe
    if auto_close_timer and auto_close_timer.is_alive():
        auto_close_timer.cancel()

    pi.set_PWM_dutycycle(gate01, closed_gates_pwm_01)
    pi.set_PWM_dutycycle(gate02, closed_gates_pwm_02)


    stop_blinking()            # Arrêt du rouge clignotant
    pi.write(R, 0)
    pi.write(G, 1)             # Vert fixe

    with lock:
        state["gate_state"] = "closed"

    print("🟢GATES OPEN🟢")


# closed_gates
def open_gates():
    """ Fermeture des gates pour 10 secondes seulement """
    global auto_close_timer

    pi.set_PWM_dutycycle(gate01, open_gates_pwm_01)
    pi.set_PWM_dutycycle(gate02, open_gates_pwm_02)

    stop_blinking()
    start_blinking()           # Rouge clignote

    pi.write(G, 0)             # Vert éteint

    with lock:
        state["gate_state"] = "open"

    print("🔴GATES CLOSED🔴")

    # Ouverture automatique après 10 secondes
    if auto_close_timer and auto_close_timer.is_alive():
        auto_close_timer.cancel()

    auto_close_timer = threading.Timer(OPEN_DURATION, close_gates)
    auto_close_timer.daemon = True
    auto_close_timer.start()

    # Son d'ouverture
    threading.Thread(target=play_sound, daemon=True).start()


# ---------------------------
# SENSOR LOOP
# ---------------------------
def sensor_loop():
    below_count = 0
    above_count = 0

    while True:
        dist = read_filtered_cm()
        if dist is None:
            time.sleep(0.1)
            continue

        dist1 = read_filtered_cm()

        print(f"{dist:.1f} cm")

        if dist < SEUIL_CM:
            below_count += 1
            above_count = 0
        else:
            above_count += 1
            below_count = 0

        # CHAQUE détection valide relance tout
        if below_count >= CONFIRM_N:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print(" TRAIN DETECTED → CLOSE GATES + SOUND ")
            open_gates()

            with lock:
                state["last_change_time"] = current_time
                state["train_present"] = True

            # reset pour permettre redétection
            below_count = 0

        # Zone libre
        if above_count >= CONFIRM_N:
            with lock:
                state["train_present"] = False

        with lock:
            state["distance_cm"] = round(dist, 1)
            state["below_count"] = below_count
            state["above_count"] = above_count

        time.sleep(0.1)

def sensor_loop_station2():
    below_count = 0
    above_count = 0
    last_state = False
    dist2 = read_filtered_cm_2()

    while True:
        dist = read_filtered_cm_2()

        if dist is None:
            time.sleep(0.1)
            continue

        if dist < SEUIL_CM:
            below_count += 1
            above_count = 0
        else:
            above_count += 1
            below_count = 0

        # 🚆 Détection ARRIVÉE station 2
        if below_count >= CONFIRM_N and not last_state:
            last_state = True
            current_time = datetime.datetime.now().strftime("%H:%M:%S")

            print("🚆 TRAIN ARRIVÉ À LA 2e GARE")

            with lock:
                state["station2_detected"] = True
                state["station2_time"] = current_time

        # 🚆 SORTIE station 2
        if above_count >= CONFIRM_N and last_state:
            last_state = False

            with lock:
                state["station2_detected"] = False

        time.sleep(0.1)

# ---------------------------
# FLASK API
# ---------------------------
app = Flask(__name__)

@app.route("/status", methods=["GET"])
def get_status():
    with lock:
        return jsonify(state)

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

# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":
    print(">>> MAIN STARTED")

    # DEFAULT STATE : OPEN GATES + GREEN LIGHT
    #open_gates
    close_gates()

    t = threading.Thread(target=sensor_loop, daemon=True)
    t.start()

    t2 = threading.Thread(target=sensor_loop_station2, daemon=True)
    t2.start()

    app.run(host="0.0.0.0", port=3004)