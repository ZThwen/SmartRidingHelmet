"""
brief SMS 集成环境测试
note 验证 SMS 功能的完整事件链路
      使用 Fake 硬件，EventBus 真实
"""
import sys
import time
sys.path.append("..")

# CPython compatibility
if not hasattr(time, "ticks_ms"):
    time.ticks_ms = lambda: int(time.time() * 1000)
if not hasattr(time, "ticks_diff"):
    time.ticks_diff = lambda a, b: a - b
if not hasattr(time, "sleep_ms"):
    time.sleep_ms = lambda ms: time.sleep(ms / 1000)

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_COLLISION_DETECTED,
    EVENT_SMS_PHONE_CONFIG, EVENT_GNSS_READY,
    EVENT_CONTROL_STATE_CHANGED,
)
from Modules.control_service import ControlService
from Modules.alarm_service import AlarmService


class _FakeLED:
    def __init__(self):
        self.calls = []
    def init(self):
        return True
    def tick(self):
        pass
    def get_data(self):
        return {}
    def on(self):
        self.calls.append(("on",))
    def off(self):
        self.calls.append(("off",))
    def blink(self, d, i):
        self.calls.append(("blink", d, i))


class _FakeAudio:
    def __init__(self):
        self.calls = []
    def init(self):
        return True
    def tick(self):
        pass
    def get_data(self):
        return {}
    def play_file(self, f):
        self.calls.append(("play_file", f))
    def play_tts(self, t):
        self.calls.append(("play_tts", t))
    def stop(self):
        self.calls.append(("stop",))
    def set_volume(self, v):
        pass
    def get_volume(self):
        return 5


class _FakeSMS:
    def __init__(self):
        self.calls = []
    def init(self):
        return True
    def tick(self):
        pass
    def get_data(self):
        return {}
    def send_sms(self, phone, message):
        self.calls.append(("send_sms", phone, message))
        return True


pass_count = 0
fail_count = 0


def _pump(bus, count=5, interval_ms=10):
    for _ in range(count):
        bus.pump()
        time.sleep_ms(interval_ms)


def _wait_for_thread():
    # SMS.send_sms runs in a real background thread via _thread.start_new_thread
    # Give it time to execute before assertions
    time.sleep_ms(100)


def _report(name, passed, detail=""):
    global pass_count, fail_count
    mark = "✓" if passed else "✗"
    if passed:
        pass_count += 1
    else:
        fail_count += 1
    print("  %s %s%s" % (mark, name, (" -- " + detail) if detail else ""))


def run_all_tests():
    global pass_count, fail_count
    pass_count = 0
    fail_count = 0

    print("=" * 60)
    print("SMS 集成环境测试")
    print("=" * 60)

    # ---- 步骤1: 创建 EventBus ----
    print("\n[步骤 1] 创建事件总线")
    bus = EventBus()
    print("  ✓ EventBus 已创建")

    # ---- 步骤2: 创建 Fake 设备 ----
    print("\n[步骤 2] 创建 Fake 设备")
    fake_led = _FakeLED()
    fake_audio = _FakeAudio()
    fake_sms = _FakeSMS()
    print("  ✓ FakeLED, FakeAudio, FakeSMS 已创建")

    # ---- 步骤3: 创建并初始化模块 ----
    print("\n[步骤 3] 创建并初始化模块")
    ctrl = ControlService(event_bus=bus)
    alarm = AlarmService(event_bus=bus, led=fake_led, audio=fake_audio, sms=fake_sms)
    ctrl.init()
    alarm.init()
    _report("ControlService 初始化", ctrl.ctx["is_init"])
    _report("AlarmService 初始化", alarm.ctx["is_init"])

    # 订阅事件用于验证
    received_events = []

    def _on_event(event, payload):
        received_events.append((event, payload))

    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, _on_event)

    # ========================================================
    print("\n" + "=" * 60)
    print("[测试 1] 手机号配置事件流转")
    print("=" * 60)
    # BLE -> ControlService -> EVENT_SMS_PHONE_CONFIG -> AlarmService._sms_phone
    raw_cmd = '{"a":"ctrl","d":{"cmd":"set_phone","phone":"13800138000"}}'
    ctrl.ctx["last_cmd_tick"] = 0
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw_cmd})
    _pump(bus)

    _report("AlarmService 接收到手机号",
            alarm._sms_phone == "13800138000",
            "phone=%s" % alarm._sms_phone)
    _report("状态变更事件已发布",
            len(received_events) >= 1)

    # ========================================================
    print("\n" + "=" * 60)
    print("[测试 2] 碰撞事件触发 SMS")
    print("=" * 60)
    # 碰撞事件 -> AlarmService._start_alarm -> SMS.send_sms()
    alarm.cancel_alarm()
    fake_sms.calls.clear()

    bus.publish(EVENT_COLLISION_DETECTED, {"level": 1})
    _pump(bus, count=10, interval_ms=20)
    _wait_for_thread()

    _report("SMS.send_sms() 被调用 1 次",
            len(fake_sms.calls) == 1)
    if fake_sms.calls:
        _report("调用 send_sms 方法",
                fake_sms.calls[0][0] == "send_sms")
        _report("手机号正确",
                fake_sms.calls[0][1] == "13800138000")
        msg = fake_sms.calls[0][2]
        _report("SMS 内容格式",
                msg.startswith("SOS:"),
                msg[:40])

    # ========================================================
    print("\n" + "=" * 60)
    print("[测试 3] GPS 数据 -> SMS 含位置链接")
    print("=" * 60)
    # GPS 坐标 -> SMS 内容含高德地图链接
    alarm.cancel_alarm()
    fake_sms.calls.clear()

    bus.publish(EVENT_GNSS_READY, {
        "latitude": 39.9042,
        "longitude": 116.4074,
        "valid": True,
    })
    _pump(bus)

    bus.publish(EVENT_COLLISION_DETECTED, {"level": 2})
    _pump(bus, count=10, interval_ms=20)
    _wait_for_thread()

    _report("SMS.send_sms() 被调用",
            len(fake_sms.calls) == 1)
    if fake_sms.calls:
        msg = fake_sms.calls[0][2]
        _report("SMS 含高德地图链接",
                "amap.com" in msg and "position=" in msg)
        _report("SMS 含 SOS 标记",
                "SOS:" in msg)

    # ========================================================
    print("\n" + "=" * 60)
    print("[测试 4] 未配置手机号不发送 SMS")
    print("=" * 60)
    alarm.cancel_alarm()
    alarm._sms_phone = None
    fake_sms.calls.clear()

    bus.publish(EVENT_COLLISION_DETECTED, {"level": 1})
    _pump(bus, count=10, interval_ms=20)
    _wait_for_thread()

    _report("未配置手机号时不发送 SMS",
            len(fake_sms.calls) == 0)

    # ========================================================
    print("\n" + "=" * 60)
    print("[测试 5] 原有控制指令不受影响")
    print("=" * 60)
    alarm.cancel_alarm()
    alarm._sms_phone = "13800138000"

    raw_cmd_on = '{"a":"ctrl","d":{"cmd":"light_on"}}'
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw_cmd_on})
    _pump(bus)

    _report("灯光控制状态更新",
            ctrl._control_state["light_mode"] == "manual")

    raw_cmd_vol = '{"a":"ctrl","d":{"cmd":"volume_up"}}'
    ctrl.ctx["last_cmd_tick"] = 0
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw_cmd_vol})
    _pump(bus)

    _report("音量指令正常",
            ctrl._control_state["volume"] >= 5)

    raw_cmd_q = '{"a":"ctrl","d":{"cmd":"query_status"}}'
    ctrl.ctx["last_cmd_tick"] = 0
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw_cmd_q})
    _pump(bus)

    _report("查询指令仍正常工作",
            ctrl._data["last_cmd"] == "query_status")

    # ========================================================
    print("\n" + "=" * 60)
    print("[测试 6] SMS 不阻塞主循环（连续事件稳定性）")
    print("=" * 60)
    alarm.cancel_alarm()
    fake_sms.calls.clear()

    for i in range(5):
        bus.publish(EVENT_COLLISION_DETECTED, {"level": 1})
        alarm.cancel_alarm()
        _pump(bus, count=3, interval_ms=5)

    _wait_for_thread()

    _report("连续 5 次碰撞循环无崩溃",
            len(fake_sms.calls) >= 1,
            "SMS 调用次数: %d" % len(fake_sms.calls))
    _report("AlarmService 无异常",
            alarm.ctx.get("err_count", 0) == 0)

    # ========================================================
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    total = pass_count + fail_count
    print("  通过: %d / %d" % (pass_count, total))
    if fail_count == 0:
        print("总体评估: ✅ 测试通过")
    else:
        print("总体评估: ❌ 测试未全部通过")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
