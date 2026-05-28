"""
brief BLEDriver 单模块测试
note Step 1 — 验证 BLE 初始化、广播、连接/断连事件
     在板子上运行，等待手机连接
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
)
from Drivers.network.BLE import BLEDriver


ble_connected = False
connected_count = 0


def on_connected(payload):
    global ble_connected, connected_count
    ble_connected = True
    connected_count += 1
    print("[test] ✓ EVENT_BLE_CONNECTED (#%d)" % connected_count)


def on_disconnected(payload):
    global ble_connected
    ble_connected = False
    print("[test] ⚠ EVENT_BLE_DISCONNECTED")


def test_ble_init():
    print("\n=== 测试 1: BLE 初始化和广播 ===")
    eb = EventBus()
    ble = BLEDriver(eb)

    eb.subscribe(EVENT_BLE_CONNECTED, on_connected)
    eb.subscribe(EVENT_BLE_DISCONNECTED, on_disconnected)

    ble.init()
    assert ble.ctx["is_init"], "BLE init 失败"
    print("✓ BLE 初始化成功")
    print("  设备名: %s" % ble.cfg["device_name"])
    print("  等待手机连接 (30s)...")
    print("  使用 NRF Connect 搜索 '%s' 并连接" % ble.cfg["device_name"])

    for i in range(300):
        ble.tick()
        eb.pump()
        time.sleep_ms(100)
        if ble_connected:
            print("✓ 手机已连接! mtu=%d" % ble.ctx["mtu"])
            break

    if not ble_connected:
        print("⚠ 未检测到手机连接，跳过后续测试")
    else:
        print("\n=== 测试 2: 连接状态和数据 ===")
        data = ble.get_data()
        status = ble.get_status()
        print("  get_data:", data)
        print("  get_status:", status)
        assert status["is_connected"], "get_status 应报告已连接"

        print("\n=== 测试 3: 发送 Notify ===")
        ble.notify_data('{"t":99,"d":{"s":"test"}}')
        print("  ✓ notify_data 发送完成 (手机 NRF Connect 应收到)")

        print("\n=== 测试 4: 多包 Notify (模拟传感器推送) ===")
        test_packets = [
            '{"t":1,"d":{"tmp":25.3,"hum":60}}',
            '{"t":2,"d":{"lat":31.23,"lon":121.47,"spd":15.5}}',
            '{"t":5,"d":{"lvl":2,"type":"collision"}}',
        ]
        for pkt in test_packets:
            ble.notify_data(pkt)
            time.sleep_ms(50)
        print("  ✓ 3 包 Notify 发送完成 (NRF Connect 应依次收到)")

        print("\n  等待断开测试... 请在手机上断开连接")
        for i in range(100):
            ble.tick()
            eb.pump()
            time.sleep_ms(100)
            if not ble_connected and connected_count > 0:
                print("✓ 手机已断开")
                break

    print("\n=== BLE 测试结束 ===")
    ble.stop()


if __name__ == "__main__":
    test_ble_init()
