"""
brief Wave 2 Service层集成测试 - ControlService
note 验证 ControlService 接收 BLE 指令后正确发布控制事件
     纯事件驱动，无硬件依赖，仅需 EventBus + ControlService
     上传到板子运行: python test_control_service_integration.py
"""
import sys
import time
import json

# CPython 兼容：MicroPython 专有函数垫片
if not hasattr(time, "ticks_ms"):
    time.ticks_ms = lambda: int(time.time() * 1000)
if not hasattr(time, "ticks_diff"):
    time.ticks_diff = lambda a, b: a - b

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    EVENT_POWER_STATE_CHANGE, POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    POWER_STATE_EMERGENCY, EVENT_TTS_REQUEST,
)
from Modules.control_service import ControlService


# ==================== 事件日志 ====================

event_log = []


def _record(tag, payload):
    """记录事件到日志，tag为事件类型缩写"""
    event_log.append({"tag": tag, "payload": dict(payload)})


def _reset_log():
    """清空事件日志"""
    global event_log
    event_log = []


def _find_events(tag):
    """按tag查找事件记录"""
    return [e for e in event_log if e["tag"] == tag]


# ==================== 系统构建 ====================

def make_system():
    """
    brief 构建最小测试系统：EventBus + ControlService
    note ControlService 纯事件驱动，不依赖任何硬件模块
    return (bus, ctrl) 元组
    """
    bus = EventBus()
    ctrl = ControlService(bus)
    ctrl.init()

    # 订阅所有输出事件用于验证
    _reset_log()
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: _record("LIGHT", p))
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: _record("VOL", p))
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: _record("ALARM", p))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: _record("POWER", p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: _record("STATE", p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: _record("TTS", p))

    return bus, ctrl


def send_cmd(bus, cmd, ctrl=None):
    """
    brief 模拟 BLE 发送控制指令
    param bus: EventBus 实例
    param cmd: 指令字符串（如 "light_on"）
    param ctrl: ControlService 实例（可选，用于重置防抖）
    note 重置防抖 → 构造 JSON → 发布 EVENT_RIDE_CONTROL → 泵送
    """
    if ctrl is not None:
        ctrl.ctx["last_cmd_tick"] = 0  # 重置防抖，允许连续发送
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()


# ==================== 测试用例 ====================

def test_01_init_and_subscribe():
    """测试1: init() 成功，订阅 EVENT_RIDE_CONTROL"""
    bus, ctrl = make_system()
    assert ctrl.ctx["is_init"] is True, "init 应成功"
    # 验证 EVENT_RIDE_CONTROL 有订阅者
    subs = bus._subscribers.get(EVENT_RIDE_CONTROL, [])
    assert len(subs) > 0, "应订阅 EVENT_RIDE_CONTROL"
    print("  OK test_01_init_and_subscribe")


def test_02_light_on():
    """测试2: light_on → 发布 EVENT_LIGHT_CONTROL{cmd:on}"""
    bus, ctrl = make_system()
    send_cmd(bus, "light_on", ctrl)
    lights = _find_events("LIGHT")
    assert len(lights) >= 1, "应发布 EVENT_LIGHT_CONTROL, 实际: %s" % event_log
    assert lights[0]["payload"]["cmd"] == "on", "cmd 应为 on"
    print("  OK test_02_light_on")


def test_03_light_off():
    """测试3: light_off → 发布 EVENT_LIGHT_CONTROL{cmd:off}"""
    bus, ctrl = make_system()
    send_cmd(bus, "light_off", ctrl)
    lights = _find_events("LIGHT")
    assert len(lights) >= 1, "应发布 EVENT_LIGHT_CONTROL, 实际: %s" % event_log
    assert lights[0]["payload"]["cmd"] == "off", "cmd 应为 off"
    print("  OK test_03_light_off")


def test_04_brightness():
    """测试4: brightness_up/down → EVENT_LIGHT_CONTROL 带正确 cmd"""
    bus, ctrl = make_system()
    # brightness_up
    send_cmd(bus, "brightness_up", ctrl)
    lights = _find_events("LIGHT")
    assert len(lights) >= 1, "brightness_up 应发布 EVENT_LIGHT_CONTROL"
    assert lights[0]["payload"]["cmd"] == "brightness_up", "cmd 应为 brightness_up"
    # brightness_down
    _reset_log()
    bus.subscribe = lambda e, c: None  # 重新订阅已在 make_system 中完成
    # 重新构建系统避免重复订阅问题
    bus, ctrl = make_system()
    send_cmd(bus, "brightness_down", ctrl)
    lights = _find_events("LIGHT")
    assert len(lights) >= 1, "brightness_down 应发布 EVENT_LIGHT_CONTROL"
    assert lights[0]["payload"]["cmd"] == "brightness_down", "cmd 应为 brightness_down"
    print("  OK test_04_brightness")


def test_05_volume():
    """测试5: volume_up/down → EVENT_VOLUME_CONTROL 带正确 cmd"""
    bus, ctrl = make_system()
    # volume_up
    send_cmd(bus, "volume_up", ctrl)
    vols = _find_events("VOL")
    assert len(vols) >= 1, "volume_up 应发布 EVENT_VOLUME_CONTROL"
    assert vols[0]["payload"]["cmd"] == "up", "cmd 应为 up"
    # volume_down
    bus, ctrl = make_system()
    send_cmd(bus, "volume_down", ctrl)
    vols = _find_events("VOL")
    assert len(vols) >= 1, "volume_down 应发布 EVENT_VOLUME_CONTROL"
    assert vols[0]["payload"]["cmd"] == "down", "cmd 应为 down"
    print("  OK test_05_volume")


def test_06_alarm_sos():
    """测试6: alarm_sos → EVENT_ALARM_CONTROL{cmd:sos}"""
    bus, ctrl = make_system()
    send_cmd(bus, "alarm_sos", ctrl)
    alarms = _find_events("ALARM")
    assert len(alarms) >= 1, "alarm_sos 应发布 EVENT_ALARM_CONTROL"
    assert alarms[0]["payload"]["cmd"] == "sos", "cmd 应为 sos"
    print("  OK test_06_alarm_sos")


def test_07_alarm_cancel():
    """测试7: alarm_cancel → EVENT_ALARM_CONTROL{cmd:cancel}"""
    bus, ctrl = make_system()
    send_cmd(bus, "alarm_cancel", ctrl)
    alarms = _find_events("ALARM")
    assert len(alarms) >= 1, "alarm_cancel 应发布 EVENT_ALARM_CONTROL"
    assert alarms[0]["payload"]["cmd"] == "cancel", "cmd 应为 cancel"
    print("  OK test_07_alarm_cancel")


def test_08_power_save():
    """测试8: power_save → EVENT_POWER_STATE_CHANGE{SUSPENDED}"""
    bus, ctrl = make_system()
    send_cmd(bus, "power_save", ctrl)
    powers = _find_events("POWER")
    assert len(powers) >= 1, "power_save 应发布 EVENT_POWER_STATE_CHANGE"
    assert powers[0]["payload"]["power_state"] == POWER_STATE_SUSPENDED, \
        "power_state 应为 SUSPENDED, 实际: %s" % powers[0]["payload"]
    print("  OK test_08_power_save")


def test_09_power_normal():
    """测试9: power_normal → EVENT_POWER_STATE_CHANGE{ACTIVE}"""
    bus, ctrl = make_system()
    send_cmd(bus, "power_normal", ctrl)
    powers = _find_events("POWER")
    assert len(powers) >= 1, "power_normal 应发布 EVENT_POWER_STATE_CHANGE"
    assert powers[0]["payload"]["power_state"] == POWER_STATE_ACTIVE, \
        "power_state 应为 ACTIVE, 实际: %s" % powers[0]["payload"]
    print("  OK test_09_power_normal")


def test_10_power_emergency():
    """测试10: power_emergency → EVENT_POWER_STATE_CHANGE{EMERGENCY}"""
    bus, ctrl = make_system()
    send_cmd(bus, "power_emergency", ctrl)
    powers = _find_events("POWER")
    assert len(powers) >= 1, "power_emergency 应发布 EVENT_POWER_STATE_CHANGE"
    assert powers[0]["payload"]["power_state"] == POWER_STATE_EMERGENCY, \
        "power_state 应为 EMERGENCY, 实际: %s" % powers[0]["payload"]
    print("  OK test_10_power_emergency")


def test_11_query_status():
    """测试11: query_status → EVENT_CONTROL_STATE_CHANGED (状态快照)"""
    bus, ctrl = make_system()
    send_cmd(bus, "query_status", ctrl)
    states = _find_events("STATE")
    # query_status 调用 _query_status() → _tts() → 然后 _push_state()
    assert len(states) >= 1, "query_status 应触发 _push_state → EVENT_CONTROL_STATE_CHANGED"
    print("  OK test_11_query_status")


def test_12_state_snapshot_fields():
    """测试12: 状态快照包含 light_brightness, volume, power_mode"""
    bus, ctrl = make_system()
    send_cmd(bus, "light_on", ctrl)
    states = _find_events("STATE")
    assert len(states) >= 1, "应发布 EVENT_CONTROL_STATE_CHANGED"
    snap = states[0]["payload"]
    assert "b" in snap, "快照应含 brightness (b 字段), 实际: %s" % snap
    assert "v" in snap, "快照应含 volume (v 字段), 实际: %s" % snap
    assert "p" in snap, "快照应含 power_mode (p 字段), 实际: %s" % snap
    # light_on 后亮度应为默认值
    assert snap["b"] == ctrl.cfg["default_brightness"], \
        "light_on 后亮度应为 %d, 实际: %d" % (ctrl.cfg["default_brightness"], snap["b"])
    print("  OK test_12_state_snapshot_fields")


def test_13_continuous_commands():
    """测试13: 连续指令 — 防抖重置后每条指令都执行"""
    bus, ctrl = make_system()
    cmds = ["light_on", "volume_up", "brightness_up"]
    for cmd in cmds:
        send_cmd(bus, cmd, ctrl)

    lights = _find_events("LIGHT")
    vols = _find_events("VOL")
    # light_on + brightness_up → 2 条 LIGHT 事件
    assert len(lights) >= 2, "连续指令应全部执行, LIGHT 事件数: %d, 日志: %s" % (len(lights), event_log)
    # volume_up → 1 条 VOL 事件
    assert len(vols) >= 1, "volume_up 应执行, VOL 事件数: %d" % len(vols)
    # 验证最后执行的指令
    assert ctrl._data["last_cmd"] == "brightness_up", \
        "最后指令应为 brightness_up, 实际: %s" % ctrl._data["last_cmd"]
    print("  OK test_13_continuous_commands")


# ==================== 主入口 ====================

def run_all():
    """运行所有测试"""
    tests = [
        test_01_init_and_subscribe,
        test_02_light_on,
        test_03_light_off,
        test_04_brightness,
        test_05_volume,
        test_06_alarm_sos,
        test_07_alarm_cancel,
        test_08_power_save,
        test_09_power_normal,
        test_10_power_emergency,
        test_11_query_status,
        test_12_state_snapshot_fields,
        test_13_continuous_commands,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print("  FAIL %s: %s" % (t.__name__, e))

    print("\n=== ControlService 集成测试结果 ===")
    print("通过: %d / 失败: %d / 总计: %d" % (passed, failed, len(tests)))
    if failed == 0:
        print("全部通过!")
    return failed


if __name__ == "__main__":
    run_all()
