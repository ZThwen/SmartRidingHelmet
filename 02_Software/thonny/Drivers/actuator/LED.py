from machine import Pin, Timer
import time
from core.Base_Module import BaseModule
from core.config import (
    EVENT_LED_ERROR, EVENT_CONFIG_UPDATE,
    LED_PIN_NAME, LED_BLINK_INTERVAL_MS,
    LED_BLINK_MIN_MS, LED_BLINK_MAX_MS,
    TIMER_ID_LED, POWER_STATE_ACTIVE
)
class LEDDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "led"
        self.cfg = {
            "pin_name": LED_PIN_NAME,
            "blink_min_ms": LED_BLINK_MIN_MS,
            "blink_max_ms": LED_BLINK_MAX_MS,
            "blink_interval_ms": LED_BLINK_INTERVAL_MS,
            "timer_id": TIMER_ID_LED,
            "max_retry": 3,
        }
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
            "blink_timer": None,
            "blink_mode": False,
            "blink_remaining_ms": 0,
        }
        self._data = {
            "state": "off",
            "blink_duration": 0,
            "blink_interval": 0,
            "valid": True,
        }
        self.led_pin = None
        self.blink_timer = None
    def init(self):
        try:
            self.led_pin = Pin(
                self.cfg["pin_name"],
                Pin.OUT,
                Pin.PULL_NONE,
                value=0
            )
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[{}] OK init | pin={}".format(self.name, self.cfg["pin_name"]))
        except Exception as e:
            print("[{}] FAIL init: {}".format(self.name, e))
            raise
    def tick(self):
        pass
    def blink(self, duration_ms, interval_ms):
        if not self.ctx["is_init"]:
            return
        if interval_ms < self.cfg["blink_min_ms"]:
            interval_ms = self.cfg["blink_interval_ms"]
        elif interval_ms > self.cfg["blink_max_ms"]:
            interval_ms = self.cfg["blink_interval_ms"]
        try:
            self._stop_blink()
            self.led_pin.value(1)
            self.blink_timer = Timer(-1)
            self._data["state"] = "on"
            self._data["blink_duration"] = duration_ms
            self._data["blink_interval"] = interval_ms
            self.ctx["blink_mode"] = True
            self.ctx["blink_remaining_ms"] = duration_ms
            self.ctx["blink_timer"] = self.blink_timer
            self._data["valid"] = True
            self.ctx["err_count"] = 0
            self.blink_timer.init(
                period=interval_ms,
                mode=Timer.PERIODIC,
                callback=self._blink_callback
            )
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] blink start err ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LED_ERROR, self.get_error_data(e))
    def _blink_callback(self, arg):
        try:
            self.ctx["blink_remaining_ms"] -= self._data["blink_interval"]
            if self.ctx["blink_remaining_ms"] <= 0:
                self.led_pin.value(0)
                self._data["state"] = "off"
                self._stop_blink()
                return
            if self._data["state"] == "on":
                self.led_pin.value(0)
                self._data["state"] = "off"
            else:
                self.led_pin.value(1)
                self._data["state"] = "on"
        except Exception as e:
            print("[{}] blink callback err: {}".format(self.name, e))
            self._stop_blink()
    def on(self):
        if not self.ctx["is_init"]:
            return
        try:
            self._stop_blink()
            self.led_pin.value(1)
            self._data["state"] = "on"
            self._data["blink_duration"] = 0
            self._data["blink_interval"] = 0
            self._data["valid"] = True
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] on err ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LED_ERROR, self.get_error_data(e))
    def off(self):
        if not self.ctx["is_init"]:
            return
        try:
            self._stop_blink()
            self.led_pin.value(0)
            self._data["state"] = "off"
            self._data["blink_duration"] = 0
            self._data["blink_interval"] = 0
            self._data["valid"] = True
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] off err ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LED_ERROR, self.get_error_data(e))
    def _stop_blink(self):
        if self.ctx["blink_timer"]:
            try:
                self.ctx["blink_timer"].deinit()
            except Exception:
                pass
        self.blink_timer = None
        self.ctx["blink_timer"] = None
        self.ctx["blink_mode"] = False
        self.ctx["blink_remaining_ms"] = 0
    def _on_config_update(self, payload):
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[{}] power: {} -> {}".format(self.name, old_state, payload["power_state"]))
            if payload["power_state"] != POWER_STATE_ACTIVE:
                self._stop_blink()
                self.led_pin.value(0)
                self._data["state"] = "off"
            elif old_state != POWER_STATE_ACTIVE:
                self.led_pin.value(1)
                self._data["state"] = "on"
    def get_data(self):
        return {
            "state": self._data["state"],
            "blink_duration": self._data["blink_duration"],
            "blink_interval": self._data["blink_interval"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "blink_mode": self.ctx["blink_mode"]
        }