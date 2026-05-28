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
- 信号质量（良好/一般/差/无）
- 报警状态（正常 / 碰撞 LvX / SOS LvX）

**R2.2 刷新频率**
- 每 2 秒 HTTP 轮询一次

**R2.2.1 方案选型**

| 维度 | HTTP 轮询 ✅ | WebSocket |
|:-----|:-------------|:----------|
| 延迟 | ≤2s | <100ms |
| 温湿度 | 秒级变化，2s 够用 | 过度设计 |
| GPS 轨迹 | 2s/点，地图线已够密 | 1s 无区别 |
| 报警通知 | 碰撞后 ≤2s 弹红字 | 快 1.9s 意义不大 |
| 协议 | REST API **已文档化** | QuecCloud WS **未公开** |
| 断线 | `wx.request` 自带超时 | 需手写心跳+重连 |
| 开发成本 | ✅ 已跑通 | 需逆向 Android SDK |

> writeData 实现后，导航指令已走 REST 下发（1-3s 延迟，可接受）。
> 如需更低延迟（秒级），后续可引入 WebSocket Relay 替换 writeData，业务层不用改。

**R2.3 缺数据占位**
- 未开始骑行：全部字段显示 `"--"`
- 报警态下：温湿度/速度显示 `"--"`（即使云端返回旧缓存也不显示）
- 常态下未获取到数据时（设备离线等）：对应字段 `"--"`

**R2.4 报警显示**
- 碰撞（alarm_type=1）：红色大字"碰撞 LvX"
- SOS（alarm_type=2）：红色大字"SOS LvX"
- 正常态：显示"正常"（默认色）

**R2.5 离线检测**
- 最近一次设备上报距今超过 15 秒 → 状态栏提示"设备离线 (Xs)"

---

## R3 骑行控制

**R3.1 开始骑行**
- 用户点击"开始骑行"按钮 → 清空旧数据 → 启动数据轮询 + 缓存
- 开始前不轮询设备数据

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

## R8 导航 *(开发中)*

**R8.1 导航数据模型（TSL 属性）**

小程序通过移远云 `writeData` API 写入以下 TSL 属性，STM32 通过 MQTT 接收：

| abId | 字段名 | 类型 | 说明 | 写入方 |
|:----:|:-------|:----:|:-----|:------|
| 10 | `nav_status` | int | 0=空闲 1=导航中 2=已到达 3=已取消 | 小程序→云 |
| 11 | `nav_dest_lat` | float | 目的地纬度 | 小程序→云 |
| 12 | `nav_dest_lon` | float | 目的地经度 | 小程序→云 |
| 13 | `nav_cur_instruction` | string | 当前转弯指令文本（如"前方200米右转"）| 小程序→云 |
| 14 | `nav_cur_distance` | int | 距下一拐弯距离（米）| 小程序→云 |
| 15 | `nav_remain_distance` | int | 距目的地剩余距离（米）| 小程序→云 |

> 这些属性需先在移远云 DMP 平台 → 产品 → 物模型中添加。

**R8.2 writeData 接口**

```
POST /v2/deviceshadow/r3/openapi/dm/writeData
Content-Type: application/json
Authorization: Bearer {accessToken}

{
  "pk": "p11yMv",
  "dk": "66ccff",
  "items": [
    {"abId": 10, "value": 1},
    {"abId": 11, "value": 22.5431}
  ]
}
```

- 接口 QPS 限制：30/秒，导航 5 秒一次完全足够
- 需要终端用户 token（与轮询 `getDeviceBusinessAttributes` 同源）
- 响应 `code=200` 表示写入成功，设备离线时可能延迟到达

**R8.3 导航流程**

```
1. 骑行者点击"导航" → wx.chooseLocation() 选目的地
2. 调用腾讯地图 WebService API 算路
3. navigation-service.js 解析路线为逐条拐弯指令队列
4. 每 5 秒推送当前指令到云（writeData: nav_cur_instruction + nav_cur_distance）
5. 每次推送同时更新 nav_remain_distance + nav_status（保持导航中）
6. 到达目的地 → writeData nav_status=2
7. 用户取消导航 → writeData nav_status=3
```

**R8.4 5 秒推流策略**

- 路线拐弯步数：通常 5-20 步
- 每步推送时机：上一条指令写入后 5 秒，或到达前一步的拐弯点
- 简化实现：直接按时间间隔推送（每 5 秒推队列中的下一步），不考虑实际 GNSS 比对
- 头盔端（后续开发）由 STM32 自行比对 GNSS 位置判断是否到达拐弯点

**R8.5 状态机**

```
idle ──用户选目的地──→ planning ──算路完成──→ navigating ──到达──→ arrived
                                                        │
                                                        └──用户取消──→ cancelled

navigating 期间每 5 秒: updateStep() → writeData(instruction, distance, remain)
arrived: writeData(status=2) → 骑行正常结束
cancelled: writeData(status=3) → 终止推流
```

**R8.6 延迟与可靠性**

| 阶段 | 延迟 | 可接受 |
|:-----|:----:|:------:|
| 小程序→写入云 | 200-500ms | ✅ |
| 云→MQTT→STM32 | 500-2000ms | ✅ |
| 总计 | 1-3s | ✅ 导航非安全关键 |
| 头盔落后步数 | ≤1 步（5秒/步）| ✅ |

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
│                  DataModule                     │
│  职责: 设备数据获取、解析、缓存                   │
│  输入: 无（轮询自动触发）                          │
│  输出: parsedData {temp,humid,speed,...}        │
│  依赖: ws-client.js                             │
│  接口: startPolling(), stopPolling(),           │
│        onData(callback), getCache()              │
├────────────────────────────────────────────────┤
│                  RideModule                     │
│  职责: 骑行状态机 + 总结计算                      │
│  状态: idle → riding → ended                    │
│  输入: 用户操作(开始/结束)                        │
│  输出: ridingState, rideSummary                 │
│  依赖: DataModule                               │
│  接口: startRide(), endRide(), getSummary()      │
├────────────────────────────────────────────────┤
│                  MapModule                      │
│  职责: 地图定位、轨迹、跟随/手动                   │
│  状态: 手机定位 / 设备定位                        │
│  输入: phoneGps | deviceGps                     │
│  输出: trackPoints[], mapCenter                 │
│  依赖: wx.getLocation                           │
│  接口: trackPoint(lat,lon), toggleFollow(),     │
│        expand(), collapse()                     │
├────────────────────────────────────────────────┤
│                  AlarmModule                    │
│  职责: 报警状态解析与显示规则                     │
│  输入: rawItems[] (abId=6,7)                    │
│  输出: alarmText, isAlarm, blockedFields        │
│  依赖: 无                                       │
│  接口: parse(items) → {text, isAlarm}           │
├────────────────────────────────────────────────┤
│                  LogModule                      │
│  职责: 运行日志记录                              │
│  输入: tag, message                             │
│  输出: console + app.log                        │
│  依赖: wx.getFileSystemManager                  │
│  接口: init(), log(tag,msg), flush()            │
└────────────────────────────────────────────────┘
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
DataModule  →  index.DataCard + ws-client
RideModule  →  index.RideButton + SummaryModal
MapModule   →  index.MapView
AlarmModule →  index.AlarmBadge + DataCard 条件显示
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
| 主题 | 浅蓝 #66ccff 背景 + 白色卡片，适合户外使用 |
| 简单优先 | 不做过度架构，模块数 = 实际需要数 |
