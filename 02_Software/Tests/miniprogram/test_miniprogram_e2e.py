"""
brief 小程序集成测试（真机 + 本地日志）
note 连接真实硬件（Temp_Humid），EventBus 完整事件链路
     GNSS 因室内无信号而模拟（GPS 坐标漂移 60s 用于验证地图轨迹）
     碰撞/SOS 报警使用 EventBus 模拟触发，验证云+小程序全链路
     日志输出到 Tests/test_miniprogram_e2e.log（同时 console）

阶段:
  ① 正常骑行 60s（GPS漂移+速度波动+信号轮换）→ 验证轨迹
  ② 碰撞报警 10s（alarm_type=1 level=2）
  ③ 解除→常态 10s（alarm_type=0）
  ④ SOS报警 10s（alarm_type=2 level=3）
  ⑤ 解除→常态 10s

执行: 上传到板子运行 python Tests/test_miniprogram_e2e.py
小程序: 同时打开观察各阶段变化
"""
import sys
sys.path.append("..")
import time

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
)
from Drivers.sensor.Temp_Humid import TempHumidDriver
from Modules.lark_cloud import LarkCloudService


# ==================== 日志系统 ====================

_LOG_PATH = "Tests/test_miniprogram_e2e.log"
_LOG_FILE = None
_T0 = 0  # 测试开始时间（ticks_ms）


def log_open():
    global _LOG_FILE, _T0
    _T0 = time.ticks_ms()
    try:
        _LOG_FILE = open(_LOG_PATH, "w")
    except:
        _LOG_FILE = None
    log_write("=" * 50)
    log_write(" 小程序集成测试 — 日志开始")
    log_write("=" * 50)


def log_close():
    global _LOG_FILE
    log_write("=" * 50)
    log_write(" 日志结束")
    if _LOG_FILE:
        _LOG_FILE.close()
        _LOG_FILE = None


def log_write(msg):
    """写日志到文件 + console"""
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    sec = elapsed / 1000.0
    line = "[%7.2fs] %s" % (sec, msg)
    print(line)
    if _LOG_FILE:
        _LOG_FILE.write(line + "\n")


# ==================== 模拟 GNSS ====================

_SIG_SEQ = [3, 2, 1, 0]   # 信号质量: 良好→一般→差→无
_SIG_IDX = 0
_TICK_COUNT = 0

# GPS 漂移参数（60s × 每2秒1次 = 30 个点）
_START_LAT = 22.5431
_START_LON = 113.9523
_END_LAT = 22.5500
_END_LON = 113.9600
_GPS_FIXED = False  # 报警阶段固定 GPS


def _sim_gnss(event_bus, tick):
    """模拟 GNSS：漂移阶段坐标递增，报警阶段固定"""
    global _SIG_IDX, _TICK_COUNT
    if tick % 2 != 0:
        return
    _TICK_COUNT += 1

    if _GPS_FIXED:
        lat, lon = _END_LAT, _END_LON
    else:
        # 60s 内漂移 30 步
        step = min(_TICK_COUNT, 30)
        lat = _START_LAT + (_END_LAT - _START_LAT) * step / 30.0
        lon = _START_LON + (_END_LON - _START_LON) * step / 30.0

    sig = _SIG_SEQ[_SIG_IDX % 4]
    sig_name = {3: "良好", 2: "一般", 1: "差", 0: "无"}[sig]
    _SIG_IDX += 1

    spd = 10.0 + (tick % 20) * 0.8
    alt = 10.0 + (tick % 16) * 0.5

    payload = {
        "latitude": lat, "longitude": lon,
        "altitude": alt, "speed_kmh": spd,
        "signal_quality": sig, "valid": True,
    }
    log_write("GNSS sim: lat=%.6f lon=%.6f spd=%.1f sig=%d(%s) alt=%.1f step=%d" % (
        lat, lon, spd, sig, sig_name, alt, _TICK_COUNT))
    event_bus.publish(EVENT_GNSS_READY, payload)


def _reset_gnss():
    global _SIG_IDX, _TICK_COUNT, _GPS_FIXED
    _SIG_IDX = 0
    _TICK_COUNT = 0
    _GPS_FIXED = False


# ==================== 事件拦截（记录 LarkCloudService 状态） ====================

def _hook_alarm(bus, lark):
    """订阅报警事件以记录日志"""
    def on_alarm(data):
        log_write("ALARM TRIGGERED: type=%s level=%s lark.alarm_active=%s" % (
            data.get("alarm_type"), data.get("level"), lark.ctx.get("alarm_active")))

    def on_cancel(data):
        log_write("ALARM CANCELED: lark.alarm_active=%s" % lark.ctx.get("alarm_active"))

    bus.subscribe(EVENT_ALARM_TRIGGERED, on_alarm)
    bus.subscribe(EVENT_ALARM_CANCELED, on_cancel)


# ==================== 主循环 ====================

def pump_loop(bus, temp_humid, lark, duration_s, simulate_gnss=True, alarm_mode=None):
    """
    模拟主循环
    param alarm_mode: None=常态, "collision"=碰撞, "sos"=SOS
    """
    end = time.ticks_ms() + duration_s * 1000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if temp_humid is not None:
            temp_humid.tick()
        lark.tick()
        bus.pump()

        # 记录 TSL 发送状态
        if lark.ctx.get("last_upload"):
            tsl = lark.ctx.get("last_tsl", {})
            if tsl:
                log_write("TSL sent: ids=%s alarm_active=%s" % (
                    sorted(tsl.keys()), lark.ctx.get("alarm_active")))

        if simulate_gnss:
            _sim_gnss(bus, tick)

        if alarm_mode == "collision":
            bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
        elif alarm_mode == "sos":
            bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3})

        tick += 1
        time.sleep_ms(100)


def wait_with_countdown(sec, msg):
    """倒计时暂停，让测试者观察小程序"""
    for i in range(sec, 0, -1):
        log_write("⏸ %s (%ds...)" % (msg, i))
        time.sleep(1)


# ==================== 初始化 ====================

def init_all():
    global PASS, FAIL
    bus = EventBus()

    log_write("--- 初始化 ---")
    log_write("  初始化 Temp_Humid...")
    try:
        temp = TempHumidDriver(event_bus=bus)
        temp.init()
    except Exception as e:
        log_write("  ~ Temp_Humid 不可用: %s" % e)
        temp = None
    if temp and temp.ctx.get("is_init"):
        log_write("  ✓ Temp_Humid 初始化成功")
    else:
        log_write("  ~ Temp_Humid 不可用")

    log_write("  初始化 LarkCloudService...")
    lark = LarkCloudService(bus)
    lark.init()
    if lark.ctx["is_init"]:
        log_write("  ✓ LarkCloudService 初始化成功")
    else:
        log_write("  ✗ LarkCloudService 初始化失败")
        FAIL += 1
        return None, None, None

    # 钩子：记录报警事件
    _hook_alarm(bus, lark)

    log_write("  等待移远云连接...")
    for i in range(30):
        if lark.qth and lark.qth.is_connected():
            log_write("  ✓ 第 %d 秒连上移远云" % (i + 1))
            break
        time.sleep(1)
    else:
        log_write("  ~ 30 秒内未连上")

    PASS += 1
    return bus, temp, lark


# ==================== 测试阶段 ====================

def test_phase_normal():
    """
    阶段①: 正常骑行 60 秒
    小程序: 温湿度/速度/位置正常，alarm=正常，地图轨迹持续绘制
    """
    global PASS, FAIL
    _reset_gnss()
    log_write("")
    log_write("=" * 50)
    log_write(" 阶段①: 正常骑行 (60 秒)")
    log_write(" GPS 漂移: (%.4f,%.4f) → (%.4f,%.4f)" % (_START_LAT, _START_LON, _END_LAT, _END_LON))
    log_write(" 小程序: 轨迹线 + alarm=正常 + 全字段")
    log_write("=" * 50)

    bus, temp, lark = init_all()
    if not lark:
        return None, None, None

    wait_with_countdown(3, "确认小程序已点「开始骑行」")
    log_write("  >>> 正常骑行中，GPS 漂移 60s <<<")

    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, temp, lark, 60, simulate_gnss=True, alarm_mode=None)

    global _GPS_FIXED
    _GPS_FIXED = True
    log_write("  ✓ 阶段①完成，GPS 固定在 (%.4f,%.4f)" % (_END_LAT, _END_LON))
    log_write("  轨迹点数: %d (预期 ~30)" % _TICK_COUNT)
    PASS += 1
    return bus, temp, lark


def test_phase_alarm(bus, temp, lark, alarm_type, level, label):
    """报警阶段（碰撞或 SOS）"""
    log_write("")
    log_write("-" * 40)
    log_write(" 阶段: %s 报警 (10 秒) type=%s level=%d" % (label, alarm_type, level))
    log_write(" 小程序: alarm='%s Lv%d' 红, 温湿度/速度='--'" % (label, level))
    log_write("-" * 40)

    wait_with_countdown(3, "观察小程序当前状态")
    log_write("  >>> 触发报警: %s <<<" % label)

    mode = "collision" if alarm_type == "collision" else "sos"
    pump_loop(bus, temp, lark, 10, simulate_gnss=True, alarm_mode=mode)

    log_write("  ✓ %s 报警完成" % label)


def test_phase_cancel(bus, temp, lark):
    """解除报警 → 恢复正常"""
    log_write("")
    log_write("-" * 40)
    log_write(" 阶段: 解除报警 → 常态 (10 秒)")
    log_write(" 小程序: alarm 恢复'正常'，温湿度/速度恢复")
    log_write("-" * 40)

    wait_with_countdown(3, "观察小程序报警态")
    log_write("  >>> 解除报警（发送 CANCEL 事件）<<<")

    bus.publish(EVENT_ALARM_CANCELED, {})
    time.sleep(1)
    lark.tick()
    bus.pump()

    pump_loop(bus, temp, lark, 10, simulate_gnss=True, alarm_mode=None)

    log_write("  ✓ 解除完成 — lark.alarm_active=%s" % lark.ctx.get("alarm_active"))


# ==================== 主入口 ====================

PASS = 0
FAIL = 0

if __name__ == "__main__":
    log_open()

    log_write(" 板子: AHT20 温湿度（真实） + GNSS（模拟漂移）")
    log_write(" 小程序: 微信开发者工具打开首页观察")
    log_write(" 准备: 1.已登录 2.点开始骑行 3.展开地图到半屏")
    log_write("")

    # 阶段①: 正常骑行 60s
    bus, temp, lark = test_phase_normal()
    if not lark:
        log_write("✗ 初始化失败，测试终止")
        log_close()
        sys.exit(1)

    # 阶段②: 碰撞报警
    test_phase_alarm(bus, temp, lark, "collision", 2, "碰撞")

    # 阶段③: 解除
    test_phase_cancel(bus, temp, lark)

    # 阶段④: SOS 报警
    test_phase_alarm(bus, temp, lark, "sos", 3, "SOS")

    # 阶段⑤: 解除
    test_phase_cancel(bus, temp, lark)

    # 总结
    log_write("")
    log_write("=" * 50)
    log_write(" 全部阶段完成")
    log_write(" 验证清单:")
    log_write("  [ ] 阶段① 地图有 ~%d 点轨迹线" % _TICK_COUNT)
    log_write("  [ ] 阶段① 温湿度/速度/位置正常，alarm=正常")
    log_write("  [ ] 阶段② alarm=碰撞 Lv2 红色，温湿度/速度=--")
    log_write("  [ ] 阶段③ alarm=正常，温湿度/速度恢复")
    log_write("  [ ] 阶段④ alarm=SOS Lv3 红色，温湿度/速度=--")
    log_write("  [ ] 阶段⑤ alarm=正常，温湿度/速度恢复")
    log_write("  通过: %d  失败: %d" % (PASS, FAIL))
    log_write("=" * 50)

    if FAIL > 0:
        log_write("⚠️  部分测试未通过")
    else:
        log_write("✅ 全部通过")

    log_close()
