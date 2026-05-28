"""
brief CloudService 单模块测试（纯 fake 数据）
note 不依赖真实传感器、不启动网络线程
     只验证事件回调逻辑 + JSON 拼装 + 报警态切换
执行: 上传到板子运行 python test_cloud_service.py
"""
import sys
sys.path.append("..")

from core.Event_Bus import EventBus
from Modules.cloud_service import CloudService


def make_service():
    """创建一个已 init 但不启网络线程的 CloudService（供测试用）"""
    from Drivers.network.thread_queue import ThreadSafeQueue
    bus = EventBus()
    svc = CloudService(bus)
    svc.send_queue = ThreadSafeQueue(max_size=100)
    svc.ctx["is_init"] = True
    return svc, bus


def test_cache_temp_humid_valid():
    """_on_temp_humid 有效数据 → 缓存正确"""
    svc, _ = make_service()
    svc._on_temp_humid({"temp": 28.5, "humid": 65.0, "valid": True})
    assert svc._data["latest_temp"] == 28.5, "temp should be 28.5"
    assert svc._data["latest_humid"] == 65.0, "humid should be 65.0"
    print("  OK temp/humid 缓存")


def test_cache_temp_humid_invalid():
    """_on_temp_humid 无效数据 → 不更新"""
    svc, _ = make_service()
    svc._on_temp_humid({"temp": 99.9, "valid": False})
    assert svc._data["latest_temp"] is None, "invalid data should not update"
    print("  OK temp/humid 无效不更新")


def test_cache_imu_valid():
    """_on_imu 有效数据 → 缓存正确"""
    svc, _ = make_service()
    svc._on_imu({"acc_x": 0.1, "acc_y": -0.2, "acc_z": 9.81,
                 "acc_total": 9.82, "valid": True})
    imu = svc._data["latest_imu"]
    assert imu["X"] == 0.1
    assert imu["Y"] == -0.2
    assert imu["total"] == 9.82
    print("  OK IMU 缓存")


def test_gnss_caches_data():
    """_on_gnss 有效定位 → latest_gnss 更新含 signal_quality"""
    svc, _ = make_service()
    svc._on_gnss({"latitude": 22.5431, "longitude": 113.9523,
                  "altitude": 15.0, "speed_kmh": 25.0,
                  "signal_quality": "good", "valid": True})
    g = svc._data["latest_gnss"]
    assert g["lat"] == 22.5431
    assert g["lon"] == 113.9523
    assert g["speed_kmh"] == 25.0
    assert g["signal_quality"] == "good"
    print("  OK GNSS 缓存含 signal_quality")


def test_gnss_invalid():
    """_on_gnss 无效 → 不更新"""
    svc, _ = make_service()
    svc._on_gnss({"valid": False})
    assert svc._data["latest_gnss"] is None, "invalid gnss not update"
    print("  OK GNSS 无效不更新")


def test_tick_produces_json():
    """tick() 首次调用 → JSON 入队"""
    svc, _ = make_service()
    svc._data["latest_temp"] = 28.5
    svc._data["latest_humid"] = 65.0
    svc.tick()
    assert svc.send_queue.size() == 1, "tick 应入队一条"
    print("  OK tick 入队")


def test_tick_interval_guard():
    """tick() 连续两次（未到间隔）→ 不入队"""
    svc, _ = make_service()
    svc._data["latest_temp"] = 28.5
    svc.tick()  # 第一次
    svc.tick()  # 第二次（时间未变，应跳过）
    assert svc.send_queue.size() == 1, "未到间隔不应入队"
    print("  OK tick 间隔控制")


def test_tick_all_nulls():
    """未收到任何传感器时 tick → JSON 字段均为 null"""
    svc, _ = make_service()
    svc.ctx["last_upload"] = 0  # 重置确保触发
    svc.tick()
    import ujson
    data = ujson.loads(svc.send_queue.get(timeout_ms=100))
    assert data["type"] == "normal"
    assert data["temp"] is None
    assert data["humidity"] is None
    assert data["speed_kmh"] is None
    assert data["latitude"] is None
    assert data["longitude"] is None
    assert data["altitude"] is None
    assert data["signal_quality"] is None
    print("  OK 初始 null 字段 + type=normal")


def test_tick_normal_payload():
    """tick() 正常态 → JSON 含 type=normal + 蛇形字段"""
    svc, _ = make_service()
    svc._data["latest_temp"] = 26.5
    svc._data["latest_humid"] = 60.0
    svc._data["latest_gnss"] = {
        "lat": 22.54, "lon": 113.95, "alt": 10.0,
        "speed_kmh": 15.0, "signal_quality": "good",
    }
    svc.ctx["last_upload"] = 0
    svc.tick()
    import ujson
    data = ujson.loads(svc.send_queue.get(timeout_ms=100))
    assert data["type"] == "normal"
    assert data["temp"] == 26.5
    assert data["humidity"] == 60.0
    assert data["speed_kmh"] == 15.0
    assert data["latitude"] == 22.54
    assert data["longitude"] == 113.95
    assert data["altitude"] == 10.0
    assert data["signal_quality"] == "good"
    print("  OK 正常态 payload 格式正确")


def test_alarm_sets_flag():
    """_on_alarm → alarm_active=True + 缓存报警信息"""
    svc, _ = make_service()
    svc._data["latest_gnss"] = {"lat": 22.54, "lon": 113.95, "alt": 10.0}
    svc._on_alarm({"alarm_type": "collision", "level": 2})
    assert svc.ctx["alarm_active"] is True
    assert svc.ctx["alarm_info"]["alarm_type"] == "collision"
    assert svc.ctx["alarm_info"]["level"] == 2
    assert svc.ctx["alarm_info"]["lat"] == 22.54
    # 不直接入队
    assert svc.send_queue.size() == 0
    print("  OK 报警设标志 + 缓存 (不入队)")


def test_alarm_sos():
    """_on_alarm sos → alarm_type=sos"""
    svc, _ = make_service()
    svc._on_alarm({"alarm_type": "sos", "level": 3})
    assert svc.ctx["alarm_active"] is True
    assert svc.ctx["alarm_info"]["alarm_type"] == "sos"
    print("  OK SOS 报警标志")


def test_alarm_canceled():
    """_on_alarm_canceled → alarm_active=False"""
    svc, _ = make_service()
    svc.ctx["alarm_active"] = True
    svc.ctx["alarm_info"] = {"alarm_type": "collision", "level": 2}
    svc._on_alarm_canceled(None)
    assert svc.ctx["alarm_active"] is False
    assert svc.ctx["alarm_info"] == {}
    print("  OK 报警解除")


def test_tick_alarm_payload():
    """报警态下 tick() → 发 type=alarm 的 payload"""
    svc, _ = make_service()
    svc.ctx["alarm_active"] = True
    svc.ctx["alarm_info"] = {
        "alarm_type": "collision", "level": 2,
        "lat": 22.54, "lon": 113.95, "alt": 10.0,
    }
    svc.ctx["last_upload"] = 0
    svc.tick()
    import ujson
    data = ujson.loads(svc.send_queue.get(timeout_ms=100))
    assert data["type"] == "alarm"
    assert data["alarm_type"] == "collision"
    assert data["level"] == 2
    assert data["latitude"] == 22.54
    assert data["longitude"] == 113.95
    assert data["altitude"] == 10.0
    print("  OK 报警态 payload（持续发送格式）")


def test_alarm_without_gnss():
    """报警时无 GPS → lat/lon 为 None"""
    svc, _ = make_service()
    svc._on_alarm({"alarm_type": "sos", "level": 3})
    assert svc.ctx["alarm_info"]["lat"] is None
    assert svc.ctx["alarm_info"]["lon"] is None
    print("  OK 无 GPS 时报警 lat/lon=None")


def test_alarm_cancel_resumes_normal():
    """报警解除后 tick() → 恢复 type=normal"""
    svc, _ = make_service()
    svc._data["latest_temp"] = 26.5
    svc.ctx["last_upload"] = 0

    # 报警态
    svc.ctx["alarm_active"] = True
    svc.ctx["alarm_info"] = {"alarm_type": "collision", "level": 2}
    svc.tick()
    import ujson
    data = ujson.loads(svc.send_queue.get(timeout_ms=100))
    assert data["type"] == "alarm"

    # 解除后
    svc._on_alarm_canceled(None)
    svc.ctx["last_upload"] = 0
    svc.tick()
    data2 = ujson.loads(svc.send_queue.get(timeout_ms=100))
    assert data2["type"] == "normal"
    assert data2["temp"] == 26.5
    print("  OK 报警解除后恢复 normal")


def main():
    print("=== CloudService Unit Test ===\n")
    tests = [
        ("temp/humid cache", test_cache_temp_humid_valid),
        ("temp/humid invalid", test_cache_temp_humid_invalid),
        ("IMU cache", test_cache_imu_valid),
        ("GNSS cache", test_gnss_caches_data),
        ("GNSS invalid", test_gnss_invalid),
        ("tick produce JSON", test_tick_produces_json),
        ("tick interval guard", test_tick_interval_guard),
        ("all nulls", test_tick_all_nulls),
        ("normal payload format", test_tick_normal_payload),
        ("alarm sets flag", test_alarm_sets_flag),
        ("alarm SOS", test_alarm_sos),
        ("alarm canceled", test_alarm_canceled),
        ("alarm payload", test_tick_alarm_payload),
        ("alarm no GPS", test_alarm_without_gnss),
        ("alarm cancel resume normal", test_alarm_cancel_resumes_normal),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            import sys
            print("  X %s: %s" % (name, e))
    print("\nResult: %s/%s passed" % (passed, len(tests)))


if __name__ == "__main__":
    main()
