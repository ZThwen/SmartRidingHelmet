"""
brief 语音指令驱动模块
note 监听 ASRPRO 语音模块的 UART 串口，将 hex 字节映射为指令字符串
     通过 EVENT_VOICE_CMD 发送给 ControlService
     手动操作永远优先 — 任何电源模式下都读取语音指令
"""
import time
from machine import UART

from core.Base_Module import BaseModule
from core.config import EVENT_VOICE_CMD, VOICE_CMD_MAP


class VoiceDriver(BaseModule):

    def __init__(self, event_bus=None, uart_id=2, baudrate=115200):
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
        # ====== 1. 心跳更新（必须在所有状态守卫之前）======
        self.ctx["last_hb"] = time.ticks_ms()

        if not self.uart:
            return
        # 手动操作永远优先 — 任何电源模式下都读取语音指令
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

    def deinit(self):
        """释放 UART 资源"""
        try:
            if self.uart:
                self.uart.deinit()
                self.uart = None
            self.ctx["is_init"] = False
            print("[%s] deinit OK" % self.name)
        except Exception as e:
            print("[%s] deinit err: %s" % (self.name, e))

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
