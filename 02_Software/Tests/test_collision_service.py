"""
brief CollisionService 单模块测试脚本
note 纯逻辑服务，通过模拟 EVENT_IMU_READY 事件输入验证碰撞检测算法
     覆盖 11 种骑行场景：正常骑行、减速带、跳跃落地、碎石路、
     正面撞击、侧面撞击、侧滑摔倒、追尾碰撞、急刹翻车、防重复、无效数据
"""
import sys
import time

sys.path.insert(0, "/")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_IMU_READY, EVENT_COLLISION_DETECTED, EVENT_CONFIG_UPDATE,
    GRAVITY,
)
from Modules.CollisionService import CollisionService

G = 9.8
SIM_SAMPLE_MS = 100


def _sim_ts(base, offset_idx):
    return base + offset_idx * SIM_SAMPLE_MS


def _gen_samples(values_g, base_ts=1000000):
    return [
        {"acc_total": v * G, "valid": True, "timestamp": _sim_ts(base_ts, i)}
        for i, v in enumerate(values_g)
    ]


def _feed_samples(collision, event_bus, samples):
    results = []
    captured = {"detected": None}

    def on_collision(payload):
        captured["detected"] = payload

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

    for s in samples:
        captured["detected"] = None
        event_bus.publish(EVENT_IMU_READY, {
            "acc_x": 0.0,
            "acc_y": 0.0,
            "acc_z": s["acc_total"],
            "acc_total": s["acc_total"],
            "valid": s["valid"],
            "timestamp": s["timestamp"],
        })
        event_bus.pump()
        collision.tick()
        if captured["detected"] is not None:
            results.append(dict(captured["detected"]))


    return results


def test_init():
    print("\n[测试 1] 初始化 CollisionService...")
    event_bus = EventBus()
    collision = CollisionService(event_bus=event_bus)
    try:
        collision.init()
        status = collision.get_status()
        assert status["is_init"] is True
        print("  ✓ 初始化成功, is_init=True")
        return event_bus, collision
    except Exception as e:
        print("  ✗ 初始化失败: {}".format(e))
        raise


def test_status(collision):
    print("\n[测试 2] 查询模块状态...")
    status = collision.get_status()
    data = collision.get_data()
    print("  get_status: is_init={}, power={}, collision_count={}".format(
        status["is_init"], status["power_state"], status["collision_count"]))
    print("  get_data:   status={}, last_level={}, last_peak={:.2f}".format(
        data["status"], data["last_level"], data["last_peak"]))
    assert status["is_init"] is True
    assert status["power_state"] == "ACTIVE"
    assert status["collision_count"] == 0
    print("  ✓ 状态正常")


def test_normal_riding(collision, event_bus):
    print("\n[测试 3] 正常骑行 (acc_g ≈ 0.8~1.5g, 无碰撞)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 1.1, 0.9, 1.2, 1.0, 1.1, 1.3, 1.0, 0.8, 1.1,
         1.0, 1.2, 1.1, 0.9, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) == 0:
        print("  ✓ 未触发碰撞 (正确)")
    else:
        print("  ✗ 误报 {} 次碰撞".format(len(results)))


def test_speed_bump(collision, event_bus):
    print("\n[测试 4] 过减速带 (峰值 3.5g, 窄脉冲, 应被脉冲宽度鉴别器排除)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 1.1, 1.0, 1.2, 1.0, 3.5, 1.0, 1.1, 1.0, 1.0,
         1.1, 1.0, 1.0, 1.0, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) == 0:
        print("  ✓ 减速带未被误判为碰撞 (鉴别器A生效)")
    else:
        print("  ✗ 减速带被误判为碰撞, level={}".format(results[0]["level"]))


def test_jump_land(collision, event_bus):
    print("\n[测试 5] 跳跃落地 (峰值 4.0g, 碰撞前有失重 0.5g, 应被失重前兆鉴别器排除)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 1.1, 1.0, 0.5, 1.0, 1.2, 1.0, 4.0, 2.5, 1.5,
         1.2, 1.0, 1.0, 1.0, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) == 0:
        print("  ✓ 跳跃落地未被误判为碰撞 (鉴别器B生效)")
    else:
        print("  ✗ 跳跃落地被误判为碰撞, level={}".format(results[0]["level"]))


def test_gravel_road(collision, event_bus):
    print("\n[测试 6] 碎石路连续振荡 (2.5~3.5g 多波峰, 应被振荡判别器排除)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 2.5, 3.0, 2.0, 3.5, 2.5, 3.0, 2.0, 3.5, 2.5,
         3.0, 2.0, 3.5, 2.5, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) == 0:
        print("  ✓ 碎石路未被误判为碰撞 (鉴别器C生效)")
    else:
        print("  ✗ 碎石路被误判为碰撞, level={}".format(results[0]["level"]))


def test_frontal_crash(collision, event_bus):
    print("\n[测试 7] 正面撞击 (峰值 12g, 高度疑似区间, 应判定为碰撞 Level 3)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 1.1, 1.0, 1.2, 1.0, 12.0, 5.0, 2.5, 1.5, 1.2,
         1.0, 1.0, 1.0, 1.0, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) == 1 and results[0]["level"] == 3:
        print("  ✓ 正面撞击正确识别, level=3, acc_total={:.1f}m/s²".format(
            results[0]["acc_total"]))
    elif len(results) == 1:
        print("  ⚠ 检测到碰撞但等级异常: level={} (期望 3)".format(
            results[0]["level"]))
    else:
        print("  ✗ 正面撞击漏报 (检测到 {} 次)".format(len(results)))


def test_side_crash(collision, event_bus):
    print("\n[测试 8] 侧面撞击 (峰值 6g, 脉冲较宽, 应判定为碰撞 Level 2)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 1.1, 1.0, 1.5, 3.0, 6.0, 5.5, 4.0, 2.5, 1.5,
         1.2, 1.0, 1.0, 1.0, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) == 1 and results[0]["level"] == 2:
        print("  ✓ 侧面撞击正确识别, level=2")
    elif len(results) == 1:
        print("  ⚠ 检测到碰撞但等级异常: level={} (期望 2)".format(
            results[0]["level"]))
    else:
        print("  ✗ 侧面撞击漏报或误报 (检测到 {} 次)".format(len(results)))


def test_side_slip(collision, event_bus):
    print("\n[测试 9] 侧滑摔倒 (峰值 4.5g, 宽平台, 应判定为碰撞 Level 1)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 1.1, 1.0, 2.0, 3.0, 4.5, 4.0, 3.5, 2.5, 2.0,
         1.5, 1.2, 1.0, 1.0, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) == 1 and results[0]["level"] == 1:
        print("  ✓ 侧滑摔倒正确识别, level=1")
    elif len(results) == 1:
        print("  ⚠ 检测到碰撞但等级异常: level={} (期望 1)".format(
            results[0]["level"]))
    else:
        print("  ✗ 侧滑摔倒漏报 (检测到 {} 次)".format(len(results)))


def test_rear_end(collision, event_bus):
    print("\n[测试 10] 追尾碰撞 (双脉冲: 4g → 8g, 应判定为碰撞 Level 3)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 1.1, 1.0, 4.0, 3.5, 2.0, 1.5, 1.0, 8.0, 5.0,
         3.0, 1.5, 1.0, 1.0, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) >= 1:
        max_level = max(r["level"] for r in results)
        if max_level == 3:
            print("  ✓ 追尾碰撞正确识别, 最高等级=3")
        else:
            print("  ⚠ 检测到碰撞但等级偏低: max_level={} (期望 3)".format(max_level))
    else:
        print("  ✗ 追尾碰撞漏报")


def test_brake_flip(collision, event_bus):
    print("\n[测试 11] 急刹翻车 (峰值 18g, 超过确认阈值, 直接判定 Level 3)...")
    base_ts = time.ticks_ms()
    samples = _gen_samples(
        [1.0, 1.1, 1.0, 1.2, 1.0, 18.0, 8.0, 4.0, 2.0, 1.2,
         1.0, 1.0, 1.0, 1.0, 1.0], base_ts)
    results = _feed_samples(collision, event_bus, samples)
    if len(results) == 1 and results[0]["level"] == 3:
        print("  ✓ 急刹翻车正确识别, level=3")
    elif len(results) >= 1:
        print("  ⚠ 检测到碰撞但等级异常: level={} (期望 3)".format(
            results[0]["level"]))
    else:
        print("  ✗ 急刹翻车漏报")


def test_cooldown(collision, event_bus):
    print("\n[测试 12] 防重复触发 (两次碰撞间隔 < 5000ms, 第二次应被抑制)...")
    base_ts = time.ticks_ms()
    samples1 = _gen_samples(
        [1.0, 1.1, 1.0, 1.2, 1.0, 10.0, 4.0, 2.0, 1.2, 1.0,
         1.0, 1.0, 1.0, 1.0, 1.0], base_ts)
    gap_ts = base_ts + 20 * SIM_SAMPLE_MS
    samples2 = _gen_samples(
        [1.0, 1.1, 1.0, 1.2, 1.0, 9.0, 4.0, 2.0, 1.2, 1.0,
         1.0, 1.0, 1.0, 1.0, 1.0], gap_ts)
    captured = []
    def on_collision(payload):
        captured.append(dict(payload))
    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)
    for s in samples1 + samples2:
        event_bus.publish(EVENT_IMU_READY, {
            "acc_x": 0.0, "acc_y": 0.0, "acc_z": s["acc_total"],
            "acc_total": s["acc_total"], "valid": s["valid"],
            "timestamp": s["timestamp"],
        })
        event_bus.pump()
        collision.tick()
 
    if len(captured) == 1:
        print("  ✓ 第二次碰撞被抑制 (仅触发 {} 次, 正确)".format(len(captured)))
    elif len(captured) == 0:
        print("  ⚠ 未检测到任何碰撞 (可能需要检查时间戳范围)")
    else:
        print("  ⚠ 防重复未完全生效 (触发了 {} 次)".format(len(captured)))


def test_invalid_data(collision, event_bus):
    print("\n[测试 13] 无效数据 (valid=False 的 IMU 数据, 应被直接丢弃)...")
    base_ts = time.ticks_ms()
    captured = []
    def on_collision(payload):
        captured.append(dict(payload))
    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)
    for i in range(5):
        event_bus.publish(EVENT_IMU_READY, {
            "acc_x": 0.0, "acc_y": 0.0, "acc_total": 50.0,
            "valid": False, "timestamp": _sim_ts(base_ts, i),
        })
        event_bus.pump()
    
    if len(captured) == 0:
        print("  ✓ 无效数据被正确丢弃")
    else:
        print("  ✗ 无效数据未被丢弃")


def test_config_update(collision, event_bus):
    print("\n[测试 14] 配置动态更新...")
    old_threshold = collision.cfg["threshold_suspect"]
    event_bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "collision",
        "threshold_suspect": 3.0,
    })
    event_bus.pump()
    new_threshold = collision.cfg["threshold_suspect"]
    if new_threshold == 3.0:
        print("  ✓ threshold_suspect 更新: {:.1f} → {:.1f}".format(
            old_threshold, new_threshold))
    else:
        print("  ✗ 配置更新失败: 期望 3.0, 实际 {:.1f}".format(new_threshold))
    event_bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "collision",
        "threshold_suspect": old_threshold,
    })
    event_bus.pump()


def test_get_data_status(collision, event_bus):
    print("\n[测试 15] get_data() / get_status() 接口完整性...")
    data = collision.get_data()
    for key in ("status", "last_peak", "last_level", "window_size", "timestamp"):
        assert key in data, "get_data() 缺少字段: {}".format(key)
    status = collision.get_status()
    for key in ("is_init", "power_state", "collision_count", "last_collision_ts"):
        assert key in status, "get_status() 缺少字段: {}".format(key)
    print("  ✓ 所有接口字段完整")


def test_event_payload_format(collision, event_bus):
    print("\n[测试 16] 碰撞事件 payload 格式验证...")
    base_ts = time.ticks_ms()
    captured = []

    def on_collision(payload):
        captured.append(dict(payload))

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)
    samples = _gen_samples(
        [1.0, 1.0, 1.0, 1.0, 1.0, 10.0, 4.0, 2.0, 1.0, 1.0,
         1.0, 1.0, 1.0, 1.0, 1.0], base_ts)
    for s in samples:
        event_bus.publish(EVENT_IMU_READY, {
            "acc_x": 0.0, "acc_y": 0.0, "acc_z": s["acc_total"],
            "acc_total": s["acc_total"], "valid": s["valid"],
            "timestamp": s["timestamp"],
        })
        event_bus.pump()
   
    if len(captured) >= 1:
        payload = captured[0]
        assert "acc_total" in payload, "缺少 acc_total"
        assert "level" in payload, "缺少 level"
        assert "timestamp" in payload, "缺少 timestamp"
        assert isinstance(payload["level"], int), "level 必须为 int"
        assert 1 <= payload["level"] <= 3, "level 范围 1~3"
        print("  ✓ payload 格式正确: acc_total={:.1f}, level={}, ts={}".format(
            payload["acc_total"], payload["level"], payload["timestamp"]))
    else:
        print("  ⚠ 未捕获碰撞事件, 跳过 payload 验证")


def main():
    print("=" * 60)
    print("CollisionService 单模块测试开始")
    print("=" * 60)

    event_bus, collision = test_init()
    test_status(collision)

    print("\n" + "-" * 60)
    print("误报排除测试 (正常骑行 + 3 种典型误报场景)")
    print("-" * 60)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()

    test_normal_riding(fresh_collision, fresh_bus)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_speed_bump(fresh_collision, fresh_bus)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_jump_land(fresh_collision, fresh_bus)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_gravel_road(fresh_collision, fresh_bus)

    print("\n" + "-" * 60)
    print("碰撞检测测试 (5 种真实碰撞场景)")
    print("-" * 60)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_frontal_crash(fresh_collision, fresh_bus)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_side_crash(fresh_collision, fresh_bus)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_side_slip(fresh_collision, fresh_bus)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_rear_end(fresh_collision, fresh_bus)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_brake_flip(fresh_collision, fresh_bus)

    print("\n" + "-" * 60)
    print("边界与健壮性测试")
    print("-" * 60)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_cooldown(fresh_collision, fresh_bus)

    fresh_bus = EventBus()
    fresh_collision = CollisionService(event_bus=fresh_bus)
    fresh_collision.init()
    test_invalid_data(fresh_collision, fresh_bus)

    test_get_data_status(collision, event_bus)
    test_event_payload_format(collision, event_bus)
    test_config_update(collision, event_bus)

    print("\n" + "=" * 60)
    print("CollisionService 单模块测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()