# 智能骑行头盔 SmartRidingHelmet

> 基于 STM32F413ZH + Quectel EC200U 的智能骑行安全装备  
> MicroPython 固件 · 微信小程序 BLE 直连 · SMS 紧急报警

---

## 项目简介

智能骑行头盔集成环境感知、碰撞检测、安全预警、BLE 近场通信、语音交互和自适应灯光控制功能。骑行途中实时监测碰撞风险，自动触发声光报警并通过短信通知紧急联系人；微信小程序通过 BLE 直连接收实时传感器数据，下发导航指令和骑行控制。

**硬件平台**：移远 UniKnect Kit GEN-1 Pro（NUCLEO-F413ZH + EC200U 4G/GNSS/BLE）  
**软件环境**：MicroPython（移远定制固件）· 微信小程序（uniapp）  
**开发工具**：Thonny IDE（固件）· 微信开发者工具（小程序）  
**代表队**：锦依卫队

---

## 核心功能

| 分类 | 功能 | 状态 |
|------|------|:----:|
| 🛡️ 安全预警 | 碰撞自动报警（30s 超时 / Level 3 升级 SOS） | ✅ |
| 🛡️ 安全预警 | 一键 SOS 求助（SMS + 声光 + BLE） | ✅ |
| 🛡️ 安全预警 | 本地声光报警（LCD 红闪 + 蜂鸣 + TTS） | ✅ |
| 🛡️ 安全预警 | 低电量提醒 | ✅ |
| 📡 传感采集 | 温湿度（AHT20 I2C） | ✅ |
| 📡 传感采集 | 碰撞检测（LIS2DH12TR 加速度计 + 三级判决） | ✅ |
| 📡 传感采集 | 位置与速度（EC200U GNSS / LBS 基站定位） | ✅ |
| 📡 传感采集 | 环境光照（GL5528 ADC，自适应背光 + 大灯） | ✅ |
| 📡 传感采集 | 心率血氧（MKS SPO2-ZS-BLE UART，外接模块） | ✅ |
| 📱 BLE 通信 | 传感器数据实时推送（Notify, FFF1） | ✅ |
| 📱 BLE 通信 | 导航指令下发（Write, FFF2，小程序 → 头盔 TTS） | ✅ |
| 📱 BLE 通信 | 骑行控制指令（Write, FFF3，灯光/音量/省电） | ✅ |
| 📱 BLE 通信 | 报警确认（Write, FFF4，关闭报警/确认安全） | ✅ |
| 🗣️ 语音交互 | 本地语音指令识别（ASRPRO UART，26 条指令） | ✅ |
| 💡 灯光控制 | 大功率 PWM 调光（PE11/TIM1_CH2, 18W） | ✅ |
| 🔋 电源管理 | 四模式切换（ACTIVE/SUSPENDED/EMERGENCY/CUSTOM） | ✅ |
| 🖥️ 显示 | LCD 开机动画 + 传感器数据 + 报警画面（ST7735 SPI） | ✅ |

---

## 系统架构

### 硬件拓扑

```
STM32 NUCLEO-F413ZH (MCU)
  ├── UniKnect Gen1-PRO 扩展板
  │   ├── Quectel EC200U (4G + GNSS + BLE 4.2 + Audio)
  │   ├── AHT20 温湿度 (I2C1, 0x38)
  │   ├── LIS2DH12TR 加速度计 (I2C1, 0x19)
  │   ├── GL5528 光敏电阻 (ADC, PC5)
  │   └── SIM 卡槽 + 扬声器接口 (J402, 8Ω/800mW)
  ├── ST7735 LCD (SPI1, DC=F12, CS=D14)
  ├── PWM_LED 大灯 (PE11, TIM1_CH2)
  ├── SOS 按键 (GPIO SW)
  ├── ASRPRO 语音识别模块 (UART)
  └── MKS SPO2-ZS-BLE 心率模块 (UART9)
```

### 四层软件架构

```
App 层 (main.py + config.py)     →  系统入口、主循环调度
  ↓ 单向依赖
Service 层 (Modules/)            →  业务逻辑：碰撞/报警/导航/灯光/电源
  ↓ 单向依赖
Device 层 (Drivers/)             →  硬件封装：传感器/执行器/网络/BLE
  ↓ 单向依赖
Vendor 层 (machine, quectel)     →  只读固件，禁止修改
```

**关键约束**：
- ❌ 跨层调用 | ❌ 模块间直接调用 | ❌ 全局变量  
- ✅ 事件驱动通信（EventBus 发布/订阅）| ✅ tick() < 5ms | ✅ 状态封装在模块对象内

### BLE 通信架构

```
手机微信小程序 (Central)
  ↕ BLE 4.2
EC200U 内置 BLE (GATT Server, 广播名: SmartHelmet-66ccff)
  ├── FFF1 (NOTIFY): 头盔 → 手机传感器数据（压缩 JSON）
  ├── FFF2 (WRITE):  手机 → 头盔导航指令
  ├── FFF3 (WRITE):  手机 → 头盔骑行控制
  └── FFF4 (WRITE):  手机 → 头盔报警确认
```

---

## 目录结构

```
SmartRidingHelmet_New/
├── 00_Planning/          # 需求文档 + 架构设计 + 硬件手册
├── 01_Hardware/          # 原理图 + PCB + 机械设计
├── 02_Software/          # 主代码仓
│   ├── core/             #   main.py, config.py, EventBus, BaseModule
│   ├── Drivers/          #   传感器/执行器/网络驱动 (Device 层)
│   ├── Modules/          #   业务服务 (Service 层)
│   ├── Tests/            #   模块测试 + 集成测试 + 压力测试
│   ├── WeChatMiniProgram/#   微信小程序 (uniapp)
│   └── dev_log.md        #   开发日志
├── 03_Integration/       # 集成测试 + 压力测试脚本
├── 04_Docs_for_Competition/  # 竞赛文档
├── 05_Tools_and_Scripts/     # 工具脚本
├── examples/             # 移远 MicroPython 参考示例 (36 个)
└── AGENTS.md             # AI Agent 工作指南
```

---

## 快速开始

### 1. 硬件准备

- NUCLEO-F413ZH 开发板 + UniKnect Gen1-PRO 扩展板
- SIM 卡（SMS 报警功能需要）
- 可选外设：MKS SPO2-ZS-BLE 心率模块、ASRPRO 语音模块

### 2. 固件烧录

```bash
# 将 02_Software/ 目录下文件通过 Thonny IDE 上传到设备
# 同步前需执行 Thonny 瘦身（去掉 docstring + f-string 转 % 格式）
# 参考: 02_Software/thonny/ 目录
```

### 3. 运行

设备上电后自动运行 `main.py`：
1. **Phase A**（~500ms）：LCD 显示开机动画
2. **Phase B**（~3-5s）：后台初始化 24 个模块，开机画面持续显示
3. **就绪**：进入主循环（tick → EventBus.pump → sleep_ms(10)），WDT 8s 启动

### 4. 连接微信小程序

1. 微信开发者工具打开 `02_Software/WeChatMiniProgram/`
2. 手机蓝牙开启，扫描 `SmartHelmet-66ccff` 设备
3. 连接后可查看实时数据、下发导航、控制灯光/音量

### 5. 运行测试

```bash
# 所有测试必须在真实设备上运行（无 PC 模拟环境）
# 将测试文件上传到设备，通过 Thonny IDE 运行
# 测试指南: 02_Software/Tests/测试指南.md
```

---

## 模块状态

| 层级 | 模块 | 状态 |
|------|------|:----:|
| **Core** | main.py, config.py, EventBus, BaseModule | ✅ |
| **传感器** | TempHumid (AHT20 I2C) | ✅ |
| | IMU (LIS2DH12TR) | ✅ |
| | GNSS (EC200U 内置) | ✅ |
| | Light (GL5528 ADC) | ✅ |
| | Battery (ADC) | ✅ |
| | HeartRate (UART9, MKS SPO2) | ✅ |
| **执行器** | LCD (ST7735 SPI) | ✅ |
| | LED (GPIO D3) | ✅ |
| | Audio (EC200U) | ✅ |
| | PWM_LED (PE11 TIM1_CH2) | ✅ |
| **接口** | Button (GPIO SW) | ✅ |
| | Voice (ASRPRO UART) | ✅ |
| **网络** | BLE (EC200U 内置) | ✅ |
| | SMS (EC200U) | ✅ |
| | Network (EC200U 4G) | ✅ |
| **服务** | DisplayService (开机动画 + 数据显示) | ✅ |
| | CollisionService (三级碰撞判决) | ✅ |
| | AlarmService (报警联动) | ✅ |
| | ControlService (27 指令统一控制) | ✅ |
| | PowerService (四模式 + 手动锁定) | ✅ |
| | LightService (自适应灯光) | ✅ |
| | BLEService (GATT 服务 + 双线程) | ✅ |
| | NavigationService (TTS 导航播报) | ✅ |
| | AudioService (TTS 队列 + 优先级) | ✅ |
| | VoiceService (语音指令调度) | ✅ |
| | SystemMonitor (24 模块心跳 + WDT) | ✅ |

---

## 测试与质量

| 测试类型 | 状态 |
|----------|:----:|
| 30 分钟有 SIM 压力测试（173/173 ops, WDT=0, 23/23 在线） | ✅ |
| 30 分钟无 SIM 压力测试 v3（192/193 ops, Audio 错误=0） | ✅ |
| 4 项边界测试（I2C 争用 / 报警切电源 / SOS 快速取消 / 队列溢出） | ✅ |
| 模块单元测试（20+ 文件） | ✅ |
| 集成测试（8+ 文件） | ✅ |

---

## 关键设计决策

- **事件驱动松耦合**：模块间禁止直接调用，所有通信通过 EventBus 发布/订阅
- **两阶段启动**：Phase A 先显示开机画面（<500ms），Phase B 后台初始化模块
- **双线程 BLE/网络**：主线程收事件缓存，后台线程发送，不阻塞主循环
- **GNSS/LBS 自动切换**：无 GNSS 信号自动降级为 LBS 基站定位，三段退避策略
- **AT_LOCK 互斥锁**：使用 `_thread.allocate_lock()` 保护 EC200U AT 通道，GNSS 非阻塞，Audio/SMS 阻塞
- **三级碰撞判决**：多级阈值 + 防误报鉴别器，区分正常颠簸与真实碰撞
- **_manual_locked 手动锁定**：用户手动操作后永久禁止自动省电，防止调亮度后被系统覆盖
- **TTS 优先级**：报警音频 > TTS 播报；报警期间 AudioDriver 拒绝 TTS 请求

---

## 开发指南

- **开发环境**：Thonny IDE（固件）+ 微信开发者工具（小程序）
- **测试要求**：所有测试在真实设备上运行，无 PC 模拟环境
- **提交规范**：Conventional Commits（`feat`/`fix`/`docs`/`test`/`refactor`/`chore`）
- **文档同步**：修改模块后同步更新架构文档、模块实现文档、测试指南
- **AI Agent 工作指南**：[AGENTS.md](./AGENTS.md)

---

**版本**：v3.6 | **更新**：2026-07-25 | **代表队**：锦依卫队
