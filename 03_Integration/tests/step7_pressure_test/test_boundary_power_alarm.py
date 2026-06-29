"""
brief 边界测试 — 报警期间电源模式切换互扰
note  验证报警 active 时切换 ACTIVE/SUSPENDED/EMERGENCY 不崩溃
usage 上传后 REPL: import test_boundary_power_alarm
"""

import sys
import time
sys.path.append("../../02_Software")
from core.Event_Bus import EventBus
from core.config import (
    EVENT_ALARM_CONTROL,
    EVENT_POWER_STATE_CHANGE,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
)
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.LCD import LCDDriver
from Drivers.network.SMS import SMSDriver
from Drivers.sensor.imu import IMUDriver
from Modules.alarm_service import AlarmService
from Modules.power_service import PowerService

bus = EventBus()

audio = AudioDriver(bus)
led = LEDDriver(bus)
lcd = LCDDriver(bus)
sms_drv = SMSDriver(bus)
imu = IMUDriver(bus)

for d in [led, lcd, audio, imu]:
    d.init()

alarm = AlarmService(bus, led=led, audio=audio, sms=sms_drv)
power = PowerService(bus)
alarm.init()
power.init()

# Trigger SOS
bus.publish(EVENT_ALARM_CONTROL, {"cmd": "sos", "source": "boundary_power"})
alarm.tick()
bus.pump()
time.sleep(2)

# Cycle power modes during alarm
for mode in [POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY, POWER_STATE_ACTIVE]:
    bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": mode})
    power.tick()
    alarm.tick()
    bus.pump()
    time.sleep(1)

# Cancel alarm
alarm.cancel_alarm()
alarm.tick()
bus.pump()
time.sleep(2)

data = alarm.get_data()
active = data.get("alarm_active", True)
pw_data = power.get_data()
pmode = pw_data.get("power_mode", "")
print("Alarm active: %s (expected: False)" % active)
print("Power mode: %s (expected: ACTIVE)" % pmode)

passed = (not active) and (pmode == POWER_STATE_ACTIVE)
print("PASS" if passed else "FAIL")
