"""
brief PowerService 集成测试
note 验证电池数据在模块间的完整流转
     包含 VoiceDriver、BLEService 的完整链路测试

测试覆盖：
1. BatteryDriver → PowerService → BLEService bat 字段
2. VoiceDriver → ControlService query_battery TTS（完整链路）
3. BLEService FFF3 → ControlService query_battery TTS（完整链路）
4. 低电量自动省电 → PowerService 发布事件
"""
import sys
import time
import json

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_BLE_CONNECTED,
    EVENT_BATTERY_READY, EVENT_BATTERY_LOW,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    EVENT_RIDE_CONTROL, EVENT_VOICE_CMD,
    VOICE_CMD_MAP,
    TTS_BATTERY_LOW, PRIORITY_CTRL,
)
from Modules.power_service import PowerService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Drivers.interface.Voice import VoiceDriver


class FakeBLEDriver:
    def __init__(self):
        self.notify_calls = []
        self.ctx = {"is_connected": True, "is_init": True}
        self._data_handler = None
        self.cfg = {
            "char_nav": 0xFFF2,
            "char_ctrl": 0xFFF3,
            "char_ack": 0xFFF4,
        }

    def set_data_handler(self, handler):
        self._data_handler = handler

    def notify_data(self, json_str):
        self.notify_calls.append(json.loads(json_str))


class FakeUART:
    """模拟 UART，可预设接收缓冲区"""
    def __init__(self):
        self._buf = bytearray()

    def any(self):
        return len(self._buf)

    def read(self, n):
        data = self._buf[:n]
        self._buf = self._buf[n:]
        return bytes(data)

    def put(self, byte_val):
        self._buf.append(byte_val)


def pump(services, eb, count=5, delay_ms=50):
    for _ in range(count):
        for svc in services:
            svc.tick()
        eb.pump()
        time.sleep_ms(delay_ms)


def test_battery_to_ble():
    """测试 1: 电池电量 → BLE merged push 包含 bat 字段"""
    print("\n=== 测试 1: 电池电量→BLE bat 字段 ===")
    eb = EventBus()
    fake_ble = FakeBLEDriver()
    power_svc = PowerService(event_bus=eb)
    ble_svc = BLEService(event_bus=eb, ble_driver=fake_ble)

    power_svc.init()
    ble_svc.init()
    ble_svc.cfg["upload_interval_ms"] = 100  # 测试用，缩短推送间隔

    # BLE 连接
    eb.publish(EVENT_BLE_CONNECTED, {})
    pump([power_svc, ble_svc], eb)

    # 发布电池数据
    eb.publish(EVENT_BATTERY_READY, {"level": 4, "battery_mv": 3800, "valid": True})
    pump([power_svc, ble_svc], eb, count=10)

    # 检查 BLE 推送中是否包含 bat 字段
    found_bat = False
    for call in fake_ble.notify_calls:
        if call.get("t") == 0 and call.get("d", {}).get("bat") == 4:
            found_bat = True
            break

    assert found_bat, "BLE merged push 中未找到 bat=4"
    print("[PASS] test_battery_to_ble")


def test_battery_voice_query():
    """测试 2: ControlService query_battery → TTS 播报"""
    print("\n=== 测试 2: 语音查询电量→TTS ===")
    eb = EventBus()
    ctrl = ControlService(event_bus=eb)
    power_svc = PowerService(event_bus=eb)
    ctrl.init()
    power_svc.init()

    # 先推送电量数据到 ControlService
    eb.publish(EVENT_BATTERY_READY, {"level": 3, "battery_mv": 3600, "valid": True})
    pump([ctrl, power_svc], eb)

    # 捕获 TTS 请求
    tts_received = []
    eb.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))

    # 模拟语音查询
    ctrl._query_battery()
    eb.pump()

    assert len(tts_received) == 1
    assert "当前电量3档" in tts_received[0]["text"]
    assert tts_received[0]["priority"] == PRIORITY_CTRL
    print("[PASS] test_battery_voice_query")


def test_low_battery_tts():
    """测试 3: 低电量 → PowerService 发布 TTS 请求"""
    print("\n=== 测试 3: 低电量→TTS 通知 ===")
    eb = EventBus()
    power_svc = PowerService(event_bus=eb)
    power_svc.init()

    tts_received = []
    eb.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))

    eb.publish(EVENT_BATTERY_READY, {"level": 2, "battery_mv": 3300, "valid": True})
    eb.pump()

    assert len(tts_received) == 1
    assert tts_received[0]["text"] == TTS_BATTERY_LOW
    print("[PASS] test_low_battery_tts")


def test_ble_cmd_query_battery():
    """测试 4: BLE FFF3 指令查询电量（完整链路：BLEService → ControlService → TTS）"""
    print("\n=== 测试 4: BLE 指令查询电量→TTS ===")
    eb = EventBus()
    fake_ble = FakeBLEDriver()
    ble_svc = BLEService(event_bus=eb, ble_driver=fake_ble)
    ctrl = ControlService(event_bus=eb)
    power_svc = PowerService(event_bus=eb)
    ble_svc.init()
    ctrl.init()
    power_svc.init()

    # BLE 连接
    eb.publish(EVENT_BLE_CONNECTED, {})
    pump([ble_svc, ctrl, power_svc], eb)

    # 先推送电量数据
    eb.publish(EVENT_BATTERY_READY, {"level": 4, "battery_mv": 3800, "valid": True})
    pump([ble_svc, ctrl, power_svc], eb)

    # 捕获 TTS 请求
    tts_received = []
    eb.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))

    # 模拟 BLE FFF3 写入：通过 BLEService._on_ble_data 写入 cmd_buffer
    # 完整链路：BLE 数据 → _on_ble_data → cmd_buffer → tick() → _parse_and_route → EVENT_RIDE_CONTROL → ControlService
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "query_battery"}})
    ble_svc._on_ble_data({"uuid": fake_ble.cfg["char_ctrl"], "value": raw})
    pump([ble_svc, ctrl, power_svc], eb, count=5)

    assert len(tts_received) == 1, "期望 1 次 TTS，实际 %d 次" % len(tts_received)
    assert "当前电量4档" in tts_received[0]["text"]
    assert tts_received[0]["priority"] == PRIORITY_CTRL
    print("[PASS] test_ble_cmd_query_battery")


def test_voice_cmd_query_battery():
    """测试 5: 语音指令查询电量（完整链路：VoiceDriver → ControlService → TTS）"""
    print("\n=== 测试 5: 语音指令查询电量→TTS ===")
    eb = EventBus()
    fake_uart = FakeUART()
    voice = VoiceDriver(event_bus=eb)
    voice.uart = fake_uart  # 注入 fake UART，跳过 init() 的硬件初始化
    voice.ctx["is_init"] = True

    ctrl = ControlService(event_bus=eb)
    power_svc = PowerService(event_bus=eb)
    ctrl.init()
    power_svc.init()

    # 先推送电量数据
    eb.publish(EVENT_BATTERY_READY, {"level": 3, "battery_mv": 3600, "valid": True})
    pump([voice, ctrl, power_svc], eb)

    # 捕获 TTS 请求
    tts_received = []
    eb.subscribe(EVENT_TTS_REQUEST, lambda p: tts_received.append(p))

    # 模拟 ASRPRO 发送 0x13 (query_battery)
    # 完整链路：UART hex → VoiceDriver.tick() → _handle_hex → VOICE_CMD_MAP → EVENT_VOICE_CMD → ControlService
    fake_uart.put(0x13)
    pump([voice, ctrl, power_svc], eb, count=5)

    assert len(tts_received) == 1, "期望 1 次 TTS，实际 %d 次" % len(tts_received)
    assert "当前电量3档" in tts_received[0]["text"]
    assert tts_received[0]["priority"] == PRIORITY_CTRL
    print("[PASS] test_voice_cmd_query_battery")


if __name__ == "__main__":
    tests = [
        test_battery_to_ble,
        test_battery_voice_query,
        test_low_battery_tts,
        test_ble_cmd_query_battery,
        test_voice_cmd_query_battery,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print("[FAIL] %s: %s" % (t.__name__, e))
            failed += 1
    print("\n=== 结果: %d passed, %d failed ===" % (passed, failed))
