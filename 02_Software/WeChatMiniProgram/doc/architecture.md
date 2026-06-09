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
     │ 登录 · 设备数据      │ 地图底图          │ 手机 GPS
     ▼                     ▼                  ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ 移远云    │     │  腾讯地图     │     │  微信定位     │
│ IoT API   │     │  CDN         │     │  wx.getLoc    │
└──────────┘     └──────────────┘     └──────────────┘
```

| 外部系统 | 协议 | 数据方向 |
|:---------|:-----|:--------|
| 头盔 BLE (`SmartHelmet-66ccff`) | BLE GATT Notify/Write | ↔ 双向（主数据通道） |
| 移远云 `iot-api.quectelcn.com` | HTTPS REST | ↔ 双向（历史方案，当前未使用） |
| 腾讯地图 CDN | HTTPS | ← 入站 |
| 微信定位 `wx.getLocation` | 微信 API | ← 入站 |

---

## C2 容器层

```
微信客户端 (用户手机)
├── 小程序容器 (微信沙箱)
│   ├── WXML 渲染线程  — 独立线程，不阻塞逻辑
│   ├── JS 逻辑线程    — 单线程事件循环
│   └── 本地存储       — app.log (日志)
└── 微信原生能力
    ├── <map> 腾讯地图
    └── GPS 芯片
```

**外部容器**：移远云 REST API · 腾讯地图 CDN

---

## C3 组件层

参考 `development.md` §3 的完整组件定义，这里仅列核心组件：

```
AuthComponent ──token──→ BleComponent
                              │
                    data.t (BLE JSON)    NavComponent (FFF2 write)
                              │               │
              ┌───────────────┼───────────────┤ BLE write
              ▼               ▼               ▼
       AlarmComponent    RideComponent    MapComponent   头盔
       (纯函数·无状态)   (状态机·缓存)   (轨迹·跟随)   BLE GATT
```

| 组件 | 职责 | 文件 |
|:-----|:-----|:-----|
| AuthComponent | 登录、token 管理 | `login.js` + `crypto.js` |
| BleComponent | BLE 扫描/连接/收发数据/自动重连 | `services/ble-service.js` |
| AlarmComponent | 报警检测、弹窗规则 | `services/alarm-service.js` |
| RideComponent | 骑行状态机、Haversine 总结 | `services/ride-service.js` |
| MapComponent | 轨迹 polyline、marker 生成 | `services/map-service.js` |
| NavComponent | 路线规划、BLE 写入导航指令 | `services/navigation-service.js` |
| RemoteControlComponent *📅* | 远端控制 UI + BLE FFF3 指令下发 | 首页控制面板（待实现） |
| LogComponent | 日志双写 | `utils/logger.js` |

> **历史方案备注**：`DataComponent`（`services/data-service.js`）为 v1 初期的 HTTP 轮询方案，当前未被 `index.js` 引用。数据采集已由 `BleComponent` 通过 BLE Notify 接管。

---

## C4 代码层 (接口契约)

```
AuthComponent
  login(phone: string, pwd: string) → token
  getToken() → string

BleComponent
  init(callbacks) → Promise
  scan() → void
  stopScan() → void
  connectById(deviceId) → void
  sendNav(dir, dist, road) → void
  sendCtrl(cmd) → void
  sendAck(id) → void
  disconnect() → void
  isConnected() → bool

AlarmComponent
  analyze(alarmType, level) → {
    displayText: string, shouldPopup: bool,
    popupClass: string, icon: string
  }

RideComponent
  start() → void
  end() → RideSummary { duration, avgSpeed, maxSpeed,
    avgTemp, maxTemp, distance, alarmCount, points }

MapComponent
  pushPoint(lat, lon) → void
  buildPolyline(points) → polyline
  buildMarker(points, iconPath) → marker
  buildRoutePolyline(points) → polyline
  buildDestMarker(lat, lon, name) → marker

NavComponent
  selectDestination() → Promise<{lat, lng, name}>
  startNavigation(dest) → void
  updateStep(stepIndex) → void
  stopNavigation() → void
  pause() → void
  resume() → void

RemoteControlComponent *📅*
  toggleLight() → void
  setVolume(level: int) → void
  sendCommand(cmd: string) → void
```

---

## 数据所有权

| 数据 | Owner | 读写约束 |
|:-----|:------|:--------|
| token | AuthComponent | 单写多读 |
| isRiding | RideComponent | 单写多读 |
| rideCache[] | RideComponent | 单写多读（BLE onData 回调写入） |
| trackPoints[] | MapComponent | 单写单读 |
| showAlarmPopup | AlarmComponent | 单写多读 |

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
| ADR-2 | BLE GATT Notify（主通道） | 低延迟、无云端依赖。HTTP 轮询为历史方案，已弃用 |
| ADR-3 | 零 npm | `require()` 即可 |
| ADR-4 | globalData 共享 | 5 个状态不需 Redux |
| ADR-5 | 导航指令经 BLE FFF2 直连 sendNav 下行 | 低延迟（<100ms）、无云端依赖。已从 writeData REST API 迁移到 BLE 直连 |

---

## 架构约束

| 约束 | 目标 |
|:-----|:-----|
| 组件行数 | Service/Utility ≤ 200 行，Page ≤ 600 行（index.js 作为调度器例外） |
| setData 频率 | ≤ 5 次/秒 |
| 全局状态 | ≤ 8 个 |
| 轨迹点 | ≤ 500 |
| npm 依赖 | 0 |

---

## 相关文档

| 文档 | 内容 |
|:-----|:-----|
| `development.md` | 全生命周期开发记录 (含踩坑/测试/上线) |
| `requirements.md` | 需求定义 R1~R13 |
| `README.md` | 项目说明 + 状态表 |
