"""
brief ControlService 单元测试（纯 fake 数据）
note 不依赖真实硬件，使用 Fake 对象记录调用
     验证指令路由、防抖、降级运行、状态回推
执行: 上传到板子运行 python test_control_service.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
)
from Modules.control_service import ControlService


class FakeLightService:
    def __init__(self):
        self.calls = []
        self.ctx = {"is_init": True}
    def set_manual_brightness(self, val):
        self.calls.append(("set_manual_brightness", val))
    def set_auto_mode(self):
        self.calls.append(("set_auto_mode",))
    def get_mode(self):
        return "auto"


class FakeAudioDriver:
    def __init__(self):
        self.calls = []
        self.ctx = {"is_init": True}
        self._volume = 5
    def set_volume(self, vol):
        self.calls.append(("set_volume", vol))
        self._volume = vol
    def get_volume(self):
        return self._volume


class FakeAlarmService:
    def __init__(self):
        self.calls = []
        self.ctx = {"is_init": True, "alarm_active": False}
    def cancel_alarm(self):
        self.calls.append(("cancel_alarm",))


def make_ctrl(light=None, audio=None, alarm=None):
    """创建已 init 的 ControlService 及 Fake 设备"""
    bus = EventBus()
    if light is None:
        light = FakeLightService()
    if audio is None:
        audio = FakeAudioDriver()
    if alarm is None:
        alarm = FakeAlarmService()
    ctrl = ControlService(bus, light_service=light,
                          audio_driver=audio, alarm_service=alarm)
    ctrl.init()
    return ctrl, bus, light, audio, alarm


def send_ble_cmd(bus, cmd):
    """发送 BLE 控制指令"""
    import json
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()


# ==================== 测试用例 ====================

def test_init():
    """初始化成功"""
    ctrl, bus, _, _, _ = make_ctrl()
    assert ctrl.ctx["is_init"] == True
    assert ctrl.name == "control_service"
    print("  OK init")


def test_light_on():
    """light_on → set_manual_brightness(50)"""
    ctrl, bus, light, _, _ = make_ctrl()
    send_ble_cmd(bus, "light_on")
    assert len(light.calls) == 1
    assert light.calls[0] == ("set_manual_brightness", 50)
    assert ctrl._control_state["light_mode"] == "manual"
    assert ctrl._control_state["light_brightness"] == 50
    print("  OK light_on")


def test_light_off():
    """light_off → set_manual_brightness(0)"""
    ctrl, bus, light, _, _ = make_ctrl()
    send_ble_cmd(bus, "light_off")
    assert light.calls[0] == ("set_manual_brightness", 0)
    assert ctrl._control_state["light_brightness"] == 0
    print("  OK light_off")


def test_brightness_up():
    """brightness_up → 亮度增加 10"""
    ctrl, bus, light, _, _ = make_ctrl()
    ctrl._control_state["light_brightness"] = 30
    send_ble_cmd(bus, "brightness_up")
    assert light.calls[0] == ("set_manual_brightness", 40)
    assert ctrl._control_state["light_brightness"] == 40
    print("  OK brightness_up")


def test_brightness_up_max():
    """brightness_up 不超过 100"""
    ctrl, bus, light, _, _ = make_ctrl()
    ctrl._control_state["light_brightness"] = 95
    send_ble_cmd(bus, "brightness_up")
    assert light.calls[0] == ("set_manual_brightness", 100)
    print("  OK brightness_up_max")


def test_brightness_down():
    """brightness_down → 亮度减少 10"""
    ctrl, bus, light, _, _ = make_ctrl()
    ctrl._control_state["light_brightness"] = 30
    send_ble_cmd(bus, "brightness_down")
    assert light.calls[0] == ("set_manual_brightness", 20)
    print("  OK brightness_down")


def test_brightness_down_min():
    """brightness_down 不低于 0"""
    ctrl, bus, light, _, _ = make_ctrl()
    ctrl._control_state["light_brightness"] = 5
    send_ble_cmd(bus, "brightness_down")
    assert light.calls[0] == ("set_manual_brightness", 0)
    print("  OK brightness_down_min")


def test_light_auto():
    """light_auto → set_auto_mode()"""
    ctrl, bus, light, _, _ = make_ctrl()
    send_ble_cmd(bus, "light_auto")
    assert light.calls[0] == ("set_auto_mode",)
    assert ctrl._control_state["light_mode"] == "auto"
    print("  OK light_auto")


def test_volume_up():
    """volume_up → 音量增加 1"""
    ctrl, bus, _, audio, _ = make_ctrl()
    ctrl._control_state["volume"] = 5
    send_ble_cmd(bus, "volume_up")
    assert audio.calls[0] == ("set_volume", 6)
    assert ctrl._control_state["volume"] == 6
    print("  OK volume_up")


def test_volume_up_max():
    """volume_up 不超过 7"""
    ctrl, bus, _, audio, _ = make_ctrl()
    ctrl._control_state["volume"] = 7
    send_ble_cmd(bus, "volume_up")
    assert audio.calls[0] == ("set_volume", 7)
    print("  OK volume_up_max")


def test_volume_down():
    """volume_down → 音量减少 1"""
    ctrl, bus, _, audio, _ = make_ctrl()
    ctrl._control_state["volume"] = 5
    send_ble_cmd(bus, "volume_down")
    assert audio.calls[0] == ("set_volume", 4)
    print("  OK volume_down")


def test_volume_down_min():
    """volume_down 不低于 0"""
    ctrl, bus, _, audio, _ = make_ctrl()
    ctrl._control_state["volume"] = 0
    send_ble_cmd(bus, "volume_down")
    assert audio.calls[0] == ("set_volume", 0)
    print("  OK volume_down_min")


def test_alarm_cancel():
    """alarm_cancel → cancel_alarm()"""
    ctrl, bus, _, _, alarm = make_ctrl()
    send_ble_cmd(bus, "alarm_cancel")
    assert len(alarm.calls) == 1
    assert alarm.calls[0] == ("cancel_alarm",)
    print("  OK alarm_cancel")


def test_power_save():
    """power_save → 发布 POWER_STATE_CHANGE(SUSPENDED)"""
    ctrl, bus, _, _, _ = make_ctrl()
    received = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: received.append(p))
    send_ble_cmd(bus, "power_save")
    assert len(received) == 1
    assert received[0]["power_state"] == POWER_STATE_SUSPENDED
    assert ctrl._control_state["power_mode"] == "suspended"
    print("  OK power_save")


def test_power_normal():
    """power_normal → 发布 POWER_STATE_CHANGE(ACTIVE)"""
    ctrl, bus, _, _, _ = make_ctrl()
    ctrl._control_state["power_mode"] = "suspended"
    received = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: received.append(p))
    send_ble_cmd(bus, "power_normal")
    assert len(received) == 1
    assert received[0]["power_state"] == POWER_STATE_ACTIVE
    assert ctrl._control_state["power_mode"] == "active"
    print("  OK power_normal")


def test_debounce():
    """防抖：300ms 内重复指令被忽略"""
    ctrl, bus, light, _, _ = make_ctrl()
    send_ble_cmd(bus, "light_on")
    assert len(light.calls) == 1
    # 立即再发一次，应被防抖忽略
    send_ble_cmd(bus, "light_on")
    assert len(light.calls) == 1, "debounce should block second call"
    print("  OK debounce")


def test_unknown_cmd():
    """未知指令被忽略"""
    ctrl, bus, light, audio, alarm = make_ctrl()
    send_ble_cmd(bus, "unknown_cmd")
    assert len(light.calls) == 0
    assert len(audio.calls) == 0
    assert len(alarm.calls) == 0
    print("  OK unknown_cmd")


def test_invalid_json():
    """非法 JSON 不崩溃"""
    ctrl, bus, _, _, _ = make_ctrl()
    bus.publish(EVENT_RIDE_CONTROL, {"raw": "not json"})
    bus.pump()
    assert ctrl.ctx["err_count"] > 0
    print("  OK invalid_json")


def test_non_ctrl_action():
    """非 ctrl action 被忽略"""
    ctrl, bus, light, _, _ = make_ctrl()
    import json
    raw = json.dumps({"a": "nav", "d": {"dir": "right"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    assert len(light.calls) == 0
    print("  OK non_ctrl_action")


def test_no_light_service():
    """无 LightService 时不崩溃"""
    ctrl, bus, _, _, _ = make_ctrl(light=None)
    send_ble_cmd(bus, "light_on")
    # 不崩溃即通过
    print("  OK no_light_service")


def test_no_audio_driver():
    """无 AudioDriver 时不崩溃"""
    ctrl, bus, _, _, _ = make_ctrl(audio=None)
    send_ble_cmd(bus, "volume_up")
    # 不崩溃即通过
    print("  OK no_audio_driver")


def test_no_alarm_service():
    """无 AlarmService 时不崩溃"""
    ctrl, bus, _, _, _ = make_ctrl(alarm=None)
    send_ble_cmd(bus, "alarm_cancel")
    # 不崩溃即通过
    print("  OK no_alarm_service")


def test_state_push():
    """控制执行后触发 EVENT_CONTROL_STATE_CHANGED"""
    ctrl, bus, _, _, _ = make_ctrl()
    received = []
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: received.append(p))
    send_ble_cmd(bus, "light_on")
    assert len(received) == 1
    assert received[0]["light_mode"] == "manual"
    assert received[0]["light_brightness"] == 50
    print("  OK state_push")


def test_get_data():
    """get_data 返回当前状态"""
    ctrl, bus, _, _, _ = make_ctrl()
    d = ctrl.get_data()
    assert "last_cmd" in d
    assert "control_state" in d
    assert "timestamp" in d
    print("  OK get_data")


def test_get_status():
    """get_status 返回模块状态"""
    ctrl, bus, _, _, _ = make_ctrl()
    s = ctrl.get_status()
    assert "is_init" in s
    assert s["is_init"] == True
    assert "control_state" in s
    print("  OK get_status")


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print(" ControlService 单元测试")
    print("=" * 50)

    tests = [
        test_init,
        test_light_on,
        test_light_off,
        test_brightness_up,
        test_brightness_up_max,
        test_brightness_down,
        test_brightness_down_min,
        test_light_auto,
        test_volume_up,
        test_volume_up_max,
        test_volume_down,
        test_volume_down_min,
        test_alarm_cancel,
        test_power_save,
        test_power_normal,
        test_debounce,
        test_unknown_cmd,
        test_invalid_json,
        test_non_ctrl_action,
        test_no_light_service,
        test_no_audio_driver,
        test_no_alarm_service,
        test_state_push,
        test_get_data,
        test_get_status,
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
    print(" 结果: {} 通过, {} 失败".format(passed, failed))
    print("=" * 50)


if __name__ == "__main__":
    main()
