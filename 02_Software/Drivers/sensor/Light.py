"""
brief 光敏传感器驱动模块 (GL5528)
note 严格遵循四元组架构规范，使用ADC采集光敏电阻
      硬件：光敏电阻 GL5528（R316），接口引脚 PC5
"""
import time
from machine import ADC, Pin

from core.Base_Module import BaseModule
from core.config import EVENT_LIGHT_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE, EVENT_POWER_STATE_CHANGE, EVENT_LIGHT_CONTROL, POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY, LIGHT_SAMPLE_MS, LIGHTSENSOR_MANUAL_MS


class LightSensorDriver(BaseModule):
    
    def __init__(self, event_bus=None):
        """
        brief 初始化模块实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus  # 保存事件总线引用
        self.name = "light_Sensor"   # 模块标识符
        
        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            # 采样参数
            "sample_ms": LIGHT_SAMPLE_MS,  # 采样间隔（ms）
            "max_retry": 3,           # 最大重试次数
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,         # 初始化完成标志
            "is_busy": False,         # 操作中标志（防重入）
            "last_tick": 0,           # 上次执行时间戳
            "err_count": 0,           # 错误计数
            "power_state": POWER_STATE_ACTIVE,  # 功耗状态
            "light_mode": "auto",     # 灯光模式（自动/手动）
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "light_intensity": 0.0,   # 光照强度值
            "valid": False,           # 数据有效性标志
        }
        

    def init(self):
        """
        brief 初始化光敏传感器
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            # ====== 1. 硬件初始化 ======
            self.ldr = ADC(Pin('C5'))  # 对应您的 ADC_CHANNEL_15, PC5
            
            # ====== 4. 订阅事件 ======
            if self.event_bus:
                # 订阅配置更新事件
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)
                # 订阅灯光控制事件（用于动态调整采样间隔）
                self.event_bus.subscribe(EVENT_LIGHT_CONTROL, self._on_light_control)
            
            # ====== 5. 设置初始化标志 ======
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成")
            
        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise  # 抛出异常，main.py会捕获

    def tick(self):
        """
        brief 周期调度：数据采集 + 事件发布
        note 主循环每轮调用，必须快速返回（<5ms），不能阻塞
        """
        # ====== 1. 状态守卫 ======
        if self.ctx["power_state"] == POWER_STATE_EMERGENCY:
            if self.ctx.get("light_mode") != "auto":
                return  # EMERGENCY + 手动模式：停止采样

        # ====== 2. 时间片校验 ======
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return  # 未到采样间隔，立即返回

        # ====== 3. 执行业务逻辑 ======
        self.ctx["is_busy"] = True  # 设置忙标志
        try:
            light_intensity = self.ldr.read_u16()  # 读取原始 ADC 值
            
            # 更新内部数据
            self._data["light_intensity"] = light_intensity
            self._data["valid"] = True
            self.ctx["err_count"] = 0  # 重置错误计数
            
            # ====== 4. 发布事件 ======
            if self.event_bus:
                self.event_bus.publish(EVENT_LIGHT_READY, self.get_data())
            
        except Exception as e:
            # ====== 5. 异常处理 ======
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print(f"[{self.name}] 读取异常 ({self.ctx['err_count']}): {e}")
            
            # 连续失败超限则发布故障事件
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
            self.ctx["last_tick"] = now  # 刷新时间戳

    # ==================== 事件回调 ====================
    def _on_config_update(self, payload):
        """
        brief 配置更新回调
        param payload: {"target": module_name, "key": value}
        """
        # ====== 1. 采样间隔更新（模块特定配置）======
        if payload.get("target") == self.name and "sample_ms" in payload:
            self.cfg["sample_ms"] = int(payload["sample_ms"])
            print(f"[{self.name}] 采样间隔更新为 {self.cfg['sample_ms']}ms")
        
        # ====== 2. 功耗状态更新（全局配置）======
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            self._update_sample_ms()
            print(f"[{self.name}] 功耗状态: {old_state} -> {payload['power_state']}")

    def _on_light_control(self, payload):
        """
        brief 灯光模式变化回调（用于动态调整采样间隔）
        param payload: {cmd: "auto"/"on"/"off"/...}
        """
        cmd = payload.get("cmd", "")
        if cmd == "auto":
            self.ctx["light_mode"] = "auto"
        else:
            self.ctx["light_mode"] = "manual"
        self._update_sample_ms()

    def _update_sample_ms(self):
        """根据灯光模式和电源状态动态调整采样间隔"""
        if self.ctx["power_state"] == POWER_STATE_SUSPENDED:
            if self.ctx.get("light_mode") == "auto":
                self.cfg["sample_ms"] = LIGHT_SAMPLE_MS  # 2s
            else:
                self.cfg["sample_ms"] = LIGHTSENSOR_MANUAL_MS  # 30s
        elif self.ctx["power_state"] == POWER_STATE_EMERGENCY:
            self.cfg["sample_ms"] = LIGHT_SAMPLE_MS  # 2s
        elif self.ctx["power_state"] == POWER_STATE_ACTIVE:
            self.cfg["sample_ms"] = LIGHT_SAMPLE_MS  # 2s

    # ==================== 辅助方法 ====================
    def get_data(self):
        """
        brief 获取数据快照（供外部查询）
        return dict 数据副本
        """
        return {
            "light_intensity": self._data["light_intensity"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }

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
