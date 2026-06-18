"""
brief 报警系统 E2E 测试
note 使用真硬件：BLE（NRF Connect/小程序）、LED、Audio
      验证：SOS/静默/取消 全流程 + 快照恢复 + 报警中保护 + 省电下报警
      每个场景前都有提示告诉你该观察什么
执行: 上传到板子运行 python test_alarm_e2e.py
"""
import sys
import time
import json
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
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
    print(" 报警系统 E2E 测试")
    print("=" * 60)
    print("\n准备：")
    print("  1. 手机打开 NRF Connect 或微信小程序")
    print("  2. 连接头盔 BLE（SmartHelmet-66ccff）")
    print("  3. 按场景提示发送 JSON 指令到 FFF3")
    print("  4. 观察 LED / 音频 / TTS 反应")

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

    # ==================== 场景 1: SOS 全流程 ====================
    print("\n" + "=" * 60)
    print("场景 1: SOS 全流程")
    print("=" * 60)
    print("  预期: LED 快闪 + SOS 音频播放 + TTS")
    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_sos\"}}")
    prompt_and_watch("alarm_sos — 观察 LED 闪烁 + 听 SOS 音", event_bus, modules, 10)

    print("  预期: LED 灭 + 音频停 + TTS 取消")
    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_cancel\"}}")
    prompt_and_watch("alarm_cancel — 观察报警停止", event_bus, modules, 8)

    # ==================== 场景 2: 静默报警 ====================
    print("\n" + "=" * 60)
    print("场景 2: 静默报警")
    print("=" * 60)
    print("  预期: 无声光，但 alarm_active=True")
    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_stealth\"}}")
    prompt_and_watch("alarm_stealth — 确认无声无光", event_bus, modules, 8)

    print("  预期: alarm_active=False")
    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_cancel\"}}")
    prompt_and_watch("alarm_cancel — 确认解除静默报警", event_bus, modules, 5)

    # ==================== 场景 3: 快照恢复 ====================
    print("\n" + "=" * 60)
    print("场景 3: 快照恢复")
    print("=" * 60)
    print("  1. 设置灯光亮度到 30")
    send_json(event_bus, "light_on")
    pump_loop(event_bus, modules, 1)
    send_json(event_bus, "brightness_down")
    pump_loop(event_bus, modules, 1)
    send_json(event_bus, "brightness_down")
    pump_loop(event_bus, modules, 1)
    print("  亮度: %d (应为 30)" % ctrl._control_state["light_brightness"])

    print("  2. 触发报警 → 取消")
    send_json(event_bus, "alarm_sos")
    pump_loop(event_bus, modules, 2)
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)

    print("  3. 检查亮度恢复")
    print("  亮度: %d (应恢复到 30)" % ctrl._control_state["light_brightness"])
    prompt_and_watch("快照恢复 — 确认亮度恢复到 30", event_bus, modules, 5)

    # ==================== 场景 4: 报警中控制保护 ====================
    print("\n" + "=" * 60)
    print("场景 4: 报警中控制保护")
    print("=" * 60)
    print("  1. 触发报警")
    send_json(event_bus, "alarm_sos")
    pump_loop(event_bus, modules, 2)

    print("  2. 报警中发送 light_on")
    print("  预期: TTS 被阻止（不播报），报警不受影响")
    prompt_and_watch("报警中 light_on — 确认无 TTS 播报", event_bus, modules, 8)

    print("  3. 取消报警")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)

    # ==================== 场景 5: 省电下报警 ====================
    print("\n" + "=" * 60)
    print("场景 5: 省电下报警")
    print("=" * 60)
    print("  1. 切换到省电模式")
    send_json(event_bus, "power_save")
    pump_loop(event_bus, modules, 1)
    print("  power_mode: %s" % ctrl._control_state["power_mode"])

    print("  2. 触发报警")
    send_json(event_bus, "alarm_sos")
    pump_loop(event_bus, modules, 2)

    print("  3. 取消报警，检查电源模式恢复")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)
    print("  power_mode: %s (应恢复到 suspended)" % ctrl._control_state["power_mode"])
    prompt_and_watch("省电下报警 — 确认模式恢复", event_bus, modules, 8)

    # 恢复正常模式
    send_json(event_bus, "power_normal")
    pump_loop(event_bus, modules, 1)

    # ==================== 场景 6: 小程序报警 ====================
    print("\n" + "=" * 60)
    print("场景 6: 小程序报警")
    print("=" * 60)
    print("  如果使用微信小程序，请在小程序点击「SOS」按钮")
    print("  如果使用 NRF Connect，手动发送:")
    print("  FFF3: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_sos\"}}")
    print("  预期: LED 闪 + SOS 音 + 小程序弹窗报警")
    prompt_and_watch("小程序报警 — 确认 BLE 链路正常", event_bus, modules, 10)

    print("  取消报警")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)

    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n检查清单:")
    print("  [ ] SOS 全流程: LED 闪 + 有声 + 恢复")
    print("  [ ] 静默报警: 无声光 + alarm_active")
    print("  [ ] 快照恢复: 取消后亮度恢复")
    print("  [ ] 报警中保护: TTS 被阻止")
    print("  [ ] 省电下报警: 报警正常 + 恢复 suspended")
    print("  [ ] 小程序报警: BLE 链路正常")


if __name__ == "__main__":
    main()
