"""
brief 边界测试 — SOS 快速连续取消循环（5 组，间隔 1s）
note  验证快速 SOS→cancel 无状态残留、LED/Audio 正确停止
usage 上传后 REPL: import test_boundary_sos_cancel
"""

import sys
import time
sys.path.append("../../02_Software")
from core.Event_Bus import EventBus
from core.config import EVENT_ALARM_CONTROL
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LED import LEDDriver
from Modules.alarm_service import AlarmService

bus = EventBus()

audio = AudioDriver(bus)
led = LEDDriver(bus)

for d in [led, audio]:
    d.init()

alarm = AlarmService(bus, led=led, audio=audio, sms=None)
alarm.init()

errors = 0

for i in range(5):
    print("--- Cycle %d ---" % (i + 1))
    bus.publish(EVENT_ALARM_CONTROL, {"cmd": "sos", "source": "cycle_%d" % i})
    alarm.tick()
    bus.pump()
    time.sleep(1)

    alarm.cancel_alarm()
    alarm.tick()
    bus.pump()
    time.sleep(0.5)

    data = alarm.get_data()
    active = data.get("alarm_active", True)
    atype = data.get("alarm_type", "UNKNOWN")
    print("  alarm_active: %s" % active)
    print("  alarm_type: %s" % atype)

    if active or atype:
        errors += 1
        print("  [ERROR] State residue!")

print("--- Final ---")
print("Total errors: %d" % errors)
print("PASS" if errors == 0 else "FAIL")
