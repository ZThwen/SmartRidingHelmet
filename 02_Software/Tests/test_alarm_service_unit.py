"""
brief AlarmService 单模块测试（纯 fake 数据）
note 不依赖真实 LED/Audio 硬件，使用 Fake 对象记录调用
      12 项测试覆盖碰撞/SOS/取消/超时/GPS/电池/功耗守卫
执行: 上传到板子运行 python test_alarm_service_unit.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_COLLISION_DETECTED, EVENT_BUTTON_PRESSED, EVENT_GPS_LOST,
    TTS_GPS_LOST,
    AUDIO_ALARM_FILE_L1, AUDIO_ALARM_FILE_L2, AUDIO_ALARM_FILE_L3,
    AUDIO_SOS_FILE, POWER_STATE_SUSPENDED,
)
from Modules.alarm_service import AlarmService


class FakeLED:
    def __init__(self):
        self.calls = []
    def blink(self, d, i):
        self.calls.append(("blink", d, i))
    def on(self):
        self.calls.append(("on",))
    def off(self):
        self.calls.append(("off",))


class FakeAudio:
    def __init__(self):
        self.calls = []
    def play_file(self, p):
        self.calls.append(("play_file", p))
    def play_tts(self, t):
        self.calls.append(("play_tts", t))
    def stop(self):
        self.calls.append(("stop",))


def make_service():
    """创建已 init 的 AlarmService 及 Fake 设备（供测试用）"""
    bus = EventBus()
    led = FakeLED()
    audio = FakeAudio()
    svc = AlarmService(bus, led, audio)
    svc.ctx["is_init"] = True
    return svc, bus, led, audio


# ==================== 测试用例 ====================

def test_collision_level1():
    """碰撞 Lv1 → LED blink(30000,1000), Audio play_file(L1)"""
    svc, _, led, audio = make_service()
    svc._on_collision({"level": 1, "acc_total": 3.0, "timemap": 100})
    assert ("blink", 30000, 1000) in led.calls, "L1 blink interval 1000"
    assert ("play_file", AUDIO_ALARM_FILE_L1) in audio.calls, "L1 play_file"
    print("  OK collision Lv1")


def test_collision_level3_upgrade():
    """碰撞 Lv3 → alarm_type=sos, blink(30000,200), play_file(L3)"""
    svc, bus, led, audio = make_service()
    captured = []
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: captured.append(p))
    svc._on_collision({"level": 3, "acc_total": 5.0, "timemap": 100})
    bus.pump()
    assert ("blink", 30000, 200) in led.calls, "L3 blink 200ms"
    assert ("play_file", AUDIO_SOS_FILE) in audio.calls, "L3 play_file(SOS)"
    assert len(captured) == 1, "EVENT_ALARM_TRIGGERED 发布"
    assert captured[0]["alarm_type"] == "sos", "L3 alarm_type=sos"
    assert captured[0]["level"] == 3, "L3 level=3"
    print("  OK collision Lv3 -> sos")


def test_button_sos_when_idle():
    """空闲按 SW 按钮 → SOS: blink(30000,200), play_file(sos)"""
    svc, _, led, audio = make_service()
    svc._on_button_press({"timestamp": time.ticks_ms()})
    assert ("blink", 30000, 200) in led.calls, "SOS blink 200ms"
    assert ("play_file", AUDIO_SOS_FILE) in audio.calls, "SOS play_file"
    print("  OK button -> SOS when idle")


def test_button_cancel_when_alarming():
    """报警中按 SW 按钮 → 取消: off + stop + publish CANCELED"""
    svc, bus, led, audio = make_service()
    captured = []
    bus.subscribe(EVENT_ALARM_CANCELED, lambda p: captured.append(p))
    svc._start_alarm("collision", 1)
    led.calls.clear()
    audio.calls.clear()
    svc._on_button_press({"timestamp": time.ticks_ms()})
    bus.pump()
    assert ("off",) in led.calls, "LED off"
    assert ("stop",) in audio.calls, "Audio stop"
    assert len(captured) == 1, "EVENT_ALARM_CANCELED 发布"
    assert not svc.ctx["alarm_active"], "alarm_active=False"
    print("  OK button -> cancel when alarming")


def test_same_level_refresh():
    """同类型 Lv1 活跃中再来 Lv1 → 只刷新 timer, 不重调硬件"""
    svc, _, led, audio = make_service()
    svc._start_alarm("collision", 1)
    old_start = svc.ctx["alarm_start"]
    led.calls.clear()
    audio.calls.clear()
    time.sleep_ms(5)
    svc._start_alarm("collision", 1)
    assert len(led.calls) == 0, "LED 不应被再次调用"
    assert len(audio.calls) == 0, "Audio 不应被再次调用"
    assert svc.ctx["alarm_start"] != old_start, "timer 应被刷新"
    print("  OK same level refresh timer")


def test_button_cancel_when_alarming():
    """碰撞中按按钮 → 取消：alarm_active=False, type 清空"""
    svc, _, _, _ = make_service()
    svc._start_alarm("collision", 1)
    assert svc.ctx["alarm_type"] == "collision"
    assert svc.ctx["alarm_active"]
    svc._on_button_press({"timestamp": time.ticks_ms()})
    assert not svc.ctx["alarm_active"], "报警中按=取消"
    assert svc.ctx["alarm_type"] == "", "alarm_type 清空"
    print("  OK button cancels collision alarm")


def test_tick_timeout():
    """alarm_start 设置到 31s 前 → tick() → 取消"""
    svc, bus, led, audio = make_service()
    captured = []
    bus.subscribe(EVENT_ALARM_CANCELED, lambda p: captured.append(p))
    svc._start_alarm("collision", 1)
    svc.ctx["alarm_start"] = time.ticks_ms() - 31000
    svc.tick()
    bus.pump()
    assert ("off",) in led.calls, "LED off"
    assert ("stop",) in audio.calls, "Audio stop"
    assert len(captured) == 1, "EVENT_ALARM_CANCELED 发布"
    assert not svc.ctx["alarm_active"], "alarm_active=False"
    print("  OK tick timeout -> cancel")


def test_publish_alarm_triggered():
    """_start_alarm → EVENT_ALARM_TRIGGERED payload 正确"""
    svc, bus, _, _ = make_service()
    captured = []
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: captured.append(p))
    svc._start_alarm("collision", 2)
    bus.pump()
    assert len(captured) == 1
    p = captured[0]
    assert p["alarm_type"] == "collision"
    assert p["level"] == 2
    assert "timestamp" in p
    print("  OK EVENT_ALARM_TRIGGERED payload")


def test_publish_alarm_canceled():
    """_cancel_alarm → EVENT_ALARM_CANCELED payload 正确"""
    svc, bus, _, _ = make_service()
    captured = []
    bus.subscribe(EVENT_ALARM_CANCELED, lambda p: captured.append(p))
    svc._start_alarm("sos", 3)
    svc._cancel_alarm()
    bus.pump()
    assert len(captured) == 1
    p = captured[0]
    assert "duration" in p
    assert "timestamp" in p
    print("  OK EVENT_ALARM_CANCELED payload")


def test_gps_lost_tts():
    """GPS 丢失 → audio.play_tts(TTS_GPS_LOST)"""
    svc, _, _, audio = make_service()
    svc._on_gps_lost({"timestamp": time.ticks_ms()})
    assert ("play_tts", TTS_GPS_LOST) in audio.calls
    print("  OK GPS lost -> TTS")


def test_battery_stubs():
    """电池事件 stub → 不抛异常、不调硬件"""
    svc, _, led, audio = make_service()
    svc._on_battery_low({"timestamp": time.ticks_ms()})
    svc._on_battery_critical({"timestamp": time.ticks_ms()})
    assert len(led.calls) == 0, "电池 stub 不应调 LED"
    assert len(audio.calls) == 0, "电池 stub 不应调 Audio"
    print("  OK battery stubs")


def test_power_guard():
    """power_state=SUSPENDED → tick 不执行 cancel"""
    svc, bus, _, _ = make_service()
    svc._start_alarm("collision", 1)
    svc.ctx["power_state"] = POWER_STATE_SUSPENDED
    svc.ctx["alarm_start"] = time.ticks_ms() - 31000
    svc.tick()
    assert svc.ctx["alarm_active"], "SUSPENDED 时不应取消"
    print("  OK power guard")


# ==================== 主函数 ====================

def main():
    print("=== AlarmService Unit Test ===\n")
    tests = [
        ("collision Lv1",             test_collision_level1),
        ("collision Lv3 -> sos",      test_collision_level3_upgrade),
        ("button SOS when idle",      test_button_sos_when_idle),
        ("button cancel when alarming", test_button_cancel_when_alarming),
        ("same level refresh",        test_same_level_refresh),
        ("tick timeout",              test_tick_timeout),
        ("publish ALARM_TRIGGERED",   test_publish_alarm_triggered),
        ("publish ALARM_CANCELED",    test_publish_alarm_canceled),
        ("GPS lost TTS",              test_gps_lost_tts),
        ("battery stubs",             test_battery_stubs),
        ("power guard",               test_power_guard),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            import sys
            print("  X %s: %s" % (name, e))
    print("\nResult: %s/%s passed" % (passed, len(tests)))


if __name__ == "__main__":
    main()
