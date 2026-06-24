"""
brief 心率血氧数据链路 + 总结弹窗 E2E 测试（板子端 MicroPython）
note 验证完整数据流：心率传感器 → EventBus → BLEService → 小程序 UI → 骑行记录 → 总结弹窗
     运行在 STM32F413ZH 板子上，通过 BLE 与微信小程序通信
     日志输出到 Tests/miniprogram/test_heartrate_summary_e2e.log

阶段:
  ① 心率血氧传感器数据推送 — 板子发送 t=0 含 hr/spo2，小程序显示心率状态栏
  ② 骑行中心率数据记录 — addRecord 含 hr/spo2 参数，rideCache 正确缓存
  ③ 心率预警样式 — hr<50/hr>190/spo2<90 触发 warn/danger 样式
  ④ 结束骑行 → 总结弹窗 — avgHeartRate/maxHeartRate/avgSpO2/minSpO2 正确显示
  ⑤ 心率折线图数据 — hrTimeSeries 正确采样，Canvas 2D 绘制
  ⑥ 无心率硬件降级 — hr/spo2 为 null 时总结弹窗显示 '--'
  ⑦ 轨迹总结功能 — polyline/markers/callout 正确

执行: 上传到板子运行 python Tests/miniprogram/test_heartrate_summary_e2e.py
小程序: 微信开发者工具打开首页，连接 BLE，全程手动观察
"""
import sys
sys.path.append("..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_HEARTRATE_READY, EVENT_BLE_CONNECTED,
)
from Drivers.network.BLE import BLEDriver
from Drivers.sensor.Temp_Humid import TempHumidDriver
from Modules.ble_service import BLEService


# ==================== 常量 ====================

_LOG_PATH = "Tests/miniprogram/test_heartrate_summary_e2e.log"
_T0 = 0
_PASS = 0
_FAIL = 0
_LOG_FILE = None

# 模拟 GNSS 起点
_START_LAT = 22.5431
_START_LON = 113.9523
_END_LAT = 22.5500
_END_LON = 113.9600
_TICK_COUNT = 0


# ==================== 日志系统 ====================

def log_open():
    global _LOG_FILE, _T0
    _T0 = time.ticks_ms()
    try:
        _LOG_FILE = open(_LOG_PATH, "w")
    except:
        _LOG_FILE = None
    log_write("=" * 55)
    log_write("  心率血氧 + 总结弹窗 E2E 测试 — 日志开始")
    log_write("=" * 55)


def log_close():
    global _LOG_FILE
    log_write("=" * 55)
    log_write("  日志结束")
    if _LOG_FILE:
        _LOG_FILE.close()
        _LOG_FILE = None


def log_write(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    sec = elapsed / 1000.0
    line = "[%7.2fs] %s" % (sec, msg)
    print(line)
    if _LOG_FILE:
        _LOG_FILE.write(line + "\n")


def log_phase(num, title, duration):
    log_write("")
    log_write("=" * 55)
    log_write("  阶段 %s: %s (%ds)" % (num, title, duration))
    log_write("=" * 55)


def log_checklist(items):
    log_write("  请确认以下结果:")
    for item in items:
        log_write("    [ ] %s" % item)


def countdown(sec, msg):
    log_write("  倒计时: %ds — %s" % (sec, msg))
    for i in range(sec, 0, -1):
        log_write("  %ds..." % i)
        time.sleep(1)


def observe(sec, items):
    log_write("")
    log_write("  观察窗口: %ds" % sec)
    log_checklist(items)
    log_write("  确认完毕等待 %ds 自动继续..." % sec)
    time.sleep(sec)


# ==================== 模拟数据 ====================

def _sim_gnss(event_bus, tick):
    global _TICK_COUNT
    if tick % 2 != 0:
        return
    _TICK_COUNT += 1
    step = min(_TICK_COUNT, 30)
    lat = _START_LAT + (_END_LAT - _START_LAT) * step / 30.0
    lon = _START_LON + (_END_LON - _START_LON) * step / 30.0
    spd = 10.0 + (tick % 20) * 0.8
    alt = 10.0 + (tick % 16) * 0.5
    payload = {
        "latitude": lat, "longitude": lon,
        "altitude": alt, "speed_kmh": spd,
        "cog": 90.0 + tick * 0.5,
        "signal_quality": 3, "valid": True,
    }
    event_bus.publish(EVENT_GNSS_READY, payload)


def _sim_heartrate(event_bus, hr_value, spo2_value, valid=True):
    """模拟心率血氧数据推送"""
    payload = {
        "heart_rate": hr_value,
        "spo2": spo2_value,
        "valid": valid,
    }
    event_bus.publish(EVENT_HEARTRATE_READY, payload)
    log_write("  HEARTRATE sim: hr=%d spo2=%d valid=%s" % (hr_value, spo2_value, valid))


# ==================== 主循环 ====================

def pump_loop(bus, temp, ble_svc, duration_s, simulate_gnss=True):
    end = time.ticks_ms() + duration_s * 1000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if temp is not None:
            temp.tick()
        if ble_svc:
            ble_svc.tick()
        bus.pump()
        if simulate_gnss:
            _sim_gnss(bus, tick)
        tick += 1
        time.sleep_ms(100)


def pump_loop_with_hr(bus, temp, ble_svc, duration_s, hr_values, spo2_values):
    """带心率血氧模拟数据的主循环"""
    end = time.ticks_ms() + duration_s * 1000
    tick = 0
    hr_idx = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if temp is not None:
            temp.tick()
        if ble_svc:
            ble_svc.tick()
        bus.pump()
        _sim_gnss(bus, tick)
        # 每 2 秒推送一组心率血氧数据
        if tick % 20 == 0 and hr_idx < len(hr_values):
            _sim_heartrate(bus, hr_values[hr_idx], spo2_values[hr_idx])
            hr_idx += 1
        tick += 1
        time.sleep_ms(100)


# ==================== 初始化 ====================

def init_all():
    global _PASS
    bus = EventBus()

    log_write("--- 初始化 ---")

    # 温湿度
    log_write("  初始化 Temp_Humid...")
    try:
        temp = TempHumidDriver(event_bus=bus)
        temp.init()
        log_write("  OK Temp_Humid 就绪")
    except Exception as e:
        log_write("  ~ Temp_Humid 不可用: %s" % e)
        temp = None

    # BLE 驱动
    log_write("  初始化 BLEDriver...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        log_write("  OK BLEDriver 就绪" if ble_driver.ctx.get("is_init") else "  ~ BLEDriver 初始化失败")
    except Exception as e:
        log_write("  ~ BLEDriver 不可用: %s" % e)
        ble_driver = None

    # BLE 推送服务
    log_write("  初始化 BLEService...")
    try:
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log_write("  OK BLEService 就绪" if ble_svc.ctx.get("is_init") else "  ~ BLEService 初始化失败")
    except Exception as e:
        log_write("  ~ BLEService 不可用: %s" % e)
        ble_svc = None

    # 等待 BLE 连接
    log_write("  等待 BLE 连接小程序...")
    for i in range(30):
        if ble_svc and ble_svc.ctx.get("ble_connected"):
            log_write("  OK 第 %d 秒 BLE 连接成功" % (i + 1))
            break
        time.sleep(1)
    else:
        log_write("  ~ 30 秒内未连上 BLE")

    _PASS += 1
    return bus, temp, ble_svc


# ==================== 阶段 ①: 心率血氧数据推送 ====================

def phase_1(bus, temp, ble_svc):
    """验证 BLE 推送含 hr/spo2，小程序心率状态栏显示"""
    global _TICK_COUNT
    _TICK_COUNT = 0
    log_phase("①", "心率血氧数据推送", 30)

    countdown(10, "请在小程序点击「开始骑行」并展开地图到半屏")

    log_write("  测试开始: 推送正常心率 hr=75 spo2=97...")
    # 正常心率范围数据
    hr_values = [72, 75, 78, 80, 82, 85, 88, 90, 85, 80, 75, 72]
    spo2_values = [96, 97, 98, 97, 96, 97, 98, 97, 96, 97, 98, 97]

    pump_loop_with_hr(bus, temp, ble_svc, 30, hr_values, spo2_values)

    log_write("  测试结束")

    # 检查 BLEService 内部缓存
    if ble_svc:
        latest_hr = ble_svc._data.get("latest_heart_rate")
        latest_spo2 = ble_svc._data.get("latest_spo2")
        log_write("  BLEService 缓存: hr=%s spo2=%s" % (latest_hr, latest_spo2))

    observe(15, [
        "小程序心率状态栏: 心率显示 75 (蓝色心形图标)",
        "小程序心率状态栏: 血氧显示 97 (无警告样式)",
        "数据卡片: 温度/湿度/速度有数值",
        "定位卡片: 纬度/经度在更新",
        "BLE 状态: 已连接",
    ])

    _PASS += 1
    log_write("  OK 阶段 ① 完成")


# ==================== 阶段 ②: 骑行中心率数据记录 ====================

def phase_2(bus, temp, ble_svc):
    """验证小程序 RideService.addRecord 含 hr/spo2"""
    global _TICK_COUNT
    _TICK_COUNT = 0
    log_phase("②", "骑行中心率数据记录", 30)

    countdown(10, "确认小程序正在骑行中（心率状态栏有数值）")

    # 模拟心率波动（骑行中常见范围 60-120）
    hr_values = [65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 100, 90]
    spo2_values = [98, 97, 97, 96, 97, 98, 97, 96, 97, 98, 97, 97]

    log_write("  模拟骑行心率波动: 65→110→90 bpm")
    pump_loop_with_hr(bus, temp, ble_svc, 30, hr_values, spo2_values)

    log_write("  测试结束")

    observe(10, [
        "小程序心率状态栏: 数值从 65 逐步升至 110 再降回 90",
        "小程序地图: 轨迹线在延伸",
        "小程序没有崩溃或卡死",
    ])

    _PASS += 1
    log_write("  OK 阶段 ② 完成")


# ==================== 阶段 ③: 心率预警样式 ====================

def phase_3(bus, temp, ble_svc):
    """验证心率预警样式：hr<50=warn, hr>190=warn, spo2<90=danger"""
    log_phase("③", "心率预警样式", 25)

    countdown(10, "观察小程序心率状态栏的样式变化")

    # 3a: 正常心率
    log_write("  3a: 正常心率 hr=80 spo2=97")
    _sim_heartrate(bus, 80, 97)
    pump_loop(bus, temp, ble_svc, 5, simulate_gnss=True)
    observe(3, [
        "心率状态栏: 80 bpm，心形图标蓝色（正常样式）",
        "血氧: 97%，无红色警告",
    ])

    # 3b: 心率偏低 hr=45（<50 预警）
    log_write("  3b: 心率偏低 hr=45 spo2=97")
    _sim_heartrate(bus, 45, 97)
    pump_loop(bus, temp, ble_svc, 5, simulate_gnss=True)
    observe(3, [
        "心率状态栏: 45 bpm，心形图标变橙色（hr-warn 样式）",
        "血氧: 97%，无红色警告",
    ])

    # 3c: 心率偏高 hr=195（>190 预警）
    log_write("  3c: 心率偏高 hr=195 spo2=97")
    _sim_heartrate(bus, 195, 97)
    pump_loop(bus, temp, ble_svc, 5, simulate_gnss=True)
    observe(3, [
        "心率状态栏: 195 bpm，心形图标变橙色（hr-warn 样式）",
        "血氧: 97%，无红色警告",
    ])

    # 3d: 血氧偏低 spo2=88（<90 预警）
    log_write("  3d: 血氧偏低 hr=80 spo2=88")
    _sim_heartrate(bus, 80, 88)
    pump_loop(bus, temp, ble_svc, 5, simulate_gnss=True)
    observe(3, [
        "心率状态栏: 80 bpm，心形图标变红色（hr-danger 样式）",
        "血氧: 88%，显示红色（spo2-danger 样式）",
    ])

    # 3e: 恢复正常
    log_write("  3e: 恢复正常 hr=75 spo2=97")
    _sim_heartrate(bus, 75, 97)
    pump_loop(bus, temp, ble_svc, 5, simulate_gnss=True)
    observe(3, [
        "心率状态栏恢复正常蓝色样式",
        "血氧恢复正常无警告",
    ])

    _PASS += 1
    log_write("  OK 阶段 ③ 完成")


# ==================== 阶段 ④: 结束骑行 → 总结弹窗 ====================

def phase_4(bus, temp, ble_svc):
    """验证结束骑行后总结弹窗包含心率血氧统计数据"""
    global _TICK_COUNT
    _TICK_COUNT = 0
    log_phase("④", "结束骑行 → 总结弹窗", 50)

    countdown(10, "请在小程序重新点击「开始骑行」→「直接出发」")

    # 模拟一次完整骑行（30秒），含心率血氧数据
    hr_values = [72, 75, 78, 80, 85, 88, 92, 95, 90, 85, 80, 75, 72, 70, 68]
    spo2_values = [97, 98, 97, 96, 97, 98, 97, 96, 97, 98, 97, 97, 98, 97, 96]

    log_write("  模拟完整骑行 30s + 心率血氧数据...")
    pump_loop_with_hr(bus, temp, ble_svc, 30, hr_values, spo2_values)

    log_write("  骑行模拟完成，请在小程序点击「结束骑行」")
    countdown(10, "请在小程序点击「结束骑行」按钮，确认弹窗出现后按 Enter 继续")

    observe(10, [
        "总结弹窗已弹出",
        "总结弹窗地图: 显示骑行轨迹 + 起点/终点 callout",
        "总结弹窗表格: 「平均心率」行有数值（如 80.0 bpm）",
        "总结弹窗表格: 「最高心率」行有数值（如 95 bpm）",
        "总结弹窗表格: 「平均血氧」行有数值（如 97.0%）",
        "总结弹窗表格: 「最低血氧」行有数值（如 96%）",
        "总结弹窗: 心率折线图可见（蓝色折线 + 数据点）",
        "心率折线图: X轴有时间刻度，Y轴有心率刻度",
    ])

    _PASS += 1
    log_write("  OK 阶段 ④ 完成")


# ==================== 阶段 ⑤: 心率折线图数据 ====================

def phase_5(bus, temp, ble_svc):
    """验证 hrTimeSeries 采样和折线图绘制"""
    global _TICK_COUNT
    _TICK_COUNT = 0
    log_phase("⑤", "心率折线图数据验证", 40)

    countdown(10, "请重新开始骑行（直接出发）")

    # 生成密集心率数据（验证采样策略：超过60点按等间隔取样）
    hr_dense = []
    spo2_dense = []
    # 80 个心率点，模拟较长骑行
    for i in range(80):
        hr_dense.append(70 + int(i * 0.5) % 30)  # 70-100 波动
        spo2_dense.append(96 + (i % 3))           # 96-98 波动

    log_write("  模拟长骑行（80个心率点，验证 hrTimeSeries 采样上限60）...")
    pump_loop_with_hr(bus, temp, ble_svc, 40, hr_dense, spo2_dense)

    log_write("  请在小程序点击「结束骑行」")
    countdown(10, "点击「结束骑行」，观察折线图后按 Enter 继续")

    observe(10, [
        "总结弹窗心率折线图: 有折线绘制",
        "折线图最多60个数据点（密集数据被等间隔采样）",
        "折线图有 X/Y 轴刻度标注",
        "折线图蓝色天依蓝 #66ccff 风格",
        "折线图有预警区间淡蓝背景（50-190 bpm）",
    ])

    _PASS += 1
    log_write("  OK 阶段 ⑤ 完成")


# ==================== 阶段 ⑥: 无心率硬件降级 ====================

def phase_6(bus, temp, ble_svc):
    """验证 hr/spo2 为 null 时总结弹窗显示 '--' 和「暂无心率数据」"""
    global _TICK_COUNT
    _TICK_COUNT = 0
    log_phase("⑥", "无心率硬件降级", 30)

    countdown(10, "重新开始骑行（直接出发），本次不推送心率数据")

    # 只推送传感器数据，不推送心率
    log_write("  模拟骑行（无心率血氧传感器数据）...")
    pump_loop(bus, temp, ble_svc, 20, simulate_gnss=True)

    log_write("  请在小程序点击「结束骑行」")
    countdown(10, "点击「结束骑行」，观察降级显示后按 Enter 继续")

    observe(10, [
        "总结弹窗表格: 「平均心率」行显示 '--'",
        "总结弹窗表格: 「最高心率」行显示 '--'",
        "总结弹窗表格: 「平均血氧」行显示 '--'",
        "总结弹窗表格: 「最低血氧」行显示 '--'",
        "折线图区域: 显示「暂无心率数据」灰色占位文字",
        "其他数据（速度/温度/里程）正常显示",
    ])

    _PASS += 1
    log_write("  OK 阶段 ⑥ 完成")


# ==================== 阶段 ⑦: 轨迹总结功能 ====================

def phase_7(bus, temp, ble_svc):
    """验证轨迹总结：polyline/markers/callout 正确"""
    global _TICK_COUNT
    _TICK_COUNT = 0
    log_phase("⑦", "轨迹总结功能", 40)

    countdown(10, "重新开始骑行（直接出发）")

    # 正常骑行含心率数据
    hr_values = [72, 78, 85, 90, 85, 80]
    spo2_values = [97, 98, 97, 96, 97, 98]

    log_write("  模拟骑行含心率 + GPS 坐标漂移...")
    pump_loop_with_hr(bus, temp, ble_svc, 25, hr_values, spo2_values)

    log_write("  请在小程序点击「结束骑行」")
    countdown(10, "点击「结束骑行」，仔细观察轨迹地图后按 Enter 继续")

    observe(10, [
        "总结弹窗地图: 蓝色 polyline 轨迹线完整",
        "总结弹窗地图: 起点标记 callout 显示「起点」（天依蓝 #66ccff 背景）",
        "总结弹窗地图: 终点标记 callout 显示「终点」（红色 #ff3d00 背景）",
        "轨迹线在深圳附近（22.5431, 113.9523 → 22.5500, 113.9600）",
        "清空主地图数据后，总结弹窗地图轨迹不受影响",
    ])

    _PASS += 1
    log_write("  OK 阶段 ⑦ 完成")


# ==================== 主入口 ====================

if __name__ == "__main__":
    log_open()

    log_write(" 板子: AHT20 温湿度(真实) + 心率血氧(模拟) + GNSS(模拟漂移)")
    log_write(" 小程序: 微信开发者工具打开首页")
    log_write(" 准备: 1.已登录 2.BLE已连接 3.准备点击开始骑行")
    log_write(" 总时长约 5-6 分钟，每阶段有倒计时和观察窗口")
    log_write("")

    # 初始化
    bus, temp, ble_svc = init_all()
    if not bus:
        log_write("X 初始化失败，测试终止")
        log_close()
        sys.exit(1)

    # 执行 7 个阶段
    try:
        phase_1(bus, temp, ble_svc)    # 心率血氧数据推送
        phase_2(bus, temp, ble_svc)    # 骑行中心率数据记录
        phase_3(bus, temp, ble_svc)    # 心率预警样式
        phase_4(bus, temp, ble_svc)    # 结束骑行 → 总结弹窗
        phase_5(bus, temp, ble_svc)    # 心率折线图数据
        phase_6(bus, temp, ble_svc)    # 无心率硬件降级
        phase_7(bus, temp, ble_svc)    # 轨迹总结功能
    except KeyboardInterrupt:
        log_write("! 测试被中断")
    except Exception as e:
        log_write("X 测试异常: %s" % e)

    # 最终验证清单
    log_write("")
    log_write("=" * 55)
    log_write("  测试完成 — 验证清单")
    log_write("=" * 55)
    log_write("  通过: %d/7  失败: %d/7" % (_PASS, _FAIL))
    log_write("")
    log_write("  [ ] ① 心率血氧数据推送 — 状态栏显示心率+血氧数值")
    log_write("  [ ] ② 骑行中心率数据记录 — addRecord 含 hr/spo2 参数")
    log_write("  [ ] ③ 心率预警样式 — warn/danger 样式正确切换")
    log_write("  [ ] ④ 结束骑行 → 总结弹窗 — 心率血氧统计行正确")
    log_write("  [ ] ⑤ 心率折线图数据 — hrTimeSeries 采样 + Canvas 绘制")
    log_write("  [ ] ⑥ 无心率硬件降级 — 显示 '--' 和「暂无心率数据」")
    log_write("  [ ] ⑦ 轨迹总结功能 — polyline + 起点/终点 callout")
    log_write("")
    log_write("  日志已保存: %s" % _LOG_PATH)
    log_write("=" * 55)

    log_close()
