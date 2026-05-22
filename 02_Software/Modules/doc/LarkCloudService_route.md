# LarkCloudService 技术路线与验证方案

> **所属层次**：Service 层
> **涉及平台**：移远云 DMP（iot-south.quectelcn.com）
> **实现状态**：🔵 验证中
> **负责人员**：郑皓文

---

## 1. 整条链路

```
头盔（Qth SDK）→ MQTT → 移远云 DMP 平台
                                  ↓
                    ┌──────────────┴──────────────┐
                    │                             │
            HTTP API (baseUrl)            WebSocket (webSocketV2Url)
            wx.request() 查询              wx.connectSocket() 实时推送
                    │                             │
                    └──────────────┬──────────────┘
                                   ↓
                             小程序 / App
```

---

## 2. 第一段：设备 → 移远云

### 2.1 用到的 API

来自 `移远云SDK-API参考手册.pdf`：

| 步骤 | API | 说明 | PDF 章节 |
|:----:|:----|:-----|:---------|
| 1 | `Qth.init()` | 初始化 SDK | 2.1 |
| 2 | `Qth.setProductInfo("p11yq3", "emcxQnJBV0VKZ0l1")` | 产品信息 | 3.1 |
| 3 | `Qth.setDK("123600000000000")` | 设备 Key | 3.2 |
| 4 | `Qth.setServer("mqtt://iot-south.quectelcn.com:1883")` | 服务器地址 | 3.3 |
| 5 | `Qth.start()` | 启动连接 | 2.2 |
| 6 | `Qth.state()` | 检查连接状态 | 2.4 |
| 7 | `Qth.sendTsl(1, {id: value})` | 上传数据 | 5.2 |
| 8 | `Qth.setEventCb({"recvTsl": fn})` | 接收指令 | 4.1 |

### 2.2 数据上传格式

```python
# 正常态（每 2 秒）
Qth.sendTsl(1, {
    1: 28.5,                               # temperature   float
    2: 65.2,                               # humidity      float
    3: 15.2,                               # speed         float
    4: 22.54,   # latitude  float
    8: 113.95,  # longitude float
    9: 10.0,    # altitude  float
    5: 3,                                   # signal_quality enum (3良好 2一般 1差 0无)
})

# 报警态（ID 6/7 作为独立属性上传）
Qth.sendTsl(1, {6: 1, 7: 2})
# ID 6 alarm_type: 0=正常 1=碰撞 2=SOS
# ID 7 alarm_level: 1~3
```

### 2.3 物模型详细定义

以下为在移远云 DMP 平台创建产品时，需要配置的完整物模型表。

#### 2.3.1 属性列表

| 功能ID | 功能类型 | 功能名称 | 标识符 | 数据类型 | 读写类型 |
|:------:|:--------|:---------|:-------|:--------|:--------|
| 1 | 属性 | 温度 | temperature | float | 只读 |
| 2 | 属性 | 湿度 | humidity | float | 只读 |
| 3 | 属性 | 速度 | speed | float | 只读 |
| 4 | 属性 | 纬度 | latitude | float | 只读 |
| 8 | 属性 | 经度 | longitude | float | 只读 |
| 9 | 属性 | 海拔 | altitude | float | 只读 |
| 5 | 属性 | 信号质量 | signal_quality | enum | 只读 |
| 6 | 属性 | 报警类型 | alarm_type | enum | 只读 |
| 7 | 属性 | 报警等级 | alarm_level | int | 只读 |

#### 2.3.2 各属性详细参数

> 说明：描述字段不超过 128 字符；整型取值范围 -2147483648 ~ 2147483647；浮点型步长 0.1

**ID 1 — temperature（温度）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | float |
| 取值范围 | -20 ~ 60 |
| 步长 | 0.1 |
| 单位 | °C |
| 描述 | 环境温度 |

**ID 2 — humidity（湿度）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | float |
| 取值范围 | 0 ~ 100 |
| 步长 | 0.1 |
| 单位 | % |
| 描述 | 环境湿度 |

**ID 3 — speed（速度）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | float |
| 取值范围 | 0 ~ 120 |
| 步长 | 0.1 |
| 单位 | km/h |
| 描述 | 当前骑行速度 |

**ID 4 — latitude（纬度）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | float |
| 取值范围 | -90 ~ 90 |
| 步长 | 0.000001 |
| 单位 | ° |
| 描述 | WGS-84 纬度 |

**ID 8 — longitude（经度）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | float |
| 取值范围 | -180 ~ 180 |
| 步长 | 0.000001 |
| 单位 | ° |
| 描述 | WGS-84 经度 |

**ID 9 — altitude（海拔）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | float |
| 取值范围 | -500 ~ 9000 |
| 步长 | 0.1 |
| 单位 | m |
| 描述 | 海拔高度 |

**ID 5 — signal_quality（信号质量）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | enum |
| 描述 | GNSS 定位信号质量 |

枚举值：

| 枚举值 | 属性描述 |
|:-----:|:---------|
| 3 | 信号良好 |
| 2 | 信号一般 |
| 1 | 信号差 |
| 0 | 无信号 |

#### 2.3.3 事件列表

| 功能ID | 功能类型 | 功能名称 | 标识符 | 数据类型 |
|:------:|:--------|:---------|:-------|:--------|
| 6 | 事件 | 报警 | alarm | struct |

事件输出参数：

| 子ID | 参数名称 | 标识符 | 数据类型 | 取值范围 | 说明 |
|:----:|:---------|:-------|:--------|:---------|:-----|
| 1 | 报警类型 | alarm_type | enum | 1/2 | 1碰撞 2SOS |
| 2 | 报警等级 | level | int | 1~3 | 1轻微 2中等 3严重 |

#### 2.3.3 报警属性详细参数

**ID 6 — alarm_type（报警类型）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | enum |
| 描述 | 报警类型（0=无报警 1=碰撞 2=SOS） |

枚举值：

| 枚举值 | 属性描述 |
|:-----:|:---------|
| 0 | 无报警 |
| 1 | 碰撞 |
| 2 | SOS求救 |

**ID 7 — alarm_level（报警等级）**

| 参数 | 值 |
|:-----|:----|
| 数据类型 | int |
| 取值范围 | 1 ~ 3 |
| 步长 | 1 |
| 单位 | 无 |
| 描述 | 报警严重等级（1轻微 2中等 3严重） |

---

### 2.4 PDF 依据

PDF 5.2 节 `sendTsl` 原文：

```
函数原型：ret = Qth.sendTsl(mode, value)
参数：
  mode: int — QoS 0 或 1
  value: dict — {物模型ID: 值}
示例：Qth.sendTsl(1, {1: 25.6, 2: 60.5})
```

### 2.5 验证清单

- [x] Qth.init() 返回 True ✅
- [x] Qth.start() 后 Qth.state() = True（异步，需等约 5~10 秒） ✅
- [x] sendTsl(ID 1~5,8,9) 数据到达平台，属性页可见 ✅
- [x] ID 4/8/9 拆分为独立 float（因 Qth SDK 不支持 struct 嵌套） ✅
- [x] ID 5 enum 类型正确解析（3/2/1/0） ✅
- [x] ID 6 alarm_type 枚举正确解析（0/1/2） ✅
- [x] ID 7 alarm_level 整型正确解析（1~3） ✅
- [x] E2E 三种场景验证通过（常态 / 报警 / 解除） ✅

> 第一段验证整体通过 — 设备侧 Qth SDK → 移远云 DMP 数据链路已完成。

---

## 3. 第二段：移远云 → 小程序

### 3.1 配置获取

在 DMP 平台创建 App 后得到（来自 Android SDK `QuecPublicConfigBean`）：

```
userDomain      = "xxx"          # 用户域
userDomainSecret = "xxx"         # 用户域密钥
baseUrl         = "https://xxx"  # HTTP API 地址
webSocketV2Url  = "wss://xxx"    # WebSocket 地址（小程序用这个）
```

### 3.2 用户登录（HTTP）

Android API 参考：`IUserService.手机号密码登录()`

```
小程序 wx.request：
  POST {baseUrl}/user/login
  Body: {phone: "138xxxx", password: "xxx"}
  Response: {code: 200, data: {token: "xxx", uid: "xxx"}}
```

保存 token，后续请求带 `Authorization: Bearer {token}`。

### 3.3 查询设备属性（HTTP）

```
小程序 wx.request：
  POST {baseUrl}/device/properties
  Header: Authorization: Bearer {token}
  Body: {productKey: "p11yq3", deviceKey: "123600000000000"}
  Response: {code: 200, data: [{id: 1, value: 28.5}, ...]}
```

### 3.4 WebSocket 实时推送

Android API 参考：`IWebSocketService`

```
小程序步骤：
1. wx.connectSocket({url: webSocketV2Url})
2. wx.onSocketOpen → 发送 login 消息（带 token）
3. 登录成功 → 调 subscribeDevice("123600000000000", "p11yq3")
4. wx.onSocketMessage → 收到 TSL 数据更新
```

### 3.5 TSL 数据对应关系

| 数据 | ID | 设备端发送 | 小程序端收到 |
|:-----|:--:|:-----------|:------------|
| 温度 | 1 | `sendTsl(1, {1: 28.5})` | `{id:1, value:28.5, type:"float"}` |
| 湿度 | 2 | `sendTsl(1, {2: 65.2})` | `{id:2, value:65.2, type:"float"}` |
| 速度 | 3 | `sendTsl(1, {3: 15.2})` | `{id:3, value:15.2, type:"float"}` |
| 纬度 | 4 | `sendTsl(1, {4: 22.54, 8: 113.95, 9: 10.0})` | `{id:4, value:22.54, type:"float"}` |
| 经度 | 8 | 同上 | `{id:8, value:113.95, type:"float"}` |
| 海拔 | 9 | 同上 | `{id:9, value:10.0, type:"float"}` |
| 信号 | 5 | `sendTsl(1, {5: 3})` | `{id:5, value:3, type:"enum"}` |
| 报警类型 | 6 | `sendTsl(1, {6: 1, 7: 2})` | `{id:6, value:1, type:"enum"}` |
| 报警等级 | 7 | `sendTsl(1, {6: 1, 7: 2})` | `{id:7, value:2, type:"int"}` |

### 3.6 验证清单

- [ ] DMP 平台创建 App，拿到 baseUrl / webSocketV2Url
- [ ] 小程序 wx.request() 调登录 → 拿到 token
- [ ] 小程序调设备属性查询 → 返回 TSL 数据
- [ ] 小程序 wx.connectSocket() 连 webSocketV2Url 成功
- [ ] WebSocket 订阅设备后收到实时推送
- [ ] 推送数据与头盔上传一致

---

## 4. 验证通过后的后续方向

### 4.1 头盔端

| 文件 | 任务 |
|:-----|:-----|
| `Modules/lark_cloud.py` | **新建**，按 2.1 节 API 实现 Qth 接入 |
| `core/config.py` | 新增产品/设备配置常量 |
| `core/main.py` | 集成 LarkCloudService |

### 4.2 小程序端

| 文件 | 当前 | 改后 |
|:-----|:-----|:-----|
| `utils/constants.js` | `WS_URL = "ws://localhost:8765"` | `WS_URL = webSocketV2Url` |
| `utils/mqtt-client.js` | 连 bridge.py | 连移远云 WebSocket + login + subscribe |
| `app.js` | — | 新增用户登录和设备绑定逻辑 |

### 4.3 可废弃

- `bridge/bridge.py` — 不再需要，小程序直连移远云
- ConnectLab MQTT 通道 — 可选保留或移除

---

## 5. 待确认的问题

| 问题 | 说明 |
|:-----|:------|
| WebSocket login 消息的 JSON 格式 | Android SDK 封装了细节，小程序侧需确认协议格式 |
| HTTP API 的具体路径 | 需要查 DMP 端 API 文档或抓包 Android Demo |
| WebSocket 推送的结构是否与 sendTsl ID 一致 | 需要实测确认 |
| 小程序能否直接 WebSocket login/subscribe | 可能需先通过 HTTP 获取 ticket |
