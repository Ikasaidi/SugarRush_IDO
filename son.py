import vlc
import time

player = vlc.MediaPlayer("/home/pi/SugarRush_IDO/son2.mp3")

player.play()

# laisser jouer 10 secondes
time.sleep(10)

player.stop()