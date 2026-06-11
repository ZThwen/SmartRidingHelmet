import time
import json

from core.Base_Module import BaseModule
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_LIGHT_CONTROL,
    EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
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
        }

    def init(self):
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_RIDE_CONTROL, self._on_ride_control)
                self.event_bus.subscribe(EVENT_LIGHT_CONTROL, self._on_light_event)
                self.event_bus.subscribe(EVENT_VOLUME_CONTROL, self._on_volume_event)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_power_event)

            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)
        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        pass

    def _on_ride_control(self, payload):
        raw = payload.get("raw", "")
        try:
            cmd_obj = json.loads(raw)
        except Exception as e:
            print("[%s] JSON解析失败: %s" % (self.name, e))
            self.ctx["err_count"] += 1
            return

        if cmd_obj.get("a") != "ctrl":
            return

        cmd = cmd_obj.get("d", {}).get("cmd", "")
        self._execute_cmd(cmd, source="ble")

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
                self._push_state()
                print("[%s] cmd=%s src=%s" % (self.name, cmd, source))
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[%s] cmd执行异常: %s cmd=%s" % (self.name, e, cmd))
        else:
            print("[%s] unknown cmd: %s" % (self.name, cmd))

    def _on_light_event(self, payload):
        cmd = payload.get("cmd", "")
        if cmd == "on":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = 50
        elif cmd == "off":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = 0
        elif cmd == "auto":
            self._control_state["light_mode"] = "auto"
        elif cmd == "brightness_up":
            cur = self._control_state["light_brightness"]
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = min(cur + 10, 100)
        elif cmd == "brightness_down":
            cur = self._control_state["light_brightness"]
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = max(cur - 10, 0)

    def _on_volume_event(self, payload):
        cmd = payload.get("cmd", "")
        cur = self._control_state["volume"]
        if cmd == "up":
            self._control_state["volume"] = min(cur + 1, 5)
        elif cmd == "down":
            self._control_state["volume"] = max(cur - 1, 0)

    def _on_power_event(self, payload):
        state = payload.get("power_state", POWER_STATE_ACTIVE)
        if state == POWER_STATE_SUSPENDED:
            self._control_state["power_mode"] = "suspended"
        elif state == POWER_STATE_EMERGENCY:
            self._control_state["power_mode"] = "emergency"
        else:
            self._control_state["power_mode"] = "active"

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
