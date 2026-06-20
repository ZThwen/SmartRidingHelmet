"""
brief BLEService 通信层集成测试（Wave 3）
note 使用 MockBLE 替代 quectel.BLE，构建完整链路：
     MockBLE → BLEDriver → BLEService → EventBus
     验证双线程架构、事件缓存、JSON 拼装、Notify 推送
     无需手机连接，纯逻辑验证。在板子上运行。
"""
import sys
import time
import json

# 路径设置：从 03_Integration/tests/wave3_communication/ 到 02_Software/
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
    EVENT_TEMP_HUMID_READY, EVENT_IMU_READY,
    EVENT_GNSS_READY, EVENT_LIGHT_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_CONTROL_STATE_CHANGED,
    BLE_UPLOAD_INTERVAL_MS, BLE_KEEPALIVE_MS,
    BLE_CHAR_DATA,
)
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


# ==================== 测试辅助 ====================

def make_system():
    """
    brief 构建完整测试系统
    note EventBus + MockBLE + BLEDriver + BLEService
         返回各组件引用，供测试用例使用
    """
    global _mock_ble_instance
    _mock_ble_instance = None

    eb = EventBus()
    ble_driver = BLEDriver(eb)
    ble_driver.init()

    svc = BLEService(eb, ble_driver=ble_driver)
    svc.init()

    return {
        "eb": eb,
        "mock": _mock_ble_instance,
        "ble_driver": ble_driver,
        "svc": svc,
    }


def pump_loop(system, iterations=20, interval_ms=50):
    """
    brief 泵循环辅助函数
    note 替代 time.sleep()，在等待期间持续驱动 EventBus 和 BLEService tick
         遵循架构规范：tick() + pump() + sleep_ms()
    param system: make_system() 返回的字典
    param iterations: 循环次数
    param interval_ms: 每次间隔 (ms)
    """
    eb = system["eb"]
    svc = system["svc"]
    for _ in range(iterations):
        svc.tick()
        eb.pump()
        time.sleep_ms(interval_ms)


def pump_loop_timed(system, duration_ms, interval_ms=50):
    """
    brief 基于 ticks_diff 的定时泵循环
    note 用于需要精确等待时间的测试（如心跳间隔）
    param system: make_system() 返回的字典
    param duration_ms: 总持续时间 (ms)
    param interval_ms: 每次间隔 (ms)
    """
    eb = system["eb"]
    svc = system["svc"]
    end = time.ticks_add(time.ticks_ms(), duration_ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        svc.tick()
        eb.pump()
        time.sleep_ms(interval_ms)


def get_notify_payloads(mock):
    """
    brief 从 MockBLE call_log 提取 notify 数据（解析 JSON）
    return list 解析后的 JSON 对象列表
    """
    results = []
    for call in mock.call_log:
        if call[0] == "notify":
            # ("notify", char_uuid, length, data_str)
            try:
                results.append(json.loads(call[3]))
            except Exception:
                results.append(call[3])
    return results


def simulate_ble_connect(system):
    """
    brief 模拟 BLE 连接
    note 通过 MockBLE 回调触发 BLEDriver → EventBus → BLEService 全链路
    """
    mock = system["mock"]
    mock._callback({"event": MockBLE.EVT_CONNECTED})
    # 泵循环驱动事件传播
    pump_loop(system, iterations=5, interval_ms=20)


def simulate_ble_disconnect(system):
    """
    brief 模拟 BLE 断连
    """
    mock = system["mock"]
    mock._callback({"event": MockBLE.EVT_DISCONNECTED})
    pump_loop(system, iterations=5, interval_ms=20)


def clear_notify_log(system):
    """清除 MockBLE 调用日志中的 notify 记录"""
    mock = system["mock"]
    mock.call_log = [c for c in mock.call_log if c[0] != "notify"]


# ==================== 测试用例 ====================

def test_01_init_success():
    """测试 1: init() 成功后 is_init=True，后台线程标志已设置"""
    print("\n=== 测试 1: init() 初始化成功 ===")
    system = make_system()
    svc = system["svc"]

    assert svc.ctx["is_init"] is True, "init() 后 is_init 应为 True"
    print("  ✓ is_init = True")

    assert svc.ctx["thread_running"] is True, "init() 后 thread_running 应为 True"
    print("  ✓ thread_running = True")

    assert svc.send_queue is not None, "init() 后 send_queue 应已创建"
    print("  ✓ send_queue 已创建")

    # 验证 BLEDriver 已注册数据处理器
    ble_driver = system["ble_driver"]
    assert ble_driver._data_handler is not None, "BLEDriver 应注册 data_handler"
    print("  ✓ BLEDriver.data_handler 已注册")

    # 停止后台线程（避免干扰后续测试）
    svc.ctx["thread_running"] = False
    time.sleep_ms(200)
    print("  ✓ 测试 1 通过")


def test_02_sensor_events_cached_and_enqueued():
    """测试 2: 传感器事件 → 数据缓存 → tick() 拼装 JSON → 入队"""
    print("\n=== 测试 2: 传感器数据缓存与 JSON 拼装 ===")
    system = make_system()
    svc = system["svc"]
    eb = system["eb"]

    # 发布传感器事件（BLE 未连接，数据只缓存不发送）
    eb.publish(EVENT_TEMP_HUMID_READY, {
        "temp": 25.3, "humid": 60.1, "valid": True})
    eb.publish(EVENT_IMU_READY, {
        "acc_x": 0.5, "acc_y": -0.2, "acc_z": 9.8, "valid": True})
    eb.publish(EVENT_GNSS_READY, {
        "latitude": 31.23, "longitude": 121.47,
        "altitude": 12.5, "speed_kmh": 15.2, "cog": 45.0, "valid": True})
    eb.publish(EVENT_LIGHT_READY, {
        "light_intensity": 8500, "valid": True})
    pump_loop(system, iterations=3, interval_ms=20)

    # 验证数据缓存
    assert svc._data["latest_temp"] == 25.3, "温度应缓存为 25.3"
    assert svc._data["latest_humid"] == 60.1, "湿度应缓存为 60.1"
    print("  ✓ 温湿度缓存: temp=%s, humid=%s" % (
        svc._data["latest_temp"], svc._data["latest_humid"]))

    assert svc._data["latest_ax"] == 0.5, "加速度 X 应缓存"
    assert svc._data["latest_ay"] == -0.2, "加速度 Y 应缓存"
    assert svc._data["latest_az"] == 9.8, "加速度 Z 应缓存"
    print("  ✓ IMU 缓存: ax=%s, ay=%s, az=%s" % (
        svc._data["latest_ax"], svc._data["latest_ay"], svc._data["latest_az"]))

    assert svc._data["latest_lat"] == 31.23, "纬度应缓存"
    assert svc._data["latest_lon"] == 121.47, "经度应缓存"
    assert svc._data["latest_spd"] == 15.2, "速度应缓存"
    assert svc._data["latest_cog"] == 45.0, "航向应缓存"
    print("  ✓ GNSS 缓存: lat=%s, lon=%s, spd=%s" % (
        svc._data["latest_lat"], svc._data["latest_lon"], svc._data["latest_spd"]))

    assert svc._data["latest_lux"] == 8500, "光照应缓存"
    print("  ✓ 光照缓存: lux=%s" % svc._data["latest_lux"])

    # 连接 BLE → force_push=True → tick() 触发 _enqueue_merged
    simulate_ble_connect(system)
    clear_notify_log(system)

    # 强制触发上传间隔
    svc.ctx["last_upload"] = 0
    pump_loop(system, iterations=30, interval_ms=50)

    # 检查 MockBLE notify 调用
    payloads = get_notify_payloads(system["mock"])
    found_sensor = False
    for p in payloads:
        if isinstance(p, dict) and p.get("t") == 0:
            d = p.get("d", {})
            assert "tmp" in d, "合并数据应包含 tmp"
            assert "hum" in d, "合并数据应包含 hum"
            assert "lat" in d, "合并数据应包含 lat"
            assert "lon" in d, "合并数据应包含 lon"
            assert d["tmp"] == 25.3, "tmp 应为 25.3"
            found_sensor = True
            print("  ✓ 合并 JSON: t=0, d=%s" % str(d))
            break
    assert found_sensor, "未收到合并的传感器数据 notify"

    svc.ctx["thread_running"] = False
    time.sleep_ms(200)
    print("  ✓ 测试 2 通过")


def test_03_ble_connected_notify():
    """测试 3: BLE 连接后数据通过 Notify 推送"""
    print("\n=== 测试 3: BLE 连接后 Notify 推送 ===")
    system = make_system()
    svc = system["svc"]
    eb = system["eb"]

    # 先连接 BLE
    simulate_ble_connect(system)
    assert svc.ctx["ble_connected"] is True, "连接后 ble_connected 应为 True"
    print("  ✓ BLE 已连接")

    # 发布传感器数据
    eb.publish(EVENT_TEMP_HUMID_READY, {
        "temp": 28.0, "humid": 55.0, "valid": True})
    pump_loop(system, iterations=3, interval_ms=20)

    # 强制上传
    svc.ctx["last_upload"] = 0
    clear_notify_log(system)
    pump_loop(system, iterations=30, interval_ms=50)

    # 检查 notify 调用
    payloads = get_notify_payloads(system["mock"])
    assert len(payloads) > 0, "连接后应有 notify 调用"

    has_data = False
    for p in payloads:
        if isinstance(p, dict) and p.get("t") == 0:
            has_data = True
            break
    assert has_data, "应收到 t=0 的传感器数据 notify"
    print("  ✓ 传感器数据已通过 Notify 推送")

    # 验证 notify 使用 FFF1 通道
    mock = system["mock"]
    notify_calls = [c for c in mock.call_log if c[0] == "notify"]
    for nc in notify_calls:
        assert nc[1] == BLE_CHAR_DATA, \
            "notify 应使用 FFF1 (0x%04X)，实际 0x%04X" % (BLE_CHAR_DATA, nc[1])
    print("  ✓ Notify 通道: FFF1 (0x%04X)" % BLE_CHAR_DATA)

    svc.ctx["thread_running"] = False
    time.sleep_ms(200)
    print("  ✓ 测试 3 通过")


def test_04_ble_disconnected_no_notify():
    """测试 4: BLE 未连接时不发送 Notify"""
    print("\n=== 测试 4: BLE 未连接时不发送 ===")
    system = make_system()
    svc = system["svc"]
    eb = system["eb"]

    # 不连接 BLE，确认状态
    assert svc.ctx["ble_connected"] is False, "初始状态 ble_connected 应为 False"

    # 发布传感器数据
    eb.publish(EVENT_TEMP_HUMID_READY, {
        "temp": 30.0, "humid": 50.0, "valid": True})
    eb.publish(EVENT_GNSS_READY, {
        "latitude": 31.0, "longitude": 121.0,
        "altitude": 10.0, "speed_kmh": 12.0, "valid": True})

    # 强制触发上传检查
    svc.ctx["last_upload"] = 0
    pump_loop(system, iterations=30, interval_ms=50)

    # 检查 MockBLE 没有 notify 调用
    mock = system["mock"]
    notify_calls = [c for c in mock.call_log if c[0] == "notify"]
    assert len(notify_calls) == 0, \
        "未连接时不应有 notify 调用，实际 %d 次" % len(notify_calls)
    print("  ✓ 未连接时无 notify 调用")

    # 验证 _enqueue_merged 守卫：ble_connected=False 时不入队
    # 注意：后台线程会消费队列，但 _enqueue_merged 根本不会入队
    print("  ✓ _enqueue_merged 守卫生效（ble_connected=False 跳过）")

    # 测试断连后清空队列
    simulate_ble_connect(system)
    # 塞入测试数据
    for i in range(5):
        svc.send_queue.put('{"t":0,"d":{"tmp":%d}}' % i)
    assert svc.send_queue.size() > 0, "队列应有数据"

    simulate_ble_disconnect(system)
    assert svc.ctx["ble_connected"] is False, "断连后 ble_connected 应为 False"
    assert svc.send_queue.size() == 0, \
        "断连后队列应清空，实际 %d" % svc.send_queue.size()
    print("  ✓ 断连后队列已清空")

    svc.ctx["thread_running"] = False
    time.sleep_ms(200)
    print("  ✓ 测试 4 通过")


def test_05_keepalive():
    """测试 5: 心跳包每 BLE_KEEPALIVE_MS 发送"""
    print("\n=== 测试 5: 心跳包 ===")
    system = make_system()
    svc = system["svc"]

    # 连接 BLE
    simulate_ble_connect(system)
    assert svc.ctx["ble_connected"] is True, "前置条件：应已连接"
    clear_notify_log(system)

    # 强制心跳触发：设置 last_keepalive 为过期
    svc.ctx["last_keepalive"] = 0
    svc.ctx["last_upload"] = time.ticks_ms()  # 防止数据上传干扰

    # 泵循环等待心跳
    pump_loop(system, iterations=10, interval_ms=50)

    # 检查心跳包
    payloads = get_notify_payloads(system["mock"])
    found_keepalive = False
    for p in payloads:
        if isinstance(p, dict) and p.get("t") == 99:
            found_keepalive = True
            print("  ✓ 心跳包: %s" % str(p))
            break
    assert found_keepalive, "未收到心跳包 (t=99)"

    # 验证心跳仅在连接时发送
    simulate_ble_disconnect(system)
    clear_notify_log(system)
    svc.ctx["last_keepalive"] = 0
    pump_loop(system, iterations=10, interval_ms=50)

    payloads = get_notify_payloads(system["mock"])
    has_keepalive = False
    for p in payloads:
        if isinstance(p, dict) and p.get("t") == 99:
            has_keepalive = True
            break
    assert not has_keepalive, "断连后不应发送心跳包"
    print("  ✓ 断连后无心跳包")

    svc.ctx["thread_running"] = False
    time.sleep_ms(200)
    print("  ✓ 测试 5 通过")


def test_06_get_data_returns_sensor_values():
    """测试 6: get_data() 返回服务状态，_data 缓存传感器值"""
    print("\n=== 测试 6: get_data() 与传感器缓存 ===")
    system = make_system()
    svc = system["svc"]
    eb = system["eb"]

    # 未连接状态
    data = svc.get_data()
    assert "ble_connected" in data, "get_data() 应包含 ble_connected"
    assert "queue_size" in data, "get_data() 应包含 queue_size"
    assert "err_count" in data, "get_data() 应包含 err_count"
    assert "timestamp" in data, "get_data() 应包含 timestamp"
    assert data["ble_connected"] is False, "未连接时 ble_connected 应为 False"
    print("  ✓ 未连接状态: %s" % str(data))

    # 发布传感器事件
    eb.publish(EVENT_TEMP_HUMID_READY, {
        "temp": 22.5, "humid": 65.0, "valid": True})
    eb.publish(EVENT_LIGHT_READY, {
        "light_intensity": 12000, "valid": True})
    pump_loop(system, iterations=3, interval_ms=20)

    # 验证内部 _data 缓存
    assert svc._data["latest_temp"] == 22.5, "温度应缓存"
    assert svc._data["latest_humid"] == 65.0, "湿度应缓存"
    assert svc._data["latest_lux"] == 12000, "光照应缓存"
    print("  ✓ 传感器值已缓存: temp=%s, humid=%s, lux=%s" % (
        svc._data["latest_temp"], svc._data["latest_humid"], svc._data["latest_lux"]))

    # 无效数据不应覆盖
    eb.publish(EVENT_TEMP_HUMID_READY, {
        "temp": 99.9, "humid": 99.9, "valid": False})
    pump_loop(system, iterations=3, interval_ms=20)
    assert svc._data["latest_temp"] == 22.5, "无效数据不应覆盖缓存"
    print("  ✓ 无效数据被过滤（valid=False 不更新缓存）")

    # 连接后 get_data 状态变化
    simulate_ble_connect(system)
    data = svc.get_data()
    assert data["ble_connected"] is True, "连接后 ble_connected 应为 True"
    print("  ✓ 连接后: ble_connected=True")

    svc.ctx["thread_running"] = False
    time.sleep_ms(200)
    print("  ✓ 测试 6 通过")


def test_07_get_status_returns_thread_state():
    """测试 7: get_status() 返回线程和连接状态"""
    print("\n=== 测试 7: get_status() 线程与连接状态 ===")
    system = make_system()
    svc = system["svc"]

    status = svc.get_status()
    assert "is_init" in status, "get_status() 应包含 is_init"
    assert "ble_connected" in status, "get_status() 应包含 ble_connected"
    assert "thread_running" in status, "get_status() 应包含 thread_running"
    assert "err_count" in status, "get_status() 应包含 err_count"
    assert "consecutive_errors" in status, "get_status() 应包含 consecutive_errors"
    print("  ✓ 状态字段完整: %s" % str(status))

    assert status["is_init"] is True, "is_init 应为 True"
    assert status["thread_running"] is True, "thread_running 应为 True"
    assert status["ble_connected"] is False, "未连接时 ble_connected 应为 False"
    assert status["err_count"] == 0, "初始 err_count 应为 0"
    assert status["consecutive_errors"] == 0, "初始 consecutive_errors 应为 0"
    print("  ✓ 初始状态值正确")

    # 连接后状态变化
    simulate_ble_connect(system)
    status = svc.get_status()
    assert status["ble_connected"] is True, "连接后 ble_connected 应为 True"
    print("  ✓ 连接后: ble_connected=True")

    # 断连后状态变化
    simulate_ble_disconnect(system)
    status = svc.get_status()
    assert status["ble_connected"] is False, "断连后 ble_connected 应为 False"
    print("  ✓ 断连后: ble_connected=False")

    svc.ctx["thread_running"] = False
    time.sleep_ms(200)
    print("  ✓ 测试 7 通过")


def test_08_control_state_push():
    """测试 8: EVENT_CONTROL_STATE_CHANGED → 快照合并 → BLE 推送"""
    print("\n=== 测试 8: 控制状态合并推送 ===")
    system = make_system()
    svc = system["svc"]
    eb = system["eb"]

    # 连接 BLE
    simulate_ble_connect(system)
    assert svc.ctx["ble_connected"] is True, "前置条件：应已连接"
    clear_notify_log(system)

    # 发布控制状态变更事件（t=7: 灯光控制）
    eb.publish(EVENT_CONTROL_STATE_CHANGED, {
        "t": 7, "m": 1, "b": 50, "v": 5, "p": 0})
    pump_loop(system, iterations=3, interval_ms=20)

    # 验证快照更新
    snap = svc._ctrl_snapshot
    assert snap["m"] == 1, "快照 mode 应为 1"
    assert snap["b"] == 50, "快照 brightness 应为 50"
    assert snap["v"] == 5, "快照 volume 应为 5"
    assert snap["p"] == 0, "快照 power 应为 0"
    assert snap["dirty"] is True, "快照应标记为 dirty"
    print("  ✓ 控制快照已更新: m=%d, b=%d, v=%d, p=%d" % (
        snap["m"], snap["b"], snap["v"], snap["p"]))

    # tick() 推送 dirty 快照
    pump_loop(system, iterations=20, interval_ms=50)

    # 检查 notify 推送
    payloads = get_notify_payloads(system["mock"])
    found_ctrl = False
    for p in payloads:
        if isinstance(p, dict) and p.get("t") == 7:
            found_ctrl = True
            assert p.get("m") == 1, "推送 mode 应为 1"
            assert p.get("b") == 50, "推送 brightness 应为 50"
            print("  ✓ 控制状态已推送: %s" % str(p))
            break
    assert found_ctrl, "未收到控制状态推送 (t=7)"

    # 验证 dirty 标志已清除
    assert svc._ctrl_snapshot["dirty"] is False, "推送后 dirty 应为 False"
    print("  ✓ dirty 标志已清除")

    # 测试多条事件合并为 1 条
    clear_notify_log(system)
    eb.publish(EVENT_CONTROL_STATE_CHANGED, {
        "t": 7, "m": 1, "b": 30, "v": 3, "p": 0})
    eb.publish(EVENT_CONTROL_STATE_CHANGED, {
        "t": 7, "m": 0, "b": 80, "v": 8, "p": 1})
    pump_loop(system, iterations=20, interval_ms=50)

    # 应只收到 1 条推送（最后一条的值）
    payloads = get_notify_payloads(system["mock"])
    ctrl_msgs = [p for p in payloads if isinstance(p, dict) and p.get("t") == 7]
    assert len(ctrl_msgs) == 1, \
        "多条事件应合并为 1 条推送，实际 %d 条" % len(ctrl_msgs)
    merged = ctrl_msgs[0]
    assert merged.get("b") == 80, "合并后 brightness 应为最后一条的值 80"
    print("  ✓ 多条控制事件合并为 1 条: %s" % str(merged))

    svc.ctx["thread_running"] = False
    time.sleep_ms(200)
    print("  ✓ 测试 8 通过")


# ==================== 主入口 ====================

def run_all_tests():
    """运行所有 BLEService 集成测试"""
    print("=" * 50)
    print("BLEService 通信层集成测试（Wave 3）")
    print("=" * 50)

    tests = [
        test_01_init_success,
        test_02_sensor_events_cached_and_enqueued,
        test_03_ble_connected_notify,
        test_04_ble_disconnected_no_notify,
        test_05_keepalive,
        test_06_get_data_returns_sensor_values,
        test_07_get_status_returns_thread_state,
        test_08_control_state_push,
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
