# Bug 审计与修复报告 — 碰撞报警 / BLE / LCD / 传感器综合修复

> **日期**：2026-06-25
> **范围**：BLE Driver / BLEService / ControlService / AlarmService / AudioService / DisplayService / IMU Driver / Temp_Humid Driver / LCD Driver
> **审计方式**：代码审查 + 逐模块链路验证 + 硬件测试

---

## 修复清单

| # | 严重度 | 模块 | Bug | 状态 |
|---|--------|------|-----|:----:|
| 1 | 🔴 致命 | BLE Driver | BLE `init()` 在开机时自动广播，且 `connect()` 未完整配置 GATT 特征值 | ✅ 已修复 |
| 2 | 🔴 致命 | BLEService | 手机断连后 `_on_disconnected` 调 `restart()`，导致 BLE 栈重启 | ✅ 已修复 |
| 3 | 🔴 致命 | ControlService | 语音"蓝牙连接"用 `is_init` 判断，断连后无法恢复广播 | ✅ 已修复 |
| 4 | 🔴 致命 | AlarmService | 碰撞报警只播 SD 卡 MP3，无 TTS 语音播报 | ✅ 已修复 |
| 5 | 🔴 致命 | AudioService | 报警期间 TTS 不循环，只播一次 | ✅ 已修复 |
| 6 | 🔴 致命 | DisplayService | 开机动画期间数据显示叠加；报警动画期间数据显示叠加 | ✅ 已修复 |
| 7 | 🔴 致命 | DisplayService | 省电/紧急模式进入时不清屏，上一次画面残留 | ✅ 已修复 |
| 8 | 🔴 致命 | AlarmService | 静默报警不发送 SMS | ✅ 已修复 |
| 9 | 🔴 致命 | IMU Driver | I2C 总线死锁后持续重试，造成死循环 | ✅ 已修复 |
| 10 | 🔴 致命 | Temp_Humid Driver | I2C 总线死锁后持续重试，造成死循环 | ✅ 已修复 |

---

## Bug 详情

---

### Bug 1：BLE `init()` 自动广播且 `connect()` 缺少 GATT 特征值配置

| 项目 | 内容 |
|------|------|
| **文件** | `Drivers/network/BLE.py:94`（init）`Drivers/network/BLE.py:178-195`（connect） |
| **发现方式** | 用户测试：BLE 扫描不到设备；蓝牙调试工具显示无特征值 |
| **根因** | `init()` 包含 `self._ble.advertise()`，开机即广播。`connect()` 中 `stop()` → `start()` → `advertise()` 后未重新配置 GATT 特征值（add_character/set_character_value/add_descriptor），手机连接后无法读取特征值，notify 失败（CME ERROR: 53） |
| **触发条件** | 语音"蓝牙连接"指令 |
| **影响** | BLE 可被发现但无法连接或连接后无法传输数据（notify 全部返回 -6） |
| **修复** | 1）`init()` 中删除 `self._ble.advertise()`，只做硬件初始化和 GATT 配置；2）`connect()` 重写为：已初始化时先 `stop()` 清理 → 调 `init()` 完整重新配置 GATT → 再 `advertise()` |
| **验证** | 蓝牙调试工具能扫描到设备且看到 4 个特征值通道，小程序能连接并收到数据 |

---

### Bug 2：BLEService 断连后重启 BLE 栈

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/ble_service.py:228-235` |
| **发现方式** | 代码审查：`_on_disconnected` 中调 `self._ble.restart()` |
| **根因** | BLEService 作为"服务"层不应执行"控制"操作。`restart()` 在服务层被调用会导致：1）语音"蓝牙断开"后 BLE 自动重启；2）`restart()` 内部 `deinit()` 可能触发二次断连事件 |
| **触发条件** | BLE 断连事件触发 |
| **影响** | 语音"蓝牙断开"失效（BLE 立即重启）；潜在 BLE 实例泄漏 |
| **修复** | `_on_disconnected` 只更新状态（`ble_connected=False`）和清空队列，不调任何控制操作 |
| **验证** | 语音"蓝牙断开"后 BLE 彻底关闭 |

---

### Bug 3：语音"蓝牙连接"断连后无效

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/control_service.py:433-441` |
| **发现方式** | 用户测试：说"蓝牙连接"后 TTS 回复"正在连接"但实际无操作 |
| **根因** | `_ble_connect()` 用 `is_init` 判断是否重启。断连后 `is_init=True`（BLE 栈仍在），`restart()` 不执行。改为调 `ble_driver.connect()`，由 BLE 内部判断是否需要 init |
| **触发条件** | BLE 断连后用户语音"蓝牙连接" |
| **影响** | 语音指令无效，用户无法手动恢复 BLE |
| **修复** | 调 `ble_driver.connect()` 替代 `restart()`，connect 内部判断 `is_init` 并执行完整初始化流程 |
| **验证** | 语音"蓝牙连接"后 BLE 正常广播，手机可连接 |

---

### Bug 4：碰撞报警无 TTS

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/alarm_service.py:150-161` |
| **发现方式** | 用户测试：碰撞报警触发后无语音播报 |
| **根因** | `_start_alarm("collision")` 只调 `audio.play_file("SD:alarm_lx.mp3")`，不发布 `EVENT_TTS_REQUEST`。SD 卡 MP3 文件不可靠（不存在时静默返回 -3） |
| **触发条件** | 碰撞检测触发报警 |
| **影响** | 用户听不到任何报警语音 |
| **修复** | 删除 `audio.play_file()` 和 `audio.play_tts()`，改为统一发布 `EVENT_TTS_REQUEST`，碰撞时 `"碰撞报警，等级X"`，SOS 时 `"SOS报警，请注意安全"` |
| **验证** | 碰撞触发后听到 TTS 语音播报 |

---

### Bug 5：报警 TTS 不循环

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/audio_service.py:95-129` |
| **发现方式** | 代码审查：`tick()` 中无报警 TTS 循环逻辑 |
| **根因** | TTS 只播放一次，报警持续期间无后续播报 |
| **触发条件** | 碰撞/SOS/静默报警触发 |
| **影响** | 用户只听到一次 TTS，持续报警时无持续提醒 |
| **修复** | `AudioService` 添加 `_alarm_tts_text` 和 `_alarm_tts_tick` 状态；`_on_alarm_triggered` 缓存 TTS 文本；`tick()` 每 5 秒重新入队一次报警 TTS；`_on_alarm_canceled` 清除状态和队列 |
| **验证** | 报警期间每隔 5 秒播报一次 TTS，取消后停止 |

---

### Bug 6：LCD 显示冲突

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/display_service.py:160-165, 318-348` |
| **发现方式** | 用户测试：开机动画未消失时数据显示叠加；报警画面与数据显示共存 |
| **根因** | `tick()` 脏标志渲染没有 `display_mode` 守卫。传感器回调在 boot/alarm 期间设 `_dirty=True`，`tick()` 直接调 `_render_normal_screen()` 渲染正常数据在开机动画/报警画面上 |
| **触发条件** | 传感器数据在 boot(2500ms) 或 alarm 期间到达 |
| **影响** | LCD 画面文字叠加，显示混乱 |
| **修复** | 1）`tick()` L160 添加 `self._dirty and self.ctx["display_mode"] == "normal"` 守卫；2）`_render_normal_screen()` 入口添加 `if self.ctx["display_mode"] != "normal": return` 防御性守卫 |
| **验证** | 开机动画无叠加 + 报警画面无叠加 |

---

### Bug 7：省电/紧急模式不进清屏

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/display_service.py:526-532` |
| **发现方式** | 用户测试：语音"省电模式"后 LCD 仍显示上次画面 |
| **根因** | `_on_power_state_change()` 进入非 ACTIVE 模式时只关闭背光，未清除屏幕内容。`tick()` 虽然跳过渲染，但 LCD 像素保留上次画面 |
| **触发条件** | 语音"省电模式"/"紧急模式"/低电量自动省电 |
| **影响** | 省电模式下 LCD 仍显示内容，未达到省电效果 |
| **修复** | `_on_power_state_change()` 非 ACTIVE 分支中，在关背光之前先调 `self.lcd_driver.clear()` 清屏 |
| **验证** | 语音"省电模式"后 LCD 立即清空 |

---

### Bug 8：静默报警不发送 SMS

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/alarm_service.py:248-255` |
| **发现方式** | 用户测试：静默报警触发后无 SMS |
| **根因** | `trigger_stealth_alarm()` 只发布 `EVENT_ALARM_TRIGGERED` 事件，完全不发送 SMS。静默报警无声光，SMS 是唯一远程通知渠道 |
| **触发条件** | 静默报警触发 |
| **影响** | 用户完全不知晓静默报警发生（BLE 未连接时） |
| **修复** | 在 `trigger_stealth_alarm()` 中添加 SMS 发送：`_build_sms_message(1, "stealth")`。同时统一 `_build_sms_message()` 接口，增加 `alarm_type` 参数，SMS 内容从固定的 `"SOS:N"` 变为 `"{alarm_type}:{level}"` |
| **验证** | 静默报警后收到 SMS 内容 `"stealth:1"` |

---

### Bug 9 & 10：IMU / Temp_Humid 传感器死循环重试

| 项目 | 内容 |
|------|------|
| **文件** | `Drivers/sensor/IMU.py:92-138` `Drivers/sensor/Temp_Humid.py:82-135` |
| **发现方式** | 日志分析：IMU 连续出现 `ETIMEDOUT` 超过 1200 次，持续重试无恢复机制 |
| **根因** | I2C 总线死锁后，两个传感器驱动每次 `tick()` 都尝试读取，超时后打印错误，但下次 `tick()` 继续重试，形成死循环 |
| **触发条件** | I2C 总线异常（如 BLE 重连过程中 AT 命令干扰） |
| **影响** | 主循环 CPU 被传感器超时占用（每 tick 55ms × 持续不断），严重挤压其他模块运行时间 |
| **修复** | 添加 `_abandoned` 标志。`tick()` 开头检查，已放弃则直接 return。`except` 中连续错误计数，达到 10 次后设 `_abandoned=True` 并打印放弃日志 |
| **验证** | I2C 异常后传感器失败 10 次即停止重试，主循环恢复正常 |

---

## 未修复的已知问题

| # | 模块 | 问题 | 影响 | 建议修复时间 |
|---|------|------|------|------------|
| 1 | LCD Driver | `set_backlight()` 无硬件 PWM/GPIO 操作，背光物理上从未改变 | 省电模式背光未实际关闭 | 确认背光引脚后修复 |
| 2 | GNSS | `AT+QGPS=1` 未执行，GNSS 一直返回 CME ERROR: 516 | 无定位数据 | 待 GNSS 模块调通 |
| 3 | display/temp_humid | tick() 耗时 60-80ms 的真阻塞未解决 | 主循环被挤压 | 优化 SPI/I2C 访问 |
| 4 | IMU | 磁力计数据读取导致 ~12ms 阻塞 | 主循环被挤压 | 后续优化 |

---

## 修复文件清单

| 文件 | 修复内容 | 源码行数 | Thonny 行数 |
|------|---------|:--------:|:----------:|
| `Drivers/network/BLE.py` | `init()` 去 advertise；`restart()`→`connect()` 重写 | 294 | 238 |
| `Modules/ble_service.py` | `_on_disconnected` 去掉 restart，只更新状态 | 389 | 347 |
| `Modules/control_service.py` | `_ble_connect` 调 `connect()` 替代 `restart()` | 666 | 无变化 |
| `Modules/alarm_service.py` | 碰撞报警 TTS 替代 MP3；静默报警 SMS；`_build_sms_message` 加 `alarm_type` | 485 | 392 |
| `Modules/audio_service.py` | 报警 TTS 每 5 秒循环播报 | 284 | 224 |
| `Modules/display_service.py` | tick() + render 加 `display_mode` 守卫；省电模式清屏 | 585 | 484 |
| `Drivers/sensor/IMU.py` | 连续 10 次失败后放弃 | 183 | 135 |
| `Drivers/sensor/Temp_Humid.py` | 连续 10 次失败后放弃 | 207 | 155 |

---

## 审查建议

1. **上板优先测试** — BLE 连接测试（connect 修复）和碰撞报警 TTS 测试
2. **测试顺序建议**：
   - BLE：语音"蓝牙连接"→ 手机扫描连接 → 小程序接收数据 → 断连 → 重连
   - 报警：触发碰撞 → TTS 播报 → 小程序收到推送 → SMS 接收 → 取消报警
   - LCD：语音"省电模式"→ LCD 清屏 → 触发报警 → 显示报警画面 → 取消报警 → 恢复显示
   - 传感器：观察 I2C 异常后传感器 10 次即停止，不再死循环
3. **后续关注** — 背光硬件控制需确认引脚后实现；GNSS 需单独调试启动流程
