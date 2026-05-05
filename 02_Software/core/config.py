"""
brief 全局配置与事件常量定义
note 所有模块通信必须引用此处常量，禁止硬编码事件名或阈值
"""

# ================= 事件名称常量 =================
EVENT_SYSTEM_READY      = "SYSTEM_READY"        # 系统就绪事件
EVENT_TEMP_HUMID_READY  = "TEMP_HUMID_READY"    # 温湿度数据就绪事件
EVENT_SENSOR_ERROR      = "SENSOR_ERROR"        # 传感器错误事件
EVENT_CONFIG_UPDATE     = "CONFIG_UPDATE"       # 配置更新事件

# ================= 默认参数配置 =================
DEFAULT_SAMPLE_MS       = 2000    # 传感器默认采样间隔 (ms)
DEFAULT_RETRY_COUNT     = 3       # 硬件通信最大重试次数
DEFAULT_TIMEOUT_MS      = 500     # 单次硬件操作超时阈值 (ms)

# ================= 功耗策略配置 =================
POWER_STATE_ACTIVE      = "ACTIVE"        # 正常工作状态
POWER_STATE_SUSPENDED   = "SUSPENDED"     # 挂起状态
POWER_STATE_DEEP_SLEEP  = "DEEP_SLEEP"    # 深度休眠状态
