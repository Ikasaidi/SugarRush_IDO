import vlc
import time

player = vlc.MediaPlayer("/home/pi/projetFinal/son3.mp3")

player.play()

# laisser jouer 10 secondes
time.sleep(10)

player.stop()
