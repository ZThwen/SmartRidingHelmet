"""
brief 全功能集成测试
note 综合测试所有功能，分阶段验证：
     Phase 1: 数据链路（传感器数据推送）
     Phase 2: 骑行模式（轨迹 + 显示）
     Phase 3: 导航模式（TTS + LCD + 路线 + 位置）
     Phase 4: 报警功能（碰撞/SOS + 导航冲突）
     Phase 5: 完整骑行流程
执行: 上传到板子运行
"""
import sys
sys.path.append("../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY, EVENT_LIGHT_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED, EVENT_NAV_CMD,
)
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver


_LOG_PATH = "Tests/miniprogram/step_b/06_full_integration.log"
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


def phase(num, title):
    log("")
    log("=" * 50)
    log(" Phase %d: %s" % (num, title))
    log("=" * 50)


def countdown(sec, msg):
    log("⏱ 倒计时: %ds — %s" % (sec, msg))
    for i in range(sec, 0, -1):
        log("  %ds..." % i)
        time.sleep(1)


def observe(sec, items, bus, ble_svc):
    log("")
    log("⏱ 观察: %ds" % sec)
    for item in items:
        log("  [ ] %s" % item)
    pump_for(bus, ble_svc, sec * 1000)


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


def push_data(bus, ble_svc, duration_s, lat=None, lon=None):
    end = time.ticks_ms() + duration_s * 1000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        if lat and tick % 20 == 0:
            bus.publish(EVENT_GNSS_READY, {
                "latitude": lat + tick * 0.000005,
                "longitude": lon + tick * 0.000008,
                "altitude": 400.0, "speed_kmh": 15.0,
                "signal_quality": "good", "valid": True,
            })
            bus.publish(EVENT_TEMP_HUMID_READY, {
                "temp": 25.0 + tick * 0.1, "humid": 60.0, "valid": True,
            })
        tick += 1
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 全功能集成测试")
    print("=" * 50)
    print(" 坐标基准: 西安 (%.4f, %.4f)" % (_BASE_LAT, _BASE_LON))

    bus = EventBus()

    # 初始化
    log("初始化全部模块...")
    try:
        audio = AudioDriver(bus)
        audio.init()
        lcd = LCDDriver(bus)
        lcd.init()
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        nav_svc = NavigationService(bus, audio_driver=audio)
        nav_svc.init()
        log("✓ 全部就绪")
    except Exception as e:
        log("✗ 初始化失败: %s" % e)
        return

    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接")
        return
    log("✓ BLE 已连接")

    # Phase 1: 数据链路
    phase(1, "数据链路验证")
    push_data(bus, ble_svc, 10, _BASE_LAT, _BASE_LON)
    observe(5, [
        "数据卡片: 温度/湿度/速度有数值",
        "定位卡片: 纬度/经度在更新",
        "BLE 状态: 已连接",
    ], bus, ble_svc)

    # Phase 2: 骑行模式
    phase(2, "骑行模式")
    log("请在小程序「开始骑行」→「直接出发」")
    countdown(10, "等待操作")
    push_data(bus, ble_svc, 20, _BASE_LAT, _BASE_LON)
    observe(5, [
        "地图: 蓝色轨迹线在延伸",
        "地图: 轨迹在西安附近",
        "数据卡片: 数值在更新",
    ], bus, ble_svc)

    # Phase 3: 导航模式（本地模拟，不依赖小程序）
    phase(3, "导航模式")

    log("▶ 模拟导航指令（本地）...")
    nav_cmds = [
        {"a": "nav", "d": {"dir": "straight", "dist": 300, "road": "长安大道"}},
        {"a": "nav", "d": {"dir": "right", "dist": 150, "road": "雁南一路"}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]
    for cmd in nav_cmds:
        bus.publish(EVENT_NAV_CMD, {"raw": json.dumps(cmd)})
        bus.pump()
        pump_for(bus, ble_svc, 100)
        # 等 TTS 播完（约 3-5 秒），避免 Malloc failed
        pump_for(bus, ble_svc, 5000)
        push_data(bus, ble_svc, 2, _BASE_LAT, _BASE_LON)

    observe(5, [
        "板子 TTS: 播报中文导航",
        "板子 LCD: 底部显示导航行",
    ], bus, ble_svc)

    # Phase 4: 报警
    phase(4, "报警功能")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    bus.pump()
    pump_for(bus, ble_svc, 100)
    observe(3, ["小程序: 报警弹窗"], bus, ble_svc)
    bus.publish(EVENT_ALARM_CANCELED, {})
    bus.pump()
    pump_for(bus, ble_svc, 100)
    observe(3, ["小程序: 弹窗消失"], bus, ble_svc)

    # Phase 5: 完整流程
    phase(5, "完整骑行流程")
    push_data(bus, ble_svc, 15, _BASE_LAT, _BASE_LON)
    observe(5, [
        "整个流程中小程序未崩溃",
        "数据正常更新",
    ], bus, ble_svc)

    # 总结
    log("")
    log("=" * 50)
    print(" 全功能集成测试完成")
    print("=" * 50)
    log("  [ ] Phase 1: 数据链路正常")
    log("  [ ] Phase 2: 骑行模式正常")
    log("  [ ] Phase 3: 导航模式正常")
    log("  [ ] Phase 4: 报警功能正常")
    log("  [ ] Phase 5: 完整流程正常")
    log("  [ ] 整体: 小程序未崩溃或卡死")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
