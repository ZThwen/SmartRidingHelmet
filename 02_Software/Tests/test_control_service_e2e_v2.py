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


# ==================== 调试输出和总结表 ====================
_test_results = []


def print_scene_state(scene_num, scene_name, ctrl, alarm=None, ble_svc=None):
    """打印当前各模块状态"""
    cs = ctrl._control_state
    print("\n  [SCENE %d] %s" % (scene_num, scene_name))
    print("    ControlService: light=%s/%s volume=%s power=%s" % (
        cs["light_mode"], cs["light_brightness"], cs["volume"], cs["power_mode"]))
    if alarm:
        print("    AlarmService: active=%s type=%s level=%s" % (
            alarm.ctx["alarm_active"], alarm.ctx["alarm_type"], alarm.ctx["alarm_level"]))
    if ble_svc:
        print("    BLEService: connected=%s queue=%s" % (
            ble_svc.ctx["ble_connected"], ble_svc.send_queue.size() if ble_svc.send_queue else 0))
    last_tts = tts_events[-1]["text"] if tts_events else "(none)"
    print("    TTS: \"%s\"" % last_tts)
    print("")


def record_result(scene_num, scene_name, cmd, expected, actual, tts_text, passed):
    """记录测试结果到总结表"""
    _test_results.append({
        "num": scene_num, "name": scene_name, "cmd": cmd,
        "expected": expected, "actual": actual,
        "tts": tts_text, "passed": passed
    })


def print_summary():
    """打印测试总结表"""
    print("\n" + "=" * 60)
    print(" E2E 测试总结")
    print("=" * 60)
    print("| # | 场景 | 指令 | 预期状态 | 实际状态 | TTS | 结果 |")
    print("|---|------|------|----------|----------|-----|------|")
    passed = 0
    failed = 0
    for r in _test_results:
        result = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            passed += 1
        else:
            failed += 1
        print("| %d | %s | %s | %s | %s | %s | %s |" % (
            r["num"], r["name"], r["cmd"], r["expected"],
            r["actual"], r["tts"], result))
    print("=" * 60)
    print(" 总计: %d 通过, %d 失败" % (passed, failed))
    print("=" * 60)


# ==================== 事件回调 ====================

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
    cs = ctrl._control_state
    print_scene_state(1, "开灯", ctrl, alarm, ble_svc)
    record_result(1, "开灯", "light_on",
                  "brightness=50", "brightness=%d" % cs["light_brightness"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["light_brightness"] == 50)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"brightness_up\"}}")
    print("  预期: 头灯变亮（50%%，已到上限）")
    prompt_and_watch("brightness_up — 观察头灯变亮", event_bus, modules, 8)
    print_scene_state(2, "亮度增加", ctrl, alarm, ble_svc)
    record_result(2, "亮度增加", "brightness_up",
                  "brightness=50", "brightness=%d" % cs["light_brightness"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["light_brightness"] == 50)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"brightness_down\"}}")
    print("  预期: 头灯变暗（45%%）")
    prompt_and_watch("brightness_down — 观察头灯变暗", event_bus, modules, 8)
    cs = ctrl._control_state
    print_scene_state(3, "亮度减少", ctrl, alarm, ble_svc)
    record_result(3, "亮度减少", "brightness_down",
                  "brightness=45", "brightness=%d" % cs["light_brightness"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["light_brightness"] == 45)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_off\"}}")
    print("  预期: 头灯熄灭")
    prompt_and_watch("light_off — 观察头灯熄灭", event_bus, modules, 8)
    cs = ctrl._control_state
    print_scene_state(4, "关灯", ctrl, alarm, ble_svc)
    record_result(4, "关灯", "light_off",
                  "brightness=0", "brightness=%d" % cs["light_brightness"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["light_brightness"] == 0)

    # ==================== 场景 2: 音量控制 ====================
    print("\n" + "=" * 60)
    print("场景 2: 音量控制")
    print("=" * 60)
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"volume_up\"}}")
    print("  预期: 音量增加，FFF1 推送 t=7")
    prompt_and_watch("volume_up — 听音量变化", event_bus, modules, 8)
    cs = ctrl._control_state
    print_scene_state(5, "音量增加", ctrl, alarm, ble_svc)
    record_result(5, "音量增加", "volume_up",
                  "volume=5", "volume=%d" % cs["volume"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["volume"] == 5)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"volume_down\"}}")
    print("  预期: 音量减小")
    prompt_and_watch("volume_down — 听音量变化", event_bus, modules, 8)
    cs = ctrl._control_state
    print_scene_state(6, "音量减少", ctrl, alarm, ble_svc)
    record_result(6, "音量减少", "volume_down",
                  "volume=4", "volume=%d" % cs["volume"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["volume"] == 4)

    # ==================== 场景 3: 电源模式 ====================
    print("\n" + "=" * 60)
    print("场景 3: 电源模式")
    print("=" * 60)
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"power_save\"}}")
    print("  预期: 进入省电模式，FFF1 推送 power_mode=suspended")
    prompt_and_watch("power_save — 观察系统进入省电", event_bus, modules, 8)
    cs = ctrl._control_state
    print_scene_state(7, "省电模式", ctrl, alarm, ble_svc)
    record_result(7, "省电模式", "power_save",
                  "power=suspended,brightness=0",
                  "power=%s,brightness=%d" % (cs["power_mode"], cs["light_brightness"]),
                  tts_events[-1]["text"] if tts_events else "",
                  cs["power_mode"] == "suspended" and cs["light_brightness"] == 0)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"power_normal\"}}")
    print("  预期: 恢复正常模式")
    prompt_and_watch("power_normal — 观察系统恢复", event_bus, modules, 8)
    cs = ctrl._control_state
    print_scene_state(8, "正常模式", ctrl, alarm, ble_svc)
    record_result(8, "正常模式", "power_normal",
                  "power=active", "power=%s" % cs["power_mode"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["power_mode"] == "active")

    # ==================== 场景 4: 报警 ====================
    print("\n" + "=" * 60)
    print("场景 4: 报警指令")
    print("=" * 60)
    print("  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_sos\"}}")
    print("  预期: LED 快闪 + SOS 音频播放，FFF1 推送 t=5")
    prompt_and_watch("alarm_sos — 观察 LED 闪烁 + 听 SOS 音", event_bus, modules, 10)
    print_scene_state(9, "SOS报警", ctrl, alarm, ble_svc)
    record_result(9, "SOS报警", "alarm_sos",
                  "alarm_active=True", "alarm_active=%s" % alarm.ctx["alarm_active"],
                  tts_events[-1]["text"] if tts_events else "",
                  alarm.ctx["alarm_active"] == True)

    print("\n  [请手动在小程序点取消报警]")
    input("  按 Enter 继续...")

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_stealth\"}}")
    print("  预期: 无声光，但 alarm_active=True，FFF1 推送 t=5")
    prompt_and_watch("alarm_stealth — 确认无声无光", event_bus, modules, 8)
    print_scene_state(10, "静默报警", ctrl, alarm, ble_svc)
    record_result(10, "静默报警", "alarm_stealth",
                  "alarm_active=True,type=stealth",
                  "alarm_active=%s,type=%s" % (
                      alarm.ctx["alarm_active"], alarm.ctx["alarm_type"]),
                  tts_events[-1]["text"] if tts_events else "",
                  alarm.ctx["alarm_active"] == True and alarm.ctx["alarm_type"] == "stealth")

    # 清除 stealth 报警
    ctrl._alarm_active = False

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
    cs = ctrl._control_state
    print("  power_mode: %s (应为 custom)" % cs["power_mode"])
    print_scene_state(11, "CUSTOM状态", ctrl, alarm, ble_svc)
    record_result(11, "CUSTOM状态", "light_on(in suspended)",
                  "power=custom,brightness=50",
                  "power=%s,brightness=%d" % (cs["power_mode"], cs["light_brightness"]),
                  tts_events[-1]["text"] if tts_events else "",
                  cs["power_mode"] == "custom")

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
    print_scene_state(12, "查询状态", ctrl, alarm, ble_svc)
    record_result(12, "查询状态", "query_status",
                  "TTS播报", "TTS=%s" % ("有" if tts_events else "无"),
                  tts_events[-1]["text"] if tts_events else "",
                  len(tts_events) > 0)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"query_temp\"}}")
    print("  预期: TTS 播报\"当前温度28度\"")
    prompt_and_watch("query_temp — 听 TTS 播报温度", event_bus, modules, 8)
    print_scene_state(13, "查询温度", ctrl, alarm, ble_svc)
    record_result(13, "查询温度", "query_temp",
                  "TTS=当前温度28度", "TTS=%s" % (tts_events[-1]["text"] if tts_events else ""),
                  tts_events[-1]["text"] if tts_events else "",
                  len(tts_events) > 0)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"query_speed\"}}")
    print("  预期: TTS 播报\"当前时速25公里\"")
    prompt_and_watch("query_speed — 听 TTS 播报速度", event_bus, modules, 8)
    print_scene_state(14, "查询速度", ctrl, alarm, ble_svc)
    record_result(14, "查询速度", "query_speed",
                  "TTS=当前时速25公里", "TTS=%s" % (tts_events[-1]["text"] if tts_events else ""),
                  tts_events[-1]["text"] if tts_events else "",
                  len(tts_events) > 0)

    print("\n  FFF3 发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"query_location\"}}")
    print("  预期: TTS 播报经纬度")
    prompt_and_watch("query_location — 听 TTS 播报位置", event_bus, modules, 8)
    print_scene_state(15, "查询位置", ctrl, alarm, ble_svc)
    record_result(15, "查询位置", "query_location",
                  "TTS播报经纬度", "TTS=%s" % (tts_events[-1]["text"] if tts_events else ""),
                  tts_events[-1]["text"] if tts_events else "",
                  len(tts_events) > 0)

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
    print_scene_state(16, "报警中查询保护", ctrl, alarm, ble_svc)
    record_result(16, "报警中查询保护", "query_temp(in alarm)",
                  "TTS被阻止", "TTS=%s" % ("有" if tts_events else "无"),
                  tts_events[-1]["text"] if tts_events else "",
                  len(tts_events) == 0)

    print("  3. 取消报警")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)

    # ==================== 场景 8: 报警快照恢复 ====================
    print("\n" + "=" * 60)
    print("场景 8: 报警快照恢复")
    print("=" * 60)
    print("  1. 设置灯光亮度到 45")
    send_json(event_bus, "light_on")
    pump_loop(event_bus, modules, 1)
    send_json(event_bus, "brightness_down")
    pump_loop(event_bus, modules, 1)
    print("  亮度: %d (应为 45)" % ctrl._control_state["light_brightness"])

    print("  2. 触发报警")
    send_json(event_bus, "alarm_sos")
    pump_loop(event_bus, modules, 2)

    print("  3. 取消报警，检查快照恢复")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)
    cs = ctrl._control_state
    print("  亮度: %d (应恢复到 45)" % cs["light_brightness"])

    print("  FFF3 发送: alarm_sos → alarm_cancel")
    print("  预期: 报警后灯光亮度恢复到报警前的值")
    prompt_and_watch("快照恢复 — 确认亮度恢复", event_bus, modules, 8)
    cs = ctrl._control_state
    print_scene_state(17, "报警快照恢复", ctrl, alarm, ble_svc)
    record_result(17, "报警快照恢复", "alarm_cancel(restore)",
                  "brightness=45", "brightness=%d" % cs["light_brightness"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["light_brightness"] == 45)

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
    cs = ctrl._control_state
    print("  power_mode: %s (应恢复到 suspended)" % cs["power_mode"])

    print("  FFF3 发送: power_save → alarm_sos → alarm_cancel")
    print("  预期: 报警正常触发，取消后恢复省电模式")
    prompt_and_watch("省电下报警 — 确认模式恢复", event_bus, modules, 8)
    cs = ctrl._control_state
    print_scene_state(18, "省电下报警", ctrl, alarm, ble_svc)
    record_result(18, "省电下报警", "alarm_cancel(in suspended)",
                  "power=suspended", "power=%s" % cs["power_mode"],
                  tts_events[-1]["text"] if tts_events else "",
                  cs["power_mode"] == "suspended")

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
    print_scene_state(19, "导航指令", ctrl, alarm, ble_svc)
    record_result(19, "导航指令", "nav(right,200m)",
                  "TTS播报导航", "TTS=%s" % (tts_events[-1]["text"] if tts_events else ""),
                  tts_events[-1]["text"] if tts_events else "",
                  len(tts_events) > 0)

    # ==================== 测试总结 ====================
    print_summary()

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
