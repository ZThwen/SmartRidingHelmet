"""
brief 骑行轨迹记录+显示测试
note 验证轨迹功能：
     BLE 坐标记录到 trackPoints
     地图显示蓝色轨迹线
     轨迹在正确位置（西安）
执行: 上传到板子运行
"""
import sys
sys.path.append("../../..")
import time

from core.Event_Bus import EventBus
from core.config import EVENT_GNSS_READY
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


_LOG_PATH = "Tests/miniprogram/step_b/03_riding_mode/test_trajectory.log"
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
    print(" 骑行轨迹记录+显示测试")
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

    log("")
    log("请在小程序「开始骑行」→「直接出发」")
    countdown(10, "等待操作")

    # === 模拟骑行轨迹 30 秒 ===
    log("")
    log("=" * 40)
    log(" 模拟骑行轨迹 (30 秒, ~15 个点)")
    log("=" * 40)
    log("  基准: 西安陕西师范大学 (%.4f, %.4f)" % (_BASE_LAT, _BASE_LON))

    for i in range(15):
        lat = _BASE_LAT + i * 0.00005
        lon = _BASE_LON + i * 0.00008
        bus.publish(EVENT_GNSS_READY, {
            "latitude": lat, "longitude": lon,
            "altitude": 400.0, "speed_kmh": 15.0, "cog": 90.0,
            "signal_quality": "good", "valid": True,
        })
        ble_svc.tick()
        bus.pump()
        if i % 5 == 0:
            log("  → 点 %d: %.4f, %.4f" % (i + 1, lat, lon))
        pump_for(bus, ble_svc, 2000)

    log("")
    log("⏱ 观察窗口: 10 秒 — 请在小程序检查:")
    log("  [ ] 地图: 蓝色轨迹线在延伸")
    log("  [ ] 地图: 轨迹在陕西师范大学附近")
    log("  [ ] 地图: 轨迹方向一致（不是随机跳跃）")
    log("  [ ] 地图: 蓝色圆点 marker 在轨迹前端")
    pump_for(bus, ble_svc, 10000)

    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
