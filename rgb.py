import pigpio
import time

R,G=2,3

pi = pigpio.pi()
pi.set_mode(R,pigpio.OUTPUT)
pi.set_mode(G,pigpio.OUTPUT)

# Allumer R, éteindre G et B
pi.write(R,0)
pi.write(G,1)
time.sleep(1)

# Allumer G, éteindre R et B
pi.write(R,1)
pi.write(G,0)
time.sleep(1)

# Éteindre tout
pi.write(R,1)
pi.write(G,1)
