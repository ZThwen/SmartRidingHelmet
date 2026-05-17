"""
brief 温湿度传感器驱动 (AHT20)
note 严格遵循四元组架构规范，适配移远模组默认I2C引脚
"""
import machine
import time

from core.Base_Module import BaseModule
from core.config import EVENT_TEMP_HUMID_READY,EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE, TEMP_HUMID_SAMPLE_MS, POWER_STATE_ACTIVE
from ahtx0 import AHT20


class TempHumidDriver(BaseModule):
    def __init__(self, event_bus=None):
        """
        brief 初始化驱动程序实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus  # 保存事件总线引用
        self.name = "temp_humid"    # 模块标识符
        
        self.cfg = {                # 静态配置
            "i2c_id": 1,            # 移远固件预定义的 I2C1
            "i2c_freq": 400000,     # 通信频率 400kHz
            "i2c_timeout": 50000,   # 超时 50ms
            "addr": 0x38,           # AHT20 固定地址
            "sample_ms": TEMP_HUMID_SAMPLE_MS,  # 默认采样间隔 2000ms
            "max_retry": 3          # 连续失败最大重试次数
        }

        self.ctx = {                # 运行时上下文
            "is_init": False,       # 硬件初始化完成标志
            "is_busy": False,       # I2C 操作中标志
            "last_tick": 0,         # 上次采样时间戳
            "err_count": 0,         # 连续采样错误计数
            "power_state": POWER_STATE_ACTIVE  # 功耗状态
        }

        self._data = {              # 传感器数据
            "temp": 0.0,            # 温度值 (℃)
            "humid": 0.0,           # 湿度值 (%RH)
            "valid": False          # 数据有效性标志
        }
        
        self.i2c = None             # I2C 实例句柄
        self.sensor = None          # AHT20 传感器实例

    def init(self):
        """
        brief 初始化模块：硬件配置 + 订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            # 1. 硬件初始化
            self.i2c = machine.I2C(
                self.cfg["i2c_id"],
                freq=self.cfg["i2c_freq"],
                timeout=self.cfg["i2c_timeout"]
            )
            
            # 2. 扫描验证设备在线
            devices = self.i2c.scan()
            if self.cfg["addr"] not in devices:
                raise RuntimeError(f"AHT20未响应 (0x{self.cfg['addr']:02X})。扫描结果: {[hex(d) for d in devices]}")
            
            # 3. 创建传感器实例
            self.sensor = AHT20(self.i2c)
            
            # 4. 订阅事件
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成 | 设备: {[hex(d) for d in devices]}")
            
        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """
        brief 周期调度：数据采集 + 事件发布
        note 主循环每轮调用，必须快速返回（<5ms）
        """
        # 状态守卫：功耗模式控制
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        # 时间片校验：未到采样间隔立即返回
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return

        # 执行采集
        self.ctx["is_busy"] = True
        try:
            # 读取传感器数据
            temp = self.sensor.temperature
            hum = self.sensor.relative_humidity
            
            # 更新内部数据
            self._data["temp"] = round(temp, 1)
            self._data["humid"] = round(hum, 1)
            self._data["valid"] = True
            self.ctx["err_count"] = 0
            
            # 发布数据就绪事件
            if self.event_bus:
                self.event_bus.publish(EVENT_TEMP_HUMID_READY, self.get_data())
            
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print(f"[{self.name}] 读取异常 ({self.ctx['err_count']}): {e}")
            
            # 连续失败超限则发布故障事件
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
            self.ctx["last_tick"] = now

    # ================= 辅助方法 =================
    def _on_config_update(self, payload):
        """
        brief 配置更新回调处理
        param payload: 配置事件负载
        note 
            - target: 指定目标模块（可选，用于模块特定配置）
            - sample_ms: 采样间隔（需要target）
            - power_state: 功耗状态（全局配置）
        """
        # ====== 1. 采样间隔更新（模块特定配置）======
        if payload.get("target") == self.name and "sample_ms" in payload:
            self.cfg["sample_ms"] = int(payload["sample_ms"])
            print(f"[{self.name}] 采样间隔更新为 {self.cfg['sample_ms']}ms")
        
        # ====== 2. 功耗状态更新（全局配置）======
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print(f"[{self.name}] 功耗状态: {old_state} -> {payload['power_state']}")

    def get_data(self):
        """
        brief 获取当前传感器数据快照
        return dict 数据副本 {temp, humid, valid, timestamp}
        """
        return {
            "temp": self._data["temp"],
            "humid": self._data["humid"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        """
        brief 查询模块运行状态快照
        return dict 运行上下文 {is_init, is_busy, err_count, power_state}
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }
