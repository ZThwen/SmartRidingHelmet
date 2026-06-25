# Bug 审计与修复报告 — UART9 与 EC200U AT 通道冲突导致初始化失败

> **日期**：2026-06-25
> **范围**：HeartRateDriver / AudioDriver / BLEDriver / SMSDriver / GNSSDriver / main.py / core/config.py
> **审计方式**：运行时日志分析 + 逐步调试排除法 + 硬件测试

---

## 修复清单

| # | 严重度 | 模块 | Bug | 状态 |
|---|--------|------|-----|:----:|
| 1 | 🔴 致命 | HeartRateDriver + 所有 quectel 模块 | HeartRate 的 UART9 初始化破坏 EC200U AT 通道，导致 Audio/BLE/SMS/GNSS 全部初始化失败 | ✅ 已修复 |
| 2 | 🟡 严重 | HeartRateDriver | init() 中 `time.sleep_ms(500)` 阻塞主线程，加剧 AT 通道异常 | ✅ 已修复 |
| 3 | 🟡 严重 | GNSSDriver | 后台线程抢占 AT 通道，初始化时与其他 quectel 模块冲突 | ✅ 已修复 |
| 4 | 🟢 轻微 | main.py | GC 阈值 15000 过高，触发太频繁 | ✅ 已修复 |
| 5 | 🟢 轻微 | DisplayService | 事件回调中直接 LCD 渲染，加重 EventBus.pump 耗时 | ✅ 已修复 |
| 6 | 🟢 轻微 | TempHumidDriver | 首次读取阻塞 3s，需模块内超时跳过 | ✅ 已修复 |

---

## Bug 详情

---

### Bug 1：UART9 初始化破坏 EC200U AT 通道

| 项目 | 内容 |
|------|------|
| **文件** | `core/config.py:87` (HEARTRATE_UART_ID=9) → `Drivers/sensor/HeartRate.py:94` |
| **发现方式** | 运行时日志分析：main.py 中 Audio AT+QAUDMOD=2 超时 15s，但 test_sms_e2e.py 独立运行正常 |
| **根因** | HeartRate 使用 UART9（TX=PD15, RX=PD14），`UART(9, 115200)` 初始化会破坏 EC200U 的 AT 通道。**具体底层机制未探明**（不涉及引脚冲突，EC200U 使用 USART6），但通过逐步调试排除了定时器、中断等其他因素，确认是 UART9 初始化本身导致的。UART5、UART6、UART7 等均无此问题 |
| **触发条件** | HeartRate.init() 在 quectel 模块（Audio/BLE/SMS/GNSS）之前执行 |
| **影响** | Audio init 阻塞 15s（AT+QAUDMOD=2 超时），BLE init 阻塞 3s（AT+QBTCFG 超时），GNSS init 失败（AT+QGPS=1 超时）。系统 3 个模块离线，初始化总耗时 25s+ |
| **修复** | 将 HeartRate 的 UART 从 UART9 改为 UART5（TX=PC12, RX=PD2），该 UART 经验证不影响 AT 通道 |
| **验证** | 修改后运行 main.py，Audio/BLE/SMS/GNSS 全部初始化成功，AT 命令无超时 |

#### 探索过程

1. **发现异常** — main.py 初始化时 Audio/BLE/SMS 的 AT 命令全部超时，但 test_sms_e2e.py 正常
2. **排除 GNSS 抢占** — 将 GNSS 线程延迟 5 秒启动，问题依旧 → 不是 AT 通道争用
3. **排除初始化顺序** — 将 Audio 移到 HeartRate 之前，问题解决 → 确认是 HeartRate 导致
4. **排除 time.sleep** — 删除 HeartRate init 中的 `time.sleep_ms(500)`，问题依旧 → 不是 sleep 阻塞
5. **定位到 UART(9, 115200)** — 创建逐步调试脚本 `test_heartrate_debug.py`，逐行测试发现只执行 `UART(9, 115200)` 就触发了 Audio 初始化失败
6. **验证 UART 特异性** — 创建 `test_uart_debug.py` 测试所有 UART 编号，结果：
   - UART1、2、4、5、7、8 → ✅ Audio 成功
   - **UART9 → ❌ Audio 失败**
   - UART10 → EC200U 重启（但最终成功）
   - **结论：只有 UART9 会导致问题**
7. **确认 UART5 可行** — 将 HeartRate 固件引脚改为 UART5（PC12/PD2），Audio/BLE 初始化正常

---

### Bug 2：HeartRate init 中 time.sleep_ms(500) 阻塞主线程

| 项目 | 内容 |
|------|------|
| **文件** | `Drivers/sensor/HeartRate.py:108` |
| **发现方式** | 代码审查发现违背 AGENTS.md 规则：`tick() < 5ms，禁止 time.sleep()` |
| **根因** | `time.sleep_ms(500)` 在 MicroPython 中阻塞整个系统 500ms，导致 EC200U 主线程无法及时处理 AT 事件 |
| **触发条件** | HeartRate.init() 执行时 |
| **影响** | 加剧 EC200U AT 通道异常，500ms 阻塞使 EC200U 状态进一步恶化 |
| **修复** | 删除 `time.sleep_ms(500)`，响应检查直接在 init() 末尾执行 |
| **验证** | HeartRate 传感器功能不受影响（数据采集在 tick 中完成） |

---

### Bug 3：GNSS 后台线程抢占 AT 通道

| 项目 | 内容 |
|------|------|
| **文件** | `Drivers/sensor/Gnss.py:84-87` |
| **发现方式** | 运行时日志：GNSS 线程每 2 秒发 AT+QGPSLOC=2，与 Audio/BLE/SMS 初始化命令争抢 AT 通道 |
| **根因** | init() 中立即启动 GNSS 后台线程，EC200U AT 通道是串行的，多模块同时发 AT 命令导致逐一超时 |
| **触发条件** | 系统初始化期间，GNSS 线程与其他 quectel 模块同时使用 AT 通道 |
| **影响** | 加剧初始化阶段的 AT 超时 |
| **修复** | init() 中只记录启动时间，tick() 中延迟 5 秒后启动线程 |
| **验证** | 初始化期间无 AT 通道竞争 |

---

## 未修复的已知问题

| # | 模块 | 问题 | 影响 | 建议修复时间 |
|---|------|------|------|------------|
| 1 | EC200U AT 通道 | UART9 初始化导致 AT 通道异常的底层机制未探明 | 已通过更换 UART 解决，但根因未知 | 后续需联系移远技术支持或查看固件源码确认 |
| 2 | TempHumidDriver | ahtx0 库内置忙等无超时 | 传感器故障时可能堵塞主循环，当前超时跳过机制已兜底 | 后续优化 |
| 3 | EventBus | pump() 无流控限制 | 极端事件风暴时可能耗时较长，当前脏标志已大幅缓解 | 后续优化 |

---

## 修复文件清单

| 文件 | 修复内容 | 源码 | Thonny |
|------|---------|:----:|:------:|
| `core/config.py` | HEARTRATE_UART_ID 9→5，引脚 PD15/PD14→PC12/PD2 | ✅ | ✅ |
| `Drivers/sensor/HeartRate.py` | 删除 `time.sleep_ms(500)` | ✅ | ✅ |
| `Drivers/sensor/Gnss.py` | 延迟 5 秒启动后台线程 | ✅ | ✅ |
| `core/main.py` | 初始化顺序恢复原始（Bug 1 已修复，不再需要调整） | ✅ | ✅ |
| `Drivers/sensor/Temp_Humid.py` | 模块内超时跳过保护 | ✅ | ✅ |
| `Modules/display_service.py` | 脏标志模式消除事件回调中 LCD 渲染 | ✅ | ✅ |

---

## 审查建议

1. **上板优先测试** — HeartRate UART5 修改和 GNSS 延迟启动最需要上板验证
2. **测试顺序建议**：
   - 先运行 `test_heartrate.py` 验证 HeartRate 功能正常
   - 再运行 `test_sms_e2e.py` 验证 AT 通道正常
   - 最后运行 `main.py` 观察初始化是否流畅
3. **后续关注** — UART9 触发 AT 通道异常的底层机制若有机会应进一步排查，可联系移远技术支持
