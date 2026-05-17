"""
brief CloudService 单模块测试（纯 fake 数据）
note 不依赖真实传感器、不启动网络线程
     只验证事件回调逻辑 + JSON 拼装 + 骑行扩展计算
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
    """_on_gnss 有效定位 → latest_gnss 更新"""
    svc, _ = make_service()
    svc._on_gnss({"latitude": 22.5431, "longitude": 113.9523,
                  "altitude": 15.0, "speed_kmh": 25.0,
                  "signal_quality": "good", "valid": True})
    g = svc._data["latest_gnss"]
    assert g["lat"] == 22.5431
    assert g["lon"] == 113.9523
    assert g["speed_kmh"] == 25.0
    print("  OK GNSS 缓存")


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
    assert data["Temp"] is None
    assert data["Humi"] is None
    assert data["G-Sensor"] is None
    assert data["GNSS"] is None
    print("  OK 初始 null")


def test_alarm_collision():
    """_on_alarm collision → collision_count++ + JSON 入队"""
    svc, _ = make_service()
    svc._on_alarm({"alarm_type": "collision", "level": 2})
    assert svc._data["collision_count"] == 1
    assert svc.send_queue.size() == 1
    print("  OK 碰撞报警入队")


def test_alarm_sos():
    """_on_alarm sos → collision_count 不变"""
    svc, _ = make_service()
    svc._on_alarm({"alarm_type": "sos", "level": 3})
    assert svc._data["collision_count"] == 0
    assert svc.send_queue.size() == 1
    print("  OK SOS 报警入队")


def test_alarm_with_gnss():
    """报警时附加上次 GPS 位置"""
    svc, _ = make_service()
    svc._data["latest_gnss"] = {"lat": 22.54, "lon": 113.95}
    svc._on_alarm({"alarm_type": "collision", "level": 2})
    import ujson
    data = ujson.loads(svc.send_queue.get(timeout_ms=100))
    assert data["location"]["lat"] == 22.54
    assert data["location"]["lon"] == 113.95
    print("  OK 报警附带 GPS")


def test_alarm_without_gnss():
    """报警时无 GPS → location 为 null"""
    svc, _ = make_service()
    svc._on_alarm({"alarm_type": "sos", "level": 3})
    import ujson
    data = ujson.loads(svc.send_queue.get(timeout_ms=100))
    assert data["location"] is None
    print("  OK 无 GPS 时报警 location=null")


def test_haversine():
    """Haversine 距离计算正确（赤道 1 度 ≈ 111km）"""
    svc, _ = make_service()
    d = svc._haversine(0, 0, 1, 0)
    assert abs(d - 111.19) < 1.0, "Haversine 误差过大: %s" % d
    print("  OK Haversine 距离")


def test_gps_track_max():
    """gps_track 超上限自动丢弃最旧"""
    svc, _ = make_service()
    svc.cfg["gps_track_max"] = 3
    for i in range(5):
        svc._on_gnss({"latitude": float(i), "longitude": float(i),
                      "altitude": 0.0, "speed_kmh": 0.0,
                      "signal_quality": "good", "valid": True})
    assert len(svc._data["gps_track"]) == 3, "应保留 3 个点"
    assert svc._data["gps_track"][0]["lat"] == 2.0, "应丢弃点 0 和 1"
    print("  OK GPS 轨迹上限")


def test_distance_accumulation():
    """连续两次 _on_gnss → total_distance 累加"""
    svc, _ = make_service()
    svc._on_gnss({"latitude": 0, "longitude": 0,
                  "altitude": 0, "speed_kmh": 0,
                  "signal_quality": "good", "valid": True})
    svc._on_gnss({"latitude": 1, "longitude": 0,
                  "altitude": 0, "speed_kmh": 0,
                  "signal_quality": "good", "valid": True})
    assert svc._data["total_distance"] > 110, "距离应约 111km"
    print("  OK 距离累加")


def test_max_speed():
    """连续两次 _on_gnss → max_speed 取最大值"""
    svc, _ = make_service()
    svc._on_gnss({"latitude": 0, "longitude": 0,
                  "altitude": 0, "speed_kmh": 15.0,
                  "signal_quality": "good", "valid": True})
    svc._on_gnss({"latitude": 1, "longitude": 0,
                  "altitude": 0, "speed_kmh": 35.0,
                  "signal_quality": "good", "valid": True})
    assert svc._data["max_speed"] == 35.0
    print("  OK 最大速度")


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
        ("alarm collision", test_alarm_collision),
        ("alarm SOS", test_alarm_sos),
        ("alarm with GPS", test_alarm_with_gnss),
        ("alarm no GPS", test_alarm_without_gnss),
        ("Haversine", test_haversine),
        ("GPS track max", test_gps_track_max),
        ("distance accumulation", test_distance_accumulation),
        ("max speed", test_max_speed),
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
