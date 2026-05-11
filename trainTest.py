# ---------------------------
# IMPORTS
# ---------------------------

import pigpio
import time
import vlc
import threading
from flask import Flask, jsonify
import datetime
from statistics import median
import requests
import signal
import sys
import atexit

# ---------------------------
# CONFIG
# ---------------------------

TRIG = 19
ECHO = 26
TRIG2 = 5
ECHO2 = 6

SEUIL_CM = 9.0
MAX_CM = 400.0
MIN_CM = 2.0
TIMEOUT_S = 0.03
NB_ECH = 5
CONFIRM_N = 3

gate01 = 17
gate02 = 11
FREQ = 50

# BARRIÈRES FERMÉES
open_gates_pwm_01 = 12.5
open_gates_pwm_02 = 10

# BARRIÈRES OUVERTES
closed_gates_pwm_01 = 7.5
closed_gates_pwm_02 = 5

REMOTE_TRAIN_URL = "http://10.10.28.131/close_gates"

STOP_TIME = 60
IGNORE_AFTER_START = 60

# Le capteur doit être clair pendant 10 secondes continues
CLEAR_TIME_REQUIRED = 10

# ---------------------------
# GLOBAL STATE
# ---------------------------

lock = threading.Lock()
cycle_lock = threading.Lock()

cycle_running = False
program_running = True
cleanup_done = False

expected_station = "station_1"

ignore_station1_until = 0
ignore_station2_until = 0

train_running = False

# ---------------------------
# INIT pigpio
# ---------------------------

pi = pigpio.pi()

if not pi.connected:
    print("Erreur connexion pigpio")
    exit(1)

pi.set_mode(gate01, pigpio.OUTPUT)
pi.set_PWM_frequency(gate01, FREQ)
pi.set_PWM_range(gate01, 100)

pi.set_mode(gate02, pigpio.OUTPUT)
pi.set_PWM_frequency(gate02, FREQ)
pi.set_PWM_range(gate02, 100)

pi.set_mode(TRIG, pigpio.OUTPUT)
pi.set_mode(ECHO, pigpio.INPUT)

pi.set_mode(TRIG2, pigpio.OUTPUT)
pi.set_mode(ECHO2, pigpio.INPUT)

pi.write(TRIG, 0)
pi.write(TRIG2, 0)

time.sleep(0.05)

# ---------------------------
# LED
# ---------------------------

R, G = 3, 2

pi.set_mode(R, pigpio.OUTPUT)
pi.set_mode(G, pigpio.OUTPUT)

blink_thread = None
stop_blink = threading.Event()

# ---------------------------
# SOUND
# ---------------------------

sound_stop_event = threading.Event()
sound_thread = None
player = vlc.MediaPlayer("/home/pi/SugarRush_IDO/son2.mp3")

# ---------------------------
# STATE
# ---------------------------

state = {
    "distance_station1_cm": None,
    "distance_station2_cm": None,
    "expected_station": "station_1",
    "train_running": False,
    "cycle_running": False,
    "last_station_detected": None,
    "last_change_time": None,
}

# ---------------------------
# SENSOR LOCKS
# ---------------------------

sensor_lock = threading.Lock()
sensor2_lock = threading.Lock()

# ---------------------------
# DISTANCE FUNCTIONS
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

    distance = (echo_end - echo_start) * 34300 / 2

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

        distance = (echo_end - echo_start) * 34300 / 2

        if distance <= 0 or distance < MIN_CM or distance > MAX_CM:
            return None

        return distance


def read_filtered_cm():
    with sensor_lock:
        vals = [d for _ in range(NB_ECH) if (d := read_distance_cm()) is not None]
        time.sleep(0.02)

    return median(vals) if vals else None


def read_filtered_cm_2():
    vals = [d for _ in range(NB_ECH) if (d := read_distance_cm_2()) is not None]
    time.sleep(0.02)

    return median(vals) if vals else None

# ---------------------------
# SOUND LOOP
# ---------------------------

def sound_loop_worker():
    while not sound_stop_event.is_set():
        local_player = vlc.MediaPlayer("/home/pi/SugarRush_IDO/son2.mp3")
        local_player.play()

        time.sleep(0.3)

        while local_player.is_playing() and not sound_stop_event.is_set():
            time.sleep(0.1)

        local_player.stop()


def start_sound_loop():
    global sound_thread

    if sound_thread is not None and sound_thread.is_alive():
        return

    print("Musique ON")

    sound_stop_event.clear()

    sound_thread = threading.Thread(
        target=sound_loop_worker,
        daemon=True
    )

    sound_thread.start()


def stop_sound():
    print("Musique OFF")

    sound_stop_event.set()

    try:
        player.stop()
    except:
        pass

# ---------------------------
# LED BLINK
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
        blink_thread = threading.Thread(
            target=blink_red,
            daemon=True
        )

        blink_thread.start()


def stop_blinking():
    stop_blink.set()
    pi.write(R, 0)

# ---------------------------
# STATION 1 EFFECTS
# ---------------------------

def start_station1_effects():
    print("STATION 1 ON: barrières fermées + LED + son")

    # Barrières fermées
    pi.set_PWM_dutycycle(gate01, open_gates_pwm_01)
    pi.set_PWM_dutycycle(gate02, open_gates_pwm_02)

    # LED
    pi.write(G, 0)
    start_blinking()

    # Son
    start_sound_loop()


def stop_station1_effects():
    print("STATION 1 OFF: barrières ouvertes + LED OFF + son OFF")

    stop_sound()
    stop_blinking()

    pi.write(R, 0)
    pi.write(G, 1)

    # Barrières ouvertes
    pi.set_PWM_dutycycle(gate01, closed_gates_pwm_01)
    pi.set_PWM_dutycycle(gate02, closed_gates_pwm_02)

# ---------------------------
# TRAIN CONTROL
# ---------------------------

def send_train_toggle():
    try:
        response = requests.post(
            REMOTE_TRAIN_URL,
            timeout=2
        )

        print(f"POST train toggle → {response.status_code}")
        return True

    except requests.RequestException as e:
        print(f"Erreur POST train : {e}")
        return False


def start_train():
    global train_running

    if not train_running:
        print("🚆 TRAIN START")

        if send_train_toggle():
            train_running = True

            with lock:
                state["train_running"] = True


def stop_train():
    global train_running

    if train_running:
        print("🛑 TRAIN STOP")

        if send_train_toggle():
            train_running = False

            with lock:
                state["train_running"] = False

# ---------------------------
# WAIT UNTIL TRAIN CLEARS STATION 1
# ---------------------------

def wait_until_station1_clear():
    clear_start_time = None

    print("Attente que le train quitte vraiment le capteur station 1...")

    while True:
        dist = read_filtered_cm()

        if dist is None or dist >= SEUIL_CM:
            if clear_start_time is None:
                clear_start_time = time.time()

            elapsed_clear = time.time() - clear_start_time
            print(f"Station 1 clear depuis {elapsed_clear:.1f}s")

            if elapsed_clear >= CLEAR_TIME_REQUIRED:
                print("Train vraiment parti du capteur station 1")
                break

        else:
            clear_start_time = None
            print(f"Train encore détecté station 1: {dist:.1f} cm")

        time.sleep(0.2)

# ---------------------------
# TRAIN CYCLE
# ---------------------------

def handle_station_detection(station_name):
    global cycle_running
    global expected_station
    global ignore_station1_until
    global ignore_station2_until

    with cycle_lock:
        if cycle_running:
            print("Cycle déjà en cours")
            return

        cycle_running = True

    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"🚉 DETECTED : {station_name}")

        with lock:
            state["cycle_running"] = True
            state["last_station_detected"] = station_name
            state["last_change_time"] = now

        stop_train()

        if station_name == "station_1":
            start_station1_effects()

        print("Repos 1 minute...")
        time.sleep(STOP_TIME)

        start_train()

        if station_name == "station_1":
            print("Train redémarré, on garde barrières fermées + LED + son")

            wait_until_station1_clear()

            stop_station1_effects()

            expected_station = "station_2"
            ignore_station1_until = time.time() + IGNORE_AFTER_START

        else:
            expected_station = "station_1"
            ignore_station2_until = time.time() + IGNORE_AFTER_START

        with lock:
            state["expected_station"] = expected_station
            state["cycle_running"] = False

        print(f"Waiting : {expected_station}")

    finally:
        with cycle_lock:
            cycle_running = False

# ---------------------------
# SENSOR LOOP STATION 1
# ---------------------------

def sensor_loop_station1():
    below_count = 0

    while program_running:
        if expected_station != "station_1":
            time.sleep(0.2)
            continue

        if time.time() < ignore_station1_until:
            time.sleep(0.2)
            continue

        dist = read_filtered_cm()

        if dist is None:
            time.sleep(0.1)
            continue

        with lock:
            state["distance_station1_cm"] = round(dist, 1)

        print(f"Station1: {dist:.1f} cm")

        if dist < SEUIL_CM:
            below_count += 1
        else:
            below_count = 0

        if below_count >= CONFIRM_N:
            below_count = 0

            threading.Thread(
                target=handle_station_detection,
                args=("station_1",),
                daemon=True
            ).start()

        time.sleep(0.1)

# ---------------------------
# SENSOR LOOP STATION 2
# ---------------------------

def sensor_loop_station2():
    below_count = 0

    while program_running:
        if expected_station != "station_2":
            time.sleep(0.2)
            continue

        if time.time() < ignore_station2_until:
            time.sleep(0.2)
            continue

        dist = read_filtered_cm_2()

        if dist is None:
            time.sleep(0.1)
            continue

        with lock:
            state["distance_station2_cm"] = round(dist, 1)

        print(f"Station2: {dist:.1f} cm")

        if dist < SEUIL_CM:
            below_count += 1
        else:
            below_count = 0

        if below_count >= CONFIRM_N:
            below_count = 0

            threading.Thread(
                target=handle_station_detection,
                args=("station_2",),
                daemon=True
            ).start()

        time.sleep(0.1)

# ---------------------------
# CLEANUP
# ---------------------------

def cleanup():
    global cleanup_done
    global program_running

    if cleanup_done:
        return

    cleanup_done = True

    print("STOP SCRIPT")

    program_running = False

    stop_station1_effects()
    stop_train()

    pi.write(R, 0)
    pi.write(G, 0)

    pi.set_PWM_dutycycle(gate01, 0)
    pi.set_PWM_dutycycle(gate02, 0)

    print("Tout arrêté")

# ---------------------------
# SIGNAL HANDLER
# ---------------------------

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

atexit.register(cleanup)

# ---------------------------
# FLASK
# ---------------------------

app = Flask(__name__)

@app.route("/status", methods=["GET"])
def get_status():
    with lock:
        return jsonify(state)

@app.route("/close_gates", methods=["POST"])
def api_close_gates():
    threading.Thread(
        target=send_train_toggle,
        daemon=True
    ).start()

    return jsonify({
        "message": "Train toggled"
    }), 200

# ---------------------------
# MAIN
# ---------------------------

if __name__ == "__main__":

    stop_station1_effects()

    start_train()

    threading.Thread(
        target=sensor_loop_station1,
        daemon=True
    ).start()

    threading.Thread(
        target=sensor_loop_station2,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=5000
    )