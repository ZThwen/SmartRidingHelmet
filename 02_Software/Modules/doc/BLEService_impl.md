# BLEService 实现路径

> **所属层次**：Service 层（业务服务层）
> **实现状态**：✅ v3 已实现（2026-06-16 环形缓冲区 + 快照合并 + UUID 分发）
> **负责人员**：郑皓文

---

## 1. 模块概述

### 做什么
1. **接收**：注册 BLE 回调，将接收到的原始数据写入环形缓冲区，tick 中解析并路由到 ControlService / NavigationService
2. **发送**：收集传感器数据、控制状态、报警事件，通过 notify 线程推送到手机

### 不是什么
- **不是**BLE 硬件驱动（BLEDriver 负责 GATT 服务配置、广播、notify 底层调用）
- **不是**指令执行（ControlService 负责）
- **不是**传感器采集（各 Sensor Driver 负责）

### 一句话
**BLE 数据的唯一入口和出口**：中断写 buffer → tick 解析路由 → 快照合并推送。

---

## 2. 文件位置

```
02_Software/Modules/ble_service.py
```

---

## 3. 架构设计

### 3.1 双线程架构

```
┌─────────────────────────────────────────────────────────────┐
│                  BLE 中断 (modem 线程)                       │
│  _ble_callback(evt)                                          │
│    ├─ EVT_CONNECTED → ctx["is_connected"] = True             │
│    ├─ EVT_DISCONNECTED → ctx["is_connected"] = False         │
│    └─ EVT_VAL_DATA → cmd_buffer.put(raw) + cmd_ready = True │
│                       ← 微秒级返回                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  主循环 (main 线程)                          │
│                                                              │
│  ble_svc.tick():                                             │
│    ├─ 检查 cmd_ready                                         │
│    ├─ drain cmd_buffer → _parse_and_route()                  │
│    │   └─ 按 UUID 分发 → EventBus.publish                    │
│    ├─ 快照推送（合并控制状态为 1 条 notify）                  │
│    └─ force_push（连接后立即推送传感器数据）                  │
│                                                              │
│  event_bus.pump():                                           │
│    └─ 处理各模块事件                                         │
│                                                              │
│  notify_thread (后台线程):                                   │
│    └─ send_queue.get() → BLEDriver.notify_data()             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 数据流

**接收流（手机 → 板子）**：
```
手机 BLE 写入 → BLEDriver._ble → BLEService._ble_callback()
  → cmd_buffer.put({"uuid": uuid, "raw": value})
  → cmd_ready = True
  → tick() drain → _parse_and_route()
    → uuid == char_nav  → EventBus(EVENT_NAV_CMD)
    → uuid == char_ctrl → EventBus(EVENT_RIDE_CONTROL)
    → uuid == char_ack  → EventBus(EVENT_BLE_ALARM_ACK)
```

**发送流（板子 → 手机）**：
```
传感器事件 → BLEService._on_xxx() → 更新 _data
控制状态事件 → BLEService._on_control_state() → 快照合并
报警事件 → BLEService._on_alarm() → send_queue.put()
tick() 周期 → _enqueue_merged() → send_queue.put()
notify_thread → send_queue.get() → BLEDriver.notify_data()
```

---

## 4. 事件订阅

| 事件 | 回调 | 用途 |
|------|------|------|
| `EVENT_BLE_CONNECTED` | `_on_connected` | 标记连接状态，触发 force_push |
| `EVENT_BLE_DISCONNECTED` | `_on_disconnected` | 清除连接状态，清空队列 |
| `EVENT_TEMP_HUMID_READY` | `_on_temp_humid` | 缓存温湿度数据 |
| `EVENT_IMU_READY` | `_on_imu` | 缓存加速度数据 |
| `EVENT_GNSS_READY` | `_on_gnss` | 缓存位置/速度数据 |
| `EVENT_LIGHT_READY` | `_on_light` | 缓存光照数据 |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm` | 立即推送报警通知 |
| `EVENT_ALARM_CANCELED` | `_on_alarm_canceled` | 推送报警取消通知 |
| `EVENT_CONTROL_STATE_CHANGED` | `_on_control_state` | 快照合并（不直接入队） |

---

## 5. BLE 消息类型

| t | 内容 | 格式 | 来源 |
|---|------|------|------|
| 0 | 传感器数据 | `{"t":0,"d":{tmp,hum,lat,lon,spd,alt,cog,lux}}` | tick 周期推送 |
| 5 | 报警触发 | `{"t":5,"a":1/2,"l":1-3}` | EVENT_ALARM_TRIGGERED |
| 6 | 报警取消 | `{"t":6,"d":{}}` | EVENT_ALARM_CANCELED |
| 7 | 控制状态（合并） | `{"t":7,"m":0/1,"b":0-100,"v":0-5,"p":0-3}` | 快照合并推送 |
| 99 | 心跳 | `{"t":99,"d":{"s":"ok"}}` | keepalive 周期 |

---

## 6. 环形缓冲区（cmd_buffer）

### 6.1 设计

```python
# __init__ 中初始化
self.cmd_buffer = ThreadSafeQueue(max_size=16)
self.cmd_ready = False
```

- 基于 `ThreadSafeQueue`（线程安全，满时丢弃最旧元素）
- 最大 16 条，每条是原始 hex 字符串
- `cmd_ready` 标志：中断写入时设 True，tick drain 后设 False

### 6.2 为什么需要环形缓冲区

| 问题 | 当前方案 | 旧方案 |
|------|---------|--------|
| 中断阻塞 | 只写 buffer，微秒级返回 | JSON 解析 + EventBus publish + handler 执行 |
| 指令堆积 | buffer 满时丢弃最旧，不无限增长 | EventBus 队列无界增长 |
| 主循环控制 | tick 中主动 drain，受控处理 | pump 中被动触发，无时间控制 |

---

## 7. 快照合并推送（_ctrl_snapshot）

### 7.1 设计

```python
self._ctrl_snapshot = {
    "m": 0, "b": 0,   # t=7: 灯光模式 + 亮度
    "v": 5,            # t=8: 音量
    "p": 0,            # t=9: 电源模式
    "dirty": False,    # 是否有未推送的控制状态
}
```

### 7.2 工作流程

```
EVENT_CONTROL_STATE_CHANGED 到达
  → _on_control_state(payload)
    → 更新快照字段（m/b/v/p）
    → dirty = True

tick() 周期
  → if dirty:
    → send_queue.put('{"t":7,"m":1,"b":50,"v":5,"p":0}')
    → dirty = False
```

### 7.3 为什么需要快照合并

| 场景 | 旧方案（3 条） | 新方案（1 条） |
|------|---------------|---------------|
| 1 次 light_on | 3 条 notify（t=7 + t=8 + t=9） | 1 条 notify（合并） |
| 1 秒 5 次指令 | 15 条 notify 队列堆积 | 最多 1 条（快照覆盖） |
| 队列压力 | 高（可能爆炸） | 低（恒定 1 条/tick） |

### 7.4 UUID 分发逻辑（v3 新增）

根据 BLE 特征值 UUID 分发到不同事件：

| UUID | 特征值 | 事件 | 说明 |
|------|--------|------|------|
| FFF2 | char_nav | EVENT_NAV_CMD | 导航指令 |
| FFF3 | char_ctrl | EVENT_RIDE_CONTROL | 控制指令 |
| FFF4 | char_ack | EVENT_BLE_ALARM_ACK | 报警确认 |

```python
def _parse_and_route(self, item):
    uuid = item.get("uuid")
    value = item.get("raw", "")

    if uuid == self._ble.cfg["char_nav"]:
        self.event_bus.publish(EVENT_NAV_CMD, {"raw": value})
    elif uuid == self._ble.cfg["char_ctrl"]:
        self.event_bus.publish(EVENT_RIDE_CONTROL, {"raw": value})
    elif uuid == self._ble.cfg["char_ack"]:
        self.event_bus.publish(EVENT_BLE_ALARM_ACK, {"raw": value})
```

**优势**：
- 按 UUID 精确路由，无需解析 JSON
- 新增特征值只需扩展 if/elif 分支
- 每个特征值独立事件，ControlService/NavigationService/AlarmService 各自处理

---

## 8. 四元组

```python
# cfg：静态配置
cfg = {
    "upload_interval_ms": BLE_UPLOAD_INTERVAL_MS,  # 传感器数据推送间隔
    "keepalive_ms": BLE_KEEPALIVE_MS,               # 心跳间隔
    "queue_max_size": 20,                            # 发送队列最大容量
}

# ctx：运行时上下文
ctx = {
    "is_init": False,
    "thread_running": False,
    "last_upload": 0,
    "last_keepalive": 0,
    "ble_connected": False,
    "err_count": 0,
    "force_push": False,
    "consecutive_errors": 0,
}

# _data：当前数据（传感器缓存）
_data = {
    "latest_temp": None,
    "latest_humid": None,
    "latest_ax": None, "latest_ay": None, "latest_az": None,
    "latest_lat": None, "latest_lon": None, "latest_alt": None,
    "latest_spd": None, "latest_cog": None,
    "latest_lux": None,
}
```

---

## 9. 依赖的 Device 驱动

| 驱动 | 导入路径 | 调用方法 |
|:----|:--------|:---------|
| BLE | `Drivers.network.BLE.BLEDriver` | `ble_driver.notify_data(json_str)` |
| ThreadSafeQueue | `Drivers.network.thread_queue` | `ThreadSafeQueue(max_size)` |

---

## 10. 约束规则

| 规则 | 说明 |
|:----|:-----|
| **中断快速返回** | `_ble_callback` 只写 buffer + 设 flag，不做 JSON 解析，不触发 EventBus |
| **tick() < 5ms** | drain buffer + 快照推送，每条 handler < 0.1ms |
| **notify 线程不阻塞主循环** | 后台线程消费 send_queue，主循环只 put |
| **快照覆盖** | 密集指令时最新状态覆盖旧状态，避免队列堆积 |
| **断连清队列** | `EVENT_BLE_DISCONNECTED` 时清空 send_queue |
| **熔断保护** | 连续 10 次 notify 失败后暂停 500ms |

---

## 11. 测试状态

### 11.1 已测试通过

| 测试项 | 结果 | 说明 |
|:------|:----:|:------|
| BLE 初始化 + 广播 | ✅ | GATT 服务/特征值配置正确 |
| 手机连接 + MTU 协商 | ✅ | MTU=247，payload ≤ 244 字节 |
| notify 推送传感器数据 | ✅ | t=0 格式正确 |
| 报警推送（压缩格式） | ✅ | t=5 ≤ 15 字节，避免 CME ERROR: 53 |
| 断连重连 | ✅ | 清队列 + force_push |
| 快照合并推送 | ✅ | Phase 3 已验证 |
| 环形缓冲区 drain | ✅ | Phase 3 已验证 |

### 11.2 待测试

| 测试项 | 优先级 | 说明 |
|:------|:-----:|:------|
| 密集指令不崩溃 | 高 | 1 秒 10 次指令，验证 buffer drain + 快照合并 |
| notify 队列不爆炸 | 高 | 密集指令后队列大小恒定 |
| BLE 回调快速返回 | 高 | 中断中不阻塞 |

---

## 12. 开发中遇到的问题

### 12.1 EventBus 注入字段膨胀 payload

**现象**：ControlState 消息 16 字节，经 EventBus 后变成 66 字节，超出 ATT_MTU。

**原因**：`EventBus.publish()` 自动注入 `source` 和 `timestamp` 字段。

**解决**：`_on_control_state` 中剥离多余字段，只保留 `("t", "m", "b", "v", "p")`。

### 12.2 缺少 ble_driver 参数导致 notify 静默失败

**现象**：所有 notify 都不发送，无报错。

**原因**：`BLEService(event_bus)` 没传 `ble_driver`，后台线程 `self._ble=None`。

**解决**：构造签名 `BLEService(event_bus, ble_driver=ble_driver)`。

### 12.3 notify 队列爆炸导致系统死机

**现象**：密集指令后系统崩溃。

**原因**：每次指令推送 3 条 notify（t=7 + t=8 + t=9），密集时队列堆积 15+ 条 AT 命令。

**解决**：快照合并为 1 条 + 控制状态快照 coalescing。
