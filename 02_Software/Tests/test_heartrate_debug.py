"""
brief HeartRate init 逐步调试脚本
note 逐步执行 HeartRate init 中的每一行代码，
     每步之后测试 Audio init 是否成功，
     找出具体是哪一行代码导致 AT 通道异常。
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

def main():
    print("=" * 60)
    print("HeartRate init 逐步调试")
    print("=" * 60)
    
    event_bus = EventBus()
    
    # ==================== 测试 0：基线（没有 HeartRate） ====================
    print("\n[测试 0] 基线：没有 HeartRate init")
    print("-" * 40)
    test_audio_init(event_bus)
    
    # ==================== 测试 1：只执行 UART(9, 115200) ====================
    print("\n[测试 1] 只执行 UART(9, 115200)")
    print("-" * 40)
    uart = UART(9, 115200)
    print("  UART9 初始化完成")
    test_audio_init(event_bus)
    uart.deinit()
    print("  UART9 已释放")
    time.sleep_ms(100)
    
    # ==================== 测试 2：UART(9, 115200) + 清空缓冲区 ====================
    print("\n[测试 2] UART(9, 115200) + 清空缓冲区")
    print("-" * 40)
    uart = UART(9, 115200)
    print("  UART9 初始化完成")
    while uart.any() > 0:
        uart.read(uart.any())
    print("  缓冲区已清空")
    test_audio_init(event_bus)
    uart.deinit()
    print("  UART9 已释放")
    time.sleep_ms(100)
    
    # ==================== 测试 3：UART(9, 115200) + 清空缓冲区 + 发送 0xFF ====================
    print("\n[测试 3] UART(9, 115200) + 清空缓冲区 + 发送 0xFF")
    print("-" * 40)
    uart = UART(9, 115200)
    print("  UART9 初始化完成")
    while uart.any() > 0:
        uart.read(uart.any())
    print("  缓冲区已清空")
    uart.write(bytes([0xFF]))
    print("  已发送 0xFF")
    test_audio_init(event_bus)
    uart.deinit()
    print("  UART9 已释放")
    time.sleep_ms(100)
    
    # ==================== 测试 4：UART(9, 115200) + 清空缓冲区 + 发送 0xFF + 等待 500ms ====================
    print("\n[测试 4] UART(9, 115200) + 清空缓冲区 + 发送 0xFF + 等待 500ms")
    print("-" * 40)
    uart = UART(9, 115200)
    print("  UART9 初始化完成")
    while uart.any() > 0:
        uart.read(uart.any())
    print("  缓冲区已清空")
    uart.write(bytes([0xFF]))
    print("  已发送 0xFF")
    time.sleep_ms(500)
    print("  已等待 500ms")
    test_audio_init(event_bus)
    uart.deinit()
    print("  UART9 已释放")
    time.sleep_ms(100)
    
    # ==================== 测试 5：不释放 UART9，测试 Audio init ====================
    print("\n[测试 5] 不释放 UART9，测试 Audio init")
    print("-" * 40)
    uart = UART(9, 115200)
    print("  UART9 初始化完成（不释放）")
    test_audio_init(event_bus)
    uart.deinit()
    print("  UART9 已释放")
    
    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("调试总结")
    print("=" * 60)
    print("请根据上述测试结果判断：")
    print("  - 如果测试 1 失败：UART(9, 115200) 导致问题")
    print("  - 如果测试 2 失败：清空缓冲区导致问题")
    print("  - 如果测试 3 失败：发送 0xFF 导致问题")
    print("  - 如果测试 4 失败：等待 500ms 导致问题")
    print("  - 如果测试 5 失败：UART9 未释放导致问题")

if __name__ == "__main__":
    main()
