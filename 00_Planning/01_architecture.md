# 智能骑行头盔 - 嵌入式软件架构设计

> **核心目标**：确保多人并行开发后，代码能**稳定、安全、高效集成**
>
> **架构原则**：简单、清晰、实用

---

## 0. 快速理解架构

**核心概念**：

| 概念 | 是什么 | 为什么需要 |
|------|--------|-----------|
| **四层架构** | App → Service → Device → Vendor | 单向依赖，边界清晰 |
| **事件驱动** | 模块通过EventBus发布/订阅事件 | 模块松耦合，独立可测 |
| **四元组** | cfg/ctx/data/ops | 状态数据封装，避免全局变量冲突 |

**关键约束**：
- ❌ 禁止跨层调用（上层调下层，下层不调上层）
- ❌ 禁止模块间直接调用（必须通过EventBus）
- ❌ 禁止全局变量（状态封装在模块对象内）
- ✅ tick()必须快速返回（<5ms），不能阻塞

**开发一个模块的流程**：
```
1. 继承 BaseModule
2. 定义四元组（cfg/ctx/data）
3. 实现 init() - 初始化硬件、订阅事件
4. 实现 tick() - 数据采集、发布事件
5. 实现 get_data() - 返回数据快照
6. 编写单模块测试 + 集成测试
```

---

## 1. 架构总览

### 1.1 为什么需要架构？

**不使用架构会遇到的问题**：

| 问题 | 后果 | 根本原因 |
|------|------|----------|
| 网络阻塞导致传感器漏采 | 数据丢失，功能异常 | 主线程执行阻塞操作 |
| 全局变量冲突 | 改一处动全身，难以维护 | 状态数据未封装 |
| 初始化顺序混乱 | 设备依赖未就绪，启动失败 | 缺少初始化顺序规范 |
| 线程不安全 | 数据读写冲突，随机崩溃 | 多线程访问共享资源未保护 |
| API直接调用 | 无法替换硬件，耦合严重 | 未封装底层接口 |

**架构如何解决**：

| 方案 | 解决的问题 | 核心思想 |
|------|-----------|----------|
| **分层隔离** | 业务与硬件耦合 | 单向依赖，边界清晰 |
| **对象封装** | 全局变量冲突 | 四元组封装状态数据 |
| **事件驱动** | 模块强耦合 | 发布订阅，松耦合通信 |
| **简单初始化** | 初始化混乱 | main.py按顺序初始化 |

### 1.2 四层架构

```
┌─────────────────────────────────────────────┐
│           App 层（应用层）                    │
│  职责：系统入口、主循环调度                   │
│  内容：main.py、config.py                    │
│  规则：按顺序初始化模块，主循环调用tick()      │
└─────────────────┬───────────────────────────┘
                  ↓ 单向依赖
┌─────────────────▼───────────────────────────┐
│         Service 层（业务服务层）              │
│  职责：业务逻辑实现                           │
│  内容：碰撞检测、报警联动、云端通信            │
│  规则：通过事件总线通信，互不直接调用          │
└─────────────────┬───────────────────────────┘
                  ↓ 单向依赖
┌─────────────────▼───────────────────────────┐
│        Device 层（设备封装层）                │
│  职责：硬件封装，统一接口                      │
│  内容：传感器、执行器、网络设备                │
│  规则：只有这里能调用Vendor API               │
└─────────────────┬───────────────────────────┘
                  ↓ 单向依赖
┌─────────────────▼───────────────────────────┐
│      Vendor 层（原厂固件层，只读！）           │
│  内容：machine、quectel、_thread模块         │
└─────────────────────────────────────────────┘
```

**关键约束**：

1. **单向依赖**：上层只能调用下层，下层绝对不能调用上层
2. **Vendor只读**：移远提供的MicroPython固件，禁止修改
3. **Service隔离**：Service层模块间禁止直接调用，必须通过EventBus

---

## 2. 对象模型：四元组设计

### 2.1 设计思想

**问题：散落的函数和全局变量**

传统面向过程方式：
- 温度、湿度等数据存放在全局变量
- 多处代码直接读写这些全局变量
- 状态标志（是否初始化、是否忙碌）也是全局变量
- 结果：多处访问同一变量，容易冲突，难以维护

**解决：对象封装**

将模块封装为独立对象，每个对象包含：
- 自己的配置参数（cfg）
- 自己的运行状态（ctx）
- 自己的数据存储（data）
- 统一的操作接口（ops）

### 2.2 四元组定义

```
┌──────────────────────────────────────────┐
│           Module Object                  │
├──────────────────────────────────────────┤
│  cfg  - 静态配置                          │
│  ctx  - 运行时上下文                      │
│  data - 当前数据                          │
│  ops  - 行为接口                          │
└──────────────────────────────────────────┘
```

| 维度 | 名称 | 用途 | 特性 | 示例内容 |
|------|------|------|------|----------|
| **cfg** | 静态配置 | 怎么接、怎么配 | 运行期不变 | I2C地址、采样周期、重试次数 |
| **ctx** | 运行时上下文 | 当前运行状态 | 内部维护 | is_init、is_busy、err_count |
| **data** | 当前数据 | 传感器值或状态值 | 外部只读 | 温度、湿度、加速度 |
| **ops** | 行为接口 | 标准化操作方法 | 统一规范 | init、tick、get_data |

### 2.3 四元组详解（以温湿度传感器为例）

**完整代码示例**：

```python
class TempHumidDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "temp_humid"
        
        # ================== cfg：静态配置 ==================
        self.cfg = {
            "i2c_id": 1,              # I2C总线编号
            "i2c_freq": 400000,       # I2C频率 400kHz
            "addr": 0x38,             # AHT20设备地址
            "sample_ms": 2000,        # 采样间隔 2000ms
            "max_retry": 3            # 最大重试次数
        }
        
        # ================== ctx：运行时上下文 ==================
        self.ctx = {
            "is_init": False,         # 初始化完成标志
            "is_busy": False,         # 操作中标志（防重入）
            "last_tick": 0,           # 上次采样时间戳
            "err_count": 0            # 错误计数
        }
        
        # ================== data：当前数据 ==================
        self._data = {
            "temp": 0.0,              # 温度值（℃）
            "humid": 0.0,             # 湿度值（%RH）
            "valid": False            # 数据有效性
        }
```

**各元组的作用**：

**cfg（静态配置）**：
- 存放硬件固定参数（I2C地址、采样周期等）
- 运行期间不变，修改配置只改此处
- 作用：配置集中管理，避免硬编码

**ctx（运行时上下文）**：
- 存放运行状态（is_init、is_busy、err_count）
- 用于状态守卫、防重入、故障检测
- 作用：控制流程，保护临界区

**data（当前数据）**：
- 存放最新有效数据（温度、湿度等）
- 外部通过get_data()读取快照，不能直接修改
- 作用：数据一致性、线程安全

**ops（行为接口）**：
- init()：初始化硬件、订阅事件
- tick()：周期调度、数据采集、事件发布
- get_data()：返回数据快照
- get_status()：返回运行状态

### 2.4 统一接口规范

**所有模块必须实现的接口**：

| 接口 | 用途 | 调用时机 | 说明 |
|------|------|----------|------|
| **init()** | 初始化硬件 | 系统启动时，按顺序调用 | 失败抛异常，main.py捕获 |
| **tick()** | 周期调度 | 主循环每轮调用 | 必须<5ms返回，不能阻塞 |
| **get_data()** | 获取数据 | 外部需要读取数据时 | 返回数据快照，外部只读 |
| **get_status()** | 获取状态 | 调试和监控时 | 返回运行状态快照 |

**接口实现示例**：

```python
def init(self):
    """初始化硬件 + 订阅事件"""
    try:
        # 1. 硬件初始化
        self.i2c = machine.I2C(self.cfg["i2c_id"], ...)
        
        # 2. 设备验证
        devices = self.i2c.scan()
        if self.cfg["addr"] not in devices:
            raise RuntimeError("设备未响应")
        
        # 3. 订阅事件
        if self.event_bus:
            self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
        
        self.ctx["is_init"] = True
    except Exception as e:
        raise  # 失败抛异常

def tick(self):
    """周期调度：数据采集 + 事件发布"""
    # 状态守卫
    if not self.ctx["is_init"]:
        return
    
    # 时间片控制
    now = time.ticks_ms()
    if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
        return
    
    # 执行采集
    try:
        temp = self.sensor.temperature
        self._data["temp"] = round(temp, 1)
        self._data["valid"] = True
        
        # 发布事件
        if self.event_bus:
            self.event_bus.publish(EVENT_TEMP_HUMID_READY, self.get_data())
    except Exception as e:
        self.ctx["err_count"] += 1
    finally:
        self.ctx["last_tick"] = now

def get_data(self):
    """返回数据快照"""
    return {
        "temp": self._data["temp"],
        "humid": self._data["humid"],
        "valid": self._data["valid"],
        "timestamp": time.ticks_ms()
    }
```

---

## 3. 事件驱动：模块解耦

### 3.1 为什么用事件驱动？

**问题：直接调用导致强耦合**

```
❌ 传统方式：
碰撞检测 → 直接调用 → 报警模块.start_alarm()
碰撞检测 → 直接调用 → 云端模块.send_alarm()

后果：
- 碰撞检测依赖报警模块和云端模块
- 报警模块未初始化 → 系统崩溃
- 无法独立测试碰撞检测
```

**解决：事件驱动**

```
✅ 事件驱动：
碰撞检测 → 发布事件 COLLISION_DETECTED → 不关心谁在监听
报警模块 ← 订阅事件 ← 收到后启动报警
云端模块 ← 订阅事件 ← 收到后发送MQTT

收益：
- 碰撞检测不依赖任何模块
- 各模块可独立开发、测试
- 新增功能只需订阅事件
```

### 3.2 事件总线使用

**发布事件**：
```python
self.event_bus.publish(EVENT_TEMP_HUMID_READY, {
    "temp": 28.5,
    "humid": 65.2,
    "valid": True
})
```

**订阅事件**：
```python
def init(self):
    self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_data_ready)

def _on_data_ready(self, payload):
    print(f"温度: {payload['temp']}℃")
```

**事件处理流程**：
```python
# main.py 主循环
while True:
    # 1. 调度所有模块
    for mod in modules:
        mod.tick()
    
    # 2. 事件泵（处理事件队列）
    event_bus.pump()
    
    time.sleep_ms(10)
```

### 3.3 事件常量表

> 所有事件名定义在 `core/config.py`，模块间通信禁止硬编码事件字符串。

| 事件常量 | 说明 | 发布者 | 订阅者 |
|----------|------|--------|--------|
| **系统事件** | | | |
| EVENT_SYSTEM_READY | 系统就绪 | main.py | 各模块 |
| EVENT_CONFIG_UPDATE | 配置更新 | CloudService | 各模块 |
| EVENT_SENSOR_ERROR | 传感器错误 | 各传感器驱动 | — |
| EVENT_LCD_ERROR | LCD 错误 | LCDDriver | DisplayService |
| EVENT_BUTTON_ERROR | 按键错误 | Button | — |
| EVENT_BUTTON_PRESSED | 按键按下 | Button | AlarmService |
| EVENT_LED_ERROR | LED 错误 | LEDDriver | — |
| EVENT_PWM_LED_ERROR | PWM 控制错误 | PWM_LED | — |
| **传感器数据就绪** | | | |
| EVENT_TEMP_HUMID_READY | 温湿度数据就绪 | TempHumidDriver | ControlService, BLEService, DisplayService |
| EVENT_IMU_READY | IMU 加速度数据就绪 | IMUDriver | CollisionService |
| EVENT_GNSS_READY | GNSS 定位数据就绪 | GNSSDriver | ControlService, BLEService, NavigationService |
| EVENT_LIGHT_READY | 光照数据就绪 | LightSensorDriver | DisplayService, LightService |
| EVENT_HEARTRATE_READY | 心率血氧数据就绪 | HeartRateDriver | ControlService |
| EVENT_LBS_READY | LBS 基站定位就绪 | GNSSDriver | — |
| **报警事件** | | | |
| EVENT_COLLISION_DETECTED | 碰撞检测到 | CollisionService | AlarmService |
| EVENT_SOS_TRIGGERED | SOS 按键触发 | Button | AlarmService |
| EVENT_ALARM_TRIGGERED | 报警触发（通用） | AlarmService | BLEService, DisplayService |
| EVENT_ALARM_CANCELED | 报警取消 | AlarmService | BLEService, DisplayService |
| **音频事件** | | | |
| EVENT_AUDIO_PLAYBACK_START | 音频开始播放 | AudioDriver | AlarmService |
| EVENT_AUDIO_PLAYBACK_END | 音频播放结束 | AudioDriver | AlarmService |
| EVENT_AUDIO_ERROR | 音频播放错误 | AudioDriver | — |
| EVENT_TTS_REQUEST | TTS 播报请求 | ControlService/NavigationService | AudioService |
| EVENT_NAV_DISPLAY | 导航显示内容变更 | NavigationService | DisplayService |
| **电源事件** | | | |
| EVENT_BATTERY_READY | 电池电量数据就绪 | BatteryDriver | PowerService, BLEService, ControlService |
| EVENT_BATTERY_LOW | 低电量警告 | PowerService | AlarmService, DisplayService |
| EVENT_BATTERY_CRITICAL | 电量严重不足 | PowerService | AlarmService |
| EVENT_POWER_STATE_CHANGE | 功耗状态切换 | ControlService, PowerService | 各传感器, LightService |
| EVENT_MANUAL_ACTIVITY | 手动活动（按键/语音） | ControlService | PowerService |
| EVENT_SYSTEM_READY | 系统就绪 | main.py | DisplayService |
| EVENT_LIGHT_BLINK_STATE | 灯光闪烁状态 | LightService | ControlService |
| **GNSS 事件** | | | |
| EVENT_GPS_LOST | GPS 信号丢失 | GNSSDriver | AlarmService, DisplayService |
| **网络事件** | | | |
| EVENT_NETWORK_CONNECTED | 网络连接成功 | Network | — |
| EVENT_NETWORK_DISCONNECTED | 网络断开 | Network | — |
| EVENT_DATA_UPLOAD_SUCCESS | 数据上传成功 | CloudService | — |
| EVENT_DATA_UPLOAD_FAILED | 数据上传失败 | CloudService | — |
| **BLE 事件（Phase 4 新增）** | | | |
| EVENT_BLE_CONNECTED | BLE 连接成功 | BLEDriver | BLEService |
| EVENT_BLE_DISCONNECTED | BLE 断开连接 | BLEDriver | BLEService |
| EVENT_RIDE_CONTROL | BLE FFF3 控制指令 | BLEService | ControlService |
| EVENT_NAV_CMD | 导航指令 | BLEService | NavigationService |
| EVENT_BLE_ALARM_ACK | 报警确认 | BLEService | AlarmService |
| **控制系统事件（Phase 4 新增）** | | | |
| EVENT_VOICE_CMD | 语音指令 | VoiceDriver | ControlService |
| EVENT_CONTROL_STATE_CHANGED | 控制状态变更 | ControlService | BLEService |
| EVENT_LIGHT_CONTROL | 灯光控制指令 | ControlService | LightService |
| EVENT_VOLUME_CONTROL | 音量控制指令 | ControlService | AudioDriver |
| EVENT_ALARM_CONTROL | 报警控制指令 | ControlService | AlarmService |
| EVENT_SMS_PHONE_CONFIG | SMS 手机号配置 | ControlService | AlarmService |

### 3.4 模块清单

> 所有模块继承 `BaseModule`，实现 `init()` / `tick()` / `get_data()` / `get_status()` 四元组接口。

| 模块 | 文件 | 层级 | 状态 | 说明 |
|------|------|------|------|------|
| TempHumidDriver | Drivers/sensor/Temp_Humid.py | Device | ✅ | AHT20 温湿度，I2C1 |
| IMUDriver | Drivers/sensor/imu.py | Device | ✅ | LIS2DH12TR 加速度/陀螺仪，I2C1 |
| GNSSDriver | Drivers/sensor/Gnss.py | Device | ✅ | EC200U 内置 GNSS + LBS 基站定位 |
| LightSensorDriver | Drivers/sensor/Light.py | Device | ✅ | GL5528 光敏电阻，ADC PC5 |
| HeartRateDriver | Drivers/sensor/HeartRate.py | Device | ✅ 已集成 main.py | MKS SPO2-ZS-BLE 心率血氧，UART5 TX=PC12 RX=PD2（原方案 UART9 走不通，已切换至 UART5）|
| BatteryDriver | Drivers/sensor/Battery.py | Device | ✅ | 电池电压 ADC，6 档电量 |
| Button | Drivers/interface/Button.py | Device | ✅ | SOS 按键，GPIO + IRQ |
| VoiceDriver | Drivers/interface/Voice.py | Device | ✅ | ASRPRO 语音识别，UART hex 映射 |
| LEDDriver | Drivers/actuator/LED.py | Device | ✅ | LED_BLUE，Timer1 闪烁 |
| AudioDriver | Drivers/actuator/Audio.py | Device | ✅ | EC200U 音频，扬声器 J402 |
| LCDDriver | Drivers/actuator/LCD.py | Device | ✅ | ST7735 LCD，SPI1 |
| PWM_LED | Drivers/actuator/PWM_LED.py | Device | ✅ | PWM 调光大功率灯，PE11 TIM1_CH2 |
| BLEDriver | Drivers/network/BLE.py | Device | ✅ | EC200U BLE 4.2 GATT Server |
| Network | Drivers/network/Network.py | Device | ⚠️ 已废弃 | 4G 网络模组（不在 main.py） |
| MQTTDriver | Drivers/network/MQTT.py | Device | ⚠️ 已废弃 | MQTT 协议封装（不在 main.py） |
| SMSDriver | Drivers/network/SMS.py | Device | ✅ | EC200U 短信发送（quectel.SMS） |
| CollisionService | Modules/collision_service.py | Service | ✅ | 碰撞检测算法（多级阈值+防误报） |
| AudioService | Modules/audio_service.py | Service | ✅ v1 | 统一音频调度（优先级队列+超时丢弃） |
| AlarmService | Modules/alarm_service.py | Service | ✅ | 报警联动（声光+BLE+云端） |
| CloudService | Modules/cloud_service.py | Service | ⚠️ 已废弃 | MQTT 云端通信（不在 main.py，由 BLE 直连手机替代） |
| DisplayService | Modules/display_service.py | Service | ✅ | LCD 显示管理 |
| BLEService | Modules/ble_service.py | Service | ✅ v3 | 环形缓冲区、快照合并推送 |
| LightService | Modules/light_service.py | Service | ✅ v1 | 自适应灯光（光照→PWM 非线性映射） |
| ControlService | Modules/control_service.py | Service | ✅ v3 | 纯事件驱动、27 条指令（含 set_phone）、TTS、报警快照 |
| NavigationService | Modules/navigation_service.py | Service | ✅ v1 | 导航指令处理（腾讯地图 API） |
| PowerService | Modules/power_service.py | Service | ✅ v1 | 电源管理，6 档电量+自动省电切换 |
| SystemMonitor | Service | 非侵入式监控：心跳扫描 + WDT 门控 + 离线诊断 | ✅ v3 |

### 3.5 初始化顺序（两阶段）

**Phase A（开机画面优先显示）**：
1. LCD 驱动（LCDDriver）
2. 显示管理服务（DisplayService）→ 显示开机画面

**Phase B（后台初始化）**：
3. 传感器组：Temp_Humid → IMU → GNSS → Light → BatteryDriver
4. 执行器组：Button → LED → Audio → PWM_LED → BLE → SMS
5. 心率组：HeartRate（必须在所有 quectel 模块之后）
6. 服务组：CollisionService → AudioService → AlarmService → ControlService → PowerService → LightService → BLEService → NavigationService → Voice → SystemMonitor

**设计原因**：Phase A 让用户尽快看到开机画面（LCD 硬件自主刷新不阻塞后台 init）；HeartRate UART9 在所有 quectel 模块之后避免破坏 AT 通道；SystemMonitor 最后初始化确保所有模块就绪后再启动监控。

**SystemMonitor 说明**：非侵入式监控层（24 个模块心跳扫描 + WDT 8s 门控 + 离线模块诊断）。15s 启动宽限期内无条件喂狗，之后需所有 CRITICAL 模块心跳有效才喂狗。连续 5 次 WDT 复位进入安全模式。

**依赖注入**：Service 层模块通过构造函数注入 Device 层引用（如 `AlarmService(event_bus, led=led, audio=audio)`），禁止 Service 间直接引用。

### 3.6 WDT 硬件看门狗

| 参数 | 值 |
|------|----|
| 超时时间 | 8000ms（8 秒） |
| 启动时机 | 系统就绪后（main.py Phase B 完成） |
| 门控逻辑 | SystemMonitor.should_feed_wdt() |
| 宽限期 | 启动后 15s 无条件喂狗 |
| 安全模式 | 连续 5 次 WDT 复位后进入 |

实现位置：`main.py:164-170`（启动）、`main.py:180-181`（主循环喂狗）、`system_monitor.py`（门控逻辑）。

---

## 4. 目录结构

```
SmartRidingHelmet_New/
│
|—— 00_Planning/                 # 项目规划
|── 01_Hardware/                 # 硬件相关
│
|—— 02_Software/                 # 🌟 软件代码区（架构与业务融合层）
│   ├── core/                    # 框架与基础设施层
│   │   ├── main.py              # 系统入口 & 主循环调度
│   │   ├── config.py            # 全局配置（阈值、网络参数、事件名常量）
│   │   ├── Event_Bus.py         # 事件总线实现
│   │   └── Base_Module.py       # 四元组模块基类（规范契约）
│   │
│   ├── Drivers/                 # 设备适配层（Device层）
│   │   ├── sensor/
│   │   │   ├── Temp_Humid.py    # 温湿度（AHT20）
│   │   │   ├── imu.py           # 加速度/陀螺仪
│   │   │   ├── Gnss.py          # GNSS定位（注意：文件名首字母大写）
│   │   │   ├── Light.py         # 光照（GL5528 ADC）
│   │   │   ├── Battery.py       # 电池电量 ADC
│   │   │   ├── HeartRate.py     # v2 新增，UART5 心率血氧
│   │   │   └── LBS.py           # 基站定位（未集成 main.py）
│   │   ├── actuator/
│   │   │   ├── LED.py           # LED指示灯
│   │   │   ├── Audio.py         # EC200U 音频输出
│   │   │   ├── LCD.py           # ST7735 LCD 显示屏
│   │   │   └── PWM_LED.py       # PWM调光LED驱动（18W大功率灯）
│   │   ├── interface/
│   │   │   ├── Button.py        # SOS按键
│   │   │   └── Voice.py         # 语音指令（ASRPRO UART hex 映射）
│   │   └── network/
│   │       ├── Network.py       # ⚠️ 已废弃（不在 main.py）
│   │       ├── MQTT.py          # ⚠️ 已废弃（不在 main.py）
│   │       ├── BLE.py           # BLE蓝牙GATT Server（纯硬件接口）
│   │       ├── SMS.py           # EC200U 短信发送
│   │       ├── Qth.py           # ⚠️ 已废弃（移远云 SDK）
│   │       └── thread_queue.py  # 线程安全队列
│   │
│   ├── Modules/                 # 业务服务层（Service层）
│   │   ├── collision_service.py # 碰撞检测算法
│   │   ├── alarm_service.py     # 报警联动逻辑
│   │   ├── cloud_service.py     # 云端通信与数据上报（MQTT）
│   │   ├── lark_cloud.py        # 移远云通信（Qth SDK）
│   │   ├── ble_service.py       # BLE推送服务
│   │   ├── display_service.py   # 显示管理服务
│   │   ├── light_service.py     # 自适应灯光服务
│   │   ├── control_service.py   # 统一控制服务（BLE远端+语音）
│   │   ├── power_service.py     # 电源管理
│   │   └── navigation_service.py# 【v2】导航引导服务
│   │
│   └── Tests/                   # 单元测试与集成测试
│       ├── test_*.py             # 各模块测试脚本（单模块/集成/E2E）
│       └── miniprogram/          # 小程序端测试
│
|—— 03_Integration/              # 🌟 系统集成与验证
│   ├── Integration_Plans.md     # 集成测试方案（定义步骤与验收标准）
│   ├── Test_Reports/            # 集成测试记录（问题与解决）
│   │   ├── 2026-XX-XX_SOS_Alarm.md
│   │   └── 2026-XX-XX_Data_Upload.md
│   └── Final_Demo_Script.py     # 最终演示脚本
│
|—— 04_Docs_for_Competition/     # 比赛提交文档
│   ├── Design_Report/           # 设计报告（含原理、方案）
│   ├── Presentation/            # 答辩PPT与视频
│   └── Open_Source/             # 开源代码包（按要求整理）
│
|—— 05_Tools_and_Scripts/        # 开发辅助工具
│   ├── flash_firmware.bat       # 固件烧录脚本
│   ├── sim_test_data.py         # 生成模拟传感器数据
│   └── connectlab_setup.md      # ConnectLab测试平台配置
│
|—— .gitignore
└── README.md                    # 项目快速启动指南
```

---

## 5. 开发规范

### 5.1 必须遵守的规则

| 规则 | 说明 | 原因 |
|------|------|------|
| 使用config常量 | 禁止硬编码事件名和阈值 | 统一管理，易于修改 |
| 通过EventBus通信 | 模块间禁止直接调用 | 松耦合，独立可测 |
| tick快速返回 | 必须<5ms，不能阻塞 | 主循环流畅，不漏采数据 |
| 封装状态数据 | 禁止全局变量 | 避免冲突，线程安全 |
| 异常捕获 | tick()中必须捕获异常 | 不让主循环崩溃 |

### 5.2 错误示例 vs 正确示例

**❌ 错误：全局变量**
```python
temperature = 0  # 全局变量

def read_sensor():
    global temperature
    temperature = sensor.read()
```

**✅ 正确：封装在对象内**
```python
class TempHumidDriver:
    def __init__(self):
        self._data = {"temp": 0.0}  # 封装在对象内
    
    def tick(self):
        self._data["temp"] = self.sensor.read()
```

**❌ 错误：直接调用**
```python
def on_collision():
    alarm.start()  # 直接调用
    cloud.send()   # 直接调用
```

**✅ 正确：事件驱动**
```python
def on_collision():
    event_bus.publish(COLLISION_DETECTED, data)  # 发布事件
```

**❌ 错误：tick中阻塞**
```python
def tick(self):
    time.sleep(1)  # 阻塞1秒
```

**✅ 正确：时间片控制**
```python
def tick(self):
    if time.ticks_diff(now, last_tick) < 1000:
        return  # 未到时间，立即返回
```

---

## 6. 架构收益

### 6.1 对开发的好处

| 收益 | 说明 |
|------|------|
| **独立开发** | 每个模块独立，多人并行开发不冲突 |
| **独立测试** | 单模块测试 + 集成测试，逐级验证 |
| **易于集成** | 接口统一、事件驱动，集成时无意外 |
| **易于维护** | 四元组结构清晰，状态数据封装 |

### 6.2 对项目的收益

| 收益 | 说明 |
|------|------|
| **可复用** | Device对象可被多个Service使用 |
| **可替换** | 更换硬件只需修改Device层实现 |
| **可扩展** | 新增功能只需新增模块和事件订阅 |
| **可集成** | 依赖明确、初始化有序，集成稳定 |

---

**文档版本**：v7.6
**更新日期**：2026-06-29
**维护团队**：锦依卫队
**备注**：Phase 4 代码完成。HeartRate 使用 UART5（原 UART9 方案走不通已切换）。CloudService/Network/MQTT 已废弃，数据通道改为 BLE 直连手机。文档同步修正（以代码为准）。
