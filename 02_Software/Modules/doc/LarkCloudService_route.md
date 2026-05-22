# LarkCloudService 技术路线与验证方案

> **所属层次**：Service 层
> **涉及平台**：移远云 DMP（iot-south.quectelcn.com）
> **实现状态**：✅ v1 已实现（2026-05-22 E2E 测试通过）
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
# 正常态（每 2 秒）：全量字段 + 显式清除报警
Qth.sendTsl(1, {
    1: 28.5,                               # temperature   float
    2: 65.2,                               # humidity      float
    3: 15.2,                               # speed         float
    4: 22.54,                              # latitude      float
    5: 3,                                  # signal_quality enum (3良好 2一般 1差 0无)
    6: 0,                                  # alarm_type=0 显式清除（防止 API 缓存旧报警值）
    7: 0,                                  # alarm_level=0 辅助清除
    8: 113.95,                             # longitude     float
    9: 10.0,                               # altitude      float
})

# 报警态（精简传输）：仅 ID 4~9，不传温湿度/速度
Qth.sendTsl(1, {
    4: 22.54,                              # latitude      float
    5: 3,                                  # signal_quality enum
    6: 1,                                  # alarm_type: 0=正常 1=碰撞 2=SOS
    7: 2,                                  # alarm_level: 1~3
    8: 113.95,                             # longitude     float
    9: 10.0,                               # altitude      float
})
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

## 3. 第二段：移远云 → 小程序 ✅

> **验证状态**：✅ HTTP 轮询验证通过（2026-05-22）
> 详细开发过程、踩坑记录见 **`WeChatMiniProgram/README.md`**

### 3.1 方案选型

| 方案 | 描述 | 优缺点 |
|:-----|:-----|:------|
| **WebSocket 实时推送** | 小程序 `wx.connectSocket` 连移远云，login→subscribe→收推送 | ✅ 低延迟 ⚠️ 协议未文档化，需从 Android SDK 逆向 |
| **HTTP 轮询** ✅ | 小程序 `wx.request` 每 2 秒调 REST API 拉最新属性 | ✅ 平台无关，`wx.request` 直接调 ⚠️ 2 秒延迟，有冗余请求 |

> **选择 HTTP 轮询**：Step A 目标是"把数据读出来显示"，轮询延迟在可用范围内；WebSocket 协议留到 Step B/C 需要低延迟场景时接入。

### 3.2 用到的 OpenAPI

BaseURL：`https://iot-api.quectelcn.com`（中国数据中心）  
API 文档：https://iot-cloud-docs.quectelcn.com

**用户管理**：

| API | 用途 | 认证方式 |
|:----|:-----|:---------|
| `POST /v2/sms/enduserapi/v2/sendPhoneSmsCode` | 发送短信验证码 | `signature`（SHA256） |
| `POST /v2/enduser/enduserapi/v2/phonePwdRegister` | 手机号密码注册 | AES 加密密码 |
| `POST /v2/enduser/enduserapi/phonePwdLogin` | 手机号密码登录 | AES + SHA256 → `accessToken` + `refreshToken` |

**设备管理**：

| API | 用途 |
|:----|:-----|
| `POST /v2/binding/enduserapi/bindDeviceSn` | SN 绑定设备 |
| `GET /v2/binding/enduserapi/userDeviceList` | 查询已绑定设备列表 |
| `GET /v2/binding/enduserapi/productTSL` | 查询物模型 TSL 定义 |
| `GET /v2/binding/enduserapi/getDeviceBusinessAttributes` | **查询设备业务属性（核心）** |

> 参数方式为 Query String（`?pk=xxx&dk=xxx`），Header 带 `Authorization: Bearer {token}`。

### 3.3 数据格式与映射

**API 返回结构**：

```json
{
  "code": 200,
  "data": {
    "customizeTslInfo": [
      {"abId": 1, "resourceCode": "temperature", "resourceValce": "28.5"},
      {"abId": 4, "resourceCode": "latitude",    "resourceValce": "22.5431"}
    ]
  }
}
```

| 字段 | 实际 API 返回 | 我们预期的 | 说明 |
|:-----|:-----|:-----|:-----|
| ID | `abId` | `id` | API 命名不同 |
| 值 | `resourceValce` | `value` | API 拼写错误（应为 resourceValue） |
| 字段名 | `resourceCode` | `code` | — |

**TSL ID 映射表**：

| abId | resourceCode | 中文 | 类型 | 单位 |
|:----:|:-------------|:-----|:-----|:-----|
| 1 | temperature | 温度 | FLOAT | °C |
| 2 | humidity | 湿度 | FLOAT | % |
| 3 | speed | 速度 | FLOAT | km/h |
| 4 | latitude | 纬度 | FLOAT | ° |
| 5 | signal_quality | 信号质量 | ENUM(0~3) | — |
| 6 | alarm_type | 报警类型 | ENUM(0~2) | — |
| 7 | level | 报警等级 | INT(1~3) | — |
| 8 | longitude | 经度 | FLOAT | ° |
| 9 | altitude | 海拔 | FLOAT | m |

> 常态下设备只传 ID 1~5,8,9（无 ID 6/7），报警态额外传 ID 6/7。小程序端每次轮询时默认 `alarm="正常"`，仅当收到 `abId=6` 且值 ≠ 0 时覆盖为报警文案。

### 3.4 验证清单

- [x] DMP 平台创建 App，获取 userDomain / userDomainSecret ✅
- [x] App 关联产品 p11yMv ✅
- [x] curl：短信验证码 → 注册用户 → 登录获取 token ✅
- [x] curl：SN 绑定设备 → 查询 TSL 模型 → 查询业务属性 ✅
- [x] 小程序：`wx.request` 轮询 `getDeviceBusinessAttributes` ✅
- [x] 小程序：数据正确解析并显示（温度/湿度/速度/位置/信号/报警） ✅
- [x] 报警态与常态差异显示正确（常态不残留报警状态） ✅
- [x] 小程序登录 UI（手机号+密码→crypto→QuecCloud AIP） ✅
- [x] 骑行控制（开始/结束/确认弹窗） ✅
- [x] 数据缓存与骑行总结（时长/速度/温度/里程/报警） ✅
- [x] 地图轨迹（polyline 实时绘制 + 展开/收起 + 跟随/手动） ✅
- [ ] WebSocket 实时推送（📅 后续）
- [ ] 导航 + 语音播报（📅 v2）

> **验证策略**：先用 curl 逐接口验证 → 确认 API 返回格式 → 再写小程序代码。避免了在小程序中盲猜 URL/参数/返回格式的低效迭代。

---

## 4. 当前状态与后续任务

### 4.1 已完成 ✅

| 层 | 模块 | 状态 |
|:---|:-----|:----:|
| Device | QthDriver (`Drivers/network/Qth.py`) | ✅ |
| Service | LarkCloudService (`Modules/lark_cloud.py`) | ✅ |
| E2E | 设备→移远云 DMP 数据链路 | ✅ |
| 小程序 | 登录+实时数据+骑行控制+总结+地图（`WeChatMiniProgram/`） | ✅ |
| 小程序 | 地图轨迹、展开/收起、跟随/手动回正 | ✅ |

### 4.2 后续任务 📅

| 优先级 | 任务 | 说明 |
|:------|:-----|:-----|
| 高 | 小程序登录页 | 替换硬编码 token，实现短信→注册→登录 UI |
| 高 | token 自动刷新 | accessToken 过期后用 refreshToken 续期 |
| 中 | WebSocket 实时推送 | 替换 HTTP 轮询，降低延迟 |
| 中 | 报警弹窗 | 小程序收到 alarm_type≠0 时弹窗提醒 |
| 低 | 骑行总结 + 轨迹 | 利用 `/v2/quecdatastorage/enduserapi/getLocationHistory` |

### 4.3 不再需要

- `bridge/bridge.py` — 小程序直连移远云，无需中间桥接
- Android SDK Demo — 仅用于参考 URL 和 API 格式
- ConnectLab MQTT 通道 — 与移远云并存，不是替代关系
