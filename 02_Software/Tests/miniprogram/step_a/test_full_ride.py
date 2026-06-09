"""
brief 完整骑行流程测试
note 合并所有功能的端到端测试
     BLE 连接 → 传感器推送 → 报警 → GPS 漂移 → 导航指令 → 结束
     板子端: 全部自动化
     小程序端: 按提示操作
"""
import sys
sys.path.append("..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_GNSS_READY, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_NAV_CMD,
)
from Modules.ble_service import BLEService
from Drivers.network.BLE import BLEDriver
from Drivers.sensor.Temp_Humid import TempHumidDriver


_LOG_PATH = "Tests/miniprogram/test_full_ride.log"
_T0 = 0


def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    line = "[%7.2fs] %s" % (elapsed / 1000.0, msg)
    print(line)
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def countdown(sec, msg):
    log("⏱ 倒计时: %ds — %s" % (sec, msg))
    for i in range(sec, 0, -1):
        log("  %ds..." % i)
        time.sleep(1)


def observe(sec, items):
    log("")
    log("⏱ 观察窗口: %ds" % sec)
    for item in items:
        log("  [ ] %s" % item)
    time.sleep(sec)


def pump_loop(bus, temp, ble_svc, duration_s, simulate_gnss=True):
    end = time.ticks_ms() + duration_s * 1000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if temp:
            temp.tick()
        ble_svc.tick()
        bus.pump()
        if simulate_gnss and tick % 20 == 0:
            lat = 22.5431 + (tick % 600) * 0.00001
            lon = 113.9523 + (tick % 600) * 0.000015
            bus.publish(EVENT_GNSS_READY, {
                "latitude": lat, "longitude": lon,
                "altitude": 10.0, "speed_kmh": 12.0,
                "signal_quality": 3, "valid": True,
            })
        tick += 1
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 完整骑行流程测试")
    print("=" * 50)

    bus = EventBus()

    # 初始化
    log("初始化...")
    try:
        temp = TempHumidDriver(event_bus=bus)
        temp.init()
        log("  ✓ Temp_Humid")
    except:
        log("  ~ Temp_Humid 不可用")
        temp = None

    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log("  ✓ BLE")
    except Exception as e:
        log("  ✗ BLE 失败: %s" % e)
        return

    # 等待连接
    countdown(10, "请在小程序点击「连接」")

    log("▶ 等待 BLE 连接...")
    wait_end = time.ticks_ms() + 20000
    while time.ticks_diff(wait_end, time.ticks_ms()) > 0:
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            break
        time.sleep_ms(100)

    if not ble_svc.ctx.get("ble_connected"):
        log("✗ 未连接，测试终止")
        return

    log("✓ BLE 已连接")

    # === 阶段 1: 正常骑行 20s ===
    log("=" * 40)
    log(" 阶段 1: 正常骑行 (20s)")
    log("=" * 40)
    log("  ⏱ 请在小程序点击「开始骑行」")
    countdown(5, "准备开始")
    pump_loop(bus, temp, ble_svc, 20)
    observe(10, [
        "数据卡片: 温度/湿度/速度有数值",
        "地图: 蓝色轨迹线在延伸",
        "状态: 骑行中...",
    ])

    # === 阶段 2: 碰撞报警 5s ===
    log("")
    log("=" * 40)
    log(" 阶段 2: 碰撞报警 (5s)")
    log("=" * 40)
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    pump_loop(bus, temp, ble_svc, 5, simulate_gnss=False)
    observe(5, [
        "全屏红色报警弹出（碰撞 Lv2）",
        "如果是导航中: 导航暂停",
    ])

    # === 阶段 3: 解除 3s ===
    log("")
    log("=" * 40)
    log(" 阶段 3: 解除报警 (3s)")
    log("=" * 40)
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, temp, ble_svc, 3)
    observe(5, [
        "报警消失",
        "状态恢复「正常」",
    ])

    # === 阶段 4: 导航指令 3 条 ===
    log("")
    log("=" * 40)
    log(" 阶段 4: 导航指令")
    log("=" * 40)
    cmds = [
        {"a": "nav", "d": {"dir": "right", "dist": 200, "road": "中山路"}},
        {"a": "nav", "d": {"dir": "straight", "dist": 500, "road": "人民路"}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]
    for i, cmd in enumerate(cmds):
        log("  [%d/3] %s" % (i + 1, json.dumps(cmd)))
        bus.publish(EVENT_NAV_CMD, {"raw": json.dumps(cmd)})
        pump_loop(bus, temp, ble_svc, 3)
    observe(5, [
        "Thonny 终端: 3 条 NAV_CMD 日志",
        "小程序: 可手动验证导航功能",
    ])

    # === 阶段 5: 继续骑行 10s ===
    log("")
    log("=" * 40)
    log(" 阶段 5: 继续骑行 (10s)")
    log("=" * 40)
    pump_loop(bus, temp, ble_svc, 10)

    # === 结束 ===
    log("")
    log("=" * 50)
    log(" 全部阶段完成")
    log("=" * 50)
    log(" 验证清单:")
    log("  [ ] 阶段 1: 数据卡片 + 轨迹正常")
    log("  [ ] 阶段 2: 碰撞报警弹窗正确")
    log("  [ ] 阶段 3: 报警解除恢复正常")
    log("  [ ] 阶段 4: 导航指令接收正确")
    log("  [ ] 阶段 5: 继续骑行数据正常")
    log("  [ ] 整体: 小程序未崩溃或卡死")
    log("")
    log("  请在小程序点击「结束骑行」查看骑行总结")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
