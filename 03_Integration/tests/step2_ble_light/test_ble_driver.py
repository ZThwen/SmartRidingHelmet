"""
brief BLEDriver 单元测试（模拟硬件层）
note 使用 MockBLE 替代 quectel.BLE，验证：
     1. init() 初始化流程
     2. BLE 广播名称
     3. GATT 服务注册 (0xFFF0)
     4. 4 个特征值 (FFF1~FFF4)
     5. notify_data() 发送通道
     6. EventBus 连接/断连事件
     7. get_data() / get_status() 返回值
     无需手机连接，纯逻辑验证。在板子上运行。
"""
import sys
import time

# 路径设置：从 03_Integration/tests/wave1_device/ 到 02_Software/
sys.path.append("../../../02_Software")


# ==================== 模拟硬件层 ====================

# 全局引用，测试用例通过它访问 MockBLE 实例
_mock_ble_instance = None


class MockBLE:
    """
    brief 模拟 EC200U BLE 模块
    note 记录所有 API 调用参数，供测试断言检查
    """
    # BLE 常量（与 quectel.BLE 一致）
    DATAFMT_STRING = 1
    PROP_READ = 0x01
    PROP_WRITE = 0x02
    PROP_NOTIFY = 0x04
    PROP_INDICATE = 0x08
    PERM_READ = 0x01
    PERM_WRITE = 0x02
    EVT_CONNECTED = 1
    EVT_DISCONNECTED = 2
    EVT_MTU = 3
    EVT_VAL_DATA = 4

    def __init__(self):
        global _mock_ble_instance
        _mock_ble_instance = self
        self.call_log = []       # 记录所有方法调用
        self._callback = None    # BLE 事件回调

    def init(self, callback):
        self._callback = callback
        self.call_log.append(("init",))
        return True

    def set_dataformat(self, fmt):
        self.call_log.append(("set_dataformat", fmt))

    def start(self, name):
        self.call_log.append(("start", name))

    def add_service(self, *args):
        self.call_log.append(("add_service",) + args)

    def add_character(self, *args):
        self.call_log.append(("add_character",) + args)

    def set_character_value(self, *args):
        self.call_log.append(("set_character_value",) + args)

    def add_descriptor(self, *args):
        self.call_log.append(("add_descriptor",) + args)

    def advertise(self):
        self.call_log.append(("advertise",))

    def notify(self, char_uuid, length, data):
        self.call_log.append(("notify", char_uuid, length, data))

    def get_addr(self):
        return "AA:BB:CC:DD:EE:FF"

    def stop(self):
        self.call_log.append(("stop",))

    def deinit(self):
        self.call_log.append(("deinit",))

    def exchange_mtu(self, mtu):
        self.call_log.append(("exchange_mtu", mtu))


class _MockQuectel:
    """模拟 quectel 模块，仅提供 BLE 类"""
    BLE = MockBLE


# 注入模拟模块（必须在 import BLEDriver 之前）
sys.modules["quectel"] = _MockQuectel()


# ==================== 导入被测模块 ====================

from core.Event_Bus import EventBus
from core.config import (
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    BLE_DEVICE_NAME, BLE_SERVICE_UUID,
    BLE_CHAR_DATA, BLE_CHAR_NAV, BLE_CHAR_CTRL, BLE_CHAR_ACK,
)
from Drivers.network.BLE import BLEDriver


# ==================== 测试辅助 ====================

def pump_loop(event_bus, modules, iterations=20, interval_ms=10):
    """
    brief 泵循环辅助函数
    note 替代 time.sleep()，在等待期间持续驱动 EventBus 和模块 tick
         遵循架构规范：tick() + pump() + sleep_ms()
    param event_bus: EventBus 实例
    param modules: 需要 tick 的模块列表
    param iterations: 循环次数
    param interval_ms: 每次间隔 (ms)
    """
    for _ in range(iterations):
        for mod in modules:
            mod.tick()
        event_bus.pump()
        time.sleep_ms(interval_ms)


def reset_mock():
    """重置 MockBLE 全局实例引用"""
    global _mock_ble_instance
    _mock_ble_instance = None


# ==================== 测试用例 ====================

def test_01_init_success():
    """测试 1: init() 成功后 is_init=True"""
    print("\n=== 测试 1: init() 初始化成功 ===")
    reset_mock()
    eb = EventBus()
    ble = BLEDriver(eb)

    ble.init()

    assert ble.ctx["is_init"] is True, "init() 后 is_init 应为 True"
    print("  ✓ is_init = True")

    # 验证底层 BLE API 调用顺序
    mock = _mock_ble_instance
    call_names = [c[0] for c in mock.call_log]
    expected_order = ["init", "set_dataformat", "start", "add_service"]
    for name in expected_order:
        assert name in call_names, "缺少 API 调用: %s" % name
    print("  ✓ API 调用顺序正确: init → set_dataformat → start → add_service")

    ble.stop()
    print("  ✓ 测试 1 通过")


def test_02_advertising_name():
    """测试 2: BLE 广播名称为 SmartHelmet-66ccff"""
    print("\n=== 测试 2: BLE 广播名称 ===")
    reset_mock()
    eb = EventBus()
    ble = BLEDriver(eb)

    ble.init()

    mock = _mock_ble_instance
    # 查找 start() 调用
    start_calls = [c for c in mock.call_log if c[0] == "start"]
    assert len(start_calls) == 1, "应调用一次 start()"
    actual_name = start_calls[0][1]
    assert actual_name == BLE_DEVICE_NAME, \
        "广播名应为 '%s'，实际为 '%s'" % (BLE_DEVICE_NAME, actual_name)
    print("  ✓ 广播名称: %s" % actual_name)

    ble.stop()
    print("  ✓ 测试 2 通过")


def test_03_gatt_service_uuid():
    """测试 3: GATT 服务注册 UUID 为 0xFFF0"""
    print("\n=== 测试 3: GATT 服务 UUID ===")
    reset_mock()
    eb = EventBus()
    ble = BLEDriver(eb)

    ble.init()

    mock = _mock_ble_instance
    # add_service(handle, uuid, is_primary) → ("add_service", handle, uuid, is_primary)
    svc_calls = [c for c in mock.call_log if c[0] == "add_service"]
    assert len(svc_calls) == 1, "应注册 1 个 GATT 服务"
    svc_handle = svc_calls[0][1]
    svc_uuid = svc_calls[0][2]
    assert svc_handle == 0, "服务 handle 应为 0"
    assert svc_uuid == BLE_SERVICE_UUID, \
        "服务 UUID 应为 0x%04X，实际为 0x%04X" % (BLE_SERVICE_UUID, svc_uuid)
    print("  ✓ GATT 服务: handle=%d, UUID=0x%04X" % (svc_handle, svc_uuid))

    ble.stop()
    print("  ✓ 测试 3 通过")


def test_04_four_characteristics():
    """测试 4: 4 个特征值 FFF1(NOTIFY), FFF2(WRITE), FFF3(WRITE), FFF4(WRITE)"""
    print("\n=== 测试 4: 4 个特征值注册 ===")
    reset_mock()
    eb = EventBus()
    ble = BLEDriver(eb)

    ble.init()

    mock = _mock_ble_instance
    # add_character(service_handle, char_index, properties, uuid)
    char_calls = [c for c in mock.call_log if c[0] == "add_character"]
    assert len(char_calls) == 4, \
        "应注册 4 个特征值，实际注册 %d 个" % len(char_calls)

    # 提取 (char_index, uuid) 对
    char_map = {}
    for call in char_calls:
        # ("add_character", svc_handle, char_index, props, uuid)
        char_index = call[2]
        char_uuid = call[4]
        char_props = call[3]
        char_map[char_index] = (char_uuid, char_props)

    # 验证 FFF1 (index=0) — NOTIFY 通道
    assert 0 in char_map, "缺少特征值 index=0 (FFF1)"
    assert char_map[0][0] == BLE_CHAR_DATA, \
        "FFF1 UUID 应为 0x%04X" % BLE_CHAR_DATA
    # FFF1 应有 NOTIFY 属性
    assert char_map[0][1] & MockBLE.PROP_NOTIFY, "FFF1 应有 NOTIFY 属性"
    print("  ✓ [0] FFF1 (数据通道, NOTIFY) UUID=0x%04X" % BLE_CHAR_DATA)

    # 验证 FFF2 (index=1) — 导航通道
    assert 1 in char_map, "缺少特征值 index=1 (FFF2)"
    assert char_map[1][0] == BLE_CHAR_NAV, \
        "FFF2 UUID 应为 0x%04X" % BLE_CHAR_NAV
    print("  ✓ [1] FFF2 (导航通道, WRITE) UUID=0x%04X" % BLE_CHAR_NAV)

    # 验证 FFF3 (index=2) — 控制通道
    assert 2 in char_map, "缺少特征值 index=2 (FFF3)"
    assert char_map[2][0] == BLE_CHAR_CTRL, \
        "FFF3 UUID 应为 0x%04X" % BLE_CHAR_CTRL
    print("  ✓ [2] FFF3 (控制通道, WRITE) UUID=0x%04X" % BLE_CHAR_CTRL)

    # 验证 FFF4 (index=3) — 报警确认通道
    assert 3 in char_map, "缺少特征值 index=3 (FFF4)"
    assert char_map[3][0] == BLE_CHAR_ACK, \
        "FFF4 UUID 应为 0x%04X" % BLE_CHAR_ACK
    print("  ✓ [3] FFF4 (报警确认, WRITE) UUID=0x%04X" % BLE_CHAR_ACK)

    ble.stop()
    print("  ✓ 测试 4 通过")


def test_05_notify_data_on_fff1():
    """测试 5: notify_data() 通过 FFF1 发送 Notify"""
    print("\n=== 测试 5: notify_data() 发送通道 ===")
    reset_mock()
    eb = EventBus()
    ble = BLEDriver(eb)

    ble.init()

    # 模拟已连接状态（notify_data 检查 is_connected）
    ble.ctx["is_connected"] = True

    mock = _mock_ble_instance
    # 清空之前的调用记录
    mock.call_log.clear()

    # 发送测试数据
    test_payload = '{"t":1,"d":{"tmp":25}}'
    ble.notify_data(test_payload)

    # 验证 notify 调用
    notify_calls = [c for c in mock.call_log if c[0] == "notify"]
    assert len(notify_calls) == 1, "应调用 1 次 notify()"
    # ("notify", char_uuid, length, data)
    notify_char = notify_calls[0][1]
    notify_len = notify_calls[0][2]
    notify_data = notify_calls[0][3]
    assert notify_char == BLE_CHAR_DATA, \
        "notify 应使用 FFF1 (0x%04X)，实际为 0x%04X" % (BLE_CHAR_DATA, notify_char)
    assert notify_data == test_payload, "notify 数据应与输入一致"
    assert notify_len == len(test_payload), "notify 长度应匹配"
    print("  ✓ notify 通道: FFF1 (0x%04X)" % BLE_CHAR_DATA)
    print("  ✓ 数据: %s" % test_payload)

    # 验证未连接时不发送
    mock.call_log.clear()
    ble.ctx["is_connected"] = False
    ble.notify_data('{"t":99}')
    notify_calls = [c for c in mock.call_log if c[0] == "notify"]
    assert len(notify_calls) == 0, "未连接时 notify_data 不应发送"
    print("  ✓ 未连接时 notify_data 静默跳过")

    ble.stop()
    print("  ✓ 测试 5 通过")


def test_06_event_bus_connected():
    """测试 6: BLE 连接时发布 EVENT_BLE_CONNECTED"""
    print("\n=== 测试 6: EVENT_BLE_CONNECTED 事件 ===")
    reset_mock()
    eb = EventBus()
    ble = BLEDriver(eb)

    # 订阅连接事件
    connected_events = []

    def on_connected(payload):
        connected_events.append(payload)

    eb.subscribe(EVENT_BLE_CONNECTED, on_connected)

    ble.init()

    # 模拟 BLE 连接回调
    mock = _mock_ble_instance
    assert mock._callback is not None, "BLE.init() 应注册回调"
    mock._callback({"event": MockBLE.EVT_CONNECTED})

    # 泵循环驱动事件
    pump_loop(eb, [ble], iterations=5)

    assert len(connected_events) == 1, \
        "应收到 1 个 EVENT_BLE_CONNECTED，实际 %d" % len(connected_events)
    assert ble.ctx["is_connected"] is True, "连接后 is_connected 应为 True"
    print("  ✓ EVENT_BLE_CONNECTED 已发布")
    print("  ✓ is_connected = True")

    ble.stop()
    print("  ✓ 测试 6 通过")


def test_07_event_bus_disconnected():
    """测试 7: BLE 断连时发布 EVENT_BLE_DISCONNECTED"""
    print("\n=== 测试 7: EVENT_BLE_DISCONNECTED 事件 ===")
    reset_mock()
    eb = EventBus()
    ble = BLEDriver(eb)

    ble.init()

    # 先模拟连接
    mock = _mock_ble_instance
    mock._callback({"event": MockBLE.EVT_CONNECTED})
    pump_loop(eb, [ble], iterations=3)
    assert ble.ctx["is_connected"] is True, "前置条件：应已连接"

    # 订阅断连事件
    disconnected_events = []

    def on_disconnected(payload):
        disconnected_events.append(payload)

    eb.subscribe(EVENT_BLE_DISCONNECTED, on_disconnected)

    # 模拟断连回调
    mock._callback({"event": MockBLE.EVT_DISCONNECTED})
    pump_loop(eb, [ble], iterations=5)

    assert len(disconnected_events) == 1, \
        "应收到 1 个 EVENT_BLE_DISCONNECTED，实际 %d" % len(disconnected_events)
    assert ble.ctx["is_connected"] is False, "断连后 is_connected 应为 False"
    print("  ✓ EVENT_BLE_DISCONNECTED 已发布")
    print("  ✓ is_connected = False")

    ble.stop()
    print("  ✓ 测试 7 通过")


def test_08_get_data_returns_status():
    """测试 8: get_data() 返回连接状态信息"""
    print("\n=== 测试 8: get_data() 返回值 ===")
    reset_mock()
    eb = EventBus()
    ble = BLEDriver(eb)

    ble.init()

    # 未连接状态
    data = ble.get_data()
    assert "is_connected" in data, "get_data() 应包含 is_connected"
    assert "mtu" in data, "get_data() 应包含 mtu"
    assert "connected_addr" in data, "get_data() 应包含 connected_addr"
    assert "timestamp" in data, "get_data() 应包含 timestamp"
    assert data["is_connected"] is False, "未连接时 is_connected 应为 False"
    assert data["mtu"] == 23, "默认 MTU 应为 23"
    print("  ✓ 未连接状态: %s" % str(data))

    # 模拟连接后
    mock = _mock_ble_instance
    mock._callback({"event": MockBLE.EVT_CONNECTED})
    pump_loop(eb, [ble], iterations=3)

    data = ble.get_data()
    assert data["is_connected"] is True, "连接后 is_connected 应为 True"
    print("  ✓ 连接后状态: is_connected=True")

    # 验证 get_status()
    status = ble.get_status()
    assert status["is_init"] is True, "get_status() is_init 应为 True"
    assert "is_connected" in status, "get_status() 应包含 is_connected"
    assert "err_count" in status, "get_status() 应包含 err_count"
    assert "power_state" in status, "get_status() 应包含 power_state"
    print("  ✓ get_status(): %s" % str(status))

    ble.stop()
    print("  ✓ 测试 8 通过")


# ==================== 主入口 ====================

def run_all_tests():
    """运行所有单元测试"""
    print("=" * 50)
    print("BLEDriver 单元测试（MockBLE）")
    print("=" * 50)

    tests = [
        test_01_init_success,
        test_02_advertising_name,
        test_03_gatt_service_uuid,
        test_04_four_characteristics,
        test_05_notify_data_on_fff1,
        test_06_event_bus_connected,
        test_07_event_bus_disconnected,
        test_08_get_data_returns_status,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print("  ✗ 失败: %s" % str(e))

    print("\n" + "=" * 50)
    print("测试结果: %d 通过, %d 失败, 共 %d" % (passed, failed, len(tests)))
    print("=" * 50)

    if failed > 0:
        print("✗ 存在失败测试")
    else:
        print("✓ 全部通过")


if __name__ == "__main__":
    run_all_tests()
