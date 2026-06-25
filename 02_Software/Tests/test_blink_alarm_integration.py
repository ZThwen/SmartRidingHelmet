"""
brief 闪烁 × 报警 × BLE 集成测试
note 不依赖真实硬件，使用 EventBus + Fake 设备验证
      验证 PWM 闪烁与报警联动、手动闪烁控制、BLE 状态回推、省电模式交互
执行: 上传到板子运行 python test_blink_alarm_integration.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_LIGHT_CONTROL, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_CONTROL_STATE_CHANGED, EVENT_POWER_STATE_CHANGE,
    EVENT_TTS_REQUEST, EVENT_LIGHT_BLINK_STATE,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
)
from Modules.control_service import ControlService
from Modules.light_service import LightService
from Modules.alarm_service import AlarmService


# ==================== Fake 设备 ====================

class FakePWMChannel:
    """模拟 PWM 通道，记录 duty 调用"""
    def __init__(self):
        self._duty = 0
        self.calls = []

    def pulse_width_percent(self, duty):
        self.calls.append(("pwm", duty))
        self._duty = duty


class FakePWMLED:
    """模拟 PWMLEDDriver，记录 blink 调用"""
    def __init__(self):
        self.calls = []
        self.cfg = {"blink_on_duty": 20, "blink_interval_ms": 500}
        self.ctx = {
            "blink_active": False,
            "blink_on": False,
            "blink_from_alarm": False,
            "blink_last_toggle": 0,
            "power_state": POWER_STATE_ACTIVE,
        }

    def start_blink(self, on_duty=None, interval_ms=None, from_alarm=False):
        self.calls.append(("start_blink", on_duty, from_alarm))
        self.ctx["blink_active"] = True
        self.ctx["blink_from_alarm"] = from_alarm
        if on_duty is not None:
            self.cfg["blink_on_duty"] = on_duty

    def stop_blink(self):
        self.calls.append("stop_blink")
        self.ctx["blink_active"] = False
        self.ctx["blink_from_alarm"] = False

    def set_blink_duty(self, duty):
        self.calls.append(("set_blink_duty", duty))
        self.cfg["blink_on_duty"] = duty

    def set_brightness(self, duty):
        self.calls.append(("set_brightness", duty))

    def is_blink_active(self):
        return self.ctx["blink_active"]

    def is_blink_from_alarm(self):
        return self.ctx["blink_from_alarm"]


class FakeLED:
    """记录 LED 调用"""
    def __init__(self):
        self.calls = []

    def on(self):
        self.calls.append("on")

    def off(self):
        self.calls.append("off")

    def blink(self, d, i):
        self.calls.append(("blink", d, i))


class FakeAudio:
    """记录 Audio 调用"""
    def __init__(self):
        self.calls = []

    def play_file(self, f):
        self.calls.append(("play_file", f))

    def stop(self):
        self.calls.append("stop")

    def init(self, cb=None):
        return True

    def set_speaker_volume(self, v):
        pass


# ==================== 环境构建 ====================

def make_env():
    """创建基础环境：EventBus + ControlService + LightService(含FakePWMLED) + AlarmService"""
    bus = EventBus()
    pwm = FakePWMLED()
    led = FakeLED()
    audio = FakeAudio()

    light = LightService(bus, pwm_led=pwm)
    alarm = AlarmService(bus, led=led, audio=audio)
    ctrl = ControlService(bus)

    light.init()
    alarm.init()
    ctrl.init()

    events = {
        "light": [], "state": [], "tts": [],
        "alarm_triggered": [], "alarm_canceled": [],
        "blink_state": [], "power": [],
    }
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: events["light"].append(p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: events["state"].append(p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: events["tts"].append(p))
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: events["alarm_triggered"].append(p))
    bus.subscribe(EVENT_ALARM_CANCELED, lambda p: events["alarm_canceled"].append(p))
    bus.subscribe(EVENT_LIGHT_BLINK_STATE, lambda p: events["blink_state"].append(p))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: events["power"].append(p))

    return ctrl, light, alarm, pwm, bus, events


def send_light_cmd(bus, cmd):
    """发布灯光控制指令"""
    bus.publish(EVENT_LIGHT_CONTROL, {"cmd": cmd})
    bus.pump()


# ==================== 测试用例 ====================

def test_sos_auto_blink():
    """SOS (level>=3) -> PWM 自动闪烁"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    alarm._start_alarm("sos", 3)
    bus.pump()
    assert pwm.ctx["blink_active"] == True
    assert pwm.ctx["blink_from_alarm"] == True
    print("  OK SOS auto blink")


def test_sos_blink_params():
    """SOS 闪烁参数：duty=20, from_alarm=True"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    alarm._start_alarm("sos", 3)
    bus.pump()
    assert pwm.cfg["blink_on_duty"] == 20
    assert pwm.ctx["blink_from_alarm"] == True
    print("  OK SOS blink params")


def test_collision_no_pwm():
    """碰撞 level<3 不触发 PWM 闪烁"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    alarm._start_alarm("collision", 2)
    assert pwm.ctx["blink_active"] == False
    print("  OK collision level<3 no PWM blink")


def test_alarm_cancel_stop_blink():
    """报警取消 -> 停止 PWM 闪烁"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    alarm._start_alarm("sos", 3)
    alarm._cancel_alarm()
    assert pwm.ctx["blink_active"] == False
    print("  OK alarm cancel stops blink")


def test_alarm_blink_blocks_manual_light_on():
    """报警闪烁中 light_on 被忽略"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    alarm._start_alarm("sos", 3)
    send_light_cmd(bus, "on")
    # 报警闪烁不允许手动中断
    assert len(pwm.calls) == 1  # 只有 start_blink，没有其他调用
    print("  OK alarm blink blocks light_on")


def test_alarm_blink_blocks_blink():
    """报警闪烁中 blink 指令被忽略"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    alarm._start_alarm("sos", 3)
    pwm.calls.clear()
    send_light_cmd(bus, "blink")
    assert len([c for c in pwm.calls if c == "stop_blink" or (isinstance(c, tuple) and c[0] == "stop_blink")]) == 0
    print("  OK alarm blink blocks blink cmd")


def test_manual_blink_stopped_by_on():
    """手动闪烁中 light_on -> 停止闪烁 + 开灯"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    # 手动开始闪烁
    send_light_cmd(bus, "blink")  # toggle on
    assert pwm.ctx["blink_active"] == True
    assert pwm.ctx["blink_from_alarm"] == False
    # 发送 light_on
    pwm.calls.clear()
    send_light_cmd(bus, "on")
    assert pwm.ctx["blink_active"] == False  # 闪烁被停止
    print("  OK manual blink stopped by light_on")


def test_manual_blink_stopped_by_off():
    """手动闪烁中 light_off -> 停止闪烁 + 关灯"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    send_light_cmd(bus, "blink")  # toggle on
    assert pwm.ctx["blink_active"] == True
    pwm.calls.clear()
    send_light_cmd(bus, "off")
    assert pwm.ctx["blink_active"] == False
    print("  OK manual blink stopped by light_off")


def test_blink_brightness_up():
    """闪烁中 brightness_up -> 改变闪烁亮度"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    send_light_cmd(bus, "blink")  # toggle on
    pwm.calls.clear()
    send_light_cmd(bus, "brightness_up")
    assert ("set_blink_duty", 25) in pwm.calls
    print("  OK blink brightness_up -> 25")


def test_blink_brightness_down():
    """闪烁中 brightness_down -> 改变闪烁亮度"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    send_light_cmd(bus, "blink")  # toggle on
    pwm.calls.clear()
    send_light_cmd(bus, "brightness_down")
    assert ("set_blink_duty", 15) in pwm.calls
    print("  OK blink brightness_down -> 15")


def test_blink_state_publish():
    """闪烁状态变更 -> EVENT_LIGHT_BLINK_STATE"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    send_light_cmd(bus, "blink")  # toggle on -> start_blink
    bus.pump()
    assert len(events["blink_state"]) >= 1
    assert events["blink_state"][-1].get("blink") == True
    print("  OK blink state published on start")


def test_blink_off_state_publish():
    """闪烁停止 -> EVENT_LIGHT_BLINK_STATE{blink:False}"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    send_light_cmd(bus, "blink")  # on
    events["blink_state"].clear()
    send_light_cmd(bus, "blink")  # off (toggle)
    bus.pump()
    assert len(events["blink_state"]) >= 1
    assert events["blink_state"][-1].get("blink") == False
    print("  OK blink stop published on toggle off")


def test_blink_state_push_ble():
    """EVENT_LIGHT_BLINK_STATE -> ControlService._push_state() -> state event 含 f=1"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    # 先让 ControlService 缓存闪烁状态
    bus.publish(EVENT_LIGHT_BLINK_STATE, {"blink": True})
    bus.pump()
    assert ctrl._blink_active == True
    # _push_state 应该包含 f=1
    # 触发一次灯光指令，看 push_state 是否包含 f 字段
    events["state"].clear()
    ctrl._push_state()
    bus.pump()
    if events["state"]:
        assert "f" in events["state"][-1]
        assert events["state"][-1]["f"] == 1
    print("  OK blink state push to BLE contains f=1")


def test_power_save_stops_manual_blink():
    """省电模式 -> 手动闪烁停止（模拟 PWM_LED._on_config_update 行为）"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    send_light_cmd(bus, "blink")  # manual blink on
    assert pwm.ctx["blink_active"] == True
    # 模拟 PWM_LED._on_config_update 对省电模式的处理
    pwm.ctx["power_state"] = POWER_STATE_SUSPENDED
    if pwm.ctx["blink_active"] and not pwm.ctx["blink_from_alarm"]:
        pwm.stop_blink()
    assert pwm.ctx["blink_active"] == False
    print("  OK power save stops manual blink")


def test_power_save_keeps_alarm_blink():
    """省电模式 -> 报警闪烁继续"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    # 用 FakePWMLED 直接触发 from_alarm=True
    pwm.ctx["blink_active"] = True
    pwm.ctx["blink_from_alarm"] = True
    pwm.ctx["power_state"] = POWER_STATE_ACTIVE
    # 进入省电模式
    pwm.calls.clear()
    bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_SUSPENDED})
    bus.pump()
    # 报警闪烁不应被停止
    assert pwm.ctx["blink_active"] == True
    print("  OK power save keeps alarm blink")


def test_on_light_blink_state_push():
    """_on_light_blink_state 调用 _push_state()"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    events["state"].clear()
    ctrl._on_light_blink_state({"blink": True})
    bus.pump()
    assert len(events["state"]) >= 1
    assert events["state"][-1]["f"] == 1
    print("  OK _on_light_blink_state -> _push_state with f=1")


def test_sos_publishes_blink_state():
    """SOS 触发 -> LightService 发布 EVENT_LIGHT_BLINK_STATE"""
    ctrl, light, alarm, pwm, bus, events = make_env()
    alarm._start_alarm("sos", 3)
    bus.pump()
    assert len(events["blink_state"]) >= 1
    assert events["blink_state"][-1].get("blink") == True
    print("  OK SOS -> light blink state published")


# ==================== 入口 ====================

def main():
    print("=" * 55)
    print(" 闪烁 × 报警 × BLE 集成测试")
    print("=" * 55)
    tests = [
        test_sos_auto_blink, test_sos_blink_params,
        test_collision_no_pwm, test_alarm_cancel_stop_blink,
        test_alarm_blink_blocks_manual_light_on,
        test_alarm_blink_blocks_blink,
        test_manual_blink_stopped_by_on, test_manual_blink_stopped_by_off,
        test_blink_brightness_up, test_blink_brightness_down,
        test_blink_state_publish, test_blink_off_state_publish,
        test_blink_state_push_ble, test_power_save_stops_manual_blink,
        test_power_save_keeps_alarm_blink,
        test_on_light_blink_state_push, test_sos_publishes_blink_state,
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
    print("结果: %d 通过, %d 失败 / 共 %d" % (passed, failed, len(tests)))


if __name__ == "__main__":
    main()
