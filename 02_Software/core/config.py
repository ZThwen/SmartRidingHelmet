"""
brief 全局配置与事件常量定义
note 所有模块通信必须引用此处常量，禁止硬编码事件名或阈值
"""

# ================= 事件名称常量 =================
# 系统事件
EVENT_SYSTEM_READY          = "SYSTEM_READY"          # 系统就绪事件
EVENT_CONFIG_UPDATE         = "CONFIG_UPDATE"         # 配置更新事件
EVENT_SENSOR_ERROR          = "SENSOR_ERROR"          # 传感器错误事件
EVENT_LCD_ERROR             = "LCD_ERROR"             # LCD错误事件
EVENT_BUTTON_ERROR          = "BUTTON_ERROR"          # 按键错误事件
EVENT_BUTTON_PRESSED        = "BUTTON_PRESSED"        # 按键按下事件
EVENT_LED_ERROR             = "LED_ERROR"             # LED错误事件

# 传感器数据就绪事件
EVENT_TEMP_HUMID_READY      = "TEMP_HUMID_READY"      # 温湿度数据就绪
EVENT_IMU_READY             = "IMU_READY"             # IMU加速度数据就绪
EVENT_GNSS_READY            = "GNSS_READY"            # GNSS定位数据就绪
EVENT_LIGHT_READY           = "LIGHT_READY"           # 光照数据就绪
EVENT_HEARTRATE_READY       = "HEARTRATE_READY"       # 心率血氧数据就绪

# 报警相关事件
EVENT_COLLISION_DETECTED    = "COLLISION_DETECTED"    # 碰撞检测到
EVENT_SOS_TRIGGERED         = "SOS_TRIGGERED"         # SOS按键触发
EVENT_ALARM_TRIGGERED       = "ALARM_TRIGGERED"       # 报警触发（通用）
EVENT_ALARM_CANCELED        = "ALARM_CANCELED"        # 报警取消

# 音频相关事件
EVENT_AUDIO_PLAYBACK_START  = "AUDIO_PLAYBACK_START"  # 音频开始播放
EVENT_AUDIO_PLAYBACK_END    = "AUDIO_PLAYBACK_END"    # 音频播放结束
EVENT_AUDIO_ERROR           = "AUDIO_ERROR"           # 音频播放错误
EVENT_RECORD_START          = "RECORD_START"          # 开始录音
EVENT_RECORD_END            = "RECORD_END"            # 录音结束

# 电源管理事件
EVENT_BATTERY_READY         = "BATTERY_READY"         # 电池电量数据就绪
EVENT_BATTERY_LOW           = "BATTERY_LOW"           # 低电量警告
EVENT_BATTERY_CRITICAL      = "BATTERY_CRITICAL"      # 电量严重不足
EVENT_POWER_STATE_CHANGE    = "POWER_STATE_CHANGE"    # 功耗状态切换
EVENT_MANUAL_ACTIVITY       = "MANUAL_ACTIVITY"       # 用户手动操作，通知 PowerService 暂停自动省电

# GNSS相关事件
EVENT_GPS_LOST              = "GPS_LOST"              # GPS信号丢失

# LBS相关事件
EVENT_LBS_READY             = "LBS_READY"              # LBS定位数据就绪

# 网络相关事件
EVENT_NETWORK_CONNECTED     = "NETWORK_CONNECTED"     # 网络连接成功
EVENT_NETWORK_DISCONNECTED  = "NETWORK_DISCONNECTED"  # 网络断开
EVENT_DATA_UPLOAD_SUCCESS   = "DATA_UPLOAD_SUCCESS"   # 数据上传成功
EVENT_DATA_UPLOAD_FAILED    = "DATA_UPLOAD_FAILED"    # 数据上传失败

# 蓝牙(BLE)相关事件
EVENT_BLE_CONNECTED         = "BLE_CONNECTED"          # BLE 连接成功
EVENT_BLE_DISCONNECTED      = "BLE_DISCONNECTED"       # BLE 断开连接
EVENT_NAV_CMD               = "NAV_CMD"                # 导航指令（手机→头盔）
EVENT_RIDE_CONTROL          = "RIDE_CONTROL"           # 骑行控制指令
EVENT_MANUAL_ACTIVITY       = "MANUAL_ACTIVITY"        # 用户手动操作（非电源/查询指令）
EVENT_BLE_ALARM_ACK         = "BLE_ALARM_ACK"          # 报警确认（手机取消）

# 控制系统事件
EVENT_CONTROL_STATE_CHANGED = "CONTROL_STATE_CHANGED"  # 控制状态变更（回推到小程序）
EVENT_SMS_PHONE_CONFIG      = "SMS_PHONE_CONFIG"       # SMS 手机号配置
EVENT_VOICE_CMD             = "VOICE_CMD"              # 语音指令（ASRPRO → ControlService）

# 控制指令事件（ControlService → 各模块）
EVENT_LIGHT_CONTROL         = "LIGHT_CONTROL"           # 灯光控制指令
EVENT_LIGHT_BLINK_STATE     = "LIGHT_BLINK_STATE"       # 灯光闪烁状态变更（LightService → ControlService）
EVENT_VOLUME_CONTROL        = "VOLUME_CONTROL"          # 音量控制指令
EVENT_ALARM_CONTROL         = "ALARM_CONTROL"           # 报警控制指令
EVENT_TTS_REQUEST           = "TTS_REQUEST"             # TTS 播报请求
EVENT_NAV_DISPLAY           = "NAV_DISPLAY"             # 导航显示内容变更（NavigationService → DisplayService）

# ================= 默认参数配置 =================
# 传感器采样间隔
TEMP_HUMID_SAMPLE_MS   = 2000    # 温湿度传感器采样间隔 (ms)
IMU_SAMPLE_MS          = 100     # IMU传感器采样间隔 (ms) - 碰撞检测需要高频
GNSS_SAMPLE_MS         = 2000    # GNSS采样间隔 (ms)
LIGHT_SAMPLE_MS        = 2000    # 光照传感器采样间隔 (ms)
LCD_SAMPLE_MS          = 2000    # LCD显示更新间隔 (ms)
DEFAULT_SAMPLE_MS      = 2000    # 传感器默认采样间隔 (ms)

# ================= 心率传感器配置 =================
HEARTRATE_SAMPLE_MS         = 2000    # 心率采样间隔 (ms)
HEARTRATE_SUSPENDED_MS      = 5000    # 省电模式采样间隔 (ms)
HEARTRATE_WARMUP_MS         = 10000   # 传感器预热时间 (ms)
HEARTRATE_UART_ID           = 5       # UART总线编号（UART5, TX=PC12, RX=PD2）
HEARTRATE_UART_BAUDRATE     = 115200  # 波特率
HEARTRATE_UART_TX_PIN       = "PC12"  # UART5 TX
HEARTRATE_UART_RX_PIN       = "PD2"   # UART5 RX
HEARTRATE_DATA_LEN          = 50      # 数据包长度（字节）
HEARTRATE_HEADER            = 0xFF    # 数据包头字节
HEARTRATE_CMD_START         = 0xFF    # 采集开指令
HEARTRATE_CMD_STOP          = 0xFE    # 采集关指令
HEARTRATE_HR_MIN            = 30      # 心率最小值 (bpm)
HEARTRATE_HR_MAX            = 240     # 心率最大值 (bpm)
HEARTRATE_SPO2_MIN          = 10      # 血氧最小值 (%)
HEARTRATE_SPO2_MAX          = 100     # 血氧最大值 (%)
HEARTRATE_HIGH_THRESHOLD    = 190     # 心率过高阈值 (bpm)
HEARTRATE_LOW_THRESHOLD     = 50      # 心率过低阈值 (bpm)
HEARTRATE_SPO2_LOW_THRESHOLD = 90     # 血氧过低阈值 (%)
HEARTRATE_TTS_HIGH = "心率过高，请注意休息"
HEARTRATE_TTS_LOW = "心率过低，请注意"
HEARTRATE_SPO2_TTS_LOW = "血氧偏低，请注意通风"
HEARTRATE_ALERT_COOLDOWN_MS = 30000

BUTTON_DEBOUNCE_MS     = 50      # 按键防抖动时间窗口 (ms)

DEFAULT_RETRY_COUNT    = 3       # 硬件通信最大重试次数
DEFAULT_TIMEOUT_MS     = 500     # 单次硬件操作超时阈值 (ms)

# ================= 音频配置 =================
AUDIO_ALARM_FILE_L1       = "SD:alarm_l1.mp3"     # 碰撞等级1报警音
AUDIO_ALARM_FILE_L2       = "SD:alarm_l2.mp3"     # 碰撞等级2报警音
AUDIO_ALARM_FILE_L3       = "SD:alarm_l3.mp3"     # 碰撞等级3报警音
AUDIO_SOS_FILE            = "SD:sos.mp3"          # SOS求救音
AUDIO_BUTTON_FILE         = "SD:button.wav"       # 按键反馈音
AUDIO_TEST_FILE           = "SD:Test.mp3"         # 测试音频

AUDIO_TTS_SPEED           = 85                     # TTS语速(0-100)
AUDIO_TTS_VOLUME          = 50                     # TTS音量(0-100)
AUDIO_SPEAKER_VOLUME      = 5                      # 扬声器音量(0-5)
AUDIO_ALARM_LOOP_COUNT    = 3                      # 报警音循环次数
TTS_BATTERY_LOW           = "当前电量不足，请及时充电"
TTS_BATTERY_CRITICAL      = "电池电量严重不足，请立即充电"
TTS_GPS_LOST              = "GPS信号已丢失"
TTS_BOOT_WELCOME           = "依路护航，锦依卫队为您保驾护航"

# 导航 TTS
TTS_NAV_TURN          = "前方%d米%s"           # 前方200米右转
TTS_NAV_ROAD          = "前方%d米%s进入%s"     # 前方200米右转进入中山路
TTS_NAV_ARRIVE        = "已到达目的地"
TTS_NAV_CANCEL        = "导航已结束"

# ================= 碰撞检测配置（裸板适配）=================
# 多级阈值（单位：g，1g=9.8m/s²）
COLLISION_THRESHOLD_SUSPECT    = 1.5    # 最低怀疑阈值 — 超过此值进入三级判决
COLLISION_THRESHOLD_LIKELY     = 3.0    # 疑似碰撞下限
COLLISION_THRESHOLD_HIGH       = 5.0    # 高度疑似下限
COLLISION_THRESHOLD_CONFIRMED  = 8.0    # 确定碰撞阈值 — 免鉴别直接报警
GRAVITY                        = 9.8    # 重力加速度

# 滑动窗口
COLLISION_WINDOW_SIZE          = 15     # 滑动窗口最大容量(样本数)
COLLISION_WINDOW_DURATION_MS   = 1500   # 窗口覆盖时间范围(ms)

# 防误报鉴别参数（裸板脉冲更短，但平移/抖动特征不变）
COLLISION_PULSE_MIN_WIDTH_MS   = 60     # 最小有效脉冲宽度(ms) — 裸板敲击脉冲约 50~100ms
COLLISION_PRE_WINDOW_MS        = 300    # 碰撞前上下文窗口(ms)
COLLISION_FREE_FALL_THRESHOLD  = 0.8    # 失重判定阈值(g)
COLLISION_VARIANCE_THRESHOLD   = 0.5    # 振荡方差阈值(g²)
COLLISION_PEAK_COUNT_THRESHOLD = 3      # 振荡波峰计数阈值

# 防重复触发（裸板碰撞后稳定较快）
COLLISION_COOLDOWN_MS          = 3000   # 碰撞事件最短间隔(ms)

# 碰撞等级划分阈值（裸板适用）
COLLISION_LEVEL1_MAX_G         = 5.0    # 轻微碰撞最大峰值(g) — 轻敲板子
COLLISION_LEVEL1_MAX_DURATION_MS = 200  # 轻微碰撞最长持续时间(ms)
COLLISION_LEVEL2_MAX_G         = 8.0    # 中等碰撞最大峰值(g) — 用力敲击
COLLISION_LEVEL2_MAX_DURATION_MS = 300  # 中等碰撞最长持续时间(ms)
# 超过上述值即为等级 3（严重碰撞 — 重敲/摔落）

# ================= 报警配置 =================
ALARM_DURATION_MS         = 30000  # 报警持续时间(ms)
ALARM_ENABLE_LOCAL        = True   # 是否启用本地声光报警

# ================= 电源管理配置 =================
BATTERY_SAMPLE_MS         = 10000  # 电量采样间隔(ms)
BATTERY_ADC_PIN           = "PC4"  # 电池电压 ADC 引脚（ADC1_IN14）
BATTERY_DIVIDER_RATIO     = 1.45   # 分压比（电池电压 / ADC 电压）
# 六档 ADC 电压阈值 (mV)，基于锂电池放电曲线映射
# 档位0: <2000mV (电池<2.9V, 没电/未接电池)
# 档位1: ≥2000mV (电池≥2.9V, 危急, <5%)
# 档位2: ≥2614mV (电池≥3.79V, 低, 5-20%)
# 档位3: ≥2669mV (电池≥3.87V, 中等, 20-40%)
# 档位4: ≥2724mV (电池≥3.95V, 良好, 40-60%)
# 档位5: ≥2772mV (电池≥4.02V, 满, 60%+)
BATTERY_LEVEL_THRESHOLDS  = [2000, 2614, 2669, 2724, 2772]  # 五个分界点，分为六档
BATTERY_AUTO_SUSPEND_LEVEL = 2     # ≤2档自动进入省电模式

# ================= 功耗策略配置 =================
POWER_STATE_ACTIVE        = "ACTIVE"        # 正常工作状态
POWER_STATE_SUSPENDED     = "SUSPENDED"     # 挂起状态
POWER_STATE_DEEP_SLEEP    = "DEEP_SLEEP"    # 深度休眠状态
POWER_STATE_EMERGENCY     = "EMERGENCY"     # 超级省电（仅 GPS + 报警 + BLE）
POWER_STATE_CUSTOM        = "CUSTOM"        # 自定义（手动操作覆盖省电模式）

# ================= 看门狗配置 =================
WDT_TIMEOUT_MS               = 8000  # 硬件看门狗超时 (ms)，8 秒

# ================= 网络通信配置 =================
NETWORK_CONNECT_TIMEOUT_MS = 60000    # 4G网络连接超时时间 (ms)

# ================= MQTT通信配置 =================
MQTT_BROKER             = "101.37.104.185"    # ConnectLab 服务器地址
MQTT_PORT               = 46233               # ConnectLab 端口（每次创建会话不同）
MQTT_USERNAME           = "quectel"           # MQTT 用户名
MQTT_PASSWORD           = "12345678"          # MQTT 密码
MQTT_CLIENT_ID          = "66ccff"            # MQTT 客户端 ID
MQTT_KEEPALIVE          = 60                  # 心跳间隔 (秒)
MQTT_MAX_RETRY          = 3                   # 最大重试次数

# MQTT Topic 定义
MQTT_TOPIC_DATA         = "helmet/data"       # 传感器数据上传
MQTT_TOPIC_CONFIG       = "helmet/config"     # 云端配置下发
MQTT_TOPIC_ALARM        = "helmet/alarm"      # 紧急报警推送
MQTT_TOPIC_STATUS       = "helmet/status"     # 设备状态（含遗嘱消息）

# MQTT QoS 等级
MQTT_QOS_DATA           = 0                   # 传感器数据（允许丢失）
MQTT_QOS_ALARM          = 1                   # 报警数据（必须送达）
MQTT_QOS_CONFIG         = 1                   # 配置下发（必须送达）

# 遗嘱消息配置
MQTT_WILL_TOPIC         = "helmet/status"     # 遗嘱消息 Topic
MQTT_WILL_MESSAGE       = '{"status":"offline","reason":"unexpected"}'
MQTT_WILL_QOS           = 1
MQTT_WILL_RETAIN        = True

# ================= CloudService 配置 =================
CLOUD_UPLOAD_INTERVAL_MS = 2000    # 数据上传间隔 (ms)
CLOUD_GPS_TRACK_MAX      = 50      # GPS 轨迹点缓存上限

# ================= 移远云 Qth 配置 =================
QTH_PRODUCT_ID     = "p11yMv"                           # 产品 ID
QTH_PRODUCT_KEY    = "Vk9WUXFZZENkV00w"                 # 产品密钥
QTH_DEVICE_KEY     = "66ccff"                           # 设备 Key
QTH_SERVER         = "mqtt://iot-south.quectelcn.com:1883"  # 移远云服务器
QTH_APP_VERSION    = "v2.0.0"                           # 应用版本号（OTA 用）

# ================= LarkCloudService 配置 =================
LARK_UPLOAD_INTERVAL_MS = 2000    # 移远云数据上传间隔 (ms)
LARK_QUEUE_MAX_SIZE     = 50      # 发送队列最大长度

# ================= 显示配置 =================
LCD_BACKLIGHT_HIGH        = 100    # 高背光亮度(%)
LCD_BACKLIGHT_MEDIUM      = 60     # 中背光亮度(%)
LCD_BACKLIGHT_LOW         = 30     # 低背光亮度(%)
LIGHT_THRESHOLD_HIGH      = 4000   # 高光照阈值(ADC值)
LIGHT_THRESHOLD_LOW       = 1000   # 低光照阈值(ADC值)

# ================= LED配置 =================
LED_PIN_NAME              = "LED_BLUE"
LED_BLINK_INTERVAL_MS     = 500
LED_BLINK_MIN_MS          = 100
LED_BLINK_MAX_MS          = 5000
TIMER_ID_LED              = 1

# ================= BLE 蓝牙配置 =================
BLE_DEVICE_NAME           = "SmartHelmet-66ccff"    # BLE 广播设备名
BLE_SERVICE_UUID          = 0xFFF0                  # GATT 主服务 UUID
BLE_CHAR_DATA             = 0xFFF1                  # 头盔数据通道 (NOTIFY)
BLE_CHAR_NAV              = 0xFFF2                  # 导航指令通道 (WRITE)
BLE_CHAR_CTRL             = 0xFFF3                  # 骑行控制通道 (WRITE)
BLE_CHAR_ACK              = 0xFFF4                  # 报警确认通道 (WRITE)
BLE_MTU                   = 247                     # 最大传输单元
BLE_UPLOAD_INTERVAL_MS    = 2000                    # BLE 通知推送间隔 (ms)
BLE_KEEPALIVE_MS          = 5000                    # 心跳间隔 (ms)

# ================= LBS 基站定位配置 =================
LBS_TIMEOUT_MS          = 15000    # LBS 定位超时 (ms)
LBS_SAMPLE_MS           = 30000    # LBS 采样间隔 (ms)

# ================= PWM LED 配置 =================
EVENT_PWM_LED_ERROR     = "PWM_LED_ERROR"      # PWM控制错误
PWM_LED_PIN             = "PE11"               # PWM引脚（STM32 PE11, TIM1_CH2, D5）
PWM_LED_TIMER_ID        = 1                    # Timer1
PWM_LED_TIMER_CHANNEL   = 2                    # Channel 2
PWM_LED_FREQ            = 1000                 # PWM频率 (Hz)

# ================= PWM LED 闪烁配置 =================
PWM_BLINK_ON_DUTY       = 20     # 闪烁亮时占空比(%)，保护大功率LED
PWM_BLINK_INTERVAL_MS   = 500    # 闪烁间隔(ms)

# ================= LightService 自适应灯光配置 =================
LIGHT_DAY_ADC_THRESHOLD    = 30000   # 白天阈值（ADC值 < 此值 → 光照强 → 灯不开）
LIGHT_NIGHT_ADC_THRESHOLD  = 50000   # 晚上阈值（ADC值 > 此值 → 光照弱 → 灯最亮）
LIGHT_BRIGHTNESS_MIN       = 5       # 最小亮度（%）
LIGHT_BRIGHTNESS_MAX       = 50      # 最大亮度（%），50%PWM上限
LIGHT_BRIGHTNESS_DEFAULT   = 25      # 开灯默认亮度（%），留增减空间
LIGHT_GAMMA                = 1.5     # 非线性映射参数（>1时暗环境更敏感）
LIGHT_BRIGHTNESS_THRESHOLD = 3       # 亮度变化阈值（小于此值不调节）
LIGHT_DEBOUNCE_MS          = 50      # 防抖间隔（ms）
LIGHT_BRIGHTNESS_STEP      = 5       # 亮度调节步长（PWM 单位，5/50=10%显示）

# ================= 电源模式采样间隔 =================
TEMP_HUMID_SUSPENDED_MS    = 30000   # 省电模式温湿度采样间隔
LIGHTSENSOR_MANUAL_MS      = 30000   # 省电模式+手动灯光：光照采样间隔
GNSS_SUSPENDED_MS          = 10000   # 省电模式 GNSS 采样间隔
GNSS_EMERGENCY_MS          = 10000   # 紧急省电 GNSS 采样间隔（降频）

# ================= 语音模块UART配置 =================
VOICE_UART_ID       = 2        # UART总线编号（UART2，对应D52/D53引脚）
VOICE_UART_BAUDRATE = 115200   # 波特率（ASRPRO固定115200）

# ================= 语音指令映射表（ASRPRO hex → ControlService cmd）=================
VOICE_CMD_MAP = {
    0x00: "wake",              # 唤醒指令（语音："小洛包"）
    0x01: "light_on",
    0x02: "light_off",
    0x03: "brightness_up",
    0x04: "brightness_down",
    0x05: "light_auto",
    0x06: "volume_up",
    0x07: "volume_down",
    0x08: "alarm_cancel",
    0x09: "alarm_sos",
    0x0A: "alarm_stealth",
    0x0B: "power_save",
    0x0C: "power_normal",
    0x0D: "power_emergency",
    0x0E: "query_status",
    0x0F: "query_speed",
    0x10: "query_temp",
    0x11: "query_humid",
    0x12: "query_location",
    0x13: "query_battery",
    0x14: "query_heartrate",
    0x15: "query_spo2",
    0x16: "ble_connect",       # 蓝牙连接
    0x17: "ble_disconnect",    # 蓝牙断开
    0x18: "voice_sleep",       # 语音休眠
    0x19: "light_blink",       # PWM灯光闪烁
}

# ================= 控制指令 TTS 播报映射表 =================
CMD_TTS_MAP = {
    "wake": "小洛包在，有什么指示",
    "light_on": "灯光已开启",
    "light_off": "灯光已关闭",
    "brightness_up": "亮度增加",
    "brightness_down": "亮度降低",
    "light_auto": "灯光自动模式",
    "volume_up": "音量增加",
    "volume_down": "音量降低",
    "alarm_sos": "报警已触发",
    "alarm_cancel": "报警已取消",
    "power_save": "省电模式",
    "power_normal": "正常模式",
    "power_emergency": "紧急省电模式",
    "ble_disconnect": "蓝牙已断开",
    "voice_sleep": "好的",
    "light_blink": "灯光闪烁",
}

# ================= TTS 优先级 =================
PRIORITY_ALARM              = 0    # 报警语音（最高优先级）
PRIORITY_NAV                = 1    # 导航播报
PRIORITY_CTRL               = 2    # 控制反馈（最低优先级）

# ================= AT 通道互斥锁 =================
# 防止 GNSS/Audio/BLE/SMS 多线程并发 AT 命令导致 EC200U 固件崩溃
# GNSS 用非阻塞获取（拿不到锁就跳过本轮），Audio 用阻塞获取（必须播放）
import _thread as _at_thread
AT_LOCK = _at_thread.allocate_lock()