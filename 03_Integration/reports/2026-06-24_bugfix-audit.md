# 系统 Bug 审计与修复报告

> **日期**：2026-06-24
> **范围**：22 模块全量逐行审计，定位 6 个 Bug，修复 4 个
> **审计方式**：AGENTS 逐行分析 tick() / 事件流 / 线程安全 / 资源冲突

---

## 修复清单

| # | 严重度 | 模块 | Bug | 状态 |
|---|--------|------|-----|:----:|
| 1 | 🔴 致命 | AudioDriver | tick() 缩进错误 → TTS 全链路死锁 | ✅ 已修复 |
| 2 | 🔴 致命 | AudioDriver | _cb_ring 无上限 → 内存泄漏 | ✅ 已修复 |
| 3 | 🔴 致命 | Button | ISR 中调用 publish() → HardFault 风险 | ✅ 已修复 |
| 4 | 🟡 严重 | BLEService | 异常处理 data 未定义 → 后台线程崩溃 | ✅ 已修复 |
| 5 | 🟡 严重 | HeartRateDriver | 无帧验证 + 无限读取 → 阻塞主循环 | ✅ 已修复 |
| 6 | 🟡 中危 | I2C1 | TempHumid + IMU 双重初始化 | ⏸️ 暂不修复 |

---

## Bug 详情

---

### Bug 1：AudioDriver.tick() 缩进错误

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/Drivers/actuator/Audio.py:99` |
| **发现方式** | 逐行审计 tick() 时注意到缩进异常 |
| **根因** | `def tick(self):` 使用了 8 空格缩进，导致被定义在 `init()` 方法体内部，成为 init 的嵌套局部函数。类级别的 tick() 实际继承自 BaseModule（空实现，`pass`） |
| **触发条件** | 任何 TTS 或音频播放请求 |
| **影响** | **级联故障**: ① `_cb_ring` 无人消费 → 无限增长 → 内存泄漏 ② `is_tts_playing` 永不清零 → AudioService 队列堵死 ③ 首条语音后所有后续 TTS（导航/语音反馈/报警提示）全部静默 |
| **修复** | 将 `def tick(self):` 缩进从 8 空格改为 4 空格（类方法级别），方法体内代码缩进同步减 4 空格 |
| **验证** | 语法检查通过；tick() 现在在类作用域，会被主循环正确调用 |

---

### Bug 2：AudioDriver._cb_ring 无容量上限

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/Drivers/actuator/Audio.py:63` |
| **发现方式** | 分析内存泄漏风险时发现 |
| **根因** | `self._cb_ring = []` 无 maxlen 限制，`_audio_event_cb` 回调只 `append` 不 `pop`（pop 在 tick 中，但 tick 因 Bug 1 失效） |
| **触发条件** | 连续 TTS/音频播放操作 |
| **影响** | 缓冲区无限增长 → OOM；修复 Bug 1 后仍需容量上限防止极端场景泄漏 |
| **修复** | tick() 的 while 循环中增加容量守卫：`len(self._cb_ring) > 10` 时 pop(0) 并 continue，丢弃最旧事件 |
| **验证** | 语法检查通过 |

---

### Bug 3：Button ISR 中调用 EventBus.publish()

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/Drivers/interface/Button.py:79` |
| **发现方式** | 分析线程安全时发现 ISR 上下文持锁 |
| **根因** | `button_handler()` 在 IRQ 上下文中直接调用 `EventBus.publish()`，该方法内部会获取 `_lock`。如果主循环恰好正在 `pump()` 中持锁，ISR 阻塞等待 → STM32 HardFault |
| **触发条件** | 按 SW 按钮的瞬间，恰好与 EventBus.pump() 持锁时段重叠 |
| **影响** | 系统硬故障重启（概率性，难以复现） |
| **修复** | ISR 只置位 `button_pressed_flag = True`，tick() 中检查标志 → 清除 → publish()。ISR 零锁操作 |
| **验证** | button_handler 中确认无 publish() 调用；tick() 中确认有标志检查 + publish |

---

### Bug 4：BLEService 后台线程异常处理中 data 未定义

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/Modules/ble_service.py:216` |
| **发现方式** | 分析异常处理路径时发现 |
| **根因** | `try` 块内 `data = self.send_queue.get()` 若在 `get()` 阶段抛异常，`data` 变量从未被赋值，但 `except` 中引用了 `data` 做日志输出。原代码用 `data if 'data' in dir() else 'N/A'` 防御，但 MicroPython 的 `dir()` 行为不可靠 |
| **触发条件** | `send_queue.get()` 抛异常（如队列损坏、锁超时） |
| **影响** | 异常处理自身再次抛异常 → 后台线程崩溃 → BLE 推送停止 |
| **修复** | try 块顶部初始化 `data = None`，异常处理中改为 `data if data is not None else 'N/A'` |
| **验证** | 语法检查通过；确认 L190 有 `data = None` |

---

### Bug 5：HeartRateDriver 无帧验证 + 无限读取

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/Drivers/sensor/HeartRate.py:148-178` |
| **发现方式** | 分析主循环阻塞风险时发现 |
| **根因** | ① `_read_uart()` 中 `self.uart.read(self.uart.any())` 一次性读取所有可用字节，UART 缓冲区可能积累数百字节 → 逐字节扫描 0xFF 帧头可能超时 ② `_parse_packet()` 无任何验证 → 直接取 raw_hr/spo2 返回 |
| **触发条件** | ① 传感器数据量大时偶尔触发"真阻塞" ② 数据损坏时接收无效值 |
| **影响** | ① 主循环偶发超时告警 ② 无效心率血氧数据被当作有效数据消费 |
| **修复** | ① `max_read = min(available, 200)` 限制读取量 ② `frames_processed` 上限 4 帧/tick ③ `_parse_packet()` 5 重验证：长度≠50→None、帧头≠0xFF→None、HR 超范围→None、SpO2 超范围→None、预热未完成→None ④ tick() 包裹 try-except，err_count>10 自动停止采集 |
| **验证** | 语法检查通过；确认 `_parse_packet` 返回类型为 `dict|None`；确认 `max_read` 和 `frames_processed` 限制 |

---

### Bug 6：I2C1 双重初始化（未修复）

| 项目 | 内容 |
|------|------|
| **文件** | `Temp_Humid.py:56-59` + `imu.py:64-67` |
| **发现方式** | 分析硬件资源冲突时发现 |
| **根因** | 两个驱动各自创建 `machine.I2C(1, ...)` 实例，后者可能重新初始化 I2C 外设 |
| **影响** | 某些 MicroPython 端口下 I2C 被重新初始化，TempHumid 的 `self.i2c` 对象可能失效 |
| **当前状态** | ⏸️ 暂不修复。当前 STM32 固件中 I2C(1) 第二次调用复用已有实例，工作正常 |
| **修复建议** | main.py 中创建单一 i2c1 实例，通过构造函数注入给两个驱动 |

---

## 未修复的已知问题（仅记录，非阻塞）

| # | 模块 | 问题 | 影响 | 建议修复时间 |
|---|------|------|------|------------|
| 1 | DisplayService | tick() 中调用 `_switch_to_normal()` 执行 SPI 阻塞操作 10-30ms | 启动约 2.5s 后主循环单次超时 | 后续优化 |
| 2 | GNSS | 后台线程检查 thread_running 有 2s 延迟 | 关机时 deinit() 等待时间较长 | 后续优化 |
| 3 | ControlService | 自订阅 EVENT_POWER_STATE_CHANGE 导致双重状态推送 | BLE 带宽浪费，UI 可能闪烁 | 后续修复 |

---

## 修复文件清单

| 文件 | 修复内容 | 源码行数 | Thonny 行数 |
|------|---------|---------|------------|
| `Drivers/actuator/Audio.py` | tick indent + _cb_ring 容量守卫 | 379→379 | 270 |
| `Drivers/interface/Button.py` | ISR 标志位模式 | 153→153 | 80 |
| `Drivers/sensor/HeartRate.py` | 帧验证 + 限流 + 异常保护 | 318→359 | 272 |
| `Modules/ble_service.py` | data 初始化 | 381→381 | 339 |

---

## 审查建议

1. **上板先测 Audio** — Bug 1 是隐藏最深的致命缺陷，修复后需要验证 TTS 连续播报是否正常
2. **测试顺序建议**：TTS 播报 → 按键按压 → 心率采集 → 30 分钟稳定性
3. **后续关注**：DisplayService SPI 阻塞优化、GNSS 线程退出延迟
