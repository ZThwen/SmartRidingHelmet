import time
import json

from core.Base_Module import BaseModule
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_VOICE_CMD,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
    POWER_STATE_CUSTOM, EVENT_TTS_REQUEST,
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    LIGHT_BRIGHTNESS_MAX,
)

try:
    _ticks_ms = time.ticks_ms
except AttributeError:
    def _ticks_ms():
        return int(time.time() * 1000)

class ControlService(BaseModule):

    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "control_service"
        self.cfg = {
            "brightness_step": 10,
            "brightness_max": LIGHT_BRIGHTNESS_MAX,
            "volume_step": 1,
            "volume_max": 5,
            "volume_min": 0,
            "default_brightness": LIGHT_BRIGHTNESS_MAX,
            "cmd_debounce_ms": 300,
        }
        self.ctx = {
            "is_init": False,
            "err_count": 0,
            "last_cmd_tick": 0,
        }
        self._data = {
            "last_cmd": "",
            "last_cmd_source": "",
        }
        self._control_state = {
            "light_mode": "auto",
            "light_brightness": 0,
            "volume": 5,
            "power_mode": "active",
        }
        self._sensor_cache = {
            "temperature": None,
            "humidity": None,
            "speed_kmh": None,
            "latitude": None,
            "longitude": None,
        }
        self._alarm_active = False
        self._cmd_handlers = {
            "light_on":        lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "on"}),
            "light_off":       lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "off"}),
            "light_auto":      lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "auto"}),
            "brightness_up":   lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "brightness_up"}),
            "brightness_down": lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "brightness_down"}),
            "volume_up":       lambda: self._pub(EVENT_VOLUME_CONTROL, {"cmd": "up"}),
            "volume_down":     lambda: self._pub(EVENT_VOLUME_CONTROL, {"cmd": "down"}),
            "alarm_cancel":    lambda: self._pub(EVENT_ALARM_CONTROL, {"cmd": "cancel"}),
            "alarm_sos":       lambda: self._pub(EVENT_ALARM_CONTROL, {"cmd": "sos"}),
            "alarm_stealth":   lambda: self._pub(EVENT_ALARM_CONTROL, {"cmd": "stealth"}),
            "power_save":      lambda: self._pub(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_SUSPENDED}),
            "power_normal":    lambda: self._pub(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_ACTIVE}),
            "power_emergency": lambda: self._pub(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_EMERGENCY}),
            "query_status":    lambda: self._query_status(),
            "query_speed":     lambda: self._query_speed(),
            "query_temp":      lambda: self._query_temp(),
            "query_humid":     lambda: self._query_humid(),
            "query_location":  lambda: self._query_location(),
            "query_battery":   lambda: self._tts("电量信息暂不可用"),
        }

    def init(self):
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_RIDE_CONTROL, self._on_ride_control)
                self.event_bus.subscribe(EVENT_VOICE_CMD, self._on_voice_cmd)
                self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
                self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)
        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        pass

    def _pub(self, event, payload):
        if self.event_bus:
            self.event_bus.publish(event, payload)

    def _on_ride_control(self, payload):
        raw = payload.get("raw", "")
        try:
            cmd_obj = json.loads(raw)
        except Exception as e:
            print("[%s] JSON err: %s" % (self.name, e))
            self.ctx["err_count"] += 1
            return
        if cmd_obj.get("a") != "ctrl":
            return
        cmd = cmd_obj.get("d", {}).get("cmd", "")
        self._execute_cmd(cmd, source="ble")

    def _on_voice_cmd(self, payload):
        cmd = payload.get("cmd", "")
        self._execute_cmd(cmd, source="voice")

    def _execute_cmd(self, cmd, source="unknown"):
        if not cmd:
            return
        now = _ticks_ms()
        if time.ticks_diff(now, self.ctx["last_cmd_tick"]) < self.cfg["cmd_debounce_ms"]:
            return
        handler = self._cmd_handlers.get(cmd)
        if handler:
            try:
                handler()
                self.ctx["last_cmd_tick"] = now
                self._data["last_cmd"] = cmd
                self._data["last_cmd_source"] = source
                self._update_control_state(cmd)
                self._push_state()
                if cmd not in ("power_save", "power_normal", "power_emergency") and not cmd.startswith("query_"):
                    if self._control_state["power_mode"] != "active":
                        self._control_state["power_mode"] = "custom"
                        if self.event_bus:
                            self.event_bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_CUSTOM})
                print("[%s] cmd=%s src=%s" % (self.name, cmd, source))
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[%s] cmd err: %s cmd=%s" % (self.name, e, cmd))
        else:
            print("[%s] unknown: %s" % (self.name, cmd))

    def _update_control_state(self, cmd):
        if cmd == "light_on":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = self.cfg["default_brightness"]
        elif cmd == "light_off":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = 0
        elif cmd == "brightness_up":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = min(
                self._control_state["light_brightness"] + self.cfg["brightness_step"],
                self.cfg["brightness_max"])
        elif cmd == "brightness_down":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = max(
                self._control_state["light_brightness"] - self.cfg["brightness_step"], 0)
        elif cmd == "light_auto":
            self._control_state["light_mode"] = "auto"
        elif cmd == "volume_up":
            self._control_state["volume"] = min(
                self._control_state["volume"] + self.cfg["volume_step"],
                self.cfg["volume_max"])
        elif cmd == "volume_down":
            self._control_state["volume"] = max(
                self._control_state["volume"] - self.cfg["volume_step"],
                self.cfg["volume_min"])
        elif cmd == "power_save":
            self._control_state["power_mode"] = "suspended"
        elif cmd == "power_normal":
            self._control_state["power_mode"] = "active"
        elif cmd == "power_emergency":
            self._control_state["power_mode"] = "emergency"

    def _on_temp_humid(self, payload):
        if payload.get("valid"):
            self._sensor_cache["temperature"] = payload.get("temp")
            self._sensor_cache["humidity"] = payload.get("humid")

    def _on_gnss(self, payload):
        if payload.get("valid"):
            self._sensor_cache["speed_kmh"] = payload.get("speed_kmh")
            self._sensor_cache["latitude"] = payload.get("latitude")
            self._sensor_cache["longitude"] = payload.get("longitude")

    def _on_alarm_triggered(self, payload):
        self._alarm_active = True

    def _on_alarm_canceled(self, payload):
        self._alarm_active = False

    def _tts(self, text):
        if self._alarm_active:
            print("[%s] TTS blocked during alarm" % self.name)
            return
        if self.event_bus:
            self.event_bus.publish(EVENT_TTS_REQUEST, {"text": text})

    def _query_status(self):
        cs = self._control_state
        parts = []
        if cs["light_mode"] == "auto":
            parts.append("灯光自动模式")
        else:
            parts.append("灯光亮度百分之%d" % cs["light_brightness"])
        parts.append("音量%d" % cs["volume"])
        mode_map = {"active": "正常模式", "suspended": "省电模式",
                    "emergency": "超级省电", "custom": "自定义模式"}
        parts.append(mode_map.get(cs["power_mode"], cs["power_mode"]))
        self._tts("，".join(parts))

    def _query_speed(self):
        speed = self._sensor_cache.get("speed_kmh")
        if speed is not None:
            self._tts("当前时速%d公里" % int(speed))
        else:
            self._tts("速度信息暂不可用")

    def _query_temp(self):
        temp = self._sensor_cache.get("temperature")
        if temp is not None:
            self._tts("当前温度%d度" % int(temp))
        else:
            self._tts("温度信息暂不可用")

    def _query_humid(self):
        humid = self._sensor_cache.get("humidity")
        if humid is not None:
            self._tts("当前湿度百分之%d" % int(humid))
        else:
            self._tts("湿度信息暂不可用")

    def _query_location(self):
        lat = self._sensor_cache.get("latitude")
        lon = self._sensor_cache.get("longitude")
        if lat is not None and lon is not None:
            self._tts("当前位置北纬%.4f东经%.4f" % (lat, lon))
        else:
            self._tts("位置信息暂不可用")

    def _push_state(self):
        if self.event_bus:
            self.event_bus.publish(EVENT_CONTROL_STATE_CHANGED,
                                   dict(self._control_state))

    def get_data(self):
        return {
            "last_cmd": self._data["last_cmd"],
            "last_cmd_source": self._data["last_cmd_source"],
            "control_state": dict(self._control_state),
            "timestamp": _ticks_ms(),
        }

    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "err_count": self.ctx["err_count"],
            "control_state": dict(self._control_state),
        }
