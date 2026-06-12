import time
from machine import UART
from core.Base_Module import BaseModule
from core.config import EVENT_VOICE_CMD, VOICE_CMD_MAP

class VoiceDriver(BaseModule):

    def __init__(self, event_bus=None, uart_id=2, baudrate=9600):
        super().__init__()
        self.event_bus = event_bus
        self.name = "voice"
        self.cfg = {
            "uart_id": uart_id,
            "baudrate": baudrate,
            "cmd_map": VOICE_CMD_MAP,
        }
        self.ctx = {
            "is_init": False,
            "err_count": 0,
        }
        self._data = {
            "last_cmd": "",
            "last_hex": 0,
        }
        self.uart = None

    def init(self):
        try:
            self.uart = UART(self.cfg["uart_id"], self.cfg["baudrate"])
            self.ctx["is_init"] = True
            print("[%s] OK init | uart=%d baud=%d" % (
                self.name, self.cfg["uart_id"], self.cfg["baudrate"]))
        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        if not self.uart:
            return
        try:
            if self.uart.any():
                data = self.uart.read(1)
                if data and len(data) > 0:
                    hex_val = data[0]
                    self._handle_hex(hex_val)
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] read err: %s" % (self.name, e))

    def _handle_hex(self, hex_val):
        cmd = self.cfg["cmd_map"].get(hex_val)
        if cmd:
            self._data["last_cmd"] = cmd
            self._data["last_hex"] = hex_val
            if self.event_bus:
                self.event_bus.publish(EVENT_VOICE_CMD, {"cmd": cmd})
            print("[%s] 0x%02X -> %s" % (self.name, hex_val, cmd))
        else:
            print("[%s] unknown: 0x%02X" % (self.name, hex_val))

    def get_data(self):
        return {
            "last_cmd": self._data["last_cmd"],
            "last_hex": self._data["last_hex"],
            "timestamp": time.ticks_ms(),
        }

    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "err_count": self.ctx["err_count"],
        }
