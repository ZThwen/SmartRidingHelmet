"""
brief BLEService + BLEDriver 端到端真机测试
note 使用真实 BLE 硬件：需手机 NRF Connect 连接观察
     测试流程：初始化 → 连接 → 注入传感器数据 → 注入报警 → 断连
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    EVENT_TEMP_HUMID_READY, EVENT_IMU_READY,
    EVENT_GNSS_READY, EVENT_LIGHT_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
)
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


ble_connected = False


def on_connected(payload):
    global ble_connected
    ble_connected = True
    print("[e2e] ✓ BLE 连接成功")


def on_disconnected(payload):
    global ble_connected
    ble_connected = False
    print("[e2e] ⚠ BLE 断开")


def pump_loop(eb, times, delay_ms=50):
    for _ in range(times):
        eb.pump()
        time.sleep_ms(delay_ms)


def wait_for_ble(eb, svc, timeout_ms=30000):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
        svc.tick()
        eb.pump()
        if ble_connected:
            return True
        time.sleep_ms(100)
    return False


def prompt_and_watch(title, guide):
    print("")
    print("=" * 60)
    print("  " + title)
    print("=" * 60)
    print("  " + guide)
    print("")


def test_ble_e2e():
    print("=== BLE 端到端真机测试 ===")
    print("准备: 手机打开 NRF Connect")

    eb = EventBus()
    ble = BLEDriver(eb)
    ble_service = BLEService(eb, ble_driver=ble)

    eb.subscribe(EVENT_BLE_CONNECTED, on_connected)
    eb.subscribe(EVENT_BLE_DISCONNECTED, on_disconnected)

    ble.init()
    ble_service.init()

    prompt_and_watch("场景 1: 手机连接头盔",
        "请用 NRF Connect 扫描并连接 'SmartHelmet-66ccff'")

    if not wait_for_ble(eb, ble_service):
        print("❌ 超时未连接，测试终止")
        ble_service.deinit()
        ble.stop()
        return

    assert ble.ctx["mtu"] >= 23, "MTU 协商失败"
    print("  MTU = %d" % ble.ctx["mtu"])

    prompt_and_watch("场景 2: 传感器数据推送",
        "观察 NRF Connect 的 Notify 窗口\n"
        "  ─ 应每 2 秒收到: {\"t\":0,\"d\":{\"tmp\":...,\"hum\":...}}")

    for i in range(3):
        eb.publish(EVENT_TEMP_HUMID_READY, {
            "temp": 25.0 + i * 0.5, "humid": 60.0 + i, "valid": True})
        eb.publish(EVENT_GNSS_READY, {
            "latitude": 31.23 + i * 0.01, "longitude": 121.47 + i * 0.01,
            "altitude": 10.0, "speed_kmh": 15.0 + i * 0.5, "valid": True})
        eb.publish(EVENT_LIGHT_READY, {
            "light_intensity": 500 + i * 100, "valid": True})
        pump_loop(eb, 10)
        ble_service.tick()
        eb.pump()
        time.sleep_ms(200)

    prompt_and_watch("场景 3: 报警即时推送",
        "观察 NRF Connect — 应快速收到:\n"
        "  {\"t\":5,\"d\":{\"lvl\":2,\"type\":\"collision\"}}")

    eb.publish(EVENT_ALARM_TRIGGERED, {
        "alarm_type": "collision", "level": 2})
    time.sleep_ms(500)
    ble_service.tick()
    pump_loop(eb, 10)

    eb.publish(EVENT_ALARM_CANCELED, {})
    time.sleep_ms(500)
    ble_service.tick()
    pump_loop(eb, 10)

    prompt_and_watch("场景 4: 断连检测",
        "请在手机上断开 BLE 连接\n"
        "  ─ 应停止推送\n"
        "  ─ 然后重新连接，应恢复推送")

    start = time.ticks_ms()
    while ble_connected and time.ticks_diff(time.ticks_ms(), start) < 20000:
        ble_service.tick()
        eb.pump()
        time.sleep_ms(100)

    if not ble_connected:
        print("\n  ✓ 已断开，等待重连...")
        if wait_for_ble(eb, ble_service, 30000):
            eb.publish(EVENT_TEMP_HUMID_READY, {
                "temp": 26.0, "humid": 62.0, "valid": True})
            pump_loop(eb, 10)
            print("  ✓ 重连成功，数据已恢复推送")

    print("\n" + "=" * 60)
    print("  BLE E2E 测试完成")
    print("=" * 60)
    ble_service.deinit()
    ble.stop()


if __name__ == "__main__":
    test_ble_e2e()
