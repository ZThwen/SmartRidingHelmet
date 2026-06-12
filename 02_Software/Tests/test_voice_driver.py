"""
brief VoiceDriver 单元测试
note 使用 Fake UART 模拟语音模块输出
     上传到板子运行 python test_voice_driver.py
"""
import sys
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_VOICE_CMD, VOICE_CMD_MAP


class FakeUART:
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


def make_voice():
    bus = EventBus()
    from Drivers.interface.Voice import VoiceDriver
    voice = VoiceDriver(bus, uart_id=2, baudrate=9600)
    fake_uart = FakeUART()
    voice.uart = fake_uart
    voice.init()
    return voice, bus, fake_uart


def test_init():
    voice, bus, uart = make_voice()
    assert voice.ctx["is_init"] == True
    assert voice.name == "voice"
    print("  OK init")


def test_light_on():
    voice, bus, uart = make_voice()
    received = []
    bus.subscribe(EVENT_VOICE_CMD, lambda p: received.append(p))
    uart.feed(0x01)
    voice.tick()
    assert len(received) == 1
    assert received[0]["cmd"] == "light_on"
    print("  OK light_on (0x01)")


def test_alarm_sos():
    voice, bus, uart = make_voice()
    received = []
    bus.subscribe(EVENT_VOICE_CMD, lambda p: received.append(p))
    uart.feed(0x09)
    voice.tick()
    assert received[0]["cmd"] == "alarm_sos"
    print("  OK alarm_sos (0x09)")


def test_query_status():
    voice, bus, uart = make_voice()
    received = []
    bus.subscribe(EVENT_VOICE_CMD, lambda p: received.append(p))
    uart.feed(0x0E)
    voice.tick()
    assert received[0]["cmd"] == "query_status"
    print("  OK query_status (0x0E)")


def test_query_speed():
    voice, bus, uart = make_voice()
    received = []
    bus.subscribe(EVENT_VOICE_CMD, lambda p: received.append(p))
    uart.feed(0x0F)
    voice.tick()
    assert received[0]["cmd"] == "query_speed"
    print("  OK query_speed (0x0F)")


def test_query_temp():
    voice, bus, uart = make_voice()
    received = []
    bus.subscribe(EVENT_VOICE_CMD, lambda p: received.append(p))
    uart.feed(0x10)
    voice.tick()
    assert received[0]["cmd"] == "query_temp"
    print("  OK query_temp (0x10)")


def test_all_mapped():
    """所有映射的 hex 值都能正确转换"""
    voice, bus, uart = make_voice()
    received = []
    bus.subscribe(EVENT_VOICE_CMD, lambda p: received.append(p))
    for hex_val, expected_cmd in VOICE_CMD_MAP.items():
        uart.feed(hex_val)
        voice.tick()
        assert received[-1]["cmd"] == expected_cmd, "0x%02X -> %s != %s" % (
            hex_val, received[-1]["cmd"], expected_cmd)
    print("  OK all %d mapped commands" % len(VOICE_CMD_MAP))


def test_unknown_hex():
    """未知 hex 值不崩溃，不发布事件"""
    voice, bus, uart = make_voice()
    received = []
    bus.subscribe(EVENT_VOICE_CMD, lambda p: received.append(p))
    uart.feed(0xFF)
    voice.tick()
    assert len(received) == 0
    print("  OK unknown hex (0xFF)")


def test_no_data():
    """无数据时不崩溃"""
    voice, bus, uart = make_voice()
    voice.tick()
    print("  OK no_data")


def test_get_data():
    """get_data 返回正确字段"""
    voice, bus, uart = make_voice()
    received = []
    bus.subscribe(EVENT_VOICE_CMD, lambda p: received.append(p))
    uart.feed(0x01)
    voice.tick()
    d = voice.get_data()
    assert d["last_cmd"] == "light_on"
    assert d["last_hex"] == 0x01
    assert "timestamp" in d
    print("  OK get_data")


def test_get_status():
    """get_status 返回正确字段"""
    voice, bus, uart = make_voice()
    s = voice.get_status()
    assert s["is_init"] == True
    assert "err_count" in s
    print("  OK get_status")


def main():
    print("=" * 50)
    print(" VoiceDriver 单元测试")
    print("=" * 50)
    tests = [test_init, test_light_on, test_alarm_sos,
             test_query_status, test_query_speed, test_query_temp,
             test_all_mapped, test_unknown_hex, test_no_data,
             test_get_data, test_get_status]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print("  FAIL {}: {}".format(t.__name__, e))
            failed += 1
    print("\n结果: %d 通过, %d 失败" % (passed, failed))


if __name__ == "__main__":
    main()
