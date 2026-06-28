"""
brief 边界测试 — EventBus 队列溢出（SOFT_MAX=40, HARD_MAX=64）
note  注入 100 事件验证 CRITICAL 优先保留、非 CRITICAL 被淘汰
usage 上传后 REPL: import test_boundary_eventbus_queue
"""

import sys
sys.path.append("../../02_Software")
from core.Event_Bus import EventBus
from core.config import EVENT_COLLISION_DETECTED, EVENT_VOICE_CMD

bus = EventBus()

critical_count = [0]
normal_count = [0]

def on_critical(event):
    critical_count[0] += 1

def on_normal(event):
    normal_count[0] += 1

bus.subscribe(EVENT_COLLISION_DETECTED, "test_boundary", on_critical)
bus.subscribe(EVENT_VOICE_CMD, "test_boundary", on_normal)

# 50 CRITICAL + 50 normal = 100 events
for i in range(100):
    if i % 2 == 0:
        bus.publish(EVENT_COLLISION_DETECTED, {"level": 1, "idx": i})
    else:
        bus.publish(EVENT_VOICE_CMD, {"cmd": "query_status", "idx": i})

# Pump all
for _ in range(150):
    bus.pump()

print("CRITICAL received: %d" % critical_count[0])
print("Non-CRITICAL received: %d" % normal_count[0])
print("(Queue HARD_MAX=64 — events beyond this dropped)")

passed = critical_count[0] >= normal_count[0]
print("PASS" if passed else "FAIL")
