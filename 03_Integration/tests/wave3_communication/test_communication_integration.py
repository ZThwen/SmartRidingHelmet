"""
brief Wave 3 通信层联合集成测试
note 验证 BLE → NavigationService + ControlService 双通道通信
     使用 MockBLE 替代 quectel.BLE，FakeAudio 替代真实音频
     无需真实硬件，纯逻辑验证。在板子上运行。

测试覆盖：
  1. 导航 + 控制双通道同时运作
  2. BLE FFF2(导航) → NavigationService → TTS
  3. BLE FFF3(控制) → ControlService → 控制事件
  4. 导航 + 控制指令交替发送
  5. 状态回推 CONTROL_STATE_CHANGED → BLEService → MockBLE notify
  6. 报警状态 → BLEService 推送报警通知
  7. 快速连续导航指令 — 队列顺序保持
  8. event_log 同时包含 NAV 和 CONTROL 事件
"""
import sys
import time
import json

# 路径设置：从 03_Integration/tests/wave3_communication/ 到 02_Software/
sys.path.append("../../../02_Software")


# ==================== 模拟硬件层 ====================

class MockBLE:
    """
    brief 模拟 EC200U BLE 模块
    note 记录所有 API 调用，追踪 notify 输出
    """
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
        self.call_log = []
        self.notify_log = []
        self._callback = None

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
        self.notify_log.append((char_uuid, length, data))

    def get_addr(self):
        return "AA:BB:CC:DD:EE:FF"

    def stop(self):
        self.call_log.append(("stop",))

    def deinit(self):
        self.call_log.append(("deinit",))

    def exchange_mtu(self, mtu):
        self.call_log.append(("exchange_mtu", mtu))


class _MockQuectel:
    """模拟 quectel 模块"""
    BLE = MockBLE


# 注入模拟模块（必须在 import BLEDriver 之前）
sys.modules["quectel"] = _MockQuectel()


# ==================== 导入被测模块 ====================

from core.Event_Bus import EventBus
from core.config import (
    EVENT_BLE_CONNECTED, EVENT_NAV_CMD, EVENT_RIDE_CONTROL,
    EVENT_CONTROL_STATE_CHANGED, EVENT_ALARM_TRIGGERED,
    EVENT_TTS_REQUEST, BLE_CHAR_NAV, BLE_CHAR_CTRL,
)
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService
from Modules.control_service import ControlService


# ==================== FakeAudio ====================

class FakeAudio:
    """模拟 AudioDriver，记录 TTS 调用"""

    def __init__(self):
        self.tts_log = []

    def play_tts(self, text):
        self.tts_log.append(text)

    def play_file(self, path):
        pass


# ==================== 事件日志 ====================

event_log = []


def _log_event(tag, payload):
    event_log.append("%s:%s" % (tag, str(payload)[:80]))


# ==================== 系统构建 ====================

def make_full_system():
    """
    brief 构建完整测试系统
    note EventBus + MockBLE + BLEDriver + BLEService
         + FakeAudio + NavigationService + ControlService
    return 元组 (eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio)
    """
    global event_log
    event_log = []

    eb = EventBus()
    mock_ble = MockBLE()
    sys.modules["quectel"].BLE = lambda: mock_ble

    ble_drv = BLEDriver(event_bus=eb)
    ble_drv._ble = mock_ble
    mock_ble._callback = ble_drv._callback

    audio = FakeAudio()
    ble_svc = BLEService(event_bus=eb, ble_driver=ble_drv)
    nav = NavigationService(event_bus=eb, audio_driver=audio, lcd_driver=None)
    ctrl = ControlService(event_bus=eb)

    for mod in [ble_drv, ble_svc, nav, ctrl]:
        try:
            mod.init()
        except Exception as e:
            print("  [WARN] init %s: %s" % (mod.name, e))

    # 订阅事件日志
    eb.subscribe(EVENT_NAV_CMD, lambda p: _log_event("NAV", p))
    eb.subscribe(EVENT_RIDE_CONTROL, lambda p: _log_event("CTRL", p))
    eb.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: _log_event("STATE", p))
    eb.subscribe(EVENT_ALARM_TRIGGERED, lambda p: _log_event("ALARM", p))
    eb.subscribe(EVENT_TTS_REQUEST, lambda p: _log_event("TTS", p))

    return eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio


def pump_loop(eb, modules, cycles=10, interval_ms=50):
    """泵循环：驱动 EventBus 和模块 tick，替代 time.sleep()"""
    for _ in range(cycles):
        for mod in modules:
            try:
                if mod.ctx.get("is_init", False):
                    mod.tick()
            except Exception:
                pass
        eb.pump()
        time.sleep_ms(interval_ms)


def simulate_ble_write(ble_drv, char_uuid, json_str):
    """
    brief 模拟手机通过 BLE 特征值写入数据
    note 触发 BLEDriver._callback → BLEService._on_ble_data → cmd_buffer
    param ble_drv: BLEDriver 实例
    param char_uuid: 特征值 UUID（BLE_CHAR_NAV 或 BLE_CHAR_CTRL）
    param json_str: 写入的 JSON 字符串
    """
    evt = {"event": MockBLE.EVT_VAL_DATA, "uuid": char_uuid, "value": json_str}
    ble_drv._callback(evt)


def send_nav_cmd(eb, nav_json_str):
    """发送导航指令事件"""
    eb.publish(EVENT_NAV_CMD, {"raw": nav_json_str})


def send_ctrl_cmd(eb, ctrl, cmd_name):
    """
    brief 发送控制指令事件（含防抖重置）
    note 重置 last_cmd_tick 绕过 300ms 防抖
    """
    ctrl.ctx["last_cmd_tick"] = 0
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd_name}})
    eb.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    eb.pump()


# ==================== 测试用例 ====================

def test_01_both_channels_operational():
    """测试 1: 导航和控制双通道同时运作"""
    print("\n=== 测试 1: 双通道同时运作 ===")
    eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio = make_full_system()

    # 导航指令通过 FFF2
    nav_json = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 200, "road": "测试路"}})
    simulate_ble_write(ble_drv, BLE_CHAR_NAV, nav_json)
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=10)

    assert nav.ctx["is_navigating"] is True, "导航服务应激活"
    assert nav.ctx["current_dir"] == "right", "方向应为 right"
    assert nav.ctx["current_dist"] == 200, "距离应为 200"
    print("  OK 导航通道: dir=right, dist=200")

    # 控制指令通过 FFF3
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl_json = json.dumps({"a": "ctrl", "d": {"cmd": "light_on"}})
    simulate_ble_write(ble_drv, BLE_CHAR_CTRL, ctrl_json)
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=10)

    assert ctrl._data["last_cmd"] == "light_on", "控制指令应执行 light_on"
    assert ctrl._control_state["light_mode"] == "manual", "灯光模式应为 manual"
    print("  OK 控制通道: cmd=light_on")
    print("  OK 测试 1 通过")


def test_02_nav_channel_tts():
    """测试 2: BLE FFF2(导航) → NavigationService → TTS"""
    print("\n=== 测试 2: 导航通道 TTS 播报 ===")
    eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio = make_full_system()

    nav_json = json.dumps({"a": "nav", "d": {"dir": "left", "dist": 500, "road": "中山路"}})
    simulate_ble_write(ble_drv, BLE_CHAR_NAV, nav_json)
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=15)

    assert nav.ctx["is_navigating"] is True, "应进入导航状态"
    assert nav.ctx["current_dir"] == "left", "方向应为 left"
    assert nav.ctx["current_dist"] == 500, "距离应为 500"
    assert nav.ctx["current_road"] == "中山路", "路名应为 中山路"
    print("  OK 导航数据解析正确")

    # 验证 TTS 文本（通过 _data 检查，TTS 在子线程播放）
    expected_tts = "前方500米左转进入中山路"
    assert nav._data["last_tts"] == expected_tts, \
        "TTS 文本应为 '%s'，实际 '%s'" % (expected_tts, nav._data["last_tts"])
    print("  OK TTS: %s" % nav._data["last_tts"])

    # 验证 LCD 文本
    expected_lcd = "< 500m 中山路"
    assert nav._data["last_lcd"] == expected_lcd, \
        "LCD 文本应为 '%s'，实际 '%s'" % (expected_lcd, nav._data["last_lcd"])
    print("  OK LCD: %s" % nav._data["last_lcd"])
    print("  OK 测试 2 通过")


def test_03_control_channel_events():
    """测试 3: BLE FFF3(控制) → ControlService → 控制事件"""
    print("\n=== 测试 3: 控制通道事件发布 ===")
    eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio = make_full_system()

    ctrl_json = json.dumps({"a": "ctrl", "d": {"cmd": "volume_up"}})
    simulate_ble_write(ble_drv, BLE_CHAR_CTRL, ctrl_json)
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=10)

    assert ctrl._data["last_cmd"] == "volume_up", "应执行 volume_up"
    assert ctrl._control_state["volume"] == 6, \
        "音量应为 6（原 5 + 步长 1），实际 %d" % ctrl._control_state["volume"]
    print("  OK volume_up: volume=%d" % ctrl._control_state["volume"])

    # 验证 CONTROL_STATE_CHANGED 事件已发布（event_log 中有 STATE 记录）
    state_events = [e for e in event_log if e.startswith("STATE")]
    assert len(state_events) > 0, "应有 CONTROL_STATE_CHANGED 事件"
    print("  OK STATE 事件数: %d" % len(state_events))
    print("  OK 测试 3 通过")


def test_04_interleaved_commands():
    """测试 4: 导航 + 控制指令交替发送 — 两者均正确处理"""
    print("\n=== 测试 4: 交替指令无冲突 ===")
    eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio = make_full_system()

    # 第 1 轮：导航
    nav_json = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 100}})
    simulate_ble_write(ble_drv, BLE_CHAR_NAV, nav_json)
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=5)

    # 第 2 轮：控制
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl_json = json.dumps({"a": "ctrl", "d": {"cmd": "light_on"}})
    simulate_ble_write(ble_drv, BLE_CHAR_CTRL, ctrl_json)
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=5)

    # 第 3 轮：导航
    nav_json2 = json.dumps({"a": "nav", "d": {"dir": "left", "dist": 300, "road": "第二路"}})
    simulate_ble_write(ble_drv, BLE_CHAR_NAV, nav_json2)
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=5)

    # 第 4 轮：控制
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl_json2 = json.dumps({"a": "ctrl", "d": {"cmd": "brightness_up"}})
    simulate_ble_write(ble_drv, BLE_CHAR_CTRL, ctrl_json2)
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=5)

    # 验证导航最终状态（最后一次导航指令）
    assert nav.ctx["current_dir"] == "left", "最终导航方向应为 left"
    assert nav.ctx["current_dist"] == 300, "最终导航距离应为 300"
    print("  OK 导航最终状态: dir=left, dist=300")

    # 验证控制最终状态
    assert ctrl._control_state["light_mode"] == "manual", "灯光模式应为 manual"
    assert ctrl._control_state["light_brightness"] >= 50, \
        "亮度应 >= 50，实际 %d" % ctrl._control_state["light_brightness"]
    print("  OK 控制最终状态: brightness=%d" % ctrl._control_state["light_brightness"])
    print("  OK 测试 4 通过")


def test_05_state_push_to_ble():
    """测试 5: CONTROL_STATE_CHANGED → BLEService → MockBLE notify"""
    print("\n=== 测试 5: 状态回推到 BLE ===")
    eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio = make_full_system()

    # 模拟 BLE 已连接
    eb.publish(EVENT_BLE_CONNECTED, {"addr": "TEST", "timestamp": 0})
    eb.pump()
    pump_loop(eb, [ble_svc], cycles=3)
    assert ble_svc.ctx["ble_connected"] is True, "BLE 应标记已连接"

    mock_ble.notify_log.clear()

    # 发送控制指令 → 状态变更 → BLEService 快照 → tick 推送
    send_ctrl_cmd(eb, ctrl, "light_on")
    pump_loop(eb, [ble_svc, ctrl], cycles=20, interval_ms=50)

    # 验证 MockBLE 收到 notify（t=7 状态推送）
    state_notifies = [n for n in mock_ble.notify_log
                      if '"t":7' in n[2]]
    assert len(state_notifies) > 0, \
        "MockBLE 应收到 t=7 状态推送，notify_log=%s" % str(mock_ble.notify_log[:5])

    # 验证推送内容包含正确字段
    payload = state_notifies[0][2]
    assert '"m":1' in payload, "m(灯光模式) 应为 1(manual)"
    assert '"b":50' in payload, "b(亮度) 应为 50"
    print("  OK 状态推送: %s" % payload)
    print("  OK 测试 5 通过")


def test_06_alarm_notification():
    """测试 6: 报警触发 → BLEService 推送报警通知"""
    print("\n=== 测试 6: 报警状态推送 ===")
    eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio = make_full_system()

    # 模拟 BLE 已连接
    eb.publish(EVENT_BLE_CONNECTED, {"addr": "TEST", "timestamp": 0})
    eb.pump()
    pump_loop(eb, [ble_svc], cycles=3)

    mock_ble.notify_log.clear()

    # 触发报警
    eb.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    eb.pump()
    pump_loop(eb, [ble_svc], cycles=15, interval_ms=50)

    # 验证报警通知已入队（t=5, a=1(碰撞), l=2）
    alarm_notifies = [n for n in mock_ble.notify_log
                      if '"t":5' in n[2]]
    assert len(alarm_notifies) > 0, \
        "应收到报警通知(t=5)，notify_log=%s" % str(mock_ble.notify_log[:5])

    payload = alarm_notifies[0][2]
    assert '"a":1' in payload, "a 应为 1(碰撞类型)"
    assert '"l":2' in payload, "l 应为 2(等级)"
    print("  OK 报警推送: %s" % payload)
    print("  OK 测试 6 通过")


def test_07_rapid_nav_commands():
    """测试 7: 快速连续导航指令 — 队列顺序保持"""
    print("\n=== 测试 7: 快速导航指令顺序 ===")
    eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio = make_full_system()

    directions = ["left", "right", "straight", "slight_left", "uturn"]

    # 快速发送 5 条导航指令（通过 BLE 写入 → cmd_buffer）
    for i, d in enumerate(directions):
        nav_json = json.dumps({"a": "nav", "d": {"dir": d, "dist": (i + 1) * 100}})
        simulate_ble_write(ble_drv, BLE_CHAR_NAV, nav_json)

    # 泵循环处理所有指令
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=30, interval_ms=50)

    # 验证最后一条指令被正确执行（顺序处理，最终状态为最后一条）
    assert nav.ctx["current_dir"] == "uturn", \
        "最终方向应为 uturn，实际 '%s'" % nav.ctx["current_dir"]
    assert nav.ctx["current_dist"] == 500, \
        "最终距离应为 500，实际 %d" % nav.ctx["current_dist"]
    print("  OK 最终状态: dir=uturn, dist=500")

    # 验证所有指令均被处理（event_log 中有 5 条 NAV 事件）
    nav_events = [e for e in event_log if e.startswith("NAV")]
    assert len(nav_events) == 5, \
        "应有 5 条 NAV 事件，实际 %d" % len(nav_events)
    print("  OK NAV 事件数: %d" % len(nav_events))
    print("  OK 测试 7 通过")


def test_08_event_log_both_channels():
    """测试 8: event_log 同时包含 NAV 和 CONTROL 事件"""
    print("\n=== 测试 8: 双通道事件日志验证 ===")
    eb, mock_ble, ble_drv, ble_svc, nav, ctrl, audio = make_full_system()

    # 发送导航指令
    nav_json = json.dumps({"a": "nav", "d": {"dir": "right", "dist": 200}})
    send_nav_cmd(eb, nav_json)
    eb.pump()
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=5)

    # 发送控制指令
    send_ctrl_cmd(eb, ctrl, "light_on")
    pump_loop(eb, [ble_svc, nav, ctrl], cycles=5)

    # 验证事件日志包含两种类型
    nav_events = [e for e in event_log if e.startswith("NAV")]
    ctrl_events = [e for e in event_log if e.startswith("CTRL")]
    state_events = [e for e in event_log if e.startswith("STATE")]

    assert len(nav_events) > 0, "event_log 应有 NAV 事件"
    assert len(ctrl_events) > 0, "event_log 应有 CTRL 事件"
    assert len(state_events) > 0, "event_log 应有 STATE 事件"

    print("  OK NAV 事件: %d" % len(nav_events))
    print("  OK CTRL 事件: %d" % len(ctrl_events))
    print("  OK STATE 事件: %d" % len(state_events))
    print("  OK 完整事件日志:")
    for entry in event_log:
        print("    %s" % entry)
    print("  OK 测试 8 通过")


# ==================== 主入口 ====================

def run_all_tests():
    """运行所有 Wave 3 通信层集成测试"""
    print("=" * 50)
    print("Wave 3 通信层联合集成测试")
    print("BLE + NavigationService + ControlService")
    print("=" * 50)

    tests = [
        test_01_both_channels_operational,
        test_02_nav_channel_tts,
        test_03_control_channel_events,
        test_04_interleaved_commands,
        test_05_state_push_to_ble,
        test_06_alarm_notification,
        test_07_rapid_nav_commands,
        test_08_event_log_both_channels,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print("  FAIL %s: %s" % (test_fn.__name__, e))

    print("\n" + "=" * 50)
    print("测试结果: %d 通过, %d 失败, 共 %d" % (passed, failed, len(tests)))
    print("=" * 50)

    if failed > 0:
        print("FAIL: 存在 %d 个失败测试" % failed)
    else:
        print("ALL PASS")


if __name__ == "__main__":
    run_all_tests()
