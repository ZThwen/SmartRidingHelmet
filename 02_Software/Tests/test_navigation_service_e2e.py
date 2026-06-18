"""
brief NavigationService 端到端测试
note 需要真实硬件 + 小程序 BLE 连接
      1. 初始化完整系统（EventBus + NavigationService + BLE）
      2. 等待小程序 BLE 连接
      3. 模拟/接收导航指令
      4. 验证 TTS 播报和 LCD 底部导航行
      5. 验证紧急暂停、静默阻塞、省电 LCD
执行: 上传到板子运行 python test_navigation_service_e2e.py
"""
import sys
import time
import json

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_NAV_CMD, EVENT_BLE_CONNECTED,
    EVENT_RIDE_CONTROL, EVENT_TTS_REQUEST,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
)
from Modules.navigation_service import NavigationService
from Modules.alarm_service import AlarmService
from Modules.control_service import ControlService
from Modules.ble_service import BLEService
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.network.BLE import BLEDriver


_LOG_PATH = "Tests/test_navigation_service_e2e.log"
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


def pump_wait(bus, sec):
    end = time.ticks_ms() + sec * 1000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        bus.pump()
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" NavigationService 端到端测试")
    print("=" * 50)

    bus = EventBus()
    bus.debug = True

    # 1. 初始化硬件驱动
    log("初始化 Audio...")
    try:
        audio = AudioDriver(bus)
        audio.init()
        log("✓ Audio 就绪")
    except Exception as e:
        log("✗ Audio 初始化失败: %s" % e)
        return

    log("初始化 LED...")
    led = LEDDriver(bus)
    led.init()

    log("初始化 PWM_LED...")
    pwm_led = PWMLEDDriver(bus)
    pwm_led.init()

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

    # 2. 初始化 Services
    log("初始化 AlarmService...")
    alarm = AlarmService(bus, led=led, audio=audio)
    alarm.init()

    log("初始化 ControlService...")
    ctrl = ControlService(event_bus=bus)
    ctrl.init()

    log("初始化 NavigationService...")
    nav_svc = NavigationService(bus, audio_driver=audio, lcd_driver=None)
    nav_svc.init()
    log("✓ 所有模块就绪")

    # 3. 等待 BLE 连接
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

    # 4. 阶段一：模拟导航指令（本地验证）
    log("=== 阶段一：模拟导航指令 ===")
    cmds = [
        {"a": "nav", "d": {"dir": "right", "dist": 200, "road": "中山路"}},
        {"a": "nav", "d": {"dir": "straight", "dist": 500, "road": "人民路"}},
        {"a": "nav", "d": {"dir": "left", "dist": 100, "road": ""}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]

    for i, cmd in enumerate(cmds):
        raw = json.dumps(cmd)
        log("▶ [%d/%d] 模拟 NAV_CMD: %s" % (i + 1, len(cmds), raw))
        bus.publish(EVENT_NAV_CMD, {"raw": raw})
        pump_wait(bus, 3)
        log("  状态: navigating=%s dir=%s dist=%s road=%s" % (
            nav_svc.ctx["is_navigating"],
            nav_svc.ctx["current_dir"],
            nav_svc.ctx["current_dist"],
            nav_svc.ctx["current_road"],
        ))

    log("")

    # 5. 阶段二：等待小程序实际导航
    log("=== 阶段二：小程序实际导航 ===")
    log("请在小程序端操作:")
    log("  1. 点击「开始骑行」")
    log("  2. 选择目的地")
    log("  3. 开始导航")
    log("")
    log("观察:")
    log("  [ ] TTS 播报中文导航指令")
    log("  [ ] LCD 底部 (y=110) 显示导航行")
    log("  [ ] 导航行内容随指令变化")
    log("  [ ] 到达后 TTS 播报'已到达目的地'")
    log("")

    countdown(60, "等待小程序导航操作...")

    # ==================== 阶段三：电源模式 × 导航 ====================
    log("")
    log("=== 阶段三：电源模式 × 导航 ===")

    # 3.1 紧急暂停
    log("--- 3.1 紧急暂停 ---")
    log("发送 power_emergency")
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "power_emergency"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    pump_wait(bus, 2)

    log("发送导航指令（应被忽略）")
    nav_cmd = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 100, "road": "测试路"}})
    bus.publish(EVENT_NAV_CMD, {"raw": nav_cmd})
    pump_wait(bus, 3)

    log("  navigating=%s dir=%s (应为 False/空)" % (
        nav_svc.ctx["is_navigating"], nav_svc.ctx["current_dir"]))

    # 恢复正常
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "power_normal"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    pump_wait(bus, 2)

    # 3.2 静默阻塞
    log("--- 3.2 静默阻塞 ---")
    log("发送 alarm_stealth")
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "alarm_stealth"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    pump_wait(bus, 2)

    log("发送导航指令（数据更新但无 TTS）")
    nav_cmd = json.dumps({"a": "nav", "d": {"dir": "left", "dist": 150, "road": "静默路"}})
    bus.publish(EVENT_NAV_CMD, {"raw": nav_cmd})
    pump_wait(bus, 3)

    log("  navigating=%s dir=%s dist=%s (数据应更新)" % (
        nav_svc.ctx["is_navigating"], nav_svc.ctx["current_dir"],
        nav_svc.ctx["current_dist"]))
    log("  预期: 无 TTS 播报（静默报警）")

    # 取消静默
    ctrl._alarm_active = False
    nav_svc._stealth_active = False

    # 3.3 省电 LCD
    log("--- 3.3 省电 LCD ---")
    log("发送 power_save")
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "power_save"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    pump_wait(bus, 2)

    log("发送导航指令（TTS 正常，LCD 跳过）")
    nav_cmd = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 80, "road": "省电路"}})
    bus.publish(EVENT_NAV_CMD, {"raw": nav_cmd})
    pump_wait(bus, 3)

    log("  navigating=%s dir=%s (数据应更新)" % (
        nav_svc.ctx["is_navigating"], nav_svc.ctx["current_dir"]))
    log("  预期: TTS 播报正常，无 LCD 写入")

    # 恢复正常
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "power_normal"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    pump_wait(bus, 2)

    log("")
    print("=" * 50)
    print(" 测试完成")
    print("=" * 50)
    print("\n检查清单:")
    print("  [ ] 基本导航: TTS 播报 + 数据更新")
    print("  [ ] 到达目的地: TTS '已到达'")
    print("  [ ] 紧急暂停: 导航被忽略")
    print("  [ ] 静默阻塞: 数据更新但无 TTS")
    print("  [ ] 省电 LCD: TTS 正常 + LCD 跳过")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
