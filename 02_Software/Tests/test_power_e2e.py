"""
brief 电源模式 E2E 测试
note 使用真硬件：BLE（NRF Connect/小程序）、LED、Audio、PWM_LED
      验证：省电/紧急/正常/CUSTOM 电源模式切换 + TTS + 灯光联动
      每个场景前都有提示告诉你该观察什么
执行: 上传到板子运行 python test_power_e2e.py
"""
import sys
import time
import json
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
)
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.network.BLE import BLEDriver
from Modules.light_service import LightService
from Modules.alarm_service import AlarmService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService


tts_events = []


def on_tts_request(payload):
    tts_events.append(payload)
    print("  [TTS] %s" % payload.get("text", ""))


def pump_loop(event_bus, modules, duration_s=3):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()


def prompt_and_watch(msg, event_bus, modules, duration_s=5):
    tts_events.clear()
    print("\n  >>> %s" % msg)
    print("  >>> 准备好后按回车开始（%d 秒观察）" % duration_s)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    print("  >>> 开始计时 %d 秒..." % duration_s)
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()
    print("  --- 收到 %d 次 TTS ---" % len(tts_events))


def send_json(event_bus, cmd):
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    event_bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    event_bus.pump()


def main():
    print("=" * 60)
    print(" 电源模式 E2E 测试")
    print("=" * 60)
    print("\n准备：")
    print("  1. 手机打开 NRF Connect 或微信小程序")
    print("  2. 连接头盔 BLE（SmartHelmet-66ccff）")
    print("  3. 按场景提示发送 JSON 指令到 FFF3")
    print("  4. 观察灯光 / LED / TTS 反应")

    event_bus = EventBus()

    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    pwm_led = PWMLEDDriver(event_bus)
    ble_driver = BLEDriver(event_bus)

    light_svc = LightService(event_bus, pwm_led=pwm_led)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    ble_svc = BLEService(event_bus, ble_driver=ble_driver)
    ctrl = ControlService(event_bus)

    init_order = [led, audio, pwm_led, ble_driver, light_svc, alarm, ble_svc, ctrl]
    modules = [led, audio, pwm_led, ble_driver, light_svc, alarm, ble_svc, ctrl]

    print("\n[初始化]")
    for mod in init_order:
        try:
            mod.init()
            print("  OK %s" % mod.name)
        except Exception as e:
            print("  FAIL %s: %s" % (mod.name, e))

    event_bus.subscribe(EVENT_TTS_REQUEST, on_tts_request)

    print("\n等待 BLE 连接...")
    print("  连接后按回车开始测试")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    # ==================== 场景 1: 省电模式 ====================
    print("\n" + "=" * 60)
    print("场景 1: 省电模式")
    print("=" * 60)
    print("  先开灯，再切省电")
    send_json(event_bus, "light_on")
    pump_loop(event_bus, modules, 1)
    print("  当前亮度: %d, power_mode: %s" % (
        ctrl._control_state["light_brightness"],
        ctrl._control_state["power_mode"]))

    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"power_save\"}}")
    print("  预期: 灯灭 + TTS '省电模式' + power_mode=suspended")
    prompt_and_watch("power_save — 观察灯灭 + 听 TTS", event_bus, modules, 8)
    print("  亮度: %d (应为 0), power_mode: %s (应为 suspended)" % (
        ctrl._control_state["light_brightness"],
        ctrl._control_state["power_mode"]))

    # ==================== 场景 2: 紧急模式 ====================
    print("\n" + "=" * 60)
    print("场景 2: 紧急模式")
    print("=" * 60)
    print("  先开灯，再切紧急")
    send_json(event_bus, "light_on")
    pump_loop(event_bus, modules, 1)

    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"power_emergency\"}}")
    print("  预期: 灯灭 + TTS '紧急省电模式' + power_mode=emergency")
    prompt_and_watch("power_emergency — 观察灯灭 + 听 TTS", event_bus, modules, 8)
    print("  亮度: %d (应为 0), power_mode: %s (应为 emergency)" % (
        ctrl._control_state["light_brightness"],
        ctrl._control_state["power_mode"]))

    # ==================== 场景 3: 恢复正常 ====================
    print("\n" + "=" * 60)
    print("场景 3: 恢复正常")
    print("=" * 60)
    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"power_normal\"}}")
    print("  预期: TTS '正常模式' + power_mode=active")
    prompt_and_watch("power_normal — 听 TTS + 确认恢复", event_bus, modules, 8)
    print("  power_mode: %s (应为 active)" % ctrl._control_state["power_mode"])

    # ==================== 场景 4: CUSTOM 覆盖 ====================
    print("\n" + "=" * 60)
    print("场景 4: CUSTOM 覆盖")
    print("=" * 60)
    print("  1. 切省电")
    send_json(event_bus, "power_save")
    pump_loop(event_bus, modules, 1)
    print("  power_mode: %s" % ctrl._control_state["power_mode"])

    print("  2. 省电下开灯")
    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_on\"}}")
    print("  预期: power_mode 变为 custom + 灯亮")
    prompt_and_watch("CUSTOM — 省电下开灯", event_bus, modules, 8)
    print("  power_mode: %s (应为 custom)" % ctrl._control_state["power_mode"])

    # 恢复正常
    send_json(event_bus, "power_normal")
    pump_loop(event_bus, modules, 1)

    # ==================== 场景 5: 省电下关灯 ====================
    print("\n" + "=" * 60)
    print("场景 5: 省电下关灯")
    print("=" * 60)
    print("  1. 开灯")
    send_json(event_bus, "light_on")
    pump_loop(event_bus, modules, 1)
    print("  亮度: %d" % ctrl._control_state["light_brightness"])

    print("  2. 切省电")
    send_json(event_bus, "power_save")
    pump_loop(event_bus, modules, 1)
    print("  亮度: %d (应为 0), power_mode: %s" % (
        ctrl._control_state["light_brightness"],
        ctrl._control_state["power_mode"]))
    prompt_and_watch("省电下关灯 — 确认亮度=0", event_bus, modules, 5)

    # 恢复正常
    send_json(event_bus, "power_normal")
    pump_loop(event_bus, modules, 1)

    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n检查清单:")
    print("  [ ] 省电模式: 灯灭 + TTS + power_mode=suspended")
    print("  [ ] 紧急模式: 灯灭 + TTS + power_mode=emergency")
    print("  [ ] 恢复正常: TTS + power_mode=active")
    print("  [ ] CUSTOM 覆盖: 省电下开灯 → custom")
    print("  [ ] 省电下关灯: 亮度=0")


if __name__ == "__main__":
    main()
