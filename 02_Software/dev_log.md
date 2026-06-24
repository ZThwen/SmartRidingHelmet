# SmartRidingHelmet 开发日志

> MicroPython 固件（STM32F413ZH + Quectel EC200U）里程碑记录
> 从早到晚，旧→新

---

## 时间轴

```
2026-05-05  ████████░░░░░░░░░░░░░░░░░░░░  项目初始化，Core 框架
2026-05-13  ██████████████░░░░░░░░░░░░░░  v1 第一阶段验收（Core + 传感器驱动）
2026-05-20  ████████████████░░░░░░░░░░░░  v1 集成完成（碰撞/报警/云端/显示全链路）
2026-05-28  ██████████████████░░░░░░░░░░  BLE 驱动 + 小程序初步设计
2026-06-02  ████████████████████░░░░░░░░  小程序 Step A 完成（BLE 直连 + 实时数据）
2026-06-09  ██████████████████████░░░░░░  导航功能完成（NavigationService + LBS）
2026-06-11  ████████████████████████░░░░  PWM_LED + LightService + ControlService
2026-06-12  ██████████████████████████░░  main.py 18 模块集成 + BLEService v3
2026-06-18  ████████████████████████████  远端控制全链路 + ControlService v3
2026-06-20  ████████████████████████████  Phase 3 交付 + Phase 4 VoiceDriver
2026-06-21  ████████████████████████████  main.py 21 模块全集成
2026-06-22  ████████████████████████████  Phase 5 AudioService + LCD 导航恢复
2026-06-23  ████████████████████████████  Phase 4 PowerService + BatteryDriver
2026-06-24  ████████████████████████████  HeartRate + Phase 4 增强 + 文档同步
```

---

## 2026-05-05

- 🏗️ **项目初始化** — 项目仓库创建，搭建四层架构骨架（App → Service → Device → Vendor）
- 🏗️ **Core 框架** — EventBus 发布/订阅机制、BaseModule 四元组基类（cfg/ctx/data/ops）、config.py 全局常量、main.py 系统入口 + 主循环

## 2026-05-13

- 🏗️ **v1 第一阶段验收完成** — 基础框架 Core 通过验收
- ✨ **传感器驱动** — TempHumidDriver（AHT20 I2C1）、IMUDriver（LIS2DH12TR I2C1）、GNSSDriver（EC200U 内置）、LightSensorDriver（GL5528 ADC PC5）
- ✨ **执行器驱动** — Button（GPIO SOS 按键）、LEDDriver（Timer1 闪烁）、AudioDriver（EC200U 音频）、LCDDriver（ST7735 SPI1）

## 2026-05-20

- 🏗️ **v1 版集成完成** — 碰撞检测、报警联动、云端通信、显示管理全链路测试通过
- ✨ **CollisionService** — 三级判决碰撞检测算法（多级阈值 + 防误报鉴别器）
- ✨ **AlarmService** — 报警联动逻辑（声光 + BLE + 云端，30s 超时，SOS 升级）
- ✨ **CloudService** — MQTT 云端通信与数据上报（ConnectLab 平台）
- ✨ **DisplayService** — LCD 显示管理 + 光照自适应背光

## 2026-05-28

- ✨ **新增模块** — BLEDriver（EC200U BLE 4.2 GATT Server）
- ✨ **新增模块** — NetworkDriver（4G 网络模组）、MQTTDriver（MQTT 协议封装）、ThreadSafeQueue（线程安全队列）
- 📱 **小程序** — 微信小程序初步设计完成，确定 BLE GATT 直连方案

## 2026-06-02

- 📱 **小程序 Step A 完成** — BLE GATT 直连 + 实时数据显示（温度/湿度/速度/位置）+ 报警弹窗（碰撞 Lv2+ / SOS 全屏红色）+ 骑行控制（开始/结束/总结）+ 地图轨迹（polyline 实时绘制）
- 📱 **小程序登录** — 手机号 + 密码 → crypto.js 纯 JS 加密（SHA256 + MD5 + AES-128-CBC）→ QuecCloud API

## 2026-06-09

- ✨ **新增模块** — NavigationService（导航指令处理，腾讯地图 bicycling API 算路）
- ✨ **新增模块** — LBS 基站定位驱动（EC200U 内置，与 GNSS 互斥）
- 🔧 **GNSS 优化** — 新增 `cog` 字段（对地航向 0-360°）+ BLE hex 解码导航指令

## 2026-06-11

- ✨ **新增模块** — PWM_LED 大功率灯光驱动（PE11/TIM1_CH2，18W，gamma 非线性映射，亮度上限 50% 散热保护）
- ✨ **新增模块** — LightService 自适应灯光（光照 ADC → gamma 映射 → PWM 亮度，自动/手动模式切换，防抖 3%/50ms）
- ✨ **新增模块** — ControlService 统一控制（BLE 远端 + 语音指令，纯事件驱动路由器）
- ✨ **新增模块** — BLEService（BLE 数据入口/出口，环形缓冲区 + 快照合并推送）

## 2026-06-12

- 🏗️ **main.py 18 模块集成** — PWM_LED、LightService、BLE、BLEService、ControlService、NavigationService 全部接入 main.py
- 🏗️ **ControlService 重构** — 改为纯事件发布模式，新增 alarm_sos / trigger_stealth / power_emergency 指令
- 🏗️ **BLEService v3** — 环形缓冲区（ThreadSafeQueue max_size=16）+ 快照合并推送（控制状态合并为 1 条 notify `{"t":7,"m":0,"b":50,"v":5,"p":0}`）
- 🔧 **重大修复** — AudioDriver 添加 EVENT_TTS_REQUEST 订阅 + stop-before-play 支持
- 🔧 **BLE 协议修复** — 剥离 EventBus 自动注入的 source/timestamp 字段；payload 大小检查 MAX_BLE_PAYLOAD=244
- 📱 **小程序** — 远端控制面板（TabBar + control page + BLE FFF3 sendCtrl）

## 2026-06-18

- 🏗️ **远端控制全链路实现** — ControlService v3（19 指令 + TTS 反馈 + 报警快照恢复：`_pre_alarm_state` 保存/恢复 + BLE 回推）
- 🏗️ **ControlService v3 增强** — 语音订阅 + 传感器缓存查询 + CUSTOM 电源状态 + CMD_TTS_MAP（1 秒防抖）
- 📱 **小程序 Step B 远端控制** — 控制页面 + BLE FFF3 sendCtrl + TabBar + 灯光/音量/报警/电源控制 UI
- 🔧 **MicroPython 兼容修复** — `__doc__` 属性不存在，改用 `getattr(t, '__doc__', '')`

## 2026-06-20

- 🏗️ **远端控制全链路合并到 main** — Phase 3 全部功能交付合并
- 🔵 **Phase 4** — 语音模块开发完成：VoiceDriver 集成验证 + ASRPRO UART 通信调试（UART2 9600bps，单字节 hex 0x00-0x13 映射 19 条指令 + 6 条查询）

## 2026-06-21

- 🏗️ **main.py 21 模块全集成** — 集成前防御性加固：LBS 子线程保护、LCD 超时锁（`display_mode` 防死锁）、线程栈保护
- 🔧 **重大修复** — TTS 线程互斥锁 + 硬编码事件字符串修复（全部改为 config 常量）
- 🔧 **重大修复** — 电源事件订阅链路断裂修复 + 传感器 EMERGENCY 分支 + 报警超时修复

## 2026-06-22

- 🟢 **Phase 5** — **AudioService 统一音频调度 + LCD 导航恢复**
  - 新建 AudioService：优先级队列（ALARM > NAV > CTRL）+ 超时 5s 丢弃 + 队列上限 3
  - NavigationService：TTS 改用 EventBus 发布 EVENT_TTS_REQUEST，不再直接调用 AudioDriver
  - DisplayService：订阅 EVENT_NAV_DISPLAY 渲染恢复导航文字（报警取消后自动恢复底部导航行）
  - AudioDriver：移除 TTS 订阅，改为纯硬件层（只接受 play_tts / stop 调用）
- 📱 **小程序** — 报警双端同步（globalData + EventBus 跨页面事件传递）
- 🔧 **重大修复** — 省电模式灯光控制修复（PWM_LED CUSTOM 模式 + ControlService 时序问题）

## 2026-06-23

- 🔵 **Phase 4** — **电源检测模块完成**
  - BatteryDriver：ADC PC4（ADC1_IN14），10s 采样间隔，电压换算 `adc_mv * 3300 // 65535 * 1.45`，6 档电量映射
  - PowerService：六档电量映射 + 自动省电切换（level ≤ 2 时发布 SUSPENDED）+ TTS 低电量播报 + BLE 推送电量 + 语音查询支持
- 📱 **小程序 Step A + Step B 全部完成** — 导航推送 + 远端控制 + 报警状态同步 + 电量显示

## 2026-06-24

- ✨ **新增模块** — HeartRate 心率血氧传感器驱动（MKS SPO2-ZS-BLE，UART9 TX=PG14 RX=PG9，代码完成，未集成 main.py，等硬件）
- 🔵 **Phase 4 增强**
  - AudioDriver：tick 中添加环形缓冲区处理
  - BatteryDriver：新增 sample_count 字段用于启动宽限期判断
  - PowerService：启动宽限期（sample_count < 3 跳过省电触发）+ 未接电池保护（battery_mv < 1000 不触发）
- 🔧 **重大修复** — 电源管理 TTS 死锁修复（移除 AudioDriver tick 中 power_state 守卫，防止 TTS 回调处理被阻塞）
- 🔧 **重大修复** — ControlService 订阅 EVENT_POWER_STATE_CHANGE 实现电源状态回推到小程序
- 📝 **文档同步** — 架构文档、设计文档、模块文档、测试指南全量对齐（15 个文件）
