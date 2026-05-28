# 智能骑行头盔 — 微信小程序开发文档

> **当前状态**：🟢 Step A 完成（实时数据显示）
> **更新日期**：2026-05-22

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

```
STM32F413 (MicroPython)
  │ QthDriver.send_tsl({1:28.5, 2:48.7, ...})
  ▼
移远云 DMP (MQTT: iot-south.quectelcn.com:1883)
  │ 数据存储
  ▼
移远云 OpenAPI (HTTP: iot-api.quectelcn.com)
  │ GET /v2/binding/enduserapi/getDeviceBusinessAttributes
  │ Authorization: Bearer {token}
  ▼
微信小程序
  │ 每 2 秒轮询 → JSON 解析 → setData → WXML 渲染
  ▼
用户手机屏幕
```

> 不是 MQTT/WebSocket 直连设备，而是 **HTTP 轮询移远云平台**。Qth SDK 已经把数据推到平台了，小程序从平台拉即可。

---

## 3. 完整操作流程

### 3.1 DMP 平台配置

| 步骤 | 操作 | 结果 |
|:----|:-----|:-----|
| 1 | App SDK → 创建 App | 获得 userDomain + userDomainSecret |
| 2 | App 详情 → 关联产品 | 关联 `p11yMv`（智能骑行头盔产品） |
| 3 | 查看 OpenAPI 文档 | https://iot-cloud-docs.quectelcn.com/document/endUserAPIAccessInstruction |

### 3.2 用户注册与登录

由于小程序登录 UI 未开发，当前用 **curl 命令行** 完成注册并获取 token：

**① 发短信验证码**

```
POST /v2/sms/enduserapi/v2/sendPhoneSmsCode
参数: codeType=3, internationalCode=86, phone, random(16位), ts(毫秒), userDomain, signature
签名: SHA256(phone + codeType + random + ts + userDomainSecret) → 小写 hex
```

| ⚠️ 坑 | userDomain 末尾字符不要多写（我们曾误写 `.1N` 实际是 `.1`） |

**② 注册用户**

```
POST /v2/enduser/enduserapi/v2/phonePwdRegister
Body: phone, pwd(AES加密), random, smsCode, userDomain, agreementList
密码加密: AES-128-CBC/PKCS5Padding
  key = MD5(random).upper()[8:24]
  iv  = key[8:] + key[:8]
```

| ⚠️ 坑 | PC 需 `pip install pycryptodome` |
| ⚠️ 坑 | pwd 和 random 每次重新生成，不复用 |

**③ 登录拿 token**

```
POST /v2/enduser/enduserapi/phonePwdLogin
Query: internationalCode, phone, pwd(加密后), random, signature, userDomain
签名: SHA256(internationalCode + phone + pwd + random + userDomainSecret)
返回: accessToken(2h) + refreshToken(30d)
```

| ⚠️ 坑 | 签名中的 pwd 是加密后的 Base64，不是明文 |
| ⚠️ 坑 | token 过期用 refreshToken 续，无需重登录 |

**当前凭据**：

```js
// utils/config.js
USER_DOMAIN: 'C.DM.1507151130577592.1'
USER_DOMAIN_SECRET: '9hGmrVHHK2RQVmAi9nR6TLbhMF8w5diWhF1wshk2P4TS'
BASE_URL: 'https://iot-api.quectelcn.com'
PRODUCT_KEY: 'p11yMv'
DEVICE_KEY: '66ccff'

// utils/ws-client.js (硬编码)
ACCESS_TOKEN: 'Bearer eyJ...'  // 来自 curl 登录返回
```

### 3.3 设备绑定

```
POST /v2/binding/enduserapi/bindDeviceSn
Query: sn=7305831455A211F1822EF18D13D07623, pk=p11yMv
```

| ⚠️ 坑 | `bindDeviceDk` 返回 `5499 产品未授权DK绑定`，产品侧禁用了 DK 绑定 |
| ⚠️ 坑 | 参数用 Query String 不是 JSON Body |
| ⚠️ 坑 | 参数名是 `pk`/`sn`，不是 `productKey`/`sn` |
| 📌 注意 | SN 在 DMP 平台 → 设备详情页获取 |

### 3.4 数据轮询

```
GET /v2/binding/enduserapi/getDeviceBusinessAttributes?pk=p11yMv&dk=66ccff
Header: Authorization: Bearer {token}
返回: customizeTslInfo[{abId, resourceCode, resourceValce, ...}]
```

| ⚠️ 坑 | 字段名是 `abId` 不是 `id` |
| ⚠️ 坑 | 字段名是 `resourceValce` 不是 `value`（API 拼写错误） |
| ⚠️ 坑 | 设备离线时 `customizeTslInfo` 为空数组 |
| ⚠️ 坑 | 微信开发者工具必须勾"不校验合法域名" |
| ⚠️ 坑 | `wx.request` 的 method 必须与实际 API 一致（GET） |

---

## 4. 代码结构

```
WeChatMiniProgram/
├── app.js              全局入口 — globalData(token, isRiding, rideCache)
├── app.json            pages+窗口+定位权限
├── utils/
│   ├── config.js       凭据配置
│   ├── crypto.js       SHA256+MD5+AES-128-CBC（纯JS）
│   ├── logger.js       日志（console+文件，上限1000条）
│   └── ws-client.js    QuecClient：轮询+离线检测+日志，token从globalData取
└── pages/
    ├── login/           手机号+密码登录页
    └── index/           首页：地图+数据卡片+骑行控制+总结弹窗
        ├── index.js     状态机(idle/riding)+数据解析+缓存+总结+地图控制
        ├── index.wxml   导航栏+地图(展开/收起)+卡片(scroll-view)+按钮+弹窗
        ├── index.wxss   暗色主题+地图/导航栏/弹窗样式
        └── index.json   自定义导航栏
```

**index.js 数据流（完整）**：

```
登录→首页(idle,不轮询,手机定位)→点击"开始骑行"
  → client.connect()
  → 每2秒: GET getDeviceBusinessAttributes
  → 回调 _onData(items)
  → 第1遍扫描 isAlarm
  → 第2遍解析: abId→字段+单位, 报警态跳过温湿度
  → 缓存 rideCache[] + 更新 trackPoints
  → setData(数据+轨迹+地图)
→ 点击"结束骑行"
  → 弹窗确认→停止轮询
  → 遍历 cache → Haversine里程/avgSpeed/avgTemp/alarmCount
  → 总结弹窗
```

**报警状态处理**：

- 每轮字段先清零为 `"--"`，alarm 默认 `"正常"`
- 两遍扫描：先判断 isAlarm（abId=6≠0），再报警态跳过温湿度
- 设备常态发 `tsl[6]=0` 显式覆盖 API 缓存

---

## 5. 当前状态

| 功能 | 状态 | 说明 |
|:-----|:----:|:-----|
| 设备→移远云数据上传 | ✅ | QthDriver + LarkCloudService E2E 通过 |
| 用户注册/登录 | ✅ | 手机号+密码→crypto→API |
| 设备绑定 | ✅ | SN 绑定成功 |
| 实时数据显示 | ✅ | 温度/湿度/速度/位置/信号/报警，每 2 秒刷新 |
| 报警高亮 | ✅ | 报警态红色显示，缺字段显示 `"--"` |
| 小程序登录 UI | ✅ | pages/login，crypto 纯 JS 加密 |
| 骑行开始/结束控制 | ✅ | 开始→轮询+缓存，结束→确认弹窗+总结 |
| 骑行总结 | ✅ | 时长/速度/温度/里程(Haversine)/报警次数 |
| 地图轨迹 | ✅ | polyline实时绘制，展开/收起，跟随/手动 |
| 手机定位 | ✅ | 空闲态微信定位，骑行态头盔GPS |
| token 自动刷新 | 📅 | 过期后用 refreshToken 续 |
| WebSocket 实时推送 | 📅 | 替换 HTTP 轮询 |
| 导航 + 语音 | 📅 | Step B / v2 |

---

## 6. 参考文档

| 文档 | 路径 |
|:-----|:-----|
| 移远云 OpenAPI 文档 | https://iot-cloud-docs.quectelcn.com |
| Android SDK Demo | `WeChatMiniProgram/android_iot_sdk_1.12.0/` |
| 技术路线与验证方案 | `Modules/doc/LarkCloudService_route.md` |
| 设计总体方案 | `02_Design_scheme.md` |
