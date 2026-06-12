"""
brief ControlService v2 单元测试（纯事件驱动架构）
note 不依赖真实硬件，验证事件发布 + 乐观状态更新
     上传到板子运行 python test_control_service_v2.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_LIGHT_CONTROL,
    EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
)
from Modules.control_service import ControlService


def make_ctrl():
    """创建已 init 的 ControlService"""
    bus = EventBus()
    ctrl = ControlService(bus)
    ctrl.init()
    return ctrl, bus


def send_ble_cmd(bus, cmd):
    """发送 BLE 控制指令"""
    import json
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()


# ==================== 初始化测试 ====================

def test_init():
    """初始化成功"""
    ctrl, bus = make_ctrl()
    assert ctrl.ctx["is_init"] == True
    assert ctrl.name == "control_service"
    print("  OK init")


# ==================== 灯光指令测试 ====================

def test_light_on():
    """light_on → 发布 EVENT_LIGHT_CONTROL{cmd:on} + 状态更新"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "light_on")
    assert len(received) == 1
    assert received[0]["cmd"] == "on"
    assert ctrl._control_state["light_mode"] == "manual"
    assert ctrl._control_state["light_brightness"] == ctrl.cfg["default_brightness"]
    print("  OK light_on")


def test_light_off():
    """light_off → 发布 EVENT_LIGHT_CONTROL{cmd:off} + 状态更新"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "light_off")
    assert len(received) == 1
    assert received[0]["cmd"] == "off"
    assert ctrl._control_state["light_brightness"] == 0
    print("  OK light_off")


def test_brightness_up():
    """brightness_up → 亮度增加 10"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["light_brightness"] = 30
    received = []
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "brightness_up")
    assert received[0]["cmd"] == "brightness_up"
    assert ctrl._control_state["light_brightness"] == 40
    print("  OK brightness_up")


def test_brightness_up_max():
    """brightness_up 不超过 brightness_max"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["light_brightness"] = ctrl.cfg["brightness_max"] - 5
    send_ble_cmd(bus, "brightness_up")
    assert ctrl._control_state["light_brightness"] == ctrl.cfg["brightness_max"]
    print("  OK brightness_up_max")


def test_brightness_down():
    """brightness_down → 亮度减少 10"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["light_brightness"] = 30
    received = []
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "brightness_down")
    assert received[0]["cmd"] == "brightness_down"
    assert ctrl._control_state["light_brightness"] == 20
    print("  OK brightness_down")


def test_brightness_down_min():
    """brightness_down 不低于 0"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["light_brightness"] = 5
    send_ble_cmd(bus, "brightness_down")
    assert ctrl._control_state["light_brightness"] == 0
    print("  OK brightness_down_min")


def test_light_auto():
    """light_auto → 发布 EVENT_LIGHT_CONTROL{cmd:auto}"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["light_mode"] = "manual"
    received = []
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "light_auto")
    assert received[0]["cmd"] == "auto"
    assert ctrl._control_state["light_mode"] == "auto"
    print("  OK light_auto")


# ==================== 音量指令测试 ====================

def test_volume_up():
    """volume_up → 音量增加 1"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["volume"] = 3
    received = []
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "volume_up")
    assert len(received) == 1
    assert received[0]["cmd"] == "up"
    assert ctrl._control_state["volume"] == 4
    print("  OK volume_up")


def test_volume_up_max():
    """volume_up 不超过 5"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["volume"] = 5
    send_ble_cmd(bus, "volume_up")
    assert ctrl._control_state["volume"] == 5
    print("  OK volume_up_max")


def test_volume_down():
    """volume_down → 音量减少 1"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["volume"] = 3
    received = []
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "volume_down")
    assert received[0]["cmd"] == "down"
    assert ctrl._control_state["volume"] == 2
    print("  OK volume_down")


def test_volume_down_min():
    """volume_down 不低于 0"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["volume"] = 0
    send_ble_cmd(bus, "volume_down")
    assert ctrl._control_state["volume"] == 0
    print("  OK volume_down_min")


# ==================== 报警指令测试 ====================

def test_alarm_cancel():
    """alarm_cancel → 发布 EVENT_ALARM_CONTROL{cmd:cancel}"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "alarm_cancel")
    assert len(received) == 1
    assert received[0]["cmd"] == "cancel"
    print("  OK alarm_cancel")


def test_alarm_sos():
    """alarm_sos → 发布 EVENT_ALARM_CONTROL{cmd:sos}"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "alarm_sos")
    assert len(received) == 1
    assert received[0]["cmd"] == "sos"
    print("  OK alarm_sos")


def test_alarm_stealth():
    """alarm_stealth → 发布 EVENT_ALARM_CONTROL{cmd:stealth}"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "alarm_stealth")
    assert len(received) == 1
    assert received[0]["cmd"] == "stealth"
    print("  OK alarm_stealth")


# ==================== 电源指令测试 ====================

def test_power_save():
    """power_save → 发布 POWER_STATE_CHANGE(SUSPENDED)"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: received.append(p))
    send_ble_cmd(bus, "power_save")
    assert len(received) == 1
    assert received[0]["power_state"] == POWER_STATE_SUSPENDED
    assert ctrl._control_state["power_mode"] == "suspended"
    print("  OK power_save")


def test_power_normal():
    """power_normal → 发布 POWER_STATE_CHANGE(ACTIVE)"""
    ctrl, bus = make_ctrl()
    ctrl._control_state["power_mode"] = "suspended"
    received = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: received.append(p))
    send_ble_cmd(bus, "power_normal")
    assert len(received) == 1
    assert received[0]["power_state"] == POWER_STATE_ACTIVE
    assert ctrl._control_state["power_mode"] == "active"
    print("  OK power_normal")


def test_power_emergency():
    """power_emergency → 发布 POWER_STATE_CHANGE(EMERGENCY)"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: received.append(p))
    send_ble_cmd(bus, "power_emergency")
    assert len(received) == 1
    assert received[0]["power_state"] == POWER_STATE_EMERGENCY
    assert ctrl._control_state["power_mode"] == "emergency"
    print("  OK power_emergency")


# ==================== 防抖 / 容错测试 ====================

def test_debounce():
    """防抖：300ms 内重复指令被忽略"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: received.append(p))
    send_ble_cmd(bus, "light_on")
    assert len(received) == 1
    send_ble_cmd(bus, "light_on")
    assert len(received) == 1, "debounce should block second call"
    print("  OK debounce")


def test_unknown_cmd():
    """未知指令被忽略"""
    ctrl, bus = make_ctrl()
    light_received = []
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: light_received.append(p))
    send_ble_cmd(bus, "unknown_cmd")
    assert len(light_received) == 0
    print("  OK unknown_cmd")


def test_invalid_json():
    """非法 JSON 不崩溃"""
    ctrl, bus = make_ctrl()
    bus.publish(EVENT_RIDE_CONTROL, {"raw": "not json"})
    bus.pump()
    assert ctrl.ctx["err_count"] > 0
    print("  OK invalid_json")


def test_non_ctrl_action():
    """非 ctrl action 被忽略"""
    ctrl, bus = make_ctrl()
    light_received = []
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: light_received.append(p))
    import json
    raw = json.dumps({"a": "nav", "d": {"dir": "right"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    assert len(light_received) == 0
    print("  OK non_ctrl_action")


# ==================== 状态回推测试 ====================

def test_state_push():
    """控制执行后触发 EVENT_CONTROL_STATE_CHANGED"""
    ctrl, bus = make_ctrl()
    received = []
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: received.append(p))
    send_ble_cmd(bus, "light_on")
    assert len(received) == 1
    assert received[0]["light_mode"] == "manual"
    print("  OK state_push")


# ==================== 数据接口测试 ====================

def test_get_data():
    """get_data 返回当前状态"""
    ctrl, bus = make_ctrl()
    d = ctrl.get_data()
    assert "last_cmd" in d
    assert "control_state" in d
    assert "timestamp" in d
    print("  OK get_data")


def test_get_status():
    """get_status 返回模块状态"""
    ctrl, bus = make_ctrl()
    s = ctrl.get_status()
    assert "is_init" in s
    assert s["is_init"] == True
    assert "control_state" in s
    print("  OK get_status")


# ==================== 无依赖降级测试 ====================

def test_no_event_bus():
    """无 EventBus 时不崩溃"""
    ctrl = ControlService(event_bus=None)
    ctrl.init()
    ctrl._execute_cmd("light_on", source="test")
    # 不崩溃即通过
    print("  OK no_event_bus")


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print(" ControlService v2 单元测试（纯事件驱动）")
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
        test_alarm_sos,
        test_alarm_stealth,
        test_power_save,
        test_power_normal,
        test_power_emergency,
        test_debounce,
        test_unknown_cmd,
        test_invalid_json,
        test_non_ctrl_action,
        test_state_push,
        test_get_data,
        test_get_status,
        test_no_event_bus,
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
