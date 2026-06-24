# 微信小程序 — 架构设计 (C4 模型)

> 架构框架: C4 模型 (Context → Container → Component → Code)  
> 完整开发记录见: `development.md`  
> 需求定义见: `requirements.md`

---

## C1 系统上下文

```
                  ┌──────────────┐
                  │   骑行者       │
                  └──────┬───────┘
                         │ 使用
                         ▼
┌──────────────────────────────────────────────────────────┐
│              智能骑行头盔 微信小程序                         │
└────┬─────────────────────┬──────────────────┬────────────┘
     │ BLE 设备数据          │ 地图底图          │ 手机 GPS
     ▼                     ▼                  ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ 头盔 BLE  │     │  腾讯地图     │     │  微信定位     │
│ GATT      │     │  CDN         │     │  wx.getLoc    │
└──────────┘     └──────────────┘     └──────────────┘
```

| 外部系统 | 协议 | 数据方向 |
|:---------|:-----|:--------|
| 头盔 BLE (`SmartHelmet-66ccff`) | BLE GATT Notify/Write | ↔ 双向（主数据通道） |
| 腾讯地图 CDN | HTTPS | ← 入站 |
| 微信定位 `wx.getLocation` | 微信 API | ← 入站 |

> **移远云已移除**（2026-06-24）：`iot-api.quectelcn.com` REST API 及 `data-service.js/ws-client.js/crypto.js` 已删除。

---

## C2 容器层

```
微信客户端 (用户手机)
├── 小程序容器 (微信沙箱)
│   ├── WXML 渲染线程  — 独立线程，不阻塞逻辑
│   ├── JS 逻辑线程    — 单线程事件循环
│   └── 本地存储       — app.log (日志) + smart_helmet_user (用户缓存)
└── 微信原生能力
    ├── <map> 腾讯地图
    └── GPS 芯片
```

---

## C3 组件层

```
UserService ──stub──→ LoginPage ──reLaunch──→ IndexPage
                                              │
StateService ──BLE callbacks──→ BleComponent
                                     │
                    data.t (BLE JSON)    NavComponent (FFF2 write)
                                     │               │
              ┌──────────────────────┼───────────────┤ BLE write
              ▼                      ▼               ▼
       AlarmComponent    RideComponent    MapComponent   头盔
       (纯函数·无状态)   (状态机·缓存)   (轨迹·跟随)   BLE GATT
```

| 组件 | 职责 | 文件 |
|:-----|:-----|:-----|
| UserService | 用户登录 stub（本地存储，云端占位） | `services/user-service.js` |
| StateService | 全局 BLE 状态管理中心，解析数据 → EventBus 广播 | `services/state-service.js` |
| BleComponent | BLE 扫描/连接/收发数据/自动重连 | `services/ble-service.js` |
| AlarmComponent | 报警检测、弹窗规则 | `services/alarm-service.js` |
| RideComponent | 骑行状态机、数据缓存、总结计算、轨迹点管理 | `services/ride-service.js` |
| MapComponent | 轨迹 polyline、marker 生成（纯函数） | `services/map-service.js` |
| NavComponent | 路线规划、BLE 写入导航指令 | `services/navigation-service.js` |
| CtrlComponent | 远端控制 BLE FFF3 指令下发 | `services/ctrl-service.js` |
| EventBus | 跨页面事件通知（on/off/emit） | `utils/event-bus.js` |
| CustomTabBar | 底部骑行/控制切换 | `custom-tab-bar/index.js` |
| LogComponent | 日志双写 | `utils/logger.js` |

> **已移除组件**：AuthComponent（`crypto.js`）、DataComponent（`data-service.js`）、WsComponent（`ws-client.js`）

---

## C4 代码层 (接口契约)

```
UserService (stub)
  login(phone, pwd) → Promise(userInfo)
  logout() → void
  isLoggedIn() → bool
  getUserInfo() → userInfo|null

StateService
  init() → void              获取 app + bus 引用
  getBleCallbacks() → {onConnected, onDisconnected, onData, onStatus, onDeviceFound}
  syncToPageData() → {}      从 globalData 同步所有状态到页面

BleComponent
  init(callbacks) → Promise
  scan() → void
  stopScan() → void
  connectById(deviceId) → void
  setCallbacks(callbacks) → void
  sendNav(dir, dist, road) → void
  sendCtrl(cmd) → void
  sendAck(id) → void
  disconnect() → void
  isConnected() → bool

AlarmComponent
  analyze(alarmType, level) → {
    displayText, shouldPopup, popupClass, icon
  }

RideComponent
  start() → void               重置状态 + 轨迹
  addRecord(parsed) → void     追加缓存（含 hr/spo2）
  end() → RideSummary { duration, avgSpeed, maxSpeed,
    avgTemp, maxTemp, avgHeartRate, maxHeartRate,
    avgSpO2, minSpO2, hrTimeSeries, distance, alarmCount, points }
  addTrackPoint(lat, lon) → void   P2: 轨迹点追加
  getTrackPoints() → []            只读
  getTrackPolylines() → []         缓存
  getTrackMarkers(iconPath, cog) → []  缓存
  getTrackPointCount() → int
  isActive() → bool
  clear() → void

MapComponent
  pushPoint(points, lat, lon) → newPoints
  buildPolyline(points) → polyline
  buildMarker(points, iconPath, rotate) → marker
  buildRoutePolyline(points) → polyline
  buildDestMarker(lat, lon, name) → marker

NavComponent
  selectDestination() → Promise<{lat, lng, name}>
  startNavigation(dest, origin) → void
  updateStep(stepIndex) → void
  stopNavigation(reason) → void
  pause() → void
  resume() → void
  isNavigating() → bool
  getState() → {state, remainDistance, routePolyline, dest}
  getCurrentInstruction() → {instruction, distance}

CtrlComponent
  lightAuto/On/Off() → void
  brightnessUp/Down() → void
  volumeUp/Down() → void
  powerSave/Emergency/Normal() → void
  alarmSos/Stealth/Cancel() → void
  parseCtrlState(data) → {lightMode, brightness, volume, powerMode}
  reset() → void
```

---

## EventBus 事件表

| 事件名 | 发布者 | 数据 | 订阅者 |
|:-------|:------|:-----|:------|
| `state:sensorUpdate` | StateService | `{formatted, raw}` | index.js |
| `state:alarmTriggered` | StateService | `{type, level, displayText, shouldPopup, popupClass, icon}` | index.js, control.js |
| `state:alarmCancelled` | StateService | — | index.js, control.js |
| `state:ctrlChanged` | StateService | `{lightMode, brightness, volume, powerMode}` | control.js |
| `ble:connected` | StateService | — | index.js, control.js |
| `ble:disconnected` | StateService | — | index.js, control.js |
| `ble:deviceFound` | StateService | `[{deviceId, name}]` | index.js |
| `ble:status` | StateService | `string` | index.js |
| `ride:start` | index.js | — | custom-tab-bar |
| `ride:end` | index.js | — | custom-tab-bar |
| `nav:stateChange` | NavService | `string` | custom-tab-bar |

---

## 数据所有权

| 数据 | Owner | 读写约束 |
|:-----|:------|:--------|
| userInfo | UserService | 单写多读（本地存储） |
| isRiding | RideComponent | 单写多读 |
| rideCache[] | RideComponent | 单写多读 |
| trackPoints[] | RideComponent (P2) | 单写多读（addTrackPoint 写入） |
| ctrlState | CtrlComponent → globalData | 单写多读 |
| latestSensorData | StateService → globalData | 单写多读 |
| alarmActive | StateService → globalData | 单写多读 |
| showAlarmPopup | Pages (index/control) | 单写单读 |

> **P2 变更**：trackPoints 数据所有权从 Page data 迁移到 RideComponent。页面从 RideService.getTrackPoints() 读取，不再本地维护。

---

## 状态机

```
骑行: idle ──start()──→ riding ──end()──→ idle (summary)

地图: following=true ──拖拽──→ following=false ──点⊙──→ following=true

报警: normal ──alarm_type≠0,level≥2──→ popup ──alarm_type=0──→ normal

导航: idle ──selectDestination()──→ planning ──路线就绪──→ navigating ──到达──→ arrived
                                                    │
                                                    └──cancel──→ cancelled
```

---

## 架构决策 (ADR)

| ID | 决策 | 理由 |
|:---|:-----|:-----|
| ADR-1 | 模块化单体 | 单用户、无并发 |
| ADR-2 | BLE GATT Notify（主通道） | 低延迟、无云端依赖 |
| ADR-3 | 零 npm | `require()` 即可 |
| ADR-4 | globalData + EventBus 共享 | 状态通过 globalData 共享，变更通过 EventBus 通知 |
| ADR-5 | 导航指令经 BLE FFF2 直连 | 低延迟（<100ms）、无云端依赖 |
| ADR-6 | 移远云移除（2026-06-24） | 项目已舍弃移远云，数据通道仅 BLE |
| ADR-7 | StateService 全局 BLE 状态管理（P1 修复） | 两个页面 BLE onData 回调重复 → StateService 统一处理 → EventBus 广播 |
| ADR-8 | trackPoints 数据所有权迁移到 RideService（P2 修复） | 防止页面切换时数据丢失，RideService 是单一数据源 |

---

## 架构约束

| 约束 | 目标 |
|:-----|:-----|
| 组件行数 | Service/Utility ≤ 250 行，Page ≤ 600 行（index.js 作为调度器例外） |
| setData 频率 | ≤ 5 次/秒 |
| 全局状态 | ≤ 10 个 |
| 轨迹点 | ≤ 500 |
| npm 依赖 | 0 |

---

## 相关文档

| 文档 | 内容 |
|:-----|:-----|
| `development.md` | 全生命周期开发记录 (含踩坑/测试/上线) |
| `requirements.md` | 需求定义 R1~R13 |
