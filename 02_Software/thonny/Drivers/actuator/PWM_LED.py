from pyb import Pin, Timer
import time
from core.Base_Module import BaseModule
from core.config import (
    EVENT_PWM_LED_ERROR, EVENT_CONFIG_UPDATE,
    PWM_LED_PIN, PWM_LED_TIMER_ID, PWM_LED_TIMER_CHANNEL,
    PWM_LED_FREQ, POWER_STATE_ACTIVE
)
class PWMLEDDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "pwm_led"
        self.cfg = {
            "pin_name": PWM_LED_PIN,
            "timer_id": PWM_LED_TIMER_ID,
            "timer_channel": PWM_LED_TIMER_CHANNEL,
            "pwm_freq": PWM_LED_FREQ,
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
            "valid": True,
        }
        self.led_pin = None
        self.pwm_timer = None
        self.pwm_channel = None
    def init(self):
        try:
            self.led_pin = Pin(
                self.cfg["pin_name"],
                Pin.OUT,
                Pin.PULL_NONE
            )
            self.pwm_timer = Timer(self.cfg["timer_id"], freq=self.cfg["pwm_freq"])
            self.pwm_channel = self.pwm_timer.channel(
                self.cfg["timer_channel"],
                Timer.PWM,
                pin=self.led_pin
            )
            self.pwm_channel.pulse_width_percent(0)
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[{}] OK init | pin={}, timer={}, channel={}, freq={}Hz".format(
                self.name, self.cfg["pin_name"], self.cfg["timer_id"],
                self.cfg["timer_channel"], self.cfg["pwm_freq"]
            ))
        except Exception as e:
            print("[{}] FAIL init: {}".format(self.name, e))
            raise
    def tick(self):
        pass
    def set_brightness(self, duty_cycle):
        if not self.ctx["is_init"]:
            return
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        if duty_cycle < 0:
            duty_cycle = 0
        elif duty_cycle > 100:
            duty_cycle = 100
        try:
            self.ctx["is_busy"] = True
            self.pwm_channel.pulse_width_percent(duty_cycle)
            self._data["duty_cycle"] = duty_cycle
            self._data["valid"] = True
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] set_brightness err ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_PWM_LED_ERROR, {
                        "module": self.name,
                        "error": str(e),
                        "timestamp": time.ticks_ms()
                    })
        finally:
            self.ctx["is_busy"] = False
    def _on_config_update(self, payload):
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[{}] power: {} -> {}".format(self.name, old_state, payload["power_state"]))
            if payload["power_state"] != POWER_STATE_ACTIVE:
                self.set_brightness(0)
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
    def deinit(self):
        try:
            if self.pwm_channel:
                self.pwm_channel.pulse_width_percent(0)
            if self.pwm_timer:
                self.pwm_timer.deinit()
            self.pwm_timer = None
            self.pwm_channel = None
            self.ctx["is_init"] = False
            print("[{}] OK deinit".format(self.name))
        except Exception as e:
            print("[{}] deinit err: {}".format(self.name, e))
