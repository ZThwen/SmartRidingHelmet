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

# 蓝牙(BLE)相关事件
EVENT_BLE_CONNECTED         = "BLE_CONNECTED"          # BLE 连接成功
EVENT_BLE_DISCONNECTED      = "BLE_DISCONNECTED"       # BLE 断开连接
EVENT_NAV_CMD               = "NAV_CMD"                # 导航指令（手机→头盔）
EVENT_RIDE_CONTROL          = "RIDE_CONTROL"           # 骑行控制指令
EVENT_BLE_ALARM_ACK         = "BLE_ALARM_ACK"          # 报警确认（手机取消）

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
TTS_BATTERY_LOW           = "当前电量不足，请及时充电"
TTS_BATTERY_CRITICAL      = "电池电量严重不足，请立即充电"
TTS_GPS_LOST              = "GPS信号已丢失"

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
BATTERY_LOW_THRESHOLD     = 20     # 低电量阈值(%)
BATTERY_CRITICAL_THRESHOLD = 10    # 严重不足阈值(%)

# ================= 功耗策略配置 =================
POWER_STATE_ACTIVE        = "ACTIVE"        # 正常工作状态
POWER_STATE_SUSPENDED     = "SUSPENDED"     # 挂起状态
POWER_STATE_DEEP_SLEEP    = "DEEP_SLEEP"    # 深度休眠状态

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