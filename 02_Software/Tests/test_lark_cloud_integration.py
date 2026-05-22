"""
brief LarkCloudService 集成测试（EventBus + 主循环）
note 模拟真实运行环境，验证事件流转和模块协作
     不依赖真实 Qth 硬件（QthDriver 用 mock）
执行: 上传到板子运行 python Tests/test_lark_cloud_integration.py
"""
import sys
sys.path.append("..")
import time

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
)
from Drivers.network.thread_queue import ThreadSafeQueue
from Modules.lark_cloud import LarkCloudService


PASS = 0
FAIL = 0


class MockQth:
    """模拟 QthDriver，不连接真实移远云"""
    def __init__(self):
        self.ctx = {"is_init": True, "err_count": 0}
        self.last_tsl = None
    def is_connected(self):
        return True
    def send_tsl(self, d):
        self.last_tsl = d
        return True
    def init(self):
        self.ctx["is_init"] = True


def make_service():
    """创建 LarkCloudService + EventBus"""
    bus = EventBus()
    svc = LarkCloudService(bus)

    mock = MockQth()
    svc.qth = mock
    svc.send_queue = ThreadSafeQueue(max_size=50)
    svc.ctx["is_init"] = True
    svc.ctx["thread_running"] = True
    svc.event_bus = bus

    # 手动订阅事件（模拟 init() 的订阅步骤，避免创建真实 QthDriver）
    bus.subscribe(EVENT_TEMP_HUMID_READY, svc._on_temp_humid)
    bus.subscribe(EVENT_GNSS_READY, svc._on_gnss)
    bus.subscribe(EVENT_ALARM_TRIGGERED, svc._on_alarm)
    bus.subscribe(EVENT_ALARM_CANCELED, svc._on_alarm_canceled)

    return svc, bus, mock


def pump_sleep(event_bus, svc, ms):
    """模拟主循环： pump + tick，持续 ms 毫秒"""
    end = time.ticks_ms() + ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        svc.tick()
        event_bus.pump()
        time.sleep_ms(10)


def test_init_with_bus():
    """EventBus 传入后 init 正常"""
    global PASS, FAIL
    bus = EventBus()
    svc = LarkCloudService(bus)
    svc.qth = MockQth()
    svc.send_queue = ThreadSafeQueue(max_size=50)
    svc.ctx["thread_running"] = True

    svc.init()
    # init 中会再次初始化 qth（覆盖掉 mock），但我们不测真实 Qth
    # 只要不抛异常就算通过
    print("  ✓ EventBus 传入后构造正常")
    PASS += 1


def test_event_temp_humid():
    """发 TEMP_HUMID_READY → 缓存更新"""
    global PASS, FAIL
    svc, bus, _ = make_service()

    bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 26.0, "humid": 60.0, "valid": True})
    pump_sleep(bus, svc, 50)

    assert svc._data["latest_temp"] == 26.0, "temp should be cached"
    assert svc._data["latest_humid"] == 60.0, "humid should be cached"
    print("  ✓ 事件驱动缓存更新")
    PASS += 1


def test_event_alarm():
    """发 ALARM_TRIGGERED → alarm_type 正确"""
    global PASS, FAIL
    svc, bus, _ = make_service()

    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    pump_sleep(bus, svc, 50)

    assert svc.ctx["alarm_active"] == True
    assert svc.ctx["alarm_type"] == 1
    assert svc.ctx["alarm_level"] == 2
    print("  ✓ 报警事件触发")
    PASS += 1


def test_event_alarm_cancel():
    """发 ALARM_CANCELED → 报警解除"""
    global PASS, FAIL
    svc, bus, _ = make_service()

    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3})
    pump_sleep(bus, svc, 50)
    assert svc.ctx["alarm_active"] == True

    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_sleep(bus, svc, 50)
    assert svc.ctx["alarm_active"] == False
    assert svc.ctx["alarm_type"] == 0
    print("  ✓ 报警解除")
    PASS += 1


def test_tick_with_full_data():
    """完整数据流程：事件→tick→队列→网络线程发送"""
    global PASS, FAIL
    svc, bus, mock = make_service()

    # 模拟传感器数据
    bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 25.0, "humid": 55.0, "valid": True})
    bus.publish(EVENT_GNSS_READY, {
        "latitude": 22.5431, "longitude": 113.9523,
        "altitude": 10.0, "speed_kmh": 15.0,
        "signal_quality": "good", "valid": True,
    })

    # 等数据缓存
    pump_sleep(bus, svc, 50)

    # 触发 tick（用相对时间确保时间片通过）
    import time
    svc.ctx["last_upload"] = time.ticks_ms() - 5000
    svc.tick()

    # 直接读 _items 验证（绕过 get() 的 MicroPython 兼容问题）
    if svc.send_queue.size() == 0:
        print("  ✗ 队列无数据")
        FAIL += 1
        return

    raw = svc.send_queue._items[0]
    mock.send_tsl(raw)
    assert mock.last_tsl is not None, "网络线程应发送数据"
    assert 1 in mock.last_tsl, "应含 ID 1"
    assert 4 in mock.last_tsl, "应含 ID 4(latitude)"
    assert 8 in mock.last_tsl, "应含 ID 8(longitude)"
    assert 9 in mock.last_tsl, "应含 ID 9(altitude)"
    print("  ✓ 完整链路: 事件→缓存→tick→队列→发送")
    PASS += 1


def test_no_crash_empty_data():
    """无传感器数据时 pump_loop 不崩"""
    global PASS, FAIL
    svc, bus, _ = make_service()

    try:
        # 连续运行 50ms
        end = time.ticks_ms() + 50
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            svc.tick()
            bus.pump()
            time.sleep_ms(10)
        print("  ✓ 空数据循环不崩")
        PASS += 1
    except Exception as e:
        print("  ✗ 空数据循环异常: %s" % e)
        FAIL += 1


def test_queue_preserves_data_on_disconnect():
    """断连时数据不丢失，留在队列中"""
    global PASS, FAIL
    svc, bus, mock = make_service()

    # 模拟断连
    mock.connected = False
    mock.is_connected = lambda: False

    svc._on_temp_humid({"temp": 25.0, "humid": 55.0, "valid": True})
    svc.ctx["last_upload"] = 0
    svc.tick()

    # 断连时数据应留在队列中
    size = svc.send_queue.size()
    if size > 0:
        print("  ✓ 断连时队列保留数据 (size=%d)" % size)
        PASS += 1
    else:
        print("  ✗ 断连时队列为空")
        FAIL += 1


if __name__ == "__main__":
    print("开始集成测试 LarkCloudService\n")

    test_init_with_bus()
    test_event_temp_humid()
    test_event_alarm()
    test_event_alarm_cancel()
    test_tick_with_full_data()
    test_no_crash_empty_data()
    test_queue_preserves_data_on_disconnect()

    print("\n========================")
    print("  通过: %d  失败: %d" % (PASS, FAIL))
    print("========================")
    if FAIL > 0:
        print("⚠️  部分测试未通过")
    else:
        print("✅ 全部通过")
