# 智能骑行头盔 - 实现路线与设计方案

## 1. 系统架构设计

### 1.1 软件分层架构（基于官方示例模块与硬件）

* **底层驱动层（无需开发）**：移远 MicroPython 固件已集成
* **API接口层（直接调用）**：直接使用官方提供的 `peripherals`、`gnss`、`network`、`mqtt`、`lcd`、`thread`、`file`、`audio` 等示例模块，完成硬件交互与协议对接
* **业务逻辑层（自主开发）**：基于API层，编写碰撞判定算法、数据封装、状态机调度等核心业务代码

### 1.2 系统状态机设计

系统采用有限状态机(FSM)模型，避免主循环陷入混乱的逻辑判断：

* **INIT (初始化态)**：调用 `network` 附网，调用 `mqtt` 连接平台，调用 `peripherals` 初始化传感器。成功后进入RUNNING；超时则进入RUNNING（离线模式）
* **RUNNING (正常骑行态)**：周期采集数据并上传，实时监测碰撞和SOS按键
* **ALARM (报警态)**：触发后强制发送远程报警，驱动本地声光及语音报警。30秒无二次触发恢复RUNNING
* **SLEEP (休眠态)**：静止超时进入，降低采集频率断开网络。检测到震动中断唤醒回INIT

---

## 2. 核心模块实现路线

### 2.1 驱动层模块（传感器与执行器）

#### 2.1.1 温湿度驱动模块（Temp_Humid.py）

**需求对应**：F-SEN-01 温湿度采集

**模块功能**：
- 初始化 AHT20 传感器（I2C 通信）
- 周期读取温湿度数据（默认 2000ms 间隔）
- 数据清洗：过滤异常值、单位换算
- 发布温湿度数据就绪事件

**发布事件**：
- `EVENT_TEMP_HUMID_READY`：温湿度数据就绪，携带数据 `{temp, humid, valid, timestamp}`

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：远程配置更新（如修改采样间隔）

**硬件说明**：
- 传感器：AHT20（I2C 地址 0x38）
- 接口：I2C1 总线（S502 开关拨至 ARDU 侧）
- 参考示例：`examples/aht20.py`

---

#### 2.1.2 IMU 加速度驱动模块（IMU.py）

**需求对应**：F-SEN-02 碰撞状态检测

**模块功能**：
- 初始化 LIS2DH12TR 三轴加速度传感器（I2C 通信）
- 周期读取三轴加速度数据（x, y, z）
- 计算加速度总和
- 发布加速度数据就绪事件

**发布事件**：
- `EVENT_IMU_READY`：加速度数据就绪，携带数据 `{acc_x, acc_y, acc_z, acc_total, valid, timestamp}`

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：远程配置更新

**硬件说明**：
- 传感器：LIS2DH12TR（I2C 地址 0x19）
- 接口：I2C1 总线（S502 开关拨至 ARDU 侧）
- 参考示例：`examples/imu.py`

---

#### 2.1.3 GNSS 定位驱动模块（GNSS.py）

**需求对应**：F-SEN-03 位置与速度采集

**模块功能**：
- 初始化 GNSS 模块
- 周期读取定位数据（经纬度、海拔、速度、信号质量）
- 发布定位数据就绪事件

**发布事件**：
- `EVENT_GNSS_READY`：定位数据就绪，携带数据 `{latitude, longitude, altitude, speed_kmh, cog, signal_quality, valid, timestamp}`

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：远程配置更新

**硬件说明**：
- 模组：EC200U 内置 GNSS
- 接口：GNSS 天线接口 J102（需外接无源 GNSS 天线）
- 参考示例：`examples/gnss.py`

**技术要点**：
- `get_location()` 返回 `cog`（Course Over Ground）字段：对地航向，0-360 度，北为 0
- 参考：`00_Planning/doc/API/Network&GNSS&File-API参考手册.pdf` 第 16 页

---

#### 2.1.3.1 LBS 基站定位驱动模块（LBS.py）

**所属层次**：Device层（设备封装层）

**需求对应**：F-SEN-03 位置与速度采集（室内补充）

**当前状态**：✅ **v1 已实现**（2026-06-09）

**模块功能**：
- 封装 quectel.LBS API，提供室内基站定位能力
- 周期触发定位（默认 30s 间隔，15s 超时）
- 定位成功发布 `EVENT_LBS_READY`
- 与 GNSSDriver 互斥（EC200U 不能同时运行 GNSS 和 LBS）

**发布事件**：
- `EVENT_LBS_READY`：LBS 定位数据就绪，携带数据 `{latitude, longitude, accuracy, source, timestamp}`

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：配置更新

**公共接口**：
- `init()`：创建 LBS 实例
- `tick()`：周期调度定位
- `deinit()`：释放 LBS 资源
- `get_data()`：获取定位数据快照
- `get_status()`：获取模块运行状态

**硬件说明**：
- 模组：EC200U 内置 LBS
- 互斥约束：不能与 GNSSDriver 同时 init（EC200U 限制）

**分层设计说明**：
- Device 层封装 LBS API，不包含业务逻辑
- 定位为 GNSS 的室内补充方案

---

#### 2.1.4 光照驱动模块（Light.py）

**需求对应**：F-SEN-04 环境光照采集

**模块功能**：
- 初始化 ADC 读取光敏电阻
- 周期读取光照数据（直接读取ADC数据）
- 发布光照数据就绪事件

**发布事件**：
- `EVENT_LIGHT_READY`：光照数据就绪，携带数据 `{light_intensity, valid, timestamp}`

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：远程配置更新

**硬件说明**：
- 传感器：光敏电阻 GL5528（R316）
- 接口：ADC 引脚 PC5
- 参考示例：`examples/ldr.py`

---

#### 2.1.5 心率驱动模块（HeartRate.py）【v2 新增，待开发】

**所属层次**：Device层（设备封装层）

**需求对应**：F-HR-01 心率监测

**当前状态**：📅 **v2 计划**（等心率带硬件到货）

**数据通路**：

  数据统一走 MQTT 通道，与现有传感器数据上传方式一致。

**模块职责**（预留）：

- 周期读取心率值（bpm）
- 缓存最新心率，供 CloudService 拼入上传 JSON
- 异常心率（过高/过低）发布事件

**发布事件**（预留）：
- `EVENT_HEART_RATE_READY`：心率数据就绪，携带数据 `{bpm, valid, timestamp}`

**依赖**：

- 外接 ANT+/BLE 心率带（已采购，待到货）

---

#### 2.1.6 SOS 按键驱动模块（Button.py）

**所属层次**：Device层（设备封装层）

**需求对应**：F-ALM-02 一键SOS求助

**模块功能**（纯硬件检测）：
- 初始化按键GPIO外部中断（下降沿触发）
- 软件消抖处理（200ms）
- 按键按下时发布SOS事件

**发布事件**：
- `EVENT_BUTTON_PRESSED`：按键按下，携带数据 `{timestamp}`

**订阅事件**：无

**硬件说明**：
- 接口：Arduino D2 引脚（外部上拉，按下接地）
- 参考示例：`examples/pin.py`

**分层设计说明**：
- Device层负责硬件状态检测，发布事件通知Service层
- 不订阅任何事件，纯输入设备
- Service层（AlarmService）订阅EVENT_BUTTON_PRESSED，解释为SOS触发业务逻辑

---

#### 2.1.6 LED 驱动模块（LED.py）

**所属层次**：Device层（设备封装层）

**需求对应**：F-ALM-03 本地声光报警

**模块功能**（纯硬件控制，无业务逻辑）：
- 初始化LED GPIO
- 控制LED常亮
- 控制LED熄灭
- 控制LED闪烁（指定间隔）

**发布事件**：无

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：配置更新

**公共接口**（供Service层调用）：
- `on()`：LED常亮
- `off()`：LED熄灭
- `blink(interval_ms)`：LED闪烁（指定闪烁间隔）
- `set_brightness(level)`：设置亮度（如果支持PWM）

**硬件说明**：
- 接口：Arduino D3 引脚（外接LED）
- 参考示例：`examples/pin.py`

**分层设计说明**：
- Device层只提供基础硬件控制，不包含业务逻辑
- 不订阅业务事件（ALARM_TRIGGERED等），由Service层调用
- Service层（AlarmService）订阅业务事件后调用LED公共接口

---

#### 2.1.7 音频驱动模块（Audio.py）

**所属层次**：Device层（设备封装层）

**需求对应**：F-ALM-03 本地声光报警

**模块功能**（纯硬件控制，无业务逻辑）：
- 初始化音频硬件（quectel.Audio）
- 播放本地音频文件（MP3/WAV）
- TTS语音播报
- 停止播放
- 音量控制（TTS音量、扬声器音量、语速调节）
- 录音功能（可选）
- 播放状态回调处理

**发布事件**：
- `EVENT_AUDIO_PLAYBACK_START`：音频开始播放，携带数据 `{"type": "alarm", "file": "alarm.mp3", "timestamp"}`
- `EVENT_AUDIO_PLAYBACK_END`：播放完成，携带数据 `{"file": "alarm.mp3", "duration": 3000, "timestamp"}`
- `EVENT_AUDIO_ERROR`：音频播放失败，携带数据 `{"error": "file not found", "timestamp"}`

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：配置更新（音量/语速参数）

**公共接口**（供Service层调用）：
- `play_file(file_path)`：播放音频文件
- `play_tts(text)`：TTS语音播报
- `stop()`：停止播放
- `set_volume(volume)`：设置音量
- `start_record(file)`：开始录音
- `stop_record()`：停止录音

**硬件说明**：
- 接口：扬声器接口 J402（外接喇叭）
- 功放：EC200U 内置功放（8欧/800mW）
- 参考示例：`examples/audio.py`

**分层设计说明**：
- Device层只提供基础播放控制，不包含业务逻辑
- 不订阅业务事件（COLLISION_DETECTED等），由Service层调用
- Service层（AlarmService）负责业务逻辑，调用Audio的公共接口

---

#### 2.1.8 LCD 驱动模块（LCD.py）

**所属层次**：Device层（设备封装层）

**需求对应**：F-ALM-03 本地声光报警

**模块功能**（纯硬件控制，无业务逻辑）：
- 初始化LCD扩展板（SPI通信）
- 显示正常数据画面（温湿度、定位信息）
- 显示报警画面（红色SOS字样）
- 清屏操作
- 设置背光亮度

**发布事件**：无

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：配置更新

**公共接口**（供Service层调用）：
- `show_normal_data(temp, humid, lat, lon)`：显示正常骑行数据
- `show_alarm(alarm_type)`：显示报警画面（collision/sos）
- `clear()`：清屏
- `set_backlight(level)`：设置背光亮度

**状态锁说明**：
LCD 内部维护 `display_mode` 状态（normal / alarm），用于防止 Service 层间显示冲突：
- `show_alarm()` 调用时 → `display_mode` 设为 `alarm`
- `show_normal_data()` 调用时 → 检查 `display_mode`，如果是 `alarm` 则**拒绝更新**，保持报警画面
- 报警取消后 `clear()` → `display_mode` 恢复 `normal`
- `set_backlight()` 不受状态锁影响，任何时候都可调节背光

**硬件说明**：
- 硬件：LCD扩展板（1.8寸TFT）
- 接口：SPI总线
- 参考示例：`examples/lcd.py`

**分层设计说明**：
- Device层只提供基础显示控制，不包含业务逻辑
- 不订阅业务/数据事件（ALARM_TRIGGERED、TEMP_HUMID_READY等）
- Service层（AlarmService、CloudService）调用LCD公共接口更新显示

---

#### 2.1.9 PWM调光LED驱动模块（PWM_LED.py）

**所属层次**：Device层（设备封装层）

**需求对应**：F-LIGHT-01 大功率灯光调光控制

**当前状态**：✅ **v1 已实现**（2026-06-10）

**模块功能**（纯硬件控制，无业务逻辑）：

- 初始化PWM硬件（Timer + Channel）
- 通过PWM占空比控制LED亮度（0-100%）
- 支持功耗状态管理（休眠时自动熄灭）
- 错误检测与事件上报

**发布事件**：

- `EVENT_PWM_LED_ERROR`：PWM控制错误，携带数据 `{"module": "pwm_led", "error": "错误信息", "timestamp}`

**订阅事件**：

- `EVENT_CONFIG_UPDATE`：配置更新（功耗状态变化）

**公共接口**（供Service层调用）：

- `set_brightness(duty_cycle)`：设置LED亮度（占空比0-100）
  - `duty_cycle=0`：LED熄灭
  - `duty_cycle=50`：LED 50%亮度
  - `duty_cycle=100`：LED最亮
- `deinit()`：反初始化PWM资源

**核心特性**：

- **直接调光**：调用 `set_brightness()` 即可立即改变亮度，无需周期调度
- **占空比自动截断**：输入超出0-100范围会自动截断到边界值
- **功耗管理**：休眠状态时自动熄灭，唤醒后恢复
- **错误容错**：连续失败超过3次才上报错误事件

**硬件说明**：

- **引脚**：PE11（Arduino D5）
- **Timer**：TIM1（Timer 1）
- **Channel**：CH2（Channel 2）
- **PWM频率**：1000Hz（默认，可配置）
- **驱动方式**：直接驱动LED或通过MOSFET驱动大功率LED
- **参考示例**：`examples/pwm.py`

**分层设计说明**：

- Device层只提供基础PWM控制，不包含业务逻辑
- 不订阅业务事件，由Service层或主循环调用

**典型应用场景**：

1. **报警闪烁**：AlarmService调用 `set_brightness()` 实现闪烁效果（高亮→低亮循环）
2. **节能控制**：休眠时功耗状态变为SUSPENDED，LED自动熄灭
3. **手动调光**：通过外部指令直接调用 `set_brightness()` 控制亮度
---

#### 2.1.10 Qth 网络驱动模块（Qth.py）

**所属层次**：Device 层（网络通信驱动）

**当前状态**：✅ **v1 已实现**（2026-05-22 E2E 测试通过）

**模块功能**：封装移远云 Qth SDK 的 `init()` / `start()` / `sendTsl()` / `state()` 接口，供 LarkCloudService 调用

**公共接口**：
- `init()`：初始化 Qth SDK → 配置产品/设备信息 → 连接移远云
- `send_tsl(tsl_dict)`：上传物模型数据（网络 I/O，需在后台线程调用）
- `is_connected()`：查询与移远云的 MQTT 连接状态
- `tick()`：pass（Qth SDK 内置自动重连，无需主循环干预）

**降级策略**：
- 固件无 `Qth` 库时 `ImportError` 捕获 → `is_init=False`，所有调用静默跳过
- `sendTsl` 返回值可能不准确（实测返回 False 时数据仍可到达平台），以平台侧为准

**依赖**：
- `Qth` 库（移远固件内置）
- `core/config` 中的产品/设备凭证常量（`QTH_PRODUCT_ID`、`QTH_DEVICE_KEY` 等）

---

#### 2.1.11 BLE 蓝牙驱动模块（BLE.py）

**所属层次**：Device层（网络通信驱动）

**需求对应**：F-NET-04 BLE 近场通信（新增需求）

**当前状态**：✅ **v1 已实现**（2026-05-27 小程序端验证通过）

**模块功能**：
- 封装 quectel.BLE()，仅 GATT Server 角色（不扫描不连接其他设备）
- 注册 BLE GATT 服务（0xFFF0）及四个特征值（FFF1~FFF4）
- 事件驱动：通过 BLE 硬件回调处理连接/断开/MTU/数据写入事件
- 支持 BLE Notify 推送（FFF1 数据通道）
- 接收手机端写入数据（FFF2 导航、FFF3 控制、FFF4 报警确认）

**发布事件**：
- `EVENT_BLE_CONNECTED`：手机连接成功，携带数据 `{addr, timestamp}`
- `EVENT_BLE_DISCONNECTED`：手机断开连接，携带数据 `{timestamp}`
- `EVENT_NAV_CMD`：收到导航指令（FFF2 写入），携带数据 `{raw}`
- `EVENT_RIDE_CONTROL`：收到骑行控制指令（FFF3 写入），携带数据 `{raw}`
- `EVENT_BLE_ALARM_ACK`：收到报警确认（FFF4 写入），携带数据 `{raw}`

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：远程配置更新（MTU、功耗状态）

**公共接口**：
- `init()`：初始化 BLE → 注册 GATT 服务 → 开始广播
- `notify_data(json_str)`：通过 FFF1 发送 BLE Notify
- `exchange_mtu(mtu)`：请求 MTU 协商
- `stop()`：停止 BLE 并释放资源
- `tick()`：pass（BLE 为事件驱动，无需轮询）

**GATT 服务结构**：

| 特征值 | UUID | 属性 | 用途 |
|:------:|:----:|:----:|:-----|
| FFF1 | 0xFFF1 | Read/Write/Notify/Indicate | 数据推送通道（头盔→手机） |
| FFF2 | 0xFFF2 | Read/Write | 导航指令通道（手机→头盔） |
| FFF3 | 0xFFF3 | Read/Write | 骑行控制通道（手机→头盔） |
| FFF4 | 0xFFF4 | Read/Write | 报警确认通道（手机→头盔） |

所有特征值均有 CCCD 描述符（0x2902），最大长度 244 字节。

**硬件说明**：
- 模组：EC200U 内置 BLE 4.2
- 广播名：`SmartHelmet-66ccff`（config.py 中配置）
- 参考示例：`examples/ble.py`

**技术要点**：
- 事件驱动：tick() 为空，所有逻辑在 BLE 硬件回调（_callback）中处理
- MTU 回退：EC200U 可能在 EVT_CONNECTED 之前先发 EVT_MTU，驱动通过 `_connected_published` 标志位防止重复发布 `EVENT_BLE_CONNECTED`
- 连接回调在 modem 线程执行，`_callback()` 整体包裹 try/except 防止异常崩溃 BLE 协议栈
- 回调中不做阻塞 I/O
- Hex 解码：FFF2 写入的导航指令可能是 hex 编码字符串，驱动自动检测（清理空格/换行后校验 hex 格式）并解码为 UTF-8

**分层设计说明**：
- Device 层 BLEDriver 封装底层 BLE API，不包含业务逻辑
- 不订阅传感器事件，由 Service 层 BLEService 负责数据组装
- Service 层通过调用 `notify_data()` 发送数据

---

### 2.2 服务层模块（业务逻辑）

#### 2.2.1 碰撞检测服务（CollisionService.py）（✅ v1 已实现）

**需求对应**：F-ALM-01 碰撞自动报警

**模块功能**：
- 接收 IMU 加速度数据
- 判断是否发生真实碰撞（排除骑行颠簸误报）
- 检测到碰撞时发布碰撞事件

**发布事件**：
- `EVENT_COLLISION_DETECTED`：检测到碰撞，携带数据 `{acc_total, level, timestamp}`

**订阅事件**：
- `EVENT_IMU_READY`：接收加速度数据
- `EVENT_CONFIG_UPDATE`：远程配置更新（如修改碰撞阈值）

**实现要求**：
- 从 IMU 合加速度数据中识别真实碰撞，排除骑行颠簸误报
- 区分碰撞等级（如轻微/中等/严重），随事件发布
- 具体算法（阈值、窗口、滤波方式）由开发人员自行设计

---

#### 2.2.2 报警联动服务（AlarmService.py）（✅ v1 已实现）

**所属层次**：Service层（业务服务层）

**需求对应**：F-ALM-01 碰撞自动报警、F-ALM-02 一键SOS求助、F-ALM-03 本地声光报警

**模块功能**（业务逻辑编排）：
- 订阅碰撞事件和SOS按键事件
- 根据业务规则触发报警联动
- 调用Device层模块（LED、Audio）实现具体报警
- 报警超时管理
- 报警状态维护

**发布事件**：
- `EVENT_ALARM_TRIGGERED`：报警触发，携带数据 `{alarm_type, level, timestamp}`
- `EVENT_ALARM_CANCELED`：报警取消，携带数据 `{duration, timestamp}`

**订阅事件**：
- `EVENT_COLLISION_DETECTED`：碰撞事件，触发碰撞报警
- `EVENT_BUTTON_PRESSED`：按键事件，触发SOS报警
- `EVENT_BATTERY_LOW`：低电量事件，触发TTS语音提示
- `EVENT_BATTERY_CRITICAL`：电量严重不足，触发紧急TTS提示
- `EVENT_GPS_LOST`：GPS丢失事件，触发TTS语音提示
- `EVENT_CONFIG_UPDATE`：配置更新

**业务逻辑说明**：
- 接收碰撞/SOS/低电量/GPS丢失等事件，协调 LED、Audio 驱动完成报警联动
- 报警超时自动取消，恢复设备正常状态
- 碰撞等级（Level 1-3）映射到不同的报警表现（声/光强度），具体映射方式由开发人员决定

**约束规则**：
- **优先级**：SOS 报警 > 碰撞报警，执行中的报警可被更高优先级事件打断
- **重复触发**：同类型报警持续期间收到新触发，刷新超时计时，不重复播放报警音
- **等级联动**：严重碰撞（Level 3）自动触发 SOS 远程报警
- **可配置**：是否启用本地声光报警

**依赖关系**：
- 依赖Audio驱动（调用play_file、play_tts方法）
- 依赖LED驱动（调用blink、on、off方法）

**公共接口**：
- `cancel_alarm()`：外部取消报警（供 ControlService 调用），与内部 `_cancel_alarm()` 逻辑一致

**分层设计说明**：
- Service层负责业务逻辑编排和事件订阅
- 不直接操作硬件，通过调用Device层接口实现具体功能

---

#### 2.2.3 云端通信服务（CloudService.py）（✅ v1 已实现）

**所属层次**：Service层（业务服务层）

**需求对应**：F-NET-01 骑行数据远程上传、F-NET-02 紧急报警远程推送、F-NET-03 远程参数配置

**模块功能**（业务逻辑与数据上传）：
- 持有 NetworkDriver 和 MQTTDriver 实例，在独立网络线程中初始化和运行
- 通过 tick() 定时拼装传感器缓存数据，经线程安全队列送入网络线程发送
- 收到报警事件后切换为报警态 payload 持续入队发送，直到报警解除
- 接收云端 MQTT 下行配置，转发为 EVENT_CONFIG_UPDATE 事件

**发布事件**：
- `EVENT_DATA_UPLOAD_SUCCESS`：数据上传成功
- `EVENT_DATA_UPLOAD_FAILED`：数据上传失败
- `EVENT_NETWORK_CONNECTED`：网络连接成功
- `EVENT_NETWORK_DISCONNECTED`：网络断开

**订阅事件**：
- `EVENT_TEMP_HUMID_READY`：温湿度数据，缓存等待打包
- `EVENT_IMU_READY`：加速度数据，缓存等待打包
- `EVENT_GNSS_READY`：定位数据（含 latitude/longitude/altitude/speed_kmh/signal_quality），缓存等待打包
- `EVENT_ALARM_TRIGGERED`：报警触发事件，立即拼装报警 JSON 入队

**依赖关系**：
- 依赖 Network 封装（`Drivers/network/Network.py`，封装 quectel.Network）
- 依赖 MQTT 封装（`Drivers/network/MQTT.py`，封装 umqtt client）
- 依赖线程安全队列（`Drivers/network/thread_queue.py`）

**技术要点**：
- 上传触发：由 tick() 按 `CLOUD_UPLOAD_INTERVAL_MS`（默认 2000ms）定时触发，不依赖 GNSS 定位状态，室内无 GPS 时仍可上传温湿度和加速度
- 双线程架构：主线程（事件回调 → 拼装 JSON → 入队）与网络线程（出队 → MQTT publish）通过线程安全队列解耦，主线程不做任何网络 I/O
- 网络线程：使用 CloudService 持有的 NetworkDriver / MQTTDriver 实例（Service → Device），不在线程内创建
- 云端配置下发：通过 MQTT 回调在网路线程中接收，发布 `EVENT_CONFIG_UPDATE` 事件通知各模块
- SD 卡缓存（v2 计划）：断网时数据落 SD 卡，重连后补发。v1 暂不实现
- 未读到数据的字段在 JSON 中输出 null，如首次启动时 Temp/Humi/G-Sensor/GNSS 均为 null

**分层设计说明**：
- Service层负责数据打包和上传业务逻辑
- 持有 Device 层对象（NetworkDriver / MQTTDriver），调用其公共接口完成网络通信
- 订阅传感器数据事件，缓存后由 tick 定时触发打包
- 不直接操作网络硬件，通过 Device 层模块接口实现
- 不依赖 LCD 驱动（显示由 DisplayService 负责）

**骑行数据扩展**：

累计计算（总里程、累计爬升、最高速度等）移至**小程序端**实现。头盔 CloudService 仅传输原始 GNSS 点位（`latitude`、`longitude`、`altitude`、`speed_kmh`），小程序端接收后：
- 逐点 Haversine 累加总里程
- 逐点海拔正差值累加总爬升
- 跟踪最高速度
- 记录骑行时长（第一条数据到最新一条的时间差）

---

#### 2.2.8 移远云通信服务（LarkCloudService）（✅ **v1 已实现**）

**所属层次**：Service 层（业务服务层）

**需求对应**：F-NET-01 骑行数据远程上传（新增移远云 Qth 通道）

**当前状态**：✅ **v1 已实现**（2026-05-22 E2E 测试通过）

> ⚠️ 单模块测试 11/12、集成测试因 MicroPython 线程兼容问题暂未完全通过，但不影响 E2E 真实硬件环境运行

**模块功能**：
- 使用 Qth SDK 接入移远云平台（`iot-south.quectelcn.com:1883`）
- 与 CloudService（ConnectLab）并存，订阅相同的传感器事件
- tick() 拼装 TSL 物模型数据 → 线程安全队列 → 网络线程调用 QthDriver.sendTsl()
- 报警时上传 alarm_type + alarm_level（ID 6/7）

**TSL 物模型**：

属性列表：

| 功能ID | 功能类型 | 功能名称 | 标识符 | 数据类型 | 读写类型 |
|:------:|:--------|:---------|:-------|:--------|:--------|
| 1 | 属性 | 温度 | temperature | float | 只读 |
| 2 | 属性 | 湿度 | humidity | float | 只读 |
| 3 | 属性 | 速度 | speed | float | 只读 |
| 4 | 属性 | 纬度 | latitude | float | 只读 |
| 5 | 属性 | 信号质量 | signal_quality | enum | 只读 |
| 6 | 属性 | 报警类型 | alarm_type | enum | 只读 |
| 7 | 属性 | 报警等级 | alarm_level | int | 只读 |
| 8 | 属性 | 经度 | longitude | float | 只读 |
| 9 | 属性 | 海拔 | altitude | float | 只读 |

> **数据结构体（location）因 Qth SDK 不支持嵌套而拆为 3 个独立 float**：ID 4（纬度）、ID 8（经度）、ID 9（海拔）

**报警态数据分离**：
- 常态上传：ID 1~5, 8, 9（温湿度 + 速度 + 位置 + 信号质量）
- 报警态上传：仅 ID 4~9（位置 + 信号质量 + 报警类型/等级），不传温湿度和速度以减少传输量

**线程模型**：
- 主线程：收事件 → 缓存 → tick() 拼装 TSL → `send_queue.put()`
- 网络线程：`send_queue.get()` → `QthDriver.send_tsl()`（Qth SDK 自动管理 MQTT 重连）

**分层设计说明**：
- Service 层 LarkCloudService 负责数据打包和上传业务逻辑
- 持有 Device 层 QthDriver 实例，调用其 `send_tsl()` 接口完成上传
- QthDriver 封装 Qth SDK 的 `init()` / `sendTsl()` / `state()` 接口
- Qth SDK 内部管理 MQTT 连接和自动重连，LarkCloudService 无需自行管理网络线程重连
- 不依赖 NetworkDriver / MQTTDriver（Qth SDK 内置通信）

**降级策略**：
- 固件无 Qth 库时 `ImportError` 捕获 → 模块静默跳过，不影响其他模块
- 移远云不可达时网络线程跳过发送，数据留在队列中等待恢复

---

#### 2.2.9 BLE 推送服务（BLEService）（✅ v1 已实现）

**所属层次**：Service层（业务服务层）

**需求对应**：F-NET-04 BLE 近场通信

**当前状态**：✅ **v1 已实现**（2026-05-27 小程序端验证通过）

**模块功能**：
- 订阅传感器事件，缓存最新数据
- tick() 定时组装合并 JSON → 线程安全队列 → 后台线程调用 BLEDriver.notify_data()
- 报警事件立即入队推送（不等 tick 周期）
- 连接后立即推送一次最新数据（force_push）
- 心跳保活（5 秒间隔）

**发布事件**：无（纯消费/转发）

**订阅事件**：
- `EVENT_BLE_CONNECTED`：连接成功，设置 force_push
- `EVENT_BLE_DISCONNECTED`：断开连接，停止推送
- `EVENT_TEMP_HUMID_READY`：缓存温湿度
- `EVENT_IMU_READY`：缓存加速度（暂不推送）
- `EVENT_GNSS_READY`：缓存定位数据
- `EVENT_LIGHT_READY`：缓存光照数据
- `EVENT_ALARM_TRIGGERED`：立即推送报警 JSON
- `EVENT_ALARM_CANCELED`：立即推送报警取消 JSON
- `EVENT_CONTROL_STATE_CHANGED`：控制状态变更，推送到小程序

**BLE JSON 协议**（手机端接收）：

| type (t) | 含义 | 数据字段 (d) |
|:--------:|:-----|:-------------|
| 0 | 合并传感器数据 | `{tmp, hum, lat, lon, spd, alt, cog, lux}` |
| 5 | 报警触发 | `{a:1, l:2}` (a: 1=碰撞, 2=SOS; l: 级别) — 压缩格式，15 字节 |
| 6 | 报警取消 | `{}` |
| 7 | 控制状态 | `{lm:"auto", lb:50, vol:5, pm:"active"}` |
| 99 | 心跳 | `{s: "ok"}` |

**依赖关系**：
- 依赖 BLEDriver（调用 `notify_data()` 接口）
- 依赖 ThreadSafeQueue（线程安全队列）
- 依赖 EventBus（订阅传感器和报警事件）

**技术要点**：
- 双线程架构：主线程（事件回调 → 缓存 → tick() 组装 JSON → 入队）与通知线程（出队 → BLE notify）通过线程安全队列解耦
- 上传间隔：`BLE_UPLOAD_INTERVAL_MS`（默认 2000ms）
- 心跳间隔：`BLE_KEEPALIVE_MS`（默认 5000ms）
- IMU 数据缓存但暂不推送（碰撞结果由 AlarmService 通过 t:5 推送）
- 断连时自动清空发送队列，防止重连后发送过期数据
- 后台线程熔断机制：连续失败 10 次后暂停发送，重连时重置
- `deinit()` 等待后台线程退出（最多 700ms），避免 use-after-free

**分层设计说明**：
- Service 层负责数据组装和推送策略
- 持有 Device 层 BLEDriver 实例，调用其 `notify_data()` 接口
- 不直接操作 BLE 硬件，通过 Device 层模块接口实现

---

#### 2.2.4 电源管理服务（PowerService.py）

**当前状态**：⏳ **v2 计划**（等待电池供电硬件就绪）

当前开发阶段使用 USB 双线供电（EC200U Type-C + Nucleo Micro-USB），无法读取真实电池电量，因此 PowerService 暂不实现。

后续若接入锂电池（18650 + 5V 升压模块），需在电源输出端加分压电路到空闲 ADC 引脚，然后在本模块的 tick() 中周期读取 ADC 值换算电量。

**发布事件**（预留）：
- `EVENT_BATTERY_LOW`：电量低于警告阈值
- `EVENT_BATTERY_CRITICAL`：电量严重不足
- `EVENT_POWER_STATE_CHANGE`：功耗状态切换

**订阅事件**（预留）：
- `EVENT_CONFIG_UPDATE`：远程配置更新

**实现要求**（预留）：
- 周期读取电池电量（ADC 分压或 AT+CBC），低于阈值时发布对应事件
- 检测到严重低电量时，通知系统进入低功耗模式
- 具体阈值和采样周期由开发人员根据电池特性决定

**分层设计说明**：
- Service层负责电量状态判断和业务逻辑
- 发布电量事件通知其他Service层模块（AlarmService）
- 不直接操作硬件，通过ADC或AT指令读取电量

---

#### 2.2.5 显示管理服务（DisplayService.py）（✅ v1 已实现）

**所属层次**：Service层（业务服务层）

**需求对应**：F-SEN-04 环境光照采集（背光调节）

**模块功能**（业务逻辑与显示管理）：
- 启动时显示开机画面（队伍 Logo + 队名 + TTS 语音播报）
- 定义正常骑行状态的 LCD 画面布局（温湿度/定位/速度等信息的显示位置和格式）
- 报警时联动切换画面（碰撞/SOS 画面由 DisplayService 订阅 `EVENT_ALARM_TRIGGERED` 后调用 LCD 接口实现，背光调节等协调配合）
- 根据环境光照强度自动调节 LCD 背光
- 系统休眠时关闭背光（接口预留）

**发布事件**：无

**订阅事件**：
- `EVENT_TEMP_HUMID_READY`：温湿度数据，用于判断系统是否正常运行
- `EVENT_GNSS_READY`：定位数据，用于判断定位是否有效
- `EVENT_LIGHT_READY`：光照数据就绪，调节背光
- `EVENT_ALARM_TRIGGERED`：报警触发，可配合调整背光或显示策略
- `EVENT_ALARM_CANCELED`：报警取消，恢复正常显示策略
- `EVENT_POWER_STATE_CHANGE`：功耗状态变化，控制背光开关（接口预留）

**依赖关系**：
- 依赖 Light 驱动（订阅光照事件）
- 依赖 LCD 驱动（调用 show_image/show_string、set_backlight、show_normal_data、show_alarm、clear 等方法）
- 依赖 Audio 驱动（开机画面播放 TTS 语音）

**实现要求**：

开机画面（init() 末尾执行）：
1. LCD 显示队伍 Logo（RGB565 取模数据，存放于 `team_logo.py`）
2. LCD 显示队伍名称
3. Audio TTS 播报系统就绪提示语（`TTS_SYSTEM_READY`）
4. 保持 2~3 秒后清屏，进入正常运行

正常画面策略：
- 定义 LCD 屏幕各信息区域的布局（如：顶部显示温湿度、中部显示定位、底部显示速度）
- CloudService 调用 `lcd.show_normal_data()` 时按此布局渲染

报警画面配合：
- 报警触发时 LCD 状态锁自动拦截正常数据刷新，DisplayService 不干预，但可配合调整背光（如报警时提高背光亮度）
- 报警取消后 LCD 恢复 normal 模式

背光调节：
- 收到 `EVENT_LIGHT_READY` 后根据光照强度调节 LCD 背光亮度
- 具体光照-背光映射策略由开发人员自行决定

**分层设计说明**：
- Service 层负责显示策略和背光调节逻辑
- 订阅光照事件实现自适应背光，订阅报警事件协调显示策略
- 不直接操作硬件，通过调用 LCD 驱动接口实现

---

#### 2.2.5.1 自适应灯光服务（LightService.py）（✅ v1 已实现）

**所属层次**：Service层（业务服务层）

**需求对应**：F-SEN-04 环境光照采集（自适应灯光调节）

**当前状态**：✅ **v1 已实现**（2026-06-10）

**模块功能**：
- 订阅 `EVENT_LIGHT_READY`，根据光照强度自动调节 LED 亮度
- 支持自动/手动模式切换（`set_manual_brightness()` / `set_auto_mode()`）
- 18W 灯散热优化（峰值亮度 50%，gamma 非线性映射）
- 防抖 + 亮度变化阈值过滤，避免频繁调节

**发布事件**：无（纯消费）

**订阅事件**：
- `EVENT_LIGHT_READY`：光照数据就绪，计算目标亮度并调用 PWM LED
- `EVENT_CONFIG_UPDATE`：配置更新（阈值参数、功耗状态）

**依赖**：
- PWMLEDDriver（Device层，调用 `set_brightness()` 接口）
- LightSensorDriver（间接依赖，通过 EventBus 事件）

**配置参数**（在 config.py 中定义）：

| 常量 | 默认值 | 说明 |
|:-----|:-------|:-----|
| `LIGHT_DAY_ADC_THRESHOLD` | 30000 | 白天阈值（ADC值 < 此值 → 光照强 → 灯不开） |
| `LIGHT_NIGHT_ADC_THRESHOLD` | 50000 | 晚上阈值（ADC值 > 此值 → 光照弱 → 灯最亮） |
| `LIGHT_BRIGHTNESS_MIN` | 5 | 最小亮度（%） |
| `LIGHT_BRIGHTNESS_MAX` | 50 | 最大亮度（%），18W灯散热限制 |
| `LIGHT_GAMMA` | 1.5 | 非线性映射参数 |
| `LIGHT_BRIGHTNESS_THRESHOLD` | 3 | 亮度变化阈值 |
| `LIGHT_DEBOUNCE_MS` | 50 | 防抖间隔（ms） |

**分层设计说明**：
- Service 层负责亮度计算算法和模式管理
- 不直接操作 PWM 硬件，通过注入的 PWMLEDDriver 引用调用 Device 层
- 纯事件驱动，tick() 为空实现

---

#### 2.2.5.2 统一控制服务（ControlService.py）（✅ v1 已实现）

**所属层次**：Service层（业务服务层）

**需求对应**：F-CTRL-01 远端控制

**当前状态**：✅ **v1 已实现**（2026-06-10）

**模块职责**：
- 订阅 `EVENT_RIDE_CONTROL` 事件（来自 BLE FFF3 写入）
- 订阅 `EVENT_VOICE_CMD` 事件（来自 VoiceDriver，预留）
- 解析 JSON 控制指令，路由到对应设备驱动
- 控制状态回推（`EVENT_CONTROL_STATE_CHANGED`）

**指令格式**：`{"a":"ctrl", "d":{"cmd":"light_on"}}`

**支持指令**：

| 指令 | 功能 | 调用目标 |
|------|------|----------|
| `light_on` | 头灯开 | `light_service.set_manual_brightness(50)` |
| `light_off` | 头灯关 | `light_service.set_manual_brightness(0)` |
| `brightness_up` | 亮度+ | `light_service.set_manual_brightness(current+10)` |
| `brightness_down` | 亮度- | `light_service.set_manual_brightness(current-10)` |
| `light_auto` | 自动模式 | `light_service.set_auto_mode()` |
| `volume_up` | 音量+ | `audio_driver.set_volume(current+1)` |
| `volume_down` | 音量- | `audio_driver.set_volume(current-1)` |
| `alarm_cancel` | 取消报警 | `alarm_service.cancel_alarm()` |
| `power_save` | 省电模式 | `EVENT_POWER_STATE_CHANGE(SUSPENDED)` |
| `power_normal` | 恢复正常 | `EVENT_POWER_STATE_CHANGE(ACTIVE)` |

**发布事件**：
- `EVENT_CONTROL_STATE_CHANGED`：控制状态变更，携带数据 `{light_mode, light_brightness, volume, power_mode}`

**订阅事件**：
- `EVENT_RIDE_CONTROL`：BLE 远端控制指令
- `EVENT_VOICE_CMD`：语音指令（预留，等 VoiceDriver 就绪后启用）

**依赖**：
- LightService（灯光控制）
- AudioDriver（音量控制）
- AlarmService（报警取消）

**技术要点**：
- 纯事件驱动，tick() 为空实现
- 指令防抖（300ms），防止快速重复触发
- 依赖可为 None，降级运行不崩溃
- 与 NavigationService 相同的架构模式

**数据流**：
  小程序 UI → sendCtrl() → BLE FFF3 → EVENT_RIDE_CONTROL → ControlService → 设备驱动

---

#### 2.2.6 导航引导服务（NavigationService.py）

**所属层次**：Service层（业务服务层）

**需求对应**：F-NAV-01 导航引导

**当前状态**：✅ **头盔端 TTS+LCD 已实现**（2026-06-09）；📅 **位置播报升级规划中**

**模块职责**：
- 订阅 `EVENT_NAV_CMD` 事件（来自 BLE FFF2 写入）
- 解析 JSON 导航指令（方向、距离、路名）
- 调用 Audio.play_tts() 播报中文导航（非阻塞：`_thread.start_new_thread`）
- 在 LCD 底部 (y=110) 写导航摘要行

**指令格式**：`{"a":"nav", "d":{"dir":"right", "dist":200, "road":"中山路"}}`

**方向映射**：left→左转、right→右转、straight→直行、slight_left→靠左、slight_right→靠右、uturn→掉头、arrive→到达目的地、cancel→导航结束

**数据流**：
  小程序（腾讯地图 API 规划路线）→ BLE FFF2 sendNav → EVENT_NAV_CMD → NavigationService → TTS 播报 + LCD 显示

**发布事件**：无（纯消费）

**订阅事件**：
- `EVENT_NAV_CMD`：收到导航指令

**TTS 播报文本**：
- 有路名：`"前方200米右转进入中山路"`
- 无路名：`"前方200米右转"`
- 到达：`"已到达目的地"`（`TTS_NAV_ARRIVE`）
- 取消：`"导航已结束"`（`TTS_NAV_CANCEL`）

**依赖**：
- BLEDriver（接收 FFF2 写入数据）
- Audio 驱动 TTS 播报
- LCD 驱动（导航行显示）

**位置播报升级方案**（📅 规划中）：

当前方案为小程序每 5 秒推流（被动接收），升级为头盔根据 GNSS 位置自主播报：
- 小程序一次性推送完整路线（所有 steps + waypoints）到头盔
- 头盔 NavigationService 比对自身 GNSS 位置，在接近拐弯点时自主 TTS 播报
- 优势：断网/弱 BLE 信号时仍可播报；播报时机更精准（基于实际位置而非定时器）
- 依赖：GNSS cog 字段（已实现）、路线数据 BLE 传输协议（待设计）

---

#### 2.2.6.1 统一控制服务（ControlService.py）（✅ 板子端已实现）

**所属层次**：Service层（业务服务层）

**需求对应**：F-CTRL-01 远端控制

**当前状态**：✅ **板子端已实现**（2026-06-11），小程序控制 UI 待开发

**模块职责**：
- 订阅 `EVENT_RIDE_CONTROL` 事件（来自 BLE FFF3 写入）
- 解析 JSON 控制指令，路由到对应设备驱动
- 控制状态回推（`EVENT_CONTROL_STATE_CHANGED`）
- 预留 `EVENT_VOICE_CMD`（等 VoiceDriver 就绪后启用）

**支持指令**：light_on/off, brightness_up/down, light_auto, volume_up/down, alarm_cancel, power_save/normal

**数据流**：
  小程序 UI（控制面板）→ sendCtrl() → BLE FFF3 → EVENT_RIDE_CONTROL → ControlService → 设备驱动

**已有基础设施**：
- 小程序端：`sendCtrl(cmd)` — ble-service.js 已实现
- 头盔端：`EVENT_RIDE_CONTROL` — config.py 已定义，BLEDriver FFF3 写入时已发布
- ControlService — 板子端已实现并真机验证通过
- BLE 回调 → EventBus → ControlService 全链路已通

**待实现**：
- 小程序端：远端控制 UI 面板（头灯开关、音量调节等按钮）
- main.py 集成（BLEDriver + BLEService + LightService + ControlService 等 v2 模块）

**依赖**：
- BLEDriver（接收 FFF3 写入数据）
- LightService（灯光控制）
- Audio 驱动（音量控制）
- AlarmService（报警取消）

---

#### 2.2.7 微信小程序（WeChatMiniProgram）【v2 新增，Step A 已完成】

**所属层次**：外部应用层

**需求对应**：F-NAV-01 导航引导、F-VOICE-01 语音交互

**当前状态**：🟢 **Step A 已完成**（2026-06-01），Step B 导航推送已实现 + 位置播报/远端控制待开发，三步走开发

**开发计划**：

| 步骤 | 内容 | 状态 |
|:----:|:----|:----:|
| Step A | 登录+实时数据+骑行控制+总结+地图轨迹+报警取消 | ✅ 已完成 (2026-06-01) |
| Step B | 导航路线规划 + 指令推送（腾讯地图 API + BLE FFF2 sendNav） | ✅ 已实现 |
| | polyline 前向差分解压 + act_desc 方向映射修复 | ✅ 已修复 |
| | 导航位置播报（头盔根据 GNSS 位置自主播报，替代 5s 推流） | 📅 规划中 |
| | 远端控制 UI（头灯开关、音量调节等控制面板，BLE FFF3 sendCtrl） | 📅 小程序端待开发 |
| | 统一控制服务（头盔端 ControlService 板子端已实现） | ✅ 板子端已实现 |
| Step C | 语音交互（微信语音识别 → BLE FFF3 命令下发） | 📅 后续 |

**通信方式**：
  头盔 → BLE GATT Notify (FFF1) → 微信小程序（BLE Central）→ 实时接收传感器数据推送

> BLE 为主要近场数据通道，每 2 秒推送合并传感器 JSON（t=0），报警事件立即推送（t=5/t=6）。
>
> **历史方案备注**：v1 初期（5/17-5/28）曾采用 HTTP 轮询方案（小程序 → 移远云 OpenAPI → 查询 TSL 数据），后于 5/28 改为 BLE 直连以降低延迟、减少云端依赖。`services/data-service.js` 和 `utils/ws-client.js` 保留作为历史参考，当前未被 `index.js` 引用。

---

#### MQTT 数据格式（`helmet/data`）

**正常态（type = normal）**

```json
{
  "type": "normal",
  "temp": 28.5,
  "humidity": 65.2,
  "speed_kmh": 15.2,
  "latitude": 22.5431,
  "longitude": 113.9523,
  "altitude": 10.0,
  "signal_quality": "good",
  "timestamp": 12345678
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | `"normal"`，小程序据此切换显示模式 |
| `temp` | float | 温度（°C） |
| `humidity` | float | 湿度（%） |
| `speed_kmh` | float | 当前速度（km/h） |
| `latitude` | float | 纬度 |
| `longitude` | float | 经度 |
| `altitude` | float | 海拔（m） |
| `signal_quality` | string | 信号质量：`good`/`fair`/`poor`/`none` |
| `timestamp` | int | 时间戳（ticks_ms） |

**报警态（type = alarm）**

```json
{
  "type": "alarm",
  "alarm_type": "collision",
  "level": 2,
  "latitude": 22.5431,
  "longitude": 113.9523,
  "altitude": 10.0,
  "timestamp": 12345678
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | `"alarm"`，小程序切换报警显示 |
| `alarm_type` | string | 报警类型：`collision` / `sos` |
| `level` | int | 严重等级 1-3 |
| `latitude` | float | 报警时纬度 |
| `longitude` | float | 报警时经度 |
| `altitude` | float | 报警时海拔 |
| `timestamp` | int | 时间戳 |

**报警态行为**：报警触发后，`helmet/data` 不再发送正常数据，改为 **持续每 2 秒发送报警 payload**，直到报警解除。小程序端收到 `type: "normal"` 即代表报警结束。

**信号质量**：复用 GNSS 驱动已实现的判定逻辑（基于卫星数 + HDOP），输出 `good` / `fair` / `poor` / `none`。

**累计字段说明**：总里程、累计爬升、最高速度、碰撞次数等累计数据由**小程序端自行根据原始 GPS 点计算**，头盔端不再维护这些累加字段。

**心率先留空**：v2 心率带硬件到货后，在正常态 JSON 中增加 `heart_rate` 字段。

---

### 2.3 模块依赖关系


驱动层（无依赖，直接操作硬件）
├── Temp_Humid        # 温湿度传感器
├── IMU               # 加速度传感器
├── GNSS              # 定位模块
├── Light             # 光照传感器
├── Button            # SOS 按键
├── LED               # LED 控制
├── Audio             # 音频播放
├── LCD               # LCD 显示
├── Network           # 4G 网络模组
├── MQTT              # MQTT 协议封装
├── BLEDriver         # BLE GATT Server（EC200U 内置 BLE 4.2）
└── Qth               # 移远云 Qth SDK 封装

服务层（依赖驱动层，部分模块间也有依赖）
├── CollisionService  # 依赖 IMU
├── PowerService      # 依赖 ADC 或 AT 指令
├── AlarmService      # 依赖 LED、Audio（LCD 已解耦给 DisplayService）
├── CloudService      # 依赖 Network、MQTT、所有传感器驱动
├── LarkCloudService  # 依赖 Qth、所有传感器驱动
├── BLEService        # 依赖 BLEDriver、ThreadSafeQueue、EventBus
├── DisplayService    # 依赖 Light、LCD、Audio
└── NavigationService # 依赖 BLEDriver（FFF2 接收）、Audio（TTS 播报）

注：服务层模块间依赖关系在开发时进一步细化

### 2.3.1 事件流总览

**阅读说明**：每个场景按时间从上到下展开，箭头表示事件流向。`[S]`=同步调用，`[E]`=事件驱动（异步）。

---

#### 场景一：主循环调度（RUNNING 态）

```
主循环 for mod in modules: mod.tick() → pump()         每10ms
 │
 ├── Temp_Humid.tick()  (每2000ms)
 │    └── 读取 AHT20
 │    └── [E] EVENT_TEMP_HUMID_READY {temp, humid, valid, timestamp}
 │          ├──→ CloudService._on_temp_humid_ready()
 │          │      └── 打包数据 → send_queue.put()     网络线程上传
 │          ├──→ BLEService._on_temp_humid()
 │          │      └── 缓存温湿度 → tick() 合并 JSON → BLE Notify (FFF1)
 │          └──→ DisplayService._on_temp_humid_ready()
 │                 └── LCD.show_normal_data()          报警中会被状态锁拦截
 │
 ├── IMU.tick()  (每100ms)
 │    └── 读取 LIS2DH12TR
 │    └── [E] EVENT_IMU_READY {acc_x, acc_y, acc_z, acc_total, valid, timestamp}
 │          ├──→ CollisionService._on_imu_data()
 │          │      └── 滑动窗口+阈值判断 → 是否碰撞
 │          └──→ CloudService._on_imu() → 缓存加速度，等待打包上传
 │
 ├── GNSS.tick()  (每2000ms)
 │    └── gnss.get_location()
 │    ├── 有定位 → [E] EVENT_GNSS_READY {lat, lon, alt, speed_kmh, signal_quality, valid, ts}
 │    │              ├──→ CloudService._on_gnss_ready() → 上传
 │    │              ├──→ BLEService._on_gnss() → 缓存 GPS → 合并推送
 │    │              └──→ DisplayService._on_gnss_ready() → LCD
 │    └── 无定位 → no_fix_count++, 超阈值后:
 │                 [E] EVENT_GPS_LOST → AlarmService._on_gps_lost() → TTS
 │
 ├── Light.tick()  (每2000ms)
 │    └── [E] EVENT_LIGHT_READY {light_intensity, valid, timestamp}
 │          ├──→ BLEService._on_light() → 缓存光照 → 合并推送
 │          └──→ DisplayService._on_light_ready() → LCD.set_backlight()
 │
 ├── PowerService.tick()  (每10000ms)
 │    ├── [E] EVENT_BATTERY_LOW       → AlarmService → TTS
 │    └── [E] EVENT_BATTERY_CRITICAL  → AlarmService → TTS + 低功耗
 │
 └── event_bus.pump()   ← 一次性分发所有待处理事件
      └── 逐个调用回调，异常隔离
```

---

#### 场景二：碰撞报警（ALARM 态）

```
CollisionService 判定碰撞 (Level 1/2/3)
 │
 └── [E] EVENT_COLLISION_DETECTED {acc_total, level, timestamp}
       │
        └──→ AlarmService._on_collision()
               ├── [S] LED.blink(duration, interval)  // 闪烁频率取决于等级
               ├── [S] Audio.play_file(file)           // 等级对应的报警音
               ├── 启动报警超时计时器 (30s)
               └── [E] EVENT_ALARM_TRIGGERED {alarm_type="collision", level, ts}
                     ├──→ CloudService._on_alarm() → 紧急推送云端
                     └──→ BLEService._on_alarm() → 立即推送 {"t":5,"a":1,"l":level} 到小程序

30s 后超时:
alarm_timer 到期
  └── [E] EVENT_ALARM_CANCELED {duration, timestamp}
        ├──→ AlarmService._cancel_alarm()
        │      ├── LED.off()
        │      ├── Audio.stop()
        │      └── 重置报警状态
        └──→ BLEService._on_alarm_canceled() → 立即推送 {"t":6,"d":{}} 到小程序
```

---

#### 场景三：SOS 按键报警（ALARM 态）

```
Button 外部中断 (GPIO + 200ms消抖)
 │
 └── [E] EVENT_BUTTON_PRESSED {timestamp}
       │
        └──→ AlarmService._on_button_press()
               ├── **报警中(ALARMING)**: 取消报警 (Cancel)
               ├── **空闲(IDLE)**: SOS 触发
               ├── [S] LED.blink(30000, 200)           // 快速闪烁
               ├── [S] Audio.play_file(sos.mp3)
               ├── 启动 30s 超时
               └── [E] EVENT_ALARM_TRIGGERED {alarm_type="sos", level=3, ts}
                     ├──→ CloudService._on_alarm() → 紧急推送（含GPS位置）
                     └──→ BLEService._on_alarm() → 立即推送 {"t":5,"a":2,"l":3} 到小程序
```

---

#### 场景四：配置更新（任何状态）

```
云端 MQTT 下发 (独立网络线程)
 │
 └── [E] EVENT_CONFIG_UPDATE {target, key:value...}
       │
       ├──→ Temp_Humid   → 更新 sample_ms
       ├──→ IMU           → 更新碰撞阈值
       ├──→ GNSS          → 更新 sample_ms / lost_count
       ├──→ LED           → 更新闪烁参数
       ├──→ Audio         → 更新音量/语速
       ├──→ PowerService  → 更新电池阈值
       └──→ LCD           → 更新刷新间隔/背光
```

---

#### 场景五：GPS 信号丢失与恢复（RUNNING 态）

```
GNSS.tick() 连续多次无定位
 └── no_fix_count ≥ lost_count
       └── [E] EVENT_GPS_LOST {source, timestamp}
             └──→ AlarmService._on_gps_lost()
                    └── Audio.play_tts("GPS信号已丢失")

恢复后:
gnss.get_location() 返回有效数据
 └── gps_lost_reported → False
 └── [E] EVENT_GNSS_READY → 恢复正常上传
```

---

#### 场景六：导航指令（当前方案）

```
小程序(腾讯地图 API 规划路线)
 │
 └── 每 5 秒 BLE FFF2 写入 {"a":"nav","d":{"dir":"right","dist":200,"road":"中山路"}}
      │
      └── BLEDriver._callback() hex 解码
           └── [E] EVENT_NAV_CMD {raw}
                 └──→ NavigationService._on_nav_cmd()
                        ├── JSON 解析 → 提取 dir/dist/road
                        ├── [S] TTS 播报(子线程): "前方200米右转进入中山路"
                        └── [S] LCD 显示(y=110): "> 200m 中山路"

到达/取消:
小程序 → sendNav("arrive"/"cancel") → NavigationService → TTS "已到达目的地" / "导航已结束"
```

---

#### 场景七：远端控制（✅ 板子端已实现）

```
小程序 UI（控制面板，如头灯按钮）
 │
 └── sendCtrl("light_on") → BLE FFF3 写入
      │
      └── BLEDriver._callback()
           └── [E] EVENT_RIDE_CONTROL {raw}
                 └──→ ControlService（✅ 板子端已实现）
                        ├── JSON 解析 → 提取 cmd
                        └── [S] 调用设备驱动（LightService.set_manual_brightness）
```

---

#### 时序对照表

| 周期 | 模块 | 频率 | 事件 | 消费方 |
|:----:|:----|:----:|:-----|:-------|
| 10ms | 主循环 | 固定 | — | 遍历所有 tick() → pump() → sleep |
| 100ms | IMU | 固定 | → EVENT_IMU_READY | CollisionService + CloudService |
| 2000ms | Temp_Humid | 固定 | → EVENT_TEMP_HUMID_READY | CloudService + BLEService |
| 2000ms | GNSS | 固定 | → EVENT_GNSS_READY / EVENT_GPS_LOST | CloudService + BLEService / AlarmService |
| 2000ms | Light | 固定 | → EVENT_LIGHT_READY | DisplayService + BLEService |
| 2000ms | BLEService | 固定 | → BLE Notify (FFF1) 合并 JSON | 小程序（BLE Central） |
| 10000ms | PowerService | 固定 | → EVENT_BATTERY_LOW / CRITICAL | AlarmService（预留） |
| 中断 | Button | 按需 | → EVENT_BUTTON_PRESSED | AlarmService |
| 云端 | CloudService | 按需 | → EVENT_CONFIG_UPDATE | 所有模块 |
| 碰撞 | CollisionService | 按需 | → EVENT_COLLISION_DETECTED | AlarmService |
| 报警 | AlarmService | 按需 | → EVENT_ALARM_TRIGGERED | CloudService（推送） + DisplayService（LCD画面） |
---

### 2.4 初始化顺序

按依赖关系确定初始化顺序：

```
1. 温湿度驱动（Temp_Humid）（✅已实现）
2. IMU 驱动（IMU）（✅已实现）
3. GNSS 驱动（GNSS）（✅已实现）
4. 光照驱动（Light）（✅已实现）
5. SOS 按键驱动（Button）（✅已实现）
6. LED 驱动（LED）（✅已实现）
7. 音频驱动（Audio）（✅已实现）
8. LCD 驱动（LCD）（✅已实现）
8.1. PWM LED 驱动（PWM_LED）（✅ v1 已实现）
9. 网络驱动：Network → MQTT（✅已实现）
10. 网络驱动：Qth（✅ v1 已实现）
11. BLE 驱动（BLEDriver）（✅ v1 已实现，待集成到 main.py）
12. 碰撞检测服务（CollisionService）（✅ v1 已实现）
13. 电源管理服务（PowerService）（⏳ v2 计划，等电池硬件）
14. 报警联动服务（AlarmService）（✅ v1 已实现）
15. 云端通信服务（CloudService）（✅ v1 已实现）
16. 移远云通信服务（LarkCloudService）（✅ v1 已实现）
17. 显示管理服务（DisplayService）（✅ v1 已实现）
17.1. 自适应灯光服务（LightService）（✅ v1 已实现）
18. BLE 推送服务（BLEService）（✅ v1 已实现，待集成到 main.py）
18.1. 统一控制服务（ControlService）（✅ v1 已实现，待集成到 main.py）

**v2 新增模块**：

| # | 模块 | 状态 | 说明 |
|:-|:----|:----|:------|
| 4.1 | LBS 基站定位（LBSDriver） | ✅ v1 已实现 | quectel.LBS 基站定位，与 GNSS 互斥 |
| 17 | 心率驱动（HeartRate） | 📅 v2 | BLE 扫描心率带广播数据 |
| 18 | PWM 调光 LED 驱动（PWM_LED） | ✅ 板子端已实现（未集成 main.py） | PE11 + TIM1_CH2，PWM 调光 |
| 18.1 | 自适应灯光服务（LightService） | ✅ 板子端已实现（未集成 main.py） | 订阅光照事件 + PWM LED 调光 + 自动/手动模式 |
| 19 | 导航引导服务（NavigationService） | ✅ 板子端已实现（未集成 main.py） | BLE FFF2 接收指令 + TTS 播报；位置播报升级 📅 |
| 19.1 | 统一控制服务（ControlService） | ✅ 板子端已实现（小程序端待开发） | BLE FFF3 接收指令 + 统一路由到设备驱动 |
| 20 | 微信小程序（WeChatMiniProgram） | 🟢 Step A + Step B 导航完成，远端控制 UI 待开发 | 登录+BLE+骑行+地图+导航推送+远端控制 🔜 |
```

---

## 3. 开发流程

### 阶段 1：准备与驱动封装

**核心任务**：
- 确认架构设计，理解事件驱动模型
- 了解并讨论需求细节（见 00_requestment.md）
- 确定实现路线（见本章第 2 节）
- 验证硬件模块可用性（运行官方示例代码）
- 开发底层驱动封装（使用 Module_Template.py）

**需完成的需求**：

| 需求ID | 需求名称 | 实现内容 | 验收标准 |
|--------|---------|---------|---------|
| F-SEN-01 | 温湿度采集 | 开发 Temp_Humid.py 驱动，封装 AHT20 传感器 | 能读取温湿度数据并发布事件 |
| F-SEN-02 | 碰撞状态检测 | 开发 IMU.py 驱动，封装 LIS2DH12TR 传感器 | 能读取三轴加速度数据并发布事件 |
| F-SEN-03 | 位置与速度采集 | 开发 GNSS.py 驱动，封装 GNSS 定位 | 能读取经纬度、速度数据并发布事件 |
| F-SEN-04 | 环境光照采集 | 开发 Light.py 驱动，封装光敏电阻 ADC 读取 | 能读取光照等级并发布事件 |
| F-ALM-02 | 一键SOS求助 | 开发 Button.py 驱动，封装按键外部中断 | 按键按下能触发中断并发布事件 |
| F-ALM-03 | 本地声光报警 | 开发 LED.py、Audio.py 驱动 | 能控制 LED 闪烁、播放报警音 |

**说明**：
- 接口层已由移远官方定义，无需自行设计
- 每个驱动模块开发完成后，立即在板子上测试验证
- 参考官方示例代码（examples/ 目录），避免重复造轮子
- 使用 Module_Template.py 快速创建驱动模块

**验收标准**：
- 所有传感器驱动能正常读取数据
- 所有执行器驱动能正常工作
- 所有驱动模块通过单独测试
- 事件发布机制验证正确

---

### 阶段 2：业务代码开发

**核心任务**：
- 开发业务服务模块（使用 Service_Template.py）
- 实现核心业务逻辑和算法
- 补充 Device 层辅助驱动（Network、MQTT）

**需完成的需求**：

| 需求ID | 需求名称 | 实现内容 | 验收标准 |
|--------|---------|---------|---------|
| F-ALM-01 | 碰撞自动报警 | 开发 CollisionService（✅ v1 已实现），订阅 IMU 数据，实现三级判决碰撞检测算法 | 能从 IMU 数据中识别真实碰撞，排除颠簸误报，发布碰撞等级 |
| F-ALM-02 | 一键SOS求助 | 开发 AlarmService（✅ v1 已实现），订阅 `EVENT_BUTTON_PRESSED`，实现 SOS 报警流程 | 按键按下立即触发 SOS 声光报警 |
| F-ALM-03 | 本地声光报警 | 在 AlarmService（✅ v1 已实现）中实现报警联动（LED 闪烁、音频播放、发布 `EVENT_ALARM_TRIGGERED`），LCD 报警画面由 DisplayService（✅ v1 已实现）负责 | 报警时 LED 闪烁、播放报警音 |
| F-NET-01 | 骑行数据远程上传 | 开发 `Drivers/network/Network.py` + `Drivers/network/MQTT.py` + CloudService（✅ v1 已实现），实现数据打包和上传 | 传感器数据能实时上传到云端 |
| F-NET-02 | 紧急报警远程推送 | CloudService（✅ v1 已实现）订阅 `EVENT_ALARM_TRIGGERED`，实现报警数据推送 | 报警事件能立即推送到云端 |
| F-NET-04 | BLE 近场通信 | 开发 `Drivers/network/BLE.py` + BLEService（✅ v1 已实现），BLE GATT Server + Notify 推送，替代 HTTP 轮询 | 手机 BLE 连接后实时接收传感器数据和报警推送 |
| F-ALM-04 | 低电量提醒 | PowerService 暂为空壳（无电池），后续接入电池后再补 | 现阶段占位，不影响其他模块 |
| F-SEN-04 | 环境光照应用 | 开发 DisplayService（✅ v1 已实现），实现开机画面（Logo + TTS）+ 背光自动调节 | 开机显示队标和语音，光照变化时自动调节背光 |

**说明**：
- F-ALM-01 碰撞检测算法（阈值、窗口、滤波方式）由开发人员自行设计
- F-ALM-02/03 报警优先级由 AlarmService 统一仲裁（SOS > 碰撞），通过发布 `EVENT_ALARM_TRIGGERED` 通知 CloudService
- F-NET-01 依赖 `Drivers/interface/Network.py` 和 `Drivers/interface/MQTT.py`，需在 CloudService 之前或同步完成
- F-NET-02 CloudService 只订阅 `EVENT_ALARM_TRIGGERED`，不直接订阅碰撞/按键原始事件，避免重复推送
- PowerService **已移入 v2 计划**，等电池供电硬件就绪后开发
- DisplayService 包含开机画面（队伍 Logo + TTS）和背光调节，依赖 LCD、Audio、Light
- DisplayService 需要提前准备队伍 Logo 的 RGB565 取模数据，存入 `team_logo.py`
- 每开发一个业务模块，立即在板子上测试
- 验证事件订阅/发布流程正确
- 使用 Service_Template.py 快速创建业务模块
- 团队成员自行协调分工

**验收标准**：
- 碰撞检测能正确识别撞击事件（无误报、漏报）
- 报警联动能正确触发本地声光报警
- 云端通信服务能正确打包数据
- 业务模块之间事件流转正常

---

### 阶段 3：系统集成（v1 ✅ 已完成）

**核心任务**（v1 已全部完成）：
- ✅ 整合所有 12 个模块到 main.py
- ✅ 实现 4G 网络通信和 MQTT 数据上传
- ✅ 碰撞自动报警、一键 SOS、本地声光报警
- ✅ LCD 开关机画面、自动背光调节、报警画面切换
- ✅ 分 5 步逐步集成，每步板上验证通过

**v1 集成结果**：

| 需求ID | 需求名称 | v1 状态 | 说明 |
|--------|---------|:-------:|------|
| F-SEN-01 | 温湿度采集 | ✅ | AHT20，每 2 秒采集 |
| F-SEN-02 | 碰撞状态检测 | ✅ | 三级判决算法，排除骑行颠簸 |
| F-SEN-03 | 位置与速度采集 | ✅ | EC200U 内置 GNSS |
| F-SEN-04 | 环境光照采集 | ✅ | GL5528 光敏电阻 ADC |
| F-ALM-01 | 碰撞自动报警 | ✅ | 碰撞→声光报警+远程推送 |
| F-ALM-02 | 一键SOS求助 | ✅ | SW 按键双击语义 |
| F-ALM-03 | 本地声光报警 | ✅ | LED 闪烁 + 音频播放/TTS |
| F-NET-01 | 骑行数据远程上传 | ✅ | MQTT 每 2 秒上传 |
| F-NET-02 | 紧急报警远程推送 | ✅ | 报警立即 MQTT 推送 |
| F-NET-03 | 远程参数配置 | ✅ | 云端下发 → EVENT_CONFIG_UPDATE |
| F-NET-04 | BLE 近场通信 | ✅ | BLE GATT Server + BLEService 推送，替代 HTTP 轮询 |
| F-ALM-04 | 低电量提醒 | ⏳ v2 计划 | 需 PowerService + 电池硬件 |
| - | 系统状态机 | ⏳ v2 计划 | 当前为扁平主循环 |

**说明**：
- 集成过程采用 5 步渐进策略，每步的 main.py 版本见 `core/main_design.md` 第 12 节
- 最终带调试反馈的全量测试版本保存在 `Tests/test_system_full_v1.py`
- 生产版本 `core/main.py` 为去除调试订阅的正式版
- v2 待办：PowerService、系统状态机、SD 卡缓存
- 系统能连续运行 30 分钟不死机

**开发时间轴**：

| 日期 | 里程碑 | 说明 |
|:----:|:-------|:-----|
| 5/5 - 5/13 | Phase 1 驱动层开发 | 传感器 + 执行器 + Button，第一阶段验收通过 |
| 5/14 | 驱动层验收 + 文档同步 | GNSS、LCD、config 等细节完善 |
| 5/17 | CloudService + Network/MQTT | 云端通信方案实现（MQTT → ConnectLab） |
| 5/18 - 5/19 | AlarmService + CollisionService + DisplayService | 业务服务层核心模块 |
| 5/20 | v1 系统集成完成 | 12 模块全部集成到 main.py，5 步渐进验证通过 |
| 5/22 | Qth + LarkCloudService | 移远云通信方案实现（Qth SDK → 移远云 DMP） |
| 5/22-5/28 | 小程序 Step A 开发 | 需求(5/22)→开发(5/23)→架构重构(5/24)→BLE 连通(5/28)，一次性 push；登录+实时数据+骑行控制+报警弹窗+地图轨迹 |
| 5/28 | BLE 模块开发 | BLEDriver + BLEService + GATT Server FFF1-FFF4 + 稳定性修复（MTU 去重、断连清队列、熔断机制） |
| 5/31 | BLE 报警修复 + 导航框架 | t=5 载荷压缩为 15 字节（ATT_MTU 限制）；navigation-service.js 搭建（腾讯地图 API + BLE FFF2 sendNav） |
| 6/01 | Step A 完成 | 轨迹显示修复（WXML concat 根因）；canvas 蓝点 marker；总结地图起点+终点标记；报警取消功能；小程序包瘦身（3099KB→141KB） |
| 6/02 | 文档对齐 + 密钥安全 | 规划文档/小程序文档同步至 Step A 完成状态；config.js 从 git 排除；BLE t=5 压缩入库 |
| 6/09 | 导航功能开发 | BLE hex 解码、TTS 非阻塞（_thread）、NavigationService 创建、LBS 驱动、GNSS cog 字段、小程序 polyline 前向差分解压 + act_desc 方向映射 |

---

### 阶段 4：v2 功能扩展（📅 规划中）

**核心任务**：
- 电源管理模块（依赖电池供电硬件就绪）
- 心率监测模块（数据统一走 MQTT，BLE 为本地传输接口）
- 大功率灯光驱动（自适应灯光，依赖硬件设计完成）
- 导航引导服务（微信小程序规划路线 → 头盔 GNSS 比对 → TTS 播报）
- 语音交互（微信小程序语音识别 → MQTT 命令 → 头盔执行）
- 微信小程序三步走（通信 → 导航 → 语音）

**v2 新增/变动模块一览**：

| 模块 | 类型 | 状态 | 关键依赖 |
|:----|:----|:----:|:--------|
| PowerService | 服务 | 🟡 等硬件 | 电池供电方案就绪 |
| HeartRate | 驱动 | 🟡 待开发 | 心率带硬件到货 |
| PWM_LED | 驱动 | ✅ 板子端已实现 | PE11 + TIM1_CH2，PWM 调光 |
| NavigationService | 服务 | ✅ 板子端已实现 | BLE FFF2 + TTS；位置播报 📅 |
| ControlService | 服务 | ✅ 板子端已实现 | BLE FFF3 + 统一路由；小程序端待开发 |
| VoiceDriver | 驱动 | 📅 等 ASRPRO 硬件 | UART 串口通信 |
| LBSDriver | 驱动 | ✅ v1 已实现 | quectel.LBS，与 GNSS 互斥 |
| WeChatMiniProgram | 外部 | 🟢 Step A 完成 + Step B 框架 | 无 |

**集成策略**：与 v1 相同的逐步集成原则，每个模块独立开发验证后加入 main.py。

---

### 阶段 5：系统测试与优化

**核心任务**：
- 完整功能测试（所有需求功能）
- 异常测试和性能测试
- 实车测试和参数调优

**需完成的测试**：

| 测试类型 | 测试内容 | 验收标准 |
|---------|---------|---------|
| 功能测试 | F-SEN-01~05 所有传感器采集功能 | 所有传感器数据正常采集 |
| 功能测试 | F-ALM-01 碰撞自动报警 | 真实碰撞 100% 报警成功 |
| 功能测试 | F-ALM-02 一键SOS求助 | 按键按下立即触发报警 |
| 功能测试 | F-ALM-03 本地声光报警 | 报警时 LED 闪烁、音频播放正常 |
| 功能测试 | F-NET-01 骑行数据远程上传 | 云端能实时看到数据 |
| 功能测试 | F-NET-02 紧急报警远程推送 | 报警事件能立即推送到云端 |
| 异常测试 | 网络断开 | 系统能降级运行，本地缓存数据 |
| 异常测试 | 传感器异常 | 系统能检测异常并发布错误事件 |
| 异常测试 | 按键异常（长按、误触） | 系统能正确处理异常按键 |
| 性能测试 | 主循环周期 | 主循环周期稳定，无阻塞 |
| 性能测试 | 内存占用 | 内存占用稳定，无泄漏 |
| 实车测试 | 户外骑行测试 | 骑行平稳路段无误报，真实撞击无漏报 |
| 实车测试 | 弱网环境测试 | 弱网环境下系统稳定，数据能补发 |

**说明**：
- 先进行功能测试，确保所有功能正常
- 再进行异常测试，确保系统健壮性
- 最后进行实车测试，验证真实场景效果
- 根据测试结果调优参数（碰撞检测阈值、采样频率等）

**验收标准**：
- 所有 P0 需求功能正常
- P1 需求功能基本完成
- 异常情况系统能降级运行，不崩溃
- 实车测试碰撞检测无误报、漏报
- 系统稳定性满足比赛演示要求

---

### 阶段 6：文档与演示准备

**核心任务**：
- 编写比赛设计文档
- 录制演示视频
- 准备答辩材料

**需完成的内容**：

| 内容类型 | 具体内容 | 要求 |
|---------|---------|------|
| 设计文档 | 系统架构设计文档 | 说明架构设计、模块划分、技术选型 |
| 设计文档 | 硬件连接说明文档 | 说明硬件连接、引脚配置、开关设置 |
| 设计文档 | 软件设计文档 | 说明软件流程、算法实现、关键技术 |
| 演示视频 | 功能演示视频 | 展示碰撞检测、报警联动、云端通信等核心功能 |
| 演示视频 | 实车测试视频 | 展示户外骑行测试场景 |
| 开源代码 | 完整源代码包 | 代码完整、注释清晰、可复现 |

**说明**：
- 文档需符合比赛要求格式
- 视频需清晰展示核心功能
- PPT 需突出创新点和技术亮点
- 代码包需完整，包含所有依赖说明

**验收标准**：
- 文档完整、格式规范、逻辑清晰
- 视频清晰展示功能，时长合适
- 代码包完整、可编译运行
- 演示彩排流畅，准备充分

---

## 4. 里程碑规划

### 里程碑总览

```
M1: 起步验证 ──→ M2: 本地闭环 ──→ M3: 云端打通 ──→ M4: 整体集成 ──→ M5: v2设计与集成 ──→ M6: 整体收官
```

---

### 时间轴

✅ M1 ──→ ✅ M2 ──→ ✅ M3 ──→ ✅ M4 ──→ 🔵 M5 ──→ 📅 M6
起步验证　　本地闭环　　云端打通　　v1 集成　　v2 进行中　　      收官
05上旬　　　05-13　　　   05-19　　　 05-20　　　 05-28~　　　　将来

> 箭头表示开发推进方向，✅=已完成　🔵=进行中　📅=计划中

| 时间 | 里程碑 | 状态 | 关键交付 |
|:-----|:-------|:----:|:---------|
| 05上旬 | M1 起步验证 | ✅ | 驱动封装：AHT20(温湿度)、LIS2DH12TR(IMU)、GNSS(定位)、GL5528(光照)、LED、Audio、LCD |
| 05-13 | M2 本地闭环 | ✅ | 碰撞检测算法(CollisionService)、报警联动(AlarmService)：LED 闪烁 + 音频 + 按钮 SOS |
| 05-19 | M3 云端打通 | ✅ | Network 驱动、MQTT 驱动、CloudService(ConnectLab) E2E 测试通过 |
| 05-20 | M4 v1 集成 | ✅ | 12 模块 main.py 集成、EventBus 事件总线、`test_system_full_v1.py` 全系统测试 |
| 05-22 | M4+ 移远云 | ✅ | QthDriver 驱动、LarkCloudService、移远云 DMP 数据通道 E2E 通过 |
| 05-28 ~ 06-02 | M5 v2 设计 | 🔵 | BLE 模块、小程序 Step A 完成 + Step B 导航框架、文档对齐 |
| 将来 | M6 收官 | 📅 | 设计文档、演示视频、答辩 PPT、开源整理 |

---

### M1: 起步验证

**里程碑目标**：掌握平台，驱动跑通

**关键成果**：
- ✅ 熟悉移远开发板和 MicroPython 环境
- ✅ 所有官方示例代码运行成功
- ✅ 温湿度、IMU、GNSS 驱动封装完成并测试通过
- ✅ LED、Audio 驱动封装完成并测试通过

---

### M2: 本地闭环

**里程碑目标**：碰撞检测 + 本地报警联动

**关键成果**：
- ✅ 碰撞检测算法实现，能识别撞击
- ✅ 本地报警联动实现（AlarmService v1：LED 闪烁、音频播放、超时取消、按钮取消）
- ✅ 敲击板子能触发报警演示


---

### M3: 云端打通

**里程碑目标**：4G 联网 + 数据上传云端

**关键成果**：
- ✅ 4G 网络连接成功
- ✅ MQTT 连接 ConnectLab 平台成功
- ✅ CloudService `Modules/cloud_service.py` 建成并 E2E 测试通过（2026-05-17）
- ✅ 传感器数据实时上传到云端
- ✅ 云端能查看实时数据和报警记录


---

### M4: v1 整体集成 ✅

**里程碑目标**：全功能集成（已完成）

**当前状态**：✅ **已完成**

**关键成果**：
- ✅ **v1 系统集成完成** — `core/main.py` 加载全部 12 个模块，按序初始化，容错跳过失败模块
- ✅ 系统连续运行稳定，主循环 100Hz 节拍，`event_bus.pump()` 事件流转正常
- ✅ 碰撞检测+声光报警+按键 SOS 业务链完整验证通过
- ✅ 离线和异常降级：传感器/网络失败不影响其他模块
- ✅ 完整集成测试保存在 `Tests/test_system_full_v1.py`

**说明**：v1 系统已按 5 步逐步集成方案（Step 0~5）全部完成并通过板上验证。每步的测试 `core/main.py` 版本以及最终带调试反馈的全量测试版本均保留在 `Tests/` 目录。

---

### M5: v2 设计与集成 📅

**里程碑目标**：电源管理、心率监测、灯光驱动、导航引导、语音交互、微信小程序

**当前状态**：📅 **进行中**

**子里程碑**：

| 子里程碑 | 内容 | 状态 |
|:--------|:----|:----:|
| M5.1 电源管理 | PowerService（等电池硬件） | 🟡 等硬件 |
| M5.2 灯光驱动 | PWM_LED（PE11, TIM1_CH2） | ✅ 板子端已实现 |
| M5.3 心率模块 | HeartRate 驱动（数据走 MQTT） | 🟡 等心率带到货 |
| M5.4 微信小程序 | Step A: 登录+实时数据+骑行控制+总结+地图+报警取消 ✅ | 🟢 完成 (2026-06-01) |
| | Step B: 导航推送（腾讯地图 API + BLE FFF2 sendNav + polyline 修复） | ✅ 已实现 (2026-06-09) |
| | Step B: 导航位置播报（头盔 GNSS 位置自主播报） | 📅 规划中 |
| | Step B: 远端控制（小程序 UI + BLE FFF3 + 头盔 Service） | 🔜 板子端已实现，小程序端待开发 |
| | Step C: 语音交互（微信语音识别 → BLE FFF3 命令下发） | 📅 第三步 |
| M5.5 导航+语音 | NavigationService ✅ + ControlService ✅（板子端） | 🔜 板子端已实现，位置播报和小程序 UI 待开发 |
| M5.6 移远云通道 | LarkCloudService + QthDriver，Qth SDK 接入移远云 | ✅ v1 已完成（2026-5-22） |

---

### M6: 整体收官 📅

**里程碑目标**：文档完善 + 演示准备 + 开源整理

**当前状态**：📅 **待 M5 达成后启动**

**关键成果**（规划）：
- 📅 完整设计文档编写完成
- 📅 演示视频录制完成
- 📅 答辩 PPT 制作完成
- 📅 开源代码包整理完成
- 📅 最终演示彩排成功

---

**文档版本**：v7.0
**更新日期**：2026-06-09
**维护团队**：锦依卫队
**备注**：v1 集成完成（M4），v2 导航功能开发中（头盔端 TTS+LCD 已实现，位置播报和远端控制待开发），BLE 直连为主数据通道
