"""
brief 电源模式 × 报警系统 跨模块集成测试
note 对标真实集成，验证 ControlService → AlarmService/LightService/AudioDriver
      的完整事件流转、状态快照、TTS 优先级、电源模式行为

      模块依赖图：
        ControlService (中心枢纽)
          ├── EVENT_LIGHT_CONTROL     → LightService → FakePWM
          ├── EVENT_VOLUME_CONTROL    → AudioDriver
          ├── EVENT_ALARM_CONTROL     → AlarmService → FakeLED + FakeAudioHW
          ├── EVENT_POWER_STATE_CHANGE → 多模块响应
          ├── EVENT_TTS_REQUEST       → AudioDriver
          └── EVENT_CONTROL_STATE_CHANGED → (监听器捕获)

      init 顺序（对齐 main.py）：
        1. Actuators: LED → Audio → PWM
        2. Services: AlarmService → LightService → ControlService → NavigationService

      上传到板子运行: python Tests/test_power_alarm_integration.py
"""
import sys
import time
sys.path.append("..")

# CPython 兼容：MicroPython 有 time.ticks_ms()/ticks_diff()，CPython 没有
if not hasattr(time, "ticks_ms"):
    time.ticks_ms = lambda: int(time.time() * 1000)
if not hasattr(time, "ticks_diff"):
    time.ticks_diff = lambda a, b: a - b

# ==================== Mock quectel.Audio ====================
# AudioDriver 导入时需要 quectel.Audio，在 PC/无硬件环境下需要 mock
import sys as _sys
class _FakeAudioHW:
    """模拟 EC200U quectel.Audio 硬件接口"""
    PLAY_END = 1
    PLAY_STOP = 2
    TTS_END = 3
    TTS_STOP = 4

    def __init__(self):
        self._cb = None
        self._vol = 5
        self._tts_speed = 85
        self._tts_vol = 50

    def init(self, cb=None):
        self._cb = cb
        return True

    def play_local(self, path, loop=False):
        pass

    def tts_play(self, text):
        pass

    def play_stop(self):
        pass

    def tts_stop(self):
        pass

    def set_speaker_volume(self, v):
        self._vol = v

    def get_speaker_volume(self):
        return self._vol

    def tts_set_speed(self, s):
        self._tts_speed = s

    def tts_set_volume(self, v):
        self._tts_vol = v

# 注入 mock 模块，让 `from quectel import Audio` 能成功
class _QuectelModule:
    Audio = _FakeAudioHW
_sys.modules["quectel"] = _QuectelModule()

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    EVENT_NAV_CMD,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
    POWER_STATE_CUSTOM,
    AUDIO_SOS_FILE,
)
from Modules.control_service import ControlService
from Modules.alarm_service import AlarmService
from Modules.light_service import LightService
from Drivers.actuator.Audio import AudioDriver
from Modules.navigation_service import NavigationService


# ==================== Fake 设备 ====================

class FakeLED:
    """记录 LED 所有调用"""
    def __init__(self):
        self.calls = []
    def on(self):
        self.calls.append(("on",))
    def off(self):
        self.calls.append(("off",))
    def blink(self, dur, interval):
        self.calls.append(("blink", dur, interval))


class FakePWM:
    """记录 PWM 占空比变化"""
    def __init__(self):
        self.duty = 0
        self._data = {"duty_cycle": 0}
        self.ctx = {"is_init": True, "power_state": POWER_STATE_ACTIVE}
    def set_brightness(self, d):
        self.duty = d
        self._data["duty_cycle"] = d
    def get_data(self):
        return dict(self._data)


# ==================== 系统组装 ====================

def make_system():
    """
    创建完整测试系统（对标真实集成）
    返回: (bus, ctrl, alarm, light, audio, nav, led, pwm, events)
    """
    bus = EventBus()
    led = FakeLED()
    pwm = FakePWM()

    # 1. Actuators
    audio = AudioDriver(bus)
    audio._calls = []  # 追踪 play_file/play_tts 调用（测试用）

    # 2. Services
    alarm = AlarmService(bus, led=led, audio=audio)
    light = LightService(bus, pwm_led=pwm)
    ctrl = ControlService(event_bus=bus)
    nav = NavigationService(bus, audio_driver=audio)

    # 3. Init（对齐 main.py 顺序）
    audio.init()
    alarm.init()
    light.init()
    ctrl.init()
    nav.init()

    # 4. 事件监听器
    events = {
        "light": [],       # EVENT_LIGHT_CONTROL
        "volume": [],      # EVENT_VOLUME_CONTROL
        "alarm": [],       # EVENT_ALARM_CONTROL
        "alarm_triggered": [],  # EVENT_ALARM_TRIGGERED
        "alarm_canceled": [],   # EVENT_ALARM_CANCELED
        "power": [],       # EVENT_POWER_STATE_CHANGE
        "state": [],       # EVENT_CONTROL_STATE_CHANGED (t=7)
        "tts": [],         # EVENT_TTS_REQUEST
    }
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: events["light"].append(dict(p)))
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: events["volume"].append(dict(p)))
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: events["alarm"].append(dict(p)))
    bus.subscribe(EVENT_ALARM_TRIGGERED, lambda p: events["alarm_triggered"].append(dict(p)))
    bus.subscribe(EVENT_ALARM_CANCELED, lambda p: events["alarm_canceled"].append(dict(p)))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: events["power"].append(dict(p)))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: events["state"].append(dict(p)))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: events["tts"].append(dict(p)))

    return bus, ctrl, alarm, light, audio, nav, led, pwm, events


def send_cmd(bus, cmd, ctrl=None):
    """发送 BLE 控制指令，自动重置指令防抖和TTS防抖"""
    import json
    if ctrl:
        ctrl.ctx["last_cmd_tick"] = 0
        ctrl.ctx["last_tts_tick"] = 0
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()


def clear_events(events):
    """清空所有事件监听器"""
    for k in events:
        events[k].clear()


# ==================== P0: 核心链路 ====================

def test_light_on_chain():
    """BLE light_on → ControlService → LightService → FakePWM duty=50"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "light_on", ctrl)
    assert pwm.duty == 50, "PWM duty 应为 50, 实际 %d" % pwm.duty
    assert light.get_mode() == "manual"
    assert ctrl._control_state["light_mode"] == "manual"
    assert ctrl._control_state["light_brightness"] == 50
    print("  OK test_light_on_chain")


def test_alarm_sos_chain():
    """BLE alarm_sos → AlarmService → LED.blink + Audio.play_file(SOS) + EVENT_ALARM_TRIGGERED"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "alarm_sos", ctrl)
    # AlarmService 响应
    assert alarm.ctx["alarm_active"] == True
    assert alarm.ctx["alarm_type"] == "sos"
    # LED 调用
    assert any(c[0] == "blink" for c in led.calls), "LED 应被调用 blink"
    # AudioDriver alarm_playing 标志
    assert audio.ctx["alarm_playing"] == True, "AudioDriver alarm_playing 应为 True"
    # EVENT_ALARM_TRIGGERED 发出
    assert len(events["alarm_triggered"]) == 1
    assert events["alarm_triggered"][0]["alarm_type"] == "sos"
    # ControlService 快照保存
    assert ctrl._alarm_active == True
    assert ctrl._pre_alarm_state is not None
    print("  OK test_alarm_sos_chain")


def test_alarm_stealth_chain():
    """BLE alarm_stealth → 无 LED/Audio 调用 + EVENT_ALARM_TRIGGERED 发出"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    led.calls.clear()
    send_cmd(bus, "alarm_stealth", ctrl)
    # AlarmService 响应
    assert alarm.ctx["alarm_active"] == True
    assert alarm.ctx["alarm_type"] == "stealth"
    # LED 不应被调用
    assert len(led.calls) == 0, "静默报警不应调用 LED"
    # EVENT_ALARM_TRIGGERED 发出
    assert len(events["alarm_triggered"]) == 1
    assert events["alarm_triggered"][0]["alarm_type"] == "stealth"
    # ControlService 无 TTS（stealth 不在 CMD_TTS_MAP 中）
    assert len(events["tts"]) == 0, "静默报警不应有 TTS"
    print("  OK test_alarm_stealth_chain")


def test_alarm_cancel_chain():
    """BLE alarm_cancel → LED.off + Audio.stop + EVENT_ALARM_CANCELED"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "alarm_sos", ctrl)
    assert alarm.ctx["alarm_active"] == True
    led.calls.clear()
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_cancel", ctrl)
    # AlarmService 取消
    assert alarm.ctx["alarm_active"] == False
    # LED off
    assert any(c[0] == "off" for c in led.calls), "LED 应被调用 off"
    # EVENT_ALARM_CANCELED 发出
    assert len(events["alarm_canceled"]) == 1
    print("  OK test_alarm_cancel_chain")


def test_state_push_merged():
    """控制操作后 EVENT_CONTROL_STATE_CHANGED 合并为 1 条 t=7"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "light_on", ctrl)
    # 应只有 1 条合并消息
    state_events = [e for e in events["state"] if e.get("t") == 7]
    assert len(state_events) == 1, "合并后只有 1 条 t=7, 实际 %d" % len(state_events)
    e = state_events[0]
    assert e["m"] == 1, "m=1 (manual)"
    assert e["b"] == 50, "b=50 (brightness)"
    assert e["v"] == 5, "v=5 (volume)"
    assert e["p"] == 0, "p=0 (active)"
    print("  OK test_state_push_merged")


def test_volume_chain():
    """BLE volume_up → AudioDriver.set_volume"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "volume_up", ctrl)
    assert ctrl._control_state["volume"] == 5  # 已经是最大值 5
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "volume_down", ctrl)
    assert ctrl._control_state["volume"] == 4
    # AudioDriver 内部 set_volume 被调用（通过 _data["volume"] 验证）
    assert audio._data["volume"] == 4
    print("  OK test_volume_chain")


# ==================== P1: 报警快照 + 恢复 ====================

def test_alarm_snapshot_restore():
    """light_on → alarm_sos → alarm_cancel → 灯光亮度恢复"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "light_on", ctrl)  # brightness=50
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "brightness_down", ctrl)  # brightness=45
    assert ctrl._control_state["light_brightness"] == 45
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_sos", ctrl)  # 触发报警，保存快照
    assert ctrl._pre_alarm_state["light_brightness"] == 45
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_cancel", ctrl)  # 取消报警，恢复快照
    assert ctrl._control_state["light_brightness"] == 45, "亮度应恢复到 45"
    assert ctrl._control_state["light_mode"] == "manual"
    print("  OK test_alarm_snapshot_restore")


def test_alarm_snapshot_volume():
    """volume_up → alarm_sos → alarm_cancel → 音量恢复"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    ctrl._control_state["volume"] = 3
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._pre_alarm_state["volume"] == 3
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_cancel", ctrl)
    assert ctrl._control_state["volume"] == 3, "音量应恢复到 3"
    print("  OK test_alarm_snapshot_volume")


def test_alarm_snapshot_push_state():
    """alarm_cancel 后 _push_state 推送恢复后的状态"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "light_on", ctrl)  # brightness=50
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_sos", ctrl)
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "alarm_cancel", ctrl)
    # alarm_cancel 触发 _push_state → 1 条 t=7 消息
    state_events = [e for e in events["state"] if e.get("t") == 7]
    assert len(state_events) >= 1, "取消后应推送恢复状态"
    last_state = state_events[-1]
    assert last_state["b"] == 50, "恢复后亮度应为 50"
    assert last_state["m"] == 1, "恢复后模式应为 manual"
    print("  OK test_alarm_snapshot_push_state")


def test_alarm_snapshot_power():
    """power_save → alarm_sos → alarm_cancel → 恢复 suspended"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_sos", ctrl)
    assert ctrl._pre_alarm_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_cancel", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended", "电源模式应恢复到 suspended"
    print("  OK test_alarm_snapshot_power")


# ==================== P2: TTS 优先级 ====================

def test_tts_blocked_during_alarm():
    """alarm_sos → light_on → AudioDriver 拒绝 TTS"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "alarm_sos", ctrl)
    assert audio.ctx["alarm_playing"] == True, "AudioDriver alarm_playing 应为 True"
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0
    clear_events(events)
    send_cmd(bus, "light_on", ctrl)
    # ControlService._maybe_tts 被 _alarm_active 阻塞
    assert len(events["tts"]) == 0, "报警中不应有 TTS_REQUEST"
    print("  OK test_tts_blocked_during_alarm")


def test_alarm_audio_cannot_be_interrupted():
    """报警中 → EVENT_TTS_REQUEST → AudioDriver 拒绝"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "alarm_sos", ctrl)
    assert audio.ctx["alarm_playing"] == True
    clear_events(events)
    # 在 play_tts 上安装间谍（验证未被调用）
    audio._tts_called = False
    _orig_play_tts = audio.play_tts
    def _spy(text):
        audio._tts_called = True
        return _orig_play_tts(text)
    audio.play_tts = _spy
    # 直接发布 TTS_REQUEST（模拟导航 TTS）
    bus.publish(EVENT_TTS_REQUEST, {"text": "前方200米右转"})
    bus.pump()
    assert audio._tts_called == False, "报警中 AudioDriver 不应播放 TTS"
    print("  OK test_alarm_audio_cannot_be_interrupted")


def test_tts_after_alarm_cancel():
    """alarm_sos → alarm_cancel → light_on → TTS 恢复"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "alarm_sos", ctrl)
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_cancel", ctrl)
    assert audio.ctx["alarm_playing"] == False, "取消后 alarm_playing 应为 False"
    assert ctrl._alarm_active == False
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0
    clear_events(events)
    send_cmd(bus, "light_on", ctrl)
    assert len(events["tts"]) == 1, "取消后 TTS 应恢复"
    assert events["tts"][0]["text"] == "灯光已开启"
    print("  OK test_tts_after_alarm_cancel")


def test_stealth_tts_blocked():
    """alarm_stealth → alarm 中 → light_on → 无 TTS（stealth 在 CMD_TTS_MAP 中被排除）"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "alarm_stealth", ctrl)
    assert ctrl._alarm_active == True
    assert audio.ctx["alarm_playing"] == True
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0
    clear_events(events)
    send_cmd(bus, "light_on", ctrl)
    assert len(events["tts"]) == 0, "静默报警中不应有 TTS"
    print("  OK test_stealth_tts_blocked")


# ==================== P3: 电源模式 ====================

def test_power_save_turns_off_light():
    """power_save → FakePWM duty=0 + EVENT_LIGHT_CONTROL{off}"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "light_on", ctrl)
    assert pwm.duty == 50
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "power_save", ctrl)
    # ControlService 发送 EVENT_LIGHT_CONTROL{off}
    off_events = [e for e in events["light"] if e.get("cmd") == "off"]
    assert len(off_events) >= 1, "power_save 应发送关灯事件"
    # LightService 收到 off → set_brightness(0) → FakePWM duty=0
    assert pwm.duty == 0, "PWM duty 应为 0, 实际 %d" % pwm.duty
    print("  OK test_power_save_turns_off_light")


def test_power_save_default_state():
    """power_save → light_mode=manual, brightness=0, power_mode=suspended"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_save", ctrl)
    cs = ctrl._control_state
    assert cs["light_mode"] == "manual"
    assert cs["light_brightness"] == 0
    assert cs["power_mode"] == "suspended"
    print("  OK test_power_save_default_state")


def test_power_emergency():
    """power_emergency → power_mode=emergency, 灯关"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "light_on", ctrl)
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "power_emergency", ctrl)
    cs = ctrl._control_state
    assert cs["power_mode"] == "emergency"
    assert cs["light_brightness"] == 0
    assert cs["light_mode"] == "manual"
    print("  OK test_power_emergency")


def test_power_normal_restores():
    """power_save → power_normal → power_mode=active"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "power_normal", ctrl)
    assert ctrl._control_state["power_mode"] == "active"
    print("  OK test_power_normal_restores")


def test_manual_op_overrides_power():
    """power_save → light_on → power_mode 变为 custom"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "light_on", ctrl)
    assert ctrl._control_state["power_mode"] == "custom"
    # 发出 POWER_STATE_CUSTOM 事件
    power_events = [e for e in events["power"] if e.get("power_state") == POWER_STATE_CUSTOM]
    assert len(power_events) >= 1, "应发出 POWER_STATE_CUSTOM 事件"
    print("  OK test_manual_op_overrides_power")


# ==================== P4: 电源模式 × 报警交叉 ====================

def test_alarm_in_suspended():
    """SUSPENDED 模式下 alarm_sos 仍正常触发"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_save", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "alarm_sos", ctrl)
    # 报警不受电源限制
    assert alarm.ctx["alarm_active"] == True
    assert alarm.ctx["alarm_type"] == "sos"
    assert any(c[0] == "blink" for c in led.calls), "LED 应闪烁"
    assert len(events["alarm_triggered"]) == 1
    assert ctrl._alarm_active == True
    print("  OK test_alarm_in_suspended")


def test_alarm_in_emergency():
    """EMERGENCY 模式下 alarm_sos 仍正常触发"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_emergency", ctrl)
    assert ctrl._control_state["power_mode"] == "emergency"
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "alarm_sos", ctrl)
    assert alarm.ctx["alarm_active"] == True
    assert any(c[0] == "blink" for c in led.calls)
    assert len(events["alarm_triggered"]) == 1
    print("  OK test_alarm_in_emergency")


def test_alarm_cancel_restores_power():
    """power_save → alarm_sos → alarm_cancel → 恢复 suspended"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_save", ctrl)
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_sos", ctrl)
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "alarm_cancel", ctrl)
    assert ctrl._control_state["power_mode"] == "suspended", "应恢复到 suspended"
    assert ctrl._control_state["light_brightness"] == 0, "亮度应为 0（suspended 默认关灯）"
    print("  OK test_alarm_cancel_restores_power")


def test_alarm_in_suspended_light_on():
    """power_save → alarm_sos → light_on(报警中可开灯) → alarm_cancel → 恢复 suspended+关灯"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_save", ctrl)  # suspended, brightness=0
    ctrl.ctx["last_cmd_tick"] = 0
    send_cmd(bus, "alarm_sos", ctrl)   # 触发报警
    assert ctrl._pre_alarm_state["light_brightness"] == 0
    assert ctrl._pre_alarm_state["power_mode"] == "suspended"
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "light_on", ctrl)    # 报警中开灯
    assert ctrl._control_state["light_brightness"] == 50
    # 注意：light_on 会触发 power_mode=custom（手动操作覆盖省电）
    ctrl.ctx["last_cmd_tick"] = 0
    clear_events(events)
    send_cmd(bus, "alarm_cancel", ctrl)  # 取消报警
    # 恢复到报警前状态：suspended, brightness=0
    assert ctrl._control_state["power_mode"] == "suspended", "应恢复到 suspended"
    assert ctrl._control_state["light_brightness"] == 0, "应恢复到 0"
    print("  OK test_alarm_in_suspended_light_on")


# ==================== P5: 语音入口 ====================

def test_voice_cmd_light_on():
    """EVENT_VOICE_CMD → ControlService → LightService → FakePWM"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    from core.config import EVENT_VOICE_CMD
    bus.publish(EVENT_VOICE_CMD, {"cmd": "light_on", "id": 1})
    bus.pump()
    assert pwm.duty == 50
    assert ctrl._control_state["light_mode"] == "manual"
    assert ctrl._control_state["light_brightness"] == 50
    print("  OK test_voice_cmd_light_on")


def test_voice_cmd_alarm_sos():
    """EVENT_VOICE_CMD alarm_sos → AlarmService 触发"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    from core.config import EVENT_VOICE_CMD
    bus.publish(EVENT_VOICE_CMD, {"cmd": "alarm_sos", "id": 2})
    bus.pump()
    assert alarm.ctx["alarm_active"] == True
    assert alarm.ctx["alarm_type"] == "sos"
    assert any(c[0] == "blink" for c in led.calls)
    print("  OK test_voice_cmd_alarm_sos")


# ==================== P6: 导航 × 电源 × 报警 ====================

def test_nav_emergency_paused():
    """power_emergency → NAV_CMD → 导航被忽略"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_emergency", ctrl)
    assert nav.ctx["power_state"] == POWER_STATE_EMERGENCY
    # 发送导航指令
    import json
    nav_cmd = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 200, "road": "中山路"}})
    bus.publish(EVENT_NAV_CMD, {"raw": nav_cmd})
    bus.pump()
    # 导航应被暂停，不更新状态
    assert nav.ctx["is_navigating"] == False, "EMERGENCY 下导航应暂停"
    assert nav._data["current_dir"] == "", "EMERGENCY 下不应处理导航"
    print("  OK test_nav_emergency_paused")


def test_nav_stealth_no_tts():
    """alarm_stealth → NAV_CMD → TTS 不播放"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "alarm_stealth", ctrl)
    assert nav.ctx["alarm_active"] == True
    assert nav.ctx["alarm_type"] == "stealth"
    clear_events(events)
    # 发送导航指令
    import json
    nav_cmd = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 200, "road": "中山路"}})
    bus.publish(EVENT_NAV_CMD, {"raw": nav_cmd})
    bus.pump()
    # 导航数据应更新（dir/dist/road），但 TTS 不播放
    assert nav._data["current_dir"] == "right"
    assert nav._data["current_dist"] == 200
    assert nav._data["last_tts"] == "", "静默报警中不应播放导航 TTS"
    print("  OK test_nav_stealth_no_tts")


def test_nav_suspended_no_lcd():
    """power_save → NAV_CMD → LCD 不更新（无 lcd_driver）"""
    bus, ctrl, alarm, light, audio, nav, led, pwm, events = make_system()
    send_cmd(bus, "power_save", ctrl)
    assert nav.ctx["power_state"] == POWER_STATE_SUSPENDED
    import json
    nav_cmd = json.dumps({"a": "nav", "d": {"dir": "left", "dist": 100, "road": ""}})
    bus.publish(EVENT_NAV_CMD, {"raw": nav_cmd})
    bus.pump()
    # 导航数据应更新
    assert nav._data["current_dir"] == "left"
    # LCD 不更新（lcd_driver=None，不报错即为通过）
    # TTS 应正常（SUSPENDED 下 TTS 不阻塞）
    print("  OK test_nav_suspended_no_lcd")


# ==================== 入口 ====================

def main():
    print("=" * 60)
    print(" 电源模式 × 报警系统 跨模块集成测试")
    print("=" * 60)

    tests = [
        # P0: 核心链路
        ("P0 核心链路", [
            test_light_on_chain,
            test_alarm_sos_chain,
            test_alarm_stealth_chain,
            test_alarm_cancel_chain,
            test_state_push_merged,
            test_volume_chain,
        ]),
        # P1: 报警快照 + 恢复
        ("P1 报警快照", [
            test_alarm_snapshot_restore,
            test_alarm_snapshot_volume,
            test_alarm_snapshot_push_state,
            test_alarm_snapshot_power,
        ]),
        # P2: TTS 优先级
        ("P2 TTS 优先级", [
            test_tts_blocked_during_alarm,
            test_alarm_audio_cannot_be_interrupted,
            test_tts_after_alarm_cancel,
            test_stealth_tts_blocked,
        ]),
        # P3: 电源模式
        ("P3 电源模式", [
            test_power_save_turns_off_light,
            test_power_save_default_state,
            test_power_emergency,
            test_power_normal_restores,
            test_manual_op_overrides_power,
        ]),
        # P4: 电源 × 报警交叉
        ("P4 电源×报警", [
            test_alarm_in_suspended,
            test_alarm_in_emergency,
            test_alarm_cancel_restores_power,
            test_alarm_in_suspended_light_on,
        ]),
        # P5: 语音入口
        ("P5 语音入口", [
            test_voice_cmd_light_on,
            test_voice_cmd_alarm_sos,
        ]),
        # P6: 导航 × 电源 × 报警
        ("P6 导航×电源×报警", [
            test_nav_emergency_paused,
            test_nav_stealth_no_tts,
            test_nav_suspended_no_lcd,
        ]),
    ]

    passed = 0
    failed = 0
    for group_name, group_tests in tests:
        print("")
        print("  [%s]" % group_name)
        print("  " + "-" * 40)
        for t in group_tests:
            try:
                t()
                passed += 1
            except Exception as e:
                print("  FAIL %s: %s" % (t.__name__, e))
                failed += 1

    print("")
    print("=" * 60)
    print(" 结果: %d 通过, %d 失败 (共 %d)" % (passed, failed, passed + failed))
    print("=" * 60)


if __name__ == "__main__":
    main()
