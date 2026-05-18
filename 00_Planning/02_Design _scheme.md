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
- `EVENT_GNSS_READY`：定位数据就绪，携带数据 `{latitude, longitude, altitude, speed_kmh, signal_quality, valid, timestamp}`

**订阅事件**：
- `EVENT_CONFIG_UPDATE`：远程配置更新

**硬件说明**：
- 模组：EC200U 内置 GNSS
- 接口：GNSS 天线接口 J102（需外接无源 GNSS 天线）
- 参考示例：`examples/gnss.py`

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

#### 2.1.5 SOS 按键驱动模块（Button.py）

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

### 2.2 服务层模块（业务逻辑）

#### 2.2.1 碰撞检测服务（CollisionService.py）

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
- 收到报警事件后立即拼装报警 JSON 入队，不等待 tick 周期
- 接收云端 MQTT 下行配置，转发为 EVENT_CONFIG_UPDATE 事件
- 未读到的传感器数据字段在 JSON 中输出 null（区分"未采集"与"值为 0"）

**发布事件**：
- `EVENT_DATA_UPLOAD_SUCCESS`：数据上传成功
- `EVENT_DATA_UPLOAD_FAILED`：数据上传失败
- `EVENT_NETWORK_CONNECTED`：网络连接成功
- `EVENT_NETWORK_DISCONNECTED`：网络断开

**订阅事件**：
- `EVENT_TEMP_HUMID_READY`：温湿度数据，缓存等待打包
- `EVENT_IMU_READY`：加速度数据，缓存等待打包
- `EVENT_GNSS_READY`：定位数据，缓存 GPS 并更新骑行扩展字段（不上传入队）
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

**骑行数据扩展（可选）**：

若需要骑行路线记录和数据总结，CloudService 维护以下累加字段，随传感器数据一并上传：

| 字段 | 来源 | 说明 |
|:----:|:----:|:------|
| `total_distance` | GNSS 经纬度 | 累加相邻点 Haversine 距离，单位 km |
| `max_speed` | GNSS 速度 | 周期内取最大值，单位 km/h |
| `ride_duration` | 系统计时 | v2 计划（需状态机就绪） |
| `total_ascent` | GNSS 海拔 | 累加海拔正差值，单位 m |
| `collision_count` | CollisionService | 碰撞触发计数 |
| `gps_track` | GNSS 点队列 | 最近 N 个 `{lat, lon}` 点（上限 `CLOUD_GPS_TRACK_MAX`），上报后清空 |

上传后云端可用这些数据还原骑行路线、生成骑行总结卡片。

---

#### 2.2.4 电源管理服务（PowerService.py）

**当前状态**：空壳占位（等待电池供电接入）

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

#### 2.2.5 显示管理服务（DisplayService.py）

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

### 2.3 模块依赖关系


驱动层（无依赖，直接操作硬件）
├── Temp_Humid        # 温湿度传感器
├── IMU               # 加速度传感器
├── GNSS              # 定位模块
├── Light             # 光照传感器
├── Button            # SOS 按键
├── LED               # LED 控制
├── Audio             # 音频播放
└── LCD               # LCD 显示

服务层（依赖驱动层，部分模块间也有依赖）
├── CollisionService  # 依赖 IMU
├── PowerService      # 依赖 ADC 或 AT 指令
├── AlarmService      # 依赖 LED、Audio、LCD、CollisionService、PowerService
├── CloudService      # 依赖所有传感器驱动、LCD
└── DisplayService    # 依赖 Light、LCD、Audio

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
 │          └──→ CloudService._on_temp_humid_ready()
 │                 ├── 打包数据 → send_queue.put()     网络线程上传
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
 │    │              └──→ CloudService._on_gnss_ready() → 上传 + LCD
 │    └── 无定位 → no_fix_count++, 超阈值后:
 │                 [E] EVENT_GPS_LOST → AlarmService._on_gps_lost() → TTS
 │
 ├── Light.tick()  (每2000ms)
 │    └── [E] EVENT_LIGHT_READY {light_intensity, valid, timestamp}
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
                     └──→ CloudService._on_alarm() → 紧急推送云端

30s 后超时:
alarm_timer 到期
  └── [E] EVENT_ALARM_CANCELED {duration, timestamp}
        └──→ AlarmService._cancel_alarm()
               ├── LED.off()
               ├── Audio.stop()
               └── 重置报警状态
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
                     └──→ CloudService._on_alarm() → 紧急推送（含GPS位置）
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

#### 时序对照表

| 周期 | 模块 | 频率 | 事件 | 消费方 |
|:----:|:----|:----:|:-----|:-------|
| 10ms | 主循环 | 固定 | — | 遍历所有 tick() → pump() → sleep |
| 100ms | IMU | 固定 | → EVENT_IMU_READY | CollisionService + CloudService |
| 2000ms | Temp_Humid | 固定 | → EVENT_TEMP_HUMID_READY | CloudService |
| 2000ms | GNSS | 固定 | → EVENT_GNSS_READY / EVENT_GPS_LOST | CloudService / AlarmService |
| 2000ms | Light | 固定 | → EVENT_LIGHT_READY | DisplayService |
| 10000ms | PowerService | 固定 | → EVENT_BATTERY_LOW / CRITICAL | AlarmService（预留） |
| 中断 | Button | 按需 | → EVENT_BUTTON_PRESSED | AlarmService |
| 云端 | CloudService | 按需 | → EVENT_CONFIG_UPDATE | 所有模块 |
| 碰撞 | CollisionService | 按需 | → EVENT_COLLISION_DETECTED | AlarmService |
| 报警 | AlarmService | 按需 | → EVENT_ALARM_TRIGGERED | CloudService（推送） + DisplayService（LCD画面） |
---

### 2.4 初始化顺序

按依赖关系确定初始化顺序：

```
1. 温湿度驱动（Temp_Humid）           （✅ 已实现）
2. IMU 驱动（IMU）                   （✅ 已实现）
3. GNSS 驱动（GNSS）                 （✅ 已实现）
4. 光照驱动（Light）                  （✅ 已实现）
5. SOS 按键驱动（Button）             （✅ 已实现）
6. LED 驱动（LED）                   （✅ 已实现）
7. 音频驱动（Audio）                  （✅ 已实现）
8. LCD 驱动（LCD）                   （✅ 已实现）
9. 碰撞检测服务（CollisionService）
10. 电源管理服务（PowerService）
11. 报警联动服务（AlarmService）       （✅ v1 已实现）
12. 云端通信服务（CloudService）       （✅ v1 已实现）
13. 显示管理服务（DisplayService）
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
| F-ALM-01 | 碰撞自动报警 | 开发 CollisionService，订阅 IMU 数据，实现碰撞检测算法 | 能从 IMU 数据中识别真实碰撞，排除颠簸误报，发布碰撞等级 |
| F-ALM-02 | 一键SOS求助 | 开发 AlarmService，订阅 `EVENT_BUTTON_PRESSED`，实现 SOS 报警流程 | 按键按下立即触发 SOS 声光报警 |
| F-ALM-03 | 本地声光报警 | 在 AlarmService 中实现报警联动（LED 闪烁、音频播放、发布 `EVENT_ALARM_TRIGGERED`），LCD 报警画面由 DisplayService 负责 | 报警时 LED 闪烁、播放报警音 |
| F-NET-01 | 骑行数据远程上传 | 开发 `Drivers/interface/Network.py` + `Drivers/interface/MQTT.py` + CloudService，实现数据打包和上传 | 传感器数据能实时上传到云端 |
| F-NET-02 | 紧急报警远程推送 | CloudService 订阅 `EVENT_ALARM_TRIGGERED`，实现报警数据推送 | 报警事件能立即推送到云端 |
| F-ALM-04 | 低电量提醒 | PowerService 暂为空壳（无电池），后续接入电池后再补 | 现阶段占位，不影响其他模块 |
| F-SEN-04 | 环境光照应用 | 开发 DisplayService，实现开机画面（Logo + TTS）+ 背光自动调节 | 开机显示队标和语音，光照变化时自动调节背光 |

**说明**：
- F-ALM-01 碰撞检测算法（阈值、窗口、滤波方式）由开发人员自行设计
- F-ALM-02/03 报警优先级由 AlarmService 统一仲裁（SOS > 碰撞），通过发布 `EVENT_ALARM_TRIGGERED` 通知 CloudService
- F-NET-01 依赖 `Drivers/interface/Network.py` 和 `Drivers/interface/MQTT.py`，需在 CloudService 之前或同步完成
- F-NET-02 CloudService 只订阅 `EVENT_ALARM_TRIGGERED`，不直接订阅碰撞/按键原始事件，避免重复推送
- PowerService 当前阶段为空壳占位（USB 供电无法读取电池电量），不影响其他模块开发
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

### 阶段 3：系统集成

**核心任务**：
- 整合所有模块到 main.py
- 实现网络通信功能
- 测试系统整体运行

**需完成的需求**：

| 需求ID | 需求名称 | 实现内容 | 验收标准 |
|--------|---------|---------|---------|
| F-NET-01 | 骑行数据远程上传 | 集成 Network、MQTT，实现 4G 联网和数据上传 | 设备能联网，数据能上传到 ConnectLab 平台 |
| F-NET-02 | 紧急报警远程推送 | 实现报警数据高优先级上传 | 报警事件能立即推送到云端 |
| F-NET-03 | 远程参数配置 (P1) | 实现云端配置下发和本地应用 | 能接收云端配置并更新参数 |
| F-ALM-04 | 低电量提醒 (P1) | 开发 PowerService，实现电量监测和提醒 | 电量低于阈值能触发提醒 |
| - | 系统状态机 | 实现系统状态切换（INIT/RUNNING/ALARM/SLEEP） | 状态切换逻辑正确 |

**说明**：
- 逐步集成，先集成核心模块（传感器、报警），再集成扩展模块（网络、功耗）
- 每集成一个模块，立即测试整体功能
- 记录集成过程中遇到的问题
- 网络操作需使用独立线程，避免阻塞主循环

**验收标准**：
- 系统能正常启动，所有模块初始化成功
- 主循环运行稳定，无明显卡顿
- 事件总线通信正常
- 网络线程工作正常
- 所有功能模块协同工作正常
- 系统能连续运行 30 分钟不死机

---

### 阶段 4：系统测试与优化

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

### 阶段 5：文档与演示准备

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
M1: 起步验证 ──→ M2: 本地闭环 ──→ M3: 云端打通 ──→ M4: 整体集成 ──→ M5: 完美收官
```

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

### M4: 整体集成

**里程碑目标**：全功能集成 + 实车测试

**关键成果**：
- ✅ 所有模块集成到主程序
- ✅ 系统连续运行 30 分钟稳定不死机
- ✅ 实车测试碰撞检测无误报、漏报
- ✅ 异常情况（断网、传感器故障）系统能降级运行

---

### M5: 完美收官

**里程碑目标**：文档完善 + 演示准备

**关键成果**：
- ✅ 设计文档编写完成
- ✅ 演示视频录制完成
- ✅ 答辩 PPT 制作完成
- ✅ 开源代码包整理完成
- ✅ 最终演示彩排成功

---

**文档版本**：v5.0  
**更新日期**：2026-05-14  
**维护团队**：锦依卫队
