"""
brief Phase 3 全链路集成测试（增强版）
note ControlService → EventBus → AlarmService/LightService/AudioDriver
     验证事件驱动架构的端到端流转
     上传到板子运行 python test_phase3_integration.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    EVENT_POWER_STATE_CHANGE, POWER_STATE_EMERGENCY, POWER_STATE_ACTIVE,
    POWER_STATE_SUSPENDED, POWER_STATE_CUSTOM,
    EVENT_TTS_REQUEST, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    AUDIO_SOS_FILE,
)
from Modules.control_service import ControlService
from Modules.alarm_service import AlarmService
from Modules.light_service import LightService


class FakeLED:
    def __init__(self):
        self.calls = []
    def on(self):
        self.calls.append(("on",))
    def off(self):
        self.calls.append(("off",))
    def blink(self, dur, interval):
        self.calls.append(("blink", dur, interval))


class FakeAudio:
    def __init__(self):
        self.calls = []
        self._vol = 5
    def play_file(self, f):
        self.calls.append(("play_file", f))
        return True
    def play_tts(self, t):
        self.calls.append(("play_tts", t))
        return True
    def stop(self):
        self.calls.append(("stop",))
    def set_volume(self, v):
        self._vol = max(0, min(5, v))
        self.calls.append(("set_volume", v))
        return True
    def get_volume(self):
        return self._vol
    def init(self, cb=None):
        return True
    def set_speaker_volume(self, v):
        self._vol = v
    def tts_set_speed(self, s):
        pass
    def tts_set_volume(self, v):
        pass


class FakePWM:
    def __init__(self):
        self.duty = 0
    def set_brightness(self, d):
        self.duty = d


# ==================== 事件日志 ====================
event_log = []

def on_any_event(tag, payload):
    """记录事件到日志，tag为事件类型缩写"""
    event_log.append("%s:%s" % (tag, str(payload)[:50]))


def make_system():
    bus = EventBus()
    led = FakeLED()
    audio = FakeAudio()
    pwm = FakePWM()
    alarm = AlarmService(bus, led=led, audio=audio)
    light = LightService(bus, pwm_led=pwm)
    ctrl = ControlService(bus)
    alarm.init()
    light.init()
    ctrl.init()

    # 事件日志订阅（每次新建系统时重置）
    event_log.clear()
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: on_any_event("LIGHT", p))
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: on_any_event("VOL", p))
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: on_any_event("ALARM", p))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: on_any_event("POWER", p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: on_any_event("STATE", p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: on_any_event("TTS", p))
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: on_any_event("ALARM_TRIG", p))
    bus.subscribe(EVENT_ALARM_CANCELED, lambda p: on_any_event("ALARM_CANCEL", p))

    return bus, ctrl, alarm, light, led, audio, pwm


def send_cmd(bus, cmd, ctrl=None):
    import json
    if ctrl:
        ctrl.ctx["last_cmd_tick"] = 0  # 重置防抖，允许连续发送
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()


# ==================== 灯光控制测试 ====================

def test_light_on_flow():
    """ControlService light_on → LightService → PWM brightness_max"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "light_on")
    assert pwm.duty == light.cfg["brightness_max"]
    assert light.get_mode() == "manual"
    print("  OK light_on_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_light_off_flow():
    """ControlService light_off → PWM 0%"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "light_on", ctrl)
    send_cmd(bus, "light_off", ctrl)
    assert pwm.duty == 0
    print("  OK light_off_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_brightness_up_flow():
    """brightness_up → 亮度 +5"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    light.set_manual_brightness(30)
    send_cmd(bus, "brightness_up")
    assert pwm.duty == 35
    print("  OK brightness_up_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_brightness_down_flow():
    """brightness_down → 亮度 -5"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    light.set_manual_brightness(30)
    send_cmd(bus, "brightness_down")
    assert pwm.duty == 25
    assert light.get_mode() == "manual"
    print("  OK brightness_down_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_light_auto_flow():
    """light_auto → LightService auto mode"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    # 先切到手动模式
    send_cmd(bus, "light_on")
    assert light.get_mode() == "manual"
    # 切回自动
    send_cmd(bus, "light_auto", ctrl)
    assert light.get_mode() == "auto"
    print("  OK light_auto_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


# ==================== 音量控制测试 ====================

def test_volume_up_flow():
    """ControlService volume_up → EVENT_VOLUME_CONTROL{up}"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    received = []
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: received.append(p))
    send_cmd(bus, "volume_up")
    assert len(received) == 1
    assert received[0]["cmd"] == "up"
    print("  OK volume_up_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_volume_down_flow():
    """ControlService volume_down → EVENT_VOLUME_CONTROL{down}"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    received = []
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: received.append(p))
    send_cmd(bus, "volume_down")
    assert len(received) == 1
    assert received[0]["cmd"] == "down"
    print("  OK volume_down_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


# ==================== 电源模式测试 ====================

def test_power_emergency_flow():
    """power_emergency → EVENT_POWER_STATE_CHANGE(EMERGENCY)"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    received = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: received.append(p))
    send_cmd(bus, "power_emergency")
    assert received[-1]["power_state"] == POWER_STATE_EMERGENCY
    assert ctrl._control_state["power_mode"] == "emergency"
    print("  OK power_emergency_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_power_save_flow():
    """power_save → suspended + light off"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "light_on")  # 先开灯
    assert pwm.duty > 0
    send_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended"
    assert pwm.duty == 0  # 灯被关闭
    assert ctrl._control_state["light_brightness"] == 0
    print("  OK power_save_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_power_normal_flow():
    """power_normal → active"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "power_emergency")  # 先进入紧急省电
    assert ctrl._control_state["power_mode"] == "emergency"
    send_cmd(bus, "power_normal", ctrl)
    assert ctrl._control_state["power_mode"] == "active"
    print("  OK power_normal_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


# ==================== 报警控制测试 ====================

def test_alarm_sos_flow():
    """ControlService alarm_sos → AlarmService → LED + Audio"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "alarm_sos")
    assert alarm.ctx["alarm_type"] == "sos"
    assert led.calls[-1][0] == "blink"
    assert audio.calls[-1][0] == "play_file"
    print("  OK alarm_sos_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_alarm_stealth_flow():
    """ControlService alarm_stealth → AlarmService → 无声光"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    led.calls.clear()
    audio.calls.clear()
    send_cmd(bus, "alarm_stealth")
    assert alarm.ctx["alarm_type"] == "stealth"
    assert alarm.ctx["alarm_active"] == True
    assert led.calls == []
    assert audio.calls == []
    print("  OK alarm_stealth_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_alarm_cancel_flow():
    """alarm_cancel → 取消报警"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "alarm_sos", ctrl)
    assert alarm.ctx["alarm_active"] == True
    send_cmd(bus, "alarm_cancel", ctrl)
    assert alarm.ctx["alarm_active"] == False
    print("  OK alarm_cancel_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


# ==================== 高级场景测试 ====================

def test_custom_mode_flow():
    """power_save → light_on → power=custom"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    # 先进入省电模式
    send_cmd(bus, "power_save")
    assert ctrl._control_state["power_mode"] == "suspended"
    # 手动开灯应覆盖为自定义模式
    send_cmd(bus, "light_on", ctrl)
    assert ctrl._control_state["power_mode"] == "custom"
    assert pwm.duty == light.cfg["brightness_max"]
    print("  OK custom_mode_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_alarm_snapshot_flow():
    """alarm_sos saves state → alarm_cancel restores state"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    # 设置初始状态：手动模式，亮度50
    send_cmd(bus, "light_on")
    assert ctrl._control_state["light_brightness"] == 50
    assert ctrl._control_state["light_mode"] == "manual"
    # 触发报警（保存快照）
    send_cmd(bus, "alarm_sos", ctrl)
    assert alarm.ctx["alarm_active"] == True
    # 取消报警（恢复快照）
    send_cmd(bus, "alarm_cancel", ctrl)
    assert alarm.ctx["alarm_active"] == False
    # 状态应恢复到报警前
    assert ctrl._control_state["light_brightness"] == 50
    assert ctrl._control_state["light_mode"] == "manual"
    print("  OK alarm_snapshot_flow")
    print("    events: %s" % event_log)
    print("    state: %s" % ctrl._control_state)


def test_tts_during_alarm():
    """alarm active → TTS blocked"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    tts_received = []
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))
    # 触发报警（会触发一次TTS "报警已触发"）
    send_cmd(bus, "alarm_sos")
    tts_count_after_alarm = len(tts_received)
    assert tts_count_after_alarm >= 1  # alarm_sos 触发的TTS
    # 报警期间发送 light_on，TTS 应被阻塞
    send_cmd(bus, "light_on", ctrl)
    assert len(tts_received) == tts_count_after_alarm  # 无新增TTS
    print("  OK tts_during_alarm")
    print("    events: %s" % event_log)
    print("    tts_count: alarm=%d, after_light_on=%d" % (tts_count_after_alarm, len(tts_received)))


def test_tts_after_alarm_cancel():
    """alarm cancel → TTS resumes"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    tts_received = []
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))
    # 触发并取消报警
    send_cmd(bus, "alarm_sos")
    send_cmd(bus, "alarm_cancel", ctrl)
    assert alarm.ctx["alarm_active"] == False
    tts_received.clear()
    # 取消后发送 light_on，TTS 应恢复
    send_cmd(bus, "light_on", ctrl)
    assert len(tts_received) >= 1  # TTS "灯光已开启"
    print("  OK tts_after_alarm_cancel")
    print("    events: %s" % event_log)
    print("    tts_after_resume: %s" % tts_received)


def test_query_status_flow():
    """query_status → TTS with state text"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    tts_received = []
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))
    send_cmd(bus, "query_status")
    assert len(tts_received) >= 1
    text = tts_received[-1]["text"]
    assert "灯光" in text  # 应包含灯光信息
    assert "音量" in text  # 应包含音量信息
    print("  OK query_status_flow")
    print("    events: %s" % event_log)
    print("    tts_text: %s" % text)


def test_query_speed_flow():
    """query_speed → TTS with speed"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    tts_received = []
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))
    ctrl._sensor_cache["speed_kmh"] = 25.5
    send_cmd(bus, "query_speed")
    assert len(tts_received) >= 1
    assert "25" in tts_received[-1]["text"]
    print("  OK query_speed_flow")
    print("    events: %s" % event_log)
    print("    tts_text: %s" % tts_received[-1]["text"])


def test_query_temp_flow():
    """query_temp → TTS with temperature"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    tts_received = []
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))
    ctrl._sensor_cache["temperature"] = 28
    send_cmd(bus, "query_temp")
    assert len(tts_received) >= 1
    assert "28" in tts_received[-1]["text"]
    print("  OK query_temp_flow")
    print("    events: %s" % event_log)
    print("    tts_text: %s" % tts_received[-1]["text"])


def test_query_location_flow():
    """query_location → TTS with coordinates"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    tts_received = []
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))
    ctrl._sensor_cache["latitude"] = 30.1234
    ctrl._sensor_cache["longitude"] = 120.5678
    send_cmd(bus, "query_location")
    assert len(tts_received) >= 1
    assert "30" in tts_received[-1]["text"]
    print("  OK query_location_flow")
    print("    events: %s" % event_log)
    print("    tts_text: %s" % tts_received[-1]["text"])


# ==================== 边界/错误测试 ====================

def test_debounce_rejects_rapid_cmd():
    """rapid commands rejected by debounce"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "light_on")
    first_duty = pwm.duty
    # 不重置防抖，立即发送第二条指令
    send_cmd(bus, "light_off")  # 无ctrl参数，不重置last_cmd_tick
    assert pwm.duty == first_duty  # 应被防抖拒绝
    print("  OK debounce_rejects_rapid_cmd")
    print("    events: %s" % event_log)


def test_unknown_cmd_ignored():
    """unknown command produces no control events"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    event_log.clear()
    send_cmd(bus, "invalid_cmd_xyz")
    # 不应产生任何灯光/音量/报警/电源事件
    control_events = [e for e in event_log if not e.startswith("STATE:")]
    assert len(control_events) == 0
    print("  OK unknown_cmd_ignored")
    print("    events: %s" % event_log)


# ==================== 入口 ====================

def main():
    print("=" * 60)
    print(" Phase 3 全链路集成测试（增强版）")
    print("=" * 60)

    tests = [
        # 灯光控制 (5)
        test_light_on_flow,
        test_light_off_flow,
        test_brightness_up_flow,
        test_brightness_down_flow,
        test_light_auto_flow,
        # 音量控制 (2)
        test_volume_up_flow,
        test_volume_down_flow,
        # 电源模式 (3)
        test_power_emergency_flow,
        test_power_save_flow,
        test_power_normal_flow,
        # 报警控制 (3)
        test_alarm_sos_flow,
        test_alarm_stealth_flow,
        test_alarm_cancel_flow,
        # 高级场景 (5)
        test_custom_mode_flow,
        test_alarm_snapshot_flow,
        test_tts_during_alarm,
        test_tts_after_alarm_cancel,
        test_query_status_flow,
        # 查询指令 (3)
        test_query_speed_flow,
        test_query_temp_flow,
        test_query_location_flow,
        # 边界/错误 (2)
        test_debounce_rejects_rapid_cmd,
        test_unknown_cmd_ignored,
    ]

    passed = 0
    failed = 0
    results = []
    for t in tests:
        try:
            t()
            passed += 1
            results.append(True)
        except Exception as e:
            print("  FAIL {}: {}".format(t.__name__, e))
            failed += 1
            results.append(False)

    print("")
    print("=" * 60)
    print(" 集成测试总结")
    print("=" * 60)
    print("| # | %-30s | %-20s | %s |" % ("测试", "场景", "结果"))
    print("|---|%s|%s|%s|" % ("-" * 30, "-" * 20, "-" * 4))
    for i, (t, result) in enumerate(zip(tests, results)):
        doc = getattr(t, '__doc__', '') or ""
        print("| %d | %-30s | %-20s | %s |" % (
            i + 1, t.__name__, doc[:20], "PASS" if result else "FAIL"))
    print("=" * 60)
    print(" 结果: %d 通过, %d 失败" % (passed, failed))
    print("=" * 60)


if __name__ == "__main__":
    main()
