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

### 3.3 项目事件定义

**传感器事件**：

| 事件名 | 触发时机 | 携带数据 |
|--------|----------|----------|
| `TEMP_HUMID_READY` | 温湿度采集完成 | temp, humid, valid |
| `IMU_DATA_READY` | 加速度数据就绪 | acc_x, acc_y, acc_z |
| `SENSOR_ERROR` | 传感器故障 | source, error |

**业务事件**：

| 事件名 | 触发时机 | 携带数据 |
|--------|----------|----------|
| `COLLISION_DETECTED` | 检测到碰撞 | acc_data, confidence |
| `SOS_BUTTON_PRESSED` | SOS按键按下 | timestamp |
| `ALARM_TRIGGERED` | 报警启动 | alarm_type |

**系统事件**：

| 事件名 | 触发时机 | 携带数据 |
|--------|----------|----------|
| `SYSTEM_READY` | 系统启动完成 | modules_count |
| `CONFIG_UPDATE` | 配置更新 | target, params |

---

## 4. 目录结构

```
SmartRidingHelmet-TeamX/
│
|—— 00_Planning/                 # 项目规划
|── 01_Hardware/                 # 硬件相关
│
|—— 02_Software/                 # 🌟 软件代码区（架构与业务融合层）
│   ├── core/                    # 框架与基础设施层
│   │   ├── main.py              # 系统入口 & 主循环调度
│   │   ├── config.py            # 全局配置（阈值、网络参数、事件名常量）
│   │   ├── Event_Bus.py         # 事件总线实现
│   │   ├── Base_Module.py       # 四元组模块基类（规范契约）
│   │   └── utils/               # 工具函数（日志封装、数据校验、时间处理）
│   │
│   ├── Drivers/                 # 设备适配层（Device层）
│   │   ├── sensor/
│   │   │   ├── Temp_Humid.py    # 温湿度（AHT20）
│   │   │   ├── imu.py           # 加速度/陀螺仪
│   │   │   └── gnss.py          # GNSS定位
│   │   ├── actuator/
│   │   │   ├── buzzer.py        # 蜂鸣器
│   │   │   └── led.py           # LED指示灯
│   │   ├── interface/
│   │   │   └── button.py        # SOS按键
│   │   └── network/
│   │       ├── cellular.py      # 4G网络模组
│   │       └── mqtt_client.py   # MQTT协议封装
│   │
│   ├── Modules/                 # 业务服务层（Service层）
│   │   ├── collision_service.py # 碰撞检测算法
│   │   ├── alarm_service.py     # 报警联动逻辑
│   │   ├── cloud_service.py     # 云端通信与数据上报
│   │   └── power_service.py     # 电源管理与功耗调度
│   │
│   └── Tests/                   # 单元测试与Mock
│       ├── test_drivers/        # 驱动层独立测试
│       ├── test_modules/        # 业务层逻辑测试
│       └── mocks/               # 模拟硬件/MQTT服务器（供离线调试）
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

**文档版本**：v6.0  
**更新日期**：2026-05-05  
**维护团队**：锦依卫队
