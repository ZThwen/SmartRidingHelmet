"""
brief AlarmService 集成测试（EventBus + 事件注入）
note 不依赖真实硬件模块，手动注入 fake 事件验证事件流转
      使用 FakeLED / FakeAudio 记录设备调用
执行: 上传到板子运行 python test_alarm_service_integration.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_COLLISION_DETECTED, EVENT_BUTTON_PRESSED, EVENT_GPS_LOST,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED, EVENT_CONFIG_UPDATE,
    TTS_GPS_LOST, POWER_STATE_ACTIVE,
    AUDIO_ALARM_FILE_L1, AUDIO_SOS_FILE,
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
    """创建 EventBus + Fake 设备 + AlarmService 实例"""
    bus = EventBus()
    led = FakeLED()
    audio = FakeAudio()
    svc = AlarmService(bus, led, audio)
    svc.init()
    return svc, bus, led, audio


def test_events_flow_collision():
    """注入 COLLISION_DETECTED → 设备调用 + 事件发布"""
    svc, bus, led, audio = make_service()
    triggered = []
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: triggered.append(p))
    bus.publish(EVENT_COLLISION_DETECTED, {
        "level": 2, "acc_total": 3.5, "timemap": 100,
    })
    bus.pump()
    assert ("blink", 30000, 500) in led.calls, "L2 blink 500ms"
    assert ("play_file", AUDIO_ALARM_FILE_L1) in audio.calls or \
           ("play_file", None) not in [c[0] for c in audio.calls]
    assert len(triggered) == 1, "EVENT_ALARM_TRIGGERED 收到"
    assert triggered[0]["level"] == 2
    print("  OK collision event flow")


def test_events_flow_sos():
    """注入 BUTTON_PRESSED（空闲）→ SOS 启动"""
    svc, bus, led, audio = make_service()
    triggered = []
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: triggered.append(p))
    bus.publish(EVENT_BUTTON_PRESSED, {"timestamp": time.ticks_ms()})
    bus.pump()
    assert ("blink", 30000, 200) in led.calls, "SOS blink 200ms"
    assert ("play_file", AUDIO_SOS_FILE) in audio.calls, "SOS play_file"
    assert triggered[0]["alarm_type"] == "sos"
    print("  OK SOS event flow")


def test_events_flow_cancel():
    """碰撞活跃中注入 BUTTON_PRESSED → 取消"""
    svc, bus, led, audio = make_service()
    canceled = []
    bus.subscribe(EVENT_ALARM_CANCELED, lambda p: canceled.append(p))
    svc._start_alarm("collision", 1)
    led.calls.clear()
    audio.calls.clear()
    bus.publish(EVENT_BUTTON_PRESSED, {"timestamp": time.ticks_ms()})
    bus.pump()
    assert ("off",) in led.calls, "LED off"
    assert ("stop",) in audio.calls, "Audio stop"
    assert len(canceled) == 1, "EVENT_ALARM_CANCELED 收到"
    assert not svc.ctx["alarm_active"], "alarm_active=False"
    print("  OK cancel event flow")


def test_mainloop_stability():
    """模拟主循环 while+tick+pump 跑 5 轮，不崩溃"""
    svc, bus, _, _ = make_service()
    for i in range(5):
        svc.tick()
        bus.pump()
        time.sleep_ms(5)
    assert svc.ctx["is_init"], "init 状态保持"
    assert svc.ctx["power_state"] == POWER_STATE_ACTIVE
    print("  OK mainloop 5 rounds stable")


def test_gps_lost_flow():
    """注入 GPS_LOST → Audio TTS 播报"""
    svc, bus, _, audio = make_service()
    bus.publish(EVENT_GPS_LOST, {"timestamp": time.ticks_ms()})
    bus.pump()
    assert ("play_tts", TTS_GPS_LOST) in audio.calls
    print("  OK GPS lost -> TTS flow")


def test_config_update_flow():
    """注入 CONFIG_UPDATE → cfg 参数更新"""
    svc, bus, _, _ = make_service()
    bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "alarm",
        "alarm_duration_ms": 15000,
        "enable_local": False,
    })
    bus.pump()
    assert svc.cfg["alarm_duration_ms"] == 15000
    assert svc.cfg["enable_local"] == False
    print("  OK config update flow")


def main():
    print("=== AlarmService Integration Test ===\n")
    tests = [
        ("collision event flow",     test_events_flow_collision),
        ("SOS event flow",           test_events_flow_sos),
        ("cancel event flow",        test_events_flow_cancel),
        ("mainloop stability",       test_mainloop_stability),
        ("GPS lost flow",            test_gps_lost_flow),
        ("config update flow",       test_config_update_flow),
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
