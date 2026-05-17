# CloudService 实现路径

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-NET-01 骑行数据上传、F-NET-02 紧急报警推送、F-NET-03 远程配置下发
> **实现状态**：✅ **v1 已实现**（2026-05-17 E2E 测试通过）
> **负责人员**：已完成

---

## 1. 模块概述

### 做什么
将传感器数据打包上传到云端，将紧急报警立即推送，接收云端配置下发并转发到各模块。

### 不是什么
- **不是**网络连接的实现（那是 `Drivers/network/Network.py` 的事）
- **不是**MQTT 协议的实现（那是 `Drivers/network/MQTT.py` 的事）
- **不是**碰撞检测或报警联动（那是 CollisionService / AlarmService 的事）
- **不是**LCD 显示更新（那是 DisplayService 的事）

### 一句话
**数据网关**：收传感器事件 → 打包 → 交给 MQTT 线程上传；收到云端消息 → 解析 → 发布配置更新。

---

## 2. 文件位置

```
02_Software/Modules/cloud_service.py                     # 本模块
02_Software/Drivers/network/Network.py                    # 先决依赖 — 4G 网络封装
02_Software/Drivers/network/MQTT.py                       # 先决依赖 — MQTT 客户端封装
02_Software/Drivers/network/thread_queue.py               # 先决依赖 — 线程安全队列工具类
```

**先决条件**：`Network.py`、`MQTT.py` 和 `thread_queue.py` 需要在 CloudService 之前或同步完成。

---

## 3. 依赖的模块

### 3.1 Device 驱动

| 驱动 | 路径 | 调用方法 | 用途 |
|:----|:----|:--------|:-----|
| Network | `Drivers.network.Network.NetworkDriver` | `connect()` / `disconnect()` / `is_connected()` | 4G 网络管理 |
| MQTT | `Drivers.network.MQTT.MQTTDriver` | `connect()` / `publish(topic, data)` / `set_callback(fn)` | 数据上下行 |

### 3.2 标准库

| 库 | 用途 |
|:--|:-----|
| `_thread` | 创建网络线程 |
| `ThreadSafeQueue` | 主循环与网络线程间数据缓冲（`Drivers/network/thread_queue.py`） |
| `ujson` | JSON 序列化上报数据 |
| `time` / `utime` | 时间戳、周期控制 |

---

## 4. 事件订阅

| 事件 | 回调方法 | 做什么 |
|:----|:--------|:-------|
| `EVENT_TEMP_HUMID_READY` | `_on_temp_humid(payload)` | 缓存温湿度，等待 tick() 定时打包 |
| `EVENT_IMU_READY` | `_on_imu(payload)` | 缓存加速度，等待 tick() 定时打包 |
| `EVENT_GNSS_READY` | `_on_gnss(payload)` | **仅缓存** GPS 并更新骑行扩展，**不触发上传**；上传由 tick() 定时触发 |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm(payload)` | **立即推送**报警到云端；根据 level 区分碰撞/SOS；collision_count++ |
| `EVENT_CONFIG_UPDATE` | `_on_config_update(payload)` | 更新上传周期 / gps_track_max 等内部参数 |

---

## 5. 事件发布

| 事件 | 发布时机 |
|:----|:--------|
| `EVENT_NETWORK_CONNECTED` | 4G 网络连接成功 |
| `EVENT_NETWORK_DISCONNECTED` | 网络断开 |
| `EVENT_DATA_UPLOAD_SUCCESS` | 数据上传成功 |
| `EVENT_DATA_UPLOAD_FAILED` | 数据上传失败 |
| `EVENT_CONFIG_UPDATE` | 收到云端配置下发，**转发**给其他模块 |

---

## 6. 数据打包格式

### 6.1 周期性传感器数据（每 2s 上传一次）

上传时机由 **tick()** 按 `CLOUD_UPLOAD_INTERVAL_MS`（默认 2000ms）定时触发。
不依赖 GNSS 定位状态——室内无 GPS 时仍可上传温湿度和加速度。

```json
{
    "Temp": 28.5,
    "Humi": 65.2,
    "G-Sensor": {"X": 0.123, "Y": -0.456, "Z": 9.812, "total": 9.823},
    "GNSS": {"lat": 22.5431, "lon": 113.9523},
    "total_distance": 12.345,
    "max_speed": 35.0,
    "total_ascent": 85.2,
    "collision_count": 0,
    "timestamp": 12345678
}
```

**字段 null 规则**：未收到对应传感器事件时，字段输出 `null`（而非 0）。
例如首次启动时若 Temp_Humid 尚未采集，`"Temp": null, "Humi": null`。
加加速度和 GNSS 同理——`ujson.dumps(None)` → `null`。

**打包逻辑**：CloudService 内部缓存最近一次温湿度、IMU 和 GNSS 数据，初始均为 `None`。
tick() 定时从缓存中取值拼装 JSON 入队，主线程不做任何网络 I/O。

### 6.2 紧急报警数据（立即推送）

收到 `EVENT_ALARM_TRIGGERED` 时 **立即入队**，不等待 tick 上传周期。
数据来自 AlarmService，CloudService 只附加上最新 GNSS 位置：

```json
{
    "alarm_type": "collision",   // 来自 AlarmService: "collision" / "sos"
    "level": 2,                  // 1-3，level 3 等同于 SOS
    "location": {"lat": 22.5431, "lon": 113.9523},  // CloudService 附加上次缓存
    "timestamp": 12345678
}
```

**注意**：报警数据需要附带 CloudService 缓存的最新一次 GNSS 位置。
若从未收到过 GNSS 定位（室内环境），`location` 字段输出 `null`。

---

## 7. 骑行数据扩展（路线 + 总结）

CloudService 内部维护累加字段，随传感器数据一起上传：

| 字段 | 来源事件 | 计算方式 |
|:----|:--------|:--------|
| `total_distance` | `EVENT_GNSS_READY` | 累加相邻两点 Haversine 距离 |
| `max_speed` | `EVENT_GNSS_READY` | 和上一次 `speed_kmh` 比大小 |
| `ride_duration` | 系统计时 | v2 计划（需状态机就绪） |
| `total_ascent` | `EVENT_GNSS_READY` | 累加海拔正差值 |
| `collision_count` | `EVENT_COLLISION_DETECTED` | 每次 +1 |
| `gps_track` | `EVENT_GNSS_READY` | N 个 `{lat, lon}` 点队列，上报后清空 |

---

## 8. 网络通信架构

### 8.1 架构总览

```
┌─ 主循环（主线程）──────────────────────┐   send_queue   ┌─ 网络线程（独立 _thread）──────┐
│                                       │    (Queue)     │                              │
│  Sensors → 事件 → CloudService        │                │  Network.connect()           │
│    _on_temp_humid → 缓存              │   json_str     │  MQTT.connect()              │
│    _on_imu → 缓存                     │◄──────────────►│  while running:              │
│    _on_gnss → 拼装 JSON → put()       │                │    data = send_queue.get()   │
│    _on_collision → 报警JSON → put()   │                │    MQTT.publish(data)        │
│                                       │                │  MQTT callback →             │
│  event_bus.pump()  ← 所有回调触发      │                │    EVENT_CONFIG_UPDATE       │
└───────────────────────────────────────┘                └──────────────────────────────┘
```

### 8.2 线程分工

| 线程 | 职责 | 规则 |
|:----|:-----|:-----|
| **主线程**（主循环） | 收事件 → 拼装 JSON → `send_queue.put()` | **不入队就返回**，绝不阻塞 |
| **网络线程**（`_thread`） | `send_queue.get()` → `MQTT.publish()` | 只负责发送，**不知道数据含义** |
| `send_queue` | `queue.Queue` 线程安全队列 | 主线程放、网络线程取 |

### 8.3 各模块职责

| 模块 | 层级 | 做什么 | 不做什么 |
|:----|:----|:-------|:---------|
| **Network.py** | Device | 封装 `quectel.Network`+`net`：SIM 检测、4G 附着、连接状态、信号强度 | 不关心数据内容，不发布事件 |
| **MQTT.py** | Device | 封装 `umqtt` 客户端：连接 broker、publish、subscribe、消息回调 | 不关心数据含义，不做业务逻辑 |
| **CloudService** | Service | 收事件 → 打包 JSON → 入队；收云端配置 → 转发 `EVENT_CONFIG_UPDATE` | 不发网络包，不做 MQTT 协议细节 |

### 8.4 Network.py 内容

纯硬件封装，调用 `quectel.Network` 原生 API + `net.csqQueryPoll()`：

```
from quectel import Network
import net as net_api

class NetworkDriver(BaseModule):
    cfg:   {connect_timeout_ms, check_interval_ms, max_retry}
    ctx:   {is_init, net_state, last_tick, err_count, power_state}
    _data: {ip, rssi, sim_present, valid}

    init():          net = Network() → net.init() → net.query_usim()
    connect(tmo):    net.attach() → 轮询 net.is_connected() 直到成功
    disconnect():    net.deinit()
    is_connected():  net.is_connected()
    set_apn(apn):    net.set_apn(apn, user, pwd)
    get_rssi():      net_api.csqQueryPoll()  # 返回 0-31
```

### 8.5 MQTT.py 内容

纯协议封装，调用 `umqtt` 客户端：

```
class MQTTDriver(BaseModule):
    cfg:   {broker, port, client_id, user, password, keepalive, max_retry}
    ctx:   {is_init, is_connected, last_tick, err_count, power_state}
    _data: {connected, valid}

    init(broker, port, client_id, user, pwd):  创建 MQTTClient 实例
    connect():           连接 broker，返回 bool
    publish(topic, payload):  发送数据
    set_callback(fn):    设置消息回调 fn(topic, msg)
    disconnect():        断开连接
```

---

## 9. MQTT 实现原理

### 9.1 MQTT 是什么

MQTT 是一种 **发布/订阅** 模式的物联网通信协议。对比 HTTP：

| | MQTT | HTTP |
|:--|:-----|:------|
| 连接方式 | **长连接**（一直连着） | 短连接（每次请求新建） |
| 通信方向 | **双向**（设备↔服务器都可以主动发） | 单向（只能客户端请求，服务器被动响应） |
| 消息模式 | 发布/订阅（一个发、多个收） | 请求/响应（一问一答） |
| 适合场景 | 传感器持续上报 + 云端随时下发指令 | 网页/App 向服务器查询数据 |
| 开销 | 极低（消息头最小 2 字节） | 较大（每次 HTTP 头几百字节） |

### 9.2 核心概念

```
┌────────────────────────────────────────────────────┐
│                    MQTT Broker                      │
│                 （消息服务器，如 ConnectLab）         │
│                                                     │
│  订阅者列表:                                        │
│    topic "helmet/data"   → [云端存储服务]           │
│    topic "helmet/config" → [头盔 CloudService]      │
│                                                     │
└──┬────────────────────────────────────┬─────────────┘
   │ publish("helmet/data", json)       │ publish("helmet/config", {...})
   │                                    │
┌──▼──────────────┐          ┌──────────▼──────────┐
│   头盔 (Publisher) │          │   云端 (Subscriber)  │
│   CloudService   │          │   ConnectLab / 后端  │
│   发布传感器数据   │          │   接收并存入数据库    │
└─────────────────┘          └─────────────────────┘

  还支持反向：
  ┌──────────▼──────────┐     publish("helmet/config", {...})
  │   云端 (Publisher)  │─────────────────────────────┐
  │   下发参数配置      │                              │
  └─────────────────────┘                              │
                                                  ┌──▼──────────────┐
                                                  │   头盔 (Subscriber)│
                                                  │   CloudService    │
                                                  │   更新配置参数     │
                                                  └─────────────────┘
```

**关键术语**：

| 术语 | 含义 | 类比 |
|:----|:-----|:-----|
| **Broker** | 消息服务器，所有消息经过它转发 | 邮局 |
| **Topic** | 消息主题，发布者指定、订阅者按主题接收 | 信箱编号 |
| **Publish** | 发布者发消息到某个 topic | 投信到信箱 |
| **Subscribe** | 订阅者声明想收哪个 topic 的消息 | 告诉邮局我要收哪个信箱的信 |
| **Callback** | 订阅后，有消息到达时自动触发的函数 | 收到信自动响铃 |

### 9.3 发送流程（头盔→云端）

```
主线程（事件驱动）                           网络线程（独立 _thread）
─────────────────────                      ─────────────────────────

_on_gnss_ready(payload):
  ├─ 拼装 JSON: {
  │    "Temp": 28.5,
  │    "Humi": 65.2,
  │    "GNSS": {"lat": 22.54, "lon": 113.95}
  │  }
  ├─ send_queue.put(json_str)  ──────→  send_queue.get()
  └─ 写 SD 卡备份                               │
                                         mqtt.publish(
                                           topic="helmet/data",
                                           payload=json_str
                                         )
                                              │
                                         网络层（4G）
                                              │
                                         ConnectLab Broker
                                              │
                                         云端后端收到 → 存入数据库
```

**注意**：`mqtt.publish()` 是在已建立的长连接上直接发一小段数据包，不是 HTTP 那种"发完就断"。

### 9.4 接收流程（云端→头盔）+ 配置下发

```
云端后台下发配置：
  publish("helmet/config", '{"target":"gnss","sample_ms":5000}')

       │
  ConnectLab Broker → 4G 网络 → EC200U 模组

       │
  网络线程中 mqtt.check_msg() 检测到新消息
       │
  MQTT 回调函数被触发 → _on_mqtt_message(topic, msg):

     config = ujson.loads(msg)                   ← 解析 JSON
     event_bus.publish(EVENT_CONFIG_UPDATE, config)  ← 转发为系统事件
       │
  event_bus.pump() 分发事件给所有订阅者
       │
  ┌────┴──────────────────────────────────────┐
  │  Gnss._on_config_update(payload):         │
  │    self.cfg["sample_ms"] = 5000           │
  │  Temp_Humid._on_config_update(payload):   │
  │    self.cfg["sample_ms"] = 5000           │
  │  ...其他模块同理                           │
  └───────────────────────────────────────────┘
```

**关键**：`check_msg()` 是非阻塞的，每次网络线程循环调用一次。有消息就触发回调，没有就立即返回继续发送队列数据。所有其他模块（Temp_Humid、IMU、GNSS、LED、Audio 等）的 `_on_config_update` 都订阅 `EVENT_CONFIG_UPDATE`，按 `target` 字段决定是否应用。

### 9.5 未来扩展：HTTP 骑行记录 App

头盔端 **不需要改任何代码**。HTTP 加在 **云端层面**：

```
头盔 ──MQTT──→ ConnectLab ──→ 云端数据库
                                     │
                                REST API（HTTP）
                                     │
                              ┌──────┴──────┐
                              │             │
                            Web 页面   骑行记录 App
```

| 场景 | 方案 | 理由 |
|:----|:-----|:------|
| 头盔上传数据 | **MQTT** | 一直在线，随时发，省电省流量 |
| 云端下发配置 | **MQTT** | 服务器主动推送，HTTP 做不到 |
| App 查看骑行记录 | **HTTP** | App 只在打开时才请求数据，无需长连接 |

### 9.6 整体数据链路全景

```
头盔端（MicroPython）                         云端（服务器）
─────────────────                         ────────────────

传感器 → 事件 → CloudService → MQTT ────→ ConnectLab
                                             │
                                             ├── 实时消息 → 告警推送
                                             │
                                             └── 存入数据库
                                                     │
                                                REST API（HTTP/HTTPS）
                                                     │
                                             ┌───────┴───────┐
                                             │               │
                                           Web 页面     骑行记录 App
```

---

## 10. SD 卡缓存策略（v2 计划）

> v1 暂不实现，以下为 v2 的设计思路。

### 写入时机
每次 `send_queue.put(data)` 的同时，将 data 追加写入 SD 卡文件。

### 读取时机
网络重连成功后，从 SD 卡文件按行读取，逐条发送到 MQTT。发送完毕清空文件。

### 文件格式
每行一个 JSON 字符串，便于追加写入和逐行读出。

### 策略建议
- 文件名：`/sd/helemt_log.txt`
- 每次重连后发送完毕即清空
- 文件超过一定大小（如 100KB）后截断旧数据

---

## 11. 实现步骤（按顺序）

### 阶段 A：先决依赖 — 写 `Drivers/network/thread_queue.py`

1. 实现 `ThreadSafeQueue` 类：put() / get(timeout_ms) / size() / clear()
2. 基于 `_thread.allocate_lock` + `_thread.allocate_semaphore` 实现
3. 满队列时丢弃最旧元素，永不阻塞主线程
4. 参考 `examples/thread.py` 的生产者消费者模式

### 阶段 B：搭 CloudService 骨架

1. 继承 `BaseModule`，类名 `CloudService`，`self.name = "cloud"`
2. 定义 `cfg`（`upload_interval_ms` / `gps_track_max` / `max_retry`）
3. 定义 `ctx`（网络状态、MQTT 状态、线程标志等）
4. 定义 `_data`（传感器缓存初始 None + 骑行扩展字段）
5. 声明 `self.network` / `self.mqtt` / `self.send_queue` 为 None

### 阶段 C：实现 init()

**实际实现与设计差异说明**：
- Network/MQTT 的 `init()` 和 `connect()` 在主线程完成（AT 指令需要主线程栈空间）
- 网络线程只做 `publish()` 和 `check_msg()`，不调任何 AT 指令
- `set_callback()` 在 init 阶段设置，后续网络线程不再调用

1. 创建 `NetworkDriver()` 和 `MQTTDriver()` 实例
2. 主线程调 `net.init()` + `mqtt.init()` + `mqtt.set_callback()`
3. 主线程调 `net.connect()` + `mqtt.connect()` + `mqtt.subscribe(CONFIG_TOPIC)`
4. 创建 `ThreadSafeQueue(max_size=100)`
5. 订阅 EVENT_TEMP_HUMID_READY / EVENT_IMU_READY / EVENT_GNSS_READY / EVENT_ALARM_TRIGGERED
6. 启动网络线程 `_thread.start_new_thread(self._network_thread, ())`
7. 设置 `is_init = True`

### 阶段 D：实现 tick() 定时上传

1. 时间片控制（基于 `time.ticks_diff`）
2. 从 `_data` 缓存中取值拼装 JSON（未读到的字段为 None → `null`）
3. `send_queue.put(ujson.dumps(payload))` 入队

### 阶段 E：实现事件回调

**`_on_temp_humid(payload)`**
1. 校验 valid
2. 缓存 temp, humid 到 `_data`

**`_on_imu(payload)`**
1. 校验 valid
2. 缓存 acc_x, acc_y, acc_z, acc_total 到 `_data`

**`_on_gnss(payload)`**
1. 校验 valid
2. 缓存 GPS 到 `_data["latest_gnss"]`（**不入队**）
3. 更新骑行扩展：Haversine 距离 / max_speed / total_ascent / gps_track

### 阶段 F：实现报警回调

**`_on_alarm(payload)`**
1. 从 AlarmService 获取 alarm_type + level
2. 附加上缓存的最新 GPS 位置（可能 None → location=null）
3. 拼装报警 JSON → **立即** `send_queue.put(json_str)`（不走 tick 周期）
4. 若 `alarm_type == "collision"` 则 `collision_count++`

### 阶段 G：实现网络线程 `_network_thread()`

```
self.network.init()
self.mqtt.init()
self.mqtt.set_callback(self._on_mqtt_message)

while 线程运行中:
    # 1. 确保网络连接
    if not net.is_connected():
        net.connect() + mqtt.connect() + subscribe(CONFIG_TOPIC)
        publish(EVENT_NETWORK_CONNECTED)

    # 2. 出队发送
    data = send_queue.get(timeout_ms=500)
    if data:
        mqtt.publish(DATA_TOPIC, data)
        publish(EVENT_DATA_UPLOAD_SUCCESS/FAILED)

    # 3. 检查下行消息
    mqtt.check_msg()
```

### 阶段 H：实现 MQTT 消息回调

```
_on_mqtt_message(topic, msg):
    config = ujson.loads(msg)
    event_bus.publish(EVENT_CONFIG_UPDATE, config)
```

### 阶段 I：实现辅助方法

- `_haversine(lat1, lon1, lat2, lon2)` → float（球面距离 km）
- `get_data()` → 数据快照
- `get_status()` → 状态快照
- `_on_config_update(payload)` → 更新 cfg 参数

---

## 12. 约束规则

| 规则 | 说明 |
|:----|:-----|
| **主循环不阻塞** | tick() 只入队、不发包。发包在独立线程 |
| **网络隔离** | Network 和 MQTT 只通过 `Drivers/network/` 访问，不直接 import quectel |
| **SD 卡可靠** | 网络断时数据落 SD 卡，不上传到内存队列（避免内存溢出） |
| **报警优先** | 报警数据不排周期队列，直接插队优先发送 |
| **回调不阻塞** | MQTT 回调在网络线程运行，只做 JSON 解析 + publish 事件，不耗时 |
| **配置转发** | 收到云端配置后发布 `EVENT_CONFIG_UPDATE`，不直接改其他模块的 cfg |

---

## 13. 附录：Network.py / MQTT.py 结构参考

见第 8.4 节和 8.5 节。

---

## 14. 开发中遇到的问题

### 14.1 _thread 栈溢出（AT 指令吃栈深）

**现象**：在 `_thread` 中调用 `Network.init()` / `MQTT.connect()` 时崩溃。

**原因**：EC200U MicroPython 的 `_thread` 默认栈过小，AT 指令（`net.attach()`、MQTT 协议握手等）需要较大的调用栈。

**解决**：
1. 所有 AT 指令移到主线程执行（`net.init()` + `net.connect()` + `mqtt.init()` + `mqtt.connect()`）
2. 网络线程只做已连接状态下的 `publish()` 和 `check_msg()`，**不碰任何 AT 指令**
3. 断连重连也在主线程 `tick()` 中完成（间隔 10s）
4. 启动线程前设置 `_thread.stack_size(4096)`（参考官方 `examples/gnss.py`、`examples/ble.py`）

### 14.2 MQTT 连接参数不一致

**现象**：TCP 连接成功但 ConnectLab 显示"没有客户端连接"。

**原因**：
- config.py 中的 `MQTT_PORT` 与 ConnectLab 实际分配端口不一致
- ConnectLab 每次创建测试会话分配不同端口，config 中写死的端口很快过期
- 诊断脚本 `test_mqtt_connect.py` 硬编码的端口也可能与 config 不同步

**解决**：每次测试前从 ConnectLab Web 界面确认当前端口，更新 config.py 的 `MQTT_PORT`。测试脚本应优先从 config 读取而非硬编码。

### 14.3 umqtt.robust 自动重连与手动重连冲突

**现象**：`umqtt.robust` 的 `MQTTClient` 在 publish 失败时会自动尝试内部重连，与 CloudService tick() 中的手动重连逻辑产生竞争。

**风险**：
- robust 内部重连成功后 `self.client` 状态已变，但 CloudService 的 `ctx["is_mqtt_ready"]` 仍为 False
- 主线程手动重连可能和 robust 内部重连同时进行，导致双重连接或 socket 冲突

**缓解**：网络线程 catch publish 异常后立即标记 `is_mqtt_ready = False`，让 tick() 从主线程统一处理重连，不依赖 robust 的自动重连。

### 14.4 EventBus 线程安全

**现象**：网络线程 publish 事件（`EVENT_DATA_UPLOAD_SUCCESS/FAILED`）的同时，主线程在 `pump()` 遍历回调列表，可能产生数据竞争。

**解决**：`Event_Bus.py` 中使用 `_thread.allocate_lock()` 保护事件队列和回调列表，确保 publish/pump 互斥。

### 14.5 MQTT 回调在子线程执行

**现象**：`_on_mqtt_message` 在网络线程中回调，不当操作会阻塞网络线程。

**约束**：
- 回调中只做 JSON 解析 + `event_bus.publish()`，不做耗时操作
- 不调 `time.sleep()`，不做文件 I/O
- 异常必须内部捕获，不能让回调抛异常导致线程退出

### 14.6 send_queue 满队列处理

**现象**：网络断连时，主线程持续入队，队列不断增长，耗尽内存。

**解决**：`ThreadSafeQueue` 满时自动丢弃最旧元素（`pop(0)`），永不阻塞主线程。同时由 `max_size=100` 控制上限。

### 14.7 JSON 字段 null 规则

**问题**：首次启动时某些传感器数据尚未采集，JSON 中应输出 `null` 而非 `0`，以区分"未采集"和"值为 0"。

**实现**：`_data` 中所有传感器缓存初始化为 `None`，`ujson.dumps(None)` 输出 `null`。只有收到有效事件后才更新为实际值。

---

## 15. 测试验证状态

### 15.1 已测试通过（2026-05-17 E2E）

| 测试项 | 结果 | 说明 |
|:------|:----|:------|
| 4G 网络连接 (`Network.connect()`) | ✅ | SIM 附着 + IP 获取 |
| MQTT TCP 连接 (`MQTT.connect()`) | ✅ | 连上 ConnectLab `172.188.83.251:41404` |
| 传感器数据上传 (`helmet/data`) | ✅ | ConnectLab 收到 `{Temp, Humi, G-Sensor, GNSS, ...}` |
| 上行 topic `helmet/data` QoS 0 | ✅ | 周期性传感器数据正常到达 |
| 下行 topic `helmet/config` 订阅 | ✅ | 已 subscribe，通道开通 |
| 主循环 tick + event_bus.pump | ✅ | CloudService 入队正常 |
| 网络线程 publish + check_msg | ✅ | 子线程收发独立运行 |

### 15.2 未测试 / 待验证

| 待测项 | 优先级 | 说明 |
|:------|:-----:|:------|
| 报警上传 `helmet/alarm` QoS 1 | 高 | 未发送过真机报警，QoS 1 at-least-once 语义未验证 |
| 配置下发从云端到头盔 | 高 | 订阅了 `helmet/config`，但未在 ConnectLab 点击发送验证回调 |
| 断连自动重连 | 中 | tick 中有重连逻辑，但未模拟断网场景验证 |
| 网络线程异常恢复 | 中 | publish 异常 → is_mqtt_ready=False → tick 重连，完整链路未测 |
| `_on_mqtt_message` 多 topic 分发 | 中 | 目前只订阅 `helmet/config`，后续若增加 topic 需验证 |
| 长时间运行稳定性 | 中 | E2E 只跑了 30s，未验证数小时连续运行 |
| SD 卡缓存（v2） | 低 | 设计已定，代码未实现 |
| gps_track 轨迹上传 | 低 | 数据已在内存收集，未加入上传 JSON 载荷 |

### 15.3 后续可调整的内容

所有数据格式和传输内容均为**可配置、可扩展**的，不受当前链路测试限制：

| 可调整项 | 原因 |
|:---------|:------|
| JSON 字段增删 | `tick()` 中 `payload` 字典随时可加/删字段 |
| 数据类型与精度 | 如 `total_distance` 的 `round(..., 3)` 可改，GNSS 可加 `heading` 等 |
| 上传周期 | 由 `config.py` 的 `CLOUD_UPLOAD_INTERVAL_MS` 控制，云端也可下发修改 |
| Topic 名称 | `helmet/data`、`helmet/alarm` 等由 `MQTT_TOPIC_*` 常量控制 |
| QoS 等级 | `MQTT_QOS_DATA` 等 config 常量，随时可改 |
| 报警触发规则 | `_on_alarm()` 中的字段映射，AlarmService 发布的 payload 结构 |
| 骑行扩展字段 | `total_distance`、`total_ascent`、`gps_track` 等实现在 `_on_gnss()` 中独立维护，上传与否可控 |
| 上传条件 | 当前每 tick 都上传，后续可按需改成"有 GNSS 才上传"或"数据变化才上传"
