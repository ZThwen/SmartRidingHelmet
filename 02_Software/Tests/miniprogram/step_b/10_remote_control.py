"""
brief 远端控制自由测试（对标真实集成）
note 完全依据 main.py 集成逻辑编写，模块范围仅覆盖远端控制相关
     提供完整调试日志，Ctrl+C 后打印测试摘要，可与小程序日志对比验证
     指令来源：BLE（手机小程序）

功能：
  - BLE 接收指令 → ControlService 执行 → 灯光/音量/电源响应
  - TTS 播报反馈（1 秒防抖）
  - 状态回推（合并格式 t=7）
  - BLE notify 计数
  - EventBus 队列监控
  - PWM duty 监控
  - Ctrl+C 后打印完整测试摘要

用法: python Tests/miniprogram/step_b/10_remote_control.py
"""
import sys
sys.path.append("../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    EVENT_TEMP_HUMID_READY, EVENT_LIGHT_READY,
)
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.sensor.Light import LightSensorDriver
from Modules.light_service import LightService
from Modules.control_service import ControlService
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


# ==================== 测试记录 ====================

class TestLog:
    """记录所有测试事件，Ctrl+C 后打印摘要"""
    def __init__(self):
        self.start_time = time.ticks_ms()
        self.commands = []
        self.state_changes = []
        self.tts_events = []
        self.errors = []
        self.ble_events = []
        self.light_events = []
        self.volume_events = []
        self.alarm_events = []
        self.power_events = []
        self.notify_count = 0

    def elapsed(self):
        return time.ticks_diff(time.ticks_ms(), self.start_time) / 1000

    def print_summary(self, ctrl, pwm_led, ble_svc, audio):
        print("")
        print("=" * 60)
        print(" 测试摘要")
        print("=" * 60)
        print(" 测试时长: %.1f 秒" % self.elapsed())
        print("")

        cs = ctrl._control_state
        print(" 【最终状态】")
        print("  灯光模式: %s" % cs["light_mode"])
        print("  灯光亮度: %d%%" % cs["light_brightness"])
        print("  音量: %d/5" % cs["volume"])
        print("  电源模式: %s" % cs["power_mode"])
        print("  PWM duty: %d%%" % pwm_led._data.get("duty_cycle", 0))
        print("  BLE 连接: %s" % ("是" if ble_svc.ctx.get("ble_connected") else "否"))
        print("  TTS 播报中: %s" % ("是" if audio.ctx.get("is_tts_playing") else "否"))
        print("")

        print(" 【指令历史】（共 %d 条）" % len(self.commands))
        for ts, cmd, src in self.commands:
            print("  [%.1fs] %s (来源: %s)" % (ts, cmd, src))
        print("")

        print(" 【状态变化历史】（共 %d 次）" % len(self.state_changes))
        for ts, state in self.state_changes:
            print("  [%.1fs] light=%s/%d%% vol=%d power=%s" % (
                ts, state["light_mode"], state["light_brightness"],
                state["volume"], state["power_mode"]))
        print("")

        print(" 【TTS 播报历史】（共 %d 次）" % len(self.tts_events))
        for ts, text in self.tts_events:
            print("  [%.1fs] %s" % (ts, text))
        print("")

        print(" 【事件统计】")
        print("  灯光事件: %d" % len(self.light_events))
        print("  音量事件: %d" % len(self.volume_events))
        print("  报警事件: %d" % len(self.alarm_events))
        print("  电源事件: %d" % len(self.power_events))
        print("  BLE 推送: %d" % self.notify_count)
        print("  错误: %d" % len(self.errors))
        print("")

        if self.errors:
            print(" 【错误列表】")
            for ts, err in self.errors:
                print("  [%.1fs] %s" % (ts, err))
            print("")

        print(" 【对比小程序日志】")
        print("  小程序日志中应看到:")
        print("  - BLE 收到 t=7 消息（控制状态回推）")
        print("  - 每次操作后收到对应的 t=7 状态")
        print("  - 无 +CME ERROR 错误")
        print("  - 传感器数据（温度/湿度/光照）正常显示")
        print("")
        print("=" * 60)


test_log = TestLog()


# ==================== BLE notify 计数 ====================

_orig_notify_data = None

def _counting_notify_data(json_str):
    test_log.notify_count += 1
    if _orig_notify_data:
        _orig_notify_data(json_str)


# ==================== 主函数 ====================

def main():
    global _orig_notify_data
    bus = EventBus()

    print("=" * 60)
    print(" 远端控制自由测试（对标真实集成）")
    print("=" * 60)

    # ==================== 1. 创建模块实例 ====================
    print("\n[1. 创建模块实例]")
    light_sensor = LightSensorDriver(bus)
    pwm_led = PWMLEDDriver(bus)
    audio = AudioDriver(bus)
    ble_driver = BLEDriver(bus)
    light_svc = LightService(bus, pwm_led=pwm_led)
    ble_svc = BLEService(bus, ble_driver=ble_driver)
    ctrl = ControlService(event_bus=bus)

    # ==================== 2. 初始化模块 ====================
    init_order = [
        light_sensor,
        pwm_led,
        audio,
        ble_driver,
        light_svc,
        ble_svc,
        ctrl,
    ]

    print("\n[2. 初始化模块]")
    for mod in init_order:
        try:
            mod.init()
            print("  OK %s" % mod.name)
        except Exception as e:
            print("  FAIL %s: %s" % (mod.name, e))
            test_log.errors.append((test_log.elapsed(), "init %s: %s" % (mod.name, e)))

    # monkey-patch BLE notify 计数
    _orig_notify_data = ble_driver.notify_data
    ble_driver.notify_data = _counting_notify_data

    # ==================== 3. 订阅事件 ====================
    print("\n[3. 订阅事件]")

    def on_ble_connected(p):
        test_log.ble_events.append((test_log.elapsed(), "connected"))
        print("\n  [BLE] 已连接")
    def on_ble_disconnected(p):
        test_log.ble_events.append((test_log.elapsed(), "disconnected"))
        print("\n  [BLE] 已断开")
    bus.subscribe(EVENT_BLE_CONNECTED, on_ble_connected)
    bus.subscribe(EVENT_BLE_DISCONNECTED, on_ble_disconnected)

    def on_ride_control(p):
        try:
            obj = json.loads(p.get("raw", ""))
            if obj.get("a") == "ctrl":
                cmd = obj.get("d", {}).get("cmd", "")
                test_log.commands.append((test_log.elapsed(), cmd, "ble"))
                print("\n  >>> 收到: %s" % cmd)
        except Exception:
            pass
    bus.subscribe(EVENT_RIDE_CONTROL, on_ride_control)

    def on_light_control(p):
        duty = pwm_led._data.get("duty_cycle", 0)
        test_log.light_events.append((test_log.elapsed(), p.get("cmd"), duty))
        print("  [LIGHT] cmd=%s → PWM duty=%d%%" % (p.get("cmd"), duty))
    def on_volume_control(p):
        test_log.volume_events.append((test_log.elapsed(), p.get("cmd")))
        print("  [VOLUME] cmd=%s" % p.get("cmd"))
    def on_alarm_control(p):
        test_log.alarm_events.append((test_log.elapsed(), p.get("cmd")))
        print("  [ALARM] cmd=%s" % p.get("cmd"))
    def on_power_change(p):
        test_log.power_events.append((test_log.elapsed(), p.get("power_state")))
        print("  [POWER] state=%s" % p.get("power_state"))
    bus.subscribe(EVENT_LIGHT_CONTROL, on_light_control)
    bus.subscribe(EVENT_VOLUME_CONTROL, on_volume_control)
    bus.subscribe(EVENT_ALARM_CONTROL, on_alarm_control)
    bus.subscribe(EVENT_POWER_STATE_CHANGE, on_power_change)

    def on_state(p):
        t = p.get("t")
        if t == 7:
            state = {
                "light_mode": "manual" if p.get("m") == 1 else "auto",
                "light_brightness": p.get("b", 0),
                "volume": p.get("v", 0),
                "power_mode": {0: "active", 1: "suspended", 2: "emergency", 3: "custom"}.get(p.get("p"), "active"),
            }
            test_log.state_changes.append((test_log.elapsed(), state))
            print("  <<< t=%d m=%s b=%s v=%s p=%s" % (t, p.get("m"), p.get("b"), p.get("v"), p.get("p")))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, on_state)

    def on_tts(p):
        text = p.get("text", "")
        test_log.tts_events.append((test_log.elapsed(), text))
        print("  [TTS] %s" % text)
    bus.subscribe(EVENT_TTS_REQUEST, on_tts)

    sensor_events = []
    def on_temp_humid(p):
        sensor_events.append(("temp_humid", p.get("temp"), p.get("humid")))
        print("  [SENSOR] 温度=%.1f 湿度=%.1f" % (p.get("temp", 0), p.get("humid", 0)))
    def on_light_ready(p):
        sensor_events.append(("light", p.get("lux", 0)))
        print("  [SENSOR] 光照=%.1f lux" % p.get("lux", 0))
    bus.subscribe(EVENT_TEMP_HUMID_READY, on_temp_humid)
    bus.subscribe(EVENT_LIGHT_READY, on_light_ready)

    print("  事件订阅完成")

    # ==================== 4. 打印指令菜单 ====================
    print("\n[4. 可用指令]")
    print("  灯光: light_on / light_off / brightness_up / brightness_down / light_auto")
    print("  音量: volume_up / volume_down")
    print("  报警: alarm_sos / alarm_cancel / alarm_stealth")
    print("  电源: power_save / power_normal / power_emergency")
    print("  查询: query_status / query_speed / query_temp / query_humid / query_location / query_battery")

    # ==================== 5. 等待 BLE 连接 ====================
    print("\n[5. 等待 BLE 连接]")
    print("  广播名: SmartHelmet-66ccff")
    print("  等待手机连接...")
    for _ in range(200):
        for mod in init_order:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            print("  ✓ BLE 已连接")
            break
        time.sleep_ms(100)
    else:
        print("  ✗ BLE 未连接，继续等待...")

    # ==================== 6. 排空初始数据 ====================
    print("\n[6. 排空初始数据]")
    end = time.ticks_ms() + 3000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        for mod in init_order:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        bus.pump()
        time.sleep_ms(10)
    print("  完成")

    # ==================== 7. 打印初始状态 ====================
    cs = ctrl._control_state
    print("\n[7. 初始状态]")
    print("  灯光: mode=%s brightness=%d%%" % (cs["light_mode"], cs["light_brightness"]))
    print("  音量: %d/5" % cs["volume"])
    print("  电源: %s" % cs["power_mode"])
    print("  PWM: duty=%d%%" % pwm_led._data.get("duty_cycle", 0))

    # ==================== 8. 主循环 ====================
    print("")
    print("=" * 60)
    print(" 实时模式已启动！Ctrl+C 退出")
    print(" 在小程序上操作，下面即时显示")
    print("=" * 60)
    print("")

    test_log.state_changes.append((test_log.elapsed(), dict(cs)))

    last_queue_print = time.ticks_ms()

    try:
        while True:
            for mod in init_order:
                if mod.ctx.get("is_init", False):
                    try:
                        mod.tick()
                    except Exception as e:
                        test_log.errors.append((test_log.elapsed(), "tick %s: %s" % (mod.name, e)))
            bus.pump()

            now = time.ticks_ms()
            if time.ticks_diff(now, last_queue_print) >= 1000:
                queue_len = len(bus._queue)
                if queue_len > 0:
                    print("  [QUEUE] len=%d" % queue_len)
                last_queue_print = now

            time.sleep_ms(10)
    except KeyboardInterrupt:
        pass

    # ==================== 9. 打印测试摘要 ====================
    test_log.print_summary(ctrl, pwm_led, ble_svc, audio)


if __name__ == "__main__":
    main()
