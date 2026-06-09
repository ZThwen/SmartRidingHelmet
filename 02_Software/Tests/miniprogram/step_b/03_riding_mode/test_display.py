"""
brief 骑行模式数据显示测试
note 验证骑行模式下数据卡片显示：
     温度、湿度、速度、定位、光照
     地图中心跟随手机 GPS
执行: 上传到板子运行
"""
import sys
sys.path.append("../../..")
import time

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY, EVENT_LIGHT_READY,
)
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


_LOG_PATH = "Tests/miniprogram/step_b/03_riding_mode/test_display.log"
_T0 = 0
_BASE_LAT = 34.1547
_BASE_LON = 108.8959


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


def pump_for(bus, ble_svc, duration_ms):
    end = time.ticks_ms() + duration_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 骑行模式数据显示测试")
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

    log("")
    log("请在小程序「开始骑行」→「直接出发」（不选目的地）")
    countdown(10, "等待操作")

    # === 持续推送数据 20 秒 ===
    log("")
    log("=" * 40)
    log(" 推送传感器数据 (20 秒)")
    log("=" * 40)

    for i in range(10):
        temp = 25.0 + i * 0.3
        humid = 60.0 - i * 0.5
        lat = _BASE_LAT + i * 0.00001
        lon = _BASE_LON + i * 0.00001
        lux = 500 + i * 50

        bus.publish(EVENT_TEMP_HUMID_READY, {
            "temp": temp, "humid": humid, "valid": True,
        })
        bus.publish(EVENT_GNSS_READY, {
            "latitude": lat, "longitude": lon,
            "altitude": 400.0, "speed_kmh": 15.0 + i,
            "cog": 90.0,
            "signal_quality": "good", "valid": True,
        })
        bus.publish(EVENT_LIGHT_READY, {
            "light_intensity": lux, "valid": True,
        })
        ble_svc.tick()
        bus.pump()

        if i % 3 == 0:
            log("  → T:%.1f H:%.1f V:%.1f lat:%.4f lon:%.4f lux:%d" % (
                temp, humid, 15.0 + i, lat, lon, lux))
        pump_for(bus, ble_svc, 2000)

    log("")
    log("⏱ 观察窗口: 10 秒 — 请在小程序检查:")
    log("  [ ] 温度卡片: 有数值（不是 --）")
    log("  [ ] 湿度卡片: 有数值（不是 --）")
    log("  [ ] 速度卡片: 有数值（不是 --）")
    log("  [ ] 定位卡片: 纬度/经度在更新")
    log("  [ ] 地图: 中心在西安附近（34.15, 108.89）")
    log("  [ ] 地图: 蓝色圆点 marker 可见")
    pump_for(bus, ble_svc, 10000)

    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
