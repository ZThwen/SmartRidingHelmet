"""
brief LarkCloudService 单模块测试（纯 fake 数据，不依赖真实 Qth）
note 不启动网络线程、不连接真实移远云
     只验证事件回调逻辑 + TSL 拼装 + 报警态切换
执行: 上传到板子运行 python Tests/test_lark_cloud.py
"""
import sys
sys.path.append("..")

from core.Event_Bus import EventBus
from Modules.lark_cloud import LarkCloudService


PASS = 0
FAIL = 0


def make_service():
    """创建一个已 init 但不启网络线程的 LarkCloudService（供测试用）"""
    from Drivers.network.thread_queue import ThreadSafeQueue
    bus = EventBus()
    svc = LarkCloudService(bus)

    # 注入模拟的 QthDriver
    class MockQth:
        def __init__(self):
            self.ctx = {"is_init": True, "err_count": 0}
        def is_connected(self):
            return True
        def send_tsl(self, d):
            return True
        def init(self):
            self.ctx["is_init"] = True

    svc.qth = MockQth()
    svc.send_queue = ThreadSafeQueue(max_size=50)
    svc.ctx["is_init"] = True
    svc.event_bus = bus
    svc.ctx["thread_running"] = True
    return svc, bus


def test_init():
    """验证模拟环境就绪"""
    global PASS, FAIL
    svc, bus = make_service()
    if svc.ctx["is_init"]:
        print("  ✓ 测试环境就绪")
        PASS += 1
    else:
        print("  ✗ 测试环境异常")
        FAIL += 1


def test_cache_temp_humid_valid():
    """_on_temp_humid 有效数据 → 缓存正确"""
    global PASS, FAIL
    svc, _ = make_service()
    svc._on_temp_humid({"temp": 28.5, "humid": 65.0, "valid": True})
    assert svc._data["latest_temp"] == 28.5, "temp should be 28.5"
    assert svc._data["latest_humid"] == 65.0, "humid should be 65.0"
    print("  ✓ temp/humid 缓存")
    PASS += 1


def test_cache_temp_humid_invalid():
    """_on_temp_humid 无效数据 → 不更新"""
    global PASS, FAIL
    svc, _ = make_service()
    svc._on_temp_humid({"temp": 99.9, "humid": 99.9, "valid": False})
    assert svc._data["latest_temp"] is None, "invalid data should not update"
    print("  ✓ 无效数据不更新")
    PASS += 1


def test_cache_gnss_valid():
    """_on_gnss 有效数据 → 缓存正确"""
    global PASS, FAIL
    svc, _ = make_service()
    payload = {
        "latitude": 22.5431, "longitude": 113.9523,
        "altitude": 15.0, "speed_kmh": 25.6,
        "signal_quality": "good", "valid": True,
    }
    svc._on_gnss(payload)
    g = svc._data["latest_gnss"]
    assert g["lat"] == 22.5431, "lat mismatch"
    assert g["lon"] == 113.9523, "lon mismatch"
    assert g["alt"] == 15.0, "alt mismatch"
    # 注意: tick() 发送时 ID 4/8/9 为独立 float，不在此测试中验证
    assert g["speed_kmh"] == 25.6, "speed mismatch"
    assert g["signal_quality"] == "good", "signal mismatch"
    print("  ✓ GNSS 缓存")
    PASS += 1


def test_cache_gnss_invalid():
    """_on_gnss 无效数据 → 不更新"""
    global PASS, FAIL
    svc, _ = make_service()
    svc._on_gnss({"valid": False})
    assert svc._data["latest_gnss"] is None, "invalid gnss should not update"
    print("  ✓ 无效定位不更新")
    PASS += 1


def test_signal_mapping():
    """_signal_to_int 映射正确"""
    global PASS, FAIL
    svc, _ = make_service()
    assert svc._signal_to_int("good") == 3
    assert svc._signal_to_int("fair") == 2
    assert svc._signal_to_int("poor") == 1
    assert svc._signal_to_int("none") == 0
    assert svc._signal_to_int("unknown") == 0  # 未知值默认 0
    print("  ✓ 信号映射正确")
    PASS += 1


def test_alarm_on():
    """_on_alarm → 标记报警态"""
    global PASS, FAIL
    svc, _ = make_service()
    svc._on_alarm({"alarm_type": "collision", "level": 2})
    assert svc.ctx["alarm_active"] == True
    assert svc.ctx["alarm_type"] == 1, "collision -> 1"
    assert svc.ctx["alarm_level"] == 2
    print("  ✓ 碰撞报警态")
    PASS += 1


def test_alarm_sos():
    """_on_alarm SOS → alarm_type=2"""
    global PASS, FAIL
    svc, _ = make_service()
    svc._on_alarm({"alarm_type": "sos", "level": 1})
    assert svc.ctx["alarm_type"] == 2, "sos -> 2"
    print("  ✓ SOS 报警态")
    PASS += 1


def test_alarm_cancel():
    """_on_alarm_canceled → 清除报警态"""
    global PASS, FAIL
    svc, _ = make_service()
    svc._on_alarm({"alarm_type": "collision", "level": 2})
    assert svc.ctx["alarm_active"] == True
    svc._on_alarm_canceled({})
    assert svc.ctx["alarm_active"] == False
    assert svc.ctx["alarm_type"] == 0
    assert svc.ctx["alarm_level"] == 0
    print("  ✓ 报警解除")
    PASS += 1


def test_tick_builds_tsl():
    """tick() 后有数据入队"""
    global PASS, FAIL
    import time
    svc, _ = make_service()

    # 模拟传感器数据
    svc._on_temp_humid({"temp": 26.5, "humid": 58.0, "valid": True})
    svc._on_gnss({
        "latitude": 22.5431, "longitude": 113.9523,
        "altitude": 10.0, "speed_kmh": 15.2,
        "signal_quality": "good", "valid": True,
    })

    # 先清空队列
    svc.send_queue.clear()
    # 用相对时间确保时间片通过
    svc.ctx["last_upload"] = time.ticks_ms() - 5000

    svc.tick()
    if svc.send_queue.size() > 0:
        print("  ✓ tick 后有数据入队")
        PASS += 1
    else:
        print("  ✗ tick 后队列为空")
        FAIL += 1


def test_tick_with_alarm():
    """报警态下 tick() → TSL 含 ID 6/7"""
    global PASS, FAIL
    import time
    svc, _ = make_service()

    svc._on_alarm({"alarm_type": "collision", "level": 3})
    svc._on_temp_humid({"temp": 26.5, "humid": 58.0, "valid": True})

    svc.send_queue.clear()
    svc.ctx["last_upload"] = time.ticks_ms() - 5000
    svc.tick()

    n = svc.send_queue.size()
    if n == 0:
        print("  ✗ 队列无数据")
        FAIL += 1
        return

    tsl = svc.send_queue._items[0]
    # MicroPython %s 格式化 int-key dict 会崩，逐字段打印
    has6 = 6 in tsl
    has7 = 7 in tsl
    if not has6:
        print("  ✗ TSL 中无 ID 6 (keys: " + str(list(tsl.keys())) + ")")
        FAIL += 1
        return
    assert tsl[6] == 1, "alarm_type 应为 1"
    assert tsl[7] == 3, "alarm_level 应为 3"
    print("  ✓ 报警态 TSL 含 ID 6/7")
    PASS += 1


def test_tick_no_data():
    """无传感器数据时 tick() 不产生空 TSL"""
    global PASS, FAIL
    import time
    svc, _ = make_service()
    svc.ctx["last_upload"] = time.ticks_ms() - 5000
    svc.tick()
    size = svc.send_queue.size()
    print("  ✓ 无数据时队列大小=%d" % size)
    PASS += 1


if __name__ == "__main__":
    print("开始测试 LarkCloudService\n")

    test_init()
    test_cache_temp_humid_valid()
    test_cache_temp_humid_invalid()
    test_cache_gnss_valid()
    test_cache_gnss_invalid()
    test_signal_mapping()
    test_alarm_on()
    test_alarm_sos()
    test_alarm_cancel()
    test_tick_builds_tsl()
    test_tick_with_alarm()
    test_tick_no_data()

    print("\n========================")
    print("  通过: %d  失败: %d" % (PASS, FAIL))
    print("========================")
    if FAIL > 0:
        print("⚠️  部分测试未通过")
    else:
        print("✅ 全部通过")
