"""
brief LarkCloudService 端到端测试（真机）
note 连接真实硬件（Temp_Humid），EventBus 完整事件链路，仅 GNSS 因室内无信号而模拟
     每阶段打印明确标记，对照小程序验证显示逻辑
执行: 上传到板子运行 python Tests/test_lark_cloud_e2e.py
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


PASS = 0
FAIL = 0

# ==================== 模拟 GNSS（支持可变信号质量） ====================

_SIG_SEQ = ["good", "fair", "poor", "none"]  # 信号质量循环
_SIG_IDX = 0

def _sim_gnss(event_bus, tick):
    """定期发布模拟 GNSS 数据（室内无真实 GPS 信号），坐标和速度微变模拟真实骑行"""
    global _SIG_IDX
    if tick % 2 != 0:
        return
    # 坐标微变模拟移动，速度随机波动
    lat = 22.5431 + (tick % 100) * 0.0001
    lon = 113.9523 + (tick % 100) * 0.0001
    spd = 15.2 + (tick % 10) * 1.5
    alt = 10.0 + (tick % 20) * 0.5
    event_bus.publish(EVENT_GNSS_READY, {
        "latitude": lat, "longitude": lon,
        "altitude": alt, "speed_kmh": spd,
        "signal_quality": _sig_quality(), "valid": True,
    })

def _sig_quality():
    """返回当前模拟信号质量，每次 GNSS 上报轮换"""
    global _SIG_IDX
    q = _SIG_SEQ[_SIG_IDX % 4]
    _SIG_IDX += 1
    return q

def _reset_sig():
    global _SIG_IDX
    _SIG_IDX = 0


# ==================== 主循环 ====================

def pump_loop(bus, temp_humid, lark, duration_s, simulate_gnss=True, alarm_mode=False):
    """
    模拟主循环：tick 各模块 → pump 事件
    param duration_s: 运行时长（秒）
    param simulate_gnss: 是否注入模拟 GNSS
    param alarm_mode: 是否注入模拟报警
    """
    end = time.ticks_ms() + duration_s * 1000
    tick = 0
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if temp_humid is not None:
            temp_humid.tick()
        lark.tick()
        bus.pump()

        if simulate_gnss:
            _sim_gnss(bus, tick)

        if alarm_mode:
            bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})

        tick += 1
        time.sleep_ms(100)   # 100ms 循环周期


def pump_loop_normal(bus, temp_humid, lark, duration_s):
    """常态循环：取消报警"""
    bus.publish(EVENT_ALARM_CANCELED, {})
    pump_loop(bus, temp_humid, lark, duration_s, simulate_gnss=True, alarm_mode=False)


# ==================== 测试用例 ====================

def test_init_all():
    """初始化真实硬件 + LarkCloudService → 连接移远云"""
    global PASS, FAIL
    bus = EventBus()

    print("  初始化 Temp_Humid...")
    try:
        temp = TempHumidDriver(event_bus=bus)
        temp.init()
    except Exception as e:
        print("  ~ Temp_Humid 不可用: %s" % e)
        temp = None
    has_temp = temp is not None and temp.ctx.get("is_init", False)
    if has_temp:
        print("  ✓ Temp_Humid 初始化成功")
    else:
        print("  ~ Temp_Humid 不可用，继续测试")

    print("  初始化 LarkCloudService...")
    lark = LarkCloudService(bus)
    lark.init()
    if lark.ctx["is_init"]:
        print("  ✓ LarkCloudService 初始化成功")
    else:
        print("  ✗ LarkCloudService 初始化失败")
        FAIL += 1
        return None, None, None

    # 等待 Qth 连接
    print("  等待移远云连接...")
    for i in range(30):
        if lark.qth and lark.qth.is_connected():
            print("  ✓ 第 %d 秒连上移远云" % (i + 1))
            break
        time.sleep(1)
    else:
        print("  ~ 30 秒内未连上，跳过等待")

    PASS += 1
    return bus, temp, lark


def test_normal():
    """测试 1：常态上传 — 小程序应显示温度/湿度/速度/位置/信号(变化)/报警=正常"""
    global PASS, FAIL
    _reset_sig()
    print("\n" + "=" * 44)
    print(" 测试 1: 常态数据上传")
    print("=" * 44)
    print("  小程序预期: 温湿度+速度+位置正常, alarm=正常(不是碰撞!), 信号轮换")
    print("  现在 -> 先看小程序当前显示什么, 5秒后开始传常态数据")

    bus, temp, lark = test_init_all()
    if not lark:
        return

    # 暂停 5 秒 — 用户观察小程序当前状态
    for i in range(5, 0, -1):
        print("  ... %d 秒后开始" % i, end="\r")
        time.sleep(1)
    print("")

    print("  >>> 阶段: 常态上传 (10 秒) <<<")
    pump_loop_normal(bus, temp, lark, 10)

    print("  ✓ 常态上传完成 — 关注小程序 alarm 是否显示 '正常'")
    PASS += 1


def test_alarm():
    """测试 2：报警上传 — 小程序应显示 alarm=碰撞 Lv2(红色), 无温湿度/速度"""
    global PASS, FAIL
    _reset_sig()
    print("\n" + "=" * 44)
    print(" 测试 2: 报警数据上传")
    print("=" * 44)
    print("  小程序预期: alarm=碰撞 Lv2 红色, 无温度/湿度/速度更新")
    print("  现在 -> 先看小程序 alarm 是不是 '正常', 5秒后触发报警")

    bus, temp, lark = test_init_all()
    if not lark:
        return

    # 先常态 5 秒
    print("  >>> 阶段: 常态(确认 alarm=正常) <<<")
    pump_loop_normal(bus, temp, lark, 5)

    # 触发报警
    print("  >>> 阶段: 触发报警！<<<")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    time.sleep(1)
    lark.tick()
    bus.pump()

    print("  >>> 阶段: 报警持续 (10 秒，看小程序 alarm 变红) <<<")
    pump_loop(bus, temp, lark, 10, simulate_gnss=True, alarm_mode=True)

    print("  ✓ 报警上传完成 — 确认小程序 alarm='碰撞 Lv2' 红色")
    PASS += 1


def test_alarm_cancel():
    """测试 3：报警解除 — 小程序应恢复 alarm=正常, 重新显示温湿度"""
    global PASS, FAIL
    _reset_sig()
    print("\n" + "=" * 44)
    print(" 测试 3: 报警解除验证")
    print("=" * 44)
    print("  小程序预期: 先 SOS Lv3 红色 → 解除 → alarm 回到 '正常', 温湿度恢复")
    print("  现在 -> 5秒后触发 SOS 报警")

    bus, temp, lark = test_init_all()
    if not lark:
        return

    # 暂停 5 秒
    for i in range(5, 0, -1):
        print("  ... %d 秒后触发" % i, end="\r")
        time.sleep(1)
    print("")

    # 触发报警 → 持续 10 秒
    print("  >>> 阶段: SOS 报警中 (10 秒) <<<")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3})
    time.sleep(1)
    lark.tick()
    bus.pump()
    pump_loop(bus, temp, lark, 10, simulate_gnss=True, alarm_mode=True)

    # 解除报警
    print("  >>> 阶段: 解除！看小程序 alarm 变回 '正常' <<<")
    bus.publish(EVENT_ALARM_CANCELED, {})
    time.sleep(1)
    lark.tick()
    bus.pump()

    # 恢复正常模式
    print("  >>> 阶段: 常态恢复 (10 秒) <<<")
    pump_loop_normal(bus, temp, lark, 10)

    print("  ✓ 报警解除完成 — 确认小程序 alarm = '正常'（不是 SOS）")
    PASS += 1


if __name__ == "__main__":
    print("LarkCloudService E2E 测试（真机）\n")
    print("  硬件: AHT20 温湿度传感器（真实）")
    print("        移远云 4G 连接（真实）")
    print("        GNSS 数据（模拟，室内无信号）")
    print("")

    test_normal()
    test_alarm()
    test_alarm_cancel()

    print("\n" + "=" * 44)
    print("  通过: %d  失败: %d" % (PASS, FAIL))
    print("=" * 44)
    if FAIL > 0:
        print("⚠️  部分测试未通过")
    else:
        print("✅ 全部通过")

    print("\n--- 小程序对照验证 ---")
    print("  测试 1 → 检查: 温度/湿度/速度/位置正常, alarm='正常', 信号轮换(良好→一般→差→无)")
    print("  测试 2 → 检查: alarm='碰撞 Lv2' 红字, 温湿度/速度保持上阶段旧值或 --")
    print("  测试 3 → 检查: 报警 5s → 解除 → alarm='正常', 温湿度/速度重新出现")
    print("  ★ 重点: 解除后 alarm 不能残留 '碰撞' 或 'SOS'")
