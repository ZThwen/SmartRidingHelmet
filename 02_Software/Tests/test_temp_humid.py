"""
brief 温湿度驱动测试脚本
note 用于验证 Temp_Humid.py 的功能是否正常
"""


from core.Event_Bus import EventBus
from core.config import EVENT_TEMP_HUMID_READY, EVENT_SENSOR_ERROR
from Drivers.sensor.Temp_Humid import TempHumidDriver

# 创建事件总线
event_bus = EventBus()
event_bus.debug = True  # 开启调试模式，查看事件订阅日志

# 订阅温湿度数据事件，打印接收到的数据
def on_temp_humid_ready(payload):
    print(f"\n[收到事件] EVENT_TEMP_HUMID_READY")
    print(f"  温度: {payload['temp']} ℃")
    print(f"  湿度: {payload['humid']} %RH")
    print(f"  有效性: {payload['valid']}")
    print(f"  时间戳: {payload['timestamp']}")

# 订阅传感器错误事件
def on_sensor_error(payload):
    print(f"\n[收到事件] EVENT_SENSOR_ERROR")
    print(f"  来源: {payload['source']}")
    print(f"  错误码: {payload['code']}")
    print(f"  错误信息: {payload['error']}")

event_bus.subscribe(EVENT_TEMP_HUMID_READY, on_temp_humid_ready)
event_bus.subscribe(EVENT_SENSOR_ERROR, on_sensor_error)

# 创建温湿度驱动实例
print("=" * 50)
print("开始测试温湿度驱动")
print("=" * 50)

temp_humid = TempHumidDriver(event_bus)

# 测试 1：初始化
print("\n[测试 1] 初始化模块")
try:
    temp_humid.init()
    print("✓ 初始化成功")
except Exception as e:
    print(f"✗ 初始化失败: {e}")
    sys.exit(1)

# 测试 2：查看模块状态
print("\n[测试 2] 查看模块状态")
status = temp_humid.get_status()
print(f"  is_init: {status['is_init']}")
print(f"  is_busy: {status['is_busy']}")
print(f"  err_count: {status['err_count']}")
print(f"  power_state: {status['power_state']}")

# 测试 3：手动触发 tick() 测试数据采集
print("\n[测试 3] 手动触发 tick() 测试")
print("等待 3 秒让传感器稳定...")
import time
time.sleep(3)

# 触发 tick()（需要等待采样间隔到达）
print("\n触发 tick()...")
for i in range(5):
    temp_humid.tick()
    event_bus.pump()  # 处理事件队列
    time.sleep(1)

# 测试 4：查看当前数据
print("\n[测试 4] 查看当前数据")
data = temp_humid.get_data()
print(f"  温度: {data['temp']} ℃")
print(f"  湿度: {data['humid']} %RH")
print(f"  有效性: {data['valid']}")

# 测试 5：连续采集测试
print("\n[测试 5] 连续采集测试（10 次）")
print("-" * 50)
for i in range(10):
    temp_humid.tick()
    event_bus.pump()
    time.sleep(2)  # 等待采样间隔

print("\n" + "=" * 50)
print("测试完成")
print("=" * 50)

# 显示最终状态
print("\n最终状态:")
status = temp_humid.get_status()
print(f"  错误计数: {status['err_count']}")
data = temp_humid.get_data()
print(f"  最终温度: {data['temp']} ℃")
print(f"  最终湿度: {data['humid']} %RH")