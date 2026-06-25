"""
brief 语音扩展集成测试（VoiceDriver + ControlService 联动）
note 不依赖真实硬件，使用 FakeUART + FakeBLEDriver + EventBus 事件监听验证
     验证语音指令映射、语音门控、BLE 连接/断开、灯光闪烁等
执行: 上传到板子运行 python test_voice_ext_integration.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_VOICE_CMD, EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL,
    EVENT_ALARM_CONTROL, EVENT_TTS_REQUEST,
    EVENT_CONTROL_STATE_CHANGED, EVENT_POWER_STATE_CHANGE,
    VOICE_CMD_MAP, CMD_TTS_MAP,
)
from Modules.control_service import ControlService


class FakeUART:
    """模拟 UART，支持 feed 注入字节"""
    def __init__(self):
        self._buf = bytearray()

    def any(self):
        return len(self._buf) > 0

    def read(self, n):
        data = self._buf[:n]
        self._buf = self._buf[n:]
        return bytes(data)

    def feed(self, hex_val):
        self._buf.append(hex_val)


class FakeBLEDriver:
    """模拟 BLEDriver，记录方法调用 + 可控 ctx 状态"""
    def __init__(self):
        self.calls = []
        self.ctx = {"is_init": False, "is_connected": False}

    def deinit(self):
        self.calls.append("deinit")
        self.ctx["is_init"] = False
        self.ctx["is_connected"] = False

    def restart(self):
        self.calls.append("restart")
        self.ctx["is_init"] = True


def make():
    """创建 VoiceDriver + ControlService + Fake 设备 + 事件监听器"""
    bus = EventBus()

    # VoiceDriver
    from Drivers.interface.Voice import VoiceDriver
    voice = VoiceDriver(bus, uart_id=2, baudrate=115200)
    voice.init()
    fake_uart = FakeUART()
    voice.uart = fake_uart

    # ControlService + FakeBLE
    ble = FakeBLEDriver()
    ctrl = ControlService(bus, ble_driver=ble)
    ctrl.init()

    events = {
        "voice_cmd": [],
        "light": [],
        "volume": [],
        "alarm": [],
        "power": [],
        "state": [],
        "tts": [],
    }
    bus.subscribe(EVENT_VOICE_CMD, lambda p: events["voice_cmd"].append(p))
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: events["light"].append(p))
    bus.subscribe(EVENT_VOLUME_CONTROL, lambda p: events["volume"].append(p))
    bus.subscribe(EVENT_ALARM_CONTROL, lambda p: events["alarm"].append(p))
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: events["power"].append(p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: events["state"].append(p))
    bus.subscribe(EVENT_TTS_REQUEST, lambda p: events["tts"].append(p))

    return voice, ctrl, bus, fake_uart, ble, events


# ==================== 测试用例 ====================

def test_voice_0x16_ble_connect():
    """VoiceDriver 0x16 → EVENT_VOICE_CMD{cmd:'ble_connect'}"""
    voice, ctrl, bus, uart, ble, events = make()
    uart.feed(0x16)
    voice.tick()
    bus.pump()
    assert len(events["voice_cmd"]) == 1
    assert events["voice_cmd"][0]["cmd"] == "ble_connect"
    print("  OK 0x16 -> ble_connect")


def test_voice_0x17_ble_disconnect():
    """VoiceDriver 0x17 → EVENT_VOICE_CMD{cmd:'ble_disconnect'}"""
    voice, ctrl, bus, uart, ble, events = make()
    uart.feed(0x17)
    voice.tick()
    bus.pump()
    assert len(events["voice_cmd"]) == 1
    assert events["voice_cmd"][0]["cmd"] == "ble_disconnect"
    print("  OK 0x17 -> ble_disconnect")


def test_voice_0x18_voice_sleep():
    """VoiceDriver 0x18 → EVENT_VOICE_CMD{cmd:'voice_sleep'}"""
    voice, ctrl, bus, uart, ble, events = make()
    uart.feed(0x18)
    voice.tick()
    bus.pump()
    assert len(events["voice_cmd"]) == 1
    assert events["voice_cmd"][0]["cmd"] == "voice_sleep"
    print("  OK 0x18 -> voice_sleep")


def test_voice_0x19_light_blink():
    """VoiceDriver 0x19 → EVENT_VOICE_CMD{cmd:'light_blink'}"""
    voice, ctrl, bus, uart, ble, events = make()
    uart.feed(0x19)
    voice.tick()
    bus.pump()
    assert len(events["voice_cmd"]) == 1
    assert events["voice_cmd"][0]["cmd"] == "light_blink"
    print("  OK 0x19 -> light_blink")


def test_voice_sleep_gate():
    """voice_sleep 后 light_on 被忽略"""
    voice, ctrl, bus, uart, ble, events = make()
    # 先执行 voice_sleep
    uart.feed(0x18)
    voice.tick()
    bus.pump()
    # 再执行 light_on (0x01)
    events["voice_cmd"].clear()
    events["light"].clear()
    uart.feed(0x01)
    voice.tick()
    bus.pump()
    # voice_cmd 已发布，但 light 事件不应被触发（因为被 gate 拦截）
    assert len(events["light"]) == 0
    print("  OK voice_sleep gate blocks light_on")


def test_voice_sleep_wake_resumes():
    """voice_sleep → wake → light_on 恢复正常"""
    voice, ctrl, bus, uart, ble, events = make()
    # voice_sleep
    ctrl.ctx["last_cmd_tick"] = 0
    uart.feed(0x18)
    voice.tick()
    bus.pump()
    time.sleep_ms(400)
    # wake (0x00)
    ctrl.ctx["last_cmd_tick"] = 0
    uart.feed(0x00)
    voice.tick()
    bus.pump()
    time.sleep_ms(400)
    # light_on (0x01)
    ctrl.ctx["last_cmd_tick"] = 0
    events["light"].clear()
    uart.feed(0x01)
    voice.tick()
    bus.pump()
    assert len(events["light"]) >= 1
    print("  OK wake resumes after voice_sleep")


def test_voice_sleep_blocks_all_non_wake():
    """休眠中所有非 wake 指令(0x0F, 0x10, 0x19)被忽略"""
    voice, ctrl, bus, uart, ble, events = make()
    uart.feed(0x18)  # sleep
    voice.tick()
    bus.pump()
    events["light"].clear()
    events["tts"].clear()
    # 非 wake 指令
    uart.feed(0x19)  # light_blink
    voice.tick()
    bus.pump()
    assert len(events["light"]) == 0
    print("  OK all non-wake blocked during sleep")


def test_ble_connect_connected():
    """BLE 已连接 → _ble_connect() → TTS '蓝牙已连接'"""
    voice, ctrl, bus, uart, ble, events = make()
    ble.ctx["is_connected"] = True
    ctrl._ble_connected = True  # 事件缓存
    events["tts"].clear()
    ctrl._execute_cmd("ble_connect", source="voice")
    bus.pump()
    assert len(events["tts"]) >= 1
    assert "已连接" in events["tts"][-1]["text"]
    print("  OK ble_connect -> 已连接 TTS")


def test_ble_connect_restart():
    """BLE 未初始化 → _ble_connect() → ble.restart() + TTS"""
    voice, ctrl, bus, uart, ble, events = make()
    ble.ctx["is_init"] = False
    ctrl._ble_connected = False
    ctrl.ctx["last_cmd_tick"] = 0
    events["tts"].clear()
    ctrl._execute_cmd("ble_connect", source="voice")
    bus.pump()
    assert "restart" in ble.calls, "restart 未调用! ble.calls=%s" % ble.calls
    assert len(events["tts"]) >= 1, "无 TTS!"
    assert "正在连接" in events["tts"][-1]["text"], "TTS 不匹配: %s" % events["tts"][-1]["text"]
    print("  OK ble_connect -> restart + TTS")


def test_ble_disconnect():
    """BLE 已初始化 → _ble_disconnect() → ble.deinit()"""
    voice, ctrl, bus, uart, ble, events = make()
    ble.ctx["is_init"] = True
    ctrl._execute_cmd("ble_disconnect", source="voice")
    assert "deinit" in ble.calls
    print("  OK ble_disconnect -> deinit")


def test_ble_disconnect_not_init():
    """BLE 未初始化 → _ble_disconnect() → 不调用 deinit()"""
    voice, ctrl, bus, uart, ble, events = make()
    ble.ctx["is_init"] = False
    ble.calls.clear()
    ctrl._execute_cmd("ble_disconnect", source="voice")
    assert "deinit" not in ble.calls
    print("  OK ble_disconnect not_init -> no deinit")


def test_light_blink_event():
    """light_blink → EVENT_LIGHT_CONTROL{cmd:'blink'}"""
    voice, ctrl, bus, uart, ble, events = make()
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl._execute_cmd("light_blink", source="voice")
    bus.pump()
    assert len(events["light"]) >= 1
    assert events["light"][-1]["cmd"] == "blink"
    print("  OK light_blink -> EVENT_LIGHT_CONTROL{blink}")


def test_light_blink_tts():
    """light_blink → TTS '灯光闪烁' (from CMD_TTS_MAP)"""
    voice, ctrl, bus, uart, ble, events = make()
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0
    ctrl._execute_cmd("light_blink", source="voice")
    bus.pump()
    assert len(events["tts"]) >= 1
    assert events["tts"][-1]["text"] == "灯光闪烁"
    print("  OK light_blink -> TTS 灯光闪烁")


def test_light_blink_light_mode():
    """light_blink → _control_state['light_mode'] = 'manual'"""
    voice, ctrl, bus, uart, ble, events = make()
    ctrl._control_state["light_mode"] = "auto"
    ctrl._execute_cmd("light_blink", source="voice")
    bus.pump()
    assert ctrl._control_state["light_mode"] == "manual"
    print("  OK light_blink -> light_mode=manual")


def test_all_26_mapped():
    """VOICE_CMD_MAP 共 26 条，全部能正确映射"""
    voice, ctrl, bus, uart, ble, events = make()
    for hex_val, expected_cmd in VOICE_CMD_MAP.items():
        uart.feed(hex_val)
        voice.tick()
        bus.pump()
        if events["voice_cmd"]:
            assert events["voice_cmd"][-1]["cmd"] == expected_cmd, \
                "0x%02X -> %s != %s" % (hex_val, events["voice_cmd"][-1]["cmd"], expected_cmd)
    assert len(VOICE_CMD_MAP) == 26
    print("  OK all %d commands mapped" % len(VOICE_CMD_MAP))


# ==================== 入口 ====================

def main():
    print("=" * 55)
    print(" 语音扩展集成测试")
    print("=" * 55)
    tests = [
        test_voice_0x16_ble_connect, test_voice_0x17_ble_disconnect,
        test_voice_0x18_voice_sleep, test_voice_0x19_light_blink,
        test_voice_sleep_gate, test_voice_sleep_wake_resumes,
        test_voice_sleep_blocks_all_non_wake,
        test_ble_connect_connected, test_ble_connect_restart,
        test_ble_disconnect, test_ble_disconnect_not_init,
        test_light_blink_event, test_light_blink_tts,
        test_light_blink_light_mode, test_all_26_mapped,
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
    print("\n结果: %d 通过, %d 失败 / 共 %d" % (passed, failed, len(tests)))


if __name__ == "__main__":
    main()
