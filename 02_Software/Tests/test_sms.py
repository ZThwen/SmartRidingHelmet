"""
brief SMS 短信单元测试 — 模拟事件流验证 AlarmService 中 SMS 逻辑
note 使用 FakeSMS 模拟硬件，不依赖真实 SIM 卡
      验证：手机号配置、GPS 缓存、SMS 发送、报警联动
执行: 上传到板子运行 python test_sms.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_SMS_PHONE_CONFIG, EVENT_GNSS_READY,
    EVENT_COLLISION_DETECTED, EVENT_ALARM_TRIGGERED,
    EVENT_TTS_REQUEST, EVENT_BUTTON_PRESSED,
)
from Modules.alarm_service import AlarmService


def _wait_sms(fake_sms, timeout_ms=500):
    """等待后台线程完成 SMS 发送"""
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
        if len(fake_sms.calls) > 0:
            return
        time.sleep_ms(10)


class _FakeLED:
    def __init__(self):
        self.calls = []

    def on(self):
        self.calls.append(("on",))

    def off(self):
        self.calls.append(("off",))

    def blink(self, d, i):
        self.calls.append(("blink", d, i))


class _FakeAudio:
    def __init__(self):
        self.calls = []

    def play_file(self, f):
        self.calls.append(("play_file", f))

    def play_tts(self, t):
        self.calls.append(("play_tts", t))

    def stop(self):
        self.calls.append(("stop",))

    def init(self, cb=None):
        return True

    def set_speaker_volume(self, v):
        pass

    def tts_set_speed(self, s):
        pass

    def tts_set_volume(self, v):
        pass

    def set_volume(self, v):
        pass

    def get_volume(self):
        return 5


class _FakeSMS:
    def __init__(self):
        self.calls = []
        self.send_result = True

    def init(self):
        self.calls.append(("init",))
        return True

    def send_sms(self, phone, message):
        self.calls.append(("send_sms", phone, message))
        return self.send_result

    def tick(self):
        pass


def make_env():
    """创建测试环境：EventBus + Fake 设备 + AlarmService"""
    bus = EventBus()
    led = _FakeLED()
    audio = _FakeAudio()
    fake_sms = _FakeSMS()

    alarm = AlarmService(bus, led=led, audio=audio, sms=fake_sms)
    alarm.init()

    events = {
        "alarm_triggered": [],
        "tts": [],
    }
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: events["alarm_triggered"].append(p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: events["tts"].append(p))

    return bus, alarm, fake_sms, events, led, audio


# ==================== 测试用例 ====================


def test_phone_config():
    """手机号配置 — 发布 EVENT_SMS_PHONE_CONFIG 后 _sms_phone 更新 + TTS"""
    bus, alarm, fake_sms, events, _, _ = make_env()

    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": "13800138000"})
    bus.pump()

    assert alarm._sms_phone == "13800138000", "手机号应被存储"
    assert len(events["tts"]) == 1, "应触发 TTS 反馈"
    assert events["tts"][0]["text"] == "手机号已配置", "TTS 应为配置成功提示"
    print("  \u2713 手机号配置成功")


def test_phone_config_invalid():
    """无效手机号 — 长度不为 11 位时应被拒绝"""
    bus, alarm, fake_sms, events, _, _ = make_env()

    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": "12345"})
    bus.pump()

    assert alarm._sms_phone is None, "无效手机号不应存储"
    assert len(events["tts"]) == 0, "无效手机号不应触发 TTS"
    print("  \u2713 无效手机号被拒绝")


def test_gnss_cache():
    """GNSS 坐标缓存 — 发布 EVENT_GNSS_READY 后 _gnss_cache 更新"""
    bus, alarm, fake_sms, events, _, _ = make_env()

    bus.publish(EVENT_GNSS_READY, {
        "latitude": 31.82188,
        "longitude": 117.11582,
        "valid": True,
    })
    bus.pump()

    assert alarm._gnss_cache.get("valid") is True, "GPS 应标记有效"
    assert abs(alarm._gnss_cache.get("latitude") - 31.82188) < 0.0001, "纬度应缓存"
    assert abs(alarm._gnss_cache.get("longitude") - 117.11582) < 0.0001, "经度应缓存"
    print("  \u2713 GNSS 坐标缓存正确")


def test_build_sms_with_gps():
    """有 GPS 时短信内容包含高德地图链接"""
    bus, alarm, fake_sms, events, _, _ = make_env()

    bus.publish(EVENT_GNSS_READY, {
        "latitude": 31.82188, "longitude": 117.11582, "valid": True,
    })
    bus.pump()

    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": "13800138000"})
    bus.pump()

    bus.publish(EVENT_COLLISION_DETECTED, {"acc_total": 6.0, "level": 2})
    bus.pump()
    _wait_sms(fake_sms)

    assert len(fake_sms.calls) > 0, "应发送 SMS"
    assert len(fake_sms.calls) > 0, "应发送 SMS"
    _, phone, msg = fake_sms.calls[0]
    assert phone == "13800138000", "手机号正确"
    assert msg.startswith("SOS:2"), "SMS 应以 SOS:{level} 开头"
    assert "(GPS)" in msg, "有 GPS 时应包含 (GPS) 标记"
    assert "uri.amap.com/marker" in msg, "应包含高德地图链接"
    print("  \u2713 有 GPS 时短信内容: %s" % msg)


def test_build_sms_without_gps():
    """无 GPS 时短信内容只有 SOS:{level}"""
    bus, alarm, fake_sms, events, _, _ = make_env()

    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": "13900139000"})
    bus.pump()

    bus.publish(EVENT_BUTTON_PRESSED, {"timestamp": time.ticks_ms()})
    bus.pump()
    _wait_sms(fake_sms)

    assert len(fake_sms.calls) >= 1, "SOS 应发送 SMS"
    _, phone, msg = fake_sms.calls[0]
    assert phone == "13900139000", "手机号正确"
    assert msg.startswith("SOS:3"), "SOS 默认级别 3"
    assert "(GPS)" not in msg, "无 GPS 时不包含位置链接"
    print("  \u2713 无 GPS 时短信内容: %s" % msg)


def test_no_sms_without_phone():
    """未配置手机号时不发送 SMS"""
    bus, alarm, fake_sms, events, _, _ = make_env()
    before = len(fake_sms.calls)

    bus.publish(EVENT_COLLISION_DETECTED, {"acc_total": 6.0, "level": 2})
    bus.pump()

    assert len(fake_sms.calls) == before, "未配置手机号不应发送 SMS"
    print("  \u2713 未配置手机号时不发送 SMS")


def test_sms_fail_no_block():
    """SMS 发送失败不影响声光报警"""
    bus, alarm, fake_sms, events, _, _ = make_env()

    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": "13800138000"})
    bus.pump()

    fake_sms.send_result = False

    bus.publish(EVENT_COLLISION_DETECTED, {"acc_total": 6.0, "level": 2})
    bus.pump()

    assert len(events["alarm_triggered"]) == 1, "报警应正常触发"
    assert events["alarm_triggered"][0]["alarm_type"] == "collision", "报警类型正确"
    print("  \u2713 SMS 发送失败不影响报警")


def test_phone_config_repeated():
    """多次配置手机号 — 最后一次覆盖之前"""
    bus, alarm, fake_sms, events, _, _ = make_env()

    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": "13800000001"})
    bus.pump()

    assert alarm._sms_phone == "13800000001", "第一次配置成功"

    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": "13900000002"})
    bus.pump()

    assert alarm._sms_phone == "13900000002", "第二次应覆盖第一次"

    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": "13700000003"})
    bus.pump()

    assert alarm._sms_phone == "13700000003", "第三次应覆盖第二次"

    # 验证 SMS 发送使用最新的手机号
    bus.publish(EVENT_COLLISION_DETECTED, {"acc_total": 6.0, "level": 2})
    bus.pump()
    _wait_sms(fake_sms)

    assert len(fake_sms.calls) > 0, "应发送 SMS"
    _, phone = fake_sms.calls[0][:2]
    assert phone == "13700000003", "应使用最后配置的手机号"
    print("  \u2713 多次配置手机号 — 最后一次生效")


# ==================== 运行 ====================


def run_all():
    """按顺序运行所有测试并打印总结"""
    tests = [
        ("手机号配置", test_phone_config),
        ("无效手机号拒绝", test_phone_config_invalid),
        ("GNSS 坐标缓存", test_gnss_cache),
        ("有 GPS 短信内容", test_build_sms_with_gps),
        ("无 GPS 短信内容", test_build_sms_without_gps),
        ("未配置不发送", test_no_sms_without_phone),
        ("SMS 失败不阻塞报警", test_sms_fail_no_block),
        ("多次配置手机号覆盖", test_phone_config_repeated),
    ]

    passed = 0
    failed = 0

    print("=" * 60)
    print("  SMS 单元测试 — AlarmService 短信逻辑")
    print("=" * 60)
    print()

    for name, func in tests:
        try:
            print("[%s] %s" % (tests.index((name, func)) + 1, name))
            func()
            passed += 1
        except AssertionError as e:
            print("  \u2717 失败: %s" % e)
            failed += 1
        except Exception as e:
            print("  \u2717 异常: %s" % e)
            failed += 1
        print()

    print("=" * 60)
    print("  测试总结")
    print("=" * 60)
    print("  通过: %d  失败: %d  总计: %d" % (passed, failed, passed + failed))
    if failed == 0:
        print("  结果: \u2705 全部通过")
    else:
        print("  结果: \u274c 存在失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    run_all()
