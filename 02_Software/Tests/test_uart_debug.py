"""
brief UART 初始化对比调试脚本
note 测试不同的 UART 编号是否会导致 Audio init 失败，
     找出问题是 UART9 特有的，还是所有 UART 都会。
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from Drivers.actuator.Audio import AudioDriver
from machine import UART

def test_audio_init(event_bus):
    """测试 Audio init 是否成功"""
    audio = AudioDriver(event_bus)
    try:
        audio.init()
        print("  ✅ Audio init 成功")
        return True
    except Exception as e:
        print("  ❌ Audio init 失败: %s" % e)
        return False

def test_uart(uart_id, event_bus):
    """测试指定 UART 初始化后 Audio 是否成功"""
    print("\n[测试] UART(%d, 115200)" % uart_id)
    print("-" * 40)
    try:
        uart = UART(uart_id, 115200)
        print("  UART%d 初始化完成" % uart_id)
        result = test_audio_init(event_bus)
        uart.deinit()
        print("  UART%d 已释放" % uart_id)
        return result
    except Exception as e:
        print("  UART%d 初始化失败: %s" % (uart_id, e))
        return False

def main():
    print("=" * 60)
    print("UART 初始化对比调试")
    print("=" * 60)
    
    event_bus = EventBus()
    
    # ==================== 基线测试 ====================
    print("\n[基线] 没有 UART 初始化")
    print("-" * 40)
    test_audio_init(event_bus)
    
    # ==================== 测试不同的 UART 编号 ====================
    # STM32F413ZH 支持的 UART：1, 2, 3, 4, 5, 6, 7, 8, 9, 10
    # USART6 是 EC200U 使用的，跳过
    uart_list = [1, 2, 3, 4, 5, 7, 8, 9, 10]
    
    results = {}
    for uart_id in uart_list:
        results[uart_id] = test_uart(uart_id, event_bus)
        time.sleep_ms(100)
    
    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print("\nUART 编号 | Audio init 结果")
    print("-" * 30)
    print("基线（无 UART） | ✅ 成功")
    for uart_id, result in results.items():
        status = "✅ 成功" if result else "❌ 失败"
        print("UART%d | %s" % (uart_id, status))
    
    # 分析结果
    failed_uarts = [uid for uid, ok in results.items() if not ok]
    if failed_uarts:
        print("\n⚠️ 以下 UART 会导致 Audio init 失败：")
        for uid in failed_uarts:
            print("  - UART%d" % uid)
        if 9 in failed_uarts and len(failed_uarts) == 1:
            print("\n结论：只有 UART9 会导致问题，可能是 UART9 特有的硬件冲突")
        else:
            print("\n结论：多个 UART 都会导致问题，可能是全局资源冲突")
    else:
        print("\n✅ 所有 UART 都不会导致 Audio init 失败")
        print("结论：问题可能是 UART9 初始化的时序或其他因素")

if __name__ == "__main__":
    main()
