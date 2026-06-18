"""
brief ControlService 单元测试（v2 纯事件驱动）
note 不依赖真实硬件，使用 EventBus 事件监听验证
     验证指令路由、防抖、状态回推、TTS 反馈
执行: 上传到板子运行 python test_control_service.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    POWER_STATE_CUSTOM,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    EVENT_TTS_REQUEST, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
)
from Modules.control_service import ControlService
from Modules.alarm_service import AlarmService


class _FakeLED:
    """记录 LED 调用"""
    def __init__(self): self.calls = []
    def on(self): self.calls.append(("on",))
    def off(self): self.calls.append(("off",))
    def blink(self, d, i): self.calls.append(("blink", d, i))


class _FakeAudio:
    """记录 Audio 调用"""
    def __init__(self): self.calls = []
    def play_file(self, f): self.calls.append(("play_file", f))
    def play_tts(self, t): self.calls.append(("play_tts", t))
    def stop(self): self.calls.append(("stop",))
    def init(self, cb=None): return True
    def set_speaker_volume(self, v): pass
    def tts_set_speed(self, s): pass
    def tts_set_volume(self, v): pass
    def set_volume(self, v): pass
    def get_volume(self): return 5


def make_ctrl():
    """创建已 init 的 ControlService + AlarmService + Fake 设备 + 事件监听器"""
    bus = EventBus()
    led = _FakeLED()
    audio = _FakeAudio()

    alarm = AlarmService(bus, led=led, audio=audio)
    ctrl = ControlService(bus)

    alarm.init()
    ctrl.init()

    events = {
        "light": [],
        "volume": [],
        "alarm": [],
        "alarm_triggered": [],
        "alarm_canceled": [],
        "power": [],
        "state": [],
        "tts": [],
    }
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: events["light"].append(p))
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: events["volume"].append(p))
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: events["alarm"].append(p))
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: events["alarm_triggered"].append(p))
    bus.subscribe(EVENT_ALARM_CANCELED, lambda p: events["alarm_canceled"].append(p))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: events["power"].append(p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: events["state"].append(p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: events["tts"].append(p))

    return ctrl, bus, events


def clear_events(events):
    for k in events:
        events[k].clear()


def send_ble_cmd(bus, cmd, ctrl=None):
    """发送 BLE 控制指令并返回 JSON，自动重置指令防抖"""
    import json
    if ctrl:
        ctrl.ctx["last_cmd_tick"] = 0
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    return raw


# ==================== 测试用例 ====================

def test_init():
    """初始化成功"""
    ctrl, bus, events = make_ctrl()
    assert ctrl.ctx["is_init"] == True
    assert ctrl.name == "control_service"
    print("  OK init")


def test_light_on():
    """light_on → EVENT_LIGHT_CONTROL{on} + 状态更新 + TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "light_on", ctrl)
    assert len(events["light"]) == 1
    assert events["light"][0]["cmd"] == "on"
    assert ctrl._control_state["light_mode"] == "manual"
    assert ctrl._control_state["light_brightness"] == 50
    # TTS 验证
    assert len(events["tts"]) == 1
    assert events["tts"][0]["text"] == "灯光已开启"
    print("  OK light_on + TTS")


def test_light_off():
    """light_off → EVENT_LIGHT_CONTROL{off} + TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "light_off", ctrl)
    assert events["light"][0]["cmd"] == "off"
    assert ctrl._control_state["light_brightness"] == 0
    assert events["tts"][0]["text"] == "灯光已关闭"
    print("  OK light_off + TTS")


def test_brightness_up():
    """brightness_up → 亮度增加 5 + TTS"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["light_brightness"] = 30
    send_ble_cmd(bus, "brightness_up", ctrl)
    assert events["light"][0]["cmd"] == "brightness_up"
    assert ctrl._control_state["light_brightness"] == 35
    assert events["tts"][0]["text"] == "亮度增加"
    print("  OK brightness_up + TTS")


def test_brightness_up_max():
    """brightness_up 不超过 LIGHT_BRIGHTNESS_MAX"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["light_brightness"] = 45
    send_ble_cmd(bus, "brightness_up", ctrl)
    assert ctrl._control_state["light_brightness"] == 50  # LIGHT_BRIGHTNESS_MAX=50
    print("  OK brightness_up_max")


def test_brightness_down():
    """brightness_down → 亮度减少 5 + TTS"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["light_brightness"] = 30
    send_ble_cmd(bus, "brightness_down", ctrl)
    assert events["light"][0]["cmd"] == "brightness_down"
    assert ctrl._control_state["light_brightness"] == 25
    assert events["tts"][0]["text"] == "亮度降低"
    print("  OK brightness_down + TTS")


def test_brightness_down_min():
    """brightness_down 不低于 0"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["light_brightness"] = 5
    send_ble_cmd(bus, "brightness_down", ctrl)
    assert ctrl._control_state["light_brightness"] == 0
    print("  OK brightness_down_min")


def test_light_auto():
    """light_auto → EVENT_LIGHT_CONTROL{auto} + TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "light_auto", ctrl)
    assert events["light"][0]["cmd"] == "auto"
    assert ctrl._control_state["light_mode"] == "auto"
    assert events["tts"][0]["text"] == "灯光自动模式"
    print("  OK light_auto + TTS")


def test_volume_up():
    """volume_up → EVENT_VOLUME_CONTROL{up} + TTS"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["volume"] = 3
    send_ble_cmd(bus, "volume_up", ctrl)
    assert events["volume"][0]["cmd"] == "up"
    assert ctrl._control_state["volume"] == 4
    assert events["tts"][0]["text"] == "音量增加"
    print("  OK volume_up + TTS")


def test_volume_up_max():
    """volume_up 不超过 5"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["volume"] = 5
    send_ble_cmd(bus, "volume_up", ctrl)
    assert ctrl._control_state["volume"] == 5  # volume_max=5, 超出后不变
    print("  OK volume_up_max")


def test_volume_down():
    """volume_down → EVENT_VOLUME_CONTROL{down} + TTS"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["volume"] = 5
    send_ble_cmd(bus, "volume_down", ctrl)
    assert events["volume"][0]["cmd"] == "down"
    assert ctrl._control_state["volume"] == 4
    assert events["tts"][0]["text"] == "音量降低"
    print("  OK volume_down + TTS")


def test_volume_down_min():
    """volume_down 不低于 0"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["volume"] = 0
    send_ble_cmd(bus, "volume_down", ctrl)
    assert ctrl._control_state["volume"] == 0
    print("  OK volume_down_min")


def test_alarm_sos():
    """alarm_sos → EVENT_ALARM_CONTROL{sos} + TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert events["alarm"][0]["cmd"] == "sos"
    assert events["tts"][0]["text"] == "报警已触发"
    print("  OK alarm_sos + TTS")


def test_alarm_cancel():
    """alarm_cancel → EVENT_ALARM_CONTROL{cancel} + TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "alarm_cancel", ctrl)
    assert events["alarm"][0]["cmd"] == "cancel"
    assert events["tts"][0]["text"] == "报警已取消"
    print("  OK alarm_cancel + TTS")


def test_alarm_stealth():
    """alarm_stealth → EVENT_ALARM_CONTROL{stealth}（静默，无 TTS）"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "alarm_stealth", ctrl)
    assert events["alarm"][0]["cmd"] == "stealth"
    assert len(events["tts"]) == 0  # 静默报警不播报
    print("  OK alarm_stealth (no TTS)")


def test_alarm_snapshot():
    """报警前状态快照 + 报警取消后恢复"""
    ctrl, bus, events = make_ctrl()
    # 设置初始状态
    ctrl._control_state["light_brightness"] = 30
    ctrl._control_state["volume"] = 3
    # 触发报警
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._alarm_active == True
    assert ctrl._pre_alarm_state is not None
    assert ctrl._pre_alarm_state["light_brightness"] == 30
    assert ctrl._pre_alarm_state["volume"] == 3
    # 取消报警
    send_ble_cmd(bus, "alarm_cancel", ctrl)
    assert ctrl._alarm_active == False
    assert ctrl._control_state["light_brightness"] == 30  # 恢复
    assert ctrl._control_state["volume"] == 3  # 恢复
    assert ctrl._pre_alarm_state is None  # 快照已清除
    print("  OK alarm_snapshot")


def test_power_save():
    """power_save → EVENT_POWER_STATE_CHANGE(SUSPENDED) + TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "power_save", ctrl)
    assert len(events["power"]) == 1
    assert events["power"][0]["power_state"] == POWER_STATE_SUSPENDED
    assert ctrl._control_state["power_mode"] == "suspended"
    assert events["tts"][0]["text"] == "省电模式"
    print("  OK power_save + TTS")


def test_power_normal():
    """power_normal → EVENT_POWER_STATE_CHANGE(ACTIVE) + TTS"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["power_mode"] = "suspended"
    send_ble_cmd(bus, "power_normal", ctrl)
    assert events["power"][0]["power_state"] == POWER_STATE_ACTIVE
    assert ctrl._control_state["power_mode"] == "active"
    assert events["tts"][0]["text"] == "正常模式"
    print("  OK power_normal + TTS")


def test_power_emergency():
    """power_emergency → EVENT_POWER_STATE_CHANGE(EMERGENCY) + TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "power_emergency", ctrl)
    assert events["tts"][0]["text"] == "紧急省电模式"
    print("  OK power_emergency + TTS")


def test_tts_debounce():
    """TTS 防抖：快速连续指令只播报 1 次"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "brightness_up", ctrl)
    # 重置防抖（300ms 指令防抖）
    ctrl.ctx["last_cmd_tick"] = 0
    send_ble_cmd(bus, "brightness_up", ctrl)
    # 只有 1 条 TTS（1 秒防抖）
    assert len(events["tts"]) == 1, "TTS 防抖应只播报 1 次，实际 %d 次" % len(events["tts"])
    print("  OK TTS debounce")


def test_query_status():
    """query_status → 动态 TTS 播报"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["light_mode"] = "auto"
    ctrl._control_state["volume"] = 3
    ctrl._control_state["power_mode"] = "active"
    send_ble_cmd(bus, "query_status", ctrl)
    # query 走 _tts() 不走 _maybe_tts()，无 1 秒防抖
    assert len(events["tts"]) == 1
    text = events["tts"][0]["text"]
    assert "自动模式" in text
    assert "音量3" in text
    assert "正常模式" in text
    print("  OK query_status: %s" % text)


def test_debounce():
    """防抖：300ms 内重复指令被忽略"""
    import json
    ctrl, bus, events = make_ctrl()
    # 第一条指令正常执行
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "light_on"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    assert len(events["light"]) == 1
    # 立即再发一次，不重置 last_cmd_tick，应被防抖忽略
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    assert len(events["light"]) == 1, "debounce should block second call"
    print("  OK debounce")


def test_unknown_cmd():
    """未知指令被忽略"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "unknown_cmd", ctrl)
    assert len(events["light"]) == 0
    assert len(events["volume"]) == 0
    assert len(events["alarm"]) == 0
    assert len(events["tts"]) == 0
    print("  OK unknown_cmd")


def test_invalid_json():
    """非法 JSON 不崩溃"""
    ctrl, bus, events = make_ctrl()
    bus.publish(EVENT_RIDE_CONTROL, {"raw": "not json"})
    bus.pump()
    assert ctrl.ctx["err_count"] > 0
    print("  OK invalid_json")


def test_non_ctrl_action():
    """非 ctrl action 被忽略"""
    ctrl, bus, events = make_ctrl()
    import json
    raw = json.dumps({"a": "nav", "d": {"dir": "right"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    assert len(events["light"]) == 0
    print("  OK non_ctrl_action")


def test_state_push():
    """控制执行后触发 EVENT_CONTROL_STATE_CHANGED（合并为 1 条）"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "light_on", ctrl)
    assert len(events["state"]) == 1, "合并后只有 1 条消息（原 3 条）"
    assert events["state"][0]["t"] == 7
    assert events["state"][0]["m"] == 1  # manual
    assert events["state"][0]["b"] == 50
    assert events["state"][0]["v"] == 5  # volume
    assert events["state"][0]["p"] == 0  # power active
    print("  OK state_push (merged)")


def test_get_data():
    """get_data 返回当前状态"""
    ctrl, bus, events = make_ctrl()
    d = ctrl.get_data()
    assert "last_cmd" in d
    assert "control_state" in d
    assert "timestamp" in d
    print("  OK get_data")


def test_get_status():
    """get_status 返回模块状态"""
    ctrl, bus, events = make_ctrl()
    s = ctrl.get_status()
    assert "is_init" in s
    assert s["is_init"] == True
    assert "control_state" in s
    print("  OK get_status")


# ==================== 新增测试：报警行为 ====================

def test_alarm_sos_triggers_event():
    """alarm_sos → EVENT_ALARM_CONTROL{cmd:"sos"}"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert len(events["alarm"]) == 1
    assert events["alarm"][0]["cmd"] == "sos"
    print("  OK alarm_sos_triggers_event")


def test_alarm_stealth_triggers_event():
    """alarm_stealth → EVENT_ALARM_CONTROL{cmd:"stealth"}"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "alarm_stealth", ctrl)
    assert len(events["alarm"]) == 1
    assert events["alarm"][0]["cmd"] == "stealth"
    print("  OK alarm_stealth_triggers_event")


def test_alarm_sos_no_auto_cancel():
    """SOS 报警不会自动取消（模拟 31s 后仍为 active）"""
    import time as _time
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._alarm_active == True
    # 手动推进 last_tts_tick 防止 TTS 防抖干扰
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0
    # 模拟 31s 后 — ControlService 不管理超时，只记录状态
    # 超时由 AlarmService 管理，这里验证 ControlService 的 _alarm_active 不会自行清除
    send_ble_cmd(bus, "light_on", ctrl)  # 发一个无关指令
    assert ctrl._alarm_active == True, "SOS 报警不应被自动清除"
    print("  OK alarm_sos_no_auto_cancel")


def test_alarm_collision_auto_cancel_via_event():
    """碰撞报警：收到 EVENT_ALARM_CANCELED 后恢复状态"""
    ctrl, bus, events = make_ctrl()
    # 设置初始状态
    ctrl._control_state["light_brightness"] = 20
    # 触发报警
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._alarm_active == True
    assert ctrl._pre_alarm_state["light_brightness"] == 20
    # 模拟 AlarmService 发出 EVENT_ALARM_CANCELED（30s 超时后）
    from core.config import EVENT_ALARM_CANCELED
    bus.publish(EVENT_ALARM_CANCELED, {"duration": 30000})
    bus.pump()
    assert ctrl._alarm_active == False
    assert ctrl._control_state["light_brightness"] == 20, "报警取消后恢复亮度"
    assert ctrl._pre_alarm_state is None
    print("  OK alarm_collision_auto_cancel_via_event")


# ==================== 新增测试：TTS 优先级 ====================

def test_tts_blocked_during_alarm():
    """报警中控制指令不触发 TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._alarm_active == True
    ctrl.ctx["last_cmd_tick"] = 0  # 重置防抖
    ctrl.ctx["last_tts_tick"] = 0
    events["tts"].clear()
    send_ble_cmd(bus, "light_on", ctrl)
    # _maybe_tts 应被 _alarm_active 阻塞
    assert len(events["tts"]) == 0, "报警中不应有 TTS"
    print("  OK tts_blocked_during_alarm")


def test_query_tts_blocked_during_alarm():
    """报警中查询指令不触发 TTS"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._alarm_active == True
    ctrl.ctx["last_cmd_tick"] = 0
    events["tts"].clear()
    send_ble_cmd(bus, "query_status", ctrl)
    # _tts() 应被 _alarm_active 阻塞
    assert len(events["tts"]) == 0, "报警中查询不应有 TTS"
    print("  OK query_tts_blocked_during_alarm")


def test_tts_after_alarm_cancel():
    """报警取消后 TTS 恢复正常"""
    import json
    ctrl, bus, events = make_ctrl()
    # alarm_sos 直接 publish
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "alarm_sos"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    assert ctrl._alarm_active == True
    # alarm_cancel 直接 publish
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0
    events["tts"].clear()
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "alarm_cancel"}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()
    assert ctrl._alarm_active == False
    # alarm_cancel 本身会触发 TTS（"报警已取消"）
    assert len(events["tts"]) == 1
    assert events["tts"][0]["text"] == "报警已取消"
    # 验证 TTS 恢复正常
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0
    events["tts"].clear()
    send_ble_cmd(bus, "light_on", ctrl)
    assert len(events["tts"]) == 1, "报警取消后 TTS 应恢复"
    print("  OK tts_after_alarm_cancel")


# ==================== 新增测试：电源模式 ====================

def test_power_save_turns_off_light():
    """power_save → EVENT_LIGHT_CONTROL{off}"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "light_on", ctrl)  # 先开灯
    events["light"].clear()
    ctrl.ctx["last_cmd_tick"] = 0
    send_ble_cmd(bus, "power_save", ctrl)
    # power_save 在 _update_control_state 中发送 EVENT_LIGHT_CONTROL{off}
    off_events = [e for e in events["light"] if e.get("cmd") == "off"]
    assert len(off_events) == 1, "power_save 应发送关灯事件"
    print("  OK power_save_turns_off_light")


def test_power_save_brightness_zero():
    """power_save 后亮度归零"""
    ctrl, bus, events = make_ctrl()
    ctrl._control_state["light_brightness"] = 40
    ctrl.ctx["last_cmd_tick"] = 0
    send_ble_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["light_brightness"] == 0
    assert ctrl._control_state["light_mode"] == "manual"
    print("  OK power_save_brightness_zero")


def test_power_emergency_turns_off_light():
    """power_emergency → EVENT_LIGHT_CONTROL{off} + 亮度归零"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "light_on", ctrl)
    events["light"].clear()
    ctrl.ctx["last_cmd_tick"] = 0
    send_ble_cmd(bus, "power_emergency", ctrl)
    off_events = [e for e in events["light"] if e.get("cmd") == "off"]
    assert len(off_events) == 1, "power_emergency 应发送关灯事件"
    assert ctrl._control_state["light_brightness"] == 0
    assert ctrl._control_state["power_mode"] == "emergency"
    print("  OK power_emergency_turns_off_light")


# ==================== 新增测试：语音入口 ====================

def test_voice_cmd_triggers_control():
    """EVENT_VOICE_CMD 同样走 _execute_cmd"""
    ctrl, bus, events = make_ctrl()
    from core.config import EVENT_VOICE_CMD
    bus.publish(EVENT_VOICE_CMD, {"cmd": "light_on", "id": 1})
    bus.pump()
    assert len(events["light"]) == 1
    assert events["light"][0]["cmd"] == "on"
    assert ctrl._control_state["light_mode"] == "manual"
    assert ctrl._control_state["light_brightness"] == 50
    print("  OK voice_cmd_triggers_control")


def test_voice_cmd_tts():
    """语音指令同样触发 TTS"""
    ctrl, bus, events = make_ctrl()
    from core.config import EVENT_VOICE_CMD
    bus.publish(EVENT_VOICE_CMD, {"cmd": "light_on", "id": 1})
    bus.pump()
    assert len(events["tts"]) == 1
    assert events["tts"][0]["text"] == "灯光已开启"
    print("  OK voice_cmd_tts")


# ==================== 新增测试：报警快照 × 电源模式 ====================

def test_alarm_snapshot_power_mode():
    """power_save → alarm_sos → alarm_cancel → 恢复 suspended"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._alarm_active == True
    assert ctrl._pre_alarm_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    send_ble_cmd(bus, "alarm_cancel", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended", "报警取消后恢复电源模式"
    print("  OK alarm_snapshot_power_mode")


def test_alarm_in_suspended():
    """SUSPENDED 模式下仍可触发报警"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    send_ble_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._alarm_active == True
    assert len(events["alarm"]) >= 1
    print("  OK alarm_in_suspended")


def test_manual_op_overrides_power():
    """SUSPENDED 下手动操作 → power_mode 变为 custom"""
    ctrl, bus, events = make_ctrl()
    send_ble_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    send_ble_cmd(bus, "light_on", ctrl)
    assert ctrl._control_state["power_mode"] == "custom"
    assert events["power"][-1]["power_state"] == POWER_STATE_CUSTOM
    print("  OK manual_op_overrides_power")


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print(" ControlService 单元测试 (v2 纯事件驱动)")
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
        test_alarm_sos,
        test_alarm_cancel,
        test_alarm_stealth,
        test_alarm_snapshot,
        test_power_save,
        test_power_normal,
        test_power_emergency,
        test_tts_debounce,
        test_query_status,
        test_debounce,
        test_unknown_cmd,
        test_invalid_json,
        test_non_ctrl_action,
        test_state_push,
        test_get_data,
        test_get_status,
        # 新增：报警行为
        test_alarm_sos_triggers_event,
        test_alarm_stealth_triggers_event,
        test_alarm_sos_no_auto_cancel,
        test_alarm_collision_auto_cancel_via_event,
        # 新增：TTS 优先级
        test_tts_blocked_during_alarm,
        test_query_tts_blocked_during_alarm,
        test_tts_after_alarm_cancel,
        # 新增：电源模式
        test_power_save_turns_off_light,
        test_power_save_brightness_zero,
        test_power_emergency_turns_off_light,
        # 新增：语音入口
        test_voice_cmd_triggers_control,
        test_voice_cmd_tts,
        # 新增：报警快照 × 电源模式
        test_alarm_snapshot_power_mode,
        test_alarm_in_suspended,
        test_manual_op_overrides_power,
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
