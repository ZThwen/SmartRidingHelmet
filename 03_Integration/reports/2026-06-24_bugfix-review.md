# Bug 审计与修复报告 — 语音控制扩展 + PWM LED 闪烁

> **日期**：2026-06-24
> **范围**：语音控制扩展 + PWM LED 闪烁功能的代码审查
> **审计方式**：explore 代理深度审查 16 个文件（源码 + Thonny），逐行对比数据流

---

## 修复清单

| # | 严重度 | 模块 | Bug | 状态 |
|---|--------|------|-----|:----:|
| 1 | 🔴 致命 | BLEDriver | deinit() 不发布 EVENT_BLE_DISCONNECTED → BLEService 状态不同步 | ✅ 已修复 |
| 2 | 🟡 严重 | ControlService | _on_light_blink_state 只缓存不推送 → 闪烁状态不更新到小程序 | ✅ 已修复 |
| 3 | 🟡 严重 | ControlService | _update_control_state light_blink 分支为 pass → light_mode 不更新 | ✅ 已修复 |
| 4 | 🟢 轻微 | PWM_LED | import 未使用的 EVENT_CONFIG_UPDATE | ✅ 已修复 |
| 5 | 🟢 轻微 | BLEDriver | restart() 中冗余 import time as _time | ✅ 已修复 |
| 6 | 🟢 轻微 | AlarmService | _on_heartrate 使用字符串 "ALARM" 而非常量 PRIORITY_ALARM | ✅ 已修复 |
| 7 | 🟢 轻微 | Thonny | control_service._control_state 含死键 "blink" | ✅ 已修复 |
| 8 | 🟡 严重 | BLEService | deinit() 用 time.sleep_ms(700) 等待线程 → 不可靠 | ✅ 已修复 |

---

## Bug 详情

---

### Bug 1：BLEDriver.deinit() 不发布 EVENT_BLE_DISCONNECTED

| 项目 | 内容 |
|------|------|
| **文件** | `Drivers/network/BLE.py:155-169` |
| **发现方式** | explore 代理审查数据流时发现 |
| **根因** | deinit() 停止 BLE 硬件并清空状态，但未通过 EventBus 通知 BLEService |
| **触发条件** | 语音说"断开蓝牙" → ControlService._ble_disconnect() → ble_driver.deinit() |
| **影响** | BLEService 仍认为 BLE 在线（ble_connected=True），notify_thread 持续尝试发送 → 异常累积 → 断路器触发（10 次连续错误后暂停 500ms） |
| **修复** | deinit() 中保存 was_connected 状态，停止硬件后如果之前已连接则发布 EVENT_BLE_DISCONNECTED |
| **验证** | 确认 deinit() 中有 was_connected 判断 + event_bus.publish |

---

### Bug 2：_on_light_blink_state 只缓存不推送

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/control_service.py:400-402` |
| **发现方式** | 用户指出闪烁状态变更不推送 |
| **根因** | _on_light_blink_state 只更新 self._blink_active 缓存，未调用 _push_state() |
| **触发条件** | 任何闪烁状态变更（手动/报警触发/报警取消） |
| **影响** | 小程序端 f 字段不实时更新，只有下次其他指令触发 _push_state() 时才带上最新状态 |
| **修复** | 在 _on_light_blink_state 末尾添加 self._push_state() |
| **验证** | 确认 _on_light_blink_state 中有 _push_state() 调用 |

---

### Bug 3：_update_control_state light_blink 分支为 pass

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/control_service.py:328-330` |
| **发现方式** | 用户指出 light_blink 指令不更新 light_mode |
| **根因** | _update_control_state 中 light_blink 分支只有 pass，未设置 light_mode |
| **触发条件** | 语音说"闪烁" → light_blink 指令执行 |
| **影响** | BLE 推送的 m 字段仍为旧值（如 auto），与实际灯光状态不一致 |
| **修复** | 改为 self._control_state["light_mode"] = "manual" |
| **验证** | 确认 light_blink 分支设置 light_mode |

---

### Bug 4：PWM_LED import 未使用的 EVENT_CONFIG_UPDATE

| 项目 | 内容 |
|------|------|
| **文件** | `Drivers/actuator/PWM_LED.py:13` |
| **发现方式** | 移远新版 BLE 文档审查时顺带发现 |
| **根因** | 历史遗留，PWM_LED 只订阅 EVENT_POWER_STATE_CHANGE，不订阅 EVENT_CONFIG_UPDATE |
| **影响** | 无运行时影响，代码整洁性问题 |
| **修复** | 从 import 列表中移除 EVENT_CONFIG_UPDATE |

---

### Bug 5：BLEDriver.restart() 冗余 import

| 项目 | 内容 |
|------|------|
| **文件** | `Drivers/network/BLE.py:180` |
| **发现方式** | 移远新版 BLE 文档审查时发现 |
| **根因** | restart() 方法内 `import time as _time`，但文件顶部已 `import time` |
| **影响** | 无运行时影响，代码风格问题 |
| **修复** | 删除冗余 import，改用已有的 time 模块 |

---

### Bug 6：AlarmService _on_heartrate 使用字符串优先级

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/alarm_service.py:306` |
| **发现方式** | explore 代理审查时发现 |
| **根因** | 发布 EVENT_TTS_REQUEST 时 priority 使用字符串 "ALARM" 而非 config.py 定义的整数常量 PRIORITY_ALARM=0 |
| **触发条件** | 心率异常 TTS 提醒 |
| **影响** | AudioService 如按整数比较优先级可能不匹配 |
| **修复** | import PRIORITY_ALARM，替换 "ALARM" 为 PRIORITY_ALARM |
| **注意** | 此 Bug 在本次会话之前已存在，非本次变更引入 |

---

### Bug 7：Thonny control_service 死键

| 项目 | 内容 |
|------|------|
| **文件** | `thonny/Modules/control_service.py:67` |
| **发现方式** | explore 代理源↔Thonny 对比时发现 |
| **根因** | Thonny 版本 _control_state 含 "blink": False，但源版本没有此键 |
| **影响** | 无运行时影响，死代码 |
| **修复** | 移除 "blink" 键，与源版本一致 |

---

### Bug 8：BLEService deinit() 线程退出不可靠

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/ble_service.py:379-383` |
| **发现方式** | 移远新版 BLE 文档审查时发现 |
| **根因** | deinit() 使用 time.sleep_ms(700) 等待后台线程退出，不可靠 |
| **触发条件** | 系统关机或 BLE 重初始化 |
| **影响** | 如果线程在 700ms 内未退出，ble.stop()/deinit() 执行时线程可能还在 notify_data()，导致崩溃 |
| **修复** | 保存 _notify_tid，deinit() 中使用 _thread.join(tid, 3000) 等待线程安全退出 |
| **验证** | 确认 init() 中保存 _notify_tid，deinit() 中使用 _thread.join |

---

## 未修复的已知问题（仅记录，非阻塞）

当前无新增未修复问题。历史遗留参见 `2026-06-24_bugfix-audit.md`。

---

## 修复文件清单

| 文件 | 修复内容 | 源码行数 | Thonny 行数 |
|------|---------|---------|------------|
| `Drivers/network/BLE.py` | deinit 发布断开事件 + 移除冗余 import | 282→288 | 228→234 |
| `Modules/control_service.py` | _on_light_blink_state 加 _push_state + light_blink 设 light_mode | 619→622 | 486→487 |
| `Modules/ble_service.py` | _thread.join 替代 sleep_ms + _notify_tid 保存 | 383→389 | 341→347 |
| `Drivers/actuator/PWM_LED.py` | 移除未使用 import | 266→265 | 212→211 |
| `Modules/alarm_service.py` | PRIORITY_ALARM 常量替换 | 347→348 | 260→261 |
| `thonny/Modules/control_service.py` | 移除死键 "blink" | 487→486 | — |

---

## 审查建议

1. **上板优先测试 Bug 1** — BLEDriver.deinit() 断开事件缺失影响最大，语音"断开蓝牙"后 BLEService 状态不同步
2. **测试顺序建议**：语音"断开蓝牙" → 语音"蓝牙连接" → 语音"闪烁" → SOS 报警 → 30 分钟稳定性
3. **后续关注**：Bug 6（alarm_service 字符串优先级）是历史遗留，建议全面排查其他 TTS 请求是否也有类似问题
