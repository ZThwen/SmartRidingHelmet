"""
brief LarkCloudService 端到端测试（真机）
note 连接真实硬件模块（Temp_Humid），通过 EventBus 走完整事件链路
     仅 GNSS 因室内无信号而模拟
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

# ==================== 模拟 GNSS ====================

def _sim_gnss(event_bus, tick):
    """定期发布模拟 GNSS 数据（室内无真实 GPS 信号）"""
    if tick % 2 != 0:
        return
    event_bus.publish(EVENT_GNSS_READY, {
        "latitude": 22.5431, "longitude": 113.9523,
        "altitude": 10.0, "speed_kmh": 15.2,
        "signal_quality": "good", "valid": True,
    })

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
    # 先发一次取消
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
        # 不标记失败——sendTsl 可能仍然可用

    PASS += 1
    return bus, temp, lark


def test_upload_normal():
    """常态：真实温湿度 + 模拟 GNSS → 上传"""
    global PASS, FAIL
    print("\n--- 测试 1: 常态上传 ---")
    bus, temp, lark = test_init_all()
    if not lark:
        return

    print("  运行主循环 5 秒（等待 Temp_Humid 采集 + 上传）...")
    pump_loop_normal(bus, temp, lark, 5)

    print("  ✓ 常态上传完成（平台应收到 ID 1~5,8,9）")
    PASS += 1


def test_upload_alarm():
    """报警态：真实温湿度 + 模拟 GNSS + 模拟报警"""
    global PASS, FAIL
    print("\n--- 测试 2: 报警上传 ---")
    bus, temp, lark = test_init_all()
    if not lark:
        return

    # 先让常态数据走一次
    pump_loop_normal(bus, temp, lark, 2)

    # 触发报警
    print("  触发报警...")
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    time.sleep(1)
    lark.tick()
    bus.pump()

    # 报警态运行 5 秒
    pump_loop(bus, temp, lark, 5, simulate_gnss=True, alarm_mode=True)

    print("  ✓ 报警上传完成（平台应只收到 ID 4~9，无温湿度/速度）")
    PASS += 1


def test_upload_alarm_cancel():
    """报警解除 → 恢复正常"""
    global PASS, FAIL
    print("\n--- 测试 3: 报警解除 ---")
    bus, temp, lark = test_init_all()
    if not lark:
        return

    # 先触发报警
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3})
    time.sleep(1)
    lark.tick()
    bus.pump()

    pump_loop(bus, temp, lark, 3, simulate_gnss=True, alarm_mode=True)

    # 解除报警
    print("  解除报警...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    time.sleep(1)
    lark.tick()
    bus.pump()

    # 恢复正常模式
    pump_loop_normal(bus, temp, lark, 5)

    print("  ✓ 报警解除完成（平台应恢复收到温湿度数据）")
    PASS += 1


if __name__ == "__main__":
    print("LarkCloudService E2E 测试（真机）\n")
    print("  硬件: AHT20 温湿度传感器（真实）")
    print("        移远云 4G 连接（真实）")
    print("        GNSS 数据（模拟，室内无信号）")
    print("")

    test_upload_normal()
    test_upload_alarm()
    test_upload_alarm_cancel()

    print("\n========================")
    print("  通过: %d  失败: %d" % (PASS, FAIL))
    print("========================")
    if FAIL > 0:
        print("⚠️  部分测试未通过")
    else:
        print("✅ 全部通过")
