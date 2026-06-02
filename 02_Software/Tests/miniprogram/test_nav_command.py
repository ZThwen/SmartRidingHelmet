"""
brief 导航指令接收测试
note 验证 FFF2 写入 → EVENT_NAV_CMD 事件发布
     板子端: 模拟发布 EVENT_NAV_CMD（等效于小程序 FFF2 写入）
     小程序端: 手动验证导航功能（选目的地 → 指令浮层）
"""
import sys
sys.path.append("..")
import time
import json

from core.Event_Bus import EventBus
from core.config import EVENT_NAV_CMD
from Modules.ble_service import BLEService
from Drivers.network.BLE import BLEDriver


_LOG_PATH = "Tests/miniprogram/test_nav_command.log"
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
    print(" 导航指令测试")
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

    # 监听 NAV_CMD
    nav_received = []
    def on_nav(data):
        raw = data.get("raw", "")
        try:
            cmd = json.loads(raw)
            d = cmd.get("d", {})
            log("  ✓ EVENT_NAV_CMD: dir=%s dist=%s road=%s" % (
                d.get("dir", ""), d.get("dist", ""), d.get("road", "")))
        except:
            log("  ✓ EVENT_NAV_CMD: %s" % raw)
        nav_received.append(raw)
    bus.subscribe(EVENT_NAV_CMD, on_nav)

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
    log("")

    # 模拟 3 条导航指令（等效于小程序 FFF2 写入）
    cmds = [
        {"a": "nav", "d": {"dir": "right", "dist": 200, "road": "中山路"}},
        {"a": "nav", "d": {"dir": "straight", "dist": 500, "road": "人民路"}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]

    for i, cmd in enumerate(cmds):
        raw = json.dumps(cmd)
        log("▶ [%d/3] 模拟 FFF2 写入: %s" % (i + 1, raw))
        bus.publish(EVENT_NAV_CMD, {"raw": raw})
        pump_wait(bus, ble_svc, 2)

    log("")
    log("✓ 发送完成: %d/%d 条指令被接收" % (len(nav_received), len(cmds)))
    log("")
    log("⏱ 观察:")
    log("  [ ] Thonny 终端显示 3 条 NAV_CMD 日志")
    log("  [ ] 小程序端可手动验证: 选目的地 → 导航 → 指令浮层")

    print("")
    print("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
