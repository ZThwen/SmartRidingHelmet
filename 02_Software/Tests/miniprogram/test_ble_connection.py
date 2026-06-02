"""
brief BLE 连接测试
note 验证 BLEDriver 广播 + 小程序扫描连接 + 断连检测
     板子端: BLEDriver 初始化 → 广播 → 等待连接
     小程序端: 手动点击「连接」按钮
"""
import sys
sys.path.append("..")
import time

from core.Event_Bus import EventBus
from core.config import EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED
from Drivers.network.BLE import BLEDriver


_LOG_PATH = "Tests/miniprogram/test_ble_connection.log"
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


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" BLE 连接测试")
    print("=" * 50)

    # 初始化
    bus = EventBus()
    ble = BLEDriver(bus)
    ble.init()

    if not ble.ctx.get("is_init"):
        log("✗ BLEDriver 初始化失败")
        return

    log("✓ BLEDriver 初始化成功")
    log("  设备名: SmartHelmet-66ccff")
    log("  服务 UUID: 0xFFF0")

    # 监听连接事件
    connected = [False]
    def on_conn(data):
        connected[0] = True
        log("✓ BLE 连接成功!")
        log("  MTU: %d" % ble.ctx.get("mtu", 0))
    def on_disc(data):
        connected[0] = False
        log("⚠ BLE 断连")

    bus.subscribe(EVENT_BLE_CONNECTED, on_conn)
    bus.subscribe(EVENT_BLE_DISCONNECTED, on_disc)

    # 等待连接
    countdown(10, "请在小程序点击「连接」")

    log("▶ 等待连接...")
    wait_end = time.ticks_ms() + 30000  # 最多等 30s
    while time.ticks_diff(wait_end, time.ticks_ms()) > 0:
        bus.pump()
        if connected[0]:
            break
        time.sleep_ms(100)

    if connected[0]:
        log("✓ 测试通过 — BLE 连接成功")
        log("")
        log("⏱ 观察: 小程序 BLE 状态应显示「已连接」")
        log("  等待 10s 观察...")
        time.sleep(10)
    else:
        log("✗ 测试失败 — 30s 内未连接")
        log("  检查: 1.板子是否上电 2.小程序蓝牙是否打开 3.是否在扫描范围内")

    # 测试断连
    log("")
    log("▶ 测试断连...")
    log("  请在小程序点击「断开」")
    wait_end = time.ticks_ms() + 15000
    while time.ticks_diff(wait_end, time.ticks_ms()) > 0:
        bus.pump()
        if not connected[0]:
            break
        time.sleep_ms(100)

    if not connected[0]:
        log("✓ 断连检测正常")
    else:
        log("  (未断连，跳过断连测试)")

    print("")
    print("=" * 50)
    print(" 测试完成")
    print("=" * 50)



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
