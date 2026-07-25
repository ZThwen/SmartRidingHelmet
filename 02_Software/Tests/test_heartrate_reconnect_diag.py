"""
brief 心率模块脱落与二次读取真机全链路集成测试 (适配真实 Byte[44] 心率索引 & 60s 锁频时长)
note 基于真实 Raw Hex 日志发现：
     心率值位于 index 44 (如 0x68=104bpm, 0x48=72bpm)，血氧位于 index 41 (如 0x63=99%)
     修改 Hook 适配真实的硬件字节偏移，并将贴合测试时间延长至 60s 适配光学收敛

运行环境：STM32 NUCLEO-F413ZH
文件位置：02_Software/Tests/test_heartrate_reconnect_diag.py
"""
import sys
import time

if ".." not in sys.path:
    sys.path.append("..")

from core.Event_Bus import EventBus
from Drivers.sensor.HeartRate import HeartRateDriver
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


def hook_uart_raw_log(hr_driver):
    """
    brief 动态挂载适配实际硬件索引(Index 44)的解析打印
    """
    original_parse = hr_driver._parse_packet

    def debug_parse(data_bytes):
        if data_bytes and len(data_bytes) == 50:
            b40 = data_bytes[40]
            b41 = data_bytes[41]
            b44 = data_bytes[44]
            hex_str = " ".join(["%02X" % b for b in data_bytes])
            
            # 检测 index 44 或 40/41 是否有有效心率
            detected_hr = 0
            if 30 <= b44 <= 240:
                detected_hr = b44
            elif 30 <= b40 <= 240:
                detected_hr = b40

            detected_spo2 = b41 if (70 <= b41 <= 100) else 0

            if detected_hr > 0 or detected_spo2 > 0:
                print("  ★ [捕获有效数据包!] 提取心率(Idx44)=%dbpm, 血氧(Idx41)=%d%% | Raw: %s" % (
                    detected_hr, detected_spo2, hex_str
                ))
            else:
                print("  >>>> [50B 串口包] Idx40=%d, Idx41=%d, Idx44=%d | Raw: %s" % (
                    b40, b41, b44, hex_str
                ))
                
        return original_parse(data_bytes)

    hr_driver._parse_packet = debug_parse
    print("  ✓ 已开启真实 Hex 字节流与 Index 44 硬件高亮 Hook！")


def run_e2e_test():
    print("=" * 65)
    print("  心率数据链路真机集成测试 (60秒锁频时长 + Index44 硬件偏移支持)")
    print("=" * 65)

    event_bus = EventBus()
    
    print("\n[1] 初始化 HeartRateDriver 驱动...")
    hr = HeartRateDriver(event_bus=event_bus)
    try:
        hr.init()
        print("  ✓ HeartRateDriver 就绪")
    except Exception as e:
        print("  ✗ HeartRateDriver 初始化失败:", e)
        return

    # 挂载硬件协议追踪 Hook
    hook_uart_raw_log(hr)

    print("\n[2] 初始化 BLEDriver 蓝牙驱动...")
    try:
        ble_driver = BLEDriver(event_bus=event_bus)
        ble_driver.init()
        print("  ✓ BLEDriver 就绪")
    except Exception as e:
        print("  ~ BLEDriver 警报/未连接:", e)
        ble_driver = None

    print("\n[3] 初始化 BLEService 蓝牙推送服务...")
    ble_svc = BLEService(event_bus=event_bus, ble_driver=ble_driver)
    try:
        ble_svc.init()
        print("  ✓ BLEService 就绪")
    except Exception as e:
        print("  ✗ BLEService 初始化失败:", e)

    print("\n" + "=" * 65)
    print("【测试开始】即将进行 3 阶段真实链路检测 (手指未按上时无数据流为正常现象)")
    print("=" * 65)

    # 启动心率采样
    hr.start_collect()

    # ----------------------------------------------------
    # 阶段 1：首次贴合测量 (60 秒)
    # ----------------------------------------------------
    print("\n>>> 【阶段 1】首次贴合测量 (60秒)")
    print(">>> 请将手指【持续按紧】心率传感器！等待 15~30秒 收敛出稳定脉搏！")
    print("-" * 65)
    
    _run_phase(hr, ble_svc, event_bus, duration_s=60, phase_name="阶段1-贴合")

    # ----------------------------------------------------
    # 阶段 2：手放开脱落观察 (20 秒)
    # ----------------------------------------------------
    print("\n>>> 【阶段 2】手放开脱落观察 (20秒)")
    print(">>> 请立刻【移开手指】，观察数据流停止或归零及 BLE 缓存状态！")
    print("-" * 65)

    _run_phase(hr, ble_svc, event_bus, duration_s=20, phase_name="阶段2-脱落")

    # ----------------------------------------------------
    # 阶段 3：二次重新贴合测试 (60 秒)
    # ----------------------------------------------------
    print("\n>>> 【阶段 3】二次重新贴合测试 (60秒)")
    print(">>> 请【再次将手指按紧】心率传感器，持续 60秒！")
    print("-" * 65)

    # 重置采集
    hr.start_collect()
    _run_phase(hr, ble_svc, event_bus, duration_s=60, phase_name="阶段3-二次贴合")

    # 打印最终总结
    print("\n" + "=" * 65)
    print("                    真实已有模块测试结果汇总")
    print("=" * 65)
    data = hr.get_data()
    status = hr.get_status()
    ble_latest_hr = ble_svc._data.get("latest_heart_rate") if ble_svc else None
    
    print("1. 真实 HeartRateDriver 驱动状态:")
    print("   - 最终数据: HR=%d, SpO2=%d, valid=%s" % (
        data["heart_rate"], data["spo2"], data["valid"]
    ))
    print("   - 接收有效包总数: %d" % status["packet_count"])

    print("\n2. 真实 BLEService 服务层状态:")
    print("   - latest_heart_rate 缓存值: %s" % ble_latest_hr)
    print("   - BLE 连接状态: %s" % (ble_svc.ctx.get("ble_connected") if ble_svc else False))
    print("=" * 65)


def _run_phase(hr, ble_svc, event_bus, duration_s, phase_name):
    start = time.ticks_ms()
    last_log = 0

    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        hr.tick()
        if ble_svc:
            ble_svc.tick()
        event_bus.pump()

        now = time.ticks_ms()
        if time.ticks_diff(now, last_log) >= 1000:
            last_log = now
            sec = time.ticks_diff(now, start) / 1000.0

            hr_data = hr.get_data()
            ble_hr = ble_svc._data.get("latest_heart_rate") if ble_svc else "N/A"
            ble_spo2 = ble_svc._data.get("latest_spo2") if ble_svc else "N/A"

            print("  [%s %4.1fs/%ds] HR驱动 -> HR:%3d, valid:%-5s | BLEService缓存 -> hr:%s, spo2:%s" % (
                phase_name, sec, duration_s,
                hr_data["heart_rate"], str(hr_data["valid"]),
                str(ble_hr), str(ble_spo2)
            ))

        time.sleep_ms(100)


if __name__ == "__main__":
    run_e2e_test()
