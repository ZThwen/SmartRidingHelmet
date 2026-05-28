# 微信小程序 — 开发全记录

> 项目: 智能骑行头盔  
> 版本: Step A v1.0 · 架构框架: C4 模型  
> 日期: 2026-05-23  
> 平台: 微信小程序 (基础库 3.16.1)  
> 语言: JavaScript (CommonJS · 零 npm 依赖)

---

## 架构总览 (C4 模型)

本文档采用 **C4 模型**（Simon Brown, 2010）描述软件架构，四级递进，每一级面向不同的读者。

```
C1 系统上下文    —  给所有人看    —  系统在什么环境中运行
C2 容器          —  给技术团队看   —  系统由哪些运行时组成
C3 组件          —  给开发者看    —  每个容器里有什么业务组件
C4 代码          —  给维护者看    —  每个组件的接口契约
```

| C4 级别 | 对应本文 § | 核心问题 |
|:--------|:----------|:---------|
| C1 | §0.1 系统上下文图 | 这个系统在什么环境里？和谁交互？ |
| C2 | §0.2 容器层 | 代码跑在哪些运行时里？ |
| C3 | §2.5 组件层 + §4.1 逻辑视图 | 每个容器里有什么组件？怎么集成？ |
| C4 | §2.5.3 接口契约 + §4.4 数据视图 | 每个组件的接口长什么样？数据谁管？ |
| 交叉 | §4.2 流程视图 · §4.3 部署视图 · §4.5 安全视图 · §4.6 ADR · §4.7 约束 | 多视角正交验证 |

### 开发阶段

```
Step A ✅           Step B 🟡 开发中    Step C 📅       上线 📅
需求→架构→开发→测试    导航 (writeData 反向通道)  语音交互         预发布→提审→全量
```

---

## 0. C1 系统上下文 · C2 容器层

### 0.1 C1 系统上下文图

```
                    ┌──────────────┐
                    │   骑行者      │
                    │  (用户)      │
                    └──────┬───────┘
                           │ 使用
                           ▼
┌──────────────────────────────────────────────────────────┐
│                                                          │
│                  智能骑行头盔 微信小程序                    │
│                  (本项目的系统边界)                         │
│                                                          │
└────┬─────────────────────┬──────────────────┬────────────┘
     │ 登录 · 轮询设备数据  │ 显示地图底图      │ GPS 定位
     ▼                     ▼                  ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ 移远云    │     │  腾讯地图     │     │  微信定位      │
│ IoT 平台  │     │  (地图瓦片)   │     │  (wx.getLoc) │
│          │     │              │     │              │
│ REST API │     │  <map> 组件   │     │  手机 GPS    │
│ 设备数据  │     │  自动加载     │      │  持续定位     │
└──────────┘     └──────────────┘     └──────────────┘
```

| 外部系统 | 关系 | 协议 | 数据方向 |
|:---------|:-----|:-----|:--------|
| 骑行者 | 使用者 | 触摸/点击 | 输入 → 系统 |
| 移远云 IoT | 设备数据 + 用户鉴权 | HTTPS REST | 双向 |
| 腾讯地图 | 地图底图 | HTTPS CDN | 系统 ← 外部 |
| 微信定位 | 手机 GPS | `wx.*` API | 系统 ← 手机 |

### 0.2 C2 容器层

系统内部由两个运行时容器组成：

```
┌─────────────────────────────────────────────────┐
│  微信客户端 (用户手机)                            │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │  小程序容器 (微信沙箱)                     │   │
│  │  ┌──────────┐  ┌──────────┐             │   │
│  │  │ WXML 渲染 │  │ JS 逻辑   │             │   │
│  │  │ (视图线程)│  │ (单线程)  │             │   │
│  │  └──────────┘  └────┬─────┘             │   │
│  │                     │ wx.request        │   │
│  │  ┌──────────┐       │ wx.getLocation    │   │
│  │  │ 本地存储  │       │ wx.getFileSysMgr  │   │
│  │  │ app.log  │       │                   │   │
│  │  └──────────┘       │                   │   │
│  └─────────────────────┼───────────────────┘   │
│                        │                        │
│  ┌─────────────────────┼───────────────────┐   │
│  │  微信原生能力        │                    │   │
│  │  <map> 腾讯地图     │ GPS 芯片           │   │
│  └─────────────────────┼───────────────────┘   │
└────────────────────────┼───────────────────────┘
                         │ HTTPS
        ┌────────────────┴────────────────┐
        ▼                                 ▼
┌──────────────┐                ┌──────────────────┐
│ 移远云 API   │                │ 腾讯地图 CDN      │
│ (外部容器)   │                │ (外部容器)        │
└──────────────┘                └──────────────────┘
```

| 容器 | 技术 | 职责 |
|:-----|:-----|:-----|
| 小程序容器 | 微信基础库 3.16.1 | 运行所有业务代码 |
| WXML 渲染线程 | 微信原生 | 独立渲染，不阻塞逻辑 |
| JS 逻辑线程 | 单线程事件循环 | 轮询、解析、状态管理 |
| 本地存储 | `wx.getFileSystemManager` | 日志文件 `app.log` |
| 移远云 API | 第三方 REST | 鉴权 + 设备数据 |
| 腾讯地图 CDN | 第三方 | `<map>` 组件底图 |

### 0.3 技术栈

| 层 | 技术选型 |
|:---|:---------|
| 运行时 | 微信小程序基础库 ≥ 2.20 |
| 视图 | WXML + WXSS |
| 逻辑 | JavaScript (CommonJS) |
| 网络 | HTTPS · `wx.request` |
| 地图 | `<map>` 原生组件 |
| 加密 | SHA256 + MD5 + AES-128-CBC (纯 JS) |
| 数据 | JSON |
| 模块化 | `require()` (微信原生) |

### 0.4 未选方案

| 不选 | 原因 |
|:-----|:-----|
| Taro / uni-app | 单平台无需跨端编译层 |
| TypeScript | 轻量项目无类型收益，增构建成本 |
| Redux / MobX | 5 个全局变量用 `globalData` 足够 |
| Vant Weapp | 自定暗色主题，不需要 100KB+ 组件库 |
| npm | 微信 npm 需构建，`require()` 即可 |
| WebSocket | QuecCloud WS 协议未文档化 |
| 自建后端 | 移远云已提供完整 REST API |

### 0.5 质量属性

| 维度 | 轻量级目标 |
|:-----|:-----------|
| 可用性 | 失败静跳，2s 自动重试 |
| 可靠性 | 零外部依赖，NaN 保护 |
| 性能 | 零框架开销，轨迹 ≤ 500 点，日志 ≤ 1000 行 |
| 安全性 | HTTPS 全链路，Token 不落盘，AES 加密传输 |
| 可维护性 | 文件 ≤ 500 行，函数 ≤ 50 行，中文注释 |
| 可扩展性 | 新字段加 `ID_MAP` 一行，新页面加路由 |

### 0.6 工具链

| 工具 | 用途 |
|:-----|:-----|
| 微信开发者工具 | IDE (编辑 + 调试 + 上传) |
| curl | API 独立验证 |
| Node.js | crypto.js 离线验证 (仅开发用) |
| Git | 版本管理 |

---

## 1. 需求分析 ✅

### 1.1 背景

骑行中无法低头看头盔屏幕。用户随身带手机，微信小程序免安装。

### 1.2 功能需求

| 编号 | 模块 | 需求 |
|:-----|:-----|:-----|
| R1 | 用户认证 | 手机号+密码登录，token 全局管理 |
| R2 | 实时数据 | 温湿度/速度/位置/信号/报警，2s 轮询，缺="--"，碰撞 Lv2+/SOS 全屏弹窗 |
| R3 | 骑行控制 | 开始→轮询+缓存，结束→确认→总结，退出保护 |
| R4 | 地图 | 手机/头盔双模定位，实时轨迹，跟随/手动，展开/收起 |
| R5 | 骑行总结 | 时长/速度/温度/里程(Haversine)/报警次数弹窗 |
| R6 | 日志 | console + app.log，上限 1000 行 |

### 1.3 Step B 需求 *(📅)*

| 编号 | 模块 | 需求 |
|:-----|:-----|:-----|
| R7 | 导航输入 | 输入目的地 → 地图选点 → 规划路线 |
| R8 | 指令下发 | 路线解析 → sendTsl(ID10/11/12) |
| R9 | 导航界面 | 地图显示路线 + 当前指令 (方向+距离+路名) |
| R10 | 心率显示 | 云端收心率 → 实时数值 + 异常预警 |
| R11 | 头灯控制 | 远程开关 → sendTsl |
| R12 | 电量显示 | 云端收电量 → 图标 + 百分比 + 低电提醒 |

### 1.4 Step C 需求 *(📅)*

| 编号 | 模块 | 需求 |
|:-----|:-----|:-----|
| R13 | 语音指令 | 语音输入 → 识别 → 指令 ("开始导航""结束骑行") |

> 嵌入式端 (Audio/TTS/传感器驱动/电池 ADC) 不在此文档范围。

### 1.5 HTTP vs WebSocket

| 维度 | HTTP 轮询 ✅ | WebSocket |
|:-----|:-------------|:----------|
| 延迟 | ≤2s (轮询) / 1-3s (writeData) | <100ms |
| 适用性 | 骑行场景和导航都够用 | 过度设计 |
| 协议 | REST API **已文档化** | 未公开 |

> writeData 打通了反向通道，导航指令延迟 1-3s，非安全关键功能，可接受。
> 如后续需要更低延迟，可加 WebSocket Relay，业务层（navigation-service.js）不变。

---

## 2. 业务架构 ✅

### 2.1 业务场景

| ID | 场景 | 角色 | 触发 |
|:---|:-----|:-----|:-----|
| S1 | 登录 | 骑行者 | 打开小程序 |
| S2 | 开始骑行 | 骑行者 | 点"开始骑行" |
| S3 | 骑行监控 | 系统 | 每 2s 自动 |
| S4 | 报警触发 | 设备 | 碰撞/SOS |
| S5 | 报警解除 | 设备 | 恢复常态 |
| S6 | 结束骑行 | 骑行者 | 点"结束骑行" |
| S7 | 中途退出 | 骑行者 | 点返回 |
| S8 | 设备离线 | 系统 | 超 15s 无数据 |
| S9 | 地图交互 | 骑行者 | 拖拽/展开/回正 |
| S10 | 导航 | 骑行者 | 选目的地 → 指令逐条下发 → 到达/取消 |

### 2.2 核心流程

```
登录 → 首页(空闲) → 点开始 → 轮询启动 → 数据刷新 + 轨迹
                                    │
              ┌─────────────────────┼──────────────────┐
              ▼                     ▼                  ▼
        碰撞/SOS触发           点"结束骑行"         点"导航"
              │                     │                  │
              ▼                     ▼                  ▼
        红色弹窗显示           确认弹窗         选目的地 + 算路
        (温湿度速度--)              │                  │
              │              ┌─────┴─────┐            │
              ▼              ▼           ▼            ▼
        报警解除          停止轮询     继续骑行  每5秒推流指令
              │              │                        │
              ▼              ▼                  ┌─────┴─────┐
        恢复正常         计算总结弹窗          到达        取消
```

### 2.3 模块分解

```
                      ┌──────────────┐
                      │   AuthMgr    │
                      │  login()    │
                      └──────┬───────┘
                             │ token
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
    ┌───────────┐   ┌───────────┐   ┌───────────┐
    │ DataMgr   │   │ RideMgr   │   │  MapMgr   │
    │ poll()    │   │ start()   │   │ track()   │
    │ parse()   │   │ end()     │   │ follow()  │
    └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
          │               │               │
          ▼               ▼               ▼
    ┌───────────┐   ┌───────────┐   ┌───────────┐
    │AlarmMgr   │   │ LogMgr    │   │globalData │
    │ detect()  │   │ log()     │   │ 共享数据   │
    └───────────┘   └───────────┘   └───────────┘
```

---

## 3. C3 组件层 · C4 代码层

### 3.1 组件定义 (C3)

| 组件 | 拥有的数据 | 行为 | 接口 |
|:-----|:----------|:-----|:-----|
| **AuthComponent** | token, refreshToken | 登录、token 存取 | `login(phone,pwd)` `getToken()` |
| **DataComponent** | 轮询定时器 | 启停轮询、调 API | `startPoll(onData)` `stopPoll()` |
| **RideComponent** | isRiding, rideCache[], startTime | 骑行生命周期、总结 | `start()` `end()` `getSummary()` |
| **MapComponent** | trackPoints[], following, expanded | 轨迹、跟随、展开 | `pushPoint(lat,lon)` `toggleFollow()` `toggleExpand()` |
| **AlarmComponent** | 无状态 (纯函数) | 报警检测、弹窗判断 | `analyze(items)` → `{isAlarm,text,popup}` |
| **LogComponent** | 日志缓冲区 | 写日志、刷盘 | `write(tag,msg)` `flush()` |
| **NavComponent** | 路线、指令序列、推流定时器 | 选目的地、算路、逐条推流到云 | `startNavigation(dest)` `updateStep()` `stopNavigation()` |
| **VoiceComponent** *📅* | 语音会话 | 语音输入→指令 | `listen()` `onCommand(cb)` |

### 3.2 集成架构

```
AuthComponent ──token──→ DataComponent
                              │
                    items[] (原始数据)    NavComponent
                              │               │
              ┌───────────────┼───────────────┤ writeDevice
              ▼               ▼               ▼
       AlarmComponent    RideComponent    MapComponent   移远云 REST API
              │               │               │
              ▼               ▼               ▼
         index.setData   index.setData   index.setData
        (弹窗+红字)     (温湿度速度)     (轨迹+跟随)

LogComponent ←── 所有组件
```

| 集成关系 | 方向 | 方式 | 耦合度 |
|:---------|:-----|:-----|:------|
| Auth → Data | 单向 | 共享 `globalData.token` | 松 |
| Data → Alarm | 单向 | 函数调用 | 松 (纯函数) |
| Data → Ride | 单向 | 回调 | 松 |
| Nav → Data | 单向 | 调用 `writeDevice` | 松 |
| Ride → Map | 单向 | 共享 `globalData.rideCache` | 松 |
| 全部 → Log | 多对一 | 函数调用 | 松 |

### 3.3 接口契约 (C4 代码层)

```
AuthComponent
  login(phone: string, pwd: string) → Promise<token>
  getToken() → string

DataComponent
  startPoll(onData: (items: TslItem[]) → void) → void
  stopPoll() → void

AlarmComponent
  analyze(items: TslItem[]) → {
    isAlarm: bool, alarmType: string, level: number,
    displayText: string, shouldPopup: bool
  }

RideComponent
  start() → void
  end() → RideSummary
  isActive() → bool
  RideSummary = { duration, avgSpeed, maxSpeed,
    avgTemp, maxTemp, distance, alarmCount, points }

MapComponent
  pushPoint(lat: number, lon: number) → void
  toggleFollow() → void · toggleExpand() → void
  resetCenter() → void

NavComponent
  selectDestination() → Promise<{lat, lng, name}>
  startNavigation(dest: {lat, lng, name}) → void
  updateStep(stepIndex: number) → void
  stopNavigation() → void

LogComponent
  write(tag: 'QC'|'PAGE'|'LOG', msg: string) → void
  flush() → void
```

### 3.4 DDD 领域建模

```
骑行域 (Ride Domain)
  ├── 聚合根: Ride
  │     ├── 实体: RideSession { id, startTime, endTime, status }
  │     └── 值对象: RideCacheEntry { time, temp, humid, speed,
  │                   lat, lon, alt, signal, alarm }
  ├── 值对象: GeoPoint · AlarmInfo
  └── 领域服务: SummaryCalculator
        calcDuration · calcAvgSpeed · calcDistance(Haversine) · calcAlarmCount

报警域 (Alarm Domain)
  └── 值对象: AlarmResult { isAlarm, displayText, level, shouldPopup }
      规则: 碰撞 Lv1 → 卡片红字
            碰撞 Lv2+ → 卡片红字 + 全屏弹窗
            SOS 任意 → 卡片红字 + 全屏弹窗(闪烁)
            alarm_type=0 → 清除

地图域 (Map Domain)
  ├── 值对象: TrackPoint { lat, lon }
  ├── 实体: MapState { center, scale, following, expanded }
  └── 规则: 未骑行→手机GPS · 开始骑行→设备GPS
            用户拖拽→取消跟随 · 点⊙→恢复跟随
```

### 3.5 代码映射

| 组件 | 当前 | 重构目标 |
|:-----|:-----|:--------|
| AuthComponent | `pages/login/login.js` | 不变 |
| DataComponent | `utils/ws-client.js` | `services/data-service.js` |
| AlarmComponent | `index.js._onData()` 内嵌 | `services/alarm-service.js` |
| RideComponent | `index.js` 骑行函数 | `services/ride-service.js` |
| MapComponent | `index.js` 地图函数 | `services/map-service.js` |
| LogComponent | `utils/logger.js` | 不变 |

---

## 4. 端到端时序

```
骑行者         小程序(Auth)    小程序(Data)     移远云        骑行者(UI)
  │                │               │              │              │
  │─输入手机号+密码→│               │              │              │
  │                │─AES加密──────→│              │              │
  │                │               │─phonePwdLogin→│              │
  │                │               │←──token─────│              │
  │                │               │              │              │
  │                │───reLaunch───→│                            │
  │                │               │                            │←─首页渲染
  │                │               │                            │
  │─点"开始骑行"──────────────→ RideComponent                    │
  │                │               │← startPoll()               │
  │                │               │                            │
  │                │               │───(每2s循环)──→│            │
  │                │               │←──items[]───│              │
  │                │               │─→ AlarmComponent.analyze() │
  │                │               │─→ RideComponent.cache()    │
  │                │               │─→ MapComponent.pushPoint() │
  │                │               │                            │─setData(数据+轨迹)
  │                │               │                            │
  │                │               │←──alarm_type=2,level=3──│  │
  │                │               │─→ AlarmComponent          │
  │                │               │                            │─🆘 SOS全屏弹窗
  │                │               │                            │
  │─点"结束骑行"──────────────→ RideComponent                    │
  │                │               │                            │←─确认弹窗
  │─确认──────────────→            │                            │
  │                │               │← stopPoll()               │
  │                │               │─→ SummaryCalculator        │
  │                │               │                            │─总结弹窗
```

---

## 5. 原型 / UI 设计 ✅

### 5.1 页面结构

```
登录页              首页(空闲态)              首页(骑行中)
┌────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 智能骑行头盔│    │ ‹ 返回 智能骑行头盔│    │ ‹ 返回 智能骑行头盔│
│            │    │ ┌──────────────┐ │    │ ┌──────────────┐ │
│ 手机号     │    │ │  地图 360rpx │ │    │ │ 地图+轨迹线  │ │
│ [________] │    │ │  蓝色定位点  │ │    │ │  ▼ 展开  ⊙  │ │
│ 密码       │    │ │  ▼ 展开      │ │    │ └──────────────┘ │
│ [________] │    │ └──────────────┘ │    │ 📶 骑行中...     │
│ [登录]     │    │ 🌡 环境 --/--/--│    │ 🌡 30.4°C/50.5%  │
│            │    │ 📍 定位 --/--/--│    │ 📍 22.55/113.96  │
│            │    │ 📶 状态 --/正常 │    │ 📶 良好/正常      │
│            │    │ [开始骑行]      │    │ [结束骑行]        │
└────────────┘    └──────────────────┘    └──────────────────┘

报警弹窗 (全屏红色)        地图展开态 (半屏)
┌──────────────────┐    ┌──────────────────┐
│       💥/🆘      │    │ ‹ 返回            │
│   碰撞/SOS 报警   │    │ ┌──────────────┐ │
│      Lv2/3       │    │ │   地图 半屏   │ │
│  位置/时间       │    │ │   轨迹+⊙     │ │
│  设备已报警      │    │ │   ▲ 收起     │ │
│                  │    │ ├──────────────┤ │
└──────────────────┘    │ │ 卡片 scroll   │ │
SOS 有闪烁动画          │ │  独立滚动     │ │
                        │ └──────────────┘ │
                        └──────────────────┘
```

### 5.2 交互规则

| 交互 | 触发 | 行为 |
|:-----|:-----|:-----|
| 登录 | 点"登录" | 加密 → API → 跳转首页 |
| 开始骑行 | 点按钮 | 清空 → 启动轮询 → 强制跟随 |
| 结束骑行 | 点按钮 | 确认框 → 停止 → 总结弹窗 |
| 报警弹窗 | 碰撞Lv2+/SOS | 全屏红色覆盖 |
| 报警解除 | alarm_type=0 | 弹窗消失 |
| 地图展开 | 点"▼ 展开" | 半屏 + scale=16 |
| 取消跟随 | 拖拽地图 | ⊙ 出现 |
| 恢复跟随 | 点⊙ | 跳回 GPS |
| 返回(骑行中) | 点‹ | 确认 → 退出或继续 |

### 5.3 配色

| 用途 | 色值 |
|:-----|:-----|
| 页面 | #0f0f1a |
| 卡片 | #1a1a2e |
| 主按钮 | #1a6fff |
| 报警 | #ff4444 |
| 文字 | #e0e0e0 / #666 / #888 |
| 轨迹线 | #1a6fff |

---

## 6. 架构视图（多视角正交验证）

> 同一系统，不同视角独立审视，自洽且互洽。

### 6.1 逻辑视图 — 代码怎么组织

```
View 层   login.wxml    index.wxml
Logic 层  login.js      index.js (页面调度)
Service   data-service  alarm-service  ride-service  map-service
Utility   config.js  crypto.js  logger.js
Global    app.js (globalData)
```

| 层 | 职责 | 约束 |
|:---|:-----|:-----|
| View | 渲染 UI | 不含业务逻辑 |
| Logic | 页面调度 | 不调 `wx.request` |
| Service | 业务能力 | 不含 `setData` |
| Utility | 通用工具 | 无状态 |

### 6.2 流程视图 — 运行时怎么跑

JS 单线程事件循环：

```
事件循环队列
├── 定时器: setInterval(2s) → fetchDevice() → wx.request(异步)
├── 用户交互: tap/regionchange → 同步执行 ≤ 5ms
├── setData: 逻辑线程 → 渲染线程 (微信自动合并 16ms 内多次调用)
└── 日志: 同步写 console，异步写文件
```

| 并发风险 | 处理 |
|:---------|:-----|
| 轮询重叠 | `setInterval` 保证不重叠 |
| setData 合并 | 微信框架自动合并 |
| 结束时回调到达 | `isRiding=false` 置位后直接 return |

### 6.3 部署视图 — 代码跑在哪

(参见 §0.2 C2 容器图)

| 节点 | 负责方 | 本项目职责 |
|:-----|:-------|:----------|
| 微信客户端 | 用户手机 | 执行小程序 |
| 小程序包 | 腾讯云 CDN | 上传分发 |
| 移远云 API | 移远 | 调 REST |
| 腾讯地图 | 腾讯 | `<map>` 自动加载 |

### 6.4 数据视图 — 数据属于谁

| 数据 | Owner | Reader |
|:-----|:------|:------|
| token | AuthComponent | DataComponent |
| isRiding | RideComponent | DataComponent, MapComponent |
| rideCache[] | RideComponent | SummaryCalculator |
| trackPoints[] | MapComponent | View |
| showAlarmPopup | AlarmComponent | View |

| 规则 | 说明 |
|:-----|:-----|
| 单写多读 | 每份数据一个 owner |
| UI 不入全局 | `showAlarmPopup` 等仅存 `page.data` |

### 6.5 安全视图 — 信任边界

```
不信任区 → 加密/HTTPS → 信任区
用户输入   → AES      → 小程序逻辑
移远 API   → HTTPS    → wx.request
设备数据   → HTTPS    → 轮询回调
WXML 渲染  → 框架转义 → 无 XSS
```

| 边界 | 风险 | 措施 |
|:-----|:-----|:-----|
| 密码输入 | 明文在内存 | 加密后即丢弃 |
| 网络 | 中间人 | 全 HTTPS |
| Token | 反编译 | 内存不落盘 |
| 日志 | 敏感泄露 | 不记密码/Token |

### 6.6 架构决策记录 (ADR)

| ID | 决策 | 理由 | 后果 |
|:---|:-----|:-----|:-----|
| ADR-1 | 模块化单体 | 单用户、6 组件、同运行时 | 无 RPC/网关 |
| ADR-2 | HTTP 轮询 | WS 协议未文档化 | 2s 延迟可接受 |
| ADR-3 | 零 npm | 微信需构建步骤 | 加密自实现须验证 |
| ADR-4 | globalData | 5 个变量不需 Redux | 须明确 owner |

### 6.7 架构约束

| 约束 | 目标 | 当前 |
|:-----|:-----|:-----|
| 组件行数 | ≤ 200 行/文件 | ⚠️ index.js 400+ |
| setData 频率 | ≤ 5 次/秒 | ✅ ~2 次/秒 |
| 全局状态 | ≤ 8 个 | ✅ 5 个 |
| 轨迹点 | ≤ 500 | ✅ |
| 日志行数 | ≤ 1000 | ✅ |
| npm 依赖 | 0 | ✅ |
| 数据写权限 | 单 owner | ⚠️ rideCache 双写 |

---

## 7. 端到端场景 · 视图追溯

### 5.1 追溯矩阵

业务场景 (S1-S9) 和架构视图 (C1-C4 + 逻辑/流程/数据/安全) 的双向验证——每个场景必须被至少一个视图覆盖，每个视图必须支撑至少一个场景。

| 场景 | C1 上下文 | C2 容器 | C3 组件 | C4 接口 | 流程视图 | 数据视图 | 安全视图 |
|:-----|:---------|:--------|:--------|:--------|:--------|:--------|:--------|
| S1 登录 | ✅ 移远云 | ✅ 小程序容器 | ✅ Auth | ✅ login() | — | ✅ token owner | ✅ AES + HTTPS |
| S2 开始骑行 | — | — | ✅ Ride+Data | ✅ start() | ✅ 事件循环 | ✅ isRiding | — |
| S3 骑行监控 | ✅ 移远云 | ✅ 渲染线程 | ✅ Data+Alarm | ✅ analyze() | ✅ setInterval | ✅ rideCache | — |
| S4 报警触发 | ✅ 移远云 | ✅ 渲染线程 | ✅ Alarm | ✅ analyze() | ✅ setData | ✅ showAlarmPopup | — |
| S5 报警解除 | ✅ 移远云 | — | ✅ Alarm | ✅ analyze() | ✅ setData | ✅ showAlarmPopup | — |
| S6 结束骑行 | — | — | ✅ Ride | ✅ end() | ✅ 确认框 | ✅ rideCache | — |
| S7 中途退出 | — | — | ✅ Ride | ✅ isActive() | ✅ 确认框 | — | — |
| S8 设备离线 | — | ✅ 本地存储 | ✅ Data | — | ✅ 15s 阈值 | — | — |
| S9 地图交互 | ✅ 腾讯地图 | ✅ <map> | ✅ Map | ✅ pushPoint() | ✅ regionchange | ✅ trackPoints | — |

✅ = 该视图对该场景有显式支撑内容。

---

## 8. 开发 ✅

### 6.1 文件清单

```
WeChatMiniProgram/
├── app.js          globalData (token, isRiding, rideCache)
├── app.json        窗口 + 定位权限
├── services/
│   ├── data-service.js    HTTP 轮询 + TSL 解析
│   ├── alarm-service.js   报警检测 + 弹窗规则
│   ├── ride-service.js    骑行状态 + Haversine 总结
│   └── map-service.js     轨迹 polyline + marker
├── utils/
│   ├── config.js      凭据
│   ├── crypto.js      SHA256+MD5+AES
│   ├── logger.js      日志
│   └── ws-client.js   兼容层 (→ data-service)
├── pages/login/       登录页 (4 文件)
├── pages/index/       首页 (4 文件)
└── doc/               文档 4 篇
```

### 6.2 关键算法

**两遍扫描**: 第 1 遍判 isAlarm → 第 2 遍解析，报警态跳过 temp/humid/speed。

**Haversine 里程**: Σ Haversine(Pᵢ₋₁, Pᵢ)，过滤 NaN + d>1000m 异常。

**加密**: `md5(random) → aesKey[8:24], aesIv = aesKey后8 + 前8`。

---

## 9. 联调 ✅

三段验证: curl(设备→云) ✅ → curl(云→小程序 API 格式) ✅ → 小程序全链路 (test_miniprogram_e2e.py) ✅

---

## 10. 测试 ✅

### 8.1 test_miniprogram_e2e.py

| 阶段 | 时长 | 数据 | 验证 |
|:-----|:----:|:-----|:-----|
| ① 正常 | 60s | GPS 漂移 + 全字段 | 轨迹、alarm=正常 |
| ② 碰撞 | 10s | alarm_type=1 Lv2 | 红字、温湿度="--" |
| ③ 解除 | 10s | 全字段 | 恢复 |
| ④ SOS | 10s | alarm_type=2 Lv3 | 红字闪烁 |
| ⑤ 解除 | 10s | 全字段 | 恢复 |

### 8.2 验证清单

| # | 项目 | 状态 |
|:--|:-----|:----:|
| 1 | 登录→首页 | ✅ |
| 2 | 地图定位 | ✅ |
| 3 | 开始→数据刷新 | ✅ |
| 4 | 轨迹绘制 | ✅ |
| 5 | 报警态字段="--" | ✅ |
| 6 | 解除→恢复 | ✅ |
| 7 | 结束→总结 | ✅ |
| 8 | 退出保护 | ✅ |
| 9 | 地图展开/收起 | ✅ |
| 10 | 跟随/手动/回正 | ✅ |
| 11 | 新骑行清旧数据 | ✅ |
| 12 | 全屏报警弹窗 | ✅ |
| 13 | Token 刷新 | 📅 |

---

## 11-14. 预发布 → 运维 📅

| 阶段 | 事项 |
|:-----|:-----|
| 预发布 | 域名白名单、体验版 |
| 提审 | 类目选择、隐私协议 |
| 灰度 | 邀请用户扫码验证 |
| 全量 | 审核通过发布 |
| 运维 | Token 刷新、异常监控、R8-R13 迭代 |

---

## 开发日志

| 日期 | 阶段 | 主要工作 |
|:-----|:-----|:---------|
| 2026-05-22 | 设备端 | STM32 → 移远云 TSL 通信调通，test_lark_cloud_e2e.py 5 阶段集成测试 |
| 2026-05-22 | 小程序 — 需求 | 需求梳理 R1~R6：登录、实时数据、骑行控制、地图、总结、日志 |
| 2026-05-23 | 小程序 — 开发 | login 页加密登录完成；index 页地图+数据卡片+骑行状态机 |
| 2026-05-23 | 小程序 — 联调+测试 | test_miniprogram_e2e.py 跑通；报警态两遍扫描修复、Haversine 异常保护 |
| 2026-05-23 | 小程序 — 打磨 | 报警全屏弹窗；离线检测；地图自动跟随修正；骑行清空旧数据 |
| 2026-05-24 AM | 框架设计 | 业务架构 3 层设计：C4 模型映射、DDD 领域建模、ADR 决策记录、多视角正交验证 |
| 2026-05-24 PM | 架构重构 | development.md 全生命周期文档、architecture.md C4 化、services/ 组件拆分 |
| 2026-05-24 | 主题换色 + 离线清除 | 全页面 #66ccff 浅蓝主题、登录页适配、导航栏颜色、结束骑行清空所有字段 |
| 2026-05-24 | 总结弹窗内嵌地图 + 过滤缓存 | 总结弹窗显示轨迹地图（include-points 全轨迹）、开始骑行只接受 rideStartTime 之后的数据 |
| 2026-05-24 | ES5 兼容 | index.js 全部函数写法改为 ES5（解决微信 enhance 插件解析报错） |
| 📅 Step B | 导航+心率+头灯+电量 | 云端导航 R7~R9、心率 R10、头灯 R11、电量 R12 |
| 📅 Step C | 语音交互 | 语音指令 R13 |

---

## 附 A: 踩坑记录

| # | 问题 | 根因 | 修复 |
|:--|:-----|:-----|:-----|
| 1 | `%-20s` 打印 | JS 无 printf | `.padEnd(18)` |
| 2 | 地图不追踪 | regionchange 误判 | `causedBy='drag'/'scale'` |
| 3 | 里程 1690km | Haversine 无保护 | +NaN+d<1000 |
| 4 | 报警不恢复 | API 缓存 ID6 | 发 `tsl[6]=0` |
| 5 | 报警态残留 | 旧缓存返回 | 两遍扫描 |
| 6 | 日志失败 | USER_DATA_PATH | 改 `'app.log'` |
| 7 | 登录卡死 | requiredPrivateInfos | 去掉 |
| 8 | 返回无效 | reLaunch 清栈 | reLaunch 跳回 |
| 9 | flatMap 不兼容 | 微信引擎 | `[].concat()` |
| 10 | 骑行不清数据 | 未复位字段 | 全字段 `"--"` |

---

## 附 B: 文件索引

| 文件 | 层 |
|:-----|:---|
| `utils/config.js` | Config |
| `utils/crypto.js` | Crypto |
| `utils/logger.js` | Log |
| `utils/ws-client.js` | Network |
| `pages/login/login.*` | View+Logic |
| `pages/index/index.*` | View+Logic |
| `app.js` | Global |
| `app.json` | Config |
| `doc/development.md` | 本文档 |
| `doc/architecture.md` | 架构细节 |
| `doc/requirements.md` | 需求细节 |
| `Tests/test_miniprogram_e2e.py` | 集成测试 |
