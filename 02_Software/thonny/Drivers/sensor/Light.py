import time
from machine import ADC, Pin
from core.Base_Module import BaseModule
from core.config import EVENT_LIGHT_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE, POWER_STATE_ACTIVE, LIGHT_SAMPLE_MS
class LightSensorDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "light_Sensor"
        self.cfg = {
            "sample_ms": LIGHT_SAMPLE_MS,
            "max_retry": 3,
        }
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
        }
        self._data = {
            "light_intensity": 0.0,
            "valid": False,
        }
    def init(self):
        try:
            self.ldr = ADC(Pin('C5'))
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[%s] ✓ 初始化完成" % self.name)
        except Exception as e:
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise
    def tick(self):
        if POWER_STATE_ACTIVE != self.ctx["power_state"]:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return
        self.ctx["is_busy"] = True
        try:
            light_intensity = self.ldr.read_u16()
            self._data["light_intensity"] = light_intensity
            self._data["valid"] = True
            self.ctx["err_count"] = 0
            if self.event_bus:
                self.event_bus.publish(EVENT_LIGHT_READY, self.get_data())
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
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[%s] 功耗状态: %s -> %s" % (self.name, old_state, payload['power_state']))
    def get_data(self):
        return {
            "light_intensity": self._data["light_intensity"],
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
