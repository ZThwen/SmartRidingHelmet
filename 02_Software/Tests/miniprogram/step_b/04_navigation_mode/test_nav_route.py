"""
brief 导航路线显示测试
note 验证导航模式下地图显示：
     地图显示绿色导航路线
     目的地 marker 显示
     导航结束恢复轨迹
执行: 上传到板子运行，小程序端观察
"""
import sys
sys.path.append("../../..")
import time

from core.Event_Bus import EventBus
from core.config import EVENT_GNSS_READY
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


_LOG_PATH = "Tests/miniprogram/step_b/04_navigation_mode/test_nav_route.log"
_T0 = 0
_BASE_LAT = 34.1547
_BASE_LON = 108.8959


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


def wait_ble(bus, ble_svc, timeout_s=20):
    log("▶ 等待 BLE 连接...")
    end = time.ticks_ms() + timeout_s * 1000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            return True
        time.sleep_ms(100)
    return False


def pump_for(bus, ble_svc, duration_ms):
    end = time.ticks_ms() + duration_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 导航路线显示测试")
    print("=" * 50)

    bus = EventBus()

    log("初始化 BLE...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log("✓ BLE 就绪")
    except Exception as e:
        log("✗ BLE 失败: %s" % e)
        return

    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接")
        return
    log("✓ BLE 已连接")

    # 推送 GNSS 坐标让小程序有板子位置
    log("▶ 推送 GNSS 坐标...")
    for i in range(3):
        bus.publish(EVENT_GNSS_READY, {
            "latitude": _BASE_LAT + i * 0.00001,
            "longitude": _BASE_LON + i * 0.00001,
            "altitude": 400.0, "speed_kmh": 15.0,
            "signal_quality": "good", "valid": True,
        })
        bus.pump()
        pump_for(bus, ble_svc, 500)

    log("")
    log("请在小程序「开始骑行」→「设置目的地」→ 选择一个目的地")
    countdown(15, "等待操作")

    log("")
    log("=" * 40)
    log(" 导航中观察 (20 秒)")
    log("=" * 40)
    log("  请在小程序检查:")

    # 持续推送 GNSS 数据
    for i in range(10):
        bus.publish(EVENT_GNSS_READY, {
            "latitude": _BASE_LAT + i * 0.00002,
            "longitude": _BASE_LON + i * 0.00003,
            "altitude": 400.0, "speed_kmh": 15.0,
            "signal_quality": "good", "valid": True,
        })
        ble_svc.tick()
        bus.pump()
        pump_for(bus, ble_svc, 2000)

    log("")
    log("  [ ] 地图: 绿色导航路线可见")
    log("  [ ] 地图: 目的地 marker 可见")
    log("  [ ] 地图: 用户位置可见（蓝点）")
    log("  [ ] 导航卡片: 显示方向和距离")

    log("")
    log("请在小程序「结束骑行」")
    countdown(10, "等待操作")

    log("")
    log("  [ ] 导航结束: 地图恢复轨迹显示")
    log("  [ ] 骑行总结: 弹窗显示")

    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
