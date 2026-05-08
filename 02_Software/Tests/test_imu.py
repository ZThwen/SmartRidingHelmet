"""
IMU单模块测试脚本
"""

import time
import sys

sys.path.insert(0, "/")

from config import EVENT_IMU_READY, EVENT_SENSOR_ERROR
from Event_Bus import EventBus
from imu import IMUDriver


def test_imu():
    print("=" * 50)
    print("IMU单模块测试开始")
    print("=" * 50)

    event_bus = EventBus()
    imu = IMUDriver(event_bus=event_bus)

    print("\n[步骤1] 初始化 IMUDriver...")
    try:
        imu.init()
        print("  ✓ 初始化成功")
    except RuntimeError as e:
        print("  ✗ 初始化失败: {}".format(e))
        print("  请检查：S502开关是否在ARDU侧、LIS2DH12是否焊接正确")
        return

    print("\n[步骤2] 查询模块状态...")
    status = imu.get_status()
    print("  is_init:   {}".format(status["is_init"]))
    print("  power:     {}".format(status["power_state"]))

    print("\n[步骤3] 手动tick测试（5次）...")
    for i in range(5):
        imu.tick()
        event_bus.pump()
        data = imu.get_data()
        if data["valid"]:
            print("    X={:.3f} Y={:.3f} Z={:.3f} T={:.3f}".format(
                data["acc_x"], data["acc_y"], data["acc_z"], data["acc_total"]
            ))
        time.sleep_ms(250)

    print("\n[步骤4] 连续采集10次...")
    valid_count = 0
    for i in range(10):
        imu.tick()
        event_bus.pump()
        data = imu.get_data()
        if data["valid"]:
            valid_count += 1
            print("  [{:02d}] T={:.3f}".format(i + 1, data["acc_total"]))
        time.sleep_ms(250)

    print("\n  有效数据: {}/10".format(valid_count))
    print("\n" + "=" * 50)
    if valid_count >= 8:
        print("✓ IMU单模块测试通过")
    else:
        print("✗ 测试失败")
    print("=" * 50)


if __name__ == "__main__":
    test_imu()
