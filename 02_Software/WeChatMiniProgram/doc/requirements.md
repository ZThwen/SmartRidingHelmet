# 微信小程序 — 需求定义

> 所属项目: 智能骑行头盔  
> 版本: Step A v1.0  
> 日期: 2026-05-23

---

## 核心目标

骑行过程中实时查看头盔数据（温湿度/速度/位置/报警），结束后回看骑行总结和轨迹。

---

## R1 用户认证

**R1.1 登录**
- 手机号 + 密码登录
- 密码 AES 加密后调用 QuecCloud `phonePwdLogin` API
- 成功后 token 存入全局，后续所有 API 请求携带
- 登录失败提示具体原因（密码错误/网络异常）

**R1.2 自动登出** *(📅 后续)*
- Token 过期自动用 refreshToken 续期

---

## R2 实时数据

**R2.1 数据显示**
- 温度（°C）、湿度（%）、速度（km/h）
- 纬度、经度、海拔（m）
- 光照（lux）— BLE t=0 数据含 lux 字段
- 报警状态（正常 / 碰撞 LvX / SOS LvX）

> **注**：信号质量字段仅在历史 HTTP 轮询方案中可用（TSL abId=5），当前 BLE 直连数据不含此字段。

**R2.2 刷新频率**
- 每 2 秒 BLE Notify 推送一次合并传感器 JSON

**R2.2.1 方案选型**

| 维度 | BLE GATT Notify ✅ | HTTP 轮询（历史方案） |
|:-----|:-------------------|:---------------------|
| 延迟 | <100ms | ≤2s |
| 依赖 | 头盔 BLE 直连，无云端 | 需移远云在线 |
| 协议 | BLE GATT (FFF1 Notify) | REST API |
| 断线 | BLE 连接状态实时感知 | 需轮询超时检测 |
| 开发成本 | ✅ 已实现 | 已弃用 |

> 导航指令通过 BLE FFF2 写入特征值下发（本地直连，无云端延迟）。
>
> **历史方案备注**：v1 初期（5/17-5/24）曾采用 HTTP 轮询方案（小程序 → 移远云 OpenAPI → 查询 TSL 数据），后于 5/28 改为 BLE 直连以降低延迟、减少云端依赖。

**R2.3 缺数据占位**
- 未开始骑行：全部字段显示 `"--"`
- 报警态下：温湿度/速度显示 `"--"`（即使云端返回旧缓存也不显示）
- 常态下未获取到数据时（设备离线等）：对应字段 `"--"`

**R2.4 报警显示**
- 碰撞（alarm_type=1）：红色大字"碰撞 LvX"
- SOS（alarm_type=2）：红色大字"SOS LvX"
- 正常态：显示"正常"（默认色）

**R2.5 离线检测**
- BLE 连接断开时 → `onDisconnected` 回调触发，状态栏显示"已断开"
- BLE 连接中但超过 5 秒无数据 → 心跳包 (t=99) 超时检测

---

## R3 骑行控制

**R3.1 开始骑行**
- 用户点击"开始骑行"按钮 → 清空旧数据 → 开始记录 BLE 数据到骑行缓存
- 开始骑行前 BLE 数据仅显示不记录

**R3.2 结束骑行**
- 点击"结束骑行" → 弹出确认框"确定要结束本次骑行吗？"
- 取消 → 继续骑行，数据继续累加
- 确认 → 停止轮询 → 计算总结 → 弹出总结弹窗
- 退出页面（返回/关闭）时若骑行中 → 同样弹出确认框
- 每次开始新骑行清空上次的缓存数据和界面数据

**R3.3 退出保护**
- 骑行中按返回 → 弹窗"确定要退出骑行吗？"
- 确认 → 停止骑行 → 返回登录页
- 取消 → 留在当前页继续骑行

---

## R4 地图

**R4.1 位置追踪**
- 未开始骑行：使用手机 GPS 定位，蓝色圆点显示，实时跟随
- 开始骑行：切换到头盔 GPS，自动跟随设备当前位置

**R4.2 轨迹绘制**
- 骑行中每收到一次设备 GPS 数据，追加到轨迹线（蓝色 polyline）
- 地图中心自动跟随当前位置（跟随模式）
- 用户手动拖拽/缩放地图 → 取消跟随，右下角出现 ⊙ 回正按钮
- 点 ⊙ → 跳回当前位置，恢复跟随

**R4.3 地图展开/收起**
- 点击地图下方"▼ 展开" → 地图扩至半屏，scale 放大
- 点击"▲ 收起" → 地图缩回紧凑高度
- 骑行中展开/收起按钮始终可用

**R4.4 地图不可拖动时**
- 展开状态下地图高度固定，不随页面滚动
- 下方数据卡片区独立 scroll-view 滚动

---

## R5 骑行总结

**R5.1 计算指标**
- 总时长（分:秒）
- 平均速度、最高速度（km/h）
- 平均温度、最高温度（°C）
- 总里程（基于 GPS 坐标 Haversine 球面距离累加，单步异常自动过滤）
- 报警次数（采集点中 alarm≠0 的数量）

**R5.2 弹窗展示**
- 结束骑行后自动弹出模态框
- 点击关闭按钮或遮罩层 → 关闭弹窗

---

## R6 日志

**R6.1 记录内容**
- 每次 API 请求的返回字段清单（abId + resourceCode + resourceValce）
- 连接状态变化（在线/离线/Token过期/网络错误）
- 页面 setData 内容（温湿度/速度/位置/信号/报警）
- 骑行状态切换（开始/结束）
- 错误信息（加密失败/网络异常）

**R6.2 输出方式**
- Console 输出（DevTools 右键导出）
- 本地文件 `app.log`（小程序沙箱内，上限 1000 条，超限删旧）

---

---

## R8 导航 *(部分已实现 🔜)*

> ⚠️ **数据通道已变更**：原设计通过移远云 `writeData` REST API 下行（R8.1-R8.2），已于 2026-05-28 决策改为 **BLE FFF2 直连 sendNav**（低延迟、无云端依赖）。旧方案保留为历史参考。

### 当前方案：BLE FFF2 直连

**R8.1 导航数据模型（BLE FFF2）**

小程序通过 `BleService.sendNav()` 写入 JSON 到 FFF2 特征值，STM32 通过 BLE GATT Write 接收：

```json
// 导航指令
{"a":"nav","d":{"dir":"right","dist":200,"road":"中山路"}}

// 到达目的地
{"a":"nav","d":{"dir":"arrive","dist":0,"road":""}}

// 取消导航
{"a":"nav","d":{"dir":"cancel","dist":0,"road":""}}
```

| 字段 | 类型 | 说明 |
|:-----|:----:|:-----|
| `a` | string | 固定 "nav" |
| `d.dir` | string | 方向指令（right/left/straight/arrive/cancel） |
| `d.dist` | int | 距下一拐弯距离（米） |
| `d.road` | string | 路名 |

**R8.2 导航流程**

```
1. 骑行者点击"导航" → wx.chooseLocation() 选目的地
2. 调用腾讯地图 WebService API 算路
3. navigation-service.js 解析路线为逐条拐弯指令队列
4. 每 5 秒推送当前指令到头盔（BLE FFF2 sendNav）
5. 到达目的地 → sendNav(arrive, 0, "")
6. 用户取消导航 → sendNav(cancel, 0, "")
```

**R8.3 5 秒推流策略（当前方案）**

- 路线拐弯步数：通常 5-20 步
- 每步推送时机：每 5 秒推队列中的下一步
- 报警时暂停推送，解除后恢复

**R8.3.1 位置播报升级方案（📅 规划中）**

- 小程序一次性推送完整路线（所有 steps + waypoints）到头盔
- 头盔 NavigationService 比对自身 GNSS 位置，在接近拐弯点时自主 TTS 播报
- 优势：断网/弱 BLE 信号时仍可播报；播报时机更精准
- 依赖：GNSS cog 字段（已实现）、路线数据 BLE 传输协议（待设计）

**R8.4 状态机**

```
idle ──用户选目的地──→ planning ──算路完成──→ navigating ──到达──→ arrived
                                                        │
                                          ┌──用户取消──→ cancelled
                                          └──报警──→ paused ──报警解除──→ navigating
```

**R8.5 延迟与可靠性**

| 阶段 | 延迟 | 可接受 |
|:-----|:----:|:------:|
| 小程序→BLE FFF2→STM32 | <100ms | ✅ |
| 总计 | <100ms | ✅ 远优于云端方案 |
| 头盔落后步数 | ≤1 步（5秒/步）| ✅ |

### 历史方案：云端 writeData（已弃用）

> 以下为 2026-05-22 至 2026-05-28 期间的设计方案，已切换为 BLE FFF2 直连。

**旧 R8.1 TSL 数据模型** — 通过移远云 writeData API 写入 TSL 属性（abId 10-15），STM32 通过 MQTT 接收。延迟 1-3s，需云端 token。

**旧 R8.2 writeData 接口** — `POST /v2/deviceshadow/r3/openapi/dm/writeData`，QPS 30/秒。

**切换原因**：BLE 直连延迟 <100ms（vs 云端 1-3s），无云端依赖，无需 DMP TSL 配置。

---

## R11 远端控制 *(✅ 已实现)*

**R11.1 控制页面**
- 独立控制页面（pages/control/control）
- 自定义底部 TabBar 切换骑行/控制页
- 灯光控制：自动/手动模式、开/关灯、亮度 0-100%（100%=PWM50%）
- 音量控制：0-7 级
- 电源模式：正常/省电
- BLE 未连接时所有控制禁用

**R11.2 指令下发**
- 通过 BLE FFF3 `sendCtrl(cmd)` 下发控制指令
- 指令格式：`{"a":"ctrl","d":{"cmd":"<command>"}}`
- 固件执行后通过 t=7 回推状态

**R11.3 状态同步**
- App.js globalData 持有 ctrlState
- EventBus 跨页面事件通知
- 页面 onShow 时从 globalData 同步

**R11.4 依赖**
- 小程序端：`sendCtrl()` 已实现（ble-service.js）
- 小程序端：`ctrl-service.js` 指令封装
- 头盔端：ControlService（✅ 已实现）
- 头盔端：LightService + PWM_LED（✅ 已实现）

---

## R9 语音交互 *(📅 远期)*

**R9.1 目标**
- 骑行中语音指令控制（如"开始导航""结束骑行"）
- 解放双手，提升安全

**R9.2 制约**
- EC200U 当前语音接口仅支持电话呼叫（voicecall）
- 无原生语音识别/唤醒词支持
- 实现需外挂语音模块或云端 ASR，难度较大

---

---

## 业务模块与组件

### 一、业务模块（逻辑层）

每个模块封装一类业务逻辑，通过明确接口通信。

```
┌────────────────────────────────────────────────┐
│                  AuthModule                     │
│  职责: 身份认证                                  │
│  输入: phone, pwd                               │
│  输出: token → globalData                       │
│  依赖: crypto.js, config.js                     │
│  接口: login(phone, pwd) → success/fail         │
├────────────────────────────────────────────────┤
│                  BleModule (主数据通道)           │
│  职责: BLE 扫描/连接/收发数据/自动重连            │
│  输入: BLE GATT Notify (FFF1)                   │
│  输出: parsedData {t, tmp, hum, spd, lat,...}   │
│  依赖: ble-protocol.js, logger.js               │
│  接口: init(cb), scan(), connectById(),         │
│        sendNav(), sendCtrl(), disconnect()       │
├────────────────────────────────────────────────┤
│                  RideModule                     │
│  职责: 骑行状态机 + 总结计算                      │
│  状态: idle → riding → ended                    │
│  输入: 用户操作(开始/结束) + BLE onData 回调      │
│  输出: ridingState, rideSummary                 │
│  依赖: BleModule (onData 回调写入 rideCache)     │
│  接口: start(), end(), addRecord(), isActive()  │
├────────────────────────────────────────────────┤
│                  MapModule                      │
│  职责: 地图定位、轨迹 polyline、marker            │
│  输入: phoneGps (wx.onLocationChange)           │
│  输出: trackPoints[], polylines, markers        │
│  依赖: wx.getLocation                           │
│  接口: pushPoint(lat,lon), buildPolyline(),     │
│        buildMarker(), buildRoutePolyline()       │
├────────────────────────────────────────────────┤
│                  AlarmModule                    │
│  职责: 报警状态解析与弹窗规则（纯函数）            │
│  输入: alarmType(1=碰撞,2=SOS), alarmLevel      │
│  输出: displayText, shouldPopup, icon           │
│  依赖: 无                                       │
│  接口: analyze(alarmType, level) → result       │
├────────────────────────────────────────────────┤
│                  NavModule                      │
│  职责: 导航路线规划 + BLE FFF2 指令推送           │
│  输入: 目的地坐标                                │
│  输出: 导航指令队列 → BLE FFF2 sendNav           │
│  依赖: config.js(TENCENT_MAP_KEY), ble-service  │
│  接口: selectDestination(), startNavigation(),  │
│        stopNavigation(), pause(), resume()       │
├────────────────────────────────────────────────┤
│                  LogModule                      │
│  职责: 运行日志记录                              │
│  输入: tag, message                             │
│  输出: console + app.log                        │
│  依赖: wx.getFileSystemManager                  │
│  接口: init(), log(tag,msg), flush()            │
└────────────────────────────────────────────────┘

> **历史备注**：`DataModule`（HTTP 轮询）已被 `BleModule`（BLE 直连）替代，`services/data-service.js` 保留作为历史参考。
```

### 二、业务组件（UI 层）

可复用的界面单元，每个组件绑定自己的数据和事件。

| 组件 | 对应 WXML | 数据输入 | 事件输出 |
|:-----|:----------|:---------|:---------|
| **NavBar** | `nav-bar` | title, showBack | `onBackPress` |
| **MapView** | `map-section` | trackPolylines, mapLat, mapLon, expanded | `onRegionChange`, `onMapReset` |
| **DataCard** | `.card` | title, rows[{label,value}] | 无 |
| **RideButton** | `bottom-bar` | riding, btnText, btnClass | `onToggleRide` |
| **SummaryModal** | `.modal` | summary{}, visible | `onClose` |
| **AlarmBadge** | `alarm-on` class | alarm | 无（样式绑定） |

### 三、模块-组件对应

```
AuthModule  →  login 页
BleModule   →  index.DataCard + ble-service.js
RideModule  →  index.RideButton + SummaryModal
MapModule   →  index.MapView
AlarmModule →  index.AlarmBadge + DataCard 条件显示
NavModule   →  index.NavCard + navigation-service.js
LogModule   →  全局 logger.js
```

---

## R7 非功能需求

| 类型 | 约束 |
|:-----|:-----|
| 性能 | 轮询间隔 2s，数据解析 < 5ms |
| 兼容 | 微信基础库 ≥ 2.20（实际 3.16.1） |
| 依赖 | 无 npm 包，纯微信原生 API + CommonJS |
| 安全 | Token 存储在 globalData，不硬编码 |
| 主题 | Tactical Cyan 暗色主题：深色基底 #080d17 + 天依蓝强调 #66ccff，适合户外使用 |
| 简单优先 | 不做过度架构，模块数 = 实际需要数 |
