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

# SERVOS
gate01 = 17
gate02 = 27   # IMPORTANT : PAS GPIO 11

REMOTE_TRAIN_URL = "http://10.10.28.131/close_gates"

STOP_TIME = 60
IGNORE_AFTER_START = 60

CLEAR_TIME_REQUIRED = 10

# ---------------------------
# GLOBAL STATE
# ---------------------------

lock = threading.Lock()
cycle_lock = threading.Lock()

program_running = True
cleanup_done = False
cycle_running = False

expected_station = "station_1"

ignore_station1_until = 0
ignore_station2_until = 0

train_running = False

LAST_ACTIVITY = time.time()

# ---------------------------
# INIT pigpio
# ---------------------------

pi = pigpio.pi()

if not pi.connected:
    print("Erreur connexion pigpio")
    sys.exit(1)

# ---------------------------
# GPIO SETUP
# ---------------------------

pi.set_mode(TRIG, pigpio.OUTPUT)
pi.set_mode(ECHO, pigpio.INPUT)

pi.set_mode(TRIG2, pigpio.OUTPUT)
pi.set_mode(ECHO2, pigpio.INPUT)

pi.write(TRIG, 0)
pi.write(TRIG2, 0)

# ---------------------------
# LED
# ---------------------------

R = 3
G = 2

pi.set_mode(R, pigpio.OUTPUT)
pi.set_mode(G, pigpio.OUTPUT)

blink_thread = None
stop_blink = threading.Event()

# ---------------------------
# SOUND
# ---------------------------

sound_lock = threading.Lock()

player = vlc.MediaPlayer(
    "/home/pi/SugarRush_IDO/son2.mp3"
)

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
# SERVO FUNCTIONS
# ---------------------------

def close_gates():

    print("Barrières fermées")

    # Ajuste si tes servos tournent à l'envers
    pi.set_servo_pulsewidth(gate01, 2500)
    pi.set_servo_pulsewidth(gate02, 2500)

def open_gates():

    print("Barrières ouvertes")

    pi.set_servo_pulsewidth(gate01, 1000)
    pi.set_servo_pulsewidth(gate02, 1000)

# ---------------------------
# DISTANCE FUNCTIONS
# ---------------------------

def read_distance_cm():

    with sensor_lock:

        pi.write(TRIG, 0)
        time.sleep(0.002)

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

        if distance < MIN_CM or distance > MAX_CM:
            return None

        return distance

def read_distance_cm_2():

    with sensor2_lock:

        pi.write(TRIG2, 0)
        time.sleep(0.002)

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

        if distance < MIN_CM or distance > MAX_CM:
            return None

        return distance

def read_filtered_cm():

    vals = []

    for _ in range(NB_ECH):

        d = read_distance_cm()

        if d is not None:
            vals.append(d)

        time.sleep(0.01)

    return median(vals) if vals else None

def read_filtered_cm_2():

    vals = []

    for _ in range(NB_ECH):

        d = read_distance_cm_2()

        if d is not None:
            vals.append(d)

        time.sleep(0.01)

    return median(vals) if vals else None

# ---------------------------
# SOUND
# ---------------------------

def start_sound():

    with sound_lock:

        try:

            player.stop()

            time.sleep(0.2)

            player.play()

            print("Musique ON")

        except Exception as e:

            print("Erreur son:", e)

def stop_sound():

    with sound_lock:

        try:

            player.stop()

            print("Musique OFF")

        except Exception as e:

            print("Erreur stop son:", e)

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

    print("STATION 1 ON")

    close_gates()

    pi.write(G, 0)

    start_blinking()

    start_sound()

def stop_station1_effects():

    print("STATION 1 OFF")

    stop_sound()

    stop_blinking()

    pi.write(R, 0)
    pi.write(G, 1)

    open_gates()

# ---------------------------
# TRAIN CONTROL
# ---------------------------

def send_train_toggle():

    try:

        response = requests.post(
            REMOTE_TRAIN_URL,
            timeout=2
        )

        print(f"POST train → {response.status_code}")

        return True

    except Exception as e:

        print("Erreur train:", e)

        return False

def start_train():

    global train_running

    if not train_running:

        print("TRAIN START")

        if send_train_toggle():

            train_running = True

            with lock:
                state["train_running"] = True

def stop_train():

    global train_running

    if train_running:

        print("TRAIN STOP")

        if send_train_toggle():

            train_running = False

            with lock:
                state["train_running"] = False

# ---------------------------
# WAIT CLEAR
# ---------------------------

def wait_until_station1_clear():

    clear_start = None

    max_wait = time.time() + 30

    while True:

        if time.time() > max_wait:

            print("Timeout clear capteur")

            break

        dist = read_filtered_cm()

        if dist is None or dist >= SEUIL_CM:

            if clear_start is None:
                clear_start = time.time()

            elapsed = time.time() - clear_start

            print(f"Capteur clear depuis {elapsed:.1f}s")

            if elapsed >= CLEAR_TIME_REQUIRED:
                break

        else:

            clear_start = None

            print(f"Train détecté: {dist:.1f} cm")

        time.sleep(0.2)

# ---------------------------
# HANDLE DETECTION
# ---------------------------

def handle_station_detection(station_name):

    global cycle_running
    global expected_station
    global ignore_station1_until
    global ignore_station2_until

    with cycle_lock:

        if cycle_running:
            return

        cycle_running = True

    try:

        now = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        print(f"DETECTED : {station_name}")

        with lock:

            state["cycle_running"] = True
            state["last_station_detected"] = station_name
            state["last_change_time"] = now

        stop_train()

        if station_name == "station_1":
            start_station1_effects()

        print("Pause train...")
        time.sleep(STOP_TIME)

        start_train()

        if station_name == "station_1":

            wait_until_station1_clear()

            stop_station1_effects()

            expected_station = "station_2"

            ignore_station1_until = (
                time.time() + IGNORE_AFTER_START
            )

        else:

            expected_station = "station_1"

            ignore_station2_until = (
                time.time() + IGNORE_AFTER_START
            )

        with lock:

            state["expected_station"] = expected_station
            state["cycle_running"] = False

        print(f"Waiting : {expected_station}")

    except Exception as e:

        print("Erreur cycle:", e)

    finally:

        cycle_running = False

# ---------------------------
# SENSOR LOOP STATION 1
# ---------------------------

def sensor_loop_station1():

    global LAST_ACTIVITY

    below_count = 0

    while program_running:

        try:

            LAST_ACTIVITY = time.time()

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

                handle_station_detection("station_1")

            time.sleep(0.1)

        except Exception as e:

            print("Erreur sensor1:", e)

            time.sleep(1)

# ---------------------------
# SENSOR LOOP STATION 2
# ---------------------------

def sensor_loop_station2():

    global LAST_ACTIVITY

    below_count = 0

    while program_running:

        try:

            LAST_ACTIVITY = time.time()

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

                handle_station_detection("station_2")

            time.sleep(0.1)

        except Exception as e:

            print("Erreur sensor2:", e)

            time.sleep(1)

# ---------------------------
# WATCHDOG
# ---------------------------

def watchdog_loop():

    global LAST_ACTIVITY

    while program_running:

        try:

            elapsed = time.time() - LAST_ACTIVITY

            if elapsed > 15:

                print("WATCHDOG RESET")

                stop_station1_effects()

                open_gates()

                LAST_ACTIVITY = time.time()

            time.sleep(5)

        except Exception as e:

            print("Erreur watchdog:", e)

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

    pi.set_servo_pulsewidth(gate01, 0)
    pi.set_servo_pulsewidth(gate02, 0)

    pi.stop()

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

    threading.Thread(
        target=watchdog_loop,
        daemon=True
    ).start()

    threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=5002,
            use_reloader=False
        ),
        daemon=True
    ).start()

    print("SYSTEM READY")

    while True:
        time.sleep(1)