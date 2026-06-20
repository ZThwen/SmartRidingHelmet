"""
brief 硬件配置参考（引脚、接口、设备地址）
note 集成测试时用于验证硬件连接是否正确
"""

# ================= I2C 总线 =================
I2C_ID     = 1
I2C_FREQ   = 400000

# AHT20 温湿度传感器
TEMP_HUMID_ADDR = 0x38

# LIS2DH12TR 加速度传感器
IMU_ADDR        = 0x19

# ================= ADC =================
LIGHT_ADC_PIN   = "PC5"      # GL5528 光敏电阻

# ================= GPIO =================
BUTTON_PIN      = "SW"       # SOS 按键
LED_PIN         = "LED_BLUE" # 指示灯

# ================= SPI =================
LCD_SPI_ID      = 1
LCD_DC_PIN      = "F12"
LCD_CS_PIN      = "D14"

# ================= PWM =================
PWM_LED_PIN      = "PE11"    # PWM 调光灯
PWM_LED_TIMER    = 1
PWM_LED_CHANNEL  = 2
PWM_LED_FREQ     = 1000

# ================= UART =================
VOICE_UART_ID    = 2         # ASRPRO 语音模块
VOICE_BAUDRATE   = 9600

# ================= BLE =================
BLE_NAME         = "SmartHelmet-66ccff"
BLE_SERVICE_UUID = 0xFFF0
BLE_CHAR_DATA    = 0xFFF1
BLE_CHAR_NAV     = 0xFFF2
BLE_CHAR_CTRL    = 0xFFF3
BLE_CHAR_ACK     = 0xFFF4
BLE_MTU          = 247
