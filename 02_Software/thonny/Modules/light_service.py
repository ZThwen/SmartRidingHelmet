import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_LIGHT_READY, EVENT_CONFIG_UPDATE, EVENT_LIGHT_CONTROL,
    POWER_STATE_ACTIVE,
    LIGHT_DAY_ADC_THRESHOLD, LIGHT_NIGHT_ADC_THRESHOLD,
    LIGHT_BRIGHTNESS_MIN, LIGHT_BRIGHTNESS_MAX,
    LIGHT_GAMMA, LIGHT_BRIGHTNESS_THRESHOLD, LIGHT_DEBOUNCE_MS
)

class LightService(BaseModule):

    def __init__(self, event_bus=None, pwm_led=None):
        super().__init__()
        self.event_bus = event_bus
        self.pwm_led = pwm_led
        self.name = "light_service"

        self.cfg = {
            "light_day_threshold": LIGHT_DAY_ADC_THRESHOLD,
            "light_night_threshold": LIGHT_NIGHT_ADC_THRESHOLD,
            "brightness_min": LIGHT_BRIGHTNESS_MIN,
            "brightness_max": LIGHT_BRIGHTNESS_MAX,
            "gamma": LIGHT_GAMMA,
            "brightness_threshold": LIGHT_BRIGHTNESS_THRESHOLD,
            "debounce_ms": LIGHT_DEBOUNCE_MS,
        }

        self.ctx = {
            "is_init": False,
            "power_state": POWER_STATE_ACTIVE,
            "auto_mode": True,
            "manual_brightness": 50,
            "last_brightness": 0,
            "last_update_tick": 0,
            "err_count": 0,
        }

        self._data = {
            "current_brightness": 0,
            "light_intensity": 0,
            "mode": "auto",
            "light_level": "unknown",
        }

    def init(self):
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_LIGHT_READY, self._on_light_ready)
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
                self.event_bus.subscribe(EVENT_LIGHT_CONTROL, self._on_light_control)

            self.ctx["is_init"] = True
            print("[{}] OK init | auto_mode={}".format(self.name, self.ctx["auto_mode"]))

        except Exception as e:
            print("[{}] FAIL init: {}".format(self.name, e))
            raise

    def tick(self):
        pass

    def _on_light_ready(self, payload):
        if not self.ctx["is_init"]:
            return

        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        if not self.ctx["auto_mode"]:
            return

        if not payload.get("valid", False):
            return

        light_intensity = payload.get("light_intensity", 0)
        self._data["light_intensity"] = light_intensity

        target_brightness, light_level = self._calculate_brightness(light_intensity)
        self._data["light_level"] = light_level

        brightness_diff = abs(target_brightness - self.ctx["last_brightness"])
        if brightness_diff < self.cfg["brightness_threshold"]:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_update_tick"]) < self.cfg["debounce_ms"]:
            return

        if self.pwm_led:
            try:
                self.pwm_led.set_brightness(target_brightness)
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[{}] pwm_led error ({}): {}".format(
                    self.name, self.ctx["err_count"], e))
                return

        self.ctx["last_brightness"] = target_brightness
        self.ctx["last_update_tick"] = now
        self._data["current_brightness"] = target_brightness

        print("[{}] light={} ({}), brightness={}%, level={}".format(
            self.name, light_intensity, light_level, target_brightness, light_level))

    def _calculate_brightness(self, light_intensity):
        light_day = self.cfg["light_day_threshold"]
        light_night = self.cfg["light_night_threshold"]
        brightness_min = self.cfg["brightness_min"]
        brightness_max = self.cfg["brightness_max"]
        gamma = self.cfg["gamma"]

        if light_intensity <= light_day:
            return (0, "day")

        if light_intensity >= light_night:
            normalized = 1.0
            brightness = brightness_min + (brightness_max - brightness_min) * pow(normalized, gamma)
            return (int(brightness), "night")

        normalized = (light_intensity - light_day) / (light_night - light_day)
        brightness = brightness_min + (brightness_max - brightness_min) * pow(normalized, gamma)

        if brightness < brightness_min:
            brightness = brightness_min
        elif brightness > brightness_max:
            brightness = brightness_max

        return (int(brightness), "transition")

    def set_manual_brightness(self, duty_cycle):
        if not self.ctx["is_init"]:
            return

        if duty_cycle < 0:
            duty_cycle = 0
        elif duty_cycle > 100:
            duty_cycle = 100

        self.ctx["auto_mode"] = False
        self.ctx["manual_brightness"] = duty_cycle
        self._data["mode"] = "manual"

        if self.pwm_led:
            try:
                self.pwm_led.set_brightness(duty_cycle)
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[{}] manual set error ({}): {}".format(
                    self.name, self.ctx["err_count"], e))
                return

        self._data["current_brightness"] = duty_cycle
        self.ctx["last_brightness"] = duty_cycle

        print("[{}] manual mode, brightness={}".format(self.name, duty_cycle))

    def set_auto_mode(self):
        if not self.ctx["is_init"]:
            return

        self.ctx["auto_mode"] = True
        self._data["mode"] = "auto"

        print("[{}] auto mode enabled".format(self.name))

    def _on_light_control(self, payload):
        cmd = payload.get("cmd", "")
        if cmd == "on":
            self.set_manual_brightness(50)
        elif cmd == "off":
            self.set_manual_brightness(0)
        elif cmd == "auto":
            self.set_auto_mode()
        elif cmd == "brightness_up":
            current = self._data.get("current_brightness", 0)
            self.set_manual_brightness(min(current + 10, 100))
        elif cmd == "brightness_down":
            current = self._data.get("current_brightness", 0)
            self.set_manual_brightness(max(current - 10, 0))

    def get_mode(self):
        return self._data["mode"]

    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "light_day_threshold" in payload:
                self.cfg["light_day_threshold"] = int(payload["light_day_threshold"])
            if "light_night_threshold" in payload:
                self.cfg["light_night_threshold"] = int(payload["light_night_threshold"])
            if "brightness_min" in payload:
                self.cfg["brightness_min"] = int(payload["brightness_min"])
            if "brightness_max" in payload:
                self.cfg["brightness_max"] = int(payload["brightness_max"])
            if "gamma" in payload:
                self.cfg["gamma"] = float(payload["gamma"])
            if "brightness_threshold" in payload:
                self.cfg["brightness_threshold"] = int(payload["brightness_threshold"])
            if "debounce_ms" in payload:
                self.cfg["debounce_ms"] = int(payload["debounce_ms"])

            print("[{}] config updated".format(self.name))

        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[{}] power: {} -> {}".format(self.name, old_state, payload["power_state"]))

    def get_data(self):
        return {
            "current_brightness": self._data["current_brightness"],
            "light_intensity": self._data["light_intensity"],
            "mode": self._data["mode"],
            "light_level": self._data["light_level"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "auto_mode": self.ctx["auto_mode"],
            "power_state": self.ctx["power_state"],
            "err_count": self.ctx["err_count"],
            "last_brightness": self.ctx["last_brightness"]
        }
