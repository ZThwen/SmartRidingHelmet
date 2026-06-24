# 功能集成报告 — 语音控制扩展 + PWM LED 闪烁

> **日期**：2026-06-24
> **功能**：语音控制扩展（BLE 连接/断开/语音休眠）+ PWM LED 闪烁（手动 + SOS 自动触发）
> **涉及模块**：VoiceDriver、ControlService、LightService、PWM_LEDDriver、BLEDriver、BLEService、AlarmService
> **状态**：✅ 完成

---

## 1. 功能概述

新增 4 条语音指令（0x16-0x19），实现：
- 语音控制蓝牙连接/断开
- 语音控制小洛包休眠/唤醒
- PWM 大功率 LED 闪烁（0%↔20%，保护 LED）
- SOS 报警自动触发 PWM 闪烁
- 闪烁状态通过 BLE 推送到小程序

语音指令总数从 22 条增加到 26 条。

---

## 2. 改动清单

| # | 文件 | 改动类型 | 改动内容 |
|---|------|---------|---------|
| 1 | `core/config.py` | 修改 | 新增 `EVENT_LIGHT_BLINK_STATE` 事件常量、`PWM_BLINK_ON_DUTY`/`PWM_BLINK_INTERVAL_MS` 配置、`VOICE_CMD_MAP` 4 条映射（0x16-0x19）、`CMD_TTS_MAP` 3 条播报 |
| 2 | `Drivers/actuator/PWM_LED.py` | 修改 | 新增 `start_blink()`/`stop_blink()`/`set_blink_duty()`/`is_blink_active()`/`is_blink_from_alarm()` 方法 + `tick()` 闪烁状态机（时间戳比较 + 占空比切换） |
| 3 | `Drivers/network/BLE.py` | 修改 | 新增 `deinit()`/`restart()` 方法 + `deinit()` 发布 `EVENT_BLE_DISCONNECTED` 事件 |
| 4 | `Modules/control_service.py` | 修改 | 新增 `_voice_active` 语音门控、`_ble_connected` BLE 状态缓存、`_blink_active` 闪烁状态缓存 + 4 个 handler（`ble_connect`/`ble_disconnect`/`voice_sleep`/`light_blink`）+ `_push_state()` 新增 `f` 字段 |
| 5 | `Modules/light_service.py` | 修改 | 订阅 `EVENT_ALARM_TRIGGERED`/`EVENT_ALARM_CANCELED` + `_on_light_control` 处理 `cmd:"blink"` + 新增 `_publish_blink_state()`/`_on_alarm_triggered()`/`_on_alarm_canceled()` + 报警闪烁不可被手动指令中断 |
| 6 | `Modules/ble_service.py` | 修改 | `_ctrl_snapshot` 新增 `f` 字段（闪烁状态）+ 使用 `_thread.join()` 安全退出后台线程 |
| 7 | `core/main.py` | 修改 | `ControlService` 注入 `ble_driver` 参数 |
| 8 | `Modules/doc/VoiceDriver_impl.md` | 修改 | 新增 0x16-0x19 指令说明、语音词条表、ASRPRO 烧录说明 |
| 9 | `Modules/doc/ControlService_impl.md` | 修改 | 新增 voice_sleep 门控说明、0x16-0x19 handler 注册表 |
| 10 | `Modules/doc/BLEService_impl.md` | 修改 | 新增 `_ctrl_snapshot` 快照合并推送说明 |

---

## 3. 数据流

### 语音闪烁流

```
ASRPRO UART 0x19
  → VoiceDriver → EVENT_VOICE_CMD{cmd:"light_blink"}
  → ControlService._on_voice_cmd → _execute_cmd
  → EVENT_LIGHT_CONTROL{cmd:"blink"}
  → LightService._on_light_control
    → pwm_led.start_blink() / stop_blink()（toggle）
    → _publish_blink_state() → EVENT_LIGHT_BLINK_STATE{blink:true/false}
  → ControlService._on_light_blink_state
    → _blink_active 缓存
    → _push_state() → EVENT_CONTROL_STATE_CHANGED{t:7,...,f:0/1}
  → BLEService._on_control_state → _ctrl_snapshot["f"]
  → BLEService.tick() → {"t":7,...,"f":1} → BLE Notify → 小程序
```

### SOS 自动闪烁流

```
碰撞 level>=3
  → CollisionService → EVENT_COLLISION_DETECTED{level:3}
  → AlarmService._start_alarm("sos", 3)
  → EVENT_ALARM_TRIGGERED{alarm_type:"sos", level:3}
  → LightService._on_alarm_triggered
    → pwm_led.start_blink(on_duty=20, from_alarm=True)
    → _publish_blink_state() → EVENT_LIGHT_BLINK_STATE
  → ControlService → _push_state() → BLE 推送 f=1
```

### 蓝牙连接/断开流

```
语音 0x17（蓝牙断开）
  → VoiceDriver → EVENT_VOICE_CMD{cmd:"ble_disconnect"}
  → ControlService._execute_cmd → ble_driver.deinit()
  → BLEDriver → EVENT_BLE_DISCONNECTED
  → ControlService._on_ble_disconnected → _ble_connected=False
  → _push_state() → BLE 推送 m=0

语音 0x16（蓝牙连接）
  → VoiceDriver → EVENT_VOICE_CMD{cmd:"ble_connect"}
  → ControlService._execute_cmd → ble_driver.restart()
  → BLEDriver → EVENT_BLE_CONNECTED
  → ControlService._on_ble_connected → _ble_connected=True
  → TTS "蓝牙正在连接"
```

### 语音休眠/唤醒流

```
语音 0x18（voice_sleep）
  → ControlService._execute_cmd → _voice_active=False
  → TTS "好的"
  → 后续非 wake 指令均被门控拦截

语音 wake（0x00）
  → ControlService._execute_cmd → _voice_active=True
  → TTS "小洛包在，有什么指示"
  → 恢复正常指令处理
```

---

## 4. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 闪烁逻辑放哪层 | LightService（Service 层） | 灯光业务逻辑，不应在 Device 层 |
| 报警如何触发闪烁 | 事件驱动（`EVENT_ALARM_TRIGGERED`） | 架构规范：Service 间禁止直接调用 |
| ControlService 如何获取闪烁状态 | 事件订阅（`EVENT_LIGHT_BLINK_STATE`） | 不注入 pwm_led，保持事件驱动 |
| 闪烁中省电模式 | 手动闪烁停止，报警闪烁继续 | 报警优先级高于省电 |
| 闪烁中碰撞报警 | 停止闪烁，执行碰撞流程 | 碰撞报警有自己的 LED 闪烁逻辑 |
| BLE 线程退出 | `_thread.join(tid, 3000)` | 移远新版 SDK 推荐，比 `time.sleep_ms` 可靠 |
| 语音休眠实现方式 | ControlService 内部 `_voice_active` 门控 | 无须修改 VoiceDriver，只拦截指令处理 |
| BLE 连接/断开操作方式 | ControlService 直接调用 `ble_driver` 接口 | 绕过 EventBus，避免事件循环复杂化 |

---

## 5. 阻塞风险

| 风险 | 等级 | 说明 | 缓解措施 |
|------|:----:|------|---------|
| tick() 超时 | 🟢 | PWM_LED.tick() 只比较时间戳 + 设置占空比，<0.1ms | 远低于 5ms 上限 |
| 内存增长 | 🟢 | 无新增动态结构（闪烁状态为固定字段） | 无 |
| 线程安全 | 🟢 | BLEService 后台线程用 `_thread.join` 安全退出 | 与新版 SDK 一致 |
| init 失败 | 🟢 | 闪烁功能依赖 PWM_LED 已初始化 | main.py 有异常捕获跳过 |
| 省电模式冲突 | 🟢 | 闪烁中进入省电模式：手动闪烁停止，报警闪烁继续 | LightService `_on_power_state_change` 已做判断 |
| BLE 驱动重入 | 🟡 | `ble_driver.restart()` 内部调用 `deinit()`+`init()`，存在时序窗口 | 已在 BLEDriver 内部加 try/except 保护 |

---

## 6. 变更数据流

### 新增事件

| 事件 | 发布者 | 订阅者 | 载荷 |
|------|--------|--------|------|
| `EVENT_LIGHT_BLINK_STATE` | LightService | ControlService | `{blink: bool}` |

### 新增/修改订阅

| 模块 | 事件 | 回调 | 用途 |
|------|------|------|------|
| ControlService | `EVENT_LIGHT_BLINK_STATE` | `_on_light_blink_state` | 缓存闪烁状态 + 推送 BLE |
| ControlService | `EVENT_BLE_CONNECTED` | `_on_ble_connected` | 更新 BLE 连接缓存 |
| ControlService | `EVENT_BLE_DISCONNECTED` | `_on_ble_disconnected` | 更新 BLE 连接缓存 |
| LightService | `EVENT_ALARM_TRIGGERED` | `_on_alarm_triggered` | SOS 自动触发 PWM 闪烁 |
| LightService | `EVENT_ALARM_CANCELED` | `_on_alarm_canceled` | 报警取消停止闪烁 |

### 新增语音指令

| Hex | Cmd | 中文语音 | TTS |
|:---:|-----|----------|-----|
| 0x16 | `ble_connect` | "蓝牙连接" | 动态判断（已连接/连接中） |
| 0x17 | `ble_disconnect` | "蓝牙断开" | "蓝牙已断开" |
| 0x18 | `voice_sleep` | "休眠" | "好的" |
| 0x19 | `light_blink` | "闪烁" | "灯光闪烁" |

### BLE 协议变更

```json
{"t":7,"m":0/1,"b":0-100,"v":0-5,"p":0-3,"f":0/1}
```

新增 `f` 字段：闪烁状态（0=关, 1=开）

### ControlService 新增指令 handler

| 指令 | 实现方式 | 行为 |
|------|---------|------|
| `ble_connect` | `self._ble_connect()` | 调用 `ble_driver.restart()`，TTS 播报 |
| `ble_disconnect` | `self._ble_disconnect()` | 调用 `ble_driver.deinit()`，TTS "蓝牙已断开" |
| `voice_sleep` | `self._sleep_voice()` | 设 `_voice_active=False`，TTS "好的" |
| `light_blink` | `self._pub(EVENT_LIGHT_CONTROL, {"cmd":"blink"})` | 转发闪烁指令给 LightService |

---

## 7. 验收标准

| # | 验证项 | 预期结果 | 验证方法 |
|---|--------|---------|---------|
| 1 | 语音"闪烁" | PWM LED 0%↔20% 闪烁，500ms 间隔 | 上板测试 |
| 2 | 再次语音"闪烁" | 停止闪烁 | 上板测试 |
| 3 | SOS 报警 | PWM LED 自动闪烁，不可被手动指令中断 | 上板测试 |
| 4 | 报警取消 | PWM 闪烁停止 | 上板测试 |
| 5 | 语音"蓝牙断开" | BLE 停止广播，TTS "蓝牙已断开" | 上板测试 |
| 6 | 语音"蓝牙连接" | BLE 重新广播，TTS "蓝牙正在连接" | 上板测试 |
| 7 | 语音"休眠" | TTS "好的"，后续指令被忽略 | 上板测试 |
| 8 | 语音"小洛包" | TTS "小洛包在"，恢复接收指令 | 上板测试 |
| 9 | BLE 推送 f 字段 | 小程序收到闪烁状态（f=0/1） | BLE 抓包 |
| 10 | 闪烁中省电模式 | 手动闪烁停止，报警闪烁继续 | 上板测试 |
| 11 | 闪烁中碰撞报警 | 停止闪烁，执行碰撞流程 | 上板测试 |
| 12 | 现有功能不受影响 | 原有 22 条指令正常 | 回归测试 |

---

## 8. 回滚方案

| 场景 | 操作 | 影响范围 |
|------|------|---------|
| 整体回滚 | 还原 7 个源文件 + 3 个文档 | 回到 22 条指令状态 |
| 仅回滚闪烁 | 还原 PWM_LED.py + light_service.py | 闪烁功能不可用，其他正常 |
| 仅回滚语音扩展 | 还原 config.py VOICE_CMD_MAP + control_service.py | 0x16-0x19 不可用 |
| 仅回滚 BLE 协议 | 还原 ble_service.py `_ctrl_snapshot` + control_service.py `_push_state()` | f 字段不推送，小程序兼容 |

---

## 9. 备注

- ASRPRO 芯片需单独烧录 0x16-0x19 对应的语音词条
- 闪烁参数：占空比 20%（保护大功率 LED），间隔 500ms
- BLE 协议新增 `f` 字段，小程序需适配（JSON 解析忽略未知字段，向后兼容）
- 语音休眠仅拦截指令处理，VoiceDriver 仍正常接收 UART 数据
- `ble_driver.restart()` 的 TTS "蓝牙正在连接" 在 BLEDriver 初始化完成后播报，不阻塞主循环
- 报警闪烁 `from_alarm=True` 标志在 PWM_LED 层维护，LightService 通过 `is_blink_from_alarm()` 检查避免手动指令中断
- 闪烁状态下 PWM LED 自动模式（光照传感器）被暂停，停止闪烁后恢复
