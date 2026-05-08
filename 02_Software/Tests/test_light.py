"""
brief 光敏传感器驱动测试脚本
note 用于验证 Light.py 的功能是否正常
"""
import sys
sys.path.append("..")

from Event_Bus import EventBus
from config import EVENT_SENSOR_ERROR
from Light import LightSensorDiver

try:
    from config import EVENT_LIGHT_READY
except ImportError:
    EVENT_LIGHT_READY = "LIGHT_READY"

event_bus = EventBus()
event_bus.debug = True

def on_light_ready(payload):
    print(f"\n[收到事件] EVENT_LIGHT_READY")
    print(f"  光照强度: {payload['Light_intensity']}")
    print(f"  有效性: {payload['valid']}")
    print(f"  时间戳: {payload['timestamp']}")

def on_sensor_error(payload):
    print(f"\n[收到事件] EVENT_SENSOR_ERROR")
    print(f"  来源: {payload.get('source', 'N/A')}")
    print(f"  错误信息: {payload.get('error', 'N/A')}")

event_bus.subscribe(EVENT_LIGHT_READY, on_light_ready)
event_bus.subscribe(EVENT_SENSOR_ERROR, on_sensor_error)

print("=" * 50)
print("开始测试光敏传感器驱动")
print("=" * 50)

light = LightSensorDiver(event_bus)

print("\n[测试 1] 初始化模块")
try:
    light.init()
    print("✓ 初始化成功")
except Exception as e:
    print(f"✗ 初始化失败: {e}")
    sys.exit(1)

print("\n[测试 2] 查看模块状态")
status = light.get_status()
print(f"  is_init: {status['is_init']}")
print(f"  is_busy: {status['is_busy']}")
print(f"  err_count: {status['err_count']}")
print(f"  power_state: {status['power_state']}")

print("\n[测试 3] 手动触发 tick() 测试")
print("等待 3 秒让传感器稳定...")
import time
time.sleep(3)

print("\n触发 tick()...")
for i in range(5):
    light.tick()
    event_bus.pump()
    time.sleep(1)

print("\n[测试 4] 查看当前数据")
data = light.get_data()
print(f"  光照强度: {data['light_intensity']}")
print(f"  有效性: {data['valid']}")

print("\n[测试 5] 连续采集测试（10 次）")
print("-" * 50)
for i in range(10):
    light.tick()
    event_bus.pump()
    time.sleep(2)

print("\n" + "=" * 50)
print("测试完成")
print("=" * 50)

print("\n最终状态:")
status = light.get_status()
print(f"  错误计数: {status['err_count']}")
data = light.get_data()
print(f"  最终光照强度: {data['light_intensity']}")
print(f"  数据有效性: {data['valid']}")
