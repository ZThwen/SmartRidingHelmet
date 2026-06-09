"""
brief 传感器数据推送测试
note 验证各传感器数据通过 BLE 推送到小程序：
     温湿度、GNSS、光照、IMU
     每种数据单独推送，验证小程序能正确解析
执行: 上传到板子运行
"""
import sys
sys.path.append("../../..")
import time

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY, EVENT_LIGHT_READY, EVENT_IMU_READY,
)
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


_LOG_PATH = "Tests/miniprogram/step_b/01_data_transmission/test_sensor_push.log"
_T0 = 0


def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    line = "[%7.2fs] %s" % (elapsed / 1000.0, msg)
    print(line)
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def countdown(sec, msg):
    log("⏱ 倒计时: %ds — %s" % (sec, msg))
    for i in range(sec, 0, -1):
        log("  %ds..." % i)
        time.sleep(1)


def wait_ble(bus, ble_svc, timeout_s=20):
    log("▶ 等待 BLE 连接...")
    end = time.ticks_ms() + timeout_s * 1000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            return True
        time.sleep_ms(100)
    return False


def pump_for(bus, ble_svc, duration_s):
    end = time.ticks_ms() + duration_s * 1000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 传感器数据推送测试")
    print("=" * 50)

    bus = EventBus()

    log("初始化 BLE...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log("✓ BLE 就绪")
    except Exception as e:
        log("✗ BLE 失败: %s" % e)
        return

    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接")
        return
    log("✓ BLE 已连接")

    # === 测试 1: 温湿度 ===
    log("")
    log("=" * 40)
    log(" 测试 1: 温湿度数据 (5 秒)")
    log("=" * 40)
    for i in range(3):
        bus.publish(EVENT_TEMP_HUMID_READY, {
            "temp": 25.0 + i, "humid": 60.0 - i * 2, "valid": True,
        })
        log("  → 温度:%.1f 湿度:%.1f" % (25.0 + i, 60.0 - i * 2))
        pump_for(bus, ble_svc, 2)
    log("  [ ] 小程序: 温度有数值")
    log("  [ ] 小程序: 湿度有数值")
    pump_for(bus, ble_svc, 3)

    # === 测试 2: GNSS ===
    log("")
    log("=" * 40)
    log(" 测试 2: GNSS 数据 (5 秒)")
    log("=" * 40)
    for i in range(3):
        bus.publish(EVENT_GNSS_READY, {
            "latitude": 34.1547 + i * 0.0001,
            "longitude": 108.8959 + i * 0.0001,
            "altitude": 400.0 + i, "speed_kmh": 15.0 + i,
            "signal_quality": "good", "valid": True,
        })
        log("  → 纬度:%.4f 经度:%.4f" % (34.1547 + i * 0.0001, 108.8959 + i * 0.0001))
        pump_for(bus, ble_svc, 2)
    log("  [ ] 小程序: 纬度/经度有数值")
    log("  [ ] 小程序: 速度有数值")
    pump_for(bus, ble_svc, 3)

    # === 测试 3: 光照 ===
    log("")
    log("=" * 40)
    log(" 测试 3: 光照数据 (5 秒)")
    log("=" * 40)
    for i in range(3):
        bus.publish(EVENT_LIGHT_READY, {
            "light_intensity": 500 + i * 200, "valid": True,
        })
        log("  → 光照:%d" % (500 + i * 200))
        pump_for(bus, ble_svc, 2)
    log("  [ ] 小程序: 光照有数值")
    pump_for(bus, ble_svc, 3)

    # === 总结 ===
    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)
    log("  [ ] 温湿度: 数据正确推送")
    log("  [ ] GNSS: 坐标正确推送")
    log("  [ ] 光照: 数据正确推送")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
