import machine
import time

from core.Base_Module import BaseModule
from core.config import EVENT_TEMP_HUMID_READY,EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE, TEMP_HUMID_SAMPLE_MS, POWER_STATE_ACTIVE, EVENT_POWER_STATE_CHANGE
from ahtx0 import AHT20

class TempHumidDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "temp_humid"

        self.cfg = {
            "i2c_id": 1,
            "i2c_freq": 400000,
            "i2c_timeout": 50000,
            "addr": 0x38,
            "sample_ms": TEMP_HUMID_SAMPLE_MS,
            "max_retry": 3
        }

        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE
        }

        self._data = {
            "temp": 0.0,
            "humid": 0.0,
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
                raise RuntimeError(f"AHT20未响应 (0x{self.cfg['addr']:02X})。扫描结果: {[hex(d) for d in devices]}")

            self.sensor = AHT20(self.i2c)

            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_power_state)

            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成 | 设备: {[hex(d) for d in devices]}")

        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return

        self.ctx["is_busy"] = True
        try:
            temp = self.sensor.temperature
            hum = self.sensor.relative_humidity

            self._data["temp"] = round(temp, 1)
            self._data["humid"] = round(hum, 1)
            self._data["valid"] = True
            self.ctx["err_count"] = 0

            if self.event_bus:
                self.event_bus.publish(EVENT_TEMP_HUMID_READY, self.get_data())

        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print(f"[{self.name}] 读取异常 ({self.ctx['err_count']}): {e}")

            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
            self.ctx["last_tick"] = now

    def _on_config_update(self, payload):
        if payload.get("target") == self.name and "sample_ms" in payload:
            self.cfg["sample_ms"] = int(payload["sample_ms"])
            print(f"[{self.name}] 采样间隔更新为 {self.cfg['sample_ms']}ms")

        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print(f"[{self.name}] 功耗状态: {old_state} -> {payload['power_state']}")

    def _on_power_state(self, payload):
        self.ctx["power_state"] = payload.get("power_state", POWER_STATE_ACTIVE)

    def get_data(self):
        return {
            "temp": self._data["temp"],
            "humid": self._data["humid"],
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
