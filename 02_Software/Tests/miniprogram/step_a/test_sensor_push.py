"""
brief 传感器数据推送测试
note 验证温湿度/光照/GNSS 数据通过 BLE 推送到小程序
     板子端: TempHumidDriver + 模拟 GNSS + BLEService 推送
     小程序端: 手动观察数据卡片更新
"""
import sys
sys.path.append("..")
import time

from core.Event_Bus import EventBus
from core.config import EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY
from Modules.ble_service import BLEService
from Drivers.network.BLE import BLEDriver
from Drivers.sensor.Temp_Humid import TempHumidDriver


_LOG_PATH = "Tests/miniprogram/test_sensor_push.log"
_T0 = 0
_PUSH_COUNT = 0


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


def sim_gnss(bus, tick):
    """模拟 GNSS 坐标漂移"""
    if tick % 2 != 0:
        return
    lat = 22.5431 + (tick % 30) * 0.0002
    lon = 113.9523 + (tick % 30) * 0.0003
    spd = 10.0 + (tick % 20) * 0.8
    bus.publish(EVENT_GNSS_READY, {
        "latitude": lat, "longitude": lon,
        "altitude": 10.0, "speed_kmh": spd,
        "signal_quality": 3, "valid": True,
    })


def main():
    global _T0, _PUSH_COUNT
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 传感器推送测试 (30s)")
    print("=" * 50)

    bus = EventBus()

    # 温湿度
    log("初始化 Temp_Humid...")
    try:
        temp = TempHumidDriver(event_bus=bus)
        temp.init()
        log("✓ Temp_Humid 就绪")
    except Exception as e:
        log("~ Temp_Humid 不可用: %s" % e)
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
    countdown(10, "请在小程序点击「连接」")

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

    log("✓ BLE 已连接，开始推送数据 (30s)")

    # 推送 30s
    end = time.ticks_ms() + 30000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if temp:
            temp.tick()
        ble_svc.tick()
        bus.pump()
        sim_gnss(bus, tick)
        tick += 1
        time.sleep_ms(100)

    log("")
    log("✓ 推送完成")
    log("")
    log("⏱ 观察小程序:")
    log("  [ ] 温度/湿度/速度有数值（不是 --）")
    log("  [ ] 纬度/经度在更新")
    log("  [ ] BLE 状态显示「已连接」")
    log("  等待 10s 确认...")
    time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
