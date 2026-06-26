"""
brief 导航 LCD 显示测试
note 验证导航指令在 LCD 底部显示：
     LCD 底部显示导航行
     导航行内容随指令变化
执行: 上传到板子运行
"""
import sys
sys.path.append("../../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import EVENT_NAV_CMD
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver


_LOG_PATH = "Tests/miniprogram/step_b/04_navigation_mode/test_nav_lcd.log"
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
    print(" 导航 LCD 显示测试")
    print("=" * 50)

    bus = EventBus()

    log("初始化 Audio + LCD...")
    try:
        audio = AudioDriver(bus)
        audio.init()
        lcd = LCDDriver(bus)
        lcd.init()
        log("✓ Audio + LCD 就绪")
    except Exception as e:
        log("✗ 初始化失败: %s" % e)
        return

    log("初始化 BLE + NavigationService...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        nav_svc = NavigationService(bus, audio_driver=audio)
        nav_svc.init()
        log("✓ BLE + NavigationService 就绪")
    except Exception as e:
        log("✗ 初始化失败: %s" % e)
        return

    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接")
        return
    log("✓ BLE 已连接")

    # === 测试: 模拟 nav 命令 → LCD 显示 ===
    log("")
    log("=" * 40)
    log(" 测试: nav 命令 → LCD 底部显示")
    log("=" * 40)
    log("  请看板子 LCD 屏幕底部")

    cmds = [
        {"a": "nav", "d": {"dir": "straight", "dist": 300, "road": "长安大道"}},
        {"a": "nav", "d": {"dir": "right", "dist": 150, "road": "雁南一路"}},
        {"a": "nav", "d": {"dir": "left", "dist": 80, "road": ""}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]

    for i, cmd in enumerate(cmds):
        raw = json.dumps(cmd)
        d = cmd["d"]
        log("  [%d/%d] dir=%s dist=%s road=%s" % (
            i + 1, len(cmds), d["dir"], d["dist"], d["road"]))
        bus.publish(EVENT_NAV_CMD, {"raw": raw})
        bus.pump()
        pump_for(bus, ble_svc, 100)
        log("  等待 LCD 更新...")
        pump_for(bus, ble_svc, 2000)

    log("")
    log("⏱ 观察: LCD 底部应显示导航行")
    log("  [ ] LCD: 底部显示绿色导航文字")
    log("  [ ] LCD: 导航行随指令变化")
    log("  [ ] LCD: 到达时显示「已到达」")
    pump_for(bus, ble_svc, 5000)

    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
