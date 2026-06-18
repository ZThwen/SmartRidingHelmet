"""
brief ControlService v2 端到端真机测试
note 使用真硬件：BLE（手机 NRF Connect）、LightService、AudioDriver、LED
      手机通过 NRF Connect 写入 FFF3 发送控制指令
      验证：硬件响应 + FFF1 notify 回推 + 查询 TTS 播报
      每个场景前都有提示告诉你该观察什么
执行: 上传到板子运行 python test_control_service_e2e_v2.py
"""
import sys
import time
import json
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
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


state_pushes = []
tts_events = []


def on_control_state(payload):
    state_pushes.append(payload)
    print("  [STATE] %s" % payload)


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
    state_pushes.clear()
    tts_events.clear()
    print("\n  >>> %s" % msg)
    print("  >>> 准备好后按回车开始（%d 秒观察）" % duration_s)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    print("  >>> 开始计时 %d 秒，用 NRF Connect 写入 FFF3..." % duration_s)
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()
    print("  --- 收到 %d 次状态回推, %d 次 TTS ---" % (len(state_pushes), len(tts_events)))
    if state_pushes:
        for i, s in enumerate(state_pushes):
            print("  状态[%d]: %s" % (i, s))
    if tts_events:
        for t in tts_events:
            print("  TTS: %s" % t.get("text", ""))


def send_json(event_bus, cmd):
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    event_bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    event_bus.pump()
    return raw


def print_status(ctrl, light_svc, pwm_led, audio):
    print("  --- 状态 ---")
    print("  ControlService: %s" % ctrl._control_state)
    print("  LightService: mode=%s brightness=%s" % (
        light_svc.get_mode(), light_svc._data["current_brightness"]))
    print("  PWM_LED: duty=%s" % pwm_led._data["duty_cycle"])
    print("  Audio: vol=%s playing=%s" % (
        audio._data["volume"], audio.get_is_playing()))


def main():
    print("=" * 60)
    print(" ControlService v2 端到端真机测试")
    print("=" * 60)
    print("\n准备：")
    print("  1. 手机打开 NRF Connect，连接头盔 BLE")
    print("  2. 找到 Service FFF0 下的 FFF3 特征值（Write）")
    print("  3. 按场景提示发送 JSON 指令到 FFF3")
    print("  4. 观察 LED / 灯光 / 音频 / TTS 反应")
    print("  5. FFF1 notify 会推送状态回推（手机端可订阅查看）")

    event_bus = EventBus()

    # Device 层
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    pwm_led = PWMLEDDriver(event_bus)
    light_sensor = LightSensorDriver(event_bus)
    ble_driver = BLEDriver(event_bus)

    # Service 层（ControlService 无模块依赖）
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

    event_bus.subscribe(EVENT_CONTROL_STATE_CHANGED, on_control_state)
    event_bus.subscribe(EVENT_TTS_REQUEST, on_tts_request)

    print("\n等待 BLE 连接...")
    print("  手机 NRF Connect 连接头盔后，按回车开始测试")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    # ==================== 场景 1: 灯光控制 ====================
    print("\n" + "=" * 60)
    print("场景 1: 灯光控制")
    print("=" * 60)
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_on\"}}")
    print("  预期: 头灯亮起（50%%），FFF1 推送 t=7 状态")
    prompt_and_watch("light_on — 观察头灯是否亮起", event_bus, modules, 8)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"brightness_up\"}}")
    print("  预期: 头灯变亮（50%%，已到上限）")
    prompt_and_watch("brightness_up — 观察头灯变亮", event_bus, modules, 8)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_off\"}}")
    print("  预期: 头灯熄灭")
    prompt_and_watch("light_off — 观察头灯熄灭", event_bus, modules, 8)

    # ==================== 场景 2: 音量控制 ====================
    print("\n" + "=" * 60)
    print("场景 2: 音量控制")
    print("=" * 60)
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"volume_up\"}}")
    print("  预期: 音量增加，FFF1 推送 t=7")
    prompt_and_watch("volume_up — 听音量变化", event_bus, modules, 8)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"volume_down\"}}")
    print("  预期: 音量减小")
    prompt_and_watch("volume_down — 听音量变化", event_bus, modules, 8)

    # ==================== 场景 3: 报警 ====================
    print("\n" + "=" * 60)
    print("场景 3: 报警指令")
    print("=" * 60)
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_sos\"}}")
    print("  预期: LED 快闪 + SOS 音频播放，FFF1 推送 t=5")
    prompt_and_watch("alarm_sos — 观察 LED 闪烁 + 听 SOS 音", event_bus, modules, 10)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_cancel\"}}")
    print("  预期: LED 灭 + 音频停，FFF1 推送 t=6")
    prompt_and_watch("alarm_cancel — 观察报警停止", event_bus, modules, 8)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_stealth\"}}")
    print("  预期: 无声光，但 alarm_active=True，FFF1 推送 t=5")
    prompt_and_watch("alarm_stealth — 确认无声无光", event_bus, modules, 8)

    # 清除 stealth 报警
    ctrl._alarm_active = False

    # ==================== 场景 4: 电源模式 ====================
    print("\n" + "=" * 60)
    print("场景 4: 电源模式")
    print("=" * 60)
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"power_save\"}}")
    print("  预期: 进入省电模式，FFF1 推送 power_mode=suspended")
    prompt_and_watch("power_save — 观察系统进入省电", event_bus, modules, 8)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"power_normal\"}}")
    print("  预期: 恢复正常模式")
    prompt_and_watch("power_normal — 观察系统恢复", event_bus, modules, 8)

    # ==================== 场景 5: CUSTOM 状态 ====================
    print("\n" + "=" * 60)
    print("场景 5: CUSTOM 状态切换")
    print("=" * 60)
    print("  1. 先切到省电模式")
    send_json(event_bus, "power_save")
    pump_loop(event_bus, modules, 1)
    print("  power_mode: %s" % ctrl._control_state["power_mode"])

    print("  2. 省电模式下发送 light_on")
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_on\"}}")
    print("  预期: power_mode 变为 custom，头灯亮起")
    prompt_and_watch("CUSTOM — 省电下开灯应变 custom", event_bus, modules, 8)
    print("  power_mode: %s (应为 custom)" % ctrl._control_state["power_mode"])

    print("  3. 恢复正常模式")
    send_json(event_bus, "power_normal")
    pump_loop(event_bus, modules, 1)

    # ==================== 场景 6: 查询指令 ====================
    print("\n" + "=" * 60)
    print("场景 6: 查询指令（TTS 播报）")
    print("=" * 60)
    print("  注意: 需要先喂传感器数据（测试中自动完成）")

    # 喂传感器数据
    event_bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 28.5, "humid": 65.2, "valid": True})
    event_bus.publish(EVENT_GNSS_READY, {"speed_kmh": 25.3, "latitude": 31.23, "longitude": 121.47, "valid": True})
    event_bus.pump()

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"query_status\"}}")
    print("  预期: TTS 播报当前灯光+音量+电源模式")
    prompt_and_watch("query_status — 听 TTS 播报状态", event_bus, modules, 8)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"query_temp\"}}")
    print("  预期: TTS 播报\"当前温度28度\"")
    prompt_and_watch("query_temp — 听 TTS 播报温度", event_bus, modules, 8)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"query_speed\"}}")
    print("  预期: TTS 播报\"当前时速25公里\"")
    prompt_and_watch("query_speed — 听 TTS 播报速度", event_bus, modules, 8)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"query_location\"}}")
    print("  预期: TTS 播报经纬度")
    prompt_and_watch("query_location — 听 TTS 播报位置", event_bus, modules, 8)

    # ==================== 场景 7: 报警中查询保护 ====================
    print("\n" + "=" * 60)
    print("场景 7: 报警中查询保护")
    print("=" * 60)
    print("  1. 触发报警")
    send_json(event_bus, "alarm_sos")
    pump_loop(event_bus, modules, 2)

    print("  2. 报警中发送 query_temp")
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"query_temp\"}}")
    print("  预期: TTS 被阻止（不播报），报警不受影响")
    prompt_and_watch("报警中查询 — 确认无 TTS 播报", event_bus, modules, 8)

    print("  3. 取消报警")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)

    # ==================== 场景 8: 报警快照恢复 ====================
    print("\n" + "=" * 60)
    print("场景 8: 报警快照恢复")
    print("=" * 60)
    print("  1. 设置灯光亮度到 30")
    send_json(event_bus, "light_on")
    pump_loop(event_bus, modules, 1)
    send_json(event_bus, "brightness_down")
    pump_loop(event_bus, modules, 1)
    send_json(event_bus, "brightness_down")
    pump_loop(event_bus, modules, 1)
    print("  亮度: %d (应为 30)" % ctrl._control_state["light_brightness"])

    print("  2. 触发报警")
    send_json(event_bus, "alarm_sos")
    pump_loop(event_bus, modules, 2)

    print("  3. 取消报警，检查快照恢复")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)
    print("  亮度: %d (应恢复到 30)" % ctrl._control_state["light_brightness"])

    print("  FFF3 发送: alarm_sos → alarm_cancel")
    print("  预期: 报警后灯光亮度恢复到报警前的值")
    prompt_and_watch("快照恢复 — 确认亮度恢复", event_bus, modules, 8)

    # ==================== 场景 9: 省电下报警 ====================
    print("\n" + "=" * 60)
    print("场景 9: 省电下报警")
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

    print("  FFF3 发送: power_save → alarm_sos → alarm_cancel")
    print("  预期: 报警正常触发，取消后恢复省电模式")
    prompt_and_watch("省电下报警 — 确认模式恢复", event_bus, modules, 8)

    # 恢复正常模式
    send_json(event_bus, "power_normal")
    pump_loop(event_bus, modules, 1)

    # ==================== 场景 10: 导航指令 ====================
    print("\n" + "=" * 60)
    print("场景 10: 导航指令")
    print("=" * 60)
    print("  FFF3 发送导航指令")
    print("  预期: TTS 播报导航 + LCD 更新")
    nav_cmd = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 200, "road": "测试路"}})
    event_bus.publish(EVENT_NAV_CMD, {"raw": nav_cmd})
    event_bus.pump()
    prompt_and_watch("导航指令 — 听 TTS 播报导航", event_bus, modules, 8)

    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print_status(ctrl, light_svc, pwm_led, audio)
    print("\n检查清单:")
    print("  [ ] 灯光: 亮/灭/调光 正常")
    print("  [ ] 音量: 增/减 正常")
    print("  [ ] 报警 SOS: LED 闪 + 有声")
    print("  [ ] 报警 stealth: 无声光")
    print("  [ ] 报警 cancel: 停止")
    print("  [ ] 电源: active/suspended/正常切换")
    print("  [ ] CUSTOM: 省电下手动操作自动切换")
    print("  [ ] 查询: TTS 播报正确内容")
    print("  [ ] 报警中查询: TTS 被阻止")
    print("  [ ] 报警快照: 取消后亮度恢复")
    print("  [ ] 省电下报警: 报警正常 + 恢复 suspended")
    print("  [ ] 导航指令: TTS 播报 + 数据更新")
    print("  [ ] FFF1 notify: 手机收到 t=7 状态回推")


if __name__ == "__main__":
    main()
