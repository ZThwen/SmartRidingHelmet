"""
================================================================================
模块开发模板 - 快速开发指南
================================================================================

使用方法：
1. 复制此模板到目标目录（Drivers/ 或 Modules/）
2. 重命名为具体模块名（如 imu.py、alarm_service.py）
3. 根据注释提示填写具体实现
4. 在 config.py 中定义事件常量
5. 在 main.py 中导入并添加到 modules 列表

================================================================================
"""

import machine
import time

from Base_Module import BaseModule
from config import EVENT_XXX_READY, EVENT_XXX_ERROR, POWER_STATE_ACTIVE


class YourModule(BaseModule):
    """
    模块说明：[一句话描述模块功能]
    
    例如：
    - 温湿度传感器驱动（AHT20）
    - 碰撞检测服务
    - 报警联动服务
    """
    
    def __init__(self, event_bus=None):
        """
        \brief 初始化模块实例
        \param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus  # 保存事件总线引用
        self.name = "your_module"   # 模块标识符（必须唯一）
        
        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            # 硬件参数
            "i2c_id": 1,              # I2C/SPI/UART 总线ID
            "i2c_freq": 400000,       # 通信频率
            "addr": 0x38,             # 设备地址
            
            # 采样参数
            "sample_ms": 2000,        # 采样间隔（ms）
            "max_retry": 3,           # 最大重试次数
            
            # 业务参数
            "threshold": 2.5,         # 碰撞阈值（示例）
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,         # 初始化完成标志
            "is_busy": False,         # 操作中标志（防重入）
            "last_tick": 0,           # 上次执行时间戳
            "err_count": 0,           # 错误计数
            "power_state": POWER_STATE_ACTIVE,  # 功耗状态
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "value": 0.0,             # 传感器值或状态值
            "valid": False,           # 数据有效性标志
        }
        
        # 硬件句柄（根据实际硬件类型声明）
        self.i2c = None               # I2C 实例
        self.spi = None               # SPI 实例
        self.uart = None              # UART 实例

    def init(self):
        """
        \brief 初始化模块：硬件配置 + 订阅事件
        \note 失败时直接 raise，main.py会捕获并停止启动
        
        实现步骤：
        1. 初始化硬件（I2C/SPI/UART/ADC等）
        2. 验证设备在线（扫描设备地址或读取设备ID）
        3. 配置硬件参数（采样率、阈值等）
        4. 订阅事件（如果有）
        5. 设置 is_init 标志
        """
        try:
            # ====== 1. 硬件初始化 ======
            # 示例：I2C 设备
            self.i2c = machine.I2C(
                self.cfg["i2c_id"],
                freq=self.cfg["i2c_freq"]
            )
            
            # ====== 2. 验证设备在线 ======
            devices = self.i2c.scan()
            if self.cfg["addr"] not in devices:
                raise RuntimeError(f"设备未响应 (0x{self.cfg['addr']:02X})")
            
            # ====== 3. 配置硬件参数 ======
            # 根据具体硬件手册配置
            
            # ====== 4. 订阅事件 ======
            if self.event_bus:
                # 订阅配置更新事件
                self.event_bus.subscribe("CONFIG_UPDATE", self._on_config_update)
                # 订阅其他事件（根据业务需求）
                # self.event_bus.subscribe(EVENT_XXX, self._on_xxx)
            
            # ====== 5. 设置初始化标志 ======
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成")
            
        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise  # 抛出异常，main.py会捕获

    def tick(self):
        """
        \brief 周期调度：数据采集 + 事件发布
        \note 主循环每轮调用，必须快速返回（<5ms），不能阻塞
        
        实现步骤：
        1. 状态守卫（功耗模式检查）
        2. 时间片校验（采样间隔检查）
        3. 执行业务逻辑（读取数据、算法处理等）
        4. 发布事件
        5. 异常处理
        """
        # ====== 1. 状态守卫 ======
        if POWER_STATE_ACTIVE != self.ctx["power_state"]:
            return  # 非活动状态，立即返回

        # ====== 2. 时间片校验 ======
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return  # 未到采样间隔，立即返回

        # ====== 3. 执行业务逻辑 ======
        self.ctx["is_busy"] = True  # 设置忙标志
        try:
            # 示例：读取传感器数据
            # raw_data = self.i2c.readfrom(self.cfg["addr"], 6)
            # value = self._parse_data(raw_data)
            value = 0.0  # 示例值
            
            # 更新内部数据
            self._data["value"] = value
            self._data["valid"] = True
            self.ctx["err_count"] = 0  # 重置错误计数
            
            # ====== 4. 发布事件 ======
            if self.event_bus:
                self.event_bus.publish(EVENT_XXX_READY, self.get_data())
            
        except Exception as e:
            # ====== 5. 异常处理 ======
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print(f"[{self.name}] 读取异常 ({self.ctx['err_count']}): {e}")
            
            # 连续失败超限则发布故障事件
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_XXX_ERROR, {
                        "source": self.name,
                        "error": str(e)
                    })
        finally:
            self.ctx["is_busy"] = False
            self.ctx["last_tick"] = now  # 刷新时间戳

    # ==================== 事件回调 ====================
    def _on_config_update(self, payload):
        """
        \brief 配置更新回调
        \param payload: {"target": module_name, "key": value}
        """
        if payload.get("target") == self.name:
            # 更新配置参数
            if "sample_ms" in payload:
                self.cfg["sample_ms"] = int(payload["sample_ms"])
                print(f"[{self.name}] 采样间隔更新为 {self.cfg['sample_ms']}ms")

    # ==================== 辅助方法 ====================
    def get_data(self):
        """
        \brief 获取数据快照（供外部查询）
        \return dict 数据副本
        """
        return {
            "value": self._data["value"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        """
        \brief 获取运行状态（供外部查询）
        \return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }
    
    def _parse_data(self, raw_data):
        """
        \brief 数据解析（私有方法）
        \param raw_data: 原始字节
        \return 解析后的值
        """
        # 根据具体传感器协议实现
        return 0.0


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
