"""
brief 初始化顺序验证测试
note 验证 HeartRate 在 quectel 模块之后初始化，AT 通道正常
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from Drivers.actuator.Audio import AudioDriver
from Drivers.network.BLE import BLEDriver
from Drivers.sensor.HeartRate import HeartRateDriver

def main():
    print("=" * 60)
    print("初始化顺序验证测试")
    print("=" * 60)
    
    event_bus = EventBus()
    
    # 测试 1：先 Audio → HeartRate → Audio（应该成功）
    print("\n[测试 1] 先 Audio → HeartRate → Audio")
    print("-" * 40)
    
    audio1 = AudioDriver(event_bus)
    try:
        audio1.init()
        print("  ✅ Audio init 1 成功")
    except Exception as e:
        print("  ❌ Audio init 1 失败: %s" % e)
        return
    
    heart_rate = HeartRateDriver(event_bus)
    try:
        heart_rate.init()
        print("  ✅ HeartRate init 成功")
    except Exception as e:
        print("  ❌ HeartRate init 失败: %s" % e)
        return
    
    audio2 = AudioDriver(event_bus)
    try:
        audio2.init()
        print("  ✅ Audio init 2 成功")
    except Exception as e:
        print("  ❌ Audio init 2 失败: %s" % e)
        return
    
    # 测试 2：验证 BLE 也正常
    print("\n[测试 2] 验证 BLE 也正常")
    print("-" * 40)
    
    ble = BLEDriver(event_bus)
    try:
        ble.init()
        print("  ✅ BLE init 成功")
    except Exception as e:
        print("  ❌ BLE init 失败: %s" % e)
        return
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！初始化顺序正确。")
    print("=" * 60)

if __name__ == "__main__":
    main()
