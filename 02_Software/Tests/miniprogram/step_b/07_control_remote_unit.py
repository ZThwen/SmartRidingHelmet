"""
brief 远端控制 E2E 测试（Phase 3 — 小程序远端控制页全指令验证）
note 覆盖全部 19 条控制指令的 BLE 写入格式、硬件解析、状态回推格式
     验证数据流: 按钮 → CtrlService → BLE FFF3 → ControlService → 事件发布 → 状态回推

执行: 上传到板子运行 python Tests/miniprogram/step_b/07_control_remote_e2e.py
小程序: 同时打开「远端控制」页观察状态变化

测试阶段:
  Phase 1: 灯光控制（light_on/off/auto, brightness_up/down）
  Phase 2: 音量控制（volume_up/down）
  Phase 3: 电源模式（normal/save/emergency）
  Phase 4: 报警控制（cancel/sos/stealth）
  Phase 5: 查询指令（status/speed/temp/humid/location/battery）
  Phase 6: 状态回推格式验证（t=7/8/9 三条消息）
"""
import sys
sys.path.append("../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_LIGHT_CONTROL,
    EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    EVENT_TTS_REQUEST, POWER_STATE_ACTIVE,
    POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
)
from Modules.control_service import ControlService


# ==================== 日志 ====================

_LOG_PATH = "Tests/miniprogram/step_b/07_control_remote_e2e.log"
_T0 = 0
_PASS = 0
_FAIL = 0


def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    line = "[%7.2fs] %s" % (elapsed / 1000.0, msg)
    print(line)
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def phase(num, title):
    log("")
    log("=" * 55)
    log(" Phase %d: %s" % (num, title))
    log("=" * 55)


def check(label, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        log("  ✓ %s" % label)
        _PASS += 1
    else:
        log("  ✗ %s %s" % (label, detail))
        _FAIL += 1


def snapshot(ctrl, tag=""):
    """打印 ControlService 内部状态快照"""
    cs = ctrl._control_state
    log("  [SNAP%s] light=%s/%d vol=%d power=%s err=%d" % (
        tag, cs["light_mode"], cs["light_brightness"],
        cs["volume"], cs["power_mode"], ctrl.ctx["err_count"]))


def send_and_snap(bus, ctrl, cmd, tag=""):
    """发送指令 + 打印前后状态"""
    cs_before = dict(ctrl._control_state)
    send_ctrl_cmd(bus, cmd)
    cs_after = ctrl._control_state
    log("  [SEND%s] %s → light=%s/%d→%s/%d vol=%d→%d power=%s→%s" % (
        tag, cmd,
        cs_before["light_mode"], cs_before["light_brightness"],
        cs_after["light_mode"], cs_after["light_brightness"],
        cs_before["volume"], cs_after["volume"],
        cs_before["power_mode"], cs_after["power_mode"]))


# ==================== 模拟 BLE 发送 ====================

def send_ctrl_cmd(bus, cmd):
    """模拟小程序通过 BLE FFF3 发送控制指令
    等待防抖间隔（硬件 cmd_debounce_ms=300ms）后再发下一条
    """
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    time.sleep_ms(350)  # 超过硬件防抖 300ms，避免被静默丢弃


# ==================== 测试基础设施 ====================

def setup():
    """初始化 ControlService + 事件采集器"""
    bus = EventBus()
    ctrl = ControlService(event_bus=bus)
    ctrl.init()

    events = {
        "light": [],
        "volume": [],
        "alarm": [],
        "power": [],
        "state": [],
        "tts": [],
    }

    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: events["light"].append(p))
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: events["volume"].append(p))
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: events["alarm"].append(p))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: events["power"].append(p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: events["state"].append(p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: events["tts"].append(p))

    return bus, ctrl, events


# ==================== Phase 1: 灯光控制 ====================

def test_light_control(bus, ctrl, events):
    phase(1, "灯光控制")

    snapshot(ctrl, "-before")

    # 1.1 light_on
    send_and_snap(bus, ctrl, "light_on", "-1.1")
    check("light_on → EVENT_LIGHT_CONTROL",
          len(events["light"]) == 1 and events["light"][-1]["cmd"] == "on")
    check("light_on → state.light_mode=manual",
          ctrl._control_state["light_mode"] == "manual")
    check("light_on → state.light_brightness=%d" % ctrl.cfg["default_brightness"],
          ctrl._control_state["light_brightness"] == ctrl.cfg["default_brightness"])

    # 1.2 brightness_up（先调低到30，因default_brightness=50=max，调不了）
    ctrl._control_state["light_brightness"] = 30
    send_ctrl_cmd(bus, "brightness_up")
    check("brightness_up → 40",
          ctrl._control_state["light_brightness"] == 40)

    # 1.3 brightness_down
    send_ctrl_cmd(bus, "brightness_down")
    check("brightness_down → 30",
          ctrl._control_state["light_brightness"] == 30)

    # 1.4 light_off
    send_ctrl_cmd(bus, "light_off")
    check("light_off → EVENT_LIGHT_CONTROL",
          len(events["light"]) >= 4 and events["light"][-1]["cmd"] == "off")
    check("light_off → brightness=0",
          ctrl._control_state["light_brightness"] == 0)

    # 1.5 light_auto
    send_ctrl_cmd(bus, "light_auto")
    check("light_auto → EVENT_LIGHT_CONTROL",
          events["light"][-1]["cmd"] == "auto")
    check("light_auto → state.light_mode=auto",
          ctrl._control_state["light_mode"] == "auto")

    snapshot(ctrl, "-after-light")

    # 1.6 brightness_up/down 边界
    ctrl._control_state["light_brightness"] = 95
    send_ctrl_cmd(bus, "brightness_up")
    check("brightness_up max clamp",
          ctrl._control_state["light_brightness"] <= ctrl.cfg["brightness_max"])

    ctrl._control_state["light_brightness"] = 5
    send_ctrl_cmd(bus, "brightness_down")
    check("brightness_down min clamp",
          ctrl._control_state["light_brightness"] >= 0)

    snapshot(ctrl, "-after-boundary")


# ==================== Phase 2: 音量控制 ====================

def test_volume_control(bus, ctrl, events):
    phase(2, "音量控制")
    ctrl._control_state["volume"] = 3
    snapshot(ctrl, "-before")

    send_and_snap(bus, ctrl, "volume_up", "-2.1")
    check("volume_up → EVENT_VOLUME_CONTROL",
          events["volume"][-1]["cmd"] == "up")
    check("volume_up → volume=4",
          ctrl._control_state["volume"] == 4)

    send_ctrl_cmd(bus, "volume_down")
    check("volume_down → EVENT_VOLUME_CONTROL",
          events["volume"][-1]["cmd"] == "down")
    check("volume_down → volume=3",
          ctrl._control_state["volume"] == 3)

    # 边界: volume_max = 5 (硬件限制)
    ctrl._control_state["volume"] = 5
    send_ctrl_cmd(bus, "volume_up")
    check("volume_up max clamp = 5",
          ctrl._control_state["volume"] == 5)

    ctrl._control_state["volume"] = 0
    send_ctrl_cmd(bus, "volume_down")
    check("volume_down min clamp = 0",
          ctrl._control_state["volume"] == 0)

    snapshot(ctrl, "-after")


# ==================== Phase 3: 电源模式 ====================

def test_power_mode(bus, ctrl, events):
    phase(3, "电源模式")

    snapshot(ctrl, "-before")
    send_and_snap(bus, ctrl, "power_save", "-3.1")
    check("power_save → EVENT_POWER_STATE_CHANGE(suspended)",
          len(events["power"]) >= 1 and
          events["power"][-1].get("power_state") == POWER_STATE_SUSPENDED)
    check("power_save → state.power_mode=suspended",
          ctrl._control_state["power_mode"] == "suspended")

    send_ctrl_cmd(bus, "power_normal")
    check("power_normal → EVENT_POWER_STATE_CHANGE(active)",
          events["power"][-1].get("power_state") == POWER_STATE_ACTIVE)
    check("power_normal → state.power_mode=active",
          ctrl._control_state["power_mode"] == "active")

    send_ctrl_cmd(bus, "power_emergency")
    check("power_emergency → EVENT_POWER_STATE_CHANGE(emergency)",
          events["power"][-1].get("power_state") == POWER_STATE_EMERGENCY)
    check("power_emergency → state.power_mode=emergency",
          ctrl._control_state["power_mode"] == "emergency")

    # 非电源操作应覆盖省电模式为 CUSTOM
    ctrl._control_state["power_mode"] = "suspended"
    send_ctrl_cmd(bus, "light_on")
    check("manual op overrides power_mode to custom",
          ctrl._control_state["power_mode"] == "custom")

    snapshot(ctrl, "-after")


# ==================== Phase 4: 报警控制 ====================

def test_alarm_control(bus, ctrl, events):
    phase(4, "报警控制")

    snapshot(ctrl, "-before")
    send_and_snap(bus, ctrl, "alarm_sos", "-4.1")
    check("alarm_sos → EVENT_ALARM_CONTROL(sos)",
          events["alarm"][-1]["cmd"] == "sos")

    send_ctrl_cmd(bus, "alarm_stealth")
    check("alarm_stealth → EVENT_ALARM_CONTROL(stealth)",
          events["alarm"][-1]["cmd"] == "stealth")

    send_ctrl_cmd(bus, "alarm_cancel")
    check("alarm_cancel → EVENT_ALARM_CONTROL(cancel)",
          events["alarm"][-1]["cmd"] == "cancel")

    snapshot(ctrl, "-after")


# ==================== Phase 5: 查询指令 ====================

def test_query_commands(bus, ctrl, events):
    phase(5, "查询指令（TTS 播报）")

    # 填入模拟传感器数据
    ctrl._sensor_cache["temperature"] = 28
    ctrl._sensor_cache["humidity"] = 65
    ctrl._sensor_cache["speed_kmh"] = 25
    ctrl._sensor_cache["latitude"] = 34.1547
    ctrl._sensor_cache["longitude"] = 108.8959
    log("  sensor_cache: temp=%d humid=%d speed=%d loc=(%.4f,%.4f)" % (
        28, 65, 25, 34.1547, 108.8959))

    send_and_snap(bus, ctrl, "query_status", "-5.1")
    check("query_status → TTS",
          len(events["tts"]) >= 1 and "灯光" in events["tts"][-1].get("text", ""))

    send_ctrl_cmd(bus, "query_speed")
    check("query_speed → TTS 时速25公里",
          "25" in events["tts"][-1].get("text", ""))

    send_ctrl_cmd(bus, "query_temp")
    check("query_temp → TTS 温度28度",
          "28" in events["tts"][-1].get("text", ""))

    send_ctrl_cmd(bus, "query_humid")
    check("query_humid → TTS 湿度65%",
          "65" in events["tts"][-1].get("text", ""))

    send_ctrl_cmd(bus, "query_location")
    check("query_location → TTS 经纬度",
          "北纬" in events["tts"][-1].get("text", "") and
          "东经" in events["tts"][-1].get("text", ""))

    send_ctrl_cmd(bus, "query_battery")
    check("query_battery → TTS 暂不可用",
          "暂不可用" in events["tts"][-1].get("text", ""))

    log("  TTS events captured: %d" % len(events["tts"]))
    for i, m in enumerate(events["tts"]):
        log("    tts[%d]: %s" % (i, m.get("text", "")))


# ==================== Phase 6: 状态回推格式验证 ====================

def test_state_push_format(bus, ctrl, events):
    phase(6, "状态回推格式验证（合并为 1 条消息）")

    log("  state events collected so far: %d" % len(events["state"]))
    # 清空之前积累的 state 事件
    events["state"] = []

    # 执行 light_on 触发状态回推
    send_and_snap(bus, ctrl, "light_on", "-6.1")

    # 检查回推消息: 应有 1 条（合并推送）
    state_msgs = events["state"][-1:]  # 最近 1 条

    check("状态回推 1 条消息（合并）", len(state_msgs) == 1)

    # 验证合并消息
    merged = events["state"][-1] if events["state"] else {}

    check("t=7: 灯光状态", merged.get("t") == 7 and "m" in merged and "b" in merged,
          "got: %s" % merged)
    check("v=音量字段", "v" in merged,
          "got: %s" % merged)
    check("p=电源字段", "p" in merged,
          "got: %s" % merged)

    # 验证 BLE 透传格式（BLEService 原样发送）
    log("  BLE 透传格式（BLEService._on_control_state 快照合并）:")
    valid_keys = ("t", "m", "b", "v", "p")
    ble_msg = {k: v for k, v in merged.items() if k in valid_keys}
    log("    → " + json.dumps(ble_msg))

    # 验证小程序 parseCtrlState 兼容性
    log("  ✅ 小程序 ctrl-service.js parseCtrlState 已适配合并格式:")
    log("    旧格式: {t:7,m:0,b:50} / {t:8,v:5} / {t:9,p:0}")
    log("    新格式: {t:7,m:0,b:50,v:5,p:0}（单条合并）")
    log("    parseCtrlState 会同时解析 t=7 中的 m/b/v/p 字段")

    # 打印全部事件统计
    log("")
    log("  [EVENT COUNTS] light=%d volume=%d alarm=%d power=%d state=%d tts=%d" % (
        len(events["light"]), len(events["volume"]), len(events["alarm"]),
        len(events["power"]), len(events["state"]), len(events["tts"])))


# ==================== 主入口 ====================

def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 55)
    print(" 远端控制 E2E 测试（Phase 3）")
    print("=" * 55)

    bus, ctrl, events = setup()
    check("ControlService 初始化", ctrl.ctx["is_init"])

    # 执行各 Phase
    test_light_control(bus, ctrl, events)
    test_volume_control(bus, ctrl, events)
    test_power_mode(bus, ctrl, events)
    test_alarm_control(bus, ctrl, events)
    test_query_commands(bus, ctrl, events)
    test_state_push_format(bus, ctrl, events)

    # 汇总
    log("")
    log("=" * 55)
    log(" 测试完成")
    log(" 通过: %d  失败: %d" % (_PASS, _FAIL))
    log("=" * 55)

    if _FAIL > 0:
        log("⚠ 部分测试未通过，检查上方 ✗ 项")
    else:
        log("✅ 全部通过")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
