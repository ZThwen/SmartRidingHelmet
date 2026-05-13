"""
brief 按键驱动测试脚本
note 用于验证 Button.py 的功能是否正常
"""
import sys

from core.Event_Bus import EventBus
from core.config import EVENT_BUTTON_PRESSED, EVENT_BUTTON_ERROR
from Drivers.interface.Button import Button

event_bus = EventBus()
event_bus.debug = True

def on_button_pressed(payload):
    print(f"\n[收到事件] EVENT_BUTTON_PRESSED")
    print(f"  来源: {payload.get('source', 'unknown')}")
    print(f"  时间戳: {payload['timestamp']}")

def on_button_error(payload):
    print(f"\n[收到事件] BUTTON_ERROR")
    print(f"  来源: {payload.get('source', 'unknown')}")
    print(f"  错误信息: {payload.get('error', 'unknown')}")

event_bus.subscribe(EVENT_BUTTON_PRESSED, on_button_pressed)
event_bus.subscribe(EVENT_BUTTON_ERROR, on_button_error)

print("=" * 50)
print("开始测试按键驱动")
print("=" * 50)

button = Button(event_bus)

print("\n[测试 1] 初始化模块")
try:
    button.init()
    print("✓ 初始化成功")
except Exception as e:
    print(f"✗ 初始化失败: {e}")
    sys.exit(1)

print("\n[测试 2] 查看模块状态")
status = button.get_status()
print(f"  is_init: {status['is_init']}")
print(f"  is_busy: {status['is_busy']}")
print(f"  err_count: {status['err_count']}")
print(f"  power_state: {status['power_state']}")

print("\n[测试 3] 测试 tick() 调用")
import time
for i in range(5):
    button.tick()
    event_bus.pump()
    time.sleep(0.1)
print("✓ tick() 调用正常")

print("\n[测试 4] 查看配置参数")
print(f"  引脚 ID: {button.cfg['id']}")
print(f"  引脚模式: {button.cfg['mode']}")
print(f"  上拉/下拉: {button.cfg['pull']}")
print(f"  防抖时间: {button.cfg['debounce_ms']} ms")
print(f"  最大重试: {button.cfg['max_retry']}")

print("\n[测试 5] 手动触发按键中断测试")
print("说明: 请手动按下按键，观察是否触发事件...")
print("等待 10 秒...")
start_time = time.time()
while time.time() - start_time < 10:
    event_bus.pump()
    time.sleep(0.01)

print("\n[测试 6] 连续运行稳定性测试")
print("-" * 50)
for i in range(20):
    button.tick()
    event_bus.pump()
    time.sleep(0.1)
print("✓ 连续运行稳定")

print("\n" + "=" * 50)
print("测试完成")
print("=" * 50)

print("\n最终状态:")
status = button.get_status()
print(f"  is_init: {status['is_init']}")
print(f"  is_busy: {status['is_busy']}")
print(f"  err_count: {status['err_count']}")
print(f"  power_state: {status['power_state']}")
