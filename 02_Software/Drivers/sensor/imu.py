"""
brief IMU加速度传感器驱动 (LIS2DH12TR)
note 严格遵循四元组架构规范，适配移远模组默认I2C引脚
      周期读取三轴加速度，计算合加速度，发布数据就绪事件
"""
import machine
import time
import math

from core.Base_Module import BaseModule
from core.config import EVENT_IMU_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE, EVENT_POWER_STATE_CHANGE, IMU_SAMPLE_MS, POWER_STATE_ACTIVE
from lis2dh12 import LIS2DH12


class IMUDriver(BaseModule):
    def __init__(self, event_bus=None):
        """
        brief 初始化IMU驱动实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus  # 保存事件总线引用
        self.name = "imu"           # 模块标识符（必须唯一）
        
        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            # 硬件参数
            "i2c_id": 1,            # 移远固件预定义的 I2C1
            "i2c_freq": 400000,     # 通信频率 400kHz
            "i2c_timeout": 50000,   # 超时 50ms
            "addr": 0x19,           # LIS2DH12TR 固定地址
            "sample_ms": IMU_SAMPLE_MS,  # 默认采样间隔 200ms（高频用于碰撞检测）
            "max_retry": 3,         # 连续失败最大重试次数
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,       # 硬件初始化完成标志
            "is_busy": False,       # I2C 操作中标志
            "last_tick": 0,         # 上次采样时间戳
            "err_count": 0,         # 连续采样错误计数
            "power_state": POWER_STATE_ACTIVE  # 功耗状态（仅记录，不阻止采集）
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "acc_x": 0.0,           # X轴加速度 (m/s²)
            "acc_y": 0.0,           # Y轴加速度 (m/s²)
            "acc_z": 0.0,           # Z轴加速度 (m/s²)
            "acc_total": 0.0,       # 合加速度 = sqrt(x² + y² + z²) (m/s²)
            "valid": False          # 数据有效性标志
        }
        
        self.i2c = None             # I2C 实例句柄
        self.sensor = None          # LIS2DH12 传感器实例
        self._abandoned = False     # 连续10次失败后放弃标志

    def init(self):
        """
        brief 初始化模块：硬件配置 + 订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            # ====== 1. 硬件初始化 ======
            self.i2c = machine.I2C(
                self.cfg["i2c_id"],
                freq=self.cfg["i2c_freq"],
                timeout=self.cfg["i2c_timeout"]
            )
            
            # ====== 2. 扫描验证设备在线 ======
            devices = self.i2c.scan()
            if self.cfg["addr"] not in devices:
                raise RuntimeError(
                    f"LIS2DH12未响应 (0x{self.cfg['addr']:02X})。扫描结果: {[hex(d) for d in devices]}"
                )
            
            # ====== 3. 创建传感器实例 ======
            self.sensor = LIS2DH12(self.i2c)
            
            # ====== 4. 订阅事件 ======
            if self.event_bus:
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)
            
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成 | 设备: {[hex(d) for d in devices]}")
            
        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """
        brief 周期调度：数据采集 + 事件发布
        note 主循环每轮调用，必须快速返回（<5ms），不能阻塞
        note IMU为安全保障模块，不判断功耗状态，始终持续采集
        """
        # 放弃检查：连续10次失败后不再尝试
        if self._abandoned:
            return
        # 时间片校验：未到采样间隔立即返回
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return

        # 执行采集
        self.ctx["is_busy"] = True
        try:
            # ====== 读取传感器数据 ======
            acc_x, acc_y, acc_z = self.sensor.acceleration
            
            # ====== 计算合加速度 ======
            acc_total = math.sqrt(acc_x ** 2 + acc_y ** 2 + acc_z ** 2)
            
            # ====== 更新内部数据 ======
            self._data["acc_x"] = round(acc_x, 3)
            self._data["acc_y"] = round(acc_y, 3)
            self._data["acc_z"] = round(acc_z, 3)
            self._data["acc_total"] = round(acc_total, 3)
            self._data["valid"] = True
            self.ctx["err_count"] = 0
            
            # ====== 发布数据就绪事件 ======
            if self.event_bus:
                self.event_bus.publish(EVENT_IMU_READY, self.get_data())
            
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[%s] 读取异常 (%d): %s" % (self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] >= 10:
                self._abandoned = True
                print("[%s] 放弃: 连续 10 次读取失败" % self.name)
            # 连续失败超限则发布故障事件
            elif self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
            self.ctx["last_tick"] = now

    # ==================== 事件回调 ====================
    def _on_config_update(self, payload):
        """
        brief 配置更新回调处理
        param payload: 配置事件负载
        """
        # 采样间隔更新（模块特定配置）
        if payload.get("target") == self.name and "sample_ms" in payload:
            self.cfg["sample_ms"] = int(payload["sample_ms"])
            print(f"[{self.name}] 采样间隔更新为 {self.cfg['sample_ms']}ms")
        
        # 功耗状态更新（全局配置）——仅记录状态，不影响采集
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]
            print(f"[{self.name}] 功耗状态记录: {payload['power_state']}")

    # ==================== 辅助方法 ====================
    def get_data(self):
        """
        brief 获取当前传感器数据快照
        return dict 数据副本 {acc_x, acc_y, acc_z, acc_total, valid, timestamp}
        """
        return {
            "acc_x": self._data["acc_x"],
            "acc_y": self._data["acc_y"],
            "acc_z": self._data["acc_z"],
            "acc_total": self._data["acc_total"],
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
