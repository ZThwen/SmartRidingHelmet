"""
brief GNSS定位驱动单模块测试脚本
note 用于验证 GNSSDriver 的各项公共接口功能是否正常
     GNSS 搜星需要时间且在室外才能定位，室内无定位属于正常情况
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (EVENT_GNSS_READY, EVENT_GPS_LOST, EVENT_SENSOR_ERROR,EVENT_CONFIG_UPDATE)
from Drivers.sensor.GNSS import GNSSDriver, GNSS_STATE_IDLE, GNSS_STATE_SEARCH, GNSS_STATE_FIXED

# ==================== 回调日志记录 ====================
event_log = []

def on_gnss_ready(payload):
    event_log.append(("GNSS_READY", payload))
    print(f"\n[事件回调] EVENT_GNSS_READY")
    print(f"  经度: {payload['longitude']:.4f}")
    print(f"  纬度: {payload['latitude']:.4f}")
    print(f"  有效性: {payload['valid']}")

def on_gps_lost(payload):
    event_log.append(("GPS_LOST", payload))
    print(f"\n[事件回调] EVENT_GPS_LOST")
    print(f"  来源: {payload.get('source')}")

def on_sensor_error(payload):
    event_log.append(("SENSOR_ERROR", payload))
    print(f"\n[事件回调] EVENT_SENSOR_ERROR")
    print(f"  来源: {payload.get('source')}")
    print(f"  错误: {payload.get('error')}")

# ==================== 测试主流程 ====================
def test_gnss():
    print("=" * 60)
    print("GNSS定位驱动单模块测试")
    print("=" * 60)

    event_bus = EventBus()
    event_bus.debug = True

    event_bus.subscribe(EVENT_GNSS_READY, on_gnss_ready)
    event_bus.subscribe(EVENT_GPS_LOST, on_gps_lost)
    event_bus.subscribe(EVENT_SENSOR_ERROR, on_sensor_error)

    gnss = GNSSDriver(event_bus)

    # ==================== 测试 1：初始化 ====================
    print("\n" + "-" * 60)
    print("[测试 1] 初始化模块")
    print("-" * 60)
    try:
        gnss.init()
        print("\n✓ 初始化成功")
    except Exception as e:
        print(f"\n✗ 初始化失败: {e}")
        return

    # ==================== 测试 2：状态查询 ====================
    print("\n" + "-" * 60)
    print("[测试 2] 查看模块状态")
    print("-" * 60)
    status = gnss.get_status()
    print(f"  is_init:      {status['is_init']}")
    print(f"  is_busy:      {status['is_busy']}")
    print(f"  err_count:    {status['err_count']}")
    print(f"  power_state:  {status['power_state']}")
    print(f"  gnss_state:   {status['gnss_state']}")
    print(f"  no_fix_count: {status['no_fix_count']}")

    # ==================== 测试 3：数据采集 ====================
    print("\n" + "-" * 60)
    print("[测试 3] 数据采集测试（每 2 秒采集一次，共 5 次）")
    print("-" * 60)
    print("  note: 室内可能无定位，属于正常情况")
    event_log.clear()

    for i in range(5):
        print(f"\n  --- 第 {i+1} 次采集 ---")
        gnss.tick()
        event_bus.pump()

        data = gnss.get_data()
        status = gnss.get_status()
        print(f"  定位状态: {status['gnss_state']}")
        print(f"  连续无定位: {status['no_fix_count']} 次")

        if data["valid"]:
            print(f"  经度: {data['longitude']:.4f}")
            print(f"  纬度: {data['latitude']:.4f}")
            print(f"  海拔: {data['altitude']:.1f} m")
            print(f"  速度: {data['speed_kmh']:.1f} km/h")
            print(f"  信号质量: {data['signal_quality']}")
        else:
            print("  暂无定位数据")

        time.sleep(2)

    # 打印事件统计
    ready_events = [e for e in event_log if e[0] == "GNSS_READY"]
    lost_events = [e for e in event_log if e[0] == "GPS_LOST"]
    print(f"\n  收到 GNSS_READY 事件: {len(ready_events)} 次")
    print(f"  收到 GPS_LOST 事件:  {len(lost_events)} 次")

    # ==================== 测试 4：数据字段完整性 ====================
    print("\n" + "-" * 60)
    print("[测试 4] 数据字段完整性验证")
    print("-" * 60)

    data = gnss.get_data()
    expected_fields = ["latitude", "longitude", "altitude", "speed_kmh", "signal_quality", "valid", "timestamp"]
    missing = [f for f in expected_fields if f not in data]
    if not missing:
        print("  ✓ get_data() 包含所有预期字段")
        print(f"    字段列表: {list(data.keys())}")
    else:
        print(f"  ✗ get_data() 缺少字段: {missing}")

    # 验证初始信号质量值为 none
    if data["signal_quality"] == "none":
        print("  ✓ signal_quality 初始值为 none")
    else:
        print(f"  ✗ signal_quality 初始异常: {data['signal_quality']}")

    # ==================== 测试 5：定位字段探测 ====================
    print("\n" + "-" * 60)
    print("[测试 5] 定位字段探测")
    print("-" * 60)
    print("  当有定位时，打印 loc.keys() 确认实际返回字段")
    print("  如果处于无定位状态，本条测试仅提示跳过")

    # 强制调用一次 get_location() 直接查看返回值
    try:
        loc = gnss.gnss.get_location()
        if loc:
            print(f"\n  返回类型: {type(loc)}")
            print(f"  所有字段: {loc.keys()}")
            print(f"  完整数据: {loc}")
        else:
            print(f"\n  暂无定位，返回值: {repr(loc)}")
            print(f"  待室外测试时再确认字段")
    except Exception as e:
        print(f"\n  读取异常: {e}")

    # ==================== 测试 6：配置更新测试 ====================
    print("\n" + "-" * 60)
    print("[测试 6] 配置更新测试")
    print("-" * 60)

    print(f"\n  更新前采样间隔: {gnss.cfg['sample_ms']}ms")
    event_bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "gnss",
        "sample_ms": 5000
    })
    event_bus.pump()
    time.sleep_ms(100)
    print(f"  更新后采样间隔: {gnss.cfg['sample_ms']}ms")
    print(f"  {'✓ 配置更新成功' if gnss.cfg['sample_ms'] == 5000 else '✗ 配置更新失败'}")

    # ==================== 测试 7：stop() 测试 ====================
    print("\n" + "-" * 60)
    print("[测试 7] stop() 停止定位测试")
    print("-" * 60)

    result = gnss.stop()
    status = gnss.get_status()
    print(f"  stop(): {'✓' if result else '✗'}")
    print(f"  停止后状态: {status['gnss_state']}")
    print(f"  预期状态: {GNSS_STATE_IDLE}")

    # ==================== 测试总结 ====================
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    print(f"\n事件接收统计:")
    print(f"  GNSS_READY: {len([e for e in event_log if e[0] == 'GNSS_READY'])} 次")
    print(f"  GPS_LOST:   {len([e for e in event_log if e[0] == 'GPS_LOST'])} 次")
    print(f"  SENSOR_ERROR: {len([e for e in event_log if e[0] == 'SENSOR_ERROR'])} 次")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_gnss()
