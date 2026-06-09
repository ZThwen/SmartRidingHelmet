"""
brief 小程序完整功能综合测试
note 覆盖板子到小程序的完整数据链路：
     Phase 0: 初始化 + BLE 连接
     Phase 1: 数据链路验证（温湿度/GNSS/光照）
     Phase 2: GPS 轨迹验证（西安坐标模拟）
     Phase 3: 导航功能验证（板子坐标源 + TTS + LCD）
     Phase 4: 报警功能验证（碰撞/SOS/取消）
     Phase 5: 报警-导航冲突验证
     Phase 6: BLE 断连/恢复验证
     Phase 7: 完整骑行流程
     Phase 8: LBS 定位验证
     板子端: 全部自动化
     小程序端: 按提示操作 + 观察检查清单
"""
import sys
sys.path.append("..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY, EVENT_LIGHT_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_NAV_CMD, EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    TTS_NAV_ARRIVE, TTS_NAV_CANCEL,
)
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService
from Drivers.network.BLE import BLEDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver


_LOG_PATH = "Tests/miniprogram/test_miniprogram_full.log"
_T0 = 0

# 西安坐标基准（陕西师范大学附近）
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


def phase_header(num, title):
    log("")
    log("=" * 50)
    log(" Phase %d: %s" % (num, title))
    log("=" * 50)


def observe(sec, items):
    log("")
    log("⏱ 观察窗口: %ds — 请在小程序检查:" % sec)
    for item in items:
        log("  [ ] %s" % item)
    log("")
    time.sleep(sec)


def pump_loop(bus, ble_svc, nav_svc, duration_s, gnss_base_lat=None, gnss_base_lon=None):
    """主循环：tick + pump + 模拟 GNSS 漂移"""
    end = time.ticks_ms() + duration_s * 1000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        # 每 2 秒模拟 GNSS 坐标漂移
        if gnss_base_lat and tick % 20 == 0:
            lat = gnss_base_lat + (tick % 100) * 0.000005
            lon = gnss_base_lon + (tick % 100) * 0.000008
            bus.publish(EVENT_GNSS_READY, {
                "latitude": lat, "longitude": lon,
                "altitude": 400.0, "speed_kmh": 15.0,
                "signal_quality": "good", "valid": True,
            })
        tick += 1
        time.sleep_ms(100)


def wait_ble(bus, ble_svc, timeout_s=20):
    """等待 BLE 连接"""
    log("▶ 等待 BLE 连接...")
    wait_end = time.ticks_ms() + timeout_s * 1000
    while time.ticks_diff(wait_end, time.ticks_ms()) > 0:
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            return True
        time.sleep_ms(100)
    return False


# ==================== 主测试流程 ====================

def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 小程序完整功能综合测试")
    print("=" * 50)
    print(" 坐标基准: 西安 (%.4f, %.4f)" % (_BASE_LAT, _BASE_LON))
    print("")

    bus = EventBus()

    # ==================== Phase 0: 初始化 ====================
    phase_header(0, "初始化")

    log("初始化 AudioDriver...")
    try:
        audio = AudioDriver(bus)
        audio.init()
        log("  ✓ AudioDriver")
    except Exception as e:
        log("  ✗ AudioDriver: %s" % e)
        audio = None

    log("初始化 LCDDriver...")
    try:
        lcd = LCDDriver(bus)
        lcd.init()
        log("  ✓ LCDDriver")
    except Exception as e:
        log("  ✗ LCDDriver: %s" % e)
        lcd = None

    log("初始化 BLEDriver + BLEService...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log("  ✓ BLE")
    except Exception as e:
        log("  ✗ BLE: %s" % e)
        return

    log("初始化 NavigationService...")
    try:
        nav_svc = NavigationService(bus, audio_driver=audio, lcd_driver=lcd)
        nav_svc.init()
        log("  ✓ NavigationService")
    except Exception as e:
        log("  ✗ NavigationService: %s" % e)
        nav_svc = None

    # 等待 BLE 连接
    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ BLE 未连接，测试终止")
        return
    log("✓ BLE 已连接")

    # ==================== Phase 1: 数据链路验证 ====================
    phase_header(1, "数据链路验证")

    log("▶ 发送传感器数据 (10 秒)...")
    end = time.ticks_ms() + 10000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        # 每 2 秒发一次温湿度 + GNSS + 光照
        if tick % 20 == 0:
            temp_val = 25.0 + (tick % 10) * 0.3
            humid_val = 60.0 - (tick % 10) * 0.5
            bus.publish(EVENT_TEMP_HUMID_READY, {
                "temp": temp_val, "humid": humid_val, "valid": True,
            })
            bus.publish(EVENT_GNSS_READY, {
                "latitude": _BASE_LAT + tick * 0.000001,
                "longitude": _BASE_LON + tick * 0.000001,
                "altitude": 400.0, "speed_kmh": 15.0,
                "signal_quality": "good", "valid": True,
            })
            bus.publish(EVENT_LIGHT_READY, {
                "light_intensity": 500 + tick * 10,
                "valid": True,
            })
            if tick % 40 == 0:
                log("  → 温度:%.1f 湿度:%.1f 速度:15.0km/h lux:%d" % (
                    temp_val, humid_val, 500 + tick * 10))
        tick += 1
        time.sleep_ms(100)

    observe(8, [
        "数据卡片: 温度有数值（不是 --）",
        "数据卡片: 湿度有数值（不是 --）",
        "数据卡片: 速度有数值（不是 --）",
        "定位卡片: 纬度/经度在更新",
        "状态栏: 显示「在线」",
        "BLE 状态: 显示「已连接」",
    ])

    # ==================== Phase 2: GPS 轨迹验证 ====================
    phase_header(2, "GPS 轨迹验证")

    log("▶ 模拟骑行轨迹 (20 秒, ~30 个坐标点)...")
    log("  基准: 西安陕西师范大学 (%.4f, %.4f)" % (_BASE_LAT, _BASE_LON))
    pump_loop(bus, ble_svc, nav_svc, 20, _BASE_LAT, _BASE_LON)

    observe(8, [
        "地图: 蓝色轨迹线在延伸（不是跳跃）",
        "地图: 轨迹在陕西师范大学附近",
        "地图: 蓝色圆点 marker 在轨迹前端",
        "定位卡片: 纬度/经度持续变化",
    ])

    # ==================== Phase 3: 导航功能验证 ====================
    phase_header(3, "导航功能验证")

    log("▶ 先推送 GNSS 坐标（让小程序有板子位置）...")
    for i in range(3):
        bus.publish(EVENT_GNSS_READY, {
            "latitude": _BASE_LAT + i * 0.00001,
            "longitude": _BASE_LON + i * 0.00001,
            "altitude": 400.0, "speed_kmh": 15.0,
            "signal_quality": "good", "valid": True,
        })
        bus.pump()
        time.sleep(500)

    log("▶ 请在小程序「开始骑行」→「设置目的地」")
    countdown(10, "等待小程序操作")

    log("▶ 发送导航指令...")
    nav_cmds = [
        {"a": "nav", "d": {"dir": "straight", "dist": 300, "road": "长安大道"}},
        {"a": "nav", "d": {"dir": "right", "dist": 150, "road": "雁南一路"}},
        {"a": "nav", "d": {"dir": "left", "dist": 80, "road": "师大路"}},
        {"a": "nav", "d": {"dir": "straight", "dist": 500, "road": "长安南路"}},
        {"a": "nav", "d": {"dir": "right", "dist": 200, "road": "纬二街"}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]

    for i, cmd in enumerate(nav_cmds):
        raw = json.dumps(cmd)
        d = cmd["d"]
        if d["dir"] == "arrive":
            desc = "到达目的地"
        else:
            dir_cn = {"straight": "直行", "right": "右转", "left": "左转", "uturn": "掉头"}.get(d["dir"], d["dir"])
            if d["road"]:
                desc = "前方%d米%s进入%s" % (d["dist"], dir_cn, d["road"])
            else:
                desc = "前方%d米%s" % (d["dist"], dir_cn)
        log("  [%d/%d] %s" % (i + 1, len(nav_cmds), desc))
        bus.publish(EVENT_NAV_CMD, {"raw": raw})
        bus.pump()
        time.sleep(100)
        # 等 TTS 播完（约 3 秒）
        pump_loop(bus, ble_svc, nav_svc, 3)

    observe(8, [
        '板子 TTS: 播报中文导航（如"前方300米直行进入长安大道"）',
        '板子 LCD: 底部显示导航行（如"^ 300m 长安大道"）',
        "小程序: 导航指令卡片显示方向和距离",
        "小程序: 地图显示绿色导航路线",
        "中文路名不乱码",
    ])

    # ==================== Phase 4: 报警功能验证 ====================
    phase_header(4, "报警功能验证")

    log("▶ 触发碰撞报警 Lv2...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    bus.pump()
    time.sleep(100)
    observe(5, [
        "小程序: 全屏红色报警弹窗（碰撞 Lv2）",
        "板子 LED: 快闪",
        "板子 Audio: 播放报警音",
    ])

    log("▶ 取消报警...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    bus.pump()
    time.sleep(100)
    observe(3, [
        "小程序: 报警弹窗消失",
        "板子 LED: 停止闪烁",
        "状态恢复「正常」",
    ])

    log("▶ 触发 SOS 报警 Lv3...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3})
    bus.pump()
    time.sleep(100)
    observe(5, [
        "小程序: 全屏红色报警弹窗（SOS）",
        "板子 LED: 快闪",
        "板子 Audio: 播放 SOS 音",
    ])

    log("▶ 取消 SOS...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    bus.pump()
    time.sleep(100)
    observe(3, [
        "小程序: SOS 弹窗消失",
        "状态恢复「正常」",
    ])

    # ==================== Phase 5: 报警-导航冲突 ====================
    phase_header(5, "报警-导航冲突")

    log("▶ 发送导航指令（模拟导航中）...")
    bus.publish(EVENT_NAV_CMD, {"raw": json.dumps(
        {"a": "nav", "d": {"dir": "straight", "dist": 300, "road": "测试路"}})})
    bus.pump()
    time.sleep(500)

    log("▶ 触发碰撞报警（导航中）...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    bus.pump()
    time.sleep(100)
    observe(5, [
        "小程序: 报警弹窗显示",
        "小程序: 导航指令卡片显示「报警中，导航暂停」",
    ])

    log("▶ 取消报警（验证导航恢复）...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    bus.pump()
    time.sleep(100)
    pump_loop(bus, ble_svc, nav_svc, 3)
    observe(5, [
        "小程序: 报警弹窗消失",
        "小程序: 导航指令卡片恢复正常",
        "板子 TTS: 继续播报导航",
    ])

    # ==================== Phase 6: BLE 断连/恢复 ====================
    phase_header(6, "BLE 断连/恢复")

    log("▶ 当前 BLE 状态: %s" % ("已连接" if ble_svc.ctx.get("ble_connected") else "未连接"))
    log("  请在小程序点击「断开」按钮")
    countdown(5, "等待手动断开")

    log("▶ 检查断连状态...")
    pump_loop(bus, ble_svc, nav_svc, 5, simulate_gnss=False)
    observe(3, [
        "小程序: BLE 状态显示「未连接」",
        "板子终端: 显示断连日志",
    ])

    log("  请在小程序点击「连接」重新连接")
    countdown(10, "等待重新连接")

    if wait_ble(bus, ble_svc, 20):
        log("✓ BLE 已重新连接")
        log("▶ 恢复数据推送...")
        pump_loop(bus, ble_svc, nav_svc, 5, _BASE_LAT, _BASE_LON)
        observe(5, [
            "小程序: BLE 状态恢复「已连接」",
            "小程序: 数据卡片恢复更新",
            "地图: 轨迹继续延伸",
        ])
    else:
        log("✗ 重新连接失败，跳过恢复测试")

    # ==================== Phase 7: 完整骑行流程 ====================
    phase_header(7, "完整骑行流程")

    log("▶ 请在小程序「结束骑行」后重新「开始骑行」")
    countdown(10, "等待操作")

    log("▶ 正常骑行 (15 秒)...")
    pump_loop(bus, ble_svc, nav_svc, 15, _BASE_LAT, _BASE_LON)

    log("▶ 碰撞报警...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    pump_loop(bus, ble_svc, nav_svc, 3)
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, ble_svc, nav_svc, 2)

    log("▶ 导航指令 3 条...")
    for cmd in [
        {"a": "nav", "d": {"dir": "right", "dist": 100, "road": "测试路A"}},
        {"a": "nav", "d": {"dir": "left", "dist": 50, "road": ""}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]:
        bus.publish(EVENT_NAV_CMD, {"raw": json.dumps(cmd)})
        pump_loop(bus, ble_svc, nav_svc, 3)

    log("▶ 继续骑行 (10 秒)...")
    pump_loop(bus, ble_svc, nav_svc, 10, _BASE_LAT, _BASE_LON)

    observe(8, [
        "整个流程中小程序未崩溃",
        "骑行总结弹窗显示",
        "骑行总结: 时长/距离/速度/温度数据正确",
        "骑行总结: 地图显示完整轨迹",
    ])

    # ==================== Phase 8: LBS 定位验证 ====================
    phase_header(8, "LBS 定位验证")

    log("▶ 尝试初始化 LBSDriver...")
    try:
        from Drivers.sensor.LBS import LBSDriver
        lbs_drv = LBSDriver(bus)
        lbs_drv.init()
        log("  ✓ LBSDriver 初始化成功")

        log("▶ 执行 LBS 定位 (15 秒超时)...")
        lbs_drv._do_positioning()
        bus.pump()

        d = lbs_drv.get_data()
        if d["valid"]:
            log("✓ LBS 定位成功: %.4f, %.4f (精度: %.0fm)" % (
                d["latitude"], d["longitude"], d.get("accuracy", 0)))
            log("  预期: 在西安附近 (%.4f, %.4f)" % (_BASE_LAT, _BASE_LON))

            log("▶ 用 LBS 坐标作为 GNSS 数据推送...")
            for i in range(5):
                bus.publish(EVENT_GNSS_READY, {
                    "latitude": d["latitude"] + i * 0.00001,
                    "longitude": d["longitude"] + i * 0.00001,
                    "altitude": 400.0, "speed_kmh": 0.0,
                    "signal_quality": "good", "valid": True,
                })
                bus.pump()
                time.sleep(500)
            observe(5, [
                "小程序: 定位卡片显示 LBS 坐标",
                "坐标在西安附近（34.15, 108.89）",
            ])
        else:
            log("✗ LBS 定位失败")
            log("  可能原因: 无 SIM 卡 / 未注册网络")

        lbs_drv.deinit()
    except Exception as e:
        log("  ✗ LBSDriver 不可用: %s" % e)
        log("  跳过 LBS 测试")

    # ==================== 总结 ====================
    log("")
    log("=" * 50)
    print(" 全部 Phase 完成")
    print("=" * 50)
    log("")
    log("最终验证清单:")
    log("  [ ] Phase 1: 传感器数据正常推送")
    log("  [ ] Phase 2: GPS 轨迹在地图上正确显示")
    log("  [ ] Phase 3: 导航 TTS 播报 + LCD 显示 + 地图路线")
    log("  [ ] Phase 4: 碰撞/SOS 报警弹窗正常")
    log("  [ ] Phase 5: 报警暂停/恢复导航正常")
    log("  [ ] Phase 6: BLE 断连/恢复正常")
    log("  [ ] Phase 7: 完整骑行流程无异常")
    log("  [ ] Phase 8: LBS 定位正常（如可用）")
    log("  [ ] 整体: 小程序未崩溃或卡死")
    log("")
    log("请在小程序点击「结束骑行」查看骑行总结")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
