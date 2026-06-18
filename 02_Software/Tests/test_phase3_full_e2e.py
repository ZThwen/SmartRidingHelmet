"""
brief Phase 3 综合集成 E2E 测试
note 模拟完整骑行流程：启动 → 连接 → 骑行 → 控制 → 报警 → 电源 → 导航 → 结束
      使用真硬件：BLE（小程序/NRF Connect）、LED、Audio、PWM_LED
      每个场景前都有提示告诉你该观察什么
执行: 上传到板子运行 python test_phase3_full_e2e.py
"""
import sys
import time
import json
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    EVENT_TEMP_HUMID_READY, EVENT_LIGHT_READY,
    EVENT_NAV_CMD,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
)
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.network.BLE import BLEDriver
from Modules.light_service import LightService
from Modules.alarm_service import AlarmService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.navigation_service import NavigationService


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


def print_status(ctrl, pwm_led, ble_svc):
    print("\n  --- 状态 ---")
    print("  ControlService: %s" % ctrl._control_state)
    print("  PWM_LED: duty=%s" % pwm_led._data.get("duty_cycle", 0))
    print("  BLE 连接: %s" % ("是" if ble_svc.ctx.get("ble_connected") else "否"))


def main():
    print("=" * 60)
    print(" Phase 3 综合集成 E2E 测试")
    print("=" * 60)
    print("\n模拟完整骑行流程：")
    print("  启动 → 连接 → 骑行 → 控制 → 报警 → 电源 → 导航 → 结束")
    print("\n准备：")
    print("  1. 手机打开微信小程序或 NRF Connect")
    print("  2. 连接头盔 BLE（SmartHelmet-66ccff）")
    print("  3. 按场景提示操作")

    event_bus = EventBus()

    # Device 层
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    pwm_led = PWMLEDDriver(event_bus)
    light_sensor = LightSensorDriver(event_bus)
    ble_driver = BLEDriver(event_bus)

    # Service 层
    light_svc = LightService(event_bus, pwm_led=pwm_led)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    ble_svc = BLEService(event_bus, ble_driver=ble_driver)
    ctrl = ControlService(event_bus)
    nav = NavigationService(event_bus, audio_driver=audio, lcd_driver=None)

    init_order = [led, audio, pwm_led, light_sensor, ble_driver,
                  light_svc, alarm, ble_svc, ctrl, nav]
    modules = [led, audio, pwm_led, light_sensor, ble_driver,
               light_svc, alarm, ble_svc, ctrl, nav]

    print("\n[初始化]")
    for mod in init_order:
        try:
            mod.init()
            print("  OK %s" % mod.name)
        except Exception as e:
            print("  FAIL %s: %s" % (mod.name, e))

    event_bus.subscribe(EVENT_TTS_REQUEST, on_tts_request)

    # ==================== 场景 1: 系统启动 ====================
    print("\n" + "=" * 60)
    print("场景 1: 系统启动")
    print("=" * 60)
    print("  所有模块初始化完成，等待 BLE 连接...")
    prompt_and_watch("系统启动 — 确认初始化无报错", event_bus, modules, 5)

    # ==================== 场景 2: BLE 连接 ====================
    print("\n" + "=" * 60)
    print("场景 2: BLE 连接")
    print("=" * 60)
    print("  请用手机连接头盔 BLE")
    print("  预期: 连接成功 + 状态回推")
    prompt_and_watch("BLE 连接 — 等待手机连接", event_bus, modules, 15)

    # ==================== 场景 3: 骑行开始 ====================
    print("\n" + "=" * 60)
    print("场景 3: 骑行开始")
    print("=" * 60)
    print("  1. 开灯")
    send_json(event_bus, "light_on")
    pump_loop(event_bus, modules, 1)
    print("  亮度: %d, PWM: %d" % (
        ctrl._control_state["light_brightness"],
        pwm_led._data.get("duty_cycle", 0)))

    print("  2. 推送传感器数据")
    event_bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 28.5, "humid": 65.2, "valid": True})
    event_bus.publish(EVENT_LIGHT_READY, {"lux": 350.0, "valid": True})
    event_bus.pump()
    prompt_and_watch("骑行开始 — 灯亮 + 传感器数据推送", event_bus, modules, 8)

    # ==================== 场景 4: 远程控制 ====================
    print("\n" + "=" * 60)
    print("场景 4: 远程控制")
    print("=" * 60)
    print("  1. 调亮灯光")
    send_json(event_bus, "brightness_up")
    pump_loop(event_bus, modules, 1)
    print("  亮度: %d" % ctrl._control_state["light_brightness"])

    print("  2. 调高音量")
    send_json(event_bus, "volume_up")
    pump_loop(event_bus, modules, 1)
    print("  音量: %d" % ctrl._control_state["volume"])

    print("  3. 查询状态")
    send_json(event_bus, "query_status")
    pump_loop(event_bus, modules, 2)

    prompt_and_watch("远程控制 — 灯光变亮 + 音量增大 + TTS", event_bus, modules, 8)

    # ==================== 场景 5: 碰撞报警 ====================
    print("\n" + "=" * 60)
    print("场景 5: 碰撞报警")
    print("=" * 60)
    print("  触发 SOS 报警")
    print("  预期: LED 快闪 + SOS 音 + TTS + 小程序弹窗")
    send_json(event_bus, "alarm_sos")
    prompt_and_watch("碰撞报警 — 观察 LED 闪烁 + 听 SOS 音", event_bus, modules, 10)

    # ==================== 场景 6: 取消恢复 ====================
    print("\n" + "=" * 60)
    print("场景 6: 取消恢复")
    print("=" * 60)
    print("  取消报警")
    print("  预期: LED 灭 + 音停 + 状态恢复")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)
    prompt_and_watch("取消恢复 — 确认报警停止 + 状态恢复", event_bus, modules, 8)

    # ==================== 场景 7: 电源切换 ====================
    print("\n" + "=" * 60)
    print("场景 7: 电源切换")
    print("=" * 60)
    print("  1. 切省电模式")
    send_json(event_bus, "power_save")
    pump_loop(event_bus, modules, 1)
    print("  power_mode: %s, 亮度: %d" % (
        ctrl._control_state["power_mode"],
        ctrl._control_state["light_brightness"]))

    print("  2. 恢复正常")
    send_json(event_bus, "power_normal")
    pump_loop(event_bus, modules, 1)
    prompt_and_watch("电源切换 — 省电 → 正常", event_bus, modules, 8)

    # ==================== 场景 8: 导航 ====================
    print("\n" + "=" * 60)
    print("场景 8: 导航")
    print("=" * 60)
    print("  发送导航指令")
    nav_cmd = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 200, "road": "测试路"}})
    event_bus.publish(EVENT_NAV_CMD, {"raw": nav_cmd})
    event_bus.pump()
    prompt_and_watch("导航 — TTS 播报 + 数据更新", event_bus, modules, 8)

    # ==================== 场景 8.5: 骑行结束 ====================
    print("\n" + "=" * 60)
    print("场景 8.5: 骑行结束")
    print("=" * 60)
    print("  关灯")
    send_json(event_bus, "light_off")
    pump_loop(event_bus, modules, 1)
    prompt_and_watch("骑行结束 — 灯灭 + 系统清理", event_bus, modules, 5)

    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print_status(ctrl, pwm_led, ble_svc)
    print("\n检查清单:")
    print("  [ ] 系统启动: 初始化无报错")
    print("  [ ] BLE 连接: 连接成功 + 状态回推")
    print("  [ ] 骑行开始: 灯亮 + 传感器数据")
    print("  [ ] 远程控制: 灯光/音量/查询正常")
    print("  [ ] 碰撞报警: LED 闪 + SOS 音 + TTS")
    print("  [ ] 取消恢复: 状态恢复")
    print("  [ ] 电源切换: 省电 → 正常")
    print("  [ ] 导航: TTS + 数据更新")
    print("  [ ] 骑行结束: 灯灭 + 清理")


if __name__ == "__main__":
    main()
