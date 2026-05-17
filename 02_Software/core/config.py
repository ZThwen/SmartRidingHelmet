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
EVENT_BATTERY_LOW           = "BATTERY_LOW"           # 低电量警告
EVENT_BATTERY_CRITICAL      = "BATTERY_CRITICAL"      # 电量严重不足
EVENT_POWER_STATE_CHANGE    = "POWER_STATE_CHANGE"    # 功耗状态切换

# GNSS相关事件
EVENT_GPS_LOST              = "GPS_LOST"              # GPS信号丢失

# 网络相关事件
EVENT_NETWORK_CONNECTED     = "NETWORK_CONNECTED"     # 网络连接成功
EVENT_NETWORK_DISCONNECTED  = "NETWORK_DISCONNECTED"  # 网络断开
EVENT_DATA_UPLOAD_SUCCESS   = "DATA_UPLOAD_SUCCESS"   # 数据上传成功
EVENT_DATA_UPLOAD_FAILED    = "DATA_UPLOAD_FAILED"    # 数据上传失败

# ================= 默认参数配置 =================
# 传感器采样间隔
TEMP_HUMID_SAMPLE_MS   = 2000    # 温湿度传感器采样间隔 (ms)
IMU_SAMPLE_MS          = 100     # IMU传感器采样间隔 (ms) - 碰撞检测需要高频
GNSS_SAMPLE_MS         = 2000    # GNSS采样间隔 (ms)
LIGHT_SAMPLE_MS        = 2000    # 光照传感器采样间隔 (ms)
LCD_SAMPLE_MS          = 2000    # LCD显示更新间隔 (ms)
DEFAULT_SAMPLE_MS      = 2000    # 传感器默认采样间隔 (ms)

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
AUDIO_SPEAKER_VOLUME      = 5                      # 扬声器音量(0-7)
AUDIO_ALARM_LOOP_COUNT    = 3                      # 报警音循环次数

# ================= 碰撞检测配置 =================
COLLISION_THRESHOLD_LOW   = 2.0    # 碰撞检测低阈值(g)
COLLISION_THRESHOLD_HIGH  = 4.0    # 碰撞检测高阈值(g)
COLLISION_WINDOW_SIZE     = 10     # 滑动窗口大小
COLLISION_DURATION_MS     = 100    # 持续时间阈值(ms)

# ================= 报警配置 =================
ALARM_DURATION_MS         = 30000  # 报警持续时间(ms)
ALARM_ENABLE_LOCAL        = True   # 是否启用本地声光报警

# ================= 电源管理配置 =================
BATTERY_SAMPLE_MS         = 10000  # 电量采样间隔(ms)
BATTERY_LOW_THRESHOLD     = 20     # 低电量阈值(%)
BATTERY_CRITICAL_THRESHOLD = 10    # 严重不足阈值(%)

# ================= 功耗策略配置 =================
POWER_STATE_ACTIVE        = "ACTIVE"        # 正常工作状态
POWER_STATE_SUSPENDED     = "SUSPENDED"     # 挂起状态
POWER_STATE_DEEP_SLEEP    = "DEEP_SLEEP"    # 深度休眠状态

# ================= 网络通信配置 =================
NETWORK_CONNECT_TIMEOUT_MS = 60000    # 4G网络连接超时时间 (ms)

# ================= MQTT通信配置 =================
MQTT_BROKER             = "172.188.83.251"    # ConnectLab 服务器地址
MQTT_PORT               = 48513               # ConnectLab 端口（每次创建会话不同）
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