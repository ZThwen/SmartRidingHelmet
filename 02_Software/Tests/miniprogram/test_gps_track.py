"""
brief GPS 轨迹测试
note 验证模拟 GNSS 坐标漂移通过 BLE 推送，小程序地图绘制轨迹
     板子端: 模拟 GNSS 漂移 + BLEService 推送
     小程序端: 手动观察地图蓝色轨迹线
"""
import sys
sys.path.append("..")
import time

from core.Event_Bus import EventBus
from core.config import EVENT_GNSS_READY
from Modules.ble_service import BLEService
from Drivers.network.BLE import BLEDriver
from Drivers.sensor.Temp_Humid import TempHumidDriver


_LOG_PATH = "Tests/miniprogram/test_gps_track.log"
_T0 = 0
_START_LAT = 22.5431
_START_LON = 113.9523
_END_LAT = 22.5500
_END_LON = 113.9600


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


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" GPS 轨迹测试 (60s)")
    print("=" * 50)

    bus = EventBus()

    # 温湿度
    log("初始化 Temp_Humid...")
    try:
        temp = TempHumidDriver(event_bus=bus)
        temp.init()
        log("✓ Temp_Humid 就绪")
    except:
        log("~ Temp_Humid 不可用")
        temp = None

    # BLE
    log("初始化 BLE...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log("✓ BLE 就绪")
    except Exception as e:
        log("✗ BLE 初始化失败: %s" % e)
        return

    # 等待连接
    countdown(10, "请在小程序点击「连接」并展开地图")

    log("▶ 等待 BLE 连接...")
    wait_end = time.ticks_ms() + 20000
    while time.ticks_diff(wait_end, time.ticks_ms()) > 0:
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            break
        time.sleep_ms(100)

    if not ble_svc.ctx.get("ble_connected"):
        log("✗ 未连接，测试终止")
        return

    log("✓ BLE 已连接")
    log("")
    log("▶ GPS 漂移: (%.4f,%.4f) → (%.4f,%.4f)" % (_START_LAT, _START_LON, _END_LAT, _END_LON))
    log("  持续 60s，约 30 个 GPS 点")
    log("")

    # 推送 60s
    end = time.ticks_ms() + 60000
    tick = 0
    point_count = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if temp:
            temp.tick()
        ble_svc.tick()
        bus.pump()

        # 每 2s 发布一个 GNSS 点
        if tick % 20 == 0:
            step = min(point_count + 1, 30)
            lat = _START_LAT + (_END_LAT - _START_LAT) * step / 30.0
            lon = _START_LON + (_END_LON - _START_LON) * step / 30.0
            spd = 10.0 + (tick % 200) * 0.08
            bus.publish(EVENT_GNSS_READY, {
                "latitude": lat, "longitude": lon,
                "altitude": 10.0, "speed_kmh": spd,
                "signal_quality": 3, "valid": True,
            })
            point_count += 1
            if point_count <= 5 or point_count % 10 == 0:
                log("  GNSS [%d/30] lat=%.4f lon=%.4f spd=%.1f" % (point_count, lat, lon, spd))

        tick += 1
        time.sleep_ms(100)

    log("")
    log("✓ 推送完成: %d 个 GPS 点" % point_count)
    log("")
    log("⏱ 观察小程序:")
    log("  [ ] 地图上有蓝色轨迹线在延伸")
    log("  [ ] 轨迹从 (%.4f,%.4f) 到 (%.4f,%.4f)" % (_START_LAT, _START_LON, _END_LAT, _END_LON))
    log("  [ ] 定位卡片纬度/经度在更新")
    log("  等待 15s 确认...")
    time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
