import time
from quectel import GNSS
from core.Base_Module import BaseModule
from core.config import (EVENT_GNSS_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE,
                    EVENT_GPS_LOST, GNSS_SAMPLE_MS, POWER_STATE_ACTIVE)
GNSS_STATE_IDLE     = "idle"
GNSS_STATE_STARTING = "starting"
GNSS_STATE_SEARCH   = "searching"
GNSS_STATE_FIXED    = "fixed"
GNSS_STATE_LOST     = "lost"
class GNSSDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "gnss"
        self.cfg = {
            "sample_ms": GNSS_SAMPLE_MS,
            "max_retry": 3,
            "lost_count": 5,
        }
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
            "gnss_state": GNSS_STATE_IDLE,
            "no_fix_count": 0,
            "gps_lost_reported": False,
        }
        self._data = {
            "latitude": 0.0,
            "longitude": 0.0,
            "altitude": 0.0,
            "speed_kmh": 0.0,
            "cog": 0.0,
            "signal_quality": "none",
            "valid": False,
        }
        self.gnss = None
    def init(self):
        try:
            self.gnss = GNSS()
            if not self.gnss.start():
                raise RuntimeError("GNSS 启动失败")
            self.ctx["gnss_state"] = GNSS_STATE_SEARCH
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[%s] ✓ 初始化完成 | 采样间隔:%sms" % (self.name, self.cfg['sample_ms']))
        except Exception as e:
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise
    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return
        self.ctx["is_busy"] = True
        try:
            loc = self.gnss.get_location()
            if loc:
                self._data["latitude"] = loc["latitude"]
                self._data["longitude"] = loc["longitude"]
                self._data["altitude"] = loc["altitude"]
                self._data["speed_kmh"] = loc["speed_kmh"]
                self._data["cog"] = loc.get("cog", 0.0)
                self._data["valid"] = True
                self.ctx["err_count"] = 0
                self.ctx["no_fix_count"] = 0
                satellites = loc.get("satellites", 0)
                hdop = loc.get("hdop", 99.0)
                if satellites >= 4 and hdop < 2.0:
                    self._data["signal_quality"] = "good"
                elif satellites >= 3 and hdop < 5.0:
                    self._data["signal_quality"] = "fair"
                elif satellites > 0:
                    self._data["signal_quality"] = "poor"
                else:
                    self._data["signal_quality"] = "none"
                old_state = self.ctx["gnss_state"]
                self.ctx["gnss_state"] = GNSS_STATE_FIXED
                self.ctx["gps_lost_reported"] = False
                if self.event_bus:
                    self.event_bus.publish(EVENT_GNSS_READY, self.get_data())
                if old_state != GNSS_STATE_FIXED:
                    print("[%s] ✓ 定位成功 | %.4f, %.4f | %s" % (self.name, loc['latitude'], loc['longitude'], self._data['signal_quality']))
            else:
                self._data["valid"] = False
                self.ctx["no_fix_count"] += 1
                if self.ctx["gnss_state"] == GNSS_STATE_FIXED:
                    self.ctx["gnss_state"] = GNSS_STATE_SEARCH
                if (self.ctx["no_fix_count"] >= self.cfg["lost_count"]
                        and not self.ctx["gps_lost_reported"]
                        and self.event_bus):
                    self.ctx["gnss_state"] = GNSS_STATE_LOST
                    self.ctx["gps_lost_reported"] = True
                    self.event_bus.publish(EVENT_GPS_LOST, {
                        "source": self.name,
                        "timestamp": time.ticks_ms()
                    })
                    print("[%s] ⚠ GPS 信号丢失" % self.name)
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] 读取异常 (%s): %s" % (self.name, self.ctx['err_count'], e))
            if self.ctx["err_count"] > self.cfg["max_retry"] and self.event_bus:
                self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
            self.ctx["last_tick"] = now
    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "sample_ms" in payload:
                self.cfg["sample_ms"] = int(payload["sample_ms"])
                print("[%s] 采样间隔更新为 %sms" % (self.name, self.cfg['sample_ms']))
            if "lost_count" in payload:
                self.cfg["lost_count"] = int(payload["lost_count"])
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]
            print("[%s] 功耗状态: %s" % (self.name, payload['power_state']))
    def get_data(self):
        return {
            "latitude": self._data["latitude"],
            "longitude": self._data["longitude"],
            "altitude": self._data["altitude"],
            "speed_kmh": self._data["speed_kmh"],
            "cog": self._data["cog"],
            "signal_quality": self._data["signal_quality"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "gnss_state": self.ctx["gnss_state"],
            "no_fix_count": self.ctx["no_fix_count"]
        }
    def stop(self):
        try:
            if self.gnss:
                self.gnss.stop()
            self.ctx["gnss_state"] = GNSS_STATE_IDLE
            print("[%s] ✓ GNSS 已停止" % self.name)
            return True
        except Exception as e:
            print("[%s] ✗ 停止失败: %s" % (self.name, e))
            return False