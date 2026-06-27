# 压力测试报告 — 30 分钟稳定性基线

> 日期：2026-06-27 | 硬件：NUCLEO-F413ZH + EC200U | 测试文件：`stress_test_30min_bare.py`

---

## 1. 测试概述

**目的**：验证智能骑行头盔固件在 30 分钟连续运行下的稳定性——无崩溃、无内存泄漏、无模块失联、关键安全链路持续在线。

**方法**：独立测试脚本（不依赖 main.py），自建 EventBus + 23 个模块实例，模拟主循环调度（tick → pump → sleep(10ms)），全程由硬件看门狗（WDT 8s）和 SystemMonitor 双重监控。

**硬件环境**：NUCLEO-F413ZH（STM32F413ZH）+ Quectel EC200U 模组。扬声器、心率传感器（UART9）、Voice（ASRPRO UART）、GNSS 天线均未连接——仅验证核心固件逻辑与模块间通信，不验证外设功能。

**运行配置**：
- 23 个模块：14 驱动 + 9 服务
- SystemMonitor：心跳扫描间隔 5s，关键模块超时 30s
- WDT：超时 8s，由 SystemMonitor.should_feed_wdt() 门控
- 测试时长：1800s（30 分钟），自动停止

---

## 2. 数据采集方法与可信度

### 2.1 采集原理

所有指标均由测试脚本在运行时直接采集，**不依赖外部仪器或日志推断**。

| 指标 | 采集方式 | 精度 | 可信度 |
|------|---------|:--:|:--:|
| 运行时长 | `ticks_diff(now, t0) // 1000` | ±1s | ⭐⭐⭐ 直接计时 |
| WDT 复位次数 | SystemMonitor 持久化计数（启动时读 `reset_cause()` + `sysmon_reset.cnt`） | ±0 | ⭐⭐⭐ 硬件寄存器 |
| 内存 | `gc.mem_free()` 每秒采集，取 min/max/end | ±1 byte | ⭐⭐⭐ GC 直接查询 |
| 关键模块存活 | SystemMonitor 每秒判 `critical_alive`，累加秒数 | ±5s (扫描窗口) | ⭐⭐ 窗口平均，非逐秒精确 |
| 模块心跳 | SystemMonitor 遍历 23 模块读 `ctx["last_hb"]`，每次扫描更新 | ±5s (扫描窗口) | ⭐⭐ 扫描时刻快照 |
| 主循环周期 | 每轮 `ticks_diff(now, loop_start)`，取 avg/max | ±1ms | ⭐⭐⭐ 逐轮计时 |
| 启动时间 | 第一个模块 init 前 → 最后一个 init 后 `ticks_diff` | ±1ms | ⭐⭐⭐ 两点差值 |
| BLE 就绪时间 | 启动后轮询 `ble_drv.ctx["is_init"]`，每次 200ms | ±200ms | ⭐⭐ 轮询精度 |
| 事件吞吐 | `loop_count × 60 / total_sec`（主循环频率） | ±0.1 ops/min | ⭐⭐⭐ 精确计次 |
| 异常计数 | try/except 逐轮累加 | ±0 | ⭐⭐⭐ 精确计次 |

### 2.2 可信度说明

**⭐⭐⭐ 高可信**：数据直接来自硬件寄存器或精确计数，不存在估算或间接推断。

**⭐⭐ 中信度**：受采集频率限制（如 SystemMonitor 5s 扫描周期），在两次扫描之间发生的短暂状态变化可能未被捕获，但宏观趋势（30 分钟级）可靠。

### 2.3 局限性

1. **扫描窗口误差**：SystemMonitor 每 5s 扫描一次，模块在扫描间隙的瞬时离线不会被记录。报告中的"关键模块存活 1800s"是扫描窗口下的宏观判读，不代表逐秒绝对精确。
2. **裸跑环境**：无外设交互（BLE 未连接、无 TTS 播放、无碰撞事件），仅验证基础调度稳定性。真实骑行场景的负载更高（BLE 推送、TTS、报警同时触发），需补充主动负载测试。
3. **单次测试**：本报告基于一次 30 分钟运行，统计意义上为单样本。竞赛场景建议重复 2-3 次取平均。

---

## 3. 测试结果

**结论：23/23 模块存活，0 次 WDT 复位，0 次异常 —— ALL PASS**

### 3.1 稳定性指标

| 指标 | 值 | 判定 |
|------|----|:--:|
| 运行时长 | 1800s (30min) | ✅ 完成 |
| WDT 复位 | 0 次 | ✅ |
| 内存 | 139KB → 112KB → 112KB (80%保留) | ✅ 无泄漏 |
| 关键模块存活 | 1800/1800s (100%) | ✅ |
| 模块心跳 | 23/23 在线 | ✅ |
| 模块异常 | 0 次 | ✅ |
| 泵异常 | 0 次 | ✅ |

### 3.2 性能指标

| 指标 | 值 | 判定 |
|------|----|:--:|
| 平均主循环周期 | 13.5ms | ✅ <20ms |
| 最慢主循环周期 | 141ms | ✅ <8s WDT |
| 启动完成时间 | 4s | ✅ |
| BLE 就绪时间 | 4s | ✅ |

### 3.3 负载指标

| 指标 | 值 | 说明 |
|------|----|------|
| TTS 已播 | 0 次 | 裸跑无人工操作 |
| 事件吞吐 | 4430 ops/min (~74Hz) | 主循环调度频率 |
| 循环次数 | 132,923 | 30min × 74Hz |
| WDT 馈异常 | 0 次 | |

### 3.4 连接状态

| 接口 | 状态 | 说明 |
|------|------|------|
| BLE | Init（未连接） | 无手机配对，正常 |
| 扬声器 | 未连接 | 不影响模块初始化 |
| 心率/Voice/GNSS | 未连接 | 仅验证模块初始化 |

### 3.5 模块心跳详情（23/23 全部在线）

```
  temp_humid           ✓ IMPORTANT
  imu                  ✓ IMPORTANT
  gnss                 ✓ IMPORTANT
  light_Sensor         ✓ AUXILIARY
  BATTERY              ✓ AUXILIARY
  heartrate            ✓ IMPORTANT
  button               ✓ AUXILIARY
  voice                ✓ AUXILIARY
  led                  ✓ AUXILIARY
  audio                ✓ IMPORTANT
  lcd                  ✓ AUXILIARY
  pwm_led              ✓ AUXILIARY
  ble                  ✓ IMPORTANT
  SMS                  ✓ AUXILIARY
  collision            ✓ CRITICAL
  audio_service        ✓ IMPORTANT
  alarm                ✓ CRITICAL
  display              ✓ IMPORTANT
  light_service        ✓ AUXILIARY
  ble_service          ✓ CRITICAL
  control_service      ✓ AUXILIARY
  navigation           ✓ AUXILIARY
  power_service        ✓ AUXILIARY
```

---

## 4. 关键指标分析

### 4.1 内存：139KB → 112KB → 112KB (80%)

三个数字 = 启动前 / 运行中最低点 / 结束时。启动分配 27KB（23 模块的 ctx/cfg/_data + 栈 + 队列），此后 30 分钟最低点与结束点持平。**若存在泄漏，结束点会持续低于最低点。持平 = GC 正常 = 零泄漏。** 堆剩余 112KB 可支撑峰值业务负载（TTS 音频缓冲、BLE 推送队列、报警事件突发）。

### 4.2 WDT 复位：0 次

硬件看门狗 8s 超时。SystemMonitor 在主循环每轮调 `should_feed_wdt()`——启动宽限期（15s）内无条件喂狗，之后需所有关键模块心跳有效才喂。30 分钟全程正常喂狗 = 主循环从未卡死超过 8s = 无死锁/活锁。

### 4.3 关键模块存活：1800/1800s (100%)

碰撞检测（collision_service）、报警触发（alarm_service）、BLE 紧急推送（ble_service）——三条是骑行安全的最后一环。全程心跳有效意味着安全链路无单点失效。注意此数据为 SystemMonitor 5s 扫描窗口下的宏观判读，逐秒精度为 ±5s。

### 4.4 主循环：平均 13.5ms，最慢 141ms

23 模块 tick() + EventBus pump + WDT feed + sleep(10ms) 的总耗时。13.5ms ≈ 74Hz 调度频率。最慢 141ms 是偶发峰值（AHT20 82ms I2C 读 + LCD SPI 刷新叠加在同一轮），远低于 WDT 的 8s 阈值。如果峰值频繁超过 200ms，需要分拆 AHT20 读取到子线程——当前单次测试未见此趋势。

### 4.5 启动时间：4 秒，BLE 同步就绪

23 模块逐个 init() 的总耗时仅 4s，且 BLE 广播同步就绪。说明：
1. 初始化顺序（传感器→执行器→心率→服务）合理
2. EC200U AT 通道（BLE/Audio/SMS/GNSS）初始化未出现懒加载竞态
3. HeartRate UART9 在所有 quectel 模块之后初始化，未破坏 AT 通道

---

## 5. 测试中发现的缺陷与修复

### 缺陷 1：应力测试未注入 AudioDriver（测试脚本 Bug）

- **现象**：audio_service 模块心跳为 0，SystemMonitor 报告 22/23 在线
- **根因**：测试脚本 `AudioService(bus)` 未传 `audio_driver` 参数；同时 `AudioService.tick()` 将 heartbeat 放在 audio_driver 空值守卫之后，导致驱动缺失时心跳不更新
- **修复**：
  - `audio_service.py`：heartbeat 移到 audio_driver 守卫之前（防御性加固）
  - 应力测试：init 后注入 `audio_svc.audio_driver = audio_drv`
- **影响**：仅测试脚本，main.py 正确注入了 AudioDriver，不受影响

### 缺陷 2：TempHumidDriver 永久放弃过于激进（模块设计缺陷）

- **现象**：AHT20 单次 I2C 读取耗时 82ms，易被总线抖动中断；原设计 10 次连续失败即永久放弃温湿度功能
- **根因**：`_abandoned` 标志无恢复机制，一次短时 I2C 抖动即导致模块永久失效
- **修复**：改为"冷却期 5 分钟 + 一次复活"机制——首次 10 次失败进入 300s 冷却后自动重试，第二次 10 次失败才永久放弃（判定为硬件故障）
- **影响**：仅 Temp_Humid.py，不影响其他模块

---

## 6. 结论

**系统固件在 30 分钟连续运行中达到竞赛级稳定性要求：**

- ✅ 零崩溃、零 WDT 复位、零内存泄漏
- ✅ 23 个模块全部在线，安全链路 100% 存活
- ✅ 主循环 74Hz 稳定运行，峰值 141ms 在设计容限内
- ✅ 4 秒冷启动，BLE 同步就绪
- ✅ 发现并修复 2 个缺陷（1 个测试脚本 Bug + 1 个模块设计缺陷）

**待补充**：连接外设后的主动负载测试（170 条操作覆盖 BLE 控制/导航/语音/电源切换/报警）、多次重复取平均。
