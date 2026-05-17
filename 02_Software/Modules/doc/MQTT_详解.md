# MQTT 详解 — 智能骑行头盔项目

> **本文目的**：结合头盔项目的实际代码和架构，讲清楚 MQTT 是什么、在我们的代码里怎么跑、每行代码是干什么的。
>
> **阅读对象**：项目团队成员，不需要 MQTT 基础。

---

## 1. MQTT 是什么

MQTT 是物联网设备最常用的通信协议。它的核心设计是**发布/订阅**模式。

### 和 HTTP 的对比

拿我们的头盔举例子：

```
HTTP 方式（不用）：
  头盔每隔 2 秒 → 发一个 HTTP 请求到服务器 → 服务器返回"收到"
  云端想改配置 → 做不到，因为 HTTP 是"一问一答"，服务器不能主动找头盔
  
MQTT 方式（我们用的）：
  头盔连上服务器后一直在线
  头盔随时可以发数据给云端（上传传感器数据）
  云端随时可以发数据给头盔（下发配置参数）
```

### 为什么不用 HTTP

| | MQTT | HTTP |
|:--|:-----|:------|
| **头盔到云端** | 随时发，连接一直在 | 每次新建连接，开销大 |
| **云端到头盔** | ✅ 服务器主动推 | ❌ 做不到，只能头盔轮询 |
| **消息头大小** | 2 字节 | 几百字节 |
| **项目 examples** | 有现成 `examples/mqtt.py` | 不适用 |

---

## 2. 三个核心概念

### 2.1 Broker（消息服务器）

**在我们的项目里，Broker = ConnectLab 平台**。

ConnectLab 是移远提供的 MQTT 在线测试平台。访问它的 Web 界面，可以看到当前测试会话的完整连接参数：

```
服务器地址: 101.37.104.185    ← 固定 IP
端口:       46205             ← 每次创建会话可能不同！
用户名:     quectel
密码:       12345678
```

**特别注意**：端口号不是固定的。示例代码里写的是 `46502`、`41990`、`40579`，但实际要以 ConnectLab 平台界面上**当前会话显示为准**。每次测试都要先看界面上的端口是多少。

头盔连接流程：

```
头盔 EC200U ──4G──→ ConnectLab (101.37.104.185:46205)
                         │
                         ├── 接收头盔上传的传感器数据
                         ├── 在 Web 界面上实时显示
                         └── 等待云端下发配置
```

### 2.2 Topic（主题）

Topic 是消息的"分类标签"。示例代码中 ConnectLab 使用固定格式的 topic：

```python
# examples/mqtt_duplex.py 中的 topic
TOPIC = b'/a1vvrmkn43t/NiFtKoHMcu6j0VIXtC6e/user/get'        # 订阅：接收云端消息
PUBLISH_TOPIC = b'/a1vvrmkn43t/NiFtKoHMcu6j0VIXtC6e/user/update'  # 发布：上传数据
```

topic 格式分解：

```
/{project_id}/{device_token}/user/{action}
   │              │                │
   │              │                ├── get: 接收云端下发
   │              │                └── update: 上传数据到头盔
   │              │
   │              └── 设备令牌（ConnectLab 分配）
   │
   └── 项目 ID（ConnectLab 分配）
```

**开发阶段**：如果我们用自己的自定义 topic（如 `helmet/data`），在 ConnectLab 平台上同样可以用，因为平台只是一个通用的 MQTT Broker，支持任何 topic。

**注意**：示例代码中的 `a1vvrmkn43t` 和 `NiFtKoHMcu6j0VIXtC6e` 是移远预配置的测试项目 ID 和设备令牌。如果自己注册 ConnectLab 项目，会得到不同的值。

### 2.3 Publish（发布）/ Subscribe（订阅）

```
头盔 publish → "helmet/data" → Broker → 转发给云端
云端 publish → "helmet/config" → Broker → 转发给头盔
```

用项目代码来理解：

```python
# 头盔上传数据（在 CloudService 的网络线程中）
mqtt.publish("helmet/data", '{"Temp":28.5,"Humi":65.2}')

# 头盔接收配置（通过回调）
def _on_mqtt_message(topic, msg):
    config = ujson.loads(msg)
    # config = {"target": "gnss", "sample_ms": 5000}
    event_bus.publish(EVENT_CONFIG_UPDATE, config)
```

---

## 3. 项目中的完整数据流

### 3.1 头盔上传传感器数据

```
Drivers/sensor/Gnss.py              Drivers/network/MQTT.py
     │                                      │
     │ EVENT_GNSS_READY                     │
     ▼                                      │
Modules/cloud_service.py                    │
  _on_gnss_ready(payload):                  │
    1. 拼装 JSON                           │
    2. send_queue.put(json_str)  ──────────►│
                                              │
    # 网络线程（独立 _thread）                │
    while running:                           │
        data = send_queue.get()              │
        mqtt.publish("helmet/data", data) ───┤──→ ConnectLab
        mqtt.check_msg()                     │
```

### 3.2 云端下发配置

```
ConnectLab 平台 Web 界面
  → 在底部消息发送区输入 topic 和 JSON
  → 点击"发送"
  → 4G 网络
  → EC200U 模组
  → 网络线程中 mqtt.check_msg() 触发回调
    → CloudService._on_mqtt_message(topic, msg)
      → event_bus.publish(EVENT_CONFIG_UPDATE, config)
        → Gnss._on_config_update(payload)
          → self.cfg["sample_ms"] = 5000
```

### 3.3 为什么用独立线程

**错误写法**（在主循环里发 MQTT 会阻塞）：

```python
# ❌ 主循环里直接 publish，网络慢时传感器全部漏采
while True:
    for mod in modules:
        mod.tick()
    event_bus.pump()
    mqtt.publish(...)     # ← 卡在这里，传感器采集停摆！
    time.sleep_ms(10)
```

**正确写法**（主循环只入队，网络线程单独发包）：

```python
# ✅ 主循环（core/main.py）
while True:
    for mod in modules:
        mod.tick()
    event_bus.pump()           # ← 事件回调只做 send_queue.put
    time.sleep_ms(10)

# ✅ 网络线程（CloudService 启动 _thread）
def _network_thread():
    while running:
        data = send_queue.get()           # ← 阻塞等数据
        mqtt.publish("helmet/data", data) # ← 慢但不影响主循环
        mqtt.check_msg()                  # ← 非阻塞检查配置
        time.sleep_ms(100)
```

---

## 4. MQTT.py 各方法详解

这是 `Drivers/network/MQTT.py` 中每个方法对应的真实 API 调用。

### 4.1 init() — 创建客户端

```python
def init(self, broker, port, client_id, user=None, password=None,
         keepalive=60, ssl=None):
    self.client = MQTTClient(
        client_id=client_id,   # 如 "helmet_001"
        server=broker,         # 101.37.104.185
        port=port,             # 以 ConnectLab 界面为准
        user=user,             # quectel
        password=password,     # 12345678
        keepalive=keepalive,   # 心跳间隔(秒)
        ssl=ssl                # None=不加密
    )
```

### 4.2 connect() — 连接服务器

```python
def connect(self):
    self.client.connect()
    self.ctx["is_connected"] = True
```

**注意**：`connect()` 前必须先确保 4G 已经连接。CloudService 中会先调 `net.connect()` 再调 `mqtt.connect()`。

### 4.3 publish() — 发布消息

```python
def publish(self, topic, payload, qos=0):
    self.client.publish(topic, payload, qos=qos)
```

**payload 的实际来源**（CloudService 中拼装）：

```python
json_str = ujson.dumps({
    "Temp": 28.5,
    "Humi": 65.2,
    "G-Sensor": {"X": 0.123, "Y": -0.456, "Z": 9.812},
    "GNSS": {"lat": 22.5431, "lon": 113.9523},
    "altitude": 15.3,
    "speed_kmh": 25.6,
    "signal_quality": "good",
    "timestamp": 12345678
})
```

### 4.4 set_callback() — 设置消息回调

```python
def set_callback(self, fn):
    self.client.set_callback(fn)
    # CloudService 中：
    # def _on_mqtt_message(topic, msg):
    #     config = ujson.loads(msg)
    #     event_bus.publish(EVENT_CONFIG_UPDATE, config)
```

### 4.5 check_msg() — 非阻塞检查消息

```python
def check_msg(self):
    self.client.check_msg()
```

**和 wait_msg 的区别**：
- `check_msg()`：非阻塞，没消息立即返回 → 网络线程用这个
- `wait_msg()`：阻塞等待消息 → 不适合我们的场景

---

## 5. ConnectLab 平台使用指南

### 5.1 平台界面长什么样

ConnectLab Web 界面（上下两半）：

```
┌──────────────────────────────────────────────┐
│  服务器信息                          刷新     │
│  ─────────────────────────────                 │
│  协议: MQTT_3.1.1                             │
│  服务器地址: 101.37.104.185:46205             │
│  用户名: quectel                              │
│  密码: 12345678                               │
│  创建时间: 2026-05-16 22:53:31                │
│  截止时间: 2026-05-17 22:53:31  ← 24h过期!   │
│  最大连接数: 5                                │
├──────────────────────┬───────────────────────┤
│  客户端连接（手Q  ）  │  数据展示区域          │
│  ─────────────        │  ─────────            │
│  暂无客户端连接       │  topic | 消息 | 时间  │
│                       │  ...                  │
├──────────────────────┴───────────────────────┤
│  消息发送区                                    │
│  ─────────                                      │
│  Topic: [              ]  Qos: [0▼]            │
│  消息:  [                                    ] │
│  [命令集 ▼]                         [发  送]   │
└──────────────────────────────────────────────┘
```

### 5.2 界面上每个部分的含义

**左上：服务器信息**
- **协议**: `MQTT_3.1.1` — 标准 MQTT 版本
- **服务器地址**: `101.37.104.185:46205` — 头盔代码里要填的 broker 和 port
- **用户名/密码**: `quectel/12345678` — MQTT 登录凭据
- **创建/截止时间**: 这个测试会话的生存期，**过期后需要重新创建**
- **最大连接数**: 5 — 同时最多 5 个设备连接

**左下：客户端连接**
- 显示当前有哪些设备连上了这个服务器
- 头盔成功连接后，这里会显示 `umqtt_client`（或我们自定义的 client_id）
- 点击"客户端连接"按钮，平台自身也可以扮演一个 MQTT 客户端
- 连接成功后，按钮文字变为"已连接"（文字前带绿色对勾）

**右侧：数据展示**
- 实时显示所有通过该服务器的消息流
- 每条消息显示：topic、消息内容、时间戳
- 头盔 publish 的数据会实时出现在这里

**底部：消息发送区**
- **Topic**: 输入要发送消息的 topic 名称
- **Qos**: 服务质量选择
- **消息**: 输入要发送的消息内容（JSON 格式）
- **命令集**: 预制的一些测试命令
- **发送**: 点击后平台会 publish 这个消息到对应 topic

### 5.3 三组使用场景

#### 场景一：模拟云端，测试头盔上传数据

```
操作步骤：
1. 头盔代码里用界面上的 broker+port 连上服务器
2. 头盔 publish 数据到某个 topic（如 "helmet/data"）
3. 界面右侧表格实时显示收到的数据 ✓
```

**测试方法**：
```
在 EC200U 上运行：
  from umqtt.robust import MQTTClient
  client = MQTTClient("test", "101.37.104.185", port=46205,
                       user="quectel", password="12345678")
  client.connect()
  client.publish(b"helmet/data", b'{"Temp":28.5}')
  # → ConnectLab 右侧表格立即显示该消息
```

#### 场景二：模拟云端，下发配置给头盔

```
操作步骤：
1. 头盔 subscribe 一个 topic（如 "helmet/config"）
2. 头盔持续调 check_msg()
3. 在平台底部输入：
   Topic: helmet/config
   Qos: 1
   消息: {"sample_ms": 5000}
4. 点击"发送"
5. 头盔回调函数收到消息 ✓
```

#### 场景三：两个客户端互相通信测试

```
操作步骤：
1. 头盔连上服务器
2. 点击左下角"客户端连接"，让浏览器也当客户端连上
3. 两个客户端可以互相 publish/subscribe
4. 测试双向通信是否正常
```

### 5.4 重要提醒

**每次测试前必须确认端口**：

```
ConnectLab 界面显示端口: 46205
头盔代码里必须用:       port = 46205

如果用示例里的固定端口 46502/41990/40579 → 连接失败！
```

**24 小时有效期**：

```
创建时间: 2026-05-16 22:53:31
截止时间: 2026-05-17 22:53:31
过期后：连接断开，右侧数据显示"暂无数据"
        需要重新创建测试会话，获取新的端口
```

---

## 6. "创建客户端"到底是什么意思

```python
client = MQTTClient(
    client_id='helmet_001',
    server='101.37.104.185',
    port=46205,
    user='quectel',
    password='12345678'
)
```

**这行代码只做了一件事**：在 EC200U 的内存里实例化一个 MQTT 客户端对象。

它不是"在云端创建一台设备"。**在云端的视角**：

| 步骤 | 代码 | 云端发生了什么 |
|:-----|:-----|:--------------|
| 1 | `MQTTClient(...)` | 什么都没发生，只是本地对象 |
| 2 | `client.connect()` | 云端收到 TCP 连接请求 |
| 3 | 连接成功 | ConnectLab 左下角显示"已连接" |
| 4 | `client.publish(...)` | 数据出现在右侧表格 |
| 5 | `client.disconnect()` | 左下角显示"暂无客户端连接" |

类比：
```
MQTTClient(...)  = 买一部手机（本地行为）
client.connect() = 插卡打电话，基站才知道你在线
client.publish() = 你说了一句话，基站转给其他人
```

---

## 7. 常见参数修改说明

### 用户名和密码能自己改吗？

- `quectel/12345678` 是移远提供的**公共测试账号**，任何人都能用
- 如果想用自己的账号，需要去 ConnectLab 平台注册
- 开发阶段用公共账号完全足够

### Client ID 能自己改吗？

- 可以随便改，只要保证唯一性
- 示例里都是 `umqtt_client`，多台设备同时用相同 ID 会踢下线
- 实际项目中应改为 `helmet_001`、`helmet_002` 等区分设备

### Topic 能自己定义吗？

- ConnectLab 是通用 MQTT Broker，支持任意 topic 名称
- 示例里的 `/a1vvrmkn43t/.../user/get` 是特定项目的格式
- 开发阶段直接用 `helmet/data`、`helmet/config` 更方便

### 端口每次都不一样吗？

- ConnectLab 每个测试会话分配不同端口
- 必须在界面上确认当前端口，不能写死

### Client ID 在什么范围（模型）？

- Client ID 就是一个普通的字符串，没有格式限制
- 唯一要求：同一时刻连到同一个 Broker 的客户端中不能重复
- 建议命名格式：`{项目缩写}_{设备编号}`，如 `helmet_001`

---

## 8. QoS 在我们的项目中的使用

```python
# 传感器数据（丢一两条无所谓，下次还有）
mqtt.publish("helmet/data", data, qos=0)

# 碰撞报警（必须到，重复也没事）
mqtt.publish("helmet/alarm", alarm_data, qos=1)
```

| QoS | 场景 | 原因 |
|:---:|:-----|:------|
| **0** | 周期性传感器数据 | 每 2 秒上传一次，丢了一条下次还有 |
| **1** | 碰撞报警 / SOS | 人命关天，必须到，重复也不影响 |
| **1** | 云端配置下发 | 配置必须应用，重复下发也无害 |

---

## 9. 常见问题排查

### 头盔连不上服务器？

```
1. 检查 4G 网络是否已连接
2. 确认端口号是否和 ConnectLab 界面一致
3. 检查 client_id 是否和其他设备冲突
4. 确认测试会话还没过期（24h）
```

### publish 发了但 ConnectLab 上看不到？

```
1. 确认右侧表格处于当前会话页面
2. 检查 topic 名称是否输对了
3. 检查 payload 能不能正确 JSON 序列化
4. 调用 client.publish() 后没有报异常
```

### 云端下发了配置但头盔没反应？

```
1. 头盔有没有 subscribe 对应的 topic？
2. 网络线程里有没有调 mqtt.check_msg()？
3. 回调函数里有没有 event_bus.publish(...)？
4. 目标模块有没有 subscribe 对应的配置事件？
```

---

## 10. 代码和文档对照表

| 你想了解什么 | 看哪里 |
|:------------|:-------|
| MQTT 的 API 方法 | `API/MQTT客户端API参考手册.pdf` |
| 我们的封装代码 | `Drivers/network/MQTT.py` |
| MQTT 在项目中的使用 | `Modules/cloud_service.py` |
| MQTT 的设计文档 | `Service/CloudService_impl.md` |
| 官方使用示例 | `examples/mqtt.py`、`examples/application.py` |
| ConnectLab 连接参数 | ConnectLab Web 界面（每次创建会话后查看） |
| 本文档 | `Service/MQTT_详解.md` |

---

**文档版本**: v2.0  
**更新日期**: 2026-05-16  
**对应模块**: `Drivers/network/MQTT.py`  
**新增内容**: v2.0 加入了 ConnectLab 平台界面详解、三组使用场景、常见参数修改说明、"创建客户端"本质解释
