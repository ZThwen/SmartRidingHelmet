# ControlService 实现路径

> **所属层次**：Service 层（业务服务层）
> **实现状态**：✅ v3 已实现（2026-06-18 远端控制全链路测试通过）
> **负责人员**：郑皓文

---

## 1. 模块概述

### 做什么
接收 BLE FFF3 / 语音 UART 的控制指令，发布对应事件到 EventBus，各模块自行订阅响应。同时缓存传感器数据供查询指令使用。

### 不是什么
- **不是**直接操作硬件（LightService/AudioDriver/AlarmService 自己处理）
- **不是**BLE 通信层（BLEDriver 负责）
- **不是**传感器采集（各 Sensor Driver 负责）

### 一句话
**纯事件驱动的指令路由器**：收到指令 → 查表 → 发布事件 → 乐观更新状态 → 回推 BLE。

---

## 2. 文件位置

```
02_Software/Modules/control_service.py
```

---

## 3. 事件订阅清单

| 事件 | 回调 | 用途 |
|------|------|------|
| `EVENT_RIDE_CONTROL` | `_on_ride_control` | BLE FFF3 写入的控制指令 |
| `EVENT_VOICE_CMD` | `_on_voice_cmd` | ASRPRO 语音指令 |
| `EVENT_TEMP_HUMID_READY` | `_on_temp_humid` | 缓存温湿度数据 |
| `EVENT_GNSS_READY` | `_on_gnss` | 缓存速度/位置数据 |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm_triggered` | 标记报警状态（保护 TTS） |
| `EVENT_ALARM_CANCELED` | `_on_alarm_canceled` | 清除报警状态 |

---

## 4. 事件发布清单

| 事件 | payload | 触发时机 |
|------|---------|----------|
| `EVENT_LIGHT_CONTROL` | `{cmd: "on"/"off"/"auto"/"brightness_up"/"brightness_down"}` | 灯光指令 |
| `EVENT_VOLUME_CONTROL` | `{cmd: "up"/"down"}` | 音量指令 |
| `EVENT_ALARM_CONTROL` | `{cmd: "cancel"/"sos"/"stealth"}` | 报警指令 |
| `EVENT_POWER_STATE_CHANGE` | `{power_state: "ACTIVE"/"SUSPENDED"/"EMERGENCY"/"CUSTOM"}` | 电源切换 |
| `EVENT_CONTROL_STATE_CHANGED` | `{t:7, m, b, v, p}` | 状态回推（合并为 1 条） |
| `EVENT_TTS_REQUEST` | `{text: "当前温度28度"}` | 查询结果 TTS 播报 |

---

## 5. 指令表（19 个）

### 5.1 控制指令（13 个）

| 指令 | 发布事件 | 响应模块 | CUSTOM 切换 |
|------|----------|----------|:-----------:|
| `light_on` | EVENT_LIGHT_CONTROL{on} | LightService | ✅ |
| `light_off` | EVENT_LIGHT_CONTROL{off} | LightService | ✅ |
| `brightness_up` | EVENT_LIGHT_CONTROL{brightness_up} | LightService | ✅ |
| `brightness_down` | EVENT_LIGHT_CONTROL{brightness_down} | LightService | ✅ |
| `light_auto` | EVENT_LIGHT_CONTROL{auto} | LightService | ✅ |
| `volume_up` | EVENT_VOLUME_CONTROL{up} | AudioDriver | ✅ |
| `volume_down` | EVENT_VOLUME_CONTROL{down} | AudioDriver | ✅ |
| `alarm_cancel` | EVENT_ALARM_CONTROL{cancel} | AlarmService | ✅ |
| `alarm_sos` | EVENT_ALARM_CONTROL{sos} | AlarmService | ✅ |
| `alarm_stealth` | EVENT_ALARM_CONTROL{stealth} | AlarmService | ✅ |
| `power_save` | EVENT_POWER_STATE_CHANGE{SUSPENDED} | 全系统 | ❌ |
| `power_normal` | EVENT_POWER_STATE_CHANGE{ACTIVE} | 全系统 | ❌ |
| `power_emergency` | EVENT_POWER_STATE_CHANGE{EMERGENCY} | 全系统 | ❌ |

### 5.2 查询指令（6 个）

| 指令 | 数据来源 | TTS 播报 |
|------|----------|----------|
| `query_status` | _control_state | "灯光亮度百分之50，音量3，正常模式" |
| `query_speed` | GNSS cache | "当前时速25公里" |
| `query_temp` | Temp_Humid cache | "当前温度28度" |
| `query_humid` | Temp_Humid cache | "当前湿度百分之65" |
| `query_location` | GNSS cache | "当前位置北纬31.23东经121.47" |
| `query_battery` | N/A | "电量信息暂不可用" |

---

## 6. BLE 回推格式

合并为 1 条消息，≤25 字节：

| 类型码 | 内容 | 格式 | 示例 |
|:------:|------|------|------|
| t=7 | 灯光 + 音量 + 电源 | `{"t":7,"m":0/1,"b":0-100,"v":0-5,"p":0-3}` | `{"t":7,"m":1,"b":50,"v":5,"p":0}` |

编码：m=0 auto/1 manual，v=0-5，p=0 active/1 suspended/2 emergency/3 custom
原理：BLEService 内部维护控制状态快照（_ctrl_snapshot），每收到 `EVENT_CONTROL_STATE_CHANGED` 更新快照字段，tick 周期统一推送 1 条，避免密集指令导致 notify 队列爆炸。

## 7. 指令来源

控制指令支持两个来源，统一走 `_execute_cmd(source)`：

| 来源 | 入口 | 事件 | 触发方式 |
|------|------|------|----------|
| BLE 远端控制 | `EVENT_RIDE_CONTROL` | BLE FFF3 写入 → BLEService buffer → tick 解析 | 手机小程序 |
| 语音指令 | `EVENT_VOICE_CMD` | ASRPRO UART → VoiceDriver tick 轮询 | 语音识别 |
| 按键取消报警 | `EVENT_ALARM_CANCELED` | Button GPIO IRQ → 直接到 AlarmService | 物理按键 |

两者最终都汇聚到 `ControlService._execute_cmd(cmd, source="ble"/"voice")`，状态回推和 TTS 反馈完全统一。

## 8. TTS 反馈机制

所有指令执行后统一触发 TTS 播报（查询指令除外，查询指令的 TTS 由各 `_query_xxx` 方法直接处理）：

```python
def _execute_cmd(self, cmd, source="unknown"):
    ...
    handler()                          # 发布控制事件
    self._update_control_state(cmd)    # 乐观更新状态
    self._push_state()                 # 推送 BLE 回推
    self._maybe_tts(cmd)               # TTS 播报（1s 防抖）
    ...

def _maybe_tts(self, cmd):
    now = _ticks_ms()
    if ticks_diff(now, self._last_tts_tick) < 1000:
        return
    self._last_tts_tick = now
    tts_text = CMD_TTS_MAP.get(cmd)
    if tts_text and self.event_bus:
        self.event_bus.publish(EVENT_TTS_REQUEST, {"text": tts_text})
```

TTS 播报规则：
- 只在有指令控制时回推和播报，其余状态为空闲
- 1 秒防抖：快速连按只播报最终状态
- 报警中 TTS 保护：`_alarm_active == True` 时不发 TTS，避免 `stop()` 中断报警音频
- 静默报警：`CMD_TTS_MAP` 中无 `alarm_stealth` 条目，静默报警不触发 TTS

---

## 9. 状态快照

报警触发时保存控制状态快照，报警取消后恢复：

```python
def _on_alarm_triggered(self, payload):
    self._pre_alarm_state = dict(self._control_state)
    self._alarm_active = True

def _on_alarm_canceled(self, payload):
    self._alarm_active = False
    if self._pre_alarm_state:
        self._control_state.update(self._pre_alarm_state)
        self._pre_alarm_state = None
        self._push_state()  # 推送恢复后的状态到 BLE
```

快照内容：`light_mode`、`light_brightness`、`volume`、`power_mode`。
使用场景：用户在 SUSPENDED 模式手动开灯 → 碰撞报警 → 取消报警 → 灯恢复到手动开灯状态（不是 SUSPENDED 默认关灯）。

---

## 10. 电源模式处理

`power_save` / `power_emergency` 指令执行时，除更新电源状态外，还主动关灯：

```python
elif cmd == "power_save":
    self._control_state["power_mode"] = "suspended"
    self._control_state["light_mode"] = "manual"
    self._control_state["light_brightness"] = 0
    self._pub(EVENT_LIGHT_CONTROL, {"cmd": "off"})
```

`power_normal` 指令只更新电源状态，不自动恢复灯光（用户手动操作）。

---

## 11. 传感器缓存

ControlService 订阅传感器事件，缓存最新数据供查询使用：

```python
self._sensor_cache = {
    "temperature": None,   # from EVENT_TEMP_HUMID_READY.temp
    "humidity": None,      # from EVENT_TEMP_HUMID_READY.humid
    "speed_kmh": None,     # from EVENT_GNSS_READY.speed_kmh
    "latitude": None,      # from EVENT_GNSS_READY.latitude
    "longitude": None,     # from EVENT_GNSS_READY.longitude
}
```

---

## 12. CUSTOM 状态切换

当用户在非 ACTIVE 模式下执行手动操作时，自动切换到 CUSTOM：

```
if cmd 非电源类 and cmd 非查询类:
    if power_mode != "active":
        power_mode = "custom"
        publish EVENT_POWER_STATE_CHANGE{CUSTOM}
```

---

## 13. 报警中 TTS 保护

`_alarm_active` 标志由 EVENT_ALARM_TRIGGERED/CANCELED 维护。`_maybe_tts()` 和 `_tts()` 均检查此标志：如果 `_alarm_active == True`，不发 TTS，避免 `stop()` 中断报警音频。静默报警期间同样阻塞 TTS。

---

## v3 变更记录（2026-06-17）

### 合并 BLE 推送
- `_push_state()` 从 3 条消息合并为 1 条
- 格式：`{"t":7,"m":1,"b":50,"v":5,"p":0}`
- 减少 BLE 传输次数，提高实时性

### TTS 反馈机制
- `_maybe_tts(cmd)` 方法：控制指令 TTS 播报
- 1 秒防抖：快速指令只播报最终状态
- 报警中阻塞：`_alarm_active=True` 时不播报
- 报警取消后恢复：`_on_alarm_canceled` 中播报 "报警已取消"

### 报警快照保存/恢复
- `_pre_alarm_state`：报警前保存状态快照
- `_on_alarm_triggered`：触发时保存当前状态
- `_on_alarm_canceled`：取消时恢复之前状态
- 防止报警覆盖用户设置

### 省电模式自动关灯
- `power_save`：设置 `light_brightness=0` + 发送 `EVENT_LIGHT_CONTROL{off}`
- `power_emergency`：同上
- 确保省电模式下灯关闭

### 手动操作覆盖省电
- 非电源/报警指令在省电模式下执行时
- 自动将 `power_mode` 改为 `custom`
- 发布 `EVENT_POWER_STATE_CHANGE{power_state: CUSTOM}`
