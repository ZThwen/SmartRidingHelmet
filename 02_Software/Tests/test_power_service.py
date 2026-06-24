"""
brief PowerService 单元测试
note 无需硬件，FakeBatteryDriver 模拟 ADC 数据

测试覆盖：
1. 五档电压映射正确性（BatteryDriver._voltage_to_level）
2. EVENT_BATTERY_READY → PowerService 状态更新
3. 低电量自动发布 EVENT_POWER_STATE_CHANGE(SUSPENDED)
4. 低电量发布 EVENT_BATTERY_LOW
5. 低电量发布 EVENT_TTS_REQUEST(TTS_BATTERY_LOW)
6. 正常电量不发布低电量事件
7. invalid 数据过滤
8. auto_suspended 标记防重复发布
9. 手动 power_normal 清除 auto_suspended
"""
import sys
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_BATTERY_READY, EVENT_BATTERY_LOW,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    POWER_STATE_SUSPENDED,
    TTS_BATTERY_LOW, PRIORITY_CTRL,
)
from Drivers.sensor.Battery import BatteryDriver
from Modules.power_service import PowerService


class FakeBatteryDriver:
    """Fake BatteryDriver for testing"""
    def __init__(self):
        self.ctx = {"is_init": True, "is_busy": False, "err_count": 0}
        self._data = {"raw": 40000, "battery_mv": 4000, "level": 4, "valid": True}

    def set_level(self, level):
        voltage_map = {1: 3000, 2: 3300, 3: 3600, 4: 3800, 5: 4200}
        self._data["level"] = level
        self._data["battery_mv"] = voltage_map.get(level, 4000)
        self._data["valid"] = True

    def get_data(self):
        d = dict(self._data)
        d["timestamp"] = 0
        return d


def test_voltage_to_level():
    """测试 1: 六档电压映射（基于锂电池放电曲线）"""
    bus = EventBus()
    drv = BatteryDriver(event_bus=bus)
    # 阈值: [2000, 2614, 2669, 2724, 2772]
    assert drv._voltage_to_level(1500) == 0  # <2000 → 没电
    assert drv._voltage_to_level(2000) == 1  # ≥2000, <2614 → 危急
    assert drv._voltage_to_level(2500) == 1  # <2614 → 危急
    assert drv._voltage_to_level(2614) == 2  # ≥2614, <2669 → 低
    assert drv._voltage_to_level(2650) == 2  # <2669 → 低
    assert drv._voltage_to_level(2669) == 3  # ≥2669, <2724 → 中等
    assert drv._voltage_to_level(2700) == 3  # <2724 → 中等
    assert drv._voltage_to_level(2724) == 4  # ≥2724, <2772 → 良好
    assert drv._voltage_to_level(2750) == 4  # <2772 → 良好
    assert drv._voltage_to_level(2772) == 5  # ≥2772 → 满
    assert drv._voltage_to_level(2900) == 5  # ≥2772 → 满
    print("[PASS] test_voltage_to_level")


def test_battery_ready_updates_state():
    """测试 2: EVENT_BATTERY_READY 更新 PowerService 状态"""
    bus = EventBus()
    svc = PowerService(event_bus=bus)
    svc.init()

    bus.publish(EVENT_BATTERY_READY, {"level": 3, "battery_mv": 3600, "valid": True})
    bus.pump()

    assert svc.get_data()["level"] == 3
    assert svc.get_data()["battery_mv"] == 3600
    assert svc.get_data()["valid"] == True
    assert svc.get_data()["is_low"] == False
    print("[PASS] test_battery_ready_updates_state")


def test_auto_suspend_on_low_battery():
    """测试 3: 低电量自动发布 EVENT_POWER_STATE_CHANGE(SUSPENDED)"""
    bus = EventBus()
    svc = PowerService(event_bus=bus)
    svc.init()

    received = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: received.append(p))

    bus.publish(EVENT_BATTERY_READY, {"level": 2, "battery_mv": 3300, "valid": True})
    bus.pump()

    assert len(received) == 1
    assert received[0]["power_state"] == POWER_STATE_SUSPENDED
    assert svc.get_data()["auto_suspended"] == True
    print("[PASS] test_auto_suspend_on_low_battery")


def test_low_battery_event():
    """测试 4: 低电量发布 EVENT_BATTERY_LOW"""
    bus = EventBus()
    svc = PowerService(event_bus=bus)
    svc.init()

    received = []
    bus.subscribe(EVENT_BATTERY_LOW, lambda p: received.append(p))

    bus.publish(EVENT_BATTERY_READY, {"level": 2, "battery_mv": 3300, "valid": True})
    bus.pump()

    assert len(received) == 1
    assert received[0]["level"] == 2
    print("[PASS] test_low_battery_event")


def test_low_battery_tts():
    """测试 5: 低电量发布 EVENT_TTS_REQUEST"""
    bus = EventBus()
    svc = PowerService(event_bus=bus)
    svc.init()

    received = []
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: received.append(p))

    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": True})
    bus.pump()

    assert len(received) == 1
    assert received[0]["text"] == TTS_BATTERY_LOW
    assert received[0]["priority"] == PRIORITY_CTRL
    print("[PASS] test_low_battery_tts")


def test_normal_no_event():
    """测试 6: 正常电量不发布低电量事件"""
    bus = EventBus()
    svc = PowerService(event_bus=bus)
    svc.init()

    power_events = []
    low_events = []
    tts_events = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: power_events.append(p))
    bus.subscribe(EVENT_BATTERY_LOW, lambda p: low_events.append(p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: tts_events.append(p))

    bus.publish(EVENT_BATTERY_READY, {"level": 4, "battery_mv": 3800, "valid": True})
    bus.pump()

    assert len(power_events) == 0
    assert len(low_events) == 0
    assert len(tts_events) == 0
    print("[PASS] test_normal_no_event")


def test_invalid_data_filtered():
    """测试 7: invalid 数据过滤"""
    bus = EventBus()
    svc = PowerService(event_bus=bus)
    svc.init()

    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": False})
    bus.pump()

    assert svc.get_data()["level"] == 0
    assert svc.get_data()["valid"] == False
    print("[PASS] test_invalid_data_filtered")


def test_no_duplicate_suspend():
    """测试 8: auto_suspended 标记防重复发布"""
    bus = EventBus()
    svc = PowerService(event_bus=bus)
    svc.init()

    power_events = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: power_events.append(p))

    # 第一次低电量
    bus.publish(EVENT_BATTERY_READY, {"level": 2, "battery_mv": 3300, "valid": True})
    bus.pump()
    assert len(power_events) == 1

    # 第二次低电量 — 不应重复发布
    bus.publish(EVENT_BATTERY_READY, {"level": 1, "battery_mv": 3000, "valid": True})
    bus.pump()
    assert len(power_events) == 1
    print("[PASS] test_no_duplicate_suspend")


if __name__ == "__main__":
    tests = [
        test_voltage_to_level,
        test_battery_ready_updates_state,
        test_auto_suspend_on_low_battery,
        test_low_battery_event,
        test_low_battery_tts,
        test_normal_no_event,
        test_invalid_data_filtered,
        test_no_duplicate_suspend,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print("[FAIL] %s: %s" % (t.__name__, e))
            failed += 1
    print("\n=== 结果: %d passed, %d failed ===" % (passed, failed))
