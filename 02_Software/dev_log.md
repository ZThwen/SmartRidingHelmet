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
2026-06-26  ████████████████████████████  系统级架构修复（P0 OOM + 碰撞判定 + 线程安全 + 模块隔离）
2026-06-27  ████████████████████████████  30 分钟全场景压力测试通过 + 8 缺陷修复
2026-06-28  ████████████████████████████  边界测试 + v3 压力测试 + _manual_locked + 开机动画 + heartbeat
2026-06-29  █████████████████████████████  8 文档全量同步 + 37 文件 6 批次提交
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

## 2026-06-25

- 🟢 **性能优化 + UART9 冲突修复**
  - HeartRate UART9 → UART5 切换，解决 HeartRate 初始化破坏 EC200U AT 通道问题
  - GNSS 线程延迟 5 秒启动，避免初始化期间 AT 通道抢占
  - Temp_Humid 超时跳过保护 + DisplayService 脏标志模式（消除回调中 LCD 渲染）
  - GC 阈值优化（15000→8000，检查间隔 100→500）
  - 创建主循环 CPU 占用监测系统

- 🔧 **BLE 重连与 GATT 修复**
  - `init()` 去掉 `advertise()`，开机只初始化不广播
  - `restart()` 重命名为 `connect()`，完整重写为 `stop → init → advertise` 流程
  - `connect()` 确保 GATT 特征值（4 通道）完整重配置
  - `BLEService._on_disconnected()` 去掉 `restart()`，只更新状态清队列
  - `ControlService._ble_connect()` 调用 `connect()` 替代 `restart()`
  - 蓝牙调试工具验证 4 个特征值通道正常，小程序可连接收发数据

- 🔧 **碰撞报警 TTS + SMS 修复**
  - 删除 SD 卡 MP3 播放（`play_file`），改为统一 `EVENT_TTS_REQUEST` 发布
  - 碰撞报警 TTS "碰撞报警，等级X"，SOS 报警 TTS "SOS报警，请注意安全"
  - AudioService 报警状态下每 5 秒循环入队报警 TTS，取消后停止
  - 静默报警 `trigger_stealth_alarm()` 增加 SMS 发送，内容 "stealth:1"
  - `_build_sms_message()` 增加 `alarm_type` 参数，SMS 内容从固定 "SOS:N" 变为 "{alarm_type}:{level}"

- 🔧 **LCD 显示修复**
  - `tick()` 脏标志渲染 + `_render_normal_screen()` 增加 `display_mode` 守卫，禁止 boot/alarm 时叠加渲染
  - 进入省电/紧急模式时 `lcd_driver.clear()` 清屏
  - 从省电模式唤醒时设 `_dirty=True` 强制重新渲染，消除报警取消后画面空白

- 🔧 **传感器看门狗**
  - IMU 和 Temp_Humid 添加 `_abandoned` 标志
  - 连续 10 次 I2C 读取失败后完全放弃，防止 I2C 死锁时无限重试占用 CPU

- 📝 **文档与报告**
  - 更新架构文档、模块实现文档、测试指南
  - 添加 Bug 修复报告（碰撞报警/BLE/LCD/传感器综合修复）
  - 添加 UART9 AT 通道冲突审计报告

## 2026-06-26

- 🟢 **系统级架构修复与优化**
  - P0 **EventBus 队列 OOM 保护** — 新增三级防御：传感器数据去重(同类型替换) + 软上限40(逐出非关键) + 硬上限64(兜底OOM)。关键事件白名单(碰撞/报警/SOS/BLE_ACK/电源切换/TTS)永不主动丢弃
  - P0 **碰撞等级判定修正** — `_determine_level()` 中 `or` → `and`，修复高峰值+短持续碰撞被误判为轻微(Level 1)而非严重(Level 3)的逻辑缺陷
  - P0 **HeartRate 阻塞移除** — `start_collect()` 删除 `time.sleep_ms(100)`，消除 EventBus 回调中 100ms 主循环冻结
  - P1 **Audio _cb_ring 线程安全** — 加 `_thread.allocate_lock()` 保护，修复回调线程与主线程并发操作无锁列表的竞争

- 🔧 **架构违规修复**
  - **NavigationService 双路径写 LCD** — 删除 `lcd_driver` 注入和 `_write_nav_line()` 方法，导航文字仅通过 `EVENT_NAV_DISPLAY` → DisplayService 单路径管理
  - **AlarmService 绕过 AudioService** — `_on_gps_lost()` 从直接调 `audio.play_tts()` 改为发布 `EVENT_TTS_REQUEST`，走统一优先级调度
  - **DisplayService 脏标记缺失** — `_on_nav_display()` 补设 `_dirty=True`，确保导航文字及时渲染

- 🔧 **15 个测试文件同步更新** — 移除 NavigationService `lcd_driver=` 过期参数；GPS 丢失 TTS 断言更新为 EventBus 事件捕获

- 🔧 **Audio 修复残留问题** — `_on_gps_lost` 相关测试文件断言更新（test_alarm_service_unit + integration）

- 📝 **文档同步** — dev_log.md 同步

## 2026-06-27

- 🟢 **30 分钟全场景压力测试（有 SIM 卡）通过**
  - 173/173 操作全部执行，WDT 0 次复位，23/23 模块在线
  - 内存 119KB→91KB→91KB，零泄漏；CPU 3.5ms/轮（75% 空闲）
  - 173 操作覆盖 BLE 控制+语音查询+导航+报警+电源 5 大域

- 🔴 **8 个缺陷发现与修复**
  - P0: AT_LOCK 全局互斥锁（GNSS/Audio/SMS 三路并发崩溃根因）
  - P0: GNSS 三段式退避（无天线 900→100 次 AT 命令，降幅 89%）
  - P0: SMS 持久线程+队列（替代每次 spawn 新线程的内存碎片模式）
  - P1: Temp_Humid 冷却+一次复活（替代永久放弃）
  - P1: SMS 冷却防抖+返回值检查（失败不静默）
  - P1: SMS 线程栈 8KB（中文 UCS2 编码不溢出）
  - P2: AudioService 心跳修正（移到驱动守卫之前）
  - P2: 离线模块诊断增强

- 📝 **报告** — 30 分钟全场景最终报告 + Bug 修复报告 + 基线报告

## 2026-06-28

- 🧪 **4 项独立边界测试全部通过**
  - I2C1 总线争用：277,881 次交替 tick，0 error
  - 报警中切电源：ACTIVE→SUSPENDED→EMERGENCY→ACTIVE，零崩溃
  - SOS 极限取消：5 组 1s 间隔循环，0 状态残留
  - EventBus 队列溢出：100 事件冲 HARD_MAX=64，CRITICAL 50/50 全保留

- 🆕 **v3 压力测试** — 构造参数修复（LightService/DisplayService/BLEService 注入驱动）+ _manual_locked 验证 + Audio 预占 + Burst 密集 + GNSS 退避触发
  - 192/193 操作，WDT 0，Audio 错误 0（timeout_ms 修复生效）

- ✨ **_manual_locked 手动锁定机制**
  - 用户调亮度/开关灯 → 永久禁止自动省电，仅 power_save 可解锁
  - 报警期间禁止自动省电（_alarm_active 标志位）
  - config.py 新增 EVENT_MANUAL_ACTIVITY 事件

- 🏗️ **两阶段开机动画**
  - Phase A：LCD+DisplayService 先显示开机画面（洛天依头像+队名）
  - Phase B：后台初始化 22 个模块，LCD 硬件自主刷新不阻塞
  - DisplayService 事件驱动 boot→normal 切换（替代固定 2500ms 定时器）
  - WDT 8s 硬件看门狗集成 + reset_cause 复位原因检测
  - SystemMonitor 非侵入式监控集成

- 🔧 **15 个模块心跳补全** — tick() 中 `last_hb` 移到状态守卫之前，解决 SystemMonitor 误判离线

- 🔧 **Audio.py timeout_ms 回退** — 撤销错误改动，190 次 TTS 报错归零

- 📝 **报告** — 无 SIM 卡 v3 压力测试报告 + 边界测试结果补充到最终报告

## 2026-06-29

- 📝 **8 个文档全量同步**
  - `02_Design _scheme.md`：8 处更新（BOOT 状态机、_manual_locked、CUSTOM 模式、初始化顺序重写、27 指令、场景八、里程碑 v9.0）
  - `01_architecture.md`：6 处更新（两阶段 init、SystemMonitor、WDT 章节、3 新事件、CloudService 清理）
  - `PowerService_impl.md`：手动锁定机制文档
  - `DisplayService_impl.md`：Boot 动画重写+英文布局
  - `ControlService_impl.md`：MANUAL_ACTIVITY+CUSTOM 覆盖
  - `AGENTS.md`：init 顺序+构建状态+heartbeat 教训
  - `测试指南.md`：Step 7 压力测试 8 个文件
  - `integration.md`：Step 7 阶段描述

- 🔧 **config.py 重复定义修复** — EVENT_MANUAL_ACTIVITY 合并为单一定义

- 📝 **37 个文件 6 批次提交** — heartbeat→_manual_locked→main→display→tests→docs
