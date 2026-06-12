"""
brief ControlService v2 E2E 测试（纯事件驱动架构）
note 不依赖真实硬件，验证事件发布 + 乐观状态更新
     上传到板子运行 python test_control_service_v2.py
     每个场景暂停，方便观察 LED/音频/LCD 反应
"""
import sys
import time
import json
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_LIGHT_CONTROL,
    EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
)
from Modules.control_service import ControlService


# ==================== 工具函数 ====================

def make_ctrl():
    """创建已 init 的 ControlService + 事件监听器"""
    bus = EventBus()
    ctrl = ControlService(bus)
    ctrl.init()

    # 注册事件监听器，记录所有发布的事件
    events = {
        "light": [],
        "volume": [],
        "alarm": [],
        "power": [],
        "state": [],
    }
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: events["light"].append(p))
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: events["volume"].append(p))
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: events["alarm"].append(p))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: events["power"].append(p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: events["state"].append(p))

    return ctrl, bus, events


def clear_events(events):
    """清空事件记录"""
    for k in events:
        events[k].clear()


def send_ble_cmd(bus, cmd):
    """发送 BLE 控制指令并返回 JSON"""
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    return raw


def print_state(ctrl, label="当前状态"):
    """打印 ControlService 状态快照"""
    cs = ctrl._control_state
    print("  %s: light_brightness=%s, light_mode=%s, volume=%s, power_mode=%s" % (
        label, cs["light_brightness"], cs["light_mode"], cs["volume"], cs["power_mode"]))


def print_events(events):
    """打印最近发布的事件"""
    for category in ["light", "volume", "alarm", "power", "state"]:
        for e in events[category]:
            print("  EVENT_%s: %s" % (category.upper(), e))


def check(test_name, ctrl, events, expected_state=None, expected_event_category=None):
    """检查结果并打印详细信息"""
    passed = True

    # 检查状态
    if expected_state:
        cs = ctrl._control_state
        for key, expected_val in expected_state.items():
            actual_val = cs.get(key)
            if actual_val != expected_val:
                print("  ❌ 状态不匹配: %s 期望=%s 实际=%s" % (key, expected_val, actual_val))
                passed = False

    # 检查事件
    if expected_event_category:
        if not events.get(expected_event_category):
            print("  ❌ 未收到 EVENT_%s" % expected_event_category.upper())
            passed = False

    if passed:
        print("  ✅ %s 通过" % test_name)
    else:
        print("  ❌ %s 失败" % test_name)

    return passed


def wait_next():
    """暂停等待用户观察"""
    try:
        input("  按回车继续...")
    except (EOFError, KeyboardInterrupt):
        print("\n测试中断")
        sys.exit(0)


# ==================== 测试场景 ====================

def scene_light_on_off(ctrl, bus, events):
    """场景: 灯光开/关"""
    print("\n" + "=" * 50)
    print("场景: 灯光开/关")
    print("=" * 50)

    # light_on
    clear_events(events)
    print("\n--- light_on ---")
    raw = send_ble_cmd(bus, "light_on")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("light_on", ctrl, events,
          expected_state={"light_mode": "manual", "light_brightness": ctrl.cfg["default_brightness"]},
          expected_event_category="light")
    wait_next()

    # light_off
    clear_events(events)
    print("\n--- light_off ---")
    raw = send_ble_cmd(bus, "light_off")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("light_off", ctrl, events,
          expected_state={"light_brightness": 0},
          expected_event_category="light")
    wait_next()


def scene_brightness(ctrl, bus, events):
    """场景: 亮度调节"""
    print("\n" + "=" * 50)
    print("场景: 亮度调节")
    print("=" * 50)

    # 先设到 30%
    ctrl._control_state["light_brightness"] = 30
    ctrl._control_state["light_mode"] = "manual"

    # brightness_up
    clear_events(events)
    print("\n--- brightness_up (30→40) ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "brightness_up")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("brightness_up", ctrl, events,
          expected_state={"light_brightness": 40},
          expected_event_category="light")
    wait_next()

    # brightness_down
    clear_events(events)
    print("\n--- brightness_down (40→30) ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "brightness_down")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("brightness_down", ctrl, events,
          expected_state={"light_brightness": 30},
          expected_event_category="light")
    wait_next()

    # brightness_up 上限
    clear_events(events)
    ctrl._control_state["light_brightness"] = ctrl.cfg["brightness_max"] - 5
    print("\n--- brightness_up 上限测试 (%s→%s) ---" % (
        ctrl.cfg["brightness_max"] - 5, ctrl.cfg["brightness_max"]))
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "brightness_up")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("brightness_up_max", ctrl, events,
          expected_state={"light_brightness": ctrl.cfg["brightness_max"]},
          expected_event_category="light")
    wait_next()

    # brightness_down 下限
    clear_events(events)
    ctrl._control_state["light_brightness"] = 5
    print("\n--- brightness_down 下限测试 (5→0) ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "brightness_down")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("brightness_down_min", ctrl, events,
          expected_state={"light_brightness": 0},
          expected_event_category="light")
    wait_next()


def scene_light_auto(ctrl, bus, events):
    """场景: 自动模式"""
    print("\n" + "=" * 50)
    print("场景: 自动模式")
    print("=" * 50)

    ctrl._control_state["light_mode"] = "manual"
    clear_events(events)
    print("\n--- light_auto ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "light_auto")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("light_auto", ctrl, events,
          expected_state={"light_mode": "auto"},
          expected_event_category="light")
    wait_next()


def scene_volume(ctrl, bus, events):
    """场景: 音量调节"""
    print("\n" + "=" * 50)
    print("场景: 音量调节")
    print("=" * 50)

    # volume_up
    ctrl._control_state["volume"] = 3
    clear_events(events)
    print("\n--- volume_up (3→4) ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "volume_up")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("volume_up", ctrl, events,
          expected_state={"volume": 4},
          expected_event_category="volume")
    wait_next()

    # volume_down
    clear_events(events)
    print("\n--- volume_down (4→3) ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "volume_down")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("volume_down", ctrl, events,
          expected_state={"volume": 3},
          expected_event_category="volume")
    wait_next()

    # volume_up 上限
    ctrl._control_state["volume"] = 5
    clear_events(events)
    print("\n--- volume_up 上限测试 (5→5, 不变) ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "volume_up")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("volume_up_max", ctrl, events,
          expected_state={"volume": 5})
    wait_next()

    # volume_down 下限
    ctrl._control_state["volume"] = 0
    clear_events(events)
    print("\n--- volume_down 下限测试 (0→0, 不变) ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "volume_down")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("volume_down_min", ctrl, events,
          expected_state={"volume": 0})
    wait_next()


def scene_alarm(ctrl, bus, events):
    """场景: 报警指令"""
    print("\n" + "=" * 50)
    print("场景: 报警指令")
    print("=" * 50)

    # alarm_cancel
    clear_events(events)
    print("\n--- alarm_cancel ---")
    raw = send_ble_cmd(bus, "alarm_cancel")
    print("  发送: %s" % raw)
    print_events(events)
    check("alarm_cancel", ctrl, events,
          expected_event_category="alarm")
    wait_next()

    # alarm_sos
    clear_events(events)
    print("\n--- alarm_sos ---")
    raw = send_ble_cmd(bus, "alarm_sos")
    print("  发送: %s" % raw)
    print_events(events)
    check("alarm_sos", ctrl, events,
          expected_event_category="alarm")
    wait_next()

    # alarm_stealth
    clear_events(events)
    print("\n--- alarm_stealth ---")
    raw = send_ble_cmd(bus, "alarm_stealth")
    print("  发送: %s" % raw)
    print_events(events)
    check("alarm_stealth", ctrl, events,
          expected_event_category="alarm")
    wait_next()


def scene_power(ctrl, bus, events):
    """场景: 电源模式"""
    print("\n" + "=" * 50)
    print("场景: 电源模式")
    print("=" * 50)

    # power_save
    clear_events(events)
    print("\n--- power_save ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "power_save")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("power_save", ctrl, events,
          expected_state={"power_mode": "suspended"},
          expected_event_category="power")
    wait_next()

    # power_emergency
    clear_events(events)
    print("\n--- power_emergency ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "power_emergency")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("power_emergency", ctrl, events,
          expected_state={"power_mode": "emergency"},
          expected_event_category="power")
    wait_next()

    # power_normal
    clear_events(events)
    print("\n--- power_normal ---")
    print_state(ctrl, "执行前")
    raw = send_ble_cmd(bus, "power_normal")
    print("  发送: %s" % raw)
    print_state(ctrl, "执行后")
    print_events(events)
    check("power_normal", ctrl, events,
          expected_state={"power_mode": "active"},
          expected_event_category="power")
    wait_next()


def scene_debounce(ctrl, bus, events):
    """场景: 防抖测试"""
    print("\n" + "=" * 50)
    print("场景: 防抖测试（300ms 内重复指令应被忽略）")
    print("=" * 50)

    clear_events(events)
    print("\n--- 连续发送两次 light_on ---")
    raw1 = send_ble_cmd(bus, "light_on")
    print("  第1次发送: %s" % raw1)
    print("  light 事件数: %d" % len(events["light"]))

    raw2 = send_ble_cmd(bus, "light_on")
    print("  第2次发送: %s" % raw2)
    print("  light 事件数: %d (应仍为1)" % len(events["light"]))

    if len(events["light"]) == 1:
        print("  ✅ 防抖生效，第2次被忽略")
    else:
        print("  ❌ 防抖失败，收到 %d 次事件" % len(events["light"]))
    wait_next()


def scene_edge_cases(ctrl, bus, events):
    """场景: 边界/容错"""
    print("\n" + "=" * 50)
    print("场景: 边界/容错")
    print("=" * 50)

    # 非法 JSON
    clear_events(events)
    print("\n--- 非法 JSON ---")
    bus.publish(EVENT_RIDE_CONTROL, {"raw": "not json"})
    bus.pump()
    print("  发送: 'not json'")
    print("  err_count: %d" % ctrl.ctx["err_count"])
    if ctrl.ctx["err_count"] > 0:
        print("  ✅ 错误被捕获，系统未崩溃")
    else:
        print("  ❌ err_count 未增加")
    wait_next()

    # 非 ctrl action
    clear_events(events)
    print("\n--- 非 ctrl action (nav) ---")
    raw = json.dumps({"a": "nav", "d": {"dir": "right"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    print("  发送: %s" % raw)
    print("  light 事件数: %d (应为0)" % len(events["light"]))
    if len(events["light"]) == 0:
        print("  ✅ 非 ctrl action 被忽略")
    else:
        print("  ❌ 非 ctrl action 未被忽略")
    wait_next()

    # 未知指令
    clear_events(events)
    print("\n--- 未知指令 ---")
    raw = send_ble_cmd(bus, "unknown_cmd")
    print("  发送: %s" % raw)
    all_events = sum(len(v) for v in events.values())
    print("  总事件数: %d (应为0)" % all_events)
    if all_events == 0:
        print("  ✅ 未知指令被忽略")
    else:
        print("  ❌ 未知指令产生了事件")
    wait_next()


def scene_state_push(ctrl, bus, events):
    """场景: 状态回推"""
    print("\n" + "=" * 50)
    print("场景: 状态回推 (EVENT_CONTROL_STATE_CHANGED)")
    print("=" * 50)

    clear_events(events)
    print("\n--- light_on 后检查状态回推 ---")
    raw = send_ble_cmd(bus, "light_on")
    print("  发送: %s" % raw)
    print("  state 事件数: %d" % len(events["state"]))
    if events["state"]:
        print("  回推内容: %s" % events["state"][-1])
        if events["state"][-1].get("light_mode") == "manual":
            print("  ✅ 状态回推正确")
        else:
            print("  ❌ 状态回推内容不正确")
    else:
        print("  ❌ 未收到状态回推")
    wait_next()


def scene_data_interface(ctrl, bus, events):
    """场景: 数据接口"""
    print("\n" + "=" * 50)
    print("场景: 数据接口 (get_data / get_status)")
    print("=" * 50)

    print("\n--- get_data ---")
    d = ctrl.get_data()
    print("  last_cmd: %s" % d.get("last_cmd"))
    print("  last_cmd_source: %s" % d.get("last_cmd_source"))
    print("  control_state: %s" % d.get("control_state"))
    print("  timestamp: %s" % d.get("timestamp"))
    required_keys = ["last_cmd", "last_cmd_source", "control_state", "timestamp"]
    missing = [k for k in required_keys if k not in d]
    if not missing:
        print("  ✅ get_data 字段完整")
    else:
        print("  ❌ get_data 缺少字段: %s" % missing)
    wait_next()

    print("\n--- get_status ---")
    s = ctrl.get_status()
    print("  is_init: %s" % s.get("is_init"))
    print("  err_count: %s" % s.get("err_count"))
    print("  control_state: %s" % s.get("control_state"))
    if s.get("is_init") == True and "control_state" in s:
        print("  ✅ get_status 正常")
    else:
        print("  ❌ get_status 异常")
    wait_next()


def scene_no_event_bus():
    """场景: 无 EventBus 降级"""
    print("\n" + "=" * 50)
    print("场景: 无 EventBus 降级运行")
    print("=" * 50)

    print("\n--- 无 EventBus 初始化 + 执行指令 ---")
    ctrl = ControlService(event_bus=None)
    ctrl.init()
    print("  is_init: %s" % ctrl.ctx["is_init"])
    ctrl._execute_cmd("light_on", source="test")
    print("  执行 light_on 后未崩溃")
    print("  ✅ 无 EventBus 降级正常")
    try:
        input("  按回车继续...")
    except (EOFError, KeyboardInterrupt):
        print("\n测试中断")
        sys.exit(0)


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print(" ControlService v2 E2E 测试（纯事件驱动）")
    print(" 每个场景暂停，按回车继续")
    print("=" * 50)

    ctrl, bus, events = make_ctrl()
    passed = 0
    failed = 0

    try:
        # 灯光
        scene_light_on_off(ctrl, bus, events)
        scene_brightness(ctrl, bus, events)
        scene_light_auto(ctrl, bus, events)

        # 音量
        scene_volume(ctrl, bus, events)

        # 报警
        scene_alarm(ctrl, bus, events)

        # 电源
        scene_power(ctrl, bus, events)

        # 防抖/容错
        scene_debounce(ctrl, bus, events)
        scene_edge_cases(ctrl, bus, events)

        # 状态回推
        scene_state_push(ctrl, bus, events)

        # 数据接口
        scene_data_interface(ctrl, bus, events)

        # 无 EventBus 降级
        scene_no_event_bus()

    except KeyboardInterrupt:
        print("\n\n测试被中断")

    print("\n" + "=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
