import machine
import time
import math
from core.Base_Module import BaseModule
from core.config import EVENT_IMU_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE, IMU_SAMPLE_MS, POWER_STATE_ACTIVE
from lis2dh12 import LIS2DH12
class IMUDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "imu"
        self.cfg = {
            "i2c_id": 1,
            "i2c_freq": 400000,
            "i2c_timeout": 50000,
            "addr": 0x19,
            "sample_ms": IMU_SAMPLE_MS,
            "max_retry": 3,
        }
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE
        }
        self._data = {
            "acc_x": 0.0,
            "acc_y": 0.0,
            "acc_z": 0.0,
            "acc_total": 0.0,
            "valid": False
        }
        self.i2c = None
        self.sensor = None
    def init(self):
        try:
            self.i2c = machine.I2C(
                self.cfg["i2c_id"],
                freq=self.cfg["i2c_freq"],
                timeout=self.cfg["i2c_timeout"]
            )
            devices = self.i2c.scan()
            if self.cfg["addr"] not in devices:
                raise RuntimeError(
                    "LIS2DH12未响应 (0x%02X)。扫描结果: %s" % (self.cfg['addr'], [hex(d) for d in devices])
                )
            self.sensor = LIS2DH12(self.i2c)
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[%s] ✓ 初始化完成 | 设备: %s" % (self.name, [hex(d) for d in devices]))
        except Exception as e:
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise
    def tick(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return
        self.ctx["is_busy"] = True
        try:
            acc_x, acc_y, acc_z = self.sensor.acceleration
            acc_total = math.sqrt(acc_x ** 2 + acc_y ** 2 + acc_z ** 2)
            self._data["acc_x"] = round(acc_x, 3)
            self._data["acc_y"] = round(acc_y, 3)
            self._data["acc_z"] = round(acc_z, 3)
            self._data["acc_total"] = round(acc_total, 3)
            self._data["valid"] = True
            self.ctx["err_count"] = 0
            if self.event_bus:
                self.event_bus.publish(EVENT_IMU_READY, self.get_data())
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[%s] 读取异常 (%s): %s" % (self.name, self.ctx['err_count'], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
            self.ctx["last_tick"] = now
    def _on_config_update(self, payload):
        if payload.get("target") == self.name and "sample_ms" in payload:
            self.cfg["sample_ms"] = int(payload["sample_ms"])
            print("[%s] 采样间隔更新为 %sms" % (self.name, self.cfg['sample_ms']))
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]
            print("[%s] 功耗状态记录: %s" % (self.name, payload['power_state']))
    def get_data(self):
        return {
            "acc_x": self._data["acc_x"],
            "acc_y": self._data["acc_y"],
            "acc_z": self._data["acc_z"],
            "acc_total": self._data["acc_total"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }
