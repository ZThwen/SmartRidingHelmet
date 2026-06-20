# 集成计划 v2 —— 智能骑行头盔 17 模块全系统集成

> **版本**：v2.0  
> **状态**：📋 计划阶段  
> **目标**：将系统从 v1（12 模块，MQTT 云通信）升级到 v2（17 模块，BLE 直连，无云）  
> **数据链路变更**：MQTT/4G 云通信 → **仅 BLE 直连**（ConnectLab 已废弃，数据不上云）

---

## 1. 集成模块清单

### 1.1 模块总表（17 个）

| 编号 | 层级 | 模块名 | 类名 | 文件路径 | v1 已有 | 备注 |
|------|------|--------|------|---------|---------|------|
| S1 | 传感器 | temp_humid | TempHumidDriver | `Drivers/sensor/Temp_Humid.py` | ✅ | AHT20, I2C1, addr 0x38 |
| S2 | 传感器 | imu | IMUDriver | `Drivers/sensor/imu.py` | ✅ | LIS2DH12TR, I2C1, addr 0x19 |
| S3 | 传感器 | gnss | GNSSDriver | `Drivers/sensor/Gnss.py` | ✅ | EC200U 内置 GNSS |
| S4 | 传感器 | light | LightSensorDriver | `Drivers/sensor/Light.py` | ✅ | GL5528, ADC PC5 |
| A1 | 执行器 | button | Button | `Drivers/interface/Button.py` | ✅ | GPIO 'SW', PULL_DOWN |
| A2 | 执行器 | led | LEDDriver | `Drivers/actuator/LED.py` | ✅ | GPIO D3, active-high |
| A3 | 执行器 | audio | AudioDriver | `Drivers/actuator/Audio.py` | ✅ | EC200U audio, 8Ω/800mW |
| A4 | 执行器 | lcd | LCDDriver | `Drivers/actuator/LCD.py` | ✅ | ST7735, SPI1 |
| A5 | 执行器 | pwm_led | PWMLEDDriver | `Drivers/actuator/PWM_LED.py` | ➕ **新增** | PE11, TIM1_CH2, 1000Hz |
| N1 | 网络 | ble | BLEDriver | `Drivers/network/BLE.py` | ➕ **新增** | EC200U BLE 4.2, GATT Server |
| V1 | 接口 | voice | VoiceDriver | `Drivers/interface/Voice.py` | ➕ **阻塞** | ASRPRO UART, 等队友代码 |
| C1 | 服务 | collision | CollisionService | `Modules/collision_service.py` | ✅ | 三级判决算法 |
| C2 | 服务 | alarm | AlarmService | `Modules/alarm_service.py` | ✅ | 声光报警联动 |
| C3 | 服务 | display | DisplayService | `Modules/display_service.py` | ✅ | LCD 画面管理 |
| C4 | 服务 | ble_service | BLEService | `Modules/ble_service.py` | ➕ **新增** | 双线程 BLE 推送 |
| C5 | 服务 | light_service | LightService | `Modules/light_service.py` | ➕ **新增** | 自适应灯光 |
| C6 | 服务 | control_service | ControlService | `Modules/control_service.py` | ➕ **新增** | 统一控制（19 指令） |
| C7 | 服务 | navigation | NavigationService | `Modules/navigation_service.py` | ➕ **新增** | TTS 播报 + LCD 导航 |

### 1.2 已废弃模块（不集成）

| 模块 | 文件 | 废弃原因 |
|------|------|---------|
| CloudService | `Modules/cloud_service.py` | MQTT/4G 云通信已弃用，数据链路改为 BLE 直连 |
| LarkCloudService | `Modules/lark_cloud.py` | 移远云废弃，不再使用 |
| NetworkDriver | `Drivers/network/Network.py` | 仅 CloudService 使用 |
| MQTTDriver | `Drivers/network/MQTT.py` | 仅 CloudService 使用 |
| QthDriver | `Drivers/network/Qth.py` | 移远云 Qth SDK，已废弃 |

### 1.3 未实现模块（暂不集成）

| 模块 | 计划 | 阻塞原因 |
|------|------|---------|
| PowerService | v2 计划 | 等电池硬件 |
| HeartRate | v2 计划 | 等心率传感器硬件 |
| LBS | `Drivers/sensor/LBS.py` | 基站定位，目前需求不明确 |

---

## 2. 依赖关系

### 2.1 构造函数注入依赖

| 模块 | 构造函数参数 | 注入来源 |
|------|-------------|---------|
| TempHumidDriver | `event_bus` | — |
| IMUDriver | `event_bus` | — |
| GNSSDriver | `event_bus` | — |
| LightSensorDriver | `event_bus` | — |
| Button | `event_bus` | — |
| LEDDriver | `event_bus` | — |
| AudioDriver | `event_bus` | — |
| LCDDriver | `event_bus` | — |
| PWMLEDDriver | `event_bus` | — |
| BLEDriver | `event_bus` | — |
| VoiceDriver | `event_bus, uart?` | 等队友确认 |
| CollisionService | `event_bus` | — |
| **AlarmService** | `event_bus, led, audio` | LEDDriver, AudioDriver |
| **DisplayService** | `event_bus, lcd_driver, audio_driver` | LCDDriver, AudioDriver |
| **BLEService** | `event_bus, ble_driver` | BLEDriver |
| **LightService** | `event_bus, pwm_led` | PWMLEDDriver |
| ControlService | `event_bus` | — |
| **NavigationService** | `event_bus, audio_driver, lcd_driver` | AudioDriver, LCDDriver |

### 2.2 事件订阅关系

| 发布者 | 事件 | 订阅者 |
|--------|------|--------|
| **TempHumidDriver** | `EVENT_TEMP_HUMID_READY` | DisplayService, BLEService, ControlService |
| **IMUDriver** | `EVENT_IMU_READY` | CollisionService, BLEService |
| **GNSSDriver** | `EVENT_GNSS_READY` | DisplayService, BLEService, ControlService |
| | `EVENT_GPS_LOST` | AlarmService |
| **LightSensorDriver** | `EVENT_LIGHT_READY` | DisplayService, BLEService, LightService |
| **Button** | `EVENT_BUTTON_PRESSED` | AlarmService |
| **CollisionService** | `EVENT_COLLISION_DETECTED` | AlarmService |
| **AlarmService** | `EVENT_ALARM_TRIGGERED` | DisplayService, BLEService, ControlService, NavigationService |
| | `EVENT_ALARM_CANCELED` | DisplayService, BLEService, ControlService, NavigationService |
| **AudioDriver** | `EVENT_AUDIO_PLAYBACK_START` | —（日志） |
| | `EVENT_AUDIO_PLAYBACK_END` | —（日志） |
| **BLEDriver** | `EVENT_BLE_CONNECTED` | BLEService |
| | `EVENT_BLE_DISCONNECTED` | BLEService |
| **BLEService** | `EVENT_NAV_CMD` | NavigationService |
| | `EVENT_RIDE_CONTROL` | ControlService |
| | `EVENT_BLE_ALARM_ACK` | ⚠️ **无订阅者**（见 8.1） |
| **ControlService** | `EVENT_LIGHT_CONTROL` | LightService |
| | `EVENT_VOLUME_CONTROL` | AudioDriver |
| | `EVENT_ALARM_CONTROL` | AlarmService |
| | `EVENT_TTS_REQUEST` | AudioDriver |
| | `EVENT_POWER_STATE_CHANGE` | DisplayService, NavigationService |
| | `EVENT_CONTROL_STATE_CHANGED` | BLEService |
| | `EVENT_VOICE_CMD` | —（等 VoiceDriver 就绪） |
| **DisplayService** | `EVENT_POWER_STATE_CHANGE` | —（自订阅监控） |

> **注**：事件总线 `publish()` 自动注入 `source` 和 `timestamp` 字段。  
> **订阅者说明**：一些模块（如 TempHumidDriver, IMUDriver）虽然订阅 `EVENT_CONFIG_UPDATE`，但这是通用配置通道，不影响初始化依赖。

---

## 3. 初始化顺序

### 3.1 总顺序（17 模块）

严格按 **传感器 → 执行器 → 网络 → 服务** 顺序初始化：

```
# === 传感器（4）===
temp_humid = TempHumidDriver(event_bus)
imu = IMUDriver(event_bus)
gnss = GNSSDriver(event_bus)
light = LightSensorDriver(event_bus)

# === 执行器（5）===
button = Button(event_bus)
led = LEDDriver(event_bus)
audio = AudioDriver(event_bus)
lcd = LCDDriver(event_bus)
pwm_led = PWMLEDDriver(event_bus)

# === 网络（1）===
ble = BLEDriver(event_bus)

# === 服务（7）===
collision = CollisionService(event_bus)
alarm = AlarmService(event_bus, led=led, audio=audio)
display = DisplayService(event_bus, lcd_driver=lcd, audio_driver=audio)
ble_service = BLEService(event_bus, ble_driver=ble)
light_service = LightService(event_bus, pwm_led=pwm_led)
control = ControlService(event_bus)
navigation = NavigationService(event_bus, audio_driver=audio, lcd_driver=lcd)
```

### 3.2 v1 vs v2 对比

| 层级 | v1（12 模块） | v2（17 模块） | 差异 |
|------|--------------|--------------|------|
| 传感器 | 4 | 4 | 不变 |
| 执行器 | 4 (Button, LED, Audio, LCD) | 5 (+ PWM_LED) | ➕ PWM_LED |
| 网络 | 0 | 1 (+ BLE) | ➕ BLEDriver |
| 服务 | 4 (Collision, Alarm, Cloud, Display) | 7 (+ BLEService, LightService, ControlService, NavigationService) | ➕ 3 服务，−CloudService |

---

## 4. 事件数据流

### 4.1 传感器数据流

```
TempHumid ──EVENT_TEMP_HUMID_READY──→ DisplayService（LCD 显示）
                                       BLEService（BLE 通知手机）
                                       ControlService（查询缓存）

IMU ────────EVENT_IMU_READY─────────→ CollisionService（碰撞判决）
                                       BLEService（数据合并）

GNSS ───────EVENT_GNSS_READY────────→ DisplayService（LCD 显示）
                                       BLEService（BLE 通知手机）
                                       ControlService（查询缓存）

GNSS ───────EVENT_GPS_LOST──────────→ AlarmService（TTS 播报）

Light ──────EVENT_LIGHT_READY───────→ DisplayService（自动背光）
                                       BLEService（数据合并）
                                       LightService（自适应灯光）
```

### 4.2 碰撞报警链

```
IMU ──→ CollisionService（三级判决）
         │
         └──EVENT_COLLISION_DETECTED──→ AlarmService
                                         ├── LED（闪烁）
                                         ├── Audio（报警音）
                                         ├── BLE（手机通知）
                                         ├── Display（报警画面）
                                         └── ControlService（报警前状态快照）
                                         30s 超时 → EVENT_ALARM_CANCELED
                                                   ├── LED（关）
                                                   ├── Audio（停止）
                                                   ├── Display（恢复画面）
                                                   ├── BLE（通知手机）
                                                   └── ControlService（恢复状态）
```

### 4.3 BLE 通信链

```
头盔 → 手机（NOTIFY, FFF1）:
  temp_humid/imu/gnss/light → BLEService._data 缓存
                              ↓ tick() 周期（2s）
                              _enqueue_merged() → send_queue.put(json)
                                                   ↓ _notify_thread（后台线程）
                                                   BLEDriver.notify_data()

手机 → 头盔（WRITE）:
  ┌─ FFF2（导航）──→ BLEService._on_ble_data() → cmd_buffer.put()
  │                    tick() → _parse_and_route() → EVENT_NAV_CMD → NavigationService
  │
  ├─ FFF3（控制）──→ BLEService._on_ble_data() → cmd_buffer.put()
  │                    tick() → _parse_and_route() → EVENT_RIDE_CONTROL → ControlService
  │
  └─ FFF4（报警确认）→ BLEService._on_ble_data() → EVNET_BLE_ALARM_ACK
                       ⚠️ 无订阅者（见 8.1 风险项）
```

### 4.4 控制指令分发

```
BLE FFF3 ──→ ControlService._on_ride_control()
              │
              ├── light_on/off/auto/brightness_up/down
              │     └──EVENT_LIGHT_CONTROL──→ LightService / PWMLEDDriver
              │
              ├── volume_up/down
              │     └──EVENT_VOLUME_CONTROL──→ AudioDriver
              │
              ├── alarm_cancel/sos/stealth
              │     └──EVENT_ALARM_CONTROL──→ AlarmService
              │
              ├── power_save/normal/emergency
              │     └──EVENT_POWER_STATE_CHANGE──→ DisplayService, NavigationService
              │
              └── query_status/speed/temp/humid/location
                    └──EVENT_TTS_REQUEST──→ AudioDriver（TTS）
```

### 4.5 电源模式行为矩阵

| 模式 | TempHumid | IMU | GNSS | LightSensor | PWM_LED | LCD | Audio | BLE |
|------|-----------|-----|------|-------------|---------|-----|-------|-----|
| **ACTIVE** | 2s | 100ms | 2s | 2s | 自动调节 | 正常显示 | 正常 | 实时推送 |
| **SUSPENDED** | 30s | 100ms | 10s | 30s/停止 | 强制关 | 背光关 | TTS 可用 | 推送（降频） |
| **EMERGENCY** | 停止 | 100ms | 10s | 30s/停止 | 强制关 | 背光关 | 仅报警音 | 仅报警推送 |
| **CUSTOM** | 按手动 | 100ms | 按手动 | 按手动 | 手动控制 | 正常 | 正常 | 正常推送 |

---

## 5. 线程模型

### 5.1 主线程（主循环）

```
while True:
    for mod in init_order:          # 所有模块 tick()
        if mod.ctx.get("is_init"):
            mod.tick()
    event_bus.pump()                # 泵事件
    time.sleep_ms(10)               # 10ms 周期
```

**约束**：
- 每个 `tick()` 必须 <5ms 返回，不能阻塞
- `time.sleep_ms(10)` 确保 100Hz 主循环频率
- `event_bus.pump()` 异常隔离：单个模块报错不影响全局

### 5.2 BLEService 后台线程

```
_notify_thread():
    while thread_running:
        data = send_queue.get()          # 阻塞等待
        if ble_connected and len(data) ≤ 244:
            ble.notify_data(data)        # BLE 通知
```

**约束**：
- `send_queue` 是 `ThreadSafeQueue`，线程安全
- 熔断保护：连续 10 次错误 → 暂停 500ms
- 主线程只 `put()`，不直接调用 `notify_data()`
- 最大载荷 244 字节（ATT_MTU 247 - 3）

### 5.3 NavigationService TTS 线程

```
_on_nav_cmd():
    if not is_tts_playing:
        is_tts_playing = True
        _thread.start_new_thread(_tts_thread, (text, driver))

_tts_thread(text, driver):
    driver.play_tts(text)            # 阻塞播放
    is_tts_playing = False           # 恢复标志
```

**约束**：
- `_thread.stack_size(4096)` 减少栈占用
- TTS 播放是阻塞操作，必须子线程
- 防重入：`is_tts_playing` 标志控制

---

## 6. 集成阶段

### 6.1 阶段总览

| 阶段 | 名称 | 内容 | 前置条件 | 产物 |
|------|------|------|---------|------|
| **Phase 0** | v1 基线 | 12 模块回归验证 | — | `test_system_v1.py` ✅ |
| **Phase 1** | Device 层 | 集成 PWM_LED + BLE | Phase 0 | `main_v1_p1.py` |
| **Phase 2** | Service 层 | 集成 LightService + ControlService | Phase 1 | `main_v1_p2.py` |
| **Phase 3** | 通信层 | 集成 BLEService + NavigationService | Phase 2 | `main_v1_p3.py` |
| **Phase 4** | 全系统 | 17 模块 → `main_v2.py` | Phase 3 | `main_v2.py` |
| **Phase 5** | 清理 | 去 debug 打印 → 正式版 | Phase 4 | `main_v2.py`（最终） |
| **Phase 6** | 语音 | VoiceDriver 集成 | 等队友代码 | `main_v2_voice.py` |

### 6.2 Phase 0 — v1 基线回归（已完成 ✅）

**目标**：确认 v1（12 模块）在板子上正常运行。

```
初始化顺序：TempHumid → IMU → GNSS → Light → Button → LED → Audio → LCD
           → Collision → Alarm → Cloud → Display
```

**验证点**：
- 12 模块全部 `is_init=True`
- 主循环 60s 无崩溃
- 传感器数据在合理范围
- `main.py` 保留为回退

**测试文件**：`Tests/test_system_full_v1.py`

### 6.3 Phase 1 — Device 层集成

**目标**：集成 PWM_LED + BLEDriver 两个设备驱动。

**步骤**：
1. 复制 `main.py` → `main_v1_p1.py`
2. 在 LCD 后插入 `pwm_led = PWMLEDDriver(event_bus)`
3. 在 pwm_led 后插入 `ble = BLEDriver(event_bus)`
4. 加入 init_order
5. 加入 tick() 循环
6. 加 debug 打印验证
7. 上传验证无崩溃 → 进入 Phase 2

```python
# Phase 1 新增行
pwm_led = PWMLEDDriver(event_bus)
ble = BLEDriver(event_bus)

init_order = [..., lcd, pwm_led, ble, collision, ...]
```

**验证点**：
- `pwm_led` 初始化成功，PWM 引脚 PE11 正常
- `ble` 初始化成功，手机可搜索到 `SmartHelmet-66ccff`
- 12 + 2 = 14 模块初始化无异常

### 6.4 Phase 2 — Service 层集成

**目标**：集成 LightService + ControlService 两个服务模块。

**步骤**：
1. 复制 Phase 1 产物 → `main_v1_p2.py`
2. 在 BLEDriver 后插入 `light_service = LightService(event_bus, pwm_led=pwm_led)`
3. 在 light_service 后插入 `control = ControlService(event_bus)`
4. 加入 init_order
5. 加入 tick() 循环
6. 加 debug 打印验证事件链：ControlService 发指令 → LightService 响应 → PWM_LED 调光
7. 上传验证无崩溃 → 进入 Phase 3

```python
# Phase 2 新增行
light_service = LightService(event_bus, pwm_led=pwm_led)
control = ControlService(event_bus)

init_order = [..., ble, light_service, control, collision, ...]
```

**关键事件链验证**：
```
发布 EVENT_RIDE_CONTROL({"raw": '{"a":"ctrl","d":{"cmd":"light_on"}}'})
  → ControlService._on_ride_control()
    → _execute_cmd("light_on")
      → EVENT_LIGHT_CONTROL({"cmd": "on"})
        → LightService._on_light_control()
          → pwm_led.set_brightness(50)
```

**验证点**：
- 14 + 2 = 16 模块初始化无异常
- 模拟 BLE 指令 → 灯光响应
- 控制状态回推机制正常

### 6.5 Phase 3 — 通信层集成

**目标**：集成 BLEService + NavigationService。

**步骤**：
1. 复制 Phase 2 产物 → `main_v1_p3.py`
2. 在 control 后插入 `ble_service = BLEService(event_bus, ble_driver=ble)`
3. 在 ble_service 后插入 `navigation = NavigationService(event_bus, audio_driver=audio, lcd_driver=lcd)`
4. 加入 init_order（注意：BLEService 需在 BLE 连接就绪后，NavigationService 需在 Audio/LCD 就绪后）
5. 加入 tick() 循环
6. `BLEService` 启动 `_notify_thread`
7. 加 debug 打印验证 BLE 数据推送
8. 上传验证无崩溃 → 进入 Phase 4

```python
# Phase 3 新增行
ble_service = BLEService(event_bus, ble_driver=ble)
navigation = NavigationService(event_bus, audio_driver=audio, lcd_driver=lcd)

init_order = [..., control, ble_service, navigation]
```

**关键事件链验证**：
```
BLEDriver 连接 → EVENT_BLE_CONNECTED → BLEService
传感器数据就绪 → BLEService._data 缓存 → tick() → send_queue.put() → notify_thread → BLE 通知

BLE FFF2 写入导航指令 → BLEService._on_ble_data() → cmd_buffer → _parse_and_route()
  → EVENT_NAV_CMD → NavigationService → TTS + LCD

BLE FFF3 写入控制指令 → BLEService._on_ble_data() → cmd_buffer → _parse_and_route()
  → EVENT_RIDE_CONTROL → ControlService
```

**验证点**：
- 16 + 2 = 18 模块初始化完成（含 VoiceDriver 占位 = 17 活跃）
- BLE 连接后，手机收到传感器数据通知（t=0，每 2s）
- BLE 心跳包每 5s 发送（t=99）
- 控制指令通过 BLE FFF3 → ControlService 完整链路
- 导航指令通过 BLE FFF2 → NavigationService → TTS
- 两条通信通道（FFF2 导航 + FFF3 控制）互不干扰

### 6.6 Phase 4 — 全系统集成（main_v2.py）

**目标**：创建 `main_v2.py`，完整 17 模块全系统。

**步骤**：
1. 复制 Phase 3 产物 → `main_v2.py`
2. 审查所有 debug 打印
3. 确认 17 模块全部在 init_order 中
4. 确认所有依赖注入参数正确
5. `main.py` 保留不变（v1 回退）
6. 全系统 E2E 测试（9 场景）

**初始化顺序（最终）**：

```
# Phase 4 — main_v2.py 最终初始化顺序
# ─── 传感器（4）───
temp_humid = TempHumidDriver(event_bus)
imu       = IMUDriver(event_bus)
gnss      = GNSSDriver(event_bus)
light     = LightSensorDriver(event_bus)

# ─── 执行器（5）───
button    = Button(event_bus)
led       = LEDDriver(event_bus)
audio     = AudioDriver(event_bus)
lcd       = LCDDriver(event_bus)
pwm_led   = PWMLEDDriver(event_bus)

# ─── 网络（1）───
ble       = BLEDriver(event_bus)

# ─── 服务（7）───
collision   = CollisionService(event_bus)
alarm       = AlarmService(event_bus, led=led, audio=audio)
display     = DisplayService(event_bus, lcd_driver=lcd, audio_driver=audio)
light_svc   = LightService(event_bus, pwm_led=pwm_led)
control     = ControlService(event_bus)
ble_service = BLEService(event_bus, ble_driver=ble)
navigation  = NavigationService(event_bus, audio_driver=audio, lcd_driver=lcd)
```

**全系统 E2E 测试场景**：

| # | 场景 | 操作 | 预期结果 |
|---|------|------|---------|
| 1 | 系统启动 | 上电 | 17 模块全部 `is_init=True` |
| 2 | BLE 连接 | 手机连接 | `ble_connected=True`，收到传感器数据 |
| 3 | 灯光控制 | 小程序发 `light_on` | PWM_LED 亮（50%），状态回推 |
| 4 | 音量控制 | 小程序发 `volume_up` | Audio 音量 +1 |
| 5 | 碰撞报警 | 敲击 IMU | LED 闪烁 + 报警音 + BLE 通知 |
| 6 | 报警取消 | 小程序发 `alarm_cancel` | 声光停止，恢复状态 |
| 7 | 电源切换 | 小程序发 `power_save` | 传感器降频，背光关闭 |
| 8 | 导航指令 | 小程序发导航 | TTS 播报 + LCD 导航行 |
| 9 | 长时间运行 | 等待 5 分钟 | 无崩溃，无内存泄漏 |

### 6.7 Phase 5 — 清理（debug 打印 → 正式版）

**目标**：去除所有调试打印，产出正式版 `main_v2.py`。

**需要清理的打印**：

| 位置 | 打印内容 | 处理方式 |
|------|---------|---------|
| `main_v2.py` tick 循环 | 模块数据快照打印（每 2s） | 移除或改为条件编译 |
| 各模块 `init()` | `"✓ / ✗ 初始化成功/失败"` | 保留（系统启动必要的状态反馈） |
| 各模块 `tick()` | 传感器数据打印 | 移除（主循环不直接打印） |
| EventBus | debug 模式 `print("[订阅] ...")` | 关闭 `event_bus.debug = False` |
| BLEService | payload 过大警告 | 保留（异常保护） |
| EventBus | `EVENT_ERR` 错误打印 | 保留（异常捕获） |

**处理策略**：
- `event_bus.debug = True` → `event_bus.debug = False`
- 移除 `loop_count % 200 == 0` 的数据快照打印块
- 保留各模块 `init()` 的成功/失败打印（上线前可考虑移除，但当前阶段保留有助于诊断）

### 6.8 Phase 6 — 语音集成（阻塞，等队友）

**状态**：⏸️ **BLOCKED** — 等待队友发送 VoiceDriver（ASRPRO）代码。

**集成内容**：
```
VoiceDriver → EVENT_VOICE_CMD → ControlService._on_voice_cmd()
                                  → 已有 19 条指令映射
```

**待队友确认**：
- VoiceDriver 构造函数参数（`event_bus`, `uart_id`?）
- UART 引脚配置
- ASRPRO hex 命令协议（已有 `VOICE_CMD_MAP`）
- VoiceDriver 的 `init()`, `tick()` 实现

---

## 7. EventBus 测试要点

### 7.1 发布/订阅测试

```python
# 测试发布订阅基本功能
received = []
def handler(data):
    received.append(data)

bus = EventBus()
bus.subscribe("TEST_EVENT", handler)
bus.publish("TEST_EVENT", {"value": 42})
bus.pump()
assert len(received) == 1
assert received[0]["value"] == 42
```

**验证点**：
- 订阅后能正确收到事件
- 发布次数 = 接收次数
- 数据内容与发布一致

### 7.2 异常隔离测试

```python
# 测试异常隔离：一个回调崩溃不影响其他
calls = []
def bad_handler(data):
    raise RuntimeError("故意崩溃")

def good_handler(data):
    calls.append(data)

bus = EventBus()
bus.subscribe("TEST", bad_handler)
bus.subscribe("TEST", good_handler)
bus.publish("TEST", {"ok": 1})
bus.pump()
assert len(calls) == 1  # good_handler 仍被调用
```

**验证点**：
- 异常模块的崩溃不影响其他模块
- `print("[EVENT_ERR] ...")` 输出错误信息
- 主循环不中断

### 7.3 线程安全测试

```python
# 测试多线程并发发布
import _thread
bus = EventBus()
results = []

def subscriber(data):
    results.append(data["thread_id"])

bus.subscribe("THREAD_SAFE", subscriber)

def publisher(tid):
    for _ in range(100):
        bus.publish("THREAD_SAFE", {"thread_id": tid})
        time.sleep_ms(1)

_thread.start_new_thread(publisher, (1,))
_thread.start_new_thread(publisher, (2,))
time.sleep_ms(500)
bus.pump()
assert len(results) == 200  # 两条线程共 200 条
```

**验证点**：
- 多线程 `publish()` 不触发 `_lock` 死锁
- 数据不丢失
- 队列顺序基本保持

### 7.4 重入测试

```python
# 测试事件回调中再次发布事件
chain = []
def handler_a(data):
    chain.append("a")
    bus.publish("EVENT_B", {})

def handler_b(data):
    chain.append("b")

bus = EventBus()
bus.subscribe("EVENT_A", handler_a)
bus.subscribe("EVENT_B", handler_b)
bus.publish("EVENT_A", {})
bus.pump()
assert "a" in chain
assert "b" in chain  # B 事件也在同一泵周期中被处理
```

**验证点**：
- 回调中 `publish()` 的新事件在 `pump()` 中被处理
- 不产生无限递归
- 队列指针正确

---

## 8. 风险与注意事项

### 8.1 已知风险

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|---------|
| R1 | `EVENT_BLE_ALARM_ACK` 无订阅者 | FFF4 通道写入的报警确认无人处理 | 报警取消已通过 FFF3 + `alarm_cancel` 指令处理，FFF4 可废弃或改为冗余通道 |
| R2 | BLEService 后台线程 `_notify_thread` 若线程启动失败 | BLE 推送不可用 | 添加 `try/except`，`is_init=False` 时跳过 tick |
| R3 | BLE 连接后立即推送大数据（CCCD 未订阅） | 手机收不到通知 | `BLEService` 连接后延迟 500ms 首次推送；`force_push` 只推一次 |
| R4 | 多线程 `EventBus.publish()` + `pump()` 竞态 | 事件丢失或重复 | `_lock.acquire()` / `release()` 保护 `_queue` |
| R5 | NavigationService TTS 子线程与 AlarmService 音频冲突 | 音频叠加 | AudioDriver `alarm_playing` 标志阻止 TTS；`is_tts_playing` 防重入 |
| R6 | PWM_LED 初始化引脚 PE11 不是 Arduino 引脚名 | 命名错误导致初始化失败 | 验证 `Pin('PE11')` 在 REPL 中可用 |
| R7 | BLE MTU 协商前默认 23 字节，载荷仅 20 字节 | 大数据包发送失败 | `_notify_thread` 检查 `len(data) ≤ 244`，t=0 合并数据控制在 244 内 |
| R8 | main.py 保留 v1 回退，但 `cloud_service` 导入 MQTT/Network | v2 中不再需要 | v2 不导入 `CloudService`，无影响。v1 仍可用。 |

### 8.2 集成检查清单

#### Phase 1 — Device 层
- [ ] `PWMLEDDriver` 导入和实例化语法检查通过
- [ ] `PWMLEDDriver` 构造函数不需要 device 参数（纯 `event_bus`）
- [ ] `BLEDriver` 导入和实例化语法检查通过
- [ ] 两个新模块加入 `init_order` 数组
- [ ] 两个新模块加入 tick 循环
- [ ] 上传板子验证 14 模块初始化无异常
- [ ] Phase 1 → Phase 2 无阻塞

#### Phase 2 — Service 层
- [ ] `LightService` 构造函数需要 `pwm_led` 参数（已传）
- [ ] `ControlService` 纯事件驱动，无需额外依赖
- [ ] 事件链验证：`EVENT_RIDE_CONTROL` → `EVENT_LIGHT_CONTROL`
- [ ] 状态回推验证：`EVENT_CONTROL_STATE_CHANGED`
- [ ] 上传板子验证 16 模块初始化无异常

#### Phase 3 — 通信层
- [ ] `BLEService` 构造函数需要 `ble_driver` 参数（已传）
- [ ] `NavigationService` 构造函数需要 `audio_driver` + `lcd_driver`
- [ ] BLEService 后台线程启动（`_notify_thread`）
- [ ] BLE 连接 → 传感器数据推送（t=0）
- [ ] BLE 心跳包 (t=99) 每 5s
- [ ] 控制指令 FFF3 → ControlService → 事件发布
- [ ] 导航指令 FFF2 → NavigationService → TTS + LCD
- [ ] 上传板子验证 18 模块（含 Voice）= 17 活跃模块

#### Phase 4 — 全系统
- [ ] `main_v2.py` 创建，`main.py` 保留
- [ ] 17 模块全部在 init_order 中
- [ ] 初始化顺序正确（传感器 → 执行器 → 网络 → 服务）
- [ ] E2E 测试 9 场景全部通过
- [ ] 5 分钟长时间运行无崩溃

#### Phase 5 — 清理
- [ ] `event_bus.debug = True` → `False`
- [ ] 移除 tick 循环的数据快照打印
- [ ] 保留初始化成功/失败打印
- [ ] 保留异常错误打印
- [ ] 产出最终 `main_v2.py`

#### Phase 6 — 语音（阻塞）
- [ ] VoiceDriver 代码到位
- [ ] 导入语法检查
- [ ] 初始化顺序确认（VoiceDriver 应在 ControlService 之前？需确认）
- [ ] UART 引脚配置正确
- [ ] hex 命令 → 控制指令映射验证
- [ ] TTS 反馈验证

### 8.3 v1 → v2 回退方案

若有问题需要回退到 v1：

```
# Thonny 中切换版本
1. 删除或重命名 main.py → main.py.bak
2. 复制 main.py（v1）恢复到 main.py
3. 或直接运行 test_system_v1.py（独立测试文件）
```

**v1 保留文件**：
- `02_Software/core/main.py` — v1 入口（12 模块 + CloudService）
- `02_Software/Modules/cloud_service.py` — 保留（不集成）
- `02_Software/Drivers/network/Network.py` — 保留（CloudService 依赖）
- `02_Software/Drivers/network/MQTT.py` — 保留（CloudService 依赖）

---

## 附录 A：事件常量总表

| 事件常量 | 值 | 发布者 | 订阅者 |
|---------|-----|--------|--------|
| `EVENT_SYSTEM_READY` | `"SYSTEM_READY"` | main.py | — |
| `EVENT_CONFIG_UPDATE` | `"CONFIG_UPDATE"` | — | CollisionService, AlarmService, LightService, PWMLEDDriver |
| `EVENT_SENSOR_ERROR` | `"SENSOR_ERROR"` | TempHumidDriver | — |
| `EVENT_BUTTON_PRESSED` | `"BUTTON_PRESSED"` | Button | AlarmService |
| `EVENT_TEMP_HUMID_READY` | `"TEMP_HUMID_READY"` | TempHumidDriver | DisplayService, BLEService, ControlService |
| `EVENT_IMU_READY` | `"IMU_READY"` | IMUDriver | CollisionService, BLEService |
| `EVENT_GNSS_READY` | `"GNSS_READY"` | GNSSDriver | DisplayService, BLEService, ControlService |
| `EVENT_LIGHT_READY` | `"LIGHT_READY"` | LightSensorDriver | DisplayService, BLEService, LightService |
| `EVENT_GPS_LOST` | `"GPS_LOST"` | GNSSDriver | AlarmService |
| `EVENT_COLLISION_DETECTED` | `"COLLISION_DETECTED"` | CollisionService | AlarmService |
| `EVENT_ALARM_TRIGGERED` | `"ALARM_TRIGGERED"` | AlarmService | DisplayService, BLEService, ControlService, NavigationService |
| `EVENT_ALARM_CANCELED` | `"ALARM_CANCELED"` | AlarmService | DisplayService, BLEService, ControlService, NavigationService |
| `EVENT_ALARM_CONTROL` | `"ALARM_CONTROL"` | ControlService | AlarmService |
| `EVENT_BLE_CONNECTED` | `"BLE_CONNECTED"` | BLEDriver | BLEService |
| `EVENT_BLE_DISCONNECTED` | `"BLE_DISCONNECTED"` | BLEDriver | BLEService |
| `EVENT_BLE_ALARM_ACK` | `"BLE_ALARM_ACK"` | BLEService | ⚠️ 无订阅者 |
| `EVENT_NAV_CMD` | `"NAV_CMD"` | BLEService | NavigationService |
| `EVENT_RIDE_CONTROL` | `"RIDE_CONTROL"` | BLEService | ControlService |
| `EVENT_CONTROL_STATE_CHANGED` | `"CONTROL_STATE_CHANGED"` | ControlService | BLEService |
| `EVENT_LIGHT_CONTROL` | `"LIGHT_CONTROL"` | ControlService | LightService |
| `EVENT_VOLUME_CONTROL` | `"VOLUME_CONTROL"` | ControlService | AudioDriver |
| `EVENT_TTS_REQUEST` | `"TTS_REQUEST"` | ControlService | AudioDriver |
| `EVENT_POWER_STATE_CHANGE` | `"POWER_STATE_CHANGE"` | ControlService | DisplayService, NavigationService |
| `EVENT_VOICE_CMD` | `"VOICE_CMD"` | VoiceDriver（未来） | ControlService |

---

## 附录 B：BLE 协议摘要

| 通道 | UUID | 方向 | 格式 | 示例 |
|------|------|------|------|------|
| 头盔数据 | FFF1 | NOTIFY（头盔→手机） | `{"t":0,"d":{"tmp":25.5,"hum":65,"lat":31.23,"lon":121.47,"spd":18.5}}` |
| 导航指令 | FFF2 | WRITE（手机→头盔） | `{"a":"nav","d":{"dir":"right","dist":200,"road":"中山路"}}` |
| 骑行控制 | FFF3 | WRITE（手机→头盔） | `{"a":"ctrl","d":{"cmd":"light_on"}}` |
| 报警确认 | FFF4 | WRITE（手机→头盔） | ⚠️ 无订阅者（冗余通道） |
| 报警推送 | FFF1 | NOTIFY | `{"t":5,"a":1,"l":2}`（15 字节） |
| 控制状态 | FFF1 | NOTIFY | `{"t":7,"m":1,"b":50,"v":5,"p":0}`（25 字节） |
| 心跳 | FFF1 | NOTIFY | `{"t":99,"d":{"s":"ok"}}` |

**载荷约束**：所有 BLE payload 必须 ≤244 字节（ATT_MTU 247 - 3 字节 ATT 头）。

---

## 附录 C：文件结构

```
02_Software/core/
├── main.py              # v1 入口（12 模块，保留为回退）
├── main_v2.py           # v2 入口（17 模块，Phase 4 创建）
├── config.py            # 全局配置
├── Event_Bus.py         # 事件总线
└── Base_Module.py       # 模块基类

02_Software/Drivers/
├── sensor/
│   ├── Temp_Humid.py    # AHT20 温湿度
│   ├── imu.py           # LIS2DH12TR 加速度计
│   ├── Gnss.py          # EC200U GNSS
│   └── Light.py         # GL5528 光敏
├── actuator/
│   ├── LED.py           # 蓝色 LED
│   ├── Audio.py         # EC200U 音频
│   ├── LCD.py           # ST7735 LCD
│   └── PWM_LED.py       # PE11 PWM 大灯
├── interface/
│   ├── Button.py        # SW 按钮
│   └── Voice.py         # ASRPRO 语音（阻塞）
└── network/
    ├── BLE.py           # EC200U BLE 驱动
    ├── thread_queue.py  # 线程安全队列
    ├── Network.py       # （废弃）
    ├── MQTT.py          # （废弃）
    └── Qth.py           # （废弃）

02_Software/Modules/
├── collision_service.py # 碰撞检测
├── alarm_service.py     # 报警联动
├── display_service.py   # 显示管理
├── ble_service.py       # BLE 推送服务
├── light_service.py     # 自适应灯光
├── control_service.py   # 统一控制
├── navigation_service.py# 导航服务
├── cloud_service.py     # （废弃）
└── lark_cloud.py        # （废弃）
```
