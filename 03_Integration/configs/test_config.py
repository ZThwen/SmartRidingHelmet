"""
brief 集成测试通用配置
note 所有集成测试引用此配置，统一超时、重试等参数
"""

# ================= 测试超时配置 =================
PUMP_DURATION_S  = 3       # 泵循环默认持续时间（秒）
OBSERVE_S        = 5       # 观察等待时间（秒）
LONG_OBSERVE_S   = 15      # 长时间观察（BLE 连接等）
SHORT_PUMP_S     = 1       # 短泵循环（指令发送后等待）

# ================= 循环配置 =================
SLEEP_MS         = 10      # 主循环 sleep_ms
LOOP_INTERVAL    = 200     # 数据快照打印间隔（循环次数）

# ================= 重试配置 =================
MAX_RETRY        = 3       # 最大重试次数
RETRY_DELAY_MS   = 100     # 重试间隔（ms）

# ================= 报告配置 =================
REPORT_DIR       = "../reports"
EVIDENCE_DIR     = ".omo/evidence"
