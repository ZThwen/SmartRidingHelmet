"""
brief CollisionService 集成环境测试
note 模拟真实主循环：直接向 EventBus 发布 EVENT_IMU_READY 模拟 IMU 数据
     CollisionService 在总线上接收并处理，验证完整的事件驱动协作链路
"""
import time
import sys

sys.path.insert(0, "/")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_IMU_READY, EVENT_COLLISION_DETECTED,
    EVENT_CONFIG_UPDATE,
)
from Modules.CollisionService import CollisionService

G = 9.8


def _publish_imu(event_bus, acc_g, timestamp, valid=True):
    acc_total = acc_g * G
    event_bus.publish(EVENT_IMU_READY, {
        "acc_x": 0.0,
        "acc_y": 0.0,
        "acc_z": acc_total,
        "acc_total": acc_total,
        "valid": valid,
        "timestamp": timestamp,
    })


def _run_loop(collision, event_bus, steps, step_ms=10):
    for _ in range(steps):
        event_bus.pump()
        collision.tick()
        time.sleep_ms(step_ms)


def test_event_flow():
    print("\n[测试1] 事件流转（IMU → CollisionService）...")
    event_bus = EventBus()
    collision = CollisionService(event_bus=event_bus)
    collision.init()

    detected_list = []

    def on_collision(payload):
        detected_list.append(dict(payload))

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

    base_ts = time.ticks_ms()
    acc_pattern = [1.0, 1.0, 1.0, 1.1, 1.0, 12.0, 5.0, 2.5, 1.5, 1.0,
                   1.0, 1.0, 1.0, 1.0, 1.0]
    for i, g in enumerate(acc_pattern):
        _publish_imu(event_bus, g, base_ts + i * 100)

    _run_loop(collision, event_bus, 20)

    if len(detected_list) == 1:
        p = detected_list[0]
        ok = ("acc_total" in p and "level" in p and "timestamp" in p
              and 1 <= p["level"] <= 3)
        print("  ✓ 收到碰撞事件 | level={} | acc_total={:.1f}m/s²".format(
            p["level"], p["acc_total"]))
        return ok
    else:
        print("  ✗ 期望 1 次碰撞, 实际 {}".format(len(detected_list)))
        return False


def test_false_positive_rejection():
    print("\n[测试2] 误报排除（减速带窄脉冲）...")
    event_bus = EventBus()
    collision = CollisionService(event_bus=event_bus)
    collision.init()

    detected_list = []

    def on_collision(payload):
        detected_list.append(dict(payload))

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

    base_ts = time.ticks_ms()
    acc_pattern = [1.0, 1.0, 1.0, 1.0, 3.5, 1.0, 1.0, 1.0, 1.0, 1.0]
    for i, g in enumerate(acc_pattern):
        _publish_imu(event_bus, g, base_ts + i * 100)

    _run_loop(collision, event_bus, 15)

    if len(detected_list) == 0:
        print("  ✓ 减速带未被误判为碰撞")
        return True
    else:
        print("  ✗ 减速带被误判为碰撞 {} 次".format(len(detected_list)))
        return False


def test_config_update():
    print("\n[测试3] 配置动态更新...")
    event_bus = EventBus()
    collision = CollisionService(event_bus=event_bus)
    collision.init()

    old = collision.cfg["threshold_suspect"]
    event_bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "collision",
        "threshold_suspect": 3.5,
    })
    event_bus.pump()
    new = collision.cfg["threshold_suspect"]
    ok = abs(new - 3.5) < 0.01
    if ok:
        print("  ✓ threshold_suspect: {:.1f} → {:.1f}".format(old, new))
    else:
        print("  ✗ 配置更新失败: 期望 3.5, 实际 {:.1f}".format(new))

    event_bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "collision",
        "threshold_suspect": old,
    })
    event_bus.pump()
    return ok


def test_config_update_reflects_behavior():
    print("\n[测试4] 配置更新影响行为...")
    event_bus = EventBus()
    collision = CollisionService(event_bus=event_bus)
    collision.init()

    detected_list = []

    def on_collision(payload):
        detected_list.append(dict(payload))

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

    event_bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "collision",
        "threshold_confirmed": 20.0,
        "threshold_high": 15.0,
        "threshold_likely": 10.0,
        "threshold_suspect": 8.0,
    })
    event_bus.pump()

    base_ts = time.ticks_ms()
    for i, g in enumerate([1.0, 1.0, 1.0, 5.0, 3.0, 2.0, 1.0, 1.0]):
        _publish_imu(event_bus, g, base_ts + i * 100)

    _run_loop(collision, event_bus, 12)

    if len(detected_list) == 0:
        print("  ✓ 阈值调高后 5g 不再触发碰撞")
        return True
    else:
        print("  ✗ 阈值调高后仍触发 {} 次碰撞".format(len(detected_list)))
        return False


def test_continuous_stability():
    print("\n[测试5] 持续运行稳定性（5秒）...")
    event_bus = EventBus()
    collision = CollisionService(event_bus=event_bus)
    collision.init()

    detected_count = [0]

    def on_collision(payload):
        detected_count[0] += 1

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

    base_ts = time.ticks_ms()
    duration_ms = 5000
    step_ms = 10
    steps = duration_ms // step_ms

    for i in range(steps):
        ts = base_ts + i * step_ms
        cycle = i % 30
        if cycle == 20:
            _publish_imu(event_bus, 16.0, ts)
        else:
            _publish_imu(event_bus, 1.0 + (cycle % 5) * 0.2, ts)

        event_bus.pump()
        collision.tick()
        if i % 100 == 0:
            time.sleep_ms(step_ms * 10)

    print("  ✓ 运行 {} 步完成, 触发 {} 次碰撞 (系统持续运行正常)".format(
        steps, detected_count[0]))
    status = collision.get_status()
    print("  collision_count={}, is_init={}".format(
        status["collision_count"], status["is_init"]))
    return detected_count[0] >= 1 and status["is_init"] is True


def test_cooldown():
    print("\n[测试6] 防重复触发...")
    event_bus = EventBus()
    collision = CollisionService(event_bus=event_bus)
    collision.init()

    detected_list = []

    def on_collision(payload):
        detected_list.append(dict(payload))

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

    base_ts = time.ticks_ms()
    pulses = [
        (1.0, base_ts + 0 * 100),
        (1.0, base_ts + 1 * 100),
        (12.0, base_ts + 2 * 100),
        (5.0, base_ts + 3 * 100),
        (1.0, base_ts + 4 * 100),
        (1.0, base_ts + 5 * 100),
        (10.0, base_ts + 6 * 100),
        (4.0, base_ts + 7 * 100),
        (1.0, base_ts + 8 * 100),
    ]
    for g, ts in pulses:
        _publish_imu(event_bus, g, ts)

    _run_loop(collision, event_bus, 15)

    if len(detected_list) == 1:
        print("  ✓ 第二次碰撞被抑制 (仅触发 {} 次)".format(len(detected_list)))
        return True
    elif len(detected_list) == 0:
        print("  ⚠ 未触发任何碰撞 (需检查时间戳对齐)")
        return False
    else:
        print("  ⚠ 防重复未完全生效 (触发了 {} 次)".format(len(detected_list)))
        return False


def test_imu_error_isolation():
    print("\n[测试7] 异常隔离（无效数据 + 异常峰值）...")
    event_bus = EventBus()
    collision = CollisionService(event_bus=event_bus)
    collision.init()

    def on_collision(payload):
        pass

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

    base_ts = time.ticks_ms()
    edge_cases = [
        (0.0, True),
        (999.0, True),
        (1.0, False),
        (-5.0, True),
        (0.001, True),
        (2.0, False),
    ]
    for i, (g, valid) in enumerate(edge_cases):
        _publish_imu(event_bus, g, base_ts + i * 100, valid=valid)

    try:
        _run_loop(collision, event_bus, 15)
        status = collision.get_status()
        print("  ✓ 所有异常数据处理完毕, 系统未崩溃")
        print("  collision_count={}, is_init={}".format(
            status["collision_count"], status["is_init"]))
        return status["is_init"] is True
    except Exception as e:
        print("  ✗ 系统异常崩溃: {}".format(e))
        return False


def test_collision_levels():
    print("\n[测试8] 碰撞等级准确性...")
    results = {}

    for desc, peak_g, expected_level in [
        ("轻微(4.5g)", 4.5, 1),
        ("中等(7.0g)", 7.0, 2),
        ("严重(14g)", 14.0, 3),
    ]:
        event_bus = EventBus()
        collision = CollisionService(event_bus=event_bus)
        collision.init()

        captured = []
        def on_collision(payload):
            captured.append(dict(payload))
        event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

        base_ts = time.ticks_ms()
        for i in range(5):
            _publish_imu(event_bus, 1.0, base_ts + i * 100)
        _publish_imu(event_bus, peak_g, base_ts + 5 * 100)
        _publish_imu(event_bus, peak_g * 0.5, base_ts + 6 * 100)
        for i in range(7, 11):
            _publish_imu(event_bus, 1.2, base_ts + i * 100)

        _run_loop(collision, event_bus, 17)

        actual = captured[0]["level"] if captured else None
        ok = actual == expected_level
        results[desc] = (ok, actual, expected_level)
        print("  {}: 期望 level={}, 实际 level={}  {}".format(
            desc, expected_level, actual, "✓" if ok else "✗"))

    return all(ok for ok, _, _ in results.values())


def main():
    print("=" * 56)
    print("CollisionService 集成环境测试")
    print("=" * 56)

    tests = [
        ("事件流转",         test_event_flow),
        ("误报排除",         test_false_positive_rejection),
        ("配置更新",         test_config_update),
        ("配置影响行为",     test_config_update_reflects_behavior),
        ("持续运行稳定性",   test_continuous_stability),
        ("防重复触发",       test_cooldown),
        ("异常隔离",         test_imu_error_isolation),
        ("碰撞等级准确性",   test_collision_levels),
    ]

    results = []
    for name, func in tests:
        try:
            ok = func()
        except Exception as e:
            print("  ‼ 测试异常: {}".format(e))
            ok = False
        results.append((name, ok))

    print("\n" + "=" * 56)
    passed = 0
    for name, ok in results:
        mark = "✓ 通过" if ok else "✗ 失败"
        print("  {}: {}".format(name, mark))
        if ok:
            passed += 1
    print("=" * 56)
    print("总分: {}/{}".format(passed, len(results)))
    if passed == len(results):
        print("✅ 集成测试全部通过")
    else:
        print("⚠  {} 项未通过，请检查".format(len(results) - passed))
    print("=" * 56)


if __name__ == "__main__":
    main()
