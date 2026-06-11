from machine import Pin
import time
from core.Base_Module import BaseModule
from core.config import EVENT_BUTTON_PRESSED, EVENT_BUTTON_ERROR, POWER_STATE_ACTIVE, BUTTON_DEBOUNCE_MS
class Button(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "button"
        self.cfg = {
            "id": 'SW',
            "mode": Pin.IN,
            "pull": Pin.PULL_DOWN,
            "debounce_ms": BUTTON_DEBOUNCE_MS,
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
            "valid": False,
        }
        self.button = None
    def init(self):
        try:
            self.button = Pin(self.cfg["id"], self.cfg["mode"], self.cfg["pull"])
            self.button.irq(trigger=Pin.IRQ_RISING, handler=self.button_handler)
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成")
        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise
    def tick(self):
        pass
    def button_handler(self, pin):
        now = time.ticks_ms()
        if self.cfg["debounce_ms"] > time.ticks_diff(now, self.ctx["last_tick"]):
            return
        self.ctx["last_tick"] = now
        if pin.value() == 1:
            self.event_bus.publish(EVENT_BUTTON_PRESSED)
    def get_data(self):
        pass
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }