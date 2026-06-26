"""
brief [Step 6] 全系统集成测试 v2 — 21 个模块完整运行
note 替代过时的 test_system_v1.py（12 模块，含已废弃的 CloudService）
       覆盖: 5 传感器 + 6 执行器/接口 + 1 网络 + 9 Service
      验证: 初始化 → 事件链 → 碰撞报警 → 音频调度 → 性能 → 内存

运行方式:
  1. 上传到板子运行（NUCLEO-F413ZH + EC200U）
  2. 观察串口输出，检查每个测试函数的 PASS/FAIL 标记
  3. 部分硬件模块（Audio, LCD, BLE）可能 init 失败，测试会跳过相关验证
"""
import sys
import time
import gc

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_SYSTEM_READY,
    EVENT_TEMP_HUMID_READY, EVENT_IMU_READY,
    EVENT_GNSS_READY, EVENT_LIGHT_READY,
    EVENT_COLLISION_DETECTED, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_TTS_REQUEST, EVENT_POWER_STATE_CHANGE,
    EVENT_AUDIO_PLAYBACK_START,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    PRIORITY_ALARM, PRIORITY_NAV, PRIORITY_CTRL,
)

from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.sensor.Battery import BatteryDriver

from Drivers.interface.Button import Button
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver

from Drivers.network.BLE import BLEDriver
from Drivers.interface.Voice import VoiceDriver

from Modules.collision_service import CollisionService
from Modules.audio_service import AudioService
from Modules.alarm_service import AlarmService
from Modules.display_service import DisplayService
from Modules.light_service import LightService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.navigation_service import NavigationService
from Modules.power_service import PowerService


def _make_logger(event_log, event_name):
    def _log(payload):
        event_log.append((event_name, payload))
    return _log


def make_system():
    bus = EventBus()
    bus.debug = False

    temp_humid = TempHumidDriver(bus)
    imu = IMUDriver(bus)
    gnss = GNSSDriver(bus)
    light = LightSensorDriver(bus)
    battery = BatteryDriver(bus)

    button = Button(bus)
    led = LEDDriver(bus)
    audio = AudioDriver(bus)
    lcd = LCDDriver(bus)
    pwm_led = PWMLEDDriver(bus)
    ble = BLEDriver(bus)

    collision = CollisionService(bus)
    audio_svc = AudioService(bus, audio_driver=audio)
    alarm = AlarmService(bus, led=led, audio=audio)
    display = DisplayService(bus, lcd_driver=lcd, audio_driver=audio)
    control_svc = ControlService(bus, temp_humid=temp_humid, gnss=gnss)
    light_svc = LightService(bus, pwm_led=pwm_led)
    ble_svc = BLEService(bus, ble_driver=ble)
    nav_svc = NavigationService(bus, audio_driver=audio)
    voice = VoiceDriver(bus)
    power_svc = PowerService(bus)

    init_order = [
        temp_humid, imu, gnss, light, battery,
        button, led, audio, lcd, pwm_led, ble,
        collision, audio_svc, alarm, display, control_svc, light_svc, ble_svc, nav_svc, voice,
        power_svc,
    ]

    modules = {
        "temp_humid": temp_humid, "imu": imu, "gnss": gnss, "light": light,
        "button": button, "led": led, "audio": audio, "lcd": lcd,
        "pwm_led": pwm_led, "ble": ble,
        "collision": collision, "audio_svc": audio_svc, "alarm": alarm,
        "display": display, "control_svc": control_svc, "light_svc": light_svc,
        "ble_svc": ble_svc, "nav_svc": nav_svc, "voice": voice,
        "battery": battery,
        "power_svc": power_svc,
    }

    return bus, modules, init_order


def init_all(bus, init_order):
    success = 0
    for mod in init_order:
        try:
            mod.init()
            if mod.ctx.get("is_init", False):
                success += 1
        except Exception:
            pass
    bus.pump()
    return success


def pump_loop(modules, bus, count=3):
    for _ in range(count):
        for mod in modules.values():
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        bus.pump()
        time.sleep_ms(10)


# ==================== 测试函数 ====================


def test_01_all_modules_init():
    bus, modules, init_order = make_system()
    event_log = []
    bus.subscribe(EVENT_SYSTEM_READY, _make_logger(event_log, EVENT_SYSTEM_READY))

    ok_count = init_all(bus, init_order)
    total = len(init_order)

    bus.publish(EVENT_SYSTEM_READY, {
        "total": total, "success": ok_count, "failed": [],
    })
    bus.pump()

    event_ok = any(e[0] == EVENT_SYSTEM_READY for e in event_log)
    print("  init: %d/%d 模块成功" % (ok_count, total))
    print("  EVENT_SYSTEM_READY: %s" % ("YES" if event_ok else "NO"))
    return ok_count == total


def test_02_sensor_event_chain():
    bus, modules, init_order = make_system()
    event_log = []

    sensor_events = [
        EVENT_TEMP_HUMID_READY, EVENT_IMU_READY,
        EVENT_GNSS_READY, EVENT_LIGHT_READY,
    ]
    for evt in sensor_events:
        bus.subscribe(evt, _make_logger(event_log, evt))

    bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 25.5, "humid": 60.0})
    bus.publish(EVENT_IMU_READY, {"acc_x": 0.1, "acc_y": 0.2, "acc_z": 9.8})
    bus.publish(EVENT_GNSS_READY, {"latitude": 31.23, "longitude": 121.47, "speed_kmh": 15.0})
    bus.publish(EVENT_LIGHT_READY, {"light_intensity": 30000})

    pump_loop(modules, bus, count=3)

    logged = set(e[0] for e in event_log)
    missing = set(sensor_events) - logged
    if not missing:
        print("  全部 %d 个传感器事件已传播" % len(sensor_events))
        return True
    else:
        for m in missing:
            print("  缺失: %s" % m)
        return False


def test_03_collision_alarm_chain():
    bus, modules, init_order = make_system()
    event_log = []

    for evt in [EVENT_COLLISION_DETECTED, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED]:
        bus.subscribe(evt, _make_logger(event_log, evt))

    init_all(bus, init_order)
    pump_loop(modules, bus, count=2)

    bus.publish(EVENT_COLLISION_DETECTED, {"level": 2, "acc_total": 35.0, "source": "test"})
    pump_loop(modules, bus, count=5)

    alarm = modules["alarm"]
    alarm_active = alarm.ctx.get("alarm_active", False)
    triggered = any(e[0] == EVENT_ALARM_TRIGGERED for e in event_log)

    print("  alarm_active=%s, triggered=%s" % (alarm_active, triggered))
    return alarm_active and triggered


def test_04_alarm_cancel():
    bus, modules, init_order = make_system()
    event_log = []

    for evt in [EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED]:
        bus.subscribe(evt, _make_logger(event_log, evt))

    init_all(bus, init_order)
    pump_loop(modules, bus, count=2)

    bus.publish(EVENT_COLLISION_DETECTED, {"level": 1})
    pump_loop(modules, bus, count=5)

    alarm = modules["alarm"]
    if not alarm.ctx.get("alarm_active", False):
        print("  报警未激活")
        return False

    alarm.cancel_alarm()
    pump_loop(modules, bus, count=3)

    not_active = not alarm.ctx.get("alarm_active", False)
    cancel_pub = any(e[0] == EVENT_ALARM_CANCELED for e in event_log)
    print("  取消后: active=%s, cancel_event=%s" % (alarm.ctx.get("alarm_active"), cancel_pub))
    return not_active and cancel_pub


def test_05_audio_priority_chain():
    bus, modules, init_order = make_system()

    init_all(bus, init_order)
    pump_loop(modules, bus, count=2)

    audio_svc = modules["audio_svc"]
    audio = modules["audio"]

    bus.publish(EVENT_TTS_REQUEST, {"text": "控制反馈", "priority": PRIORITY_CTRL})
    pump_loop(modules, bus, count=2)
    assert audio.tts_history[-1] == "控制反馈"

    bus.publish(EVENT_TTS_REQUEST, {"text": "导航播报", "priority": PRIORITY_NAV})
    pump_loop(modules, bus, count=2)
    assert audio.tts_history[-1] == "导航播报"
    print("  NAV 打断 CTRL: %s" % audio.tts_history[-1])

    bus.publish(EVENT_TTS_REQUEST, {"text": "报警语音", "priority": PRIORITY_ALARM})
    pump_loop(modules, bus, count=2)
    assert audio.tts_history[-1] == "报警语音"
    print("  ALARM 打断 NAV: %s" % audio.tts_history[-1])
    return True


def test_06_display_sensor_update():
    bus, modules, init_order = make_system()

    init_all(bus, init_order)
    pump_loop(modules, bus, count=2)

    bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 28.3, "humid": 55.0})
    bus.publish(EVENT_GNSS_READY, {"latitude": 31.23, "longitude": 121.47, "speed_kmh": 12.5})
    pump_loop(modules, bus, count=3)

    display = modules["display"]
    data = display.get_data()
    checks = [
        ("temp", 28.3), ("humid", 55.0),
        ("lat", 31.23), ("lon", 121.47), ("speed", 12.5),
    ]

    ok = True
    for key, expected in checks:
        actual = data.get(key)
        if actual == expected:
            print("  %s=%s" % (key, actual))
        else:
            print("  %s: 期望 %s, 实际 %s" % (key, expected, actual))
            ok = False
    return ok


def test_07_power_state_propagation():
    bus, modules, init_order = make_system()

    init_all(bus, init_order)
    pump_loop(modules, bus, count=2)

    bus.publish(EVENT_POWER_STATE_CHANGE, {
        "power_state": POWER_STATE_SUSPENDED,
        "source": "test",
    })
    pump_loop(modules, bus, count=3)

    ok_count = 0
    total = 0
    for name, mod in modules.items():
        ctx_state = mod.ctx.get("power_state", None)
        if ctx_state is not None:
            total += 1
            if ctx_state == POWER_STATE_SUSPENDED:
                ok_count += 1
                print("  %s: SUSPENDED" % name)
            else:
                print("  %s: %s (期望 SUSPENDED)" % (name, ctx_state))

    # ControlService 特殊验证：检查 _control_state["power_mode"]
    ctrl = modules.get("control_svc")
    if ctrl and ctrl.ctx.get("power_state") is not None:
        total += 1
        if getattr(ctrl, "_control_state", {}).get("power_mode") == POWER_STATE_SUSPENDED:
            ok_count += 1
            print("  control_svc._control_state[power_mode]: SUSPENDED")
        else:
            print("  control_svc._control_state[power_mode] 未更新")

    if total == 0:
        print("  无模块支持 power_state")
        return True
    print("  电源状态: %d/%d 正确" % (ok_count, total))
    return ok_count == total


def test_08_main_loop_performance():
    bus, modules, init_order = make_system()

    init_all(bus, init_order)
    pump_loop(modules, bus, count=10)

    cycles = 100
    violations = []

    for _ in range(cycles):
        for mod in init_order:
            if not mod.ctx.get("is_init", False):
                continue
            t0 = time.ticks_us()
            try:
                mod.tick()
            except Exception:
                pass
            elapsed = time.ticks_diff(time.ticks_us(), t0)
            if elapsed > 5000:
                violations.append((mod.name, elapsed))
        bus.pump()
        time.sleep_ms(10)

    if not violations:
        print("  全部 tick() < 5ms, 共 %d 轮" % cycles)
        return True
    else:
        for name, elapsed in violations[:5]:
            print("  %s: %dus > 5000us" % (name, elapsed))
        return False


def test_09_memory_stability():
    bus, modules, init_order = make_system()

    init_all(bus, init_order)

    gc.collect()
    mem_before = gc.mem_free()

    for _ in range(50):
        bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 25.0, "humid": 50.0})
        bus.publish(EVENT_GNSS_READY, {"latitude": 31.0, "longitude": 121.0, "speed_kmh": 10.0})
        bus.publish(EVENT_COLLISION_DETECTED, {"level": 1})
        pump_loop(modules, bus, count=2)

    gc.collect()
    mem_after = gc.mem_free()
    delta = mem_before - mem_after

    print("  内存: %d → %d (delta=%d)" % (mem_before, mem_after, delta))
    return delta < 2000


def test_10_voice_event_chain():
    bus, modules, init_order = make_system()

    init_all(bus, init_order)
    pump_loop(modules, bus, count=2)

    from core.config import EVENT_VOICE_CMD
    bus.subscribe(EVENT_VOICE_CMD, _make_logger([], "voice_cmd"))

    event_log = []
    bus.subscribe(EVENT_VOICE_CMD, _make_logger(event_log, EVENT_VOICE_CMD))

    bus.publish(EVENT_VOICE_CMD, {"cmd": "light_on", "source": "voice"})
    pump_loop(modules, bus, count=3)

    ctrl = modules["control_svc"]
    ctrl_data = ctrl.get_data()
    cmd_ok = ctrl_data.get("last_cmd") == "light_on"
    print("  voice light_on: last_cmd=%s, source=%s" % (ctrl_data.get("last_cmd"), ctrl_data.get("last_cmd_source")))
    return cmd_ok


def run_all():
    print("=" * 60)
    print("  Step 6 全系统集成测试 v2 — 21 模块")
    print("=" * 60)

    tests = [
        ("test_01_all_modules_init", test_01_all_modules_init),
        ("test_02_sensor_event_chain", test_02_sensor_event_chain),
        ("test_03_collision_alarm_chain", test_03_collision_alarm_chain),
        ("test_04_alarm_cancel", test_04_alarm_cancel),
        ("test_05_audio_priority_chain", test_05_audio_priority_chain),
        ("test_06_display_sensor_update", test_06_display_sensor_update),
        ("test_07_power_state_propagation", test_07_power_state_propagation),
        ("test_08_main_loop_performance", test_08_main_loop_performance),
        ("test_09_memory_stability", test_09_memory_stability),
        ("test_10_voice_event_chain", test_10_voice_event_chain),
    ]

    results = {}
    for name, func in tests:
        print("\n--- %s ---" % name)
        try:
            ok = func()
            results[name] = ok
            print("  %s: %s" % (name, "PASS" if ok else "FAIL"))
        except Exception as e:
            print("  %s: FAIL (%s)" % (name, e))
            results[name] = False

    print("\n" + "=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print("  测试摘要: %d/%d 通过" % (passed, total))
    for name, ok in results.items():
        print("    %s: %s" % (name, "PASS" if ok else "FAIL"))
    print("=" * 60)
    return passed == total


if __name__ == "__main__":
    run_all()
