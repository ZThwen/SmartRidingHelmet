"""
brief [Step 6] AudioService 集成测试 — 优先级队列调度验证
note 验证 AudioService 的 5 条调度规则：
       1. 高优先级打断低优先级（ALARM > NAV > CTRL）
       2. 同优先级覆盖当前
       3. 低优先级入队等待
       4. 报警期间拒绝非报警请求
       5. 队列上限 3 个，超时 5s 自动丢弃

运行方式:
  1. 上传到板子运行
  2. 观察串口输出，检查每个测试函数的 PASS/FAIL 标记
"""
import sys
import time

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TTS_REQUEST, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    PRIORITY_ALARM, PRIORITY_NAV, PRIORITY_CTRL,
)
from Modules.audio_service import AudioService


class FakeAudio:
    """模拟 AudioDriver，记录 play_tts/stop 调用"""

    def __init__(self):
        self.name = "fake_audio"
        self.ctx = {
            "is_init": True,
            "is_tts_playing": False,
            "is_playing": False,
            "alarm_playing": False,
        }
        self.tts_history = []
        self.stop_count = 0

    def play_tts(self, text):
        self.ctx["is_tts_playing"] = True
        self.tts_history.append(text)

    def stop(self):
        self.ctx["is_tts_playing"] = False
        self.stop_count += 1

    def get_data(self):
        return {"playback_status": "idle"}

    def deinit(self):
        pass


def make_system():
    bus = EventBus()
    audio = FakeAudio()
    svc = AudioService(bus, audio_driver=audio)
    svc.init()
    return bus, audio, svc


def pump_loop(bus, svc, count=3):
    for _ in range(count):
        svc.tick()
        bus.pump()
        time.sleep_ms(10)


def test_01_init():
    bus, audio, svc = make_system()
    ok = svc.ctx["is_init"]
    print("  init: is_init=%s" % ok)
    return ok


def test_02_high_priority_preempts_low():
    """高优先级(NAV)打断低优先级(CTRL)"""
    bus, audio, svc = make_system()

    bus.publish(EVENT_TTS_REQUEST, {"text": "控制反馈", "priority": PRIORITY_CTRL})
    pump_loop(bus, svc, count=2)
    assert audio.tts_history[-1] == "控制反馈"
    print("  CTRL播放中: %s" % audio.tts_history[-1])

    bus.publish(EVENT_TTS_REQUEST, {"text": "导航播报", "priority": PRIORITY_NAV})
    pump_loop(bus, svc, count=2)
    assert audio.stop_count >= 1, "应先 stop"
    assert audio.tts_history[-1] == "导航播报"
    print("  NAV打断CTRL, stop_count=%d, 最新=%s" % (audio.stop_count, audio.tts_history[-1]))
    return True


def test_03_same_priority_overwrites():
    """同优先级覆盖当前"""
    bus, audio, svc = make_system()

    bus.publish(EVENT_TTS_REQUEST, {"text": "导航A", "priority": PRIORITY_NAV})
    pump_loop(bus, svc, count=2)
    assert audio.tts_history[-1] == "导航A"

    bus.publish(EVENT_TTS_REQUEST, {"text": "导航B", "priority": PRIORITY_NAV})
    pump_loop(bus, svc, count=2)
    assert audio.tts_history[-1] == "导航B"
    print("  同优先级覆盖: A→B, stop_count=%d" % audio.stop_count)
    return True


def test_04_low_priority_enqueues():
    """低优先级入队等待"""
    bus, audio, svc = make_system()

    bus.publish(EVENT_TTS_REQUEST, {"text": "导航播报", "priority": PRIORITY_NAV})
    pump_loop(bus, svc, count=2)
    assert audio.tts_history[-1] == "导航播报"

    bus.publish(EVENT_TTS_REQUEST, {"text": "控制反馈", "priority": PRIORITY_CTRL})
    pump_loop(bus, svc, count=2)
    assert audio.tts_history[-1] == "导航播报", "CTRL 不应打断 NAV"
    assert svc._data["queue_size"] == 1, "CTRL 应入队"
    print("  低优先级入队: queue_size=%d, 当前播放=%s" % (svc._data["queue_size"], audio.tts_history[-1]))

    svc.ctx["current_priority"] = PRIORITY_CTRL + 1
    svc.ctx["err_count"] = 0
    svc.tick()
    pump_loop(bus, svc, count=2)
    assert audio.tts_history[-1] == "控制反馈"
    print("  播放结束后出队: 最新=%s" % audio.tts_history[-1])
    return True


def test_05_alarm_suppresses_non_alarm():
    """报警期间拒绝非报警请求"""
    bus, audio, svc = make_system()

    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision"})
    pump_loop(bus, svc, count=2)
    assert svc.ctx["alarm_playing"] is True

    bus.publish(EVENT_TTS_REQUEST, {"text": "控制反馈", "priority": PRIORITY_CTRL})
    pump_loop(bus, svc, count=2)
    assert svc._data["total_dropped"] >= 1
    print("  报警期间 CTRL 被拒: dropped=%d" % svc._data["total_dropped"])

    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, svc, count=2)
    assert svc.ctx["alarm_playing"] is False

    bus.publish(EVENT_TTS_REQUEST, {"text": "控制反馈", "priority": PRIORITY_CTRL})
    pump_loop(bus, svc, count=2)
    assert audio.tts_history[-1] == "控制反馈"
    print("  报警取消后 TTS 恢复: %s" % audio.tts_history[-1])
    return True


def test_06_queue_overflow():
    """队列满时丢弃最旧"""
    bus, audio, svc = make_system()

    bus.publish(EVENT_TTS_REQUEST, {"text": "导航播报", "priority": PRIORITY_NAV})
    pump_loop(bus, svc, count=2)

    for i in range(5):
        bus.publish(EVENT_TTS_REQUEST, {"text": "控制%d" % i, "priority": PRIORITY_CTRL})
        pump_loop(bus, svc, count=1)

    queue_size = len(svc._queue)
    print("  队列: size=%d, max=%d, dropped=%d" % (queue_size, svc.cfg["queue_max_size"], svc._data["total_dropped"]))
    return queue_size <= svc.cfg["queue_max_size"]


def test_07_queue_timeout():
    """队列项超时 5s 自动丢弃"""
    bus, audio, svc = make_system()

    bus.publish(EVENT_TTS_REQUEST, {"text": "导航播报", "priority": PRIORITY_NAV})
    pump_loop(bus, svc, count=2)

    svc._queue.append({
        "text": "过期项",
        "priority": PRIORITY_CTRL,
        "enqueue_time": time.ticks_ms() - 6000,
    })
    svc._data["queue_size"] = len(svc._queue)
    print("  添加过期项: queue_size=%d" % len(svc._queue))

    svc.tick()
    pump_loop(bus, svc, count=2)
    print("  tick后: queue_size=%d, dropped=%d" % (len(svc._queue), svc._data["total_dropped"]))
    return len(svc._queue) == 0


def test_08_alarm_clears_non_alarm_queue():
    """报警触发时清空非报警队列"""
    bus, audio, svc = make_system()

    bus.publish(EVENT_TTS_REQUEST, {"text": "导航播报", "priority": PRIORITY_NAV})
    pump_loop(bus, svc, count=2)
    svc._queue.append({
        "text": "排队控制",
        "priority": PRIORITY_CTRL,
        "enqueue_time": time.ticks_ms(),
    })
    svc._data["queue_size"] = len(svc._queue)
    print("  报警前: queue_size=%d" % len(svc._queue))

    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision"})
    pump_loop(bus, svc, count=2)
    print("  报警后: queue_size=%d, alarm_playing=%s" % (len(svc._queue), svc.ctx["alarm_playing"]))
    return len(svc._queue) == 0


def run_all():
    print("=" * 60)
    print("  Step 6 AudioService 集成测试")
    print("=" * 60)

    tests = [
        ("test_01_init", test_01_init),
        ("test_02_high_priority_preempts_low", test_02_high_priority_preempts_low),
        ("test_03_same_priority_overwrites", test_03_same_priority_overwrites),
        ("test_04_low_priority_enqueues", test_04_low_priority_enqueues),
        ("test_05_alarm_suppresses_non_alarm", test_05_alarm_suppresses_non_alarm),
        ("test_06_queue_overflow", test_06_queue_overflow),
        ("test_07_queue_timeout", test_07_queue_timeout),
        ("test_08_alarm_clears_non_alarm_queue", test_08_alarm_clears_non_alarm_queue),
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
