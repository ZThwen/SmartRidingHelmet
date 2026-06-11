from pyb import Pin, Timer
p = Pin('PE11', Pin.OUT)
t = Timer(1, freq=1000)
ch = t.channel(2, Timer.PWM, pin=p)
ch.pulse_width_percent(50)