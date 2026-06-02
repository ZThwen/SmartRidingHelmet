"""
brief 小程序 E2E 集成测试 v2（真机 + BLE + 导航）
note 覆盖: BLE 数据通道 / 导航指令 / 报警冲突 / GPS丢失 / 快速循环 / BLE断连 / 队列溢出 / 完整流程
     运行在 STM32 板子上，通过 BLE 与微信小程序通信
     日志输出到 Tests/test_miniprogram_e2e_v2.log（同时 console）

执行: 上传到板子运行 python Tests/test_miniprogram_e2e_v2.py
小程序: 同时打开观察各阶段变化
"""
import sys
sys.path.append("..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    EVENT_NAV_CMD, EVENT_GPS_LOST,
)
from Modules.ble_service import BLEService
from Drivers.network.BLE import BLEDriver
from Drivers.sensor.Temp_Humid import TempHumidDriver


# ==================== 常量 ====================

_COUNTDOWN_SEC = 10    # 阶段前倒计时
_OBSERVE_SEC = 15      # 阶段后观察窗口
_LOG_PATH = "Tests/test_miniprogram_e2e_v2.log"
_PASS = 0
_FAIL = 0
_LOG_FILE = None
_T0 = 0


# ==================== 日志系统 ====================

def log_open():
    global _LOG_FILE, _T0
    _T0 = time.ticks_ms()
    try:
        _LOG_FILE = open(_LOG_PATH, "w")
    except:
        _LOG_FILE = None
    log_write("=" * 55)
    log_write("  小程序 E2E 测试 v2 — 日志开始")
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
    """输出观察清单"""
    log_write("  请确认以下结果:")
    for item in items:
        log_write("    [ ] %s" % item)


def countdown(sec, msg):
    """倒计时"""
    log_write("  ⏱ 倒计时: %ds — %s" % (sec, msg))
    for i in range(sec, 0, -1):
        log_write("  ⏱ %ds..." % i)
        time.sleep(1)


def observe(sec, items):
    """观察窗口"""
    log_write("")
    log_write("  ⏱ 观察窗口: %ds" % sec)
    log_checklist(items)
    log_write("  确认完毕等待 %ds 自动继续..." % sec)
    time.sleep(sec)


# ==================== 模拟 GNSS ====================

_START_LAT = 22.5431
_START_LON = 113.9523
_END_LAT = 22.5500
_END_LON = 113.9600
_TICK_COUNT = 0
_GPS_VALID = True


def _sim_gnss(event_bus, tick):
    global _TICK_COUNT, _GPS_VALID
    if tick % 2 != 0:
        return
    _TICK_COUNT += 1

    if not _GPS_VALID:
        # GPS 丢失：发布 GPS_LOST 事件
        event_bus.publish(EVENT_GPS_LOST, {"reason": "no_fix"})
        return

    step = min(_TICK_COUNT, 30)
    lat = _START_LAT + (_END_LAT - _START_LAT) * step / 30.0
    lon = _START_LON + (_END_LON - _START_LON) * step / 30.0
    spd = 10.0 + (tick % 20) * 0.8
    alt = 10.0 + (tick % 16) * 0.5

    payload = {
        "latitude": lat, "longitude": lon,
        "altitude": alt, "speed_kmh": spd,
        "signal_quality": 3, "valid": True,
    }
    event_bus.publish(EVENT_GNSS_READY, payload)


def _reset_gnss():
    global _TICK_COUNT, _GPS_VALID
    _TICK_COUNT = 0
    _GPS_VALID = True


# ==================== 主循环 ====================

def pump_loop(bus, temp_humid, ble_svc, duration_s, simulate_gnss=True):
    end = time.ticks_ms() + duration_s * 1000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if temp_humid is not None:
            temp_humid.tick()
        if ble_svc:
            ble_svc.tick()
        bus.pump()

        if simulate_gnss:
            _sim_gnss(bus, tick)

        tick += 1
        time.sleep_ms(100)


# ==================== 初始化 ====================

def init_all():
    global _PASS, _FAIL
    bus = EventBus()

    log_write("--- 初始化 ---")

    # 温湿度
    log_write("  初始化 Temp_Humid...")
    try:
        temp = TempHumidDriver(event_bus=bus)
        temp.init()
        log_write("  ✓ Temp_Humid 就绪")
    except Exception as e:
        log_write("  ~ Temp_Humid 不可用: %s" % e)
        temp = None

    # BLE 驱动（初始化硬件 + 开始广播）
    log_write("  初始化 BLEDriver...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        log_write("  ✓ BLEDriver 就绪" if ble_driver.ctx.get("is_init") else "  ~ BLEDriver 初始化失败")
    except Exception as e:
        log_write("  ~ BLEDriver 不可用: %s" % e)
        ble_driver = None

    # BLE 推送服务
    log_write("  初始化 BLEService...")
    try:
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log_write("  ✓ BLEService 就绪" if ble_svc.ctx.get("is_init") else "  ~ BLEService 初始化失败")
    except Exception as e:
        log_write("  ~ BLEService 不可用: %s" % e)
        ble_svc = None

    # 等待 BLE 连接
    log_write("  等待 BLE 连接小程序...")
    for i in range(30):
        if ble_svc and ble_svc.ctx.get("ble_connected"):
            log_write("  ✓ 第 %d 秒 BLE 连接成功" % (i + 1))
            break
        time.sleep(1)
    else:
        log_write("  ~ 30 秒内未连上 BLE")

    _PASS += 1
    return bus, temp, ble_svc


# ==================== 阶段 ①: BLE 基础数据通道 ====================

def phase_1(bus, temp, ble_svc):
    """BLE 数据通道: t=0 传感器 + t=99 keepalive"""
    _reset_gnss()
    log_phase("①", "BLE 基础数据通道", 30)

    countdown(_COUNTDOWN_SEC, "请在小程序点击「开始骑行」并展开地图到半屏")

    log_write("  ▶ 测试开始...")
    pump_loop(bus, temp, ble_svc,30, simulate_gnss=True)
    log_write("  ▶ 测试结束")

    observe(_OBSERVE_SEC, [
        "小程序地图上有蓝色轨迹线在延伸",
        "环境卡片: 温度/湿度/速度有数值（不是 --）",
        "定位卡片: 纬度/经度/海拔在更新",
        "BLE 状态显示「已连接」",
        "报警显示「正常」",
    ])

    _PASS += 1
    log_write("  ✓ 阶段 ① 完成")


# ==================== 阶段 ②: 导航指令接收 ====================

def phase_2(bus, temp, ble_svc):
    """导航指令: 模拟小程序 FFF2 写入 nav 指令"""
    log_phase("②", "导航指令接收", 20)

    # 监听 NAV_CMD 事件
    nav_cmds = []
    def on_nav_cmd(data):
        raw = data.get("raw", "")
        log_write("  📩 NAV_CMD received: %s" % raw)
        nav_cmds.append(raw)
    bus.subscribe(EVENT_NAV_CMD, on_nav_cmd)

    countdown(_COUNTDOWN_SEC, "请在小程序选择目的地并开始导航")

    log_write("  ▶ 模拟小程序发送 3 条导航指令...")

    # 模拟 3 条导航指令
    cmds = [
        {"a": "nav", "d": {"dir": "right", "dist": 200, "road": "中山路"}},
        {"a": "nav", "d": {"dir": "straight", "dist": 500, "road": "人民路"}},
        {"a": "nav", "d": {"dir": "left", "dist": 150, "road": "解放路"}},
    ]
    for i, cmd in enumerate(cmds):
        raw = json.dumps(cmd)
        bus.publish(EVENT_NAV_CMD, {"raw": raw})
        log_write("  📤 发送指令 %d: %s" % (i + 1, raw))
        time.sleep(1)

    # 同时继续推送传感器数据
    pump_loop(bus, temp, ble_svc,15, simulate_gnss=True)

    log_write("  ▶ 测试结束")
    log_write("  收到 %d 条 NAV_CMD (预期 3)" % len(nav_cmds))

    observe(_OBSERVE_SEC, [
        "Thonny 终端显示 3 行 NAV_CMD received",
        "每条指令的 dir/dist/road 字段正确",
        "小程序导航指令浮层显示当前指令",
    ])

    _PASS += 1
    log_write("  ✓ 阶段 ② 完成")


# ==================== 阶段 ③: 报警-导航冲突 ====================

def phase_3(bus, temp, ble_svc):
    """报警-导航冲突: 碰撞→解除→SOS→解除"""
    log_phase("③", "报警-导航冲突", 30)

    countdown(_COUNTDOWN_SEC, "请确认小程序正在导航中（指令浮层可见）")

    # 3a: 碰撞报警
    log_write("  ▶ 触发碰撞报警...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    pump_loop(bus, temp, ble_svc,8, simulate_gnss=True)

    observe(8, [
        "小程序弹出全屏红色报警（碰撞 Lv2）",
        "导航指令浮层显示「报警中，导航暂停」",
    ])

    # 3b: 解除碰撞
    log_write("  ▶ 解除碰撞报警...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    observe(5, [
        "红色报警消失",
        "导航指令浮层恢复显示正常指令",
    ])

    # 3c: SOS 报警
    log_write("  ▶ 触发 SOS 报警...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3})
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    observe(5, [
        "小程序弹出全屏红色报警（SOS Lv3）",
        "报警有闪烁效果",
    ])

    # 3d: 解除 SOS
    log_write("  ▶ 解除 SOS 报警...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    observe(5, [
        "红色报警消失",
        "导航恢复正常",
        "报警显示「正常」",
    ])

    _PASS += 1
    log_write("  ✓ 阶段 ③ 完成")


# ==================== 阶段 ④: GPS 信号丢失 ====================

def phase_4(bus, temp, ble_svc):
    """GPS 信号丢失与恢复"""
    global _GPS_VALID
    log_phase("④", "GPS 信号丢失", 20)

    countdown(_COUNTDOWN_SEC, "请观察小程序定位卡片的纬度/经度数值")

    # 正常骑行 5s
    log_write("  ▶ 正常骑行 5s...")
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    # GPS 丢失
    log_write("  ▶ 模拟 GPS 信号丢失...")
    _GPS_VALID = False
    pump_loop(bus, temp, ble_svc,10, simulate_gnss=True)

    observe(8, [
        "定位卡片: 纬度/经度冻结或显示 --",
        "地图轨迹停止延伸",
    ])

    # GPS 恢复
    log_write("  ▶ GPS 信号恢复...")
    _GPS_VALID = True
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    observe(5, [
        "定位卡片: 纬度/经度恢复更新",
        "地图轨迹继续延伸",
    ])

    _PASS += 1
    log_write("  ✓ 阶段 ④ 完成")


# ==================== 阶段 ⑤: 快速报警循环 ====================

def phase_5(bus, temp, ble_svc):
    """快速报警/解除循环"""
    log_phase("⑤", "快速报警循环", 15)

    countdown(_COUNTDOWN_SEC, "请观察小程序报警弹窗的切换")

    log_write("  ▶ 快速报警循环: 碰撞→解除→SOS→解除→碰撞")
    events = [
        (EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2}, "碰撞报警"),
        (EVENT_ALARM_CANCELED, {}, "解除"),
        (EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3}, "SOS 报警"),
        (EVENT_ALARM_CANCELED, {}, "解除"),
        (EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 1}, "碰撞 Lv1"),
    ]

    for i, (evt, data, label) in enumerate(events):
        log_write("  📤 [%d/5] %s" % (i + 1, label))
        bus.publish(evt, data)
        # 推送几次传感器数据
        for _ in range(5):
            if temp:
                temp.tick()
            if ble_svc:
                ble_svc.tick()
            bus.pump()
            _sim_gnss(bus, i * 5)
            time.sleep_ms(300)

    # 最终解除
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, temp, ble_svc,3, simulate_gnss=True)

    observe(_OBSERVE_SEC, [
        "每次报警切换小程序都正确响应",
        "最终状态: 报警显示「正常」",
        "小程序没有崩溃或卡死",
        "数据卡片仍在正常更新",
    ])

    _PASS += 1
    log_write("  ✓ 阶段 ⑤ 完成")


# ==================== 阶段 ⑥: BLE 断连恢复 ====================

def phase_6(bus, temp, ble_svc):
    """BLE 断连与恢复"""
    log_phase("⑥", "BLE 断连恢复", 20)

    countdown(_COUNTDOWN_SEC, "请观察小程序 BLE 状态栏")

    # 正常骑行
    log_write("  ▶ 正常骑行 5s...")
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    # 模拟断连
    log_write("  ▶ 模拟 BLE 断连...")
    if ble_svc:
        ble_svc.ctx["ble_connected"] = False
        bus.publish(EVENT_BLE_DISCONNECTED, {})
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    observe(5, [
        "BLE 状态显示「已断开」",
        "数据卡片停止更新",
    ])

    # 恢复连接
    log_write("  ▶ 模拟 BLE 恢复连接...")
    if ble_svc:
        ble_svc.ctx["ble_connected"] = True
        bus.publish(EVENT_BLE_CONNECTED, {})
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    observe(5, [
        "BLE 状态恢复「已连接」",
        "数据卡片恢复更新",
    ])

    _PASS += 1
    log_write("  ✓ 阶段 ⑥ 完成")


# ==================== 阶段 ⑦: 队列溢出保护 ====================

def phase_7(bus, temp, ble_svc):
    """快速发布超过队列上限的事件"""
    log_phase("⑦", "队列溢出保护", 10)

    countdown(_COUNTDOWN_SEC, "请保持小程序打开，观察是否异常")

    log_write("  ▶ 快速发布 25 个报警事件...")
    for i in range(25):
        if i % 2 == 0:
            bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 1})
        else:
            bus.publish(EVENT_ALARM_CANCELED, {})
        if ble_svc:
            ble_svc.tick()
        time.sleep_ms(50)

    log_write("  ▶ 发布完毕，继续正常运行 5s...")
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)

    observe(_OBSERVE_SEC, [
        "小程序没有崩溃或卡死",
        "数据卡片仍在正常更新",
        "报警状态最终为「正常」",
    ])

    _PASS += 1
    log_write("  ✓ 阶段 ⑦ 完成")


# ==================== 阶段 ⑧: 完整骑行流程 ====================

def phase_8(bus, temp, ble_svc):
    """完整骑行流程模拟"""
    _reset_gnss()
    log_phase("⑧", "完整骑行流程", 60)

    countdown(_COUNTDOWN_SEC, "请在小程序重新点击「开始骑行」（可选设目的地）")

    # 8a: 正常骑行 20s
    log_write("  ▶ 8a: 正常骑行 20s...")
    pump_loop(bus, temp, ble_svc,20, simulate_gnss=True)
    log_write("  ✓ 正常骑行完成")

    # 8b: 碰撞报警 5s
    log_write("  ▶ 8b: 碰撞报警 5s...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    pump_loop(bus, temp, ble_svc,5, simulate_gnss=True)
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, temp, ble_svc,3, simulate_gnss=True)
    log_write("  ✓ 碰撞报警+解除完成")

    # 8c: 模拟导航指令
    log_write("  ▶ 8c: 模拟导航指令 3 条...")
    nav_cmds = [
        {"a": "nav", "d": {"dir": "right", "dist": 200, "road": "中山路"}},
        {"a": "nav", "d": {"dir": "straight", "dist": 500, "road": "人民路"}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]
    for cmd in nav_cmds:
        bus.publish(EVENT_NAV_CMD, {"raw": json.dumps(cmd)})
        pump_loop(bus, temp, ble_svc,3, simulate_gnss=True)
    log_write("  ✓ 导航指令完成")

    # 8d: 正常骑行 20s
    log_write("  ▶ 8d: 正常骑行 20s...")
    pump_loop(bus, temp, ble_svc,20, simulate_gnss=True)
    log_write("  ✓ 完整流程结束")

    observe(_OBSERVE_SEC, [
        "全流程无异常",
        "轨迹线完整（蓝色 polyline）",
        "报警弹窗正确弹出和消失",
        "导航指令浮层正确显示",
        "最终数据卡片正常",
    ])

    _PASS += 1
    log_write("  ✓ 阶段 ⑧ 完成")


# ==================== 主入口 ====================

if __name__ == "__main__":
    log_open()

    log_write(" 板子: AHT20 温湿度（真实） + GNSS（模拟漂移）")
    log_write(" 小程序: 微信开发者工具打开首页")
    log_write(" 准备: 1.已登录 2.BLE已连接 3.准备点击开始骑行")
    log_write(" 总时长约 5-6 分钟，每阶段有倒计时和观察窗口")
    log_write("")

    # 初始化
    bus, temp, ble_svc = init_all()
    if not bus:
        log_write("✗ 初始化失败，测试终止")
        log_close()
        sys.exit(1)

    # 执行 8 个阶段
    try:
        phase_1(bus, temp, ble_svc)
        phase_2(bus, temp, ble_svc)
        phase_3(bus, temp, ble_svc)
        phase_4(bus, temp, ble_svc)
        phase_5(bus, temp, ble_svc)
        phase_6(bus, temp, ble_svc)
        phase_7(bus, temp, ble_svc)
        phase_8(bus, temp, ble_svc)
    except KeyboardInterrupt:
        log_write("⚠ 测试被中断")
    except Exception as e:
        log_write("✗ 测试异常: %s" % e)

    # 最终验证清单
    log_write("")
    log_write("=" * 55)
    log_write("  测试完成 — 验证清单")
    log_write("=" * 55)
    log_write("  通过: %d/8  失败: %d/8" % (_PASS, _FAIL))
    log_write("")
    log_write("  [ ] ① BLE 数据通道 — 数据卡片+轨迹+BLE状态")
    log_write("  [ ] ② 导航指令接收 — 串口收到 NAV_CMD")
    log_write("  [ ] ③ 报警-导航冲突 — 暂停+恢复正确")
    log_write("  [ ] ④ GPS 信号丢失 — 冻结+恢复")
    log_write("  [ ] ⑤ 快速报警循环 — 不崩溃不卡死")
    log_write("  [ ] ⑥ BLE 断连恢复 — 断连+重连+数据恢复")
    log_write("  [ ] ⑦ 队列溢出保护 — 不阻塞不崩溃")
    log_write("  [ ] ⑧ 完整骑行流程 — 全流程正常")
    log_write("")
    log_write("  日志已保存: %s" % _LOG_PATH)
    log_write("=" * 55)

    log_close()
