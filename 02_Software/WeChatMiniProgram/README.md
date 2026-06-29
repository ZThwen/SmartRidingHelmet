# 智能骑行头盔 — 微信小程序开发文档

> **当前状态**：🟢 Step A ✅ · Step B ✅ (全部完成) · Step C 📅 (语音交互)
> **更新日期**：2026-06-29

---

## 1. 技术选型：为什么是小程序不是 Android App

| | Android App | 微信小程序 |
|:--|:----|:-----|
| 开发语言 | Java/Kotlin | JavaScript（接近 Python） |
| 分发 | 打包 APK，应用商店上架 | 扫码即用，微信内打开 |
| 开发环境 | Android Studio（重） | 微信开发者工具（轻） |
| 中国队选手体验 | 需安装 | 微信生态内直达 |

**结论**：小程序是正确选择。BLE 直连无需云端中转，纯微信原生 API 即可完成全部功能。

---

## 2. 通信架构

### 当前方案：BLE GATT 直连（全部功能）

```
STM32F413 + EC200U (MicroPython)
  │ BLE GATT Notify (FFF1) ── 传感器数据上行
  │ BLE GATT Write  (FFF2) ── 导航指令下行
  │ BLE GATT Write  (FFF3) ── 控制指令下行
  │ BLE GATT Write  (FFF4) ── 报警确认上行
  ▼
微信小程序 (ble-service.js BLE Central)
  │ StateService 全局 BLE 数据处理 → EventBus 广播
  ▼
各页面 (index / control) 订阅事件 → setData → WXML
```

- **数据上行**（头盔→小程序）：BLE GATT Notify FFF1，2s 间隔推送传感器合并 JSON
- **导航下行**（小程序→头盔）：BLE GATT Write FFF2，5s 间隔推送导航指令
- **控制下行**（小程序→头盔）：BLE GATT Write FFF3，灯光/音量/电源/报警控制
- **报警确认上行**（头盔→小程序）：BLE GATT Write FFF4，报警确认回执
- **延迟**：<100ms，无云端依赖
- **消息类型**：t=0 传感器数据（含心率/血氧）、t=5 报警触发、t=6 报警解除、t=7/8/9 控制状态回推、t=99 心跳

> 历史方案：移远云 HTTP 轮询（2026-05-17 ~ 2026-05-28），已于 2026-06-24 完全移除。`data-service.js`、`ws-client.js`、`crypto.js` 均已删除。

---

## 3. 代码结构

```
WeChatMiniProgram/
├── app.js                全局入口 — globalData(userInfo, isRiding, rideCache, bleConnected, bleStatus, ctrlState, alarmActive, smsPhone, latestSensorData)
├── app.json              pages + 窗口 + 定位权限 (custom navigation style)
├── services/
│   ├── state-service.js         全局 BLE 状态管理中心 — onData 解析 → EventBus 广播（P1 修复）
│   ├── ble-service.js           BLE Central 客户端（扫描/连接/收发 notify-write/自动重连）
│   ├── alarm-service.js         报警检测 + 弹窗规则（纯函数）
│   ├── ride-service.js          骑行状态机 + Haversine 总结计算 + 轨迹点管理（P2 修复）
│   ├── map-service.js           轨迹 polyline + marker 生成（纯函数）
│   ├── navigation-service.js    导航状态机（腾讯地图 API 算路 + BLE FFF2 指令推送）
│   ├── ctrl-service.js          远端控制 21 命令（灯光/音量/电源/报警）+ parseCtrlState
│   └── user-service.js          用户登录 stub（本地存储，云端占位）
├── utils/
│   ├── config.js           BLE + 腾讯地图凭据
│   ├── event-bus.js        跨页面事件总线（on / off / emit）
│   ├── logger.js           日志（console + 文件，上限 1000 条）
│   └── ble-protocol.js     BLE 协议常量（UUID、设备前缀、重连参数、类型映射）
├── pages/
│   ├── login/              登录页（手机号 + 密码，UserService stub 本地存储）
│   ├── index/              首页：地图 + 数据卡片 + 骑行控制 + 导航 + 报警 + 总结
│   │   ├── index.js        调度器（EventBus 订阅者，不含 BLE onData 回调）
│   │   ├── index.wxml      导航栏 + 地图(展开/收起) + 卡片 + 弹窗 + 导航浮层
│   │   ├── index.wxss      白色主题 + #66CCFF 强调色
│   │   └── index.json      自定义导航栏
│   └── control/            控制页：灯光/音量/电源/报警/紧急电话
│       ├── control.js      控制面板（EventBus 订阅者，BLE FFF3 下发指令）
│       ├── control.wxml     按钮 + 滑块 + 状态显示
│       ├── control.wxss     白色主题
│       └── control.json
├── custom-tab-bar/
│   └── index.js            自定义底部 Tab（骑行/控制切换 + 浮动导航按钮）
└── doc/                    文档 5 篇（README / architecture / requirements / development / voice_feasibility）
```

**数据流（BLE 直连）**：

```
登录 → 首页(idle, 手机 GPS 定位) → 点击"开始骑行"
  → BleService.init() + scan() + connectById()
  → BLE Notify 每 2s 推送 JSON: {"t":0,"d":{tmp,hum,spd,lat,lon,alt,lux,hr,spo2,...}}
  → StateService 全局 onData 回调:
    t=0 → EventBus("state:sensorUpdate") → index.js setData + RideService.addRecord() + addTrackPoint()
    t=5 → EventBus("state:alarmTriggered") → index.js 全屏报警弹窗 + control.js 更新状态
    t=6 → EventBus("state:alarmCancelled") → index.js 清除报警 + control.js 更新状态
    t=7 → EventBus("state:ctrlChanged") → control.js UI 同步
  → 控制页操作 → ctrl-service.js → BLE FFF3 sendCtrl → 头盔执行
  → 导航 → navigation-service.js → BLE FFF2 sendNav → 头盔播报
  → 点击"结束骑行"
  → 确认 → 停止 BLE → RideService.end() → EventBus("ride:end") → 总结弹窗(含地图)
```

---

## 4. 当前状态

### Step A *(✅ 已完成 2026-06-01)*

| 功能 | 状态 | 说明 |
|:-----|:----:|:-----|
| BLE 直连数据通道 | ✅ | BLE GATT Notify FFF1，t=0 传感器/t=5 报警/t=6 解除/t=99 心跳 |
| 用户登录 | ✅ | 手机号+密码 → UserService stub（本地存储，无云端后端） |
| 实时数据显示 | ✅ | 温度/湿度/速度/心率/血氧/位置/光照/报警，BLE 2s 推送 |
| 报警弹窗 | ✅ | 碰撞 Lv2+/SOS 全屏红色弹窗 + 报警取消功能（BLE FFF4 ack） |
| 骑行控制 | ✅ | 开始→BLE数据+缓存，结束→确认→总结 |
| 骑行总结 | ✅ | 全屏页面，时长/速度/温度/心率/里程/报警次数，起点+终点标记 |
| 地图轨迹 | ✅ | polyline 实时绘制（BLE GPS），canvas 蓝点 marker，show-location 条件切换 |
| 测试文件 | ✅ | Tests/miniprogram/ 测试文件 |

### Step B *(✅ 全部完成 2026-06-24)*

| 功能 | 状态 | 说明 |
|:-----|:----:|:-----|
| 导航路线规划 | ✅ | navigation-service.js + 腾讯地图 bicycling API |
| 导航指令推送 | ✅ | BLE FFF2 sendNav（5s 间隔推流） |
| 导航界面 | ✅ | 指令浮层 + 规划路线 polyline（绿色） + 底部浮动按钮 |
| polyline 修复 | ✅ | 前向差分解压 + act_desc 方向映射 |
| **远端控制** | ✅ | pages/control + ctrl-service.js 21 指令 + BLE FFF3 sendCtrl |
| 灯光控制 | ✅ | 自动/手动模式、开/关灯、闪烁、亮度 0-100%（100%=PWM50%） |
| 音量控制 | ✅ | 0-7 级 |
| 电源模式 | ✅ | 正常/省电/紧急 |
| 报警控制 | ✅ | SOS/静默报警/取消报警 |
| 紧急电话 | ✅ | SMS 通知联系人 |
| 心率/血氧显示 | ✅ | BLE t=0 数据含 hr/spo2 字段，骑行总结含心率时序图 |
| P1 修复：StateService | ✅ | 全局 BLE 回调中心，消除两页面 onData 重复逻辑 |
| P2 修复：轨迹所有权 | ✅ | trackPoints 迁移到 RideService，防止页面切换数据丢失 |
| 控制状态同步 | ✅ | EventBus state:ctrlChanged → control.js UI 同步 |
| 自定义 TabBar | ✅ | custom-tab-bar 骑行/控制切换 + 浮动导航按钮 |

### Step C *(📅)*

| 功能 | 状态 | 说明 |
|:-----|:----:|:-----|
| 语音交互 | 📅 | 手机微信语音 API → BLE FFF3 下发指令（详见 doc/voice_feasibility.md） |
| 导航位置播报升级 | 📅 | 头盔 GNSS 自主播报（替代 5s 推流） |

---

## 5. 参考文档

| 文档 | 路径 |
|:-----|:-----|
| 架构设计 (C4) | `doc/architecture.md` |
| 需求定义 | `doc/requirements.md` |
| 开发全记录 | `doc/development.md` |
| 语音可行性分析 | `doc/voice_feasibility.md` |
| 设计总体方案 | `../../00_Planning/02_Design_scheme.md` |
| 腾讯地图 WebService API | https://lbs.qq.com/service/webService/webServiceGuide/webServiceRoute |
