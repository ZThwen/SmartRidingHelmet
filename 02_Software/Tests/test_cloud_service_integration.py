"""
brief CloudService 集成测试（EventBus + 事件注入）
note 不依赖真实传感器模块，手动注入 fake 事件验证链路
      通过 make_service() 手动创建 queue + 订阅事件，不调 init()
      避免启动网络线程（无硬件时 init 会抛异常）
执行: 上传到板子运行 python test_cloud_integration.py
"""
import sys
sys.path.append("..")

from core.Event_Bus import EventBus
from Drivers.network.thread_queue import ThreadSafeQueue
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_IMU_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED, EVENT_CONFIG_UPDATE,
)
from Modules.cloud_service import CloudService


def make_service():
    """创建 CloudService 实例并手动接线（不调 init，不启动硬件线程）"""
    bus = EventBus()
    svc = CloudService(bus)
    svc.send_queue = ThreadSafeQueue(max_size=100)
    # 手动订阅回调（模拟 init 中的行为）
    bus.subscribe(EVENT_TEMP_HUMID_READY, svc._on_temp_humid)
    bus.subscribe(EVENT_IMU_READY, svc._on_imu)
    bus.subscribe(EVENT_GNSS_READY, svc._on_gnss)
    bus.subscribe(EVENT_ALARM_TRIGGERED, svc._on_alarm)
    bus.subscribe(EVENT_ALARM_CANCELED, svc._on_alarm_canceled)
    bus.subscribe(EVENT_CONFIG_UPDATE, svc._on_config_update)
    svc.ctx["is_init"] = True
    return svc, bus


def test_event_temp_humid_flow():
    """注入 TEMP_HUMID_READY → 缓存更新"""
    svc, bus = make_service()
    bus.publish(EVENT_TEMP_HUMID_READY, {
        "temp": 28.0, "humid": 60.0, "valid": True,
    })
    bus.pump()
    assert svc._data["latest_temp"] == 28.0
    assert svc._data["latest_humid"] == 60.0
    print("  OK temp/humid 事件链路")


def test_event_imu_flow():
    """注入 IMU_READY → 缓存更新"""
    svc, bus = make_service()
    bus.publish(EVENT_IMU_READY, {
        "acc_x": 0.1, "acc_y": -0.2, "acc_z": 9.81,
        "acc_total": 9.82, "valid": True,
    })
    bus.pump()
    assert svc._data["latest_imu"]["total"] == 9.82
    print("  OK IMU 事件链路")


def test_event_gnss_flow():
    """注入 GNSS_READY → GPS 缓存（含 signal_quality）"""
    svc, bus = make_service()
    bus.publish(EVENT_GNSS_READY, {
        "latitude": 22.54, "longitude": 113.95,
        "altitude": 15.0, "speed_kmh": 25.0,
        "signal_quality": "good", "valid": True,
    })
    bus.pump()
    g = svc._data["latest_gnss"]
    assert g["lat"] == 22.54
    assert g["speed_kmh"] == 25.0
    assert g["signal_quality"] == "good"
    print("  OK GNSS 事件链路（含信号质量）")


def test_tick_queues_data():
    """tick() 调用后队列有数据"""
    svc, _ = make_service()
    svc._data["latest_temp"] = 25.0
    svc._data["latest_humid"] = 55.0
    svc.tick()
    assert svc.send_queue.size() >= 1
    print("  OK tick 入队链路")


def test_event_alarm_flow():
    """注入 ALARM_TRIGGERED → alarm_active=True"""
    svc, bus = make_service()
    svc._data["latest_gnss"] = {"lat": 22.54, "lon": 113.95}
    bus.publish(EVENT_ALARM_TRIGGERED, {
        "alarm_type": "collision", "level": 2,
    })
    bus.pump()
    assert svc.ctx["alarm_active"] is True
    assert svc.ctx["alarm_info"]["alarm_type"] == "collision"
    # 不入队（由 tick 持续发送）
    assert svc.send_queue.size() == 0
    print("  OK 报警事件链路（设标志，不入队）")


def test_event_alarm_cancel_flow():
    """注入 ALARM_CANCELED → alarm_active=False"""
    svc, bus = make_service()
    svc.ctx["alarm_active"] = True
    svc.ctx["alarm_info"] = {"alarm_type": "collision", "level": 2}
    bus.publish(EVENT_ALARM_CANCELED, {})
    bus.pump()
    assert svc.ctx["alarm_active"] is False
    print("  OK 报警取消事件链路")


def test_config_update_flow():
    """注入 CONFIG_UPDATE → cfg 参数更新"""
    svc, bus = make_service()
    bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "cloud",
        "upload_interval_ms": 5000,
    })
    bus.pump()
    assert svc.cfg["upload_interval_ms"] == 5000
    print("  OK 配置更新链路")


def main():
    print("=== CloudService Integration Test ===\n")
    tests = [
        ("temp/humid event flow", test_event_temp_humid_flow),
        ("IMU event flow", test_event_imu_flow),
        ("GNSS event flow", test_event_gnss_flow),
        ("tick queues data", test_tick_queues_data),
        ("alarm event flow", test_event_alarm_flow),
        ("alarm cancel flow", test_event_alarm_cancel_flow),
        ("config update flow", test_config_update_flow),
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
