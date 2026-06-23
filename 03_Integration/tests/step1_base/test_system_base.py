"""
brief [Step 1] 基础系统验证测试 — 11 个模块（无 CloudService/MQTT）
note 覆盖: 4 传感器 + 4 执行器 + 3 Service
       验证内容: init -> 事件流 -> 碰撞报警链 -> 显示更新 -> 电源管理 -> 性能

运行方式:
  1. 上传到板子运行
  2. 观察串口输出，检查每个测试函数的 ✓/✗ 标记
"""
import sys
import time

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_SYSTEM_READY,
    EVENT_TEMP_HUMID_READY,
    EVENT_IMU_READY,
    EVENT_GNSS_READY,
    EVENT_LIGHT_READY,
    EVENT_COLLISION_DETECTED,
    EVENT_ALARM_TRIGGERED,
    EVENT_ALARM_CANCELED,
    EVENT_AUDIO_PLAYBACK_START,
    EVENT_POWER_STATE_CHANGE,
    POWER_STATE_ACTIVE,
    POWER_STATE_SUSPENDED,
)

from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.sensor.Light import LightSensorDriver

from Drivers.interface.Button import Button
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver

from Modules.collision_service import CollisionService
from Modules.alarm_service import AlarmService
from Modules.display_service import DisplayService


def _make_logger(event_log, event_name):
    """创建事件日志记录闭包"""
    def _log(payload):
        event_log.append((event_name, payload))
    return _log


def make_system():
    """
    brief 创建 11 模块系统实例（无 CloudService/MQTT）
    return (event_bus, modules_dict, init_order_list)
    """
    event_bus = EventBus()
    event_bus.debug = False

    # --- 传感器 ---
    temp_humid = TempHumidDriver(event_bus)
    imu = IMUDriver(event_bus)
    gnss = GNSSDriver(event_bus)
    light = LightSensorDriver(event_bus)

    # --- 执行器 ---
    button = Button(event_bus)
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    lcd = LCDDriver(event_bus)

    # --- 服务（注入 Device 引用）---
    collision = CollisionService(event_bus)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    display = DisplayService(event_bus, lcd_driver=lcd, audio_driver=audio)

    modules = {
        "temp_humid": temp_humid,
        "imu": imu,
        "gnss": gnss,
        "light": light,
        "button": button,
        "led": led,
        "audio": audio,
        "lcd": lcd,
        "collision": collision,
        "alarm": alarm,
        "display": display,
    }

    init_order = [temp_humid, imu, gnss, light,
                  button, led, audio, lcd,
                  collision, alarm, display]

    return event_bus, modules, init_order


def init_all(event_bus, init_order):
    """
    brief 尝试初始化所有模块，返回成功计数
    """
    success = 0
    for mod in init_order:
        try:
            mod.init()
            if mod.ctx.get("is_init", False):
                success += 1
        except Exception:
            pass
    event_bus.pump()
    return success


def pump_loop(init_order, event_bus, count=1):
    """运行 n 轮 tick + pump + sleep 循环"""
    for _ in range(count):
        for mod in init_order:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()
        time.sleep_ms(10)


# ==================== 测试函数 ====================


def test_01_all_modules_init():
    """
    brief 测试所有 11 模块初始化成功
    """
    event_bus, modules, init_order = make_system()
    event_log = []
    event_bus.subscribe(EVENT_SYSTEM_READY, _make_logger(event_log, EVENT_SYSTEM_READY))

    print(f"  -> 共 {len(init_order)} 个模块")
    failures = []
    for mod in init_order:
        try:
            mod.init()
            status = mod.ctx.get("is_init", False)
            if status:
                print(f"  ✓ {mod.name} 初始化成功")
            else:
                print(f"  ~ {mod.name} init() 未设置 is_init=True")
                failures.append(mod.name)
        except Exception as e:
            print(f"  ✗ {mod.name} init() 异常: {e}")
            failures.append(mod.name)

    event_bus.publish(EVENT_SYSTEM_READY, {
        "total": len(init_order),
        "success": len(init_order) - len(failures),
        "failed": failures,
    })
    event_bus.pump()

    ok = len(failures) == 0
    event_ok = any(e[0] == EVENT_SYSTEM_READY for e in event_log)

    if ok:
        print(f"  ✓ 全部 {len(init_order)} 模块初始化成功")
    else:
        print(f"  ✗ {len(failures)} 个模块初始化失败: {failures}")
    if event_ok:
        print(f"  ✓ EVENT_SYSTEM_READY 已发布")

    # 严格模式：全通过才算通过（无硬件的模块会 init 失败，这里允许
    # 测试知晓设备层可能因缺少真硬件而报错，但至少验证 init 流程通畅）
    print(f"  → 通过率: {len(init_order) - len(failures)}/{len(init_order)}")
    return ok


def test_02_sensor_data_events():
    """
    brief 发布传感器事件，验证 EventBus 传播正确
    """
    event_bus, modules, init_order = make_system()
    event_log = []

    sensor_events = [
        EVENT_TEMP_HUMID_READY,
        EVENT_IMU_READY,
        EVENT_GNSS_READY,
        EVENT_LIGHT_READY,
    ]
    for evt in sensor_events:
        event_bus.subscribe(evt, _make_logger(event_log, evt))

    # 发布传感器数据事件
    event_bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 25.5, "humid": 60.0})
    event_bus.publish(EVENT_IMU_READY, {"acc_x": 0.1, "acc_y": 0.2, "acc_z": 9.8})
    event_bus.publish(EVENT_GNSS_READY, {"lat": 31.23, "lon": 121.47, "speed": 15.0})
    event_bus.publish(EVENT_LIGHT_READY, {"intensity": 30000})

    pump_loop(init_order, event_bus, count=3)

    logged_events = set(e[0] for e in event_log)
    all_events = set(sensor_events)
    missing = all_events - logged_events

    if not missing:
        print(f"  ✓ 所有 {len(sensor_events)} 个传感器事件均已传播")
        for evt in sensor_events:
            print(f"    ✓ {evt}")
        return True
    else:
        for evt in missing:
            print(f"  ✗ {evt} 未在 event_log 中")
        print(f"  ✓ 已接收: {len(logged_events)}/{len(sensor_events)}")
        return False


def test_03_collision_alarm_chain():
    """
    brief 碰撞->报警联动：模拟碰撞事件触发声光报警
    """
    event_bus, modules, init_order = make_system()
    event_log = []

    for evt in [EVENT_COLLISION_DETECTED, EVENT_ALARM_TRIGGERED,
                EVENT_AUDIO_PLAYBACK_START, EVENT_ALARM_CANCELED]:
        event_bus.subscribe(evt, _make_logger(event_log, evt))

    init_all(event_bus, init_order)
    pump_loop(init_order, event_bus, count=2)

    # 发布碰撞事件（模拟 CollisionService 检测结果）
    event_bus.publish(EVENT_COLLISION_DETECTED, {
        "level": 2,
        "acc_total": 35.0,
        "source": "test",
    })
    pump_loop(init_order, event_bus, count=5)

    alarm = modules["alarm"]
    alarm_active = alarm.ctx.get("alarm_active", False)
    alarm_triggered = any(e[0] == EVENT_ALARM_TRIGGERED for e in event_log)

    if alarm_active:
        print(f"  ✓ AlarmService.alarm_active = True")
    else:
        print(f"  ✗ AlarmService 未激活报警")
    if alarm_triggered:
        print(f"  ✓ EVENT_ALARM_TRIGGERED 已发布")
    else:
        print(f"  ✗ EVENT_ALARM_TRIGGERED 未发布")

    print(f"  报警类型: {alarm.ctx.get('alarm_type', 'N/A')}")
    print(f"  报警等级: {alarm.ctx.get('alarm_level', 'N/A')}")

    return alarm_active and alarm_triggered


def test_04_alarm_cancel():
    """
    brief 触发报警->取消：验证报警状态复位与声光停止
    """
    event_bus, modules, init_order = make_system()
    event_log = []

    for evt in [EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED]:
        event_bus.subscribe(evt, _make_logger(event_log, evt))

    init_all(event_bus, init_order)
    pump_loop(init_order, event_bus, count=2)

    # 步骤 1: 触发报警
    event_bus.publish(EVENT_COLLISION_DETECTED, {"level": 1})
    pump_loop(init_order, event_bus, count=5)

    alarm = modules["alarm"]
    if not alarm.ctx.get("alarm_active", False):
        print(f"  ✗ 报警未激活（可能硬件模块未 init 导致链断开）")
        return False
    print(f"  ✓ 报警已激活 (type={alarm.ctx['alarm_type']}, level={alarm.ctx['alarm_level']})")

    # 步骤 2: 取消报警（通过公开接口，模拟 ControlService 或按钮取消）
    alarm.cancel_alarm()
    pump_loop(init_order, event_bus, count=3)

    alarm_active = alarm.ctx.get("alarm_active", False)
    cancel_published = any(e[0] == EVENT_ALARM_CANCELED for e in event_log)

    if not alarm_active:
        print(f"  ✓ AlarmService.alarm_active = False（已复位）")
    else:
        print(f"  ✗ AlarmService 报警状态未复位")
    if cancel_published:
        print(f"  ✓ EVENT_ALARM_CANCELED 已发布")
    else:
        print(f"  ✗ EVENT_ALARM_CANCELED 未发布")

    return (not alarm_active) and cancel_published


def test_05_display_update():
    """
    brief 传感器->显示更新：发布传感器事件验证 DisplayService 内部数据变更
    """
    event_bus, modules, init_order = make_system()

    init_all(event_bus, init_order)
    pump_loop(init_order, event_bus, count=2)

    display = modules["display"]

    # 发布传感器数据
    event_bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 28.3, "humid": 55.0})
    event_bus.publish(EVENT_GNSS_READY, {"latitude": 31.23, "longitude": 121.47, "speed_kmh": 12.5})
    event_bus.publish(EVENT_LIGHT_READY, {"light_intensity": 25000})
    pump_loop(init_order, event_bus, count=3)

    data = display.get_data()
    checks = [
        ("temp", 28.3),
        ("humid", 55.0),
        ("lat", 31.23),
        ("lon", 121.47),
        ("speed", 12.5),
        ("light_intensity", 25000),
    ]

    all_ok = True
    for key, expected in checks:
        actual = data.get(key)
        if actual == expected:
            print(f"  ✓ _data['{key}'] = {actual}")
        else:
            print(f"  ✗ _data['{key}'] 期望 {expected}, 实际 {actual}")
            all_ok = False

    return all_ok


def test_06_power_state_change():
    """
    brief 电源状态切换：验证 EVENT_POWER_STATE_CHANGE 在各模块中传播
    """
    event_bus, modules, init_order = make_system()

    init_all(event_bus, init_order)
    pump_loop(init_order, event_bus, count=2)

    # 发布省电模式切换
    event_bus.publish(EVENT_POWER_STATE_CHANGE, {
        "power_state": POWER_STATE_SUSPENDED,
        "source": "test",
    })
    pump_loop(init_order, event_bus, count=3)

    ok_count = 0
    total_checked = 0
    for name, mod in modules.items():
        # Button 没有省电模式，跳过
        if name == "button":
            continue
        ctx_state = mod.ctx.get("power_state", None)
        if ctx_state is not None:
            total_checked += 1
            if ctx_state == POWER_STATE_SUSPENDED:
                ok_count += 1
                print(f"  ✓ {name}.power_state = {ctx_state}")
            else:
                print(f"  ✗ {name}.power_state = {ctx_state} (期望 {POWER_STATE_SUSPENDED})")

    if total_checked == 0:
        print(f"  ⚠ 无模块支持 power_state（非致命）")
        return True

    all_ok = ok_count == total_checked
    print(f"  电源状态更新: {ok_count}/{total_checked} 模块正确")
    return all_ok


def test_07_main_loop_performance():
    """
    brief 主循环性能：运行 100 轮 tick + pump，验证每模块 tick() < 5ms
    """
    event_bus, modules, init_order = make_system()

    init_all(event_bus, init_order)
    pump_loop(init_order, event_bus, count=10)  # 预热

    cycles = 100
    total_start = time.ticks_ms()
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
            if elapsed > 5000:  # > 5000us = 5ms
                violations.append((mod.name, elapsed))
        event_bus.pump()
        time.sleep_ms(10)

    total_time = time.ticks_diff(time.ticks_ms(), total_start)
    avg_cycle = total_time / cycles if cycles > 0 else 0

    print(f"  总耗时: {total_time}ms, 平均每轮: {avg_cycle:.1f}ms")

    if not violations:
        print(f"  ✓ 所有 tick() < 5ms, 共 {cycles} 轮")
        return True
    else:
        for name, elapsed in violations[:10]:
            print(f"  ✗ {name}.tick() = {elapsed}us > 5000us")
        if len(violations) > 10:
            print(f"  ... 还有 {len(violations) - 10} 个超限")
        return False


def run_all():
    """
    brief 运行所有 7 个测试并输出摘要
    """
    print("=" * 60)
    print("  Step 1 基础系统验证 — 11 模块基线测试")
    print("=" * 60)

    tests = [
        ("test_01_all_modules_init", test_01_all_modules_init),
        ("test_02_sensor_data_events", test_02_sensor_data_events),
        ("test_03_collision_alarm_chain", test_03_collision_alarm_chain),
        ("test_04_alarm_cancel", test_04_alarm_cancel),
        ("test_05_display_update", test_05_display_update),
        ("test_06_power_state_change", test_06_power_state_change),
        ("test_07_main_loop_performance", test_07_main_loop_performance),
    ]

    results = {}
    for name, func in tests:
        print(f"\n--- {name} ---")
        try:
            ok = func()
            results[name] = ok
        except Exception as e:
            print(f"  ✗ 测试异常: {e}")
            results[name] = False

    # 摘要
    print("\n" + "=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"  测试摘要: {passed}/{total} 通过")
    for name, ok in results.items():
        print(f"    {name}: {'✓' if ok else '✗'}")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    run_all()
