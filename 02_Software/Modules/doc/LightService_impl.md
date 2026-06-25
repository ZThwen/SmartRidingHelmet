# LightService 实现路径

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-SEN-04 环境光照采集（自适应灯光调节）、F-LIGHT-01 大功率灯光驱动
> **实现状态**：✅ **v1 已实现**（2026-06-11）
> **负责人员**：郑皓文

---

## 1. 模块概述

### 做什么
订阅光照传感器事件，根据环境光照强度**自动调节** PWM LED 亮度。支持自动/手动模式切换，gamma 非线性映射使暗环境更敏感，防抖避免频繁调节。

### 不是什么
- **不是**PWM LED 驱动（那是 `Drivers/actuator/PWM_LED.py` 的事）
- **不是**光照传感器驱动（那是 `Drivers/sensor/Light.py` 的事）
- **不是**碰撞检测或报警联动（那是 CollisionService / AlarmService 的事）

### 一句话
**自适应灯光控制器**：收光照事件 → gamma 映射 → 调 PWM LED 亮度；收到控制指令 → 切换自动/手动模式。

---

## 2. 文件位置

```
02_Software/Modules/light_service.py                     # 本模块
02_Software/Drivers/actuator/PWM_LED.py                  # 先决依赖 — PWM LED 驱动
02_Software/Drivers/sensor/Light.py                      # 先决依赖 — 光照传感器（间接，通过 EventBus）
```

---

## 3. 依赖的 Device 驱动

| 驱动 | 导入路径 | 调用方法 | 用途 |
|:----|:--------|:---------|:-----|
| PWM_LED | `Drivers.actuator.PWM_LED.PWMLEDDriver` | `set_brightness(duty_cycle)` | 设置 LED 亮度（0-100%） |

**注意**：LightService 不创建 PWM LED 实例，由主循环创建后通过构造函数注入。

---

## 4. 事件订阅

| 事件 | 回调方法 | 做什么 |
|:----|:--------|:-------|
| `EVENT_LIGHT_READY` | `_on_light_ready(payload)` | 光照数据就绪，计算目标亮度并调用 PWM LED |
| `EVENT_LIGHT_CONTROL` | `_on_light_control(payload)` | 灯光控制指令（on/off/auto/brightness_up/brightness_down/blink） |
| `EVENT_POWER_STATE_CHANGE` | `_on_config_update(payload)` | 电源状态变化，功耗联动 |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm_triggered(payload)` | 报警触发 → level >= 3 时自动启动 PWM 闪烁 |
| `EVENT_ALARM_CANCELED` | `_on_alarm_canceled(payload)` | 报警取消 → 停止闪烁 |

---

## 5. 事件发布

| 事件 | 携带数据 | 发布时机 |
|:----|:--------|:--------|
| `EVENT_LIGHT_BLINK_STATE` | `{blink: bool, duty: int}` | 闪烁状态变更时（开/关/报警触发/取消） |

---

## 6. 核心算法

### 6.1 Gamma 非线性映射

GL5528 光敏电阻特性：ADC 值大 → 光照弱，ADC 值小 → 光照强。

```
光照强度 (ADC)
├── ≤ 30000 (白天阈值)     → brightness = 0（灯不开）
├── 30000 ~ 50000 (过渡期)  → normalized = (adc - day) / (night - day)
│                           → brightness = min + (max - min) × pow(normalized, gamma)
└── ≥ 50000 (晚上阈值)     → brightness = max（灯最亮）
```

**gamma = 1.5**：暗环境（normalized 接近 1）时亮度变化更明显，符合人眼感知。

### 6.2 防抖机制

- **亮度变化阈值**：亮度变化 < 3% 时不调节（`LIGHT_BRIGHTNESS_THRESHOLD`）
- **时间防抖**：两次调节间隔 < 50ms 时跳过（`LIGHT_DEBOUNCE_MS`）

### 6.3 模式切换

| 模式 | 触发方式 | 行为 |
|:----|:--------|:-----|
| **自动** | 默认 / `set_auto_mode()` / `EVENT_LIGHT_CONTROL{auto}` | 根据光照事件自动调节 |
| **手动** | `set_manual_brightness(duty_cycle)` / `EVENT_LIGHT_CONTROL{on/off/brightness_up/down}` | 覆盖自动调节，固定亮度 |
| **闪烁** | `EVENT_LIGHT_CONTROL{blink}` / `EVENT_ALARM_TRIGGERED`（level≥3） | PWM 以 500ms 间隔闪烁（占空比 20%） |

---

## 7. 配置参数表

| 常量 | 默认值 | 说明 |
|:-----|:-------|:-----|
| `LIGHT_DAY_ADC_THRESHOLD` | 30000 | 白天阈值（ADC 值 < 此值 → 光照强 → 灯不开） |
| `LIGHT_NIGHT_ADC_THRESHOLD` | 50000 | 晚上阈值（ADC 值 > 此值 → 光照弱 → 灯最亮） |
| `LIGHT_BRIGHTNESS_MIN` | 5 | 最小亮度（%） |
| `LIGHT_BRIGHTNESS_MAX` | 50 | 最大亮度（%），18W 灯散热限制 |
| `LIGHT_GAMMA` | 1.5 | 非线性映射参数（>1 时暗环境更敏感） |
| `LIGHT_BRIGHTNESS_THRESHOLD` | 3 | 亮度变化阈值（小于此值不调节） |
| `LIGHT_DEBOUNCE_MS` | 50 | 防抖间隔（ms） |
| `LIGHT_BRIGHTNESS_STEP` | 5 | 亮度调节步长（PWM 单位，5/50=10% 显示） |

---

## 8. 数据快照

```python
get_data() → {
    "current_brightness": 25,    # 当前亮度（%）
    "light_intensity": 42000,    # 当前光照强度（ADC 值）
    "mode": "auto",              # "auto" 或 "manual"
    "light_level": "transition", # "day" / "transition" / "night"
    "timestamp": 12345678
}
```

---

## 9. 电源模式行为

| 电源模式 | LightService 行为 |
|:--------|:------------------|
| ACTIVE | 正常自动调节 |
| SUSPENDED | 停止自动调节（`power_state != ACTIVE` 时跳过） |
| EMERGENCY | 停止自动调节 |

---

## 10. 实现步骤

### 阶段 A：定义四元组
1. `cfg`：阈值、gamma、防抖参数
2. `ctx`：is_init、power_state、auto_mode、manual_brightness、last_brightness
3. `_data`：current_brightness、light_intensity、mode、light_level

### 阶段 B：实现 init()
1. 订阅 `EVENT_LIGHT_READY`、`EVENT_LIGHT_CONTROL`、`EVENT_POWER_STATE_CHANGE`、`EVENT_ALARM_TRIGGERED`、`EVENT_ALARM_CANCELED`
2. 设置 `is_init = True`

### 阶段 C：实现核心算法
1. `_calculate_brightness(light_intensity)` → gamma 映射
2. `_on_light_ready()` → 阈值检查 + 防抖 + 调用 PWM LED
3. `_on_light_control()` → 模式切换 / 手动亮度 / blink 指令处理
4. `_on_alarm_triggered()` → SOS（level≥3）自动启动闪烁
5. `_on_alarm_canceled()` → 停止闪烁

### 阶段 D：实现辅助方法
1. `set_manual_brightness(duty_cycle)` → 手动模式
2. `set_auto_mode()` → 恢复自动
3. `_publish_blink_state()` → 发布 `EVENT_LIGHT_BLINK_STATE`（供 ControlService 缓存闪烁状态）
4. `get_data()` / `get_status()` → 数据快照

---

## 11. 约束规则

| 规则 | 说明 |
|:----|:-----|
| **tick 为空** | 纯事件驱动，不需要周期调度 |
| **亮度上限 50%** | 18W 灯散热限制，`LIGHT_BRIGHTNESS_MAX` 控制 |
| **非 ACTIVE 模式不调节** | power_state != ACTIVE 时跳过自动调节 |
| **手动覆盖自动** | 手动设置后切换为手动模式，需显式调用 `set_auto_mode()` 恢复 |
| **闪烁冲突处理** | 报警触发闪烁时拒绝任何灯光指令；手动闪烁可被开灯/关灯/调亮度覆盖 |
| **闪烁保护** | 亮时占空比固定 20%，间隔 500ms，保护大功率 LED |
| **PWM LED 异常容错** | 连续失败才上报错误，单次失败不阻塞 |
