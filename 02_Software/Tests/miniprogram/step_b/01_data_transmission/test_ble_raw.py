"""
brief BLE 原始数据收发测试
note 验证 BLE 数据通道基础功能：
     1. 板子发送 keepalive → 小程序能收到
     2. 板子发送传感器数据 → 小程序能解析
     3. 小程序发送 nav 命令 → 板子能收到并解析
执行: 上传到板子运行，小程序端观察
"""
import sys
sys.path.append("../../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY, EVENT_LIGHT_READY,
    EVENT_NAV_CMD,
)
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService
from Drivers.actuator.Audio import AudioDriver


_LOG_PATH = "Tests/miniprogram/step_b/01_data_transmission/test_ble_raw.log"
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


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" BLE 原始数据收发测试")
    print("=" * 50)

    bus = EventBus()

    # 初始化 BLE
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

    # 初始化 Audio + NavigationService（用于接收 nav 命令）
    log("初始化 Audio + NavigationService...")
    try:
        audio = AudioDriver(bus)
        audio.init()
        nav_svc = NavigationService(bus, audio_driver=audio, lcd_driver=None)
        nav_svc.init()
        log("✓ Audio + NavigationService 就绪")
    except Exception as e:
        log("✗ Audio/Nav 失败: %s" % e)
        return

    # 监听 nav 命令
    nav_received = []
    def on_nav(data):
        raw = data.get("raw", "")
        log("  ✓ 收到 NAV_CMD: %s" % str(raw)[:60])
        nav_received.append(raw)
    bus.subscribe(EVENT_NAV_CMD, on_nav)

    # 等待连接
    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接，测试终止")
        return
    log("✓ BLE 已连接")

    # === 测试 1: 发送传感器数据 ===
    log("")
    log("=" * 40)
    log(" 测试 1: 发送传感器数据 (10 秒)")
    log("=" * 40)
    log("  请在小程序观察: 数据卡片有数值更新")

    for i in range(5):
        bus.publish(EVENT_TEMP_HUMID_READY, {
            "temp": 25.0 + i * 0.5, "humid": 60.0 - i, "valid": True,
        })
        bus.publish(EVENT_GNSS_READY, {
            "latitude": 34.1547 + i * 0.00001,
            "longitude": 108.8959 + i * 0.00001,
            "altitude": 400.0, "speed_kmh": 15.0,
            "signal_quality": "good", "valid": True,
        })
        bus.publish(EVENT_LIGHT_READY, {
            "light_intensity": 500 + i * 100, "valid": True,
        })
        ble_svc.tick()
        bus.pump()
        log("  → 第 %d 组数据已发送" % (i + 1))
        pump_end = time.ticks_ms() + 2000
        while time.ticks_diff(pump_end, time.ticks_ms()) > 0:
            ble_svc.tick()
            bus.pump()
            time.sleep_ms(100)

    log("")
    log("  [ ] 小程序: 温度/湿度/速度有数值")
    log("  [ ] 小程序: 定位卡片有坐标")
    pump_end = time.ticks_ms() + 5000
    while time.ticks_diff(pump_end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)

    # === 测试 2: 等待小程序发送 nav 命令 ===
    log("")
    log("=" * 40)
    log(" 测试 2: 接收小程序 nav 命令 (30 秒)")
    log("=" * 40)
    log("  请在小程序「开始骑行」→「设置目的地」→「开始导航」")
    log("  观察: 板子是否收到 nav 命令")

    end = time.ticks_ms() + 30000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)

    log("")
    log("  收到 %d 条 nav 命令" % len(nav_received))
    if nav_received:
        log("  ✓ nav 命令接收正常")
        for i, raw in enumerate(nav_received[:3]):
            log("    [%d] %s" % (i + 1, str(raw)[:60]))
    else:
        log("  ✗ 未收到 nav 命令")

    # === 总结 ===
    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)
    log("  [ ] 传感器数据: 小程序能接收")
    log("  [ ] nav 命令: 板子能接收")
    log("  [ ] 数据格式: JSON 正确解析")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
