
from machine import Pin
import time

from core.Base_Module import BaseModule
from core.config import EVENT_BUTTON_PRESSED, EVENT_BUTTON_ERROR, POWER_STATE_ACTIVE, BUTTON_DEBOUNCE_MS


class Button(BaseModule):
    
    def __init__(self, event_bus=None):
        """
        brief 初始化模块实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus  # 保存事件总线引用
        self.name = "button"   # 模块标识符（必须唯一）
        
        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            # 硬件参数
            "id": 'SW',
            "mode": Pin.IN,
            "pull": Pin.PULL_DOWN,
            
            # 采样参数
            "debounce_ms": BUTTON_DEBOUNCE_MS, # 防抖动窗口（ms）
            "max_retry": 3,             # 最大重试次数
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,         # 初始化完成标志
            "is_busy": False,         # 操作中标志（防重入）
            "last_tick": 0,           # 上次执行时间戳
            "err_count": 0,           # 错误计数
            "power_state": POWER_STATE_ACTIVE,  # 功耗状态
            "button_pressed_flag": False,  # ISR 标志位：IRQ 中置位，tick() 中消费
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "valid": False,           # 数据有效性标志
        }

        self.button = None

    def init(self):
        """
        brief 初始化模块：硬件配置 + 订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动

        """
        try:
            self.button = Pin(self.cfg["id"], self.cfg["mode"], self.cfg["pull"])
            self.button.irq(trigger=Pin.IRQ_RISING, handler=self.button_handler)
            
            # ====== 5. 设置初始化标志 ======
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成")
            
        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise  # 抛出异常，main.py会捕获

    def tick(self):
        """
        brief 主循环调度：检查 ISR 标志位并发布事件
        note ISR 只设置标志位，这里消费标志位并发布事件，避免 ISR 中持锁
        """
        if not self.ctx["is_init"]:
            return

        self.ctx["last_hb"] = time.ticks_ms()
        if self.ctx["button_pressed_flag"]:
            self.ctx["button_pressed_flag"] = False
            if self.event_bus:
                self.event_bus.publish(EVENT_BUTTON_PRESSED, {
                    "timestamp": time.ticks_ms()
                })

    # ==================== 事件回调 ====================
    def button_handler(self, pin):
        """
        brief 按键中断回调（ISR 上下文，必须快速返回）
        note 不直接 publish()，仅设置标志位，由 tick() 消费
        """
        now = time.ticks_ms()
        if self.cfg["debounce_ms"] > time.ticks_diff(now, self.ctx["last_tick"]):
            return
        self.ctx["last_tick"] = now

        if pin.value() == 1:
            self.ctx["button_pressed_flag"] = True

    # ==================== 辅助方法 ====================
    def get_data(self):
        pass

    def get_status(self):
        """
        brief 获取运行状态（供外部查询）
        return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }


# ================================================================================
# 快速开发检查清单
# ================================================================================
"""
□ 修改类名和 self.name
□ 在 config.py 中定义事件常量（EVENT_XXX_READY、EVENT_XXX_ERROR）
□ 实现 init() 中的硬件初始化逻辑
□ 实现 tick() 中的数据采集/业务逻辑
□ 根据需要订阅事件（在 init() 中）
□ 根据需要发布事件（在 tick() 中）
□ 在 main.py 中导入模块类
□ 在 main.py 的 modules 列表中添加实例
□ 测试验证功能正常
"""

# ================================================================================
# 常见硬件初始化示例
# ================================================================================
"""
【I2C 设备】
self.i2c = machine.I2C(1, freq=400000)
devices = self.i2c.scan()
data = self.i2c.readfrom(addr, length)
self.i2c.writeto(addr, data)

【SPI 设备】
self.spi = machine.SPI(1, baudrate=1000000, polarity=0, phase=0)
data = self.spi.read(length)

【UART 设备】
self.uart = machine.UART(1, baudrate=9600)
data = self.uart.read()

【ADC 设备】
self.adc = machine.ADC(machine.Pin('A0'))
value = self.adc.read()

【GPIO 设备】
self.pin = machine.Pin('D2', machine.Pin.IN, machine.Pin.PULL_UP)
value = self.pin.value()
"""
