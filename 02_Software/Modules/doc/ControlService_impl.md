# ControlService 实现文档

> **所属层次**：Service 层（业务服务层）
> **实现状态**：✅ v2 已实现（2026-06-12 纯事件驱动架构）
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
| `EVENT_CONTROL_STATE_CHANGED` | `{t:7, m, b}` / `{t:8, v}` / `{t:9, p}` | 状态回推（3 条） |
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

拆分为 3 条消息，每条 ≤25 字节：

| 类型码 | 内容 | 格式 | 示例 |
|:------:|------|------|------|
| t=7 | 灯光 | `{"t":7,"m":0/1,"b":0-100}` | `{"t":7,"m":1,"b":50}` |
| t=8 | 音量 | `{"t":8,"v":0-5}` | `{"t":8,"v":5}` |
| t=9 | 电源 | `{"t":9,"p":0-3}` | `{"t":9,"p":0}` |

编码：m=0 auto/1 manual，p=0 active/1 suspended/2 emergency/3 custom

---

## 7. 传感器缓存

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

## 8. CUSTOM 状态切换

当用户在非 ACTIVE 模式下执行手动操作时，自动切换到 CUSTOM：

```
if cmd 非电源类 and cmd 非查询类:
    if power_mode != "active":
        power_mode = "custom"
        publish EVENT_POWER_STATE_CHANGE{CUSTOM}
```

---

## 9. 报警中 TTS 保护

`_alarm_active` 标志由 EVENT_ALARM_TRIGGERED/CANCELED 维护。查询指令执行前检查：如果 `_alarm_active == True`，不发 TTS，避免 `stop()` 中断报警音频。
