"""
brief 报警-导航冲突测试
note 验证导航中触发报警的行为：
     导航中触发报警 → 导航暂停
     报警取消 → 导航恢复
执行: 上传到板子运行
"""
import sys
sys.path.append("../../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import EVENT_NAV_CMD, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService
from Drivers.actuator.Audio import AudioDriver


_LOG_PATH = "Tests/miniprogram/step_b/05_alarm/test_alarm_nav.log"
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
    print(" 报警-导航冲突测试")
    print("=" * 50)

    bus = EventBus()

    log("初始化 Audio + BLE + NavigationService...")
    try:
        audio = AudioDriver(bus)
        audio.init()
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        nav_svc = NavigationService(bus, audio_driver=audio, lcd_driver=None)
        nav_svc.init()
        log("✓ 全部就绪")
    except Exception as e:
        log("✗ 初始化失败: %s" % e)
        return

    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接")
        return
    log("✓ BLE 已连接")

    # === 测试: 导航中触发报警 ===
    log("")
    log("=" * 40)
    log(" 测试: 导航 → 报警 → 取消 → 导航恢复")
    log("=" * 40)

    log("▶ 发送导航指令...")
    bus.publish(EVENT_NAV_CMD, {"raw": json.dumps(
        {"a": "nav", "d": {"dir": "straight", "dist": 300, "road": "测试路"}})})
    bus.pump()
    pump_for(bus, ble_svc, 100)
    log("  导航状态: %s" % nav_svc.ctx.get("is_navigating"))
    pump_for(bus, ble_svc, 3000)

    log("▶ 触发碰撞报警...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    bus.pump()
    pump_for(bus, ble_svc, 100)
    log("  [ ] 小程序: 报警弹窗")
    log("  [ ] 小程序: 导航卡片显示「报警中，导航暂停」")
    pump_for(bus, ble_svc, 5000)

    log("▶ 取消报警...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    bus.pump()
    pump_for(bus, ble_svc, 100)
    log("  [ ] 小程序: 报警弹窗消失")
    log("  [ ] 小程序: 导航卡片恢复正常")
    pump_for(bus, ble_svc, 3000)

    log("▶ 发送新导航指令（验证恢复）...")
    bus.publish(EVENT_NAV_CMD, {"raw": json.dumps(
        {"a": "nav", "d": {"dir": "right", "dist": 100, "road": "恢复路"}})})
    bus.pump()
    pump_for(bus, ble_svc, 100)
    log("  导航状态: %s" % nav_svc.ctx.get("is_navigating"))
    pump_for(bus, ble_svc, 3000)

    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)
    log("  [ ] 导航中报警: 导航暂停")
    log("  [ ] 报警取消: 导航恢复")
    log("  [ ] 恢复后: 新导航指令正常处理")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
