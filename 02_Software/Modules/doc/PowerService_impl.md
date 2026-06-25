# PowerService 实现文档

> **所属层次**：Service 层（业务服务层）
> **实现状态**：✅ v1 已实现（2026-06-23 电池检测全链路测试通过）
> **负责人员**：郑皓文

---

## 1. 模块概述

### 做什么
监听 BatteryDriver 发布的电池电量数据，低电量时自动发布省电模式切换事件和 TTS 通知。为 BLEService 和 ControlService 提供电量数据。

### 不是什么
- **不是** ADC 采样（BatteryDriver 负责）
- **不是**电源模式切换的执行者（各驱动模块自行响应 `EVENT_POWER_STATE_CHANGE`）
- **不是**报警服务（低电量 TTS 直接走 AudioService，不经过 AlarmService）

### 一句话
**电池电量的事件桥梁**：BatteryDriver 采样 → PowerService 判断 → 发布省电/TTS 事件。

---

## 2. 文件位置

```
02_Software/Modules/power_service.py
02_Software/Drivers/sensor/Battery.py    # ADC 驱动
02_Software/core/config.py               # BATTERY_* 常量
```

---

## 3. 事件订阅清单

| 事件 | 回调 | 用途 |
|------|------|------|
| `EVENT_BATTERY_READY` | `_on_battery` | 缓存电量数据，判断低电量 |
| `EVENT_POWER_STATE_CHANGE` | `_on_power_state` | 跟踪电源状态，清除 `auto_suspended` 标记 |

---

## 4. 事件发布清单

| 事件 | 载荷 | 触发时机 |
|------|------|---------|
| `EVENT_POWER_STATE_CHANGE` | `{power_state: POWER_STATE_SUSPENDED}` | `level ≤ auto_suspend_level` 且当前 ACTIVE 且未自动省电过 |
| `EVENT_BATTERY_LOW` | `{level}` | `level ≤ low_level`（2） |
| `EVENT_TTS_REQUEST` | `{text: TTS_BATTERY_LOW, priority: PRIORITY_CTRL}` | 与 `EVENT_BATTERY_LOW` 同时发布 |

---

## 5. 六档电量映射

基于锂电池放电曲线（2.95V-4.2V），经分压（÷1.45）后 ADC 电压 2000-2900mV：

| 档位 | ADC 电压 | 电池电压 | 电量范围 | 含义 |
|------|---------|---------|---------|------|
| 0 | <2000mV | <2.95V | 0% | 没电 / 未接电池 |
| 1 | ≥2000mV | ≥2.95V | <5% | 危急 |
| 2 | ≥2614mV | ≥3.79V | 5-20% | 低（触发自动省电） |
| 3 | ≥2669mV | ≥3.87V | 20-40% | 中等 |
| 4 | ≥2724mV | ≥3.95V | 40-60% | 良好 |
| 5 | ≥2772mV | ≥4.02V | 60%+ | 满 |

阈值常量：`BATTERY_LEVEL_THRESHOLDS = [2000, 2614, 2669, 2724, 2772]`

---

## 6. 自动省电逻辑

```python
def _on_battery(self, payload):
    battery_mv = payload.get("battery_mv", 0)
    level = payload.get("level", 0)
    sample_count = payload.get("sample_count", 0)
    # 未接电池保护
    if battery_mv < 1000:
        return
    # 启动宽限期：前 3 次采样不触发省电
    if sample_count < 3:
        return
    # ...
    if (level <= self.cfg["auto_suspend_level"]      # ≤2 档
            and not self._data["auto_suspended"]      # 未自动省电过
            and self._data["power_mode"] == POWER_STATE_ACTIVE):  # 当前正常模式
        self._data["auto_suspended"] = True
        self.event_bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_SUSPENDED})
        self.event_bus.publish(EVENT_BATTERY_LOW, {"level": level})
        self.event_bus.publish(EVENT_TTS_REQUEST, {"text": TTS_BATTERY_LOW, "priority": PRIORITY_CTRL})

    # 电量回升 → 自动恢复 ACTIVE
    if level > self.cfg["auto_suspend_level"] and self._data["auto_suspended"]:
        self._data["auto_suspended"] = False
        self.event_bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_ACTIVE})
```

**防重复发布**：`auto_suspended` 标记确保低电量只触发一次省电。以下两种情况会清除标记并恢复 ACTIVE：
1. 电量回升到 > `auto_suspend_level`（自动恢复）
2. 用户手动切换到正常模式（通过 ControlService 发布 `EVENT_POWER_STATE_CHANGE(ACTIVE)`）

---

## 7. BatteryDriver 说明

BatteryDriver 遵循 Light.py 的四元组 + ADC 模式：

- **采样间隔**：`BATTERY_SAMPLE_MS = 10000`（10 秒）
- **ADC 引脚**：PC4（ADC1_IN14）
- **电压换算**：`adc_mv = raw * 3300 // 65535`，`battery_mv = int(adc_mv * 1.45)`
- **输出字段**：`{raw, adc_mv, battery_mv, level, valid, timestamp, sample_count}`

---

## 8. BLE 数据推送

BLEService 订阅 `EVENT_BATTERY_READY`，缓存 `level` 到 `_data["latest_battery"]`，在 `_enqueue_merged()` 中加入 `d["bat"]` 字段：

```json
{"t": 0, "d": {"tmp": 25.3, "hum": 60.1, "bat": 4, ...}}
```

---

## 9. 语音查询

ControlService 订阅 `EVENT_BATTERY_READY`，缓存 `level` 到 `_sensor_cache["battery_level"]`。收到 `query_battery` 指令时：

```python
def _query_battery(self):
    level = self._sensor_cache.get("battery_level")
    if level is not None:
        self.event_bus.publish(EVENT_TTS_REQUEST, {
            "text": "当前电量%d档" % level, "priority": PRIORITY_CTRL})
```

---

## 10. 变更记录

| 版本 | 日期 | 内容 |
|------|------|------|
| v1 | 2026-06-23 | 初始版本：六档映射、自动省电、TTS 通知、BLE 推送、语音查询 |
| v2 | 2026-06-25 | 新增电量回升自动恢复 ACTIVE 逻辑 |
