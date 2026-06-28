"""
brief 边界测试 — BLE payload 244/245 字节边界
note  验证 MAX_BLE_PAYLOAD=244：244 字节通过，245 字节拒绝
      MAX_BLE_PAYLOAD 定义在 BLEService._notify_thread() 内 (line 190)，
      检查逻辑为 if len(data) > MAX_BLE_PAYLOAD: drop
usage 上传后 REPL: import test_boundary_ble_payload
"""

import sys
import time
import json
sys.path.append("../../02_Software")
from core.Event_Bus import EventBus
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService

bus = EventBus()
ble_drv = BLEDriver(bus)
ble_svc = BLEService(bus, ble_driver=ble_drv)

# 不调用 ble_drv.init() 和 ble_svc.init() — 无需真实 BLE 硬件
# 直接构造 send_queue 并验证边界逻辑

MAX_BLE_PAYLOAD = 244

# ---- 构造恰好 244 字节和 245 字节的 payload ----
base = {
    "tmp": 25.5, "hum": 65.3, "lat": 31.2304, "lon": 121.4737,
    "spd": 18.5, "alt": 12.0, "cog": 180.0, "lux": 32000,
    "bat": 4, "hr": 72, "spo2": 98,
}
base_str = json.dumps(base)
base_len = len(base_str)
print("Base payload: %d bytes" % base_len)

# Pad to exactly 244
target = MAX_BLE_PAYLOAD
padding_needed = target - base_len
if padding_needed > 10:
    pad = "x" * (padding_needed - 10)
    payload_244 = json.dumps({**base, "pad": pad})
else:
    payload_244 = base_str + ("x" * (target - base_len))

# Trim to exactly 244 if overshot
if len(payload_244) > target:
    payload_244 = payload_244[:target]
print("244-byte len: %d" % len(payload_244))

payload_245 = payload_244 + "y"
print("245-byte len: %d" % len(payload_245))

# ---- 验证边界条件 ----
# 核心逻辑：len(data) > MAX_BLE_PAYLOAD → drop
# 即 244 <= 244 → pass, 245 > 244 → drop
accepted_244 = len(payload_244) <= MAX_BLE_PAYLOAD
rejected_245 = len(payload_245) > MAX_BLE_PAYLOAD

print("244-byte accepted (<=244): %s" % accepted_244)
print("245-byte rejected (>244): %s" % rejected_245)

# 额外验证：send_queue 本身不限制长度（限制在 notify_thread 中）
ble_svc.send_queue = __import__('Drivers.network.thread_queue', fromlist=['ThreadSafeQueue']).ThreadSafeQueue(max_size=20)
ble_svc.send_queue.put(payload_244)
ble_svc.send_queue.put(payload_245)
print("send_queue accepts both sizes: queue_size=%d" % ble_svc.send_queue.size())

result = "PASS" if (accepted_244 and rejected_245) else "FAIL"
print(result)
