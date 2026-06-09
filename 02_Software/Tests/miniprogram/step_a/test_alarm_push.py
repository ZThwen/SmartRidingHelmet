"""
brief 报警推送测试
note 验证碰撞/SOS 报警通过 BLE 推送到小程序
     板子端: 发布报警事件 → BLEService 推送 t=5/t=6
     小程序端: 手动观察全屏报警弹窗
"""
import sys
sys.path.append("..")
import time

from core.Event_Bus import EventBus
from core.config import EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED
from Modules.ble_service import BLEService
from Drivers.network.BLE import BLEDriver


_LOG_PATH = "Tests/miniprogram/test_alarm_push.log"
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


def pump_wait(bus, ble_svc, sec):
    end = time.ticks_ms() + sec * 1000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 报警推送测试")
    print("=" * 50)

    bus = EventBus()

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

    log("✓ BLE 已连接")

    # === 测试 1: 碰撞报警 ===
    log("▶ [1/4] 触发碰撞报警 (level=2)")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    pump_wait(bus, ble_svc, 5)
    log("  ✓ 已发送 t=5")
    log("  ⏱ 观察: 小程序应弹出全屏红色报警（碰撞 Lv2）")
    time.sleep(5)

    # === 测试 2: 解除碰撞 ===
    log("▶ [2/4] 解除碰撞报警")
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_wait(bus, ble_svc, 3)
    log("  ✓ 已发送 t=6")
    log("  ⏱ 观察: 小程序报警应消失")
    time.sleep(5)

    # === 测试 3: SOS 报警 ===
    log("▶ [3/4] 触发 SOS 报警 (level=3)")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3})
    pump_wait(bus, ble_svc, 5)
    log("  ✓ 已发送 t=5")
    log("  ⏱ 观察: 小程序应弹出全屏红色报警（SOS Lv3）+ 闪烁")
    time.sleep(5)

    # === 测试 4: 解除 SOS ===
    log("▶ [4/4] 解除 SOS")
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_wait(bus, ble_svc, 3)
    log("  ✓ 已发送 t=6")
    log("  ⏱ 观察: 小程序报警应消失，状态恢复「正常」")
    time.sleep(5)

    # === 快速循环 ===
    log("")
    log("▶ 快速报警循环 (5 次)")
    events = [
        (EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2}, "碰撞"),
        (EVENT_ALARM_CANCELED, {}, "解除"),
        (EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3}, "SOS"),
        (EVENT_ALARM_CANCELED, {}, "解除"),
        (EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 1}, "碰撞 Lv1"),
    ]
    for i, (evt, data, label) in enumerate(events):
        log("  [%d/5] %s" % (i + 1, label))
        bus.publish(evt, data)
        pump_wait(bus, ble_svc, 2)

    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_wait(bus, ble_svc, 2)

    log("")
    log("✓ 测试完成")
    log("⏱ 最终确认: 小程序报警显示「正常」")

    print("")
    print("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
