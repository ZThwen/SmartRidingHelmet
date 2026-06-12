"""
brief Phase 3 全链路集成测试
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
    EVENT_POWER_STATE_CHANGE, POWER_STATE_EMERGENCY,
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
    return bus, ctrl, alarm, light, led, audio, pwm


def send_cmd(bus, cmd):
    import json
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()


# ==================== 测试 ====================

def test_light_on_flow():
    """ControlService light_on → LightService → PWM brightness_max"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "light_on")
    assert pwm.duty == light.cfg["brightness_max"]
    assert light.get_mode() == "manual"
    print("  OK light_on_flow")


def test_light_off_flow():
    """ControlService light_off → PWM 0%"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "light_on")
    send_cmd(bus, "light_off")
    assert pwm.duty == 0
    print("  OK light_off_flow")


def test_brightness_up_flow():
    """brightness_up → 亮度 +10"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    light.set_manual_brightness(30)
    send_cmd(bus, "brightness_up")
    assert pwm.duty == 40
    print("  OK brightness_up_flow")


def test_alarm_sos_flow():
    """ControlService alarm_sos → AlarmService → LED + Audio"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "alarm_sos")
    assert alarm.ctx["alarm_type"] == "sos"
    assert led.calls[-1][0] == "blink"
    assert audio.calls[-1][0] == "play_file"
    print("  OK alarm_sos_flow")


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


def test_alarm_cancel_flow():
    """alarm_cancel → 取消报警"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    send_cmd(bus, "alarm_sos")
    assert alarm.ctx["alarm_active"] == True
    send_cmd(bus, "alarm_cancel")
    assert alarm.ctx["alarm_active"] == False
    print("  OK alarm_cancel_flow")


def test_volume_up_flow():
    """ControlService volume_up → AudioDriver +1"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    audio.set_volume(3)
    send_cmd(bus, "volume_up")
    assert audio.get_volume() == 4
    print("  OK volume_up_flow")


def test_power_emergency_flow():
    """power_emergency → EVENT_POWER_STATE_CHANGE(EMERGENCY)"""
    bus, ctrl, alarm, light, led, audio, pwm = make_system()
    received = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: received.append(p))
    send_cmd(bus, "power_emergency")
    assert received[-1]["power_state"] == POWER_STATE_EMERGENCY
    assert ctrl._control_state["power_mode"] == "emergency"
    print("  OK power_emergency_flow")


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print(" Phase 3 全链路集成测试")
    print("=" * 50)

    tests = [
        test_light_on_flow,
        test_light_off_flow,
        test_brightness_up_flow,
        test_alarm_sos_flow,
        test_alarm_stealth_flow,
        test_alarm_cancel_flow,
        test_volume_up_flow,
        test_power_emergency_flow,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print("  FAIL {}: {}".format(t.__name__, e))
            failed += 1

    print("")
    print("=" * 50)
    print(" 结果: %d 通过, %d 失败" % (passed, failed))
    print("=" * 50)


if __name__ == "__main__":
    main()
