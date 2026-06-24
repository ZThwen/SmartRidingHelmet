"""
brief 心率血氧模块硬件测试
note 所有代码放到根目录测试，真实佩戴测试
      需求验证：
      1. 心率数据采集
      2. 血氧数据采集
      3. force_read() 强制读取
      测试环境：STM32 NUCLEO-F413ZH
      心率模块：MKS_SPO2_ZS_BLE（USART6, PG14/PG9）
      测试场景：手指测试 + force_read测试
"""
import time

try:
    from core.config import (
        EVENT_HEARTRATE_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE,
        POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    )
    from core.Event_Bus import EventBus
except:
    from config import (
        EVENT_HEARTRATE_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE,
        POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    )
    from Event_Bus import EventBus

from Drivers.sensor.HeartRate import HeartRateDriver


def test_scenario(hr, event_bus, scenario_name, duration_sec, instruction):
    """
    brief 测试场景
    param hr: 心率驱动实例
    param event_bus: 事件总线
    param scenario_name: 场景名称
    param duration_sec: 测试时长（秒）
    param instruction: 测试说明
    """
    print("\n" + "=" * 60)
    print("[%s] %s" % (scenario_name, instruction))
    print("=" * 60)
    print("测试时长：%d秒" % duration_sec)
    print("预热时间：%d秒（前%d秒数据可能无效）" % (
        hr.cfg["warmup_ms"] // 1000,
        hr.cfg["warmup_ms"] // 1000
    ))

    hr.start_collect()

    start_time = time.ticks_ms()
    last_print_time = 0
    valid_count = 0
    invalid_count = 0

    while True:
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, start_time)

        if elapsed >= duration_sec * 1000:
            break

        hr.tick()
        event_bus.pump()

        if time.ticks_diff(now, last_print_time) >= 1000:
            data = hr.get_data()
            status = hr.get_status()

            if data["valid"]:
                valid_count += 1
                print("  [%5.1fs] HR=%3dbpm, SpO2=%3d%% (包数:%d, 错误:%d)" % (
                    elapsed / 1000.0,
                    data["heart_rate"],
                    data["spo2"],
                    status["packet_count"],
                    status["err_count"]
                ))
            else:
                invalid_count += 1
                print("  [%5.1fs] 数据无效 (HR=%3d, SpO2=%3d, 包数:%d, 错误:%d)" % (
                    elapsed / 1000.0,
                    data["heart_rate"],
                    data["spo2"],
                    status["packet_count"],
                    status["err_count"]
                ))

            last_print_time = now

    hr.stop_collect()

    print("\n统计：")
    print("  有效数据：%d次" % valid_count)
    print("  无效数据：%d次" % invalid_count)
    print("  数据包数：%d个" % status["packet_count"])
    if valid_count > 0:
        data = hr.get_data()
        print("  最终数据：HR=%dbpm, SpO2=%d%%" % (data["heart_rate"], data["spo2"]))

    return valid_count, invalid_count


def test_force_read(hr):
    """
    brief 测试 force_read() 强制读取功能
    """
    print("\n" + "=" * 60)
    print("[force_read测试] 验证返回缓存数据")
    print("=" * 60)

    hr.start_collect()
    time.sleep_ms(3000)

    print("  测试1：连续3次 force_read()")
    for i in range(3):
        data = hr.force_read()
        print("    第%d次: HR=%d, SpO2=%d, valid=%s" % (
            i + 1, data["heart_rate"], data["spo2"], data["valid"]
        ))
        time.sleep_ms(500)

    hr.stop_collect()
    print("  force_read测试完成")


def test_heartrate():
    """
    brief 心率血氧模块硬件测试主函数
    note 真实场景测试，需要佩戴心率传感器
    """
    print("=" * 60)
    print("心率血氧模块 - 硬件测试")
    print("=" * 60)

    print("\n[需求验证]")
    print("  1. 心率数据采集（bpm）")
    print("  2. 血氧数据采集（%%）")
    print("  3. force_read() 返回缓存")

    print("\n[测试场景]")
    print("  场景1：手指测试（60秒）")
    print("  场景2：force_read测试")

    event_bus = EventBus()

    print("\n[步骤1] 创建Device层模块")
    hr = HeartRateDriver(event_bus=event_bus)
    print("  已创建: HeartRateDriver")

    print("\n[步骤2] 初始化模块")
    try:
        hr.init()
        print("  OK 初始化成功")
    except Exception as e:
        print("  FAIL 初始化失败: %s" % e)
        return

    print("\n[步骤3] 显示配置参数")
    print("  串口: UART%d" % hr.cfg["uart_id"])
    print("  波特率: %d" % hr.cfg["baudrate"])
    print("  采样间隔: %dms" % hr.cfg["sample_ms"])
    print("  预热时间: %d秒" % (hr.cfg["warmup_ms"] // 1000))
    print("  数据包长度: %d字节" % hr.cfg["data_len"])

    v1, i1 = test_scenario(hr, event_bus, "手指测试", 60, "请将手指放在传感器上，持续检测60秒")

    time.sleep_ms(2000)

    test_force_read(hr)

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    print("\n手指测试（60秒）：")
    print("  有效数据：%d次" % v1)
    print("  无效数据：%d次" % i1)

    print("\n验收标准：")
    if v1 > 10:
        print("  手指测试通过（有效数据>10次）")
    else:
        print("  手指测试失败（有效数据<10次）")

    print("\n数据包格式说明：")
    print("  第1字节：数据包头（255）")
    print("  第2-40字节：波形数据")
    print("  第41字节：心率（bpm）")
    print("  第42字节：血氧（%%）")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_heartrate()
