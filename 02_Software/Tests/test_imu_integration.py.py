"""
IMU集成环境测试
"""

import time
import sys

sys.path.insert(0, "/")

from core.config import EVENT_IMU_READY, EVENT_CONFIG_UPDATE
from core.Event_Bus import EventBus
from Drivers.sensor.imu import IMUDriver


def test_event_flow():
    print("\n[测试1] 事件流转（5秒）...")
    event_bus = EventBus()
    imu = IMUDriver(event_bus=event_bus)
    imu_data_list = []

    def on_imu_ready(event_data):
        imu_data_list.append(event_data)
        print("  total={:.3f}".format(event_data["acc_total"]))

    event_bus.subscribe(EVENT_IMU_READY, on_imu_ready)

    try:
        imu.init()
    except RuntimeError as e:
        print("  失败: {}".format(e))
        return False

    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < 5000:
        imu.tick()
        event_bus.pump()
        time.sleep_ms(10)

    print("  收到 {} 个事件".format(len(imu_data_list)))
    return len(imu_data_list) >= 20


def test_config_update():
    print("\n[测试2] 配置更新...")
    event_bus = EventBus()
    imu = IMUDriver(event_bus=event_bus)
    try:
        imu.init()
    except RuntimeError as e:
        print("  失败: {}".format(e))
        return False

    old = imu.cfg["sample_ms"]
    event_bus.publish(EVENT_CONFIG_UPDATE, {"target": "imu", "sample_ms": 500})
    event_bus.pump()
    new = imu.cfg["sample_ms"]
    print("  {}ms -> {}ms".format(old, new))
    return new == 500


def test_continuous():
    print("\n[测试3] 连续采样10次...")
    event_bus = EventBus()
    imu = IMUDriver(event_bus=event_bus)
    try:
        imu.init()
    except RuntimeError as e:
        print("  失败: {}".format(e))
        return False

    valid = 0
    for i in range(10):
        imu.tick()
        event_bus.pump()
        if imu.get_data()["valid"]:
            valid += 1
        time.sleep_ms(250)

    print("  有效: {}/10".format(valid))
    return valid >= 8


def main():
    print("=" * 50)
    print("IMU集成环境测试")
    print("=" * 50)

    results = [
        ("事件流转", test_event_flow()),
        ("配置更新", test_config_update()),
        ("连续采样", test_continuous()),
    ]

    print("\n" + "=" * 50)
    for name, ok in results:
        print("  {}: {}".format(name, "✓ 通过" if ok else "✗ 失败"))
    print("=" * 50)


if __name__ == "__main__":
    main()
