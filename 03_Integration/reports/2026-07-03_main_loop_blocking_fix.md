# Bug 审计与修复报告 — 主循环阻塞导致系统不可用

> **日期**：2026-07-03
> **范围**：main.py, display_service.py, images2.py, alarm_icon.py, boot_text.py
> **审计方式**：集成测试 + 逐步排除法 + 硬件测试

---

## 修复清单

| # | 严重度 | 模块 | Bug | 状态 |
|---|--------|------|-----|:----:|
| 1 | 🔴 致命 | images2/alarm_icon/boot_text | 单行 hex 超长导致 MicroPython 编译器崩溃 → WDT 复位 | ✅ 已修复 |
| 2 | 🔴 致命 | main.py | `_record_pre_feed_state()` 每轮主循环写 wdt_diag.cnt 文件，flash I/O 阻塞 10-50ms/轮 | ✅ 已修复 |
| 3 | 🔴 致命 | main.py | 每 200 轮打印 24 模块 get_data()，串口传输 ~87ms，阻塞主循环 | ✅ 已修复 |
| 4 | 🔴 致命 | display_service.py | `_on_system_ready()` 在 EventBus.pump() 回调中同步执行 LCD SPI，阻塞 pump 217ms | ✅ 已修复 |
| 5 | 🟡 严重 | display_service.py | `_switch_to_normal()` 释放图片数据导致下次启动图片丢失 | ✅ 已修复 |

---

## Bug 详情

---

### Bug 1：图片文件单行超长 → MicroPython 编译器崩溃 → WDT 复位

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/images2.py`, `02_Software/alarm_icon.py`, `02_Software/boot_text.py` |
| **发现方式** | 串口日志显示 "invalid syntax" / "name too long"，上传 boot_text.py 后生成 wdt_diag.cnt |
| **根因** | `bytes.fromhex("...")` 将整个 hex 数据放在一行（images2: 40042 字符, alarm_icon: 9260 字符, boot_text: 12836 字符），MicroPython lexer 行缓冲 < 1024 字符 |
| **触发条件** | 设备上有这三个文件 |
| **影响** | MicroPython 编译器崩溃 → WDT 8 秒超时复位 → 系统无法启动 |
| **修复** | 将 hex 字符串拆分为多行隐式拼接，每行 64 字符 |
| **验证** | `ast.parse` 通过，display init 日志显示"加载成功" |

---

### Bug 2：`_record_pre_feed_state` 每轮写文件 → 主循环堵塞

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/core/main.py:182` |
| **发现方式** | 创建 main_step_debug.py 逐步集成测试，A-I 组全部 PASS，证明模块无问题；对比 main.py 与诊断工具差异，定位到文件写入操作 |
| **根因** | `sysmon._record_pre_feed_state(slow_modules)` 每轮主循环打开 wdt_diag.cnt 写入模块心跳数据。STM32 MicroPython flash 写入每次 10-50ms+，24 模块迭代后单轮耗时达 100-300ms |
| **触发条件** | WDT 启动后的每一轮主循环 |
| **影响** | 主循环实际周期从目标 ~15ms 膨胀到 ~100ms+，GNSS 线程启动延迟，语音响应滞后，调试信息 1 分钟后才打印 |
| **修复** | 删除 `_record_pre_feed_state()` 调用及相关 `slow_modules` 管理代码 |
| **验证** | main_no_filewrite.py（移除文件写入后）运行流畅，BEAT 正常 |

---

### Bug 3：24 模块 `get_data()` 全量打印 → 周期性阻塞

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/core/main.py:222-227` |
| **发现方式** | 代码审查，串口 115200 baud 传输时间计算 |
| **根因** | 每 200 轮（约 2 秒）打印 24 个模块的 `get_data()`，串口传输 ~1000 字符需 ~87ms，加字符串格式化总计 ~100ms |
| **触发条件** | 主循环运行中，`loop_count % 200 == 0` |
| **影响** | 每 2 秒产生一个 ~100ms 的阻塞脉冲，系统周期性卡顿 |
| **修复** | 删除该调试打印块 |
| **验证** | 代码审查确认 |

---

### Bug 4：`_on_system_ready` 在 pump 回调中执行 LCD SPI

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/Modules/display_service.py:380-401` |
| **发现方式** | 串口日志显示 "EventBus.pump 耗时 217ms" |
| **根因** | `_on_system_ready()` 在 `EventBus.pump()` 回调中同步调用 `_switch_to_normal()`，包含 `clear()` + `gc.collect()` + `show_string()` 等 LCD SPI 操作 ~120ms |
| **触发条件** | `EVENT_SYSTEM_READY` 发布后 |
| **影响** | 启动时 pump 阻塞 217ms，所有事件处理延迟 |
| **修复** | 改为设置 `_needs_switch_to_normal = True` 延迟标志，在 `tick()` 中执行 |
| **验证** | pump 耗时从 217ms 降至 16ms |

---

### Bug 5：`_switch_to_normal` 释放图片数据

| 项目 | 内容 |
|------|------|
| **文件** | `02_Software/Modules/display_service.py:466-476` |
| **发现方式** | 用户反馈"下次启动图片不存在" |
| **根因** | `_switch_to_normal()` 将 `luotianyi_icon_data` 和 `boot_text_data` 设为 None 并 `gc.collect()`，导致下次启动时图片文件已不可用 |
| **触发条件** | 开机画面切换到正常画面时 |
| **影响** | 设备重启后图片丢失，无法再次显示开机动画 |
| **修复** | 删除图片数据释放代码 |
| **验证** | 代码审查确认 |

---

## 未修复的已知问题

| # | 模块 | 问题 | 影响 | 建议 |
|---|------|------|------|------|
| 1 | Temp_Humid | AHT20 传感器每 2 秒 I2C 阻塞 73ms | 主循环周期性变慢 | 已知硬件权衡，暂不修 |
| 2 | DisplayService | `_render_normal_screen` 每秒 SPI 阻塞 60ms | 主循环周期性变慢 | 渲染硬件限制，旧版本亦存在 |
| 3 | GNSS | 线程启动 5000ms 硬编码延迟 | GNSS 启动慢 | 可降低到 1000ms |

---

## 修复文件清单

| 文件 | 修复内容 | 源码行数 | Thonny 行数 |
|------|---------|---------|------------|
| `02_Software/core/main.py` | 删除 `_record_pre_feed_state` + `slow_modules` + debug print | -15 行 | -15 行 |
| `02_Software/Modules/display_service.py` | pump 回调延迟到 tick + 移除图片释放 | +8/-16 行 | +8/-16 行 |
| `02_Software/images2.py` | 单行 hex → 多行拼接 | +628 行 | +628 行 |
| `02_Software/alarm_icon.py` | 单行 hex → 多行拼接 | +147 行 | +147 行 |
| `02_Software/boot_text.py` | 单行 hex → 多行拼接 | +203 行 | +203 行 |

---

## 审查建议

1. **上板优先测试** — main.py 的 `_record_pre_feed_state` 删除是最关键修复，直接影响系统可用性
2. **测试顺序** — 先测 main.py（确认主循环恢复），再测语音交互（确认响应即时），最后测 GNSS 启动时间
3. **后续关注** — temp_humid 73ms 和 display 60ms 是两个已知的周期性阻塞，当系统负载增加时需重新评估
