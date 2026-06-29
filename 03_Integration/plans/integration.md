# SmartRidingHelmet v2 全局集成方案

## TL;DR (For humans)

**What you'll get:** 将 v2 新增的 10 个模块渐进式集成到 `main.py`，形成 21 模块全系统运行，覆盖传感器→执行器→BLE通信→音频调度→灯光→导航→远端控制→语音→电池/电源的完整业务链路。

**Why this approach:** 采用 5-Step 渐进式策略（搭积木），每步只新增 1-2 个模块并在板子上验证通过后再推进下一步。每步聚焦一个独立业务链路，出问题能精确定位。

**What it will NOT do:**
- 不集成 MQTT/4G 云连接（CloudService/Qth）— 整个集成不需要
- 不集成 LBSDriver — P2 优先级，等 GNSS 互斥切换逻辑稳定后再加
- 不修改任何已有模块的核心逻辑 — 仅修改 `main.py` 和必要的 import

**Effort:** Large（涉及 main.py 重写 + 5 个集成阶段 + 板级验证）
**Risk:** Medium — 主要风险来自 BLE 硬件单例重复初始化、音频通道抢占、线程栈溢出
**Decisions to sanity-check:**
1. 不需要 MQTT/4G 云连接（CloudService/Qth 不集成）
2. VoiceDriver UART 波特率使用 115200（config.py 定义）而非 9600
3. 初始化顺序遵循"传感器→执行器→网络→服务"四阶段

---

> TL;DR (machine): Large effort, Medium risk. 7-step progressive integration of 11 new modules into main.py, producing a 22-module system (no MQTT/cloud): Step1=base(11), Step2=BLE+PWM(15), Step3=Nav(16), Step4=Control(17), Step5=Voice(18), Step6=AudioService+Battery+Power(21), Step7=HeartRate(22).

---

## 1. 系统全景：数据流 / 控制流 / 事件流

### 1.1 数据流（传感器 → 显示/BLE/控制）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           数 据 流 (Data Flow)                              │
│                                                                             │
│  [Temp_Humid] ──EVENT_TEMP_HUMID_READY──→ DisplayService (LCD显示温度湿度)   │
│       │                              ──→ BLEService (合并到 t=0 推送手机)    │
│       │                              ──→ ControlService (缓存供查询)         │
│       │                                                                     │
│  [IMU] ──EVENT_IMU_READY──→ CollisionService (三级判决算法)                  │
│       │                     ──→ BLEService (合并到 t=0 推送)                 │
│       │                                                                     │
│  [GNSS] ──EVENT_GNSS_READY──→ DisplayService (LCD显示定位/速度)              │
│       │                      ──→ BLEService (合并到 t=0 推送)                │
│       │                      ──→ ControlService (缓存供查询)                  │
│       │                                                                     │
│  [Light] ──EVENT_LIGHT_READY──→ DisplayService (自动调节LCD背光)             │
│        │                      ──→ LightService (自适应灯光亮度计算)           │
│        │                      ──→ BLEService (合并到 t=0 推送)               │
│        │                                                                 │
│  [HeartRate] ──EVENT_HEARTRATE_READY──→ ControlService (缓存供查询)         │
│        │                                                                 │
│  [Voice] ──EVENT_VOICE_CMD──→ ControlService (统一指令入口)                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 控制流（用户指令 → 执行器响应）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          控 制 流 (Control Flow)                             │
│                                                                             │
│  来源1: 手机小程序                                                           │
│    BLE FFF3 写入 ──→ BLEDriver (回调) ──→ BLEService (解析JSON)              │
│      ──EVENT_RIDE_CONTROL──→ ControlService._on_ride_control()               │
│        ──→ _cmd_handlers[cmd]() ──→ 发布对应事件                             │
│                                                                             │
│  来源2: 语音模块                                                             │
│    ASRPRO UART ──→ VoiceDriver.tick() ──EVENT_VOICE_CMD──→                   │
│      ControlService._on_voice_cmd() ──→ _cmd_handlers[cmd]()                │
│        ──→ 发布对应事件                                                      │
│                                                                             │
│  来源3: 物理按键                                                             │
│    Button IRQ ──EVENT_BUTTON_PRESSED──→ AlarmService._on_button_press()      │
│      ──→ 空闲时触发SOS / 报警中取消报警                                      │
│                                                                             │
│  ┌─────────────── ControlService 指令分发表 (19条) ───────────────────┐      │
│  │ light_on/off/auto   → EVENT_LIGHT_CONTROL  → LightService         │      │
│  │ brightness_up/down  → EVENT_LIGHT_CONTROL  → LightService         │      │
│  │ volume_up/down      → EVENT_VOLUME_CONTROL → AudioDriver          │      │
│  │ alarm_cancel        → EVENT_ALARM_CONTROL  → AlarmService         │      │
│  │ alarm_sos           → EVENT_ALARM_CONTROL  → AlarmService         │      │
│  │ alarm_stealth       → EVENT_ALARM_CONTROL  → AlarmService         │      │
│  │ power_save/normal/  → EVENT_POWER_STATE_CHANGE → 所有传感器/执行器 │      │
│  │   emergency         →                                            │      │
│  │ query_status/speed/ → TTS播报（通过 EVENT_TTS_REQUEST → Audio）   │      │
│  │   temp/humid/       →                                            │      │
│  │   location/battery  →                                            │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
│  执行链路示例（语音开灯）：                                                   │
│    "开灯" → VoiceDriver → EVENT_VOICE_CMD{cmd:"light_on"}                   │
│      → ControlService → EVENT_LIGHT_CONTROL{cmd:"on"}                       │
│        → LightService → pwm_led.set_brightness(50)                          │
│        → ControlService → EVENT_TTS_REQUEST{text:"灯光已开启"}               │
│          → AudioDriver.play_tts("灯光已开启")                                │
│        → ControlService → EVENT_CONTROL_STATE_CHANGED{...}                  │
│          → BLEService → BLE notify t=7 推送手机                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 事件流（完整事件总线拓扑）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     事件总线拓扑 (Event Bus Topology)                        │
│                                                                             │
│  事件名                        发布者              订阅者                     │
│  ─────────────────────────────────────────────────────────────────────────   │
│  EVENT_TEMP_HUMID_READY       TempHumidDriver     DisplayService            │
│                                                   BLEService                │
│                                                   ControlService            │
│                                                                             │
│  EVENT_IMU_READY              IMUDriver           CollisionService          │
│                                                   BLEService                │
│                                                                             │
│  EVENT_GNSS_READY             GNSSDriver          DisplayService            │
│                                                   BLEService                │
│                                                   ControlService            │
│                                                   NavigationService         │
│                                                                             │
│  EVENT_LIGHT_READY            LightSensorDriver   DisplayService            │
│                                                   LightService              │
│                                                   BLEService                │
│                                                                             │
│  EVENT_BATTERY_READY          BatteryDriver       PowerService              │
│                                                   ControlService            │
│                                                                             │
│  EVENT_BATTERY_LOW            PowerService        （外部/日志）              │
│                                                                             │
│  EVENT_COLLISION_DETECTED     CollisionService    AlarmService              │
│                                                                             │
│  EVENT_ALARM_TRIGGERED        AlarmService        DisplayService            │
│                                                   BLEService                │
│                                                   ControlService            │
│                                                   NavigationService         │
│                                                                             │
│  EVENT_ALARM_CANCELED         AlarmService        DisplayService            │
│                                                   BLEService                │
│                                                   ControlService            │
│                                                   NavigationService         │
│                                                                             │
│  EVENT_BLE_CONNECTED          BLEDriver           BLEService                │
│  EVENT_BLE_DISCONNECTED       BLEDriver           BLEService                │
│                                                                             │
│  EVENT_RIDE_CONTROL           BLEService          ControlService            │
│  EVENT_NAV_CMD                BLEService          NavigationService         │
│  EVENT_BLE_ALARM_ACK          BLEService          AlarmService              │
│                                                                             │
│  EVENT_VOICE_CMD              VoiceDriver         ControlService            │
│                                                                             │
│  EVENT_CONTROL_STATE_CHANGED  ControlService      BLEService                │
│                                                                             │
│  EVENT_LIGHT_CONTROL          ControlService      LightService              │
│  EVENT_VOLUME_CONTROL         ControlService      AudioDriver               │
│  EVENT_ALARM_CONTROL          ControlService      AlarmService              │
│  EVENT_TTS_REQUEST            ControlService      AudioService              │
│                                                   AudioDriver (直连,已废弃) │
│                                                                             │
│  EVENT_POWER_STATE_CHANGE     ControlService      所有传感器/LightService    │
│                                                   PowerService              │
│                                                   CollisionService          │
│                                                   AlarmService              │
│                                                   PWM_LEDDriver             │
│                                                   ControlService            │
│                                                                             │
│  EVENT_CONFIG_UPDATE          （外部/调试）        所有模块（通用配置更新）    │
│  EVENT_SYSTEM_READY           main.py             各模块                    │
│  EVENT_BUTTON_PRESSED         Button              AlarmService              │
│  EVENT_GPS_LOST               GNSSDriver          AlarmService              │
│                                                   DisplayService            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.4 模块依赖矩阵

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     模块依赖矩阵 (Dependency Matrix)                        │
│                                                                             │
│  模块                  构造函数参数                    依赖的Device          │
│  ─────────────────────────────────────────────────────────────────────────   │
│  CollisionService      (event_bus)                    无（纯事件驱动）       │
│  AudioService          (event_bus, audio_driver)      AudioDriver            │
│  PowerService          (event_bus)                    无（纯事件驱动）       │
│  AlarmService          (event_bus, led, audio)        LEDDriver, AudioDriver │
│  DisplayService        (event_bus, lcd_driver,        LCDDriver, AudioDriver │
│                         audio_driver)                                     │
│  LightService          (event_bus, pwm_led)           PWMLEDDriver           │
│  BLEService            (event_bus, ble_driver)        BLEDriver              │
│  ControlService        (event_bus, temp_humid,        TempHumidDriver,       │
│                         gnss, heart_rate,              GNSSDriver,            │
│                         power_svc)                    HeartRateDriver         │
│  NavigationService     (event_bus, audio_driver,      AudioDriver,           │
│                         lcd_driver)                   LCDDriver              │
│                                                                             │
│  依赖方向：Service → Device（单向，禁止反向）                                │
│  Service 间：禁止直接调用，必须通过 EventBus                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 初始化顺序与 main.py 编排

### 2.1 四阶段初始化顺序（v2 完整版）

```
阶段 1 — 传感器（数据源最先就绪）
  1. TempHumidDriver    → I2C1, addr 0x38
  2. IMUDriver          → I2C1, addr 0x19
  3. GNSSDriver         → EC200U 内置 GNSS
  4. LightSensorDriver  → ADC PC5
  5. BatteryDriver      → ADC PC4（电池电压）       ← v2 新增

阶段 2 — 执行器+接口（硬件输出就绪）
  6. Button             → GPIO 'SW', IRQ_RISING
  7. LEDDriver          → GPIO 'LED_BLUE', Timer1
  8. AudioDriver        → EC200U quectel.Audio
  9. LCDDriver          → SPI1, dc=F12, cs=D14
  10. PWMLEDDriver       → PE11, TIM1_CH2        ← v2 新增
  11. VoiceDriver       → UART2, 115200          ← v2 新增

阶段 3 — 网络（通信通道就绪）
  12. BLEDriver         → EC200U 内置 BLE 4.2    ← v2 新增

阶段 4 — 业务服务（依赖下层模块）
  13. PowerService      → 电源管理（自动省电+TTS）← v2 新增
  14. CollisionService  → 碰撞检测
  15. AudioService      → 统一音频调度（注入 audio_driver）   ← v2 新增
  16. AlarmService      → 报警联动（注入 led, audio）
  17. DisplayService    → LCD 显示（注入 lcd_driver, audio_driver）
  18. LightService      → 自适应灯光（注入 pwm_led）        ← v2 新增
  19. BLEService        → BLE 推送（注入 ble_driver）       ← v2 新增
  20. ControlService    → 统一控制（注入 temp_humid, gnss）  ← v2 新增
  21. NavigationService → 导航引导（注入 audio_driver, lcd_driver）← v2 新增

   注：LBSDriver 暂不集成（P2 优先级）
```

### 2.2 依赖注入规则

| 规则 | 说明 |
|------|------|
| Service 禁止自己 import 底层硬件 | 必须通过构造函数注入 Device 实例 |
| 注入对象可为 None | 调用处必须有 `if self.xxx:` 判空保护 |
| Service 间禁止直接引用 | 必须通过 EventBus 事件通信 |
| 初始化失败不阻塞 | `try...except` 包裹每个 `init()`，失败只跳过 |

### 2.3 Fail-Safe 容错降级

```python
# main.py 初始化循环模板
for mod in init_order:
    try:
        print(f"  -> 初始化 {mod.name}...")
        mod.init()
        print(f"  {mod.name} 初始化成功")
    except Exception as e:
        print(f"  {mod.name} 初始化失败: {e} — 跳过")
        failed.append(mod)
```

- VoiceDriver 失败（UART 没接好）→ 只打印 Error，继续初始化后续模块
- BLEDriver 失败（硬件异常）→ BLEService 注入的 ble_driver 仍可用但功能降级
- PWM_LED 失败 → LightService 的 pwm_led 为 None，判空跳过

---

## 3. 关键风险与防御措施

### 3.1 硬件资源互斥

| 风险 | 影响 | 防御措施 | 来源 |
|------|------|----------|------|
| 音频通道独占 | 导航 TTS 和碰撞报警音同时调用 → 底层挂死 | AlarmService 报警音优先级 > TTS；AudioDriver 在 `alarm_playing=True` 时拒绝 TTS | `config.py`: AudioDriver 内部逻辑 |
| BLE 硬件单例 | 反复 init() 返回 `+CME ERROR: 4` | BLE 只 init 一次，测试用模块级单例 | `03_Integration/reports/learnings.md` |
| I2C1 总线竞争 | Temp_Humid + IMU 共享 I2C1 | 所有 I2C 操作在主线程 tick() 中串行执行 | 架构约束 |
| GNSS/LBS 互斥 | EC200U 不能同时运行 | 当前只 init GNSS，LBS 暂不集成 | `03_Integration/plans/集成指南.md` |

### 3.2 线程安全

| 风险 | 影响 | 防御措施 |
|------|------|----------|
| BLE modem 线程回调异常 | BLE 协议栈崩溃 | BLEService 所有回调用 `try-except` 包裹 |
| 网络线程栈溢出 | Hard Fault | `_thread.stack_size(4096)` + 入口函数 `try-except` |
| EventBus 并发发布 | 队列数据竞争 | `_thread.allocate_lock()` 保护 `_queue` |

### 3.3 状态机安全

| 风险 | 影响 | 防御措施 |
|------|------|----------|
| LCD display_mode 永久死锁 | 报警事件丢失 → LCD 卡在报警画面 | 增加超时自动解锁（60s 无报警事件 → 恢复 normal） |
| 静默报警 vs 真实碰撞冲突 | Level 3 碰撞被静默模式吞掉 | 硬件碰撞 Level 3 强制打破静默，触发最大音量声光报警 |
| BLE 断连队列雪崩 | 重连后发送过期数据 | 断连时清空 send_queue + _ctrl_snapshot；重连只发一次全量快照 |

### 3.4 主循环性能

| 约束 | 值 | 监控方式 |
|------|-----|----------|
| tick() 红线 | < 5ms | `ticks_diff` 守卫 + WARNING 打印 |
| 内存下限 | > 15000 bytes | 每 100 循环 `gc.collect()` + `gc.mem_free()` 检查 |
| 主循环 sleep | 10ms | `time.sleep_ms(10)` 固定间隔 |

---

## 4. 集成阶段与步骤

### Step 1: 基础基线（去除移远云）⏳ 当前执行

**目标**：从 v1 main.py 中移除 CloudService（MQTT/4G），形成 11 模块纯净基线。

**当前状态**：v1 main.py 包含 12 个模块（含 CloudService），需要移除。

**移除模块**：
| 模块 | 操作 |
|------|------|
| CloudService | 删除 import 和实例化，从 init_order 移除 |

**保留模块（11个）**：
| 类别 | 模块 |
|------|------|
| 传感器 (4) | TempHumidDriver, IMUDriver, GNSSDriver, LightSensorDriver |
| 执行器 (4) | Button, LEDDriver, AudioDriver, LCDDriver |
| 服务 (3) | CollisionService, AlarmService, DisplayService |

**修改文件**：`02_Software/core/main.py`

**具体变更**：
1. 删除 import：`from Modules.cloud_service import CloudService`
2. 删除实例化：`cloud = CloudService(event_bus)`
3. 从 init_order 移除 `cloud`

**验证目标**：
1. 11 个模块全部初始化成功
2. 传感器数据正常上报（温湿度、IMU、GNSS、光照）
3. 碰撞报警链路畅通（LED 闪烁 + 音频播放 + LCD 切换）
4. 主循环 tick() 稳定在 5ms 以内
5. 无任何 MQTT/4G 相关日志输出

**测试文件**：`03_Integration/tests/wave0_baseline/test_system_base.py`（新建）

---

### Step 2: BLE + 灯光链路集成

**目标**：加入 BLE 近场通信 + PWM 灯光控制，形成 15 模块系统。

**新增模块（4个）**：
| 模块 | 文件 | 初始化位置 |
|------|------|-----------|
| BLEDriver | `Drivers/network/BLE.py` | 阶段 3（LCD 之后） |
| PWMLEDDriver | `Drivers/actuator/PWM_LED.py` | 阶段 2（LCD 之后） |
| BLEService | `Modules/ble_service.py` | 阶段 4（DisplayService 之后） |
| LightService | `Modules/light_service.py` | 阶段 4（BLEService 之后） |

**修改文件**：`02_Software/core/main.py`

**具体变更**：
1. 新增 import：
   ```python
   from Drivers.network.BLE import BLEDriver
   from Drivers.actuator.PWM_LED import PWMLEDDriver
   from Modules.ble_service import BLEService
   from Modules.light_service import LightService
   ```
2. 创建实例：
   ```python
   ble = BLEDriver(event_bus)
   pwm_led = PWMLEDDriver(event_bus)
   ```
3. 创建服务：
   ```python
   ble_svc = BLEService(event_bus, ble_driver=ble)
   light_svc = LightService(event_bus, pwm_led=pwm_led)
   ```
4. init_order 加入：ble, pwm_led（执行器区），ble_svc, light_svc（服务区）

**数据流验证**：
```
链路1 — BLE 数据推送：
传感器 → EventBus → BLEService._on_xxx() → 缓存
BLEService.tick() (每 2000ms) → 合并 t=0 JSON → ble.notify_data()
→ 手机小程序收到传感器数据

链路2 — 自适应灯光：
Light → EVENT_LIGHT_READY → LightService → 计算亮度
→ pwm_led.set_brightness(计算值)

链路3 — 极限冲突：
BLE 连接中 → 敲击桌子模拟碰撞
→ AlarmService → LED 快闪 + 音频报警
→ LightService 暂停自动调光（报警态）
```

**验证目标**：
1. BLE 连接成功，小程序收到 t=0 传感器数据
2. PWM_LED 根据光照自动调节亮度
3. 断连后队列清空，重连不发过期数据
4. 报警时灯光行为正确
5. 主循环 tick() < 5ms

**测试文件**：
- `03_Integration/tests/wave1_device/test_device_integration.py`（已有，PWM+BLE 联合）
- `03_Integration/tests/wave3_communication/test_ble_service_integration.py`（已有）
- `03_Integration/tests/wave2_service/test_light_service_integration.py`（已有）

---

### Step 3: 导航链路集成

**目标**：加入 NavigationService，实现 BLE 导航指令 → TTS 播报 + LCD 显示。

**新增模块（1个）**：
| 模块 | 文件 | 初始化位置 |
|------|------|-----------|
| NavigationService | `Modules/navigation_service.py` | 阶段 4（LightService 之后） |

**修改文件**：`02_Software/core/main.py`

**具体变更**：
1. 新增 import：`from Modules.navigation_service import NavigationService`
2. 创建服务：`nav_svc = NavigationService(event_bus, audio_driver=audio, lcd_driver=lcd)`
3. init_order 加入 nav_svc

**数据流验证**：
```
BLE FFF2 写入 {"a":"nav","d":{"dir":"right","dist":200,"road":"中山路"}}
→ BLEDriver 回调 → BLEService → EVENT_NAV_CMD{raw:...}
→ NavigationService._on_nav_cmd()
→ AudioDriver.play_tts("前方200米右转进入中山路")
→ LCDDriver 显示导航信息
```

**验证目标**：
1. 手动发布 EVENT_NAV_CMD → TTS 播报导航指令
2. LCD 显示导航信息
3. 导航 TTS 能被报警音打断（优先级正确）
4. 导航结束 → LCD 恢复正常画面

**测试文件**：
- `03_Integration/tests/wave3_communication/test_navigation_service_integration.py`（已有）

---

### Step 4: 远端控制集成

**目标**：加入 ControlService，实现 BLE 远端控制 + 状态回推 + TTS 反馈。

**新增模块（1个）**：
| 模块 | 文件 | 初始化位置 |
|------|------|-----------|
| ControlService | `Modules/control_service.py` | 阶段 4（NavigationService 之后） |

**修改文件**：`02_Software/core/main.py`

**具体变更**：
1. 新增 import：`from Modules.control_service import ControlService`
2. 创建服务：`ctrl_svc = ControlService(event_bus, temp_humid=temp_humid, gnss=gnss)`
3. init_order 加入 ctrl_svc

**数据流验证**：
```
链路1 — BLE 远端控制：
手机 FFF3 写入 {"cmd":"light_on"}
→ BLEService → EVENT_RIDE_CONTROL
→ ControlService → EVENT_LIGHT_CONTROL{cmd:"on"}
→ LightService → pwm_led.set_brightness(50)
→ EVENT_CONTROL_STATE_CHANGED → BLEService → BLE notify t=7
→ EVENT_TTS_REQUEST → AudioDriver.play_tts("灯光已开启")

链路2.5 — 电源状态回推：
PowerService 检测低电量 → EVENT_POWER_STATE_CHANGE{SUSPENDED}
→ ControlService._on_power_state() → 更新 _control_state["power_mode"]
→ _push_state() → EVENT_CONTROL_STATE_CHANGED → BLEService → BLE notify t=7
→ 手机小程序收到电源模式变更

链路2 — 查询状态：
手机下发 query_status
→ ControlService → 读取缓存传感器数据
→ EVENT_TTS_REQUEST → AudioDriver（TTS 播报）
→ EVENT_CONTROL_STATE_CHANGED → BLEService → BLE notify t=7

链路3 — 报警态屏蔽：
报警激活时 → ControlService 拦截非紧急指令
→ TTS 静默，控制指令丢弃
```

**验证目标**：
1. 小程序下发 light_on → PWM_LED 亮起 + TTS 反馈
2. 小程序下发 query_status → TTS 播报状态
3. 小程序下发 alarm_cancel → 报警取消
4. 状态快照 t=7 正确回推
5. 报警态下控制指令被屏蔽

**测试文件**：
- `03_Integration/tests/wave2_service/test_control_service_integration.py`（已有）

---

### Step 5: 语音控制集成

**目标**：加入 VoiceDriver，实现语音指令 → ControlService → 执行器响应。

**新增模块（1个）**：
| 模块 | 文件 | 初始化位置 |
|------|------|-----------|
| VoiceDriver | `Drivers/interface/Voice.py` | 阶段 2（PWM_LED 之后） |

**修改文件**：`02_Software/core/main.py`

**具体变更**：
1. 新增 import：`from Drivers.interface.Voice import VoiceDriver`
2. 创建实例：`voice = VoiceDriver(event_bus)`
3. init_order 加入 voice

**数据流验证**：
```
链路 — 语音控灯：
ASRPRO UART 发送 0x01（"开灯"）
→ VoiceDriver.tick() → EVENT_VOICE_CMD{cmd:"light_on"}
→ ControlService → EVENT_LIGHT_CONTROL{cmd:"on"}
→ LightService → pwm_led.set_brightness(50)
→ EVENT_TTS_REQUEST → AudioDriver.play_tts("灯光已开启")
→ EVENT_CONTROL_STATE_CHANGED → BLEService → BLE notify t=7

链路 — 语音查询：
ASRPRO 发送 0x0E（query_status）
→ VoiceDriver → EVENT_VOICE_CMD
→ ControlService → TTS 播报状态
```

**Fail-Safe**：VoiceDriver 初始化失败（UART 没接好）→ 只打印 Error，不阻塞系统。

**验证目标**：
1. ASRPRO 发送 hex → VoiceDriver 解析 → EVENT_VOICE_CMD 发布
2. 语音"开灯" → PWM_LED 亮起 + TTS 反馈
3. 语音"查询状态" → TTS 播报
4. 无 ASRPRO 硬件时系统正常启动（VoiceDriver 跳过）

**测试文件**：
- `03_Integration/tests/step5_voice/test_voice_driver.py`
- `03_Integration/tests/step5_voice/test_voice_control_integration.py`
- `03_Integration/tests/step5_voice/test_voice_e2e.py`
- `03_Integration/tests/step5_voice/test_voice_real_debug.py`

---

### Step 6: 补充测试（AudioService + 电池/电源 + 全系统 v2）

**目标**：为新增的 AudioService、BatteryDriver、PowerService 模块编写集成测试，并创建 21 模块全系统集成测试替代过时的 v1 版本。

**新增模块（3个）**：
| 模块 | 文件 | 说明 |
|------|------|------|
| AudioService | `Modules/audio_service.py` | 统一音频调度（优先级队列 + 超时丢弃） |
| BatteryDriver | `Drivers/sensor/Battery.py` | ADC PC4 电池电压采集，6 档电量 |
| PowerService | `Modules/power_service.py` | 低电量自动省电 + TTS 提醒 |

**AudioService 调度规则**：
1. 高优先级打断低优先级（ALARM(0) > NAV(1) > CTRL(2)）
2. 同优先级覆盖当前
3. 低优先级入队等待（队列上限 3）
4. 报警期间拒绝非报警请求
5. 队列项超时 5s 自动丢弃

**BatteryDriver + PowerService 规则**：
1. ADC PC4 采集电池电压，分压比 1.45
2. 6 档电量映射：0(没电) / 1(危急) / 2(低) / 3(中等) / 4(良好) / 5(满)
3. level≤2 时自动切换 SUSPENDED 省电模式
4. 低电量 TTS 播报"当前电量不足，请及时充电"
5. auto_suspended 防重复标记，手动 ACTIVE 时清除
6. 启动宽限期：前 3 次 ADC 采样不做省电决策（sample_count < 3 → 跳过）
7. 未接电池保护：battery_mv < 1000 时跳过省电逻辑
8. 低电量阈值：battery_mv < 1000 视为未接电池（原 500→1000）

**初始化顺序变更**：
```
原：... → CollisionService → AudioService → AlarmService → ...
新：BatteryDriver(传感器区) + PowerService → CollisionService → AudioService → AlarmService → ...
```

**测试文件**：
- `03_Integration/tests/step6_addition/test_audio_service.py`（8 个用例）
- `03_Integration/tests/step6_addition/test_power_battery.py`（8 个用例）
- `03_Integration/tests/step6_addition/test_full_system_v2.py`（10 个用例）

**验证目标**：
1. AudioService 优先级调度正确（高打断低、同级覆盖、低入队）
2. 报警期间非报警 TTS 被拒绝
3. 队列满时丢弃最旧，超时项自动清理
4. BatteryDriver ADC 读数 + 6 档映射正确
5. level≤2 → 自动省电 + TTS + EVENT_BATTERY_LOW
6. 21 模块全部初始化成功
7. 传感器事件链 → DisplayService 正确更新
8. 碰撞报警链路畅通
9. 主循环 tick() < 5ms
10. 内存无泄漏

---

### Step 7: 心率血氧模块集成

**目标**：集成 HeartRateDriver，实现心率血氧数据采集 + 语音查询。

**新增模块（1个）**：
| 模块 | 文件 | 说明 |
|------|------|------|
| HeartRateDriver | `Drivers/sensor/HeartRate.py` | MKS SPO2-ZS-BLE 心率血氧，UART9 |

**修改文件**：
- `02_Software/core/main.py`：添加 HeartRateDriver 初始化
- `02_Software/Modules/control_service.py`：添加 heart_rate 参数 + query_heartrate/query_spo2

**初始化顺序变更**：
```
原：BatteryDriver → Button → ...
新：BatteryDriver → HeartRateDriver → Button → ...
```

**数据流验证**：
```
链路1 — 心率数据采集：
HeartRateDriver.tick() (每 2000ms) → UART 读取 50 字节帧
→ EVENT_HEARTRATE_READY{heart_rate, spo2, valid}
→ ControlService 缓存

链路2 — 语音查询心率：
ASRPRO 发送 0x14 → VoiceDriver → EVENT_VOICE_CMD{cmd:"query_heartrate"}
→ ControlService._query_heartrate()
→ heart_rate.force_read() → 返回缓存数据
→ TTS 播报"当前心率94次每分钟"

链路3 — 语音查询血氧：
ASRPRO 发送 0x15 → VoiceDriver → EVENT_VOICE_CMD{cmd:"query_spo2"}
→ ControlService._query_spo2()
→ heart_rate.force_read() → 返回缓存数据
→ TTS 播报"当前血氧饱和度百分之88"
```

**验证目标**：
1. HeartRateDriver 初始化成功（UART9）
2. 心率血氧数据正常采集（HR=90-95, SpO2=86-91）
3. 语音"查询心率" → TTS 播报实际心率值
4. 语音"查询血氧" → TTS 播报实际血氧值
5. force_read() 返回缓存数据，不阻塞主循环
6. 主循环 tick() < 5ms

**测试文件**：
- `02_Software/Tests/test_heartrate.py`（手指测试 60 秒 + force_read 测试）

---

```python
"""
brief 智能骑行头盔系统入口 — v2 正式版
note 集成 21 个模块（5 传感器 + 6 执行器/接口 + 1 网络 + 9 Service）
     不含 MQTT 云连接，LBSDriver 暂不集成（P2）
"""
import sys
import time
import gc

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_SYSTEM_READY

# 传感器
from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.sensor.Battery import BatteryDriver

# 执行器+接口
from Drivers.interface.Button import Button
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.interface.Voice import VoiceDriver

# 网络
from Drivers.network.BLE import BLEDriver

# 服务
from Modules.collision_service import CollisionService
from Modules.audio_service import AudioService
from Modules.alarm_service import AlarmService
from Modules.display_service import DisplayService
from Modules.light_service import LightService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.navigation_service import NavigationService
from Modules.power_service import PowerService


def main():
    print("智能骑行头盔系统启动 (v2)...")

    # 1. 创建事件总线
    event_bus = EventBus()
    event_bus.debug = True

    # 2. 创建模块实例
    # --- 阶段1: 传感器 ---
    temp_humid = TempHumidDriver(event_bus)
    imu = IMUDriver(event_bus)
    gnss = GNSSDriver(event_bus)
    light = LightSensorDriver(event_bus)

    # --- 阶段2: 执行器+接口 ---
    button = Button(event_bus)
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    lcd = LCDDriver(event_bus)
    pwm_led = PWMLEDDriver(event_bus)
    voice = VoiceDriver(event_bus)

    # --- 阶段3: 网络 ---
    ble = BLEDriver(event_bus)

    # --- 阶段4: 服务（注入 Device 引用）---
    collision = CollisionService(event_bus)
    audio_svc = AudioService(event_bus, audio_driver=audio)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    display = DisplayService(event_bus, lcd_driver=lcd, audio_driver=audio)
    light_svc = LightService(event_bus, pwm_led=pwm_led)
    ble_svc = BLEService(event_bus, ble_driver=ble)
    ctrl_svc = ControlService(event_bus, temp_humid=temp_humid, gnss=gnss)
    nav_svc = NavigationService(event_bus, audio_driver=audio, lcd_driver=lcd)
    power_svc = PowerService(event_bus)

    # 3. 按序初始化
    init_order = [
        # 传感器
        temp_humid, imu, gnss, light, battery_drv,
        # 执行器+接口
        button, led, audio, lcd, pwm_led, voice,
        # 网络
        ble,
        # 服务
        power_svc, collision, audio_svc, alarm, display,
        # 服务 v2
        light_svc, ble_svc, ctrl_svc, nav_svc,
    ]
    failed = []

    print("\n[初始化阶段]")
    for mod in init_order:
        try:
            print(f"  -> 初始化 {mod.name}...")
            mod.init()
            print(f"  {mod.name} 初始化成功")
        except Exception as e:
            print(f"  {mod.name} 初始化失败: {e} — 跳过")
            failed.append(mod)

    # 4. 发布系统就绪事件
    success = len(init_order) - len(failed)
    event_bus.publish(EVENT_SYSTEM_READY, {
        "total": len(init_order),
        "success": success,
        "failed": [m.name for m in failed],
    })

    if failed:
        print(f"\n系统就绪（{success}/{len(init_order)} 模块在线）")
        print(f"   离线: {', '.join(m.name for m in failed)}")
    else:
        print(f"\n系统就绪，{success} 个模块在线")

    # 5. 主循环
    print("进入主循环（事件驱动）")
    loop_count = 0
    try:
        while True:
            loop_start = time.ticks_ms()

            for mod in init_order:
                if not mod.ctx.get("is_init", False):
                    continue
                try:
                    mod.tick()
                except Exception as e:
                    print(f"[ERROR] {mod.name}.tick(): {e}")

            event_bus.pump()
            time.sleep_ms(10)

            # 性能监控（死守 5ms 红线）
            loop_cost = time.ticks_diff(time.ticks_ms(), loop_start)
            if loop_cost > 5:
                print(f"WARNING: 主循环耗时 {loop_cost}ms，超过 5ms 红线！")

            loop_count += 1

            # 内存监控（每 100 次循环）
            if loop_count % 100 == 0:
                gc.collect()
                free_mem = gc.mem_free()
                if free_mem < 15000:
                    print(f"CRITICAL: 剩余内存不足 {free_mem} bytes！")

            # 数据快照（每 2 秒）
            if loop_count % 200 == 0:
                print("\n--- 模块数据 (每 2 秒) ---")
                for mod in init_order:
                    if mod.ctx.get("is_init", False):
                        print(f"  [{mod.name}] {mod.get_data()}")

    except KeyboardInterrupt:
        print("\n系统已停止")


if __name__ == "__main__":
    main()
```

### Step 7: 压力测试与边界验证

**目标**：30 分钟全场景压力测试（193 操作）+ 4 项独立边界测试，验证系统在极限负载下的稳定性。

**测试文件**：
- `stress_test_30min_v3.py`：30 分钟全场景（构造参数修复 + _manual_locked + Burst + Audio 预占 + GNSS 退避）
- `test_boundary_sensors.py`：I2C1 总线争用（27 万次交替，0 error）
- `test_boundary_power_alarm.py`：报警中切电源（SUSPENDED→EMERGENCY→ACTIVE）
- `test_boundary_sos_cancel.py`：SOS 快速取消（5 组，0 状态残留）
- `test_boundary_eventbus_queue.py`：EventBus 队列溢出（CRITICAL 50/50 保留）

**通过标准**：30 分钟零 WDT 复位、23/23 模块在线、零内存泄漏、Audio 错误 0 次

---

### 6.1 测试 Step 对应关系

| Step | 模块数 | 测试文件 | 验证内容 |
|------|--------|---------|---------|
| Step 1 ✅ | 11 | `test_system_base.py` | 去除 CloudService 基线 |
| Step 2 ✅ | 15 | `test_pwm_led.py`, `test_ble_driver.py`, `test_ble_service.py`, `test_light_service.py`, `test_device_integration.py` | BLE + PWM + Light |
| Step 3 ✅ | 16 | `test_navigation_service.py`, `test_navigation_e2e.py` | 导航 TTS + LCD |
| Step 4 ✅ | 17 | `test_control_service.py`, `test_control_e2e.py`, `test_light_control.py` | 远端控制 19 指令 |
| Step 5 ✅ | 18 | `test_voice_driver.py`, `test_voice_control_integration.py`, `test_voice_e2e.py`, `test_voice_real_debug.py` | 语音指令入口 |
| Step 6 🔧 | 21 | `test_audio_service.py`, `test_power_battery.py`, `test_full_system_v2.py` | AudioService + Battery/Power + 全系统 E2E |
| ✅ Step 7 | 24 | 8 个文件 | 压力测试 + 边界测试 |

### 6.2 测试模式

所有测试遵循：
1. `make_system()` 工厂函数创建 EventBus + 模块实例
2. `pump_loop()` 替代 `time.sleep()` — `tick() + pump() + sleep_ms(50)`
3. `event_log` 全局列表追踪事件用于断言
4. Mock/Fake 硬件：`MockBLE`, `FakePWM`, `FakeAudio`, `FakeLCD`
5. BLE 硬件单例：模块级 `_shared_ble` 避免重复 init
6. **测试只能在设备上运行** — 通过 Thonny 上传到 NUCLEO-F413ZH

### 6.3 破坏性测试（Step 5 完成后必做）

| 测试 | 操作 | 预期结果 |
|------|------|---------|
| 拔天线 | 拔掉 GNSS 天线 | EVENT_GPS_LOST → TTS 提示，系统继续运行 |
| 并发打断 | 导航 TTS 中敲击桌子 | 报警音打断 TTS，系统不死机 |
| BLE 脏数据 | 向 FFF3 发送超长/畸形数据 | BLEService 安全丢弃，主循环不卡 |
| 断电重启 | 报警中拔电源重启 | LCD 恢复到 normal 模式 |

---

## Scope

### Must have
- v2 全部 10 个新模块集成到 main.py（BLEDriver, BLEService, ControlService, PWM_LED, LightService, NavigationService, VoiceDriver, AudioService, BatteryDriver, PowerService）
- 完整的依赖注入和判空保护
- Fail-Safe 容错降级（单模块失败不阻塞系统）
- 主循环性能监控（5ms 红线 + 内存监控）
- 6 步渐进式集成，每步有验证目标

### Must NOT have
- 不集成 MQTT/4G 云连接（CloudService、Qth 不移入）
- 不集成 LBSDriver — P2 优先级
- 不修改任何已有模块的核心业务逻辑
- 不在 main.py 中引入 Service 间直接调用
- 不在 PC 上运行测试（必须上板）

## Verification strategy
- Test decision: tests-after（测试文件已存在，集成后上板验证）
- Evidence: 每次上板测试的终端输出保存到 `03_Integration/reports/`
- 每个 Step 完成后对照验证目标逐项确认

## Execution strategy

### Dependency matrix
| Step | 新增模块 | 依赖 | 阻塞 |
|------|---------|------|------|
| Step 1 | 无（移除 CloudService） | 无 | Step 2 |
| Step 2 | BLEDriver, BLEService, PWM_LED, LightService | Step 1 完成 | Step 3, 4, 5 |
| Step 3 | NavigationService | Step 2 完成 | Step 4, 5 |
| Step 4 | ControlService | Step 2 完成 | Step 5 |
| Step 5 | VoiceDriver | Step 4 完成 | Step 6 |
| Step 6 | AudioService | Step 5 完成 | — |

## Commit strategy
每个 Step 完成后提交一次：
```
refactor(main): remove CloudService, establish 11-module base (Step 1)
feat(main): integrate BLE + PWM_LED + LightService (Step 2)
feat(main): integrate NavigationService (Step 3)
feat(main): integrate ControlService for remote control (Step 4)
feat(main): integrate VoiceDriver for voice control (Step 5)
feat(main): integrate AudioService + BatteryDriver + PowerService + full system v2 tests (Step 6)
```

## Success criteria
1. 全部模块初始化成功（无 MQTT 云连接，仅本地 + BLE 功能）
2. 微信小程序连接 BLE 后收到传感器数据推送（t=0）
3. 小程序下发控制指令后收到状态回推（t=7）
4. 语音"开灯" → PWM_LED 亮起 + TTS 反馈
5. 导航指令 → TTS 播报 + LCD 显示
6. 报警音能打断导航 TTS
7. 主循环 tick() 稳定 < 5ms
8. 内存 > 15000 bytes，连续运行 30 分钟无泄漏

---

## 8. 压力测试与稳定性评估

### 8.1 测试目标

验证系统在真实使用场景下长期运行的稳定性。聚焦三个核心问题：
- 系统能不能 30 分钟不崩？
- 内存会不会越跑越少？
- 关键功能（BLE、报警）在压力下是否可靠？

### 8.2 性能指标

仅关注体现系统稳定性的核心指标：

| 指标 | 定义 | 合格标准 |
|------|------|:--:|
| **连续运行时间** | 系统从启动到主动停止或崩溃的时长 | ≥ 30 分钟 |
| **WDT 复位次数** | 运行期间硬件看门狗触发复位的次数 | **0 次** |
| **内存趋势** | `gc.mem_free()` 随时间的变化趋势 | 最终内存 ≥ 初始的 60% |
| **关键模块存活** | SystemMonitor 报告的 `critical_alive` 状态 | 始终 True |
| **BLE 连接保持** | 与手机 BLE 连接的持续时长 | ≥ 30 分钟（允许 1 次断连重连） |

### 8.3 测试场景

#### 场景 1：稳态运行基线（30 分钟）
- 系统正常启动，所有模块在线
- BLE 保持连接，手机端接收传感器数据推送
- 不做任何主动操作，静置观察
- 每 30 秒记录：`gc.mem_free()`、`critical_alive`、`any_alive`
- **验证**：系统 30 分钟不崩溃、内存不泄漏、关键模块全活

#### 场景 2：导航复合场景（15 分钟）
- 手机发送完整骑行路线导航指令（~5 秒一条转弯指令）
- 导航过程中偶尔发语音指令（开灯/关灯）
- BLE 持续推送传感器数据
- **验证**：导航期间主循环不被卡死、TTS 正常播报、WDT 不触发

#### 场景 3：报警链路验证
- 敲击板子模拟碰撞 → 观测：LED 闪烁、TTS 报警播报、BLE 报警推送
- 在报警期间发语音指令 → 验证 TTS 优先级（报警不被打断）
- **验证**：报警链路完整、主循环在报警期间稳定

### 8.4 测试通过标准

| 项目 | 标准 |
|------|------|
| 30 分钟无崩溃 | `main.py` 持续运行，未被 WDT 复位 |
| 内存健康 | `gc.mem_free() > 50KB` 始终成立 |
| SystemMonitor 全绿 | `critical_alive=True` 持续保持 |
| BLE 连接稳定 | 30 分钟内断开次数 ≤ 1 |
| 导航 + 语音 | 全部指令正常执行，无丢失 |

### 8.5 测试执行清单

- [ ] 场景 1：稳态基线 30 分钟
- [ ] 场景 2：导航复合 15 分钟  
- [ ] 场景 3：报警链路验证
- [ ] 数据采集：整理日志、内存快照、SystemMonitor 报告
- [ ] 生成稳定性测试报告
