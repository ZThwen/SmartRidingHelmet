# 创建一个最小测试脚本
import sys
sys.path.append("..")
from core.Event_Bus import EventBus
from Drivers.actuator.Audio import AudioDriver

event_bus = EventBus()

# 1. 跳过 HeartRate init

# 2. 初始化 Audio（测试 AT 命令）
audio = AudioDriver(event_bus)
try:
    audio.init()
    print("Audio init 成功！")
except Exception as e:
    print("Audio init 失败：", e)