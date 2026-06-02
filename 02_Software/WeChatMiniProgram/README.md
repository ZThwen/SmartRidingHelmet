# 智能骑行头盔 — 微信小程序开发文档

> **当前状态**：🟢 Step A 完成（实时数据显示 + BLE 直连） · Step B 导航框架已搭建
> **更新日期**：2026-06-01

---

## 1. 技术选型：为什么是小程序不是 Android App

| | Android App | 微信小程序 |
|:--|:----|:-----|
| 开发语言 | Java/Kotlin | JavaScript（接近 Python） |
| SDK | 有（.aar 文件，仅 Android） | 无 JS SDK，直接用 HTTP |
| 分发 | 打包 APK，应用商店上架 | 扫码即用，微信内打开 |
| 开发环境 | Android Studio（重） | 微信开发者工具（轻） |
| 中国队选手体验 | 需安装 | 微信生态内直达 |

**结论**：小程序是正确选择。没有 JS SDK 没关系——移远云的 REST API 平台无关，`wx.request` 直接调。

---

## 2. 通信架构

### 当前方案：BLE GATT 直连（Step A 已完成）

```
STM32F413 (MicroPython)
  │ BLE GATT Notify (FFF1)
  │ JSON: {"t":0,"d":{tmp,hum,spd,lat,lon,...}}
  ▼
微信小程序 (ble-service.js BLE Central)
  │ wx.onBLECharacteristicValueChange → JSON.parse → setData → WXML
  ▼
用户手机屏幕
```

- **数据下行**（小程序→头盔）：BLE GATT Write FFF2（导航指令 sendNav）、FFF3（控制 sendCtrl）
- **延迟**：<100ms，无云端依赖
- **消息类型**：t=0 传感器合并数据、t=5 报警触发、t=6 报警解除、t=99 心跳

### 历史方案：移远云 HTTP 轮询（已弃用）

> 2026-05-17 ~ 2026-05-28 期间使用。已切换为 BLE 直连（低延迟、无云端依赖）。
> `services/data-service.js` 和 `utils/ws-client.js` 保留作为历史参考，当前未被任何页面引用。

---

## 3. 完整操作流程

### 3.1 DMP 平台配置

| 步骤 | 操作 | 结果 |
|:----|:-----|:-----|
| 1 | App SDK → 创建 App | 获得 userDomain + userDomainSecret |
| 2 | App 详情 → 关联产品 | 关联 `p11yMv`（智能骑行头盔产品） |
| 3 | 查看 OpenAPI 文档 | https://iot-cloud-docs.quectelcn.com/document/endUserAPIAccessInstruction |

### 3.2 用户注册与登录

**注册**（首次使用，通过 curl 命令行完成）：

```
POST /v2/sms/enduserapi/v2/sendPhoneSmsCode  ← 发短信验证码
POST /v2/enduser/enduserapi/v2/phonePwdRegister  ← 注册
```

| ⚠️ 坑 | userDomain 末尾字符不要多写（我们曾误写 `.1N` 实际是 `.1`） |
| ⚠️ 坑 | pwd 和 random 每次重新生成，不复用 |

**登录**（小程序内完成，已有登录 UI）：

小程序 `pages/login/` 提供手机号+密码登录界面。密码经 `crypto.js`（纯 JS SHA256+MD5+AES-128-CBC）加密后调用 QuecCloud `phonePwdLogin` API，成功后 token 存入 `globalData`。

```
POST /v2/enduser/enduserapi/phonePwdLogin
Query: internationalCode, phone, pwd(加密后), random, signature, userDomain
签名: SHA256(internationalCode + phone + pwd + random + userDomainSecret)
返回: accessToken(2h) + refreshToken(30d)
```

| ⚠️ 坑 | 签名中的 pwd 是加密后的 Base64，不是明文 |
| ⚠️ 坑 | token 过期用 refreshToken 续，无需重登录 |

**当前凭据**（`utils/config.js`）：

| 配置项 | 值 |
|:-------|:---|
| USER_DOMAIN | `C.DM.1507151130577592.1` |
| BASE_URL | `https://iot-api.quectelcn.com` |
| PRODUCT_KEY | `p11yMv` |
| DEVICE_KEY | `66ccff` |
| BLE_DEVICE_PREFIX | `SmartHelmet-` |
| TENCENT_MAP_KEY | 腾讯地图 WebService API Key |

### 3.3 设备绑定

```
POST /v2/binding/enduserapi/bindDeviceSn
Query: sn=7305831455A211F1822EF18D13D07623, pk=p11yMv
```

| ⚠️ 坑 | `bindDeviceDk` 返回 `5499 产品未授权DK绑定`，产品侧禁用了 DK 绑定 |
| ⚠️ 坑 | 参数用 Query String 不是 JSON Body |
| ⚠️ 坑 | 参数名是 `pk`/`sn`，不是 `productKey`/`sn` |
| 📌 注意 | SN 在 DMP 平台 → 设备详情页获取 |

### 3.4 数据通道

**当前方案：BLE GATT Notify（主通道）**

小程序作为 BLE Central，连接头盔 GATT Server（Service UUID 0xFFF0），通过 FFF1 Notify 每 2 秒接收传感器数据 JSON。

**历史方案：HTTP 轮询（已弃用）**

> 原方案通过 `GET /v2/binding/enduserapi/getDeviceBusinessAttributes` 每 2 秒轮询 TSL 数据。已弃用，详见 `services/data-service.js`。

---

## 4. 代码结构

```
WeChatMiniProgram/
├── app.js              全局入口 — globalData(token, isRiding, rideCache)
├── app.json            pages + 窗口 + 定位权限
├── services/
│   ├── ble-service.js          BLE Central 客户端（主数据通道，扫描/连接/收发/自动重连）
│   ├── alarm-service.js        报警检测 + 弹窗规则（纯函数）
│   ├── ride-service.js         骑行状态机 + Haversine 总结
│   ├── map-service.js          轨迹 polyline + marker 生成
│   ├── navigation-service.js   导航状态机（腾讯地图 API 算路 + BLE FFF2 指令推送）
│   └── data-service.js         [已弃用] HTTP 轮询 + TSL 解析（历史参考）
├── utils/
│   ├── config.js       凭据配置
│   ├── crypto.js       SHA256 + MD5 + AES-128-CBC（纯 JS）
│   ├── logger.js       日志（console + 文件，上限 1000 条）
│   ├── ble-protocol.js BLE 协议常量（UUID、设备前缀、重连参数、类型映射）
│   └── ws-client.js    [已弃用] 兼容层（→ data-service，历史参考）
├── pages/
│   ├── login/          登录页（手机号 + 密码，crypto 加密）
│   └── index/          首页：地图 + 数据卡片 + 骑行控制 + 导航 + 报警 + 总结
│       ├── index.js    调度器（BLE 连接 + 数据解析 + 状态管理 + 事件分发）
│       ├── index.wxml  导航栏 + 地图(展开/收起) + 卡片 + 弹窗 + 导航浮层
│       ├── index.wxss  Tactical Cyan 暗色主题 + 动画
│       └── index.json  自定义导航栏
└── doc/                文档 4 篇（architecture / requirements / development / voice_feasibility）
```

**index.js 数据流（BLE 直连）**：

```
登录 → 首页(idle, 手机 GPS 定位) → 点击"开始骑行"
  → BleService.init() + scan() + connectById()
  → BLE Notify 每 2s 推送 JSON: {"t":0,"d":{tmp,hum,spd,lat,lon,alt,lux}}
  → onData 回调:
    t=0 → 解析传感器数据 → setData(显示) + rideCache(缓存) + trackPoints(轨迹)
    t=5 → AlarmService.analyze() → 全屏报警弹窗 + 暂停导航
    t=6 → 清除报警 + 恢复导航
  → 点击"结束骑行"
  → 确认 → 停止 BLE → RideService.end() → 总结弹窗(含地图)
```

---

## 5. 当前状态

### Step A *(✅ 已完成 2026-06-01)*

| 功能 | 状态 | 说明 |
|:-----|:----:|:-----|
| BLE 直连数据通道 | ✅ | BLE GATT Notify FFF1，t=0 传感器/t=5 报警/t=6 解除/t=99 心跳 |
| 用户注册/登录 | ✅ | 手机号+密码→crypto→QuecCloud API，登录 UI 完整 |
| 实时数据显示 | ✅ | 温度/湿度/速度/位置/报警，BLE 2s 推送 |
| 报警弹窗 | ✅ | 碰撞 Lv2+/SOS 全屏红色弹窗 + 报警取消功能 |
| 骑行控制 | ✅ | 开始→BLE数据+缓存，结束→确认→总结 |
| 骑行总结 | ✅ | 全屏页面，时长/速度/温度/里程/报警次数，起点+终点标记 |
| 地图轨迹 | ✅ | polyline 实时绘制（BLE GPS），canvas 蓝点 marker，show-location 条件切换 |
| 小程序登录 UI | ✅ | pages/login，crypto 纯 JS 加密 |
| 测试文件 | ✅ | Tests/miniprogram/ 6 个独立测试文件 |

### Step B *(🔜 导航框架已搭建)*

| 功能 | 状态 | 说明 |
|:-----|:----:|:-----|
| 导航路线规划 | 🔜 | navigation-service.js + 腾讯地图 bicycling API |
| 导航指令下发 | 🔜 | BLE FFF2 sendNav（5s 间隔推送转弯指令） |
| 导航界面 | 🔜 | 指令浮层 + 规划路线 polyline（绿色） |

### Step C *(📅)*

| 功能 | 状态 | 说明 |
|:-----|:----:|:-----|
| 语音交互 | 📅 | 语音指令 R13（详见 doc/voice_feasibility.md） |

---

## 6. 参考文档

| 文档 | 路径 |
|:-----|:-----|
| 架构设计 (C4) | `doc/architecture.md` |
| 需求定义 | `doc/requirements.md` |
| 开发全记录 | `doc/development.md` |
| 语音可行性分析 | `doc/voice_feasibility.md` |
| 导航 brainstorm | `doc/.brainstorms/260528-2100-navigation/` |
| 移远云 OpenAPI 文档 | https://iot-cloud-docs.quectelcn.com |
| 设计总体方案 | `00_Planning/02_Design_scheme.md` |
