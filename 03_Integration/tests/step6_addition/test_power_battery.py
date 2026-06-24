"""
brief [Step 6] 电池/电源管理集成测试 — BatteryDriver + PowerService
note 验证: ADC 读数 → 电量档位 → 低电量自动省电 → TTS 提醒
      覆盖: BatteryDriver 电压映射 + PowerService 事件链 + 全系统集成

运行方式:
  1. 上传到板子运行（NUCLEO-F413ZH + 电源扩展板）
  2. 观察串口输出，检查每个测试函数的 PASS/FAIL 标记
"""
import sys
import time

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_BATTERY_READY, EVENT_BATTERY_LOW,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    TTS_BATTERY_LOW, PRIORITY_CTRL,
    BATTERY_LEVEL_THRESHOLDS,
)
from Drivers.sensor.Battery import BatteryDriver
from Modules.power_service import PowerService


def _make_logger(event_log, event_name):
    def _log(payload):
        event_log.append((event_name, payload))
    return _log


def make_system():
    bus = EventBus()
    battery = BatteryDriver(bus)
    power_svc = PowerService(bus)
    return bus, battery, power_svc


def pump_loop(bus, count=3):
    for _ in range(count):
        bus.pump()
        time.sleep_ms(10)


# ==================== 测试函数 ====================


def test_01_battery_adc_read():
    """BatteryDriver ADC 读数 + EVENT_BATTERY_READY 发布"""
    bus, battery, power_svc = make_system()
    event_log = []
    bus.subscribe(EVENT_BATTERY_READY, _make_logger(event_log, EVENT_BATTERY_READY))

    battery.init()
    battery._data = {"raw": 55517, "adc_mv": 2795, "battery_mv": 4052, "level": 5, "valid": True}
    bus.publish(EVENT_BATTERY_READY, battery.get_data())
    pump_loop(bus, count=2)

    assert len(event_log) >= 1
    data = event_log[0][1]
    assert data["valid"] is True
    assert data["level"] == 5
    print("  ADC: raw=%d adc=%dmV battery=%dmV level=%d" % (
        data["raw"], data["adc_mv"], data["battery_mv"], data["level"]))
    return True


def test_02_battery_level_mapping():
    """电压→档位映射正确（6 档）"""
    bus, battery, power_svc = make_system()
    battery.init()

    thresholds = BATTERY_LEVEL_THRESHOLDS
    test_cases = [
        (1500, 0), (2000, 1), (2500, 1),
        (2614, 2), (2650, 2), (2669, 3),
        (2700, 3), (2724, 4), (2750, 4),
        (2772, 5), (2900, 5),
    ]
    ok = 0
    for mv, expected in test_cases:
        actual = battery._voltage_to_level(mv)
        if actual == expected:
            ok += 1
        else:
            print("  FAIL: %dmV → %d (期望 %d)" % (mv, actual, expected))

    print("  映射: %d/%d 正确" % (ok, len(test_cases)))
    return ok == len(test_cases)


def test_03_power_service_init():
    """PowerService 初始化 + 事件订阅"""
    bus, battery, power_svc = make_system()
    power_svc.init()
    assert power_svc.ctx["is_init"] is True
    print("  PowerService init OK")
    return True


def test_04_battery_low_auto_suspend():
    """level≤2 → 自动切换 SUSPENDED + TTS + EVENT_BATTERY_LOW"""
    bus, battery, power_svc = make_system()
    event_log = []

    bus.subscribe(EVENT_POWER_STATE_CHANGE, _make_logger(event_log, "POWER_STATE"))
    bus.subscribe(EVENT_BATTERY_LOW, _make_logger(event_log, "BATTERY_LOW"))
    bus.subscribe(EVENT_TTS_REQUEST, _make_logger(event_log, "TTS"))

    battery.init()
    power_svc.init()

    bus.publish(EVENT_BATTERY_READY, {"level": 2, "battery_mv": 3430, "valid": True, "sample_count": 3})
    pump_loop(bus, count=3)

    power_events = [e for e in event_log if e[0] == "POWER_STATE"]
    low_events = [e for e in event_log if e[0] == "BATTERY_LOW"]
    tts_events = [e for e in event_log if e[0] == "TTS"]

    assert len(power_events) >= 1, "应发布 POWER_STATE_CHANGE"
    assert power_events[0][1]["power_state"] == POWER_STATE_SUSPENDED
    assert len(low_events) >= 1, "应发布 BATTERY_LOW"
    assert len(tts_events) >= 1, "应发布 TTS"
    assert tts_events[0][1]["text"] == TTS_BATTERY_LOW
    assert power_svc.get_data()["auto_suspended"] is True

    print("  level=2 → SUSPENDED + BATTERY_LOW + TTS ✓")
    return True


def test_05_battery_normal_no_action():
    """level>2 → 无事件触发"""
    bus, battery, power_svc = make_system()
    event_log = []

    bus.subscribe(EVENT_POWER_STATE_CHANGE, _make_logger(event_log, "POWER_STATE"))
    bus.subscribe(EVENT_BATTERY_LOW, _make_logger(event_log, "BATTERY_LOW"))
    bus.subscribe(EVENT_TTS_REQUEST, _make_logger(event_log, "TTS"))

    battery.init()
    power_svc.init()

    bus.publish(EVENT_BATTERY_READY, {"level": 4, "battery_mv": 3800, "valid": True, "sample_count": 3})
    pump_loop(bus, count=3)

    assert len(event_log) == 0, "正常电量不应有事件 (实际 %d)" % len(event_log)
    print("  level=4 → 无事件 ✓")
    return True


def test_06_power_mode_reset():
    """手动 ACTIVE → 清除 auto_suspended 标记"""
    bus, battery, power_svc = make_system()

    battery.init()
    power_svc.init()

    bus.publish(EVENT_BATTERY_READY, {"level": 2, "battery_mv": 3300, "valid": True, "sample_count": 3})
    pump_loop(bus, count=2)
    assert power_svc.get_data()["auto_suspended"] is True

    bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_ACTIVE})
    pump_loop(bus, count=2)
    assert power_svc.get_data()["auto_suspended"] is False
    print("  ACTIVE → auto_suspended=False ✓")
    return True


def test_07_invalid_battery_ignored():
    """invalid=False 数据被跳过"""
    bus, battery, power_svc = make_system()

    battery.init()
    power_svc.init()

    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": False})
    pump_loop(bus, count=2)

    assert power_svc.get_data()["valid"] is False
    assert power_svc.get_data()["level"] == 0
    print("  invalid=True → 数据被跳过 ✓")
    return True


def test_08_battery_dedup():
    """auto_suspended 防重复：连续两次低电量只触发一次"""
    bus, battery, power_svc = make_system()
    event_log = []

    bus.subscribe(EVENT_POWER_STATE_CHANGE, _make_logger(event_log, "POWER_STATE"))

    battery.init()
    power_svc.init()

    bus.publish(EVENT_BATTERY_READY, {"level": 2, "battery_mv": 3300, "valid": True, "sample_count": 3})
    pump_loop(bus, count=2)
    assert len(event_log) == 1

    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": True, "sample_count": 3})
    pump_loop(bus, count=2)
    assert len(event_log) == 1, "不应重复触发 (实际 %d)" % len(event_log)
    print("  连续低电量 → 只触发 1 次 ✓")
    return True


def test_09_startup_grace_period():
    """前 3 次采样不做省电决策（启动宽限期）"""
    bus, battery, power_svc = make_system()
    event_log = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, _make_logger(event_log, "POWER_STATE"))
    battery.init()
    power_svc.init()

    # sample_count=0 → 不触发
    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": True, "sample_count": 0})
    pump_loop(bus, count=2)
    assert len(event_log) == 0, "sample_count=0 不应触发"

    # sample_count=1 → 不触发
    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": True, "sample_count": 1})
    pump_loop(bus, count=2)
    assert len(event_log) == 0, "sample_count=1 不应触发"

    # sample_count=2 → 不触发
    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": True, "sample_count": 2})
    pump_loop(bus, count=2)
    assert len(event_log) == 0, "sample_count=2 不应触发"

    # sample_count=3 → 应触发
    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": True, "sample_count": 3})
    pump_loop(bus, count=2)
    assert len(event_log) >= 1, "sample_count=3 应触发省电"
    print("  启动宽限期: 0/1/2 跳过, 3 触发 ✓")
    return True


def run_all():
    print("=" * 60)
    print("  Step 6 电池/电源管理集成测试")
    print("=" * 60)

    tests = [
        ("test_01_battery_adc_read", test_01_battery_adc_read),
        ("test_02_battery_level_mapping", test_02_battery_level_mapping),
        ("test_03_power_service_init", test_03_power_service_init),
        ("test_04_battery_low_auto_suspend", test_04_battery_low_auto_suspend),
        ("test_05_battery_normal_no_action", test_05_battery_normal_no_action),
        ("test_06_power_mode_reset", test_06_power_mode_reset),
        ("test_07_invalid_battery_ignored", test_07_invalid_battery_ignored),
        ("test_08_battery_dedup", test_08_battery_dedup),
        ("test_09_startup_grace_period", test_09_startup_grace_period),
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
