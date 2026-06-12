import time
from core.Base_Module import BaseModule
from core.config import (
    EVENT_LBS_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE,
    LBS_TIMEOUT_MS, LBS_SAMPLE_MS, POWER_STATE_ACTIVE,
)
# CPython 兼容
try:
    _ticks_ms = time.ticks_ms
except AttributeError:
    import time as _time
    def _ticks_ms():
        return int(_time.time() * 1000)
class LBSDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "lbs"
        self.cfg = {
            "timeout_ms": LBS_TIMEOUT_MS,
            "sample_ms": LBS_SAMPLE_MS,
        }
        self.ctx = {
            "is_init": False,
            "is_positioning": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
        }
        self._data = {
            "latitude": None,
            "longitude": None,
            "accuracy": None,
            "valid": False,
        }
        self._lbs = None
    def init(self):
        try:
            from quectel import LBS as _LBS
            self._lbs = _LBS()
            self.ctx["is_init"] = True
            print("[{}] 初始化完成".format(self.name))
        except Exception as e:
            print("[{}] 初始化失败: {}".format(self.name, e))
            raise
    def tick(self):
        if not self.ctx["is_init"]:
            return
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        if self.ctx["is_positioning"]:
            return
        now = _ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return
        self.ctx["last_tick"] = now
        self._do_positioning()
    def _do_positioning(self):
        if self.ctx["is_positioning"]:
            return
        if not self._lbs:
            return
        self.ctx["is_positioning"] = True
        try:
            loc = self._lbs.get_location(self.cfg["timeout_ms"])
            print("[{}] get_location 返回: {}".format(self.name, loc))
            if loc and "latitude" in loc and "longitude" in loc:
                self._data["latitude"] = loc["latitude"]
                self._data["longitude"] = loc["longitude"]
                self._data["accuracy"] = loc.get("accuracy", 0)
                self._data["valid"] = True
                self.ctx["err_count"] = 0
                if self.event_bus:
                    self.event_bus.publish(EVENT_LBS_READY, {
                        "latitude": loc["latitude"],
                        "longitude": loc["longitude"],
                        "accuracy": loc.get("accuracy", 0),
                        "source": "lbs",
                        "timestamp": _ticks_ms(),
                    })
                print("[{}] 定位成功: {:.4f}, {:.4f} (精度: {:.0f}m)".format(
                    self.name, loc["latitude"], loc["longitude"], loc.get("accuracy", 0)))
            else:
                self._data["valid"] = False
                self.ctx["err_count"] += 1
                print("[{}] 定位失败 (err_count={})".format(self.name, self.ctx["err_count"]))
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 定位异常: {}".format(self.name, e))
            if self.event_bus:
                self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_positioning"] = False
    def deinit(self):
        try:
            if self._lbs:
                self._lbs.deinit()
                self._lbs = None
            self.ctx["is_init"] = False
            print("[{}] 已释放".format(self.name))
        except Exception as e:
            print("[{}] 释放失败: {}".format(self.name, e))
    def get_data(self):
        return {
            "latitude": self._data["latitude"],
            "longitude": self._data["longitude"],
            "accuracy": self._data["accuracy"],
            "valid": self._data["valid"],
            "timestamp": _ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_positioning": self.ctx["is_positioning"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
        }
