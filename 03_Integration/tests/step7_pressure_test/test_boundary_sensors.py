"""
brief 边界测试 — I2C1 总线争用（Temp_Humid + IMU 共享 I2C1）
note  验证 1 分钟高频交替 tick() 不崩溃、不丢数据
usage 上传后 REPL: import test_boundary_sensors
"""

import sys
import time
sys.path.append("../../02_Software")
from core.Event_Bus import EventBus
from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver

bus = EventBus()
temp = TempHumidDriver(bus)
imu = IMUDriver(bus)
temp.init()
imu.init()

# Warmup: 5 ticks before the main loop
for _ in range(5):
    temp.tick()
    imu.tick()

t0 = time.ticks_ms()
errors = 0
loops = 0

while time.ticks_diff(time.ticks_ms(), t0) < 60000:
    try:
        temp.tick()
        imu.tick()
        loops += 1
    except Exception as e:
        errors += 1
        print("[ERROR] Loop %d: %s" % (loops, e))

td = temp.get_data()
id_ = imu.get_data()
print("Loops: %d" % loops)
print("Errors: %d" % errors)
print("Temp_Humid data: %s" % str(td))
print("IMU data: %s" % str(id_))

passed = (errors == 0 and isinstance(td, dict) and isinstance(id_, dict))
print("PASS" if passed else "FAIL")
