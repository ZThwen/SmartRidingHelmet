"""
brief Step 5 语音控制集成测试：VoiceDriver + ControlService 联合事件链
note 使用 FakeUART 模拟 ASRPRO 语音模块输出，验证完整事件链：
     FakeUART.feed(0x01) → VoiceDriver._handle_hex() → EVENT_VOICE_CMD
         → ControlService._on_voice_cmd() → _execute_cmd()
             → EVENT_LIGHT_CONTROL / EVENT_VOLUME_CONTROL / EVENT_ALARM_CONTROL / etc.
     上传到板子运行：python test_voice_control_integration.py
     无硬件依赖，仅需 EventBus + VoiceDriver + ControlService
"""
import sys
import time

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_VOICE_CMD, VOICE_CMD_MAP,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST, EVENT_CONTROL_STATE_CHANGED,
    POWER_STATE_SUSPENDED,
)
from Drivers.interface.Voice import VoiceDriver
from Modules.control_service import ControlService


# ==================== Fake UART ====================

class FakeUART:
    """
    brief 模拟 UART，从内存缓冲区提供语音 hex 字节
    note 替代真实 UART2，模拟 ASRPRO 逐字节发送 hex 指令
    """

    def __init__(self):
        self._buf = bytearray()

    def any(self):
        return len(self._buf) > 0

    def read(self, n):
        data = self._buf[:n]
        self._buf = self._buf[n:]
        return bytes(data)

    def feed(self, hex_val):
        """向缓冲区注入一个 hex 字节"""
        self._buf.append(hex_val)


# ==================== 事件日志 ====================

event_log = []


def _record(tag, payload):
    """记录事件到全局日志，tag 为事件类型缩写"""
    event_log.append({"tag": tag, "payload": dict(payload)})


def _reset_log():
    global event_log
    event_log = []


def _find(tag):
    """按 tag 查找事件"""
    return [e for e in event_log if e["tag"] == tag]


# ==================== 系统构建 ====================

def make_system():
    """
    brief 构建 VoiceDriver + ControlService 联合测试系统
    note 按事件链顺序初始化：EventBus → VoiceDriver → ControlService
          通过 FakeUART 注入 hex 字节，事件日志验证流转
          voice.init() 会创建真实 UART，因此跳过 init()，直接注入 FakeUART
    return (bus, voice, ctrl, fake_uart) 四元组
    """
    bus = EventBus()
    voice = VoiceDriver(bus, uart_id=2, baudrate=115200)
    fake_uart = FakeUART()
    # 注入 FakeUART 替代真实硬件 — 必须在 init() 之后设置
    # 因为 init() 会创建 self.uart = UART(...) 覆盖 FakeUART
    # 所以跳过 init()，手动标记已初始化
    voice.uart = fake_uart
    voice.ctx["is_init"] = True

    ctrl = ControlService(bus)
    ctrl.init()

    _reset_log()

    # 订阅所有输出事件用于验证
    bus.subscribe(EVENT_VOICE_CMD, lambda p: _record("VOICE", p))
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: _record("LIGHT", p))
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: _record("VOL", p))
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: _record("ALARM", p))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: _record("POWER", p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: _record("TTS", p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: _record("STATE", p))

    return bus, voice, ctrl, fake_uart


def voice_feed(fake_uart, voice, ctrl, hex_val):
    """
    brief 将 hex 字节注入 FakeUART 并触发完整事件链
    param fake_uart: FakeUART 实例
    param voice: VoiceDriver 实例
    param ctrl: ControlService 实例（用于重置防抖）
    param hex_val: ASRPRO hex 指令字节
    note 重置 ControlService 防抖以确保连续发送不被丢弃
          单次 bus.pump() 会 drain 整条级联事件链
    """
    ctrl.ctx["last_cmd_tick"] = 0   # 重置指令防抖
    ctrl.ctx["last_tts_tick"] = 0   # 重置 TTS 防抖
    fake_uart.feed(hex_val)
    voice.tick()
    # pump 事件总线 — drain 所有级联事件（VOICE_CMD → LIGHT_CTRL / VOL / etc.）
    voice.event_bus.pump()


# ==================== 测试用例 ====================

def test_01_voice_light_on():
    """
    brief 测试 1: 0x01 → EVENT_VOICE_CMD("light_on") → EVENT_LIGHT_CONTROL("on")
    note 完整链路：FakeUART → VoiceDriver → ControlService → EVENT_LIGHT_CONTROL
    """
    print("\n--- test_01_voice_light_on ---")
    bus, voice, ctrl, uart = make_system()

    voice_feed(uart, voice, ctrl, 0x01)

    # 验证 EVENT_VOICE_CMD
    voice_events = _find("VOICE")
    assert len(voice_events) >= 1, "应发布 EVENT_VOICE_CMD"
    assert voice_events[0]["payload"]["cmd"] == "light_on", \
        "VOICE_CMD cmd 应为 light_on, 实际: %s" % voice_events[0]["payload"]

    # 验证 EVENT_LIGHT_CONTROL 级联
    light_events = _find("LIGHT")
    assert len(light_events) >= 1, "应级联发布 EVENT_LIGHT_CONTROL"
    assert light_events[0]["payload"]["cmd"] == "on", \
        "LIGHT_CONTROL cmd 应为 on, 实际: %s" % light_events[0]["payload"]

    # 验证 ControlService 记录了指令
    assert ctrl._data["last_cmd"] == "light_on", \
        "ControlService 最后指令应为 light_on, 实际: %s" % ctrl._data["last_cmd"]
    assert ctrl._data["last_cmd_source"] == "voice", \
        "指令来源应为 voice, 实际: %s" % ctrl._data["last_cmd_source"]

    print("  OK voice_light_on: 0x01 → 'light_on' → LIGHT_CONTROL{cmd:'on'}")
    print("    events: %s" % [e["tag"] for e in event_log])


def test_02_voice_volume_up():
    """
    brief 测试 2: 0x06 → EVENT_VOICE_CMD("volume_up") → EVENT_VOLUME_CONTROL("up")
    note 验证音量控制事件链
    """
    print("\n--- test_02_voice_volume_up ---")
    bus, voice, ctrl, uart = make_system()

    voice_feed(uart, voice, ctrl, 0x06)

    # 验证 EVENT_VOICE_CMD
    voice_events = _find("VOICE")
    assert len(voice_events) >= 1, "应发布 EVENT_VOICE_CMD"
    assert voice_events[0]["payload"]["cmd"] == "volume_up", \
        "VOICE_CMD cmd 应为 volume_up, 实际: %s" % voice_events[0]["payload"]

    # 验证 EVENT_VOLUME_CONTROL 级联
    vol_events = _find("VOL")
    assert len(vol_events) >= 1, "应级联发布 EVENT_VOLUME_CONTROL"
    assert vol_events[0]["payload"]["cmd"] == "up", \
        "VOLUME_CONTROL cmd 应为 up, 实际: %s" % vol_events[0]["payload"]

    print("  OK voice_volume_up: 0x06 → 'volume_up' → VOLUME_CONTROL{cmd:'up'}")
    print("    events: %s" % [e["tag"] for e in event_log])


def test_03_voice_alarm_sos():
    """
    brief 测试 3: 0x09 → EVENT_VOICE_CMD("alarm_sos") → EVENT_ALARM_CONTROL("sos")
    note 验证 SOS 报警事件链
    """
    print("\n--- test_03_voice_alarm_sos ---")
    bus, voice, ctrl, uart = make_system()

    voice_feed(uart, voice, ctrl, 0x09)

    # 验证 EVENT_VOICE_CMD
    voice_events = _find("VOICE")
    assert len(voice_events) >= 1, "应发布 EVENT_VOICE_CMD"
    assert voice_events[0]["payload"]["cmd"] == "alarm_sos", \
        "VOICE_CMD cmd 应为 alarm_sos, 实际: %s" % voice_events[0]["payload"]

    # 验证 EVENT_ALARM_CONTROL 级联
    alarm_events = _find("ALARM")
    assert len(alarm_events) >= 1, "应级联发布 EVENT_ALARM_CONTROL"
    assert alarm_events[0]["payload"]["cmd"] == "sos", \
        "ALARM_CONTROL cmd 应为 sos, 实际: %s" % alarm_events[0]["payload"]

    print("  OK voice_alarm_sos: 0x09 → 'alarm_sos' → ALARM_CONTROL{cmd:'sos'}")
    print("    events: %s" % [e["tag"] for e in event_log])


def test_04_voice_power_save():
    """
    brief 测试 4: 0x0B → EVENT_VOICE_CMD("power_save") → EVENT_POWER_STATE_CHANGE(SUSPENDED)
    note 验证省电模式事件链
    """
    print("\n--- test_04_voice_power_save ---")
    bus, voice, ctrl, uart = make_system()

    voice_feed(uart, voice, ctrl, 0x0B)

    # 验证 EVENT_VOICE_CMD
    voice_events = _find("VOICE")
    assert len(voice_events) >= 1, "应发布 EVENT_VOICE_CMD"
    assert voice_events[0]["payload"]["cmd"] == "power_save", \
        "VOICE_CMD cmd 应为 power_save, 实际: %s" % voice_events[0]["payload"]

    # 验证 EVENT_POWER_STATE_CHANGE 级联
    power_events = _find("POWER")
    assert len(power_events) >= 1, "应级联发布 EVENT_POWER_STATE_CHANGE"
    assert power_events[0]["payload"]["power_state"] == POWER_STATE_SUSPENDED, \
        "power_state 应为 SUSPENDED, 实际: %s" % power_events[0]["payload"]

    print("  OK voice_power_save: 0x0B → 'power_save' → POWER_STATE_CHANGE{SUSPENDED}")
    print("    events: %s" % [e["tag"] for e in event_log])


def test_05_voice_query_temp():
    """
    brief 测试 5: 0x10 → EVENT_VOICE_CMD("query_temp") → EVENT_TTS_REQUEST
    note 查询温度指令触发 TTS（无传感器时播报"温度信息暂不可用"）
    """
    print("\n--- test_05_voice_query_temp ---")
    bus, voice, ctrl, uart = make_system()

    voice_feed(uart, voice, ctrl, 0x10)

    # 验证 EVENT_VOICE_CMD
    voice_events = _find("VOICE")
    assert len(voice_events) >= 1, "应发布 EVENT_VOICE_CMD"
    assert voice_events[0]["payload"]["cmd"] == "query_temp", \
        "VOICE_CMD cmd 应为 query_temp, 实际: %s" % voice_events[0]["payload"]

    # 验证 EVENT_TTS_REQUEST 级联（query_temp 无传感器 → TTS"温度信息暂不可用"）
    tts_events = _find("TTS")
    assert len(tts_events) >= 1, "应级联发布 EVENT_TTS_REQUEST"
    assert "温度" in tts_events[0]["payload"].get("text", ""), \
        "TTS 文本应包含'温度', 实际: %s" % tts_events[0]["payload"]

    print("  OK voice_query_temp: 0x10 → 'query_temp' → TTS_REQUEST")
    print("    TTS text: %s" % tts_events[0]["payload"].get("text", ""))
    print("    events: %s" % [e["tag"] for e in event_log])


def test_06_voice_brightness_up_down():
    """
    brief 测试 6: 0x03/0x04 → brightness_up / brightness_down → EVENT_LIGHT_CONTROL
    note 验证亮度调节两条指令的事件链均正确
    """
    print("\n--- test_06_voice_brightness_up_down ---")

    # brightness_up (0x03)
    bus, voice, ctrl, uart = make_system()
    voice_feed(uart, voice, ctrl, 0x03)

    light_events = _find("LIGHT")
    assert len(light_events) >= 1, "brightness_up 应发布 EVENT_LIGHT_CONTROL"
    assert light_events[0]["payload"]["cmd"] == "brightness_up", \
        "LIGHT_CONTROL cmd 应为 brightness_up, 实际: %s" % light_events[0]["payload"]
    print("  OK brightness_up: 0x03 → LIGHT_CONTROL{cmd:'brightness_up'}")

    # brightness_down (0x04) — 重建系统避免防抖残留
    bus, voice, ctrl, uart = make_system()
    voice_feed(uart, voice, ctrl, 0x04)

    light_events = _find("LIGHT")
    assert len(light_events) >= 1, "brightness_down 应发布 EVENT_LIGHT_CONTROL"
    assert light_events[0]["payload"]["cmd"] == "brightness_down", \
        "LIGHT_CONTROL cmd 应为 brightness_down, 实际: %s" % light_events[0]["payload"]
    print("  OK brightness_down: 0x04 → LIGHT_CONTROL{cmd:'brightness_down'}")


def test_07_voice_all_control_cmds():
    """
    brief 测试 7: 遍历 VOICE_CMD_MAP 全部 20 个 hex 指令
    note 验证每条 hex → VOICE_CMD 映射正确、ControlService 不崩溃
          各指令发布的事件类型通过 _cmd_handlers 验证
    """
    print("\n--- test_07_voice_all_control_cmds (%d cmds) ---" % len(VOICE_CMD_MAP))

    # 已知各 cmd 对应的级联事件类型
    CMD_EVENT_MAP = {
        "wake":              ["TTS"],              # lambda: None + TTS"小洛包在"
        "light_on":          ["LIGHT", "TTS"],     # LIGHT(on) + TTS"灯光已开启"
        "light_off":         ["LIGHT", "TTS"],     # LIGHT(off) + TTS"灯光已关闭"
        "light_auto":        ["LIGHT", "TTS"],     # LIGHT(auto) + TTS"灯光自动模式"
        "brightness_up":     ["LIGHT", "TTS"],     # LIGHT(brightness_up)
        "brightness_down":   ["LIGHT", "TTS"],     # LIGHT(brightness_down)
        "volume_up":         ["VOL", "TTS"],       # VOL(up)
        "volume_down":       ["VOL", "TTS"],       # VOL(down)
        "alarm_cancel":      ["ALARM", "TTS"],     # ALARM(cancel) + TTS"报警已取消"
        "alarm_sos":         ["ALARM", "TTS"],     # ALARM(sos) + TTS"报警已触发"
        "alarm_stealth":     ["ALARM"],            # ALARM(stealth) 无 TTS
        "power_save":        ["POWER", "LIGHT", "TTS"],  # POWER + LIGHT(off) + TTS
        "power_normal":      ["POWER", "TTS"],     # POWER + TTS
        "power_emergency":   ["POWER", "LIGHT", "TTS"],  # POWER + LIGHT(off) + TTS
        "query_status":      ["TTS"],              # _query_status → TTS
        "query_speed":       ["TTS"],              # _query_speed → TTS
        "query_temp":        ["TTS"],              # _query_temp → TTS
        "query_humid":       ["TTS"],              # _query_humid → TTS
        "query_location":    ["TTS"],              # _query_location → TTS
        "query_battery":     ["TTS"],              # _tts("电量信息暂不可用")
    }

    passed = 0
    for hex_val, expected_cmd in sorted(VOICE_CMD_MAP.items()):
        bus, voice, ctrl, uart = make_system()
        voice_feed(uart, voice, ctrl, hex_val)

        # 验证 VOICE_CMD
        voice_events = _find("VOICE")
        assert len(voice_events) >= 1, \
            "0x%02X: 应发布 VOICE_CMD, 日志: %s" % (hex_val, event_log)
        actual_cmd = voice_events[0]["payload"]["cmd"]
        assert actual_cmd == expected_cmd, \
            "0x%02X: VOICE_CMD cmd 应为 '%s', 实际: '%s'" % (hex_val, expected_cmd, actual_cmd)

        # 验证 ControlService 记录
        assert ctrl._data["last_cmd"] == expected_cmd, \
            "0x%02X: last_cmd 应为 '%s', 实际: '%s'" % (hex_val, expected_cmd, ctrl._data["last_cmd"])

        # 验证级联事件类型
        expected_events = CMD_EVENT_MAP.get(expected_cmd, [])
        for evt_tag in expected_events:
            found = _find(evt_tag)
            assert len(found) >= 1, \
                "0x%02X -> '%s': 应级联发布 %s 事件, 日志 tags: %s" % (
                    hex_val, expected_cmd, evt_tag, [e["tag"] for e in event_log])

        # 验证 STATE_CHANGED（所有指令都会 _push_state）
        state_events = _find("STATE")
        assert len(state_events) >= 1, \
            "0x%02X -> '%s': 应发布 STATE_CHANGED" % (hex_val, expected_cmd)

        passed += 1

    print("  OK all %d/%d commands mapped and routed correctly" % (passed, len(VOICE_CMD_MAP)))


def test_08_voice_unknown_hex():
    """
    brief 测试 8: 0xFF 未知 hex → 不崩溃、不发布事件
    note VoiceDriver 对未映射的 hex 只打印日志，不发布事件
    """
    print("\n--- test_08_voice_unknown_hex ---")
    bus, voice, ctrl, uart = make_system()

    voice_feed(uart, voice, ctrl, 0xFF)

    # 未知 hex 不应发布 VOICE_CMD
    voice_events = _find("VOICE")
    assert len(voice_events) == 0, \
        "0xFF 未知 hex 不应发布 VOICE_CMD, 实际发布: %s" % voice_events

    # 未知 hex 不应触发任何级联事件
    assert len(event_log) == 0, \
        "0xFF 不应触发任何级联事件, 实际: %s" % event_log

    # VoiceDriver 不应崩溃
    assert voice.ctx["is_init"] == True, "VoiceDriver 应保持初始化状态"
    assert voice.ctx["err_count"] == 0, "VoiceDriver 错误计数应为 0"

    print("  OK unknown_hex: 0xFF → no events, no crash")
    print("    events: %s" % [e["tag"] for e in event_log])


# ==================== 主入口 ====================

def run_all():
    """运行所有 Voice + Control 集成测试"""
    print("=" * 60)
    print("Step 5 语音控制集成测试")
    print("VoiceDriver + ControlService + FakeUART")
    print("事件链: 0x01 → VOICE_CMD → ControlService → LIGHT_CONTROL")
    print("=" * 60)

    tests = [
        test_01_voice_light_on,
        test_02_voice_volume_up,
        test_03_voice_alarm_sos,
        test_04_voice_power_save,
        test_05_voice_query_temp,
        test_06_voice_brightness_up_down,
        test_07_voice_all_control_cmds,
        test_08_voice_unknown_hex,
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
            import sys as _sys
            try:
                _sys.print_exception(e)
            except Exception:
                pass

    print("\n" + "=" * 60)
    print("结果: %d 通过, %d 失败 / 共 %d" % (passed, failed, len(tests)))
    print("=" * 60)

    if failed > 0:
        print("!!! 存在失败测试，请检查 !!!")
    else:
        print("ALL PASS")


if __name__ == "__main__":
    run_all()
