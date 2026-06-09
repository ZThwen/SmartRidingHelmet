"""
brief LBSDriver 单模块测试（纯 fake 数据）
note 不依赖真实 quectel.LBS 硬件，使用 Fake 对象记录调用
执行: 上传到板子运行 python test_lbs_unit.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_LBS_READY
from Drivers.sensor.LBS import LBSDriver


class FakeLBS:
    """模拟 quectel.LBS"""
    def __init__(self, result=None):
        self.calls = []
        self._result = result
    def get_location(self, timeout_ms):
        self.calls.append(("get_location", timeout_ms))
        return self._result
    def deinit(self):
        self.calls.append(("deinit",))


def make_driver(loc_result=None):
    """创建 LBSDriver + EventBus，注入 FakeLBS"""
    bus = EventBus()
    drv = LBSDriver(bus)
    drv._lbs = FakeLBS(loc_result)
    drv.ctx["is_init"] = True
    return drv, bus


# ==================== 测试用例 ====================

def test_get_location_success():
    """定位成功 → 发布 EVENT_LBS_READY"""
    drv, bus = make_driver({"latitude": 31.84, "longitude": 117.24, "accuracy": 4400.0, "status": 0})
    captured = []
    bus.subscribe(EVENT_LBS_READY, lambda p: captured.append(p))
    drv._do_positioning()
    bus.pump()
    assert len(captured) == 1
    assert captured[0]["latitude"] == 31.84
    assert captured[0]["longitude"] == 117.24
    assert captured[0]["accuracy"] == 4400.0
    assert captured[0]["source"] == "lbs"
    assert drv.ctx["is_positioning"] == False
    assert drv._data["valid"] == True
    print("  OK get_location_success")


def test_get_location_failure():
    """定位失败 → 不发布事件，err_count +1"""
    drv, bus = make_driver(None)
    captured = []
    bus.subscribe(EVENT_LBS_READY, lambda p: captured.append(p))
    drv._do_positioning()
    bus.pump()
    assert len(captured) == 0
    assert drv.ctx["err_count"] == 1
    assert drv._data["valid"] == False
    print("  OK get_location_failure")


def test_get_location_no_coords():
    """返回值缺少坐标 → 定位失败"""
    drv, bus = make_driver({"status": 1})  # 有 status 但没坐标
    captured = []
    bus.subscribe(EVENT_LBS_READY, lambda p: captured.append(p))
    drv._do_positioning()
    bus.pump()
    assert len(captured) == 0
    assert drv.ctx["err_count"] == 1
    print("  OK get_location_no_coords")


def test_no_duplicate_positioning():
    """is_positioning=True 时不重复启动"""
    drv, bus = make_driver({"latitude": 31.84, "longitude": 117.24, "accuracy": 4400.0, "status": 0})
    drv.ctx["is_positioning"] = True
    drv._do_positioning()
    assert len(drv._lbs.calls) == 0  # 没有调用 get_location
    print("  OK no_duplicate_positioning")


def test_get_data():
    """get_data 返回定位数据"""
    drv, _ = make_driver()
    drv._data["latitude"] = 31.84
    drv._data["longitude"] = 117.24
    d = drv.get_data()
    assert d["latitude"] == 31.84
    assert d["longitude"] == 117.24
    assert "accuracy" in d
    assert "valid" in d
    print("  OK get_data")


def test_get_status():
    """get_status 返回模块状态"""
    drv, _ = make_driver()
    s = drv.get_status()
    assert "is_init" in s
    assert "is_positioning" in s
    assert "err_count" in s
    print("  OK get_status")


def test_deinit():
    """deinit 释放 LBS 资源"""
    drv, _ = make_driver()
    fake = drv._lbs  # 保存引用（deinit 后 _lbs 会被置 None）
    drv.deinit()
    assert ("deinit",) in fake.calls
    assert drv.ctx["is_init"] == False
    print("  OK deinit")


def test_no_event_bus():
    """无 EventBus 时不崩溃"""
    from Drivers.sensor.LBS import LBSDriver
    drv = LBSDriver(None)
    drv._lbs = FakeLBS({"latitude": 31.84, "longitude": 117.24, "accuracy": 4400.0, "status": 0})
    drv.ctx["is_init"] = True
    drv._do_positioning()
    assert drv._data["valid"] == True
    print("  OK no_event_bus")


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print(" LBSDriver 单元测试")
    print("=" * 50)

    tests = [
        test_get_location_success,
        test_get_location_failure,
        test_get_location_no_coords,
        test_no_duplicate_positioning,
        test_get_data,
        test_get_status,
        test_deinit,
        test_no_event_bus,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print("  FAIL {}: {}".format(t.__name__, e))
            failed += 1

    print("")
    print("=" * 50)
    print(" 结果: {} 通过, {} 失败".format(passed, failed))
    print("=" * 50)


if __name__ == "__main__":
    main()
