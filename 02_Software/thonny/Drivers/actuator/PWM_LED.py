import time
from machine import Pin, Timer

from core.Base_Module import BaseModule
from core.config import (
    EVENT_CONFIG_UPDATE, EVENT_POWER_STATE_CHANGE,
    POWER_STATE_ACTIVE
)

class PWMLedDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "pwm_led"

        self.cfg = {
            "pin_name": "PE11",
            "timer_id": 1,
            "channel": 2,
            "freq": 1000,
            "max_duty": 100,
            "max_retry": 3,
        }

        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
        }

        self._data = {
            "duty_cycle": 0,
            "valid": False,
        }

        self.pwm_channel = None

    def init(self):
        try:
            pin = Pin(self.cfg["pin_name"], Pin.OUT, Pin.PULL_NONE)

            timer = Timer(self.cfg["timer_id"])
            self.pwm_channel = timer.channel(
                self.cfg["channel"],
                Timer.PWM,
                pin=pin,
                freq=self.cfg["freq"],
                duty_cycle=0
            )

            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_power_state)

            self.ctx["is_init"] = True
            print(f"[{self.name}] OK init | pin={self.cfg['pin_name']} "
                  f"TIM{self.cfg['timer_id']}_CH{self.cfg['channel']}")

        except Exception as e:
            print(f"[{self.name}] FAIL init: {e}")
            raise

    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        pass

    def set_brightness(self, duty_cycle):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return False

        duty_cycle = max(0, min(100, int(duty_cycle)))
        try:
            self.pwm_channel.duty_cycle(duty_cycle)
            self._data["duty_cycle"] = duty_cycle
            self._data["valid"] = True
            self.ctx["err_count"] = 0
            return True
        except Exception as e:
            self.ctx["err_count"] += 1
            print(f"[{self.name}] set_brightness err ({self.ctx['err_count']}): {e}")
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    from core.config import EVENT_LED_ERROR
                    self.event_bus.publish(EVENT_LED_ERROR, self.get_error_data(e))
            return False

    def off(self):
        return self.set_brightness(0)

    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "brightness" in payload:
                self.set_brightness(int(payload["brightness"]))

        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print(f"[{self.name}] power: {old_state} -> {payload['power_state']}")

    def _on_power_state(self, payload):
        new_state = payload.get("power_state", POWER_STATE_ACTIVE)
        self.ctx["power_state"] = new_state
        if new_state != POWER_STATE_ACTIVE:
            try:
                self.pwm_channel.duty_cycle(0)
                self._data["duty_cycle"] = 0
            except Exception:
                pass

    def get_data(self):
        return {
            "duty_cycle": self._data["duty_cycle"],
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
