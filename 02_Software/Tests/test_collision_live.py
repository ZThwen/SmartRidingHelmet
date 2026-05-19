"""
========================================================
裸板实况碰撞检测测试
========================================================
操作说明：
  ① 轻敲板子 → 模拟轻微碰撞 (Level 1)
  ② 用力敲击 → 模拟中等碰撞 (Level 2)
  ③ 自由落体摔落 → 模拟严重碰撞 (Level 3)
  ④ 桌面平移/抖动 → 应被算法排除（不触发报警）
  按 Ctrl+C 停止测试
========================================================
[imu] ✓ 初始化成功
[collision] ✓ 初始化完成

▶ 测试运行中，请操作裸板...
--------------------------------------------------------
加速度:    9.3 m/s² ( 0.95 g) | 状态: 正常         ← 静止
加速度:   14.2 m/s² ( 1.45 g) | 状态: 正常         ← 轻移
加速度:   29.4 m/s² ( 3.00 g) | 状态: 可疑         ← 快速平移(>2.0g)

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ⚡ 碰撞事件已发布!
  EVENT: EVENT_COLLISION_DETECTED
  等级: 3 (🚨严重(3))
  加速度: 156.8 m/s² (16.0 g)
  接收方: → AlarmService (报警联动)
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

加速度:   98.0 m/s² (10.00 g) | 状态: 🚨严重(3)     ← 碰撞后 3 秒内仍显示等级
加速度:    9.8 m/s² ( 1.00 g) | 状态: 正常         ← 恢复平静brief CollisionService 裸板实况碰撞检测测试
note 连接真实 IMU 硬件，晃动、敲击或摔落裸板时实时输出：
      - 当前加速度
      - 实时碰撞状态(正常/可疑/碰撞 Level X)
      - 碰撞事件发布记录(供后期 AlarmService 集成验证)
     按 Ctrl+C 停止
"""
import time
import sys

sys.path.insert(0, "/")

from core.Event_Bus import EventBus
from core.config import EVENT_IMU_READY, EVENT_COLLISION_DETECTED, COLLISION_THRESHOLD_SUSPECT
from Drivers.sensor.imu import IMUDriver
from Modules.CollisionService import CollisionService


def _get_level_tag(level):
    return {1: "🌟轻微(1)", 2: "⚠️中等(2)", 3: "🚨严重(3)"}.get(level, "未知")


def _get_state_label(acc_g, collision_info):
    if collision_info["level"] > 0:
        duration = time.ticks_diff(time.ticks_ms(), collision_info["ts"])
        if duration < 3000:
            return _get_level_tag(collision_info["level"])
    if acc_g >= COLLISION_THRESHOLD_SUSPECT:
        return "可疑"
    return "正常"


def main():
    print("=" * 56)
    print("裸板实况碰撞检测测试")
    print("=" * 56)
    print("操作说明：")
    print("  ① 轻敲板子 → 模拟轻微碰撞 (Level 1)")
    print("  ② 用力敲击 → 模拟中等碰撞 (Level 2)")
    print("  ③ 自由落体摔落 → 模拟严重碰撞 (Level 3)")
    print("  ④ 桌面平移/抖动 → 应被算法排除（不触发报警）")
    print("  按 Ctrl+C 停止测试")
    print("=" * 56)

    event_bus = EventBus()

    # ====== 初始化 IMU 驱动 ======
    imu = IMUDriver(event_bus=event_bus)
    try:
        imu.init()
        print("[imu] ✓ 初始化成功")
    except Exception as e:
        print("[imu] ✗ 初始化失败: {}".format(e))
        print("请检查：S502开关是否在ARDU侧、LIS2DH12是否焊接正确")
        return

    # ====== 初始化碰撞检测服务 ======
    collision = CollisionService(event_bus=event_bus)
    collision.init()

    # ====== 状态跟踪变量 ======
    collision_log = []
    collision_info = {"level": 0, "ts": 0, "acc_g": 0.0}

    # ====== 订阅碰撞事件 ======
    def on_collision(payload):
        level = payload["level"]
        acc = payload["acc_total"]
        acc_g = acc / 9.8
        collision_log.append({"level": level, "acc": acc, "ts": payload["timestamp"]})
        collision_info["level"] = level
        collision_info["ts"] = payload["timestamp"]
        collision_info["acc_g"] = acc_g

        print("\n" + "!" * 56)
        print("  ⚡ 碰撞事件已发布!")
        print("  EVENT: EVENT_COLLISION_DETECTED")
        print("  等级: {} ({})".format(level, _get_level_tag(level)))
        print("  加速度: {:.1f} m/s² ({:.1f} g)".format(acc, acc_g))
        print("  接收方: → AlarmService (报警联动)")
        print("  " + "!" * 56 + "\n")

    event_bus.subscribe(EVENT_COLLISION_DETECTED, on_collision)

    # ====== 主循环：实时采集 + 判决 ======
    print("\n▶ 测试运行中，请操作裸板...")
    print("-" * 56)
    try:
        tick_count = 0
        while True:
            imu.tick()
            event_bus.pump()

            tick_count += 1
            if tick_count % 20 == 0:
                data = imu.get_data()
                if data["valid"]:
                    acc_g = data["acc_total"] / 9.8
                    state = _get_state_label(acc_g, collision_info)
                    sys.stdout.write("\r加速度: {:6.1f} m/s² ({:5.2f} g) | 状态: {}  ".format(
                        data["acc_total"], acc_g, state))

            time.sleep_ms(10)

    except KeyboardInterrupt:
        print("\n" + "=" * 56)
        status = collision.get_status()
        print("测试总结")
        print("-" * 56)
        print("累计碰撞次数: {}".format(status["collision_count"]))
        print("-" * 56)
        if collision_log:
            print("碰撞事件发布记录:")
            for i, c in enumerate(collision_log):
                print("  #{:02d} level={} | {:.1f} m/s² ({:.1f} g)".format(
                    i + 1, c["level"], c["acc"], c["acc"] / 9.8))
        else:
            print("本次测试未触发任何碰撞事件")
        print("-" * 56)
        print("集成就绪确认:")
        print("  CollisionService → EVENT_COLLISION_DETECTED → AlarmService")
        print("  事件发布路径: {} 次发送 ✓".format(len(collision_log)))
        print("=" * 56)


if __name__ == "__main__":
    main()