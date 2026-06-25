# AlarmService 实现路径

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-ALM-01 碰撞自动报警、F-ALM-02 一键SOS求助、F-ALM-03 本地声光报警
> **实现状态**：✅ **v2 已实现**（2026-06-25 新增 SMS/静默报警/心率异常/ControlService 远端控制）
> **负责人员**：郑皓文

---

## 1. 模块概述

### 做什么
接收碰撞事件、SOS 按键事件、低电量事件、GPS 丢失事件，**协调** LED、Audio 两个 Device 驱动完成报警联动，管理报警超时，发布报警状态事件通知其他 Service。

### 不是什么
- **不是**直接操作硬件（LED/Audio 是 Device 层的事）
- **不是**碰撞检测算法（那是 CollisionService 的事）
- **不是**云端推送（那是 CloudService 的事，AlarmService 只管发布 `EVENT_ALARM_TRIGGERED`）

### 一句话
**事件驱动的报警编排器**：收到事件 → 调 Device 接口 → 启动/刷新计时器 → 发布结果事件。

---

## 2. 文件位置

```
02_Software/Modules/alarm_service.py
```

参考模板：`Service_Template.py`

---

## 3. 依赖的 Device 驱动

| 驱动 | 导入路径 | 调用方法 |
|:----|:--------|:---------|
| LED | `Drivers.actuator.LED.LEDDriver` | `led.blink(duration_ms, interval_ms)` / `led.on()` / `led.off()` |
| Audio | `Drivers.actuator.Audio.AudioDriver` | `audio.play_file(path)` / `audio.play_tts(text)` / `audio.stop()` |

**注意**：AlarmService 不创建这些驱动实例，由主循环创建后通过构造函数注入。
LCD 报警画面由 DisplayService 负责，AlarmService 不再直接操作 LCD。

---

## 4. 事件订阅

在 `init()` 中完成订阅：

| 事件 | 回调方法 | 触发时机 | 本模块做什么 |
|:----|:--------|:--------|:-----------|
| `EVENT_COLLISION_DETECTED` | `_on_collision(payload)` | CollisionService 检测到碰撞 | 判断等级 → 启动碰撞报警流程 |
| `EVENT_BUTTON_PRESSED` | `_on_button_press(payload)` | 用户按下按键 | **空闲→SOS 触发** / **报警中→取消报警**（状态依赖双语义） |
| `EVENT_BATTERY_LOW` | `_on_battery_low(payload)` | PowerService 检测到低电量 | 当前为 stub |
| `EVENT_BATTERY_CRITICAL` | `_on_battery_critical(payload)` | PowerService 检测到严重低电量 | 当前为 stub |
| `EVENT_GPS_LOST` | `_on_gps_lost(payload)` | GNSS 连续无定位 | TTS 播报"GPS信号已丢失" |
| `EVENT_CONFIG_UPDATE` | `_on_config_update(payload)` | 云端配置下发 | 更新报警时长等参数 |
| `EVENT_ALARM_CONTROL` | `_on_alarm_control(payload)` | ControlService 远端控制 | 路由 cancel/sos/stealth 指令 |
| `EVENT_HEARTRATE_READY` | `_on_heartrate(payload)` | HeartRate 数据就绪 | 心率异常时 TTS 提醒（不触发报警） |
| `EVENT_SMS_PHONE_CONFIG` | `_on_sms_phone_config(payload)` | BLE 配置手机号 | 存储紧急联系人手机号 |
| `EVENT_GNSS_READY` | `_on_gnss(payload)` | GNSS 定位数据就绪 | 缓存坐标供 SMS 发送时使用 |

---

## 5. 事件发布

| 事件 | 携带数据 | 发布时机 |
|:----|:--------|:--------|
| `EVENT_ALARM_TRIGGERED` | `{alarm_type, level, timestamp}` | 碰撞/SOS/静默报警启动时 |
| `EVENT_ALARM_CANCELED` | `{duration, timestamp}` | 报警超时自动取消或手动取消时 |
| `EVENT_TTS_REQUEST` | `{text, priority}` | 报警启动时播报 TTS（priority=PRIORITY_ALARM） |

`EVENT_ALARM_TRIGGERED` 被 BLEService 订阅，用于通知手机端小程序。

---

## 6. 内部状态机

```
IDLE ──收到碰撞/SOS事件──> ALARMING
 │                            │
 │                            ├── 30s 超时 ──> IDLE (发布 ALARM_CANCELED)
 │                            │
 │                            ├── SW按钮（报警中）──> IDLE (发布 ALARM_CANCELED)
 │                            │
 │                            ├── SOS 打断碰撞 ──> 重启 SOS 流程
 │                            │
 │                            ├── 同类型 level<3 ──> 刷新 30s 计时器
 │                            │
 │                            └── 同类型 level=3 ──> 升级为 SOS
```

### 四元组关键字段

```
ctx:
  "is_init":       False           # 初始化完成标志
  "last_tick":     0               # 上次 tick 时间戳
  "power_state":   "ACTIVE"        # 当前电源模式
  "alarm_active":  False           # 当前是否在报警中
  "alarm_type":    ""              # 当前报警类型: collision / sos / stealth / ""
  "alarm_level":   0               # 当前碰撞等级 1-3（仅碰撞）
  "alarm_start":   0               # 报警开始时间戳（用于超时判断）
  "hr_alert_tick": 0               # 上次心率异常 TTS 时间戳（防抖）

sms 缓存:
  "_sms_phone":    None            # 配置的紧急联系人手机号（从 BLE 接收）
  "_gnss_cache":   {}              # 缓存最新 GNSS 坐标（供 SMS 使用）

_data:
  "last_alarm":    {}              # 最近一次报警的快照
```

---

## 7. 实现步骤（按顺序）

### 步骤 1：搭骨架
1. 复制 `Service_Template.py`，重命名为 `AlarmService.py`
2. 改类名为 `AlarmService`，改 `self.name = "alarm"`
3. 导入 config 事件常量、BaseModule
4. 定义 cfg/ctx/_data 四元组

### 步骤 2：实现 init()
1. 设置 `is_init = True`
2. 订阅 10 个事件（见第 4 节）
3. 初始化 ctx 中的报警状态
4. 打印 `[alarm] OK init`

### 步骤 3：实现 tick()
1. 时间片控制：用 `check_interval_ms` 防止高频空转
2. **超时检查**：如果 `alarm_active == True` 且 `alarm_type == "collision"` 且超过 30s，调用 `_cancel_alarm()`（SOS 和 stealth 需手动取消）

### 步骤 4：实现碰撞回调 `_on_collision(payload)`
1. 提取 `level`、`acc_total`
2. 调用 `_start_alarm("collision", level)`
3. **打断规则**：如果当前是碰撞报警且收到 SOS，由 `_on_button_press` 处理，本方法不负责打断

### 步骤 5：实现 SOS 回调 `_on_button_press(payload)`
1. **打断规则**：如果当前正在执行碰撞报警，先停止碰撞相关操作，切换为 SOS 流程
2. 调用 `_start_alarm("sos", 3)`

### 步骤 6：实现 `_start_alarm(alarm_type, level)`
核心报警启动方法，所有报警入口都走这里：
1. 判断状态：
   - 同类型且 level<3 → 仅刷新超时计时器
   - Level 3 碰撞 → 升级为 sos（让 CloudService 按 SOS 推送）
   - SOS 打断碰撞 → 先 cancel 再重启 SOS
2. 判断类型调 Device：
   - `collision` → `led.blink(ALARM_DURATION_MS, level_to_interval(level))` + `audio.play_file(level_to_file(level))`
   - `sos` → `led.blink(ALARM_DURATION_MS, 200)` + `audio.play_file(AUDIO_SOS_FILE)`
3. 发布 `EVENT_ALARM_TRIGGERED`
4. 启动/刷新 30s 超时计时器
5. 更新 ctx 报警状态

### 步骤 7：实现 `_cancel_alarm()`
1. `led.off()`
2. `audio.stop()`
3. 发布 `EVENT_ALARM_CANCELED`
4. 重置 ctx 报警状态（alarm_active=False, alarm_type="", alarm_level=0）

### 步骤 8：实现辅助映射

```
level_to_interval(level):
  1 → 1000ms
  2 → 500ms
  3 → 200ms

level_to_file(level):
  1 → AUDIO_ALARM_FILE_L1
  2 → AUDIO_ALARM_FILE_L2
  3 → AUDIO_ALARM_FILE_L3
```

### 步骤 9：实现低电量、GPS 丢失回调（TTS 播报）
- `_on_battery_low()` → `audio.play_tts(TTS_BATTERY_LOW)`
- `_on_battery_critical()` → `audio.play_tts(TTS_BATTERY_CRITICAL)`
- `_on_gps_lost()` → `audio.play_tts(TTS_GPS_LOST)`

### 步骤 10：实现 get_data()、get_status()
按四元组规范返回数据快照。

### 步骤 11：实现公开接口与扩展方法

**`cancel_alarm()`**：公开取消接口，供 ControlService 远端调用，内部委托 `_cancel_alarm()`。

**`trigger_sos()`**：公开 SOS 触发接口，供 ControlService 远端调用，内部调用 `_start_alarm("sos", 3)`。

**`trigger_stealth_alarm()`**：静默报警模式。无 LED 无声音，仅发布 `EVENT_ALARM_TRIGGERED`（alarm_type="stealth"）供 BLEService 通知手机端。触发前先取消已有报警。

### 步骤 12：实现事件路由回调

**`_on_alarm_control(payload)`**：接收 ControlService 的报警控制指令，路由到对应方法：
- `cmd="cancel"` → `cancel_alarm()`
- `cmd="sos"` → `trigger_sos()`
- `cmd="stealth"` → `trigger_stealth_alarm()`

**`_on_heartrate(payload)`**：心率异常 TTS 提醒。检查 hr/spo2 是否超阈值，有冷却时间防抖（`HEARTRATE_ALERT_COOLDOWN_MS`）。报警中不触发。

**`_on_sms_phone_config(payload)`**：接收 BLE 下发的紧急联系人手机号，校验 11 位后存储。

**`_on_gnss(payload)`**：缓存最新 GNSS 坐标，供 SMS 发送时构建高德地图链接。

### 步骤 13：实现 SMS 辅助方法

**`_build_sms_message(level)`**：构建 SMS 内容。有 GPS 时附带高德地图链接（WGS84→GCJ02 坐标转换），无 GPS 时仅发送等级。

**`_wgs84_to_gcj02(lng, lat)`**：WGS84 坐标系转 GCJ02（火星坐标系），适配高德地图。

---

## 8. 约束规则（必须遵守）

| 规则 | 说明 |
|:----|:-----|
| **优先级** | SOS > 碰撞。SOS 事件到达时，无论当前状态如何，立即切换到 SOS 流程 |
| **手动取消** | 报警中按下 SW 按钮 = 取消报警（不需要长按，状态依赖：AlarmService 检查自身 alarm_active 决定 SOS 或 Cancel） |
| **重复触发** | 同类型报警期间收到新触发 → 只刷新 30s 计时器，不重新播放报警音（Level 3 碰撞除外） |
| **等级联动** | Level 3 碰撞 → 发布 `EVENT_ALARM_TRIGGERED` 时 `alarm_type` 标注为 `sos` 级别，让 BLEService 按 SOS 通知手机 |
| **不操作硬件** | 所有硬件交互必须通过调用 Device 驱动公共接口，不 import machine、quectel |
| **tick() < 5ms** | tick() 只做超时检查，不做重操作 |
| **回调不阻塞** | 所有 _on_xxx 回调不能有 sleep、不能有阻塞 I/O |

---

## 9. 需要从 config.py 引用的常量

```python
from core.config import (
    # 事件
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_COLLISION_DETECTED, EVENT_BUTTON_PRESSED,
    EVENT_BATTERY_LOW, EVENT_BATTERY_CRITICAL, EVENT_GPS_LOST,
    EVENT_CONFIG_UPDATE, EVENT_ALARM_CONTROL, EVENT_POWER_STATE_CHANGE,
    EVENT_SMS_PHONE_CONFIG, EVENT_GNSS_READY,
    EVENT_HEARTRATE_READY, EVENT_TTS_REQUEST,
    # 配置
    ALARM_DURATION_MS, ALARM_ENABLE_LOCAL,
    AUDIO_ALARM_FILE_L1, AUDIO_ALARM_FILE_L2, AUDIO_ALARM_FILE_L3,
    AUDIO_SOS_FILE,
    TTS_BATTERY_LOW, TTS_BATTERY_CRITICAL, TTS_GPS_LOST,
    # 功耗
    POWER_STATE_ACTIVE,
    # TTS 优先级
    PRIORITY_ALARM, PRIORITY_CTRL,
    # 心率阈值与 TTS
    HEARTRATE_HIGH_THRESHOLD, HEARTRATE_LOW_THRESHOLD,
    HEARTRATE_SPO2_LOW_THRESHOLD,
    HEARTRATE_TTS_HIGH, HEARTRATE_TTS_LOW, HEARTRATE_SPO2_TTS_LOW,
    HEARTRATE_ALERT_COOLDOWN_MS,
)

---

## 10. 开发中遇到的问题

### 10.1 构造注入缺少 None guard

**现象**：测试时传入 `led=None` 后 `_start_alarm()` 直接崩溃。

**原因**：`self.led.blink()` 和 `self.audio.play_file()` 没有判空保护。

**解决**：所有 Device 调用前加 `if self.led:` / `if self.audio:` 保护。构造签名 `AlarmService(event_bus, led=None, audio=None, sms=None)` 明确允许 None。

### 10.2 Level 3 碰撞升级逻辑放错位置

**现象**：首次 Level 3 碰撞触发后 `alarm_type` 仍然是 `"collision"`，没有升级为 `"sos"`。

**原因**：`if level >= 3: alarm_type = "sos"` 放在了 `if self.ctx["alarm_active"]:` 内部。首次触发时 `alarm_active=False`，整个块被跳过。

**解决**：将 Level 3 升级逻辑移到函数最前面，独立于 `alarm_active` 状态执行。

### 10.3 按钮双语义在测试中导致场景串扰

**现象**：E2E 测试场景 2（SOS 触发）按下按钮后 `alarm_active=True`，但场景 3（取消）再按时走到了 Cancel 而非预期的 SOS。

**原因**：按钮语义是**状态依赖**的（IDLE→SOS, ALARMING→Cancel）。场景过渡时没有清理状态 + 排空事件队列，旧事件污染了新场景。

**解决**：每个 E2E 场景前调用 `svc._cancel_alarm()` + `pump_loop()` 清理状态和队列。

### 10.4 time.sleep() 阻塞导致 tick() 超时失效

**现象**：`cfg["alarm_duration_ms"]=8000` 但报警 15s 后仍未自动取消。

**原因**：E2E 测试中使用 `time.sleep()` 等待观察，期间主线程完全阻塞，`tick()` 不运行，超时检查永远不会触发。

**解决**：使用 `pump_sleep(event_bus, svc, ms)` 替代 `time.sleep()`，它在等待期间持续调用 `svc.tick()` + `event_bus.pump()`。

### 10.5 无音频文件时 play_file 静默失败

**现象**：`audio.play_file("SD:alarm_l2.mp3")` 返回 `+CME ERROR: 905`（文件不存在）。

**影响**：LED 报警正常，音频需要补文件。当前 TTS 通道可用。

**当前方案**：E2E 测试中额外调用 `audio.play_tts(...)` 替代验证音频输出。正式部署需在 SD 卡放入对应文件。

---

## 11. 测试验证状态

### 11.1 已测试通过（2026-05-18 E2E 真机）

| 测试项 | 结果 | 说明 |
|:------|:----|:------|
| 碰撞报警 Level 1-3 | ✅ | LED 按等级闪烁 (1000/500/200ms)，超时自动取消 |
| Level 3 升级 SOS | ✅ | `alarm_type` 标记为 `sos`，LED 200ms 快速闪烁 |
| SOS 按钮触发 | ✅ | 空闲时按 SW 按钮 → LED 200ms 闪烁 + Audio TTS |
| 报警中按钮取消 | ✅ | ALARMING 时按 SW 按钮 → LED 灭、Audio 停 |
| 同类型重复触发刷新 | ✅ | 已报警时同类型事件只刷新 30s 计时器 |
| 30s 超时自动取消 | ✅ | tick() 轮询检测超时后取消 |
| GPS 丢失 TTS | ✅ | `_on_gps_lost` → `audio.play_tts(TTS_GPS_LOST)` |
| 主循环 30s 稳定性 | ✅ | 无崩溃、无内存泄漏（2999 tick/模块） |
| 电池事件 stub | ✅ | `_on_battery_low/critical` 不抛异常 |

### 11.2 未测试 / 待验证

| 待测项 | 优先级 | 说明 |
|:------|:-----:|:------|
| 碰撞事件从 CollisionService 真实链路 | 高 | CollisionService ✅ 已完成，碰撞→报警链路已验证 |
| 音频文件部署 | 高 | `SD:alarm_l1.mp3` / `l2.mp3` / `l3.mp3` / `sos.mp3` 需放入 SD 卡 |
| 长时间运行稳定性 | 中 | E2E 只跑了 30s，未验证数小时 |
| 功耗切换 | 中 | `power_state=SUSPENDED` 时 tick 跳过，但未真机验证低功耗 |

### 11.3 后续可调整的内容

| 可调整项 | 原因 |
|:---------|:------|
| 报警时长 | `cfg["alarm_duration_ms"]` 随时可改，云端可通过 `EVENT_CONFIG_UPDATE` 下发 |
| LED 闪烁间隔 | `_level_to_interval()` 映射表可调整 |
| 报警音频文件 | `AUDIO_ALARM_FILE_L1` 等 config 常量可更换路径 |
| TTS 文本 | `TTS_BATTERY_LOW` 等常量可修改播报内容 |
| 按钮语义 | 当前状态依赖（IDLE→SOS, ALARMING→Cancel），可扩展为配置 |
| 电池回调 | `_on_battery_low/critical` 当前为 stub，PowerService 就绪后填写 TTS 播报 |
```
