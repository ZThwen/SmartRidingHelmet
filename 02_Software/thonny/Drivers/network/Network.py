import time
from quectel import Network
from core.Base_Module import BaseModule
from core.config import (EVENT_CONFIG_UPDATE, POWER_STATE_ACTIVE,
                    NETWORK_CONNECT_TIMEOUT_MS)
NET_STATE_DISCONNECTED  = "disconnected"
NET_STATE_CONNECTING    = "connecting"
NET_STATE_CONNECTED     = "connected"
NET_STATE_ERROR         = "error"
class NetworkDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "network"
        self.cfg = {
            "connect_timeout_ms": NETWORK_CONNECT_TIMEOUT_MS,
            "max_retry": 3,
        }
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
            "net_state": NET_STATE_DISCONNECTED,
        }
        self._data = {
            "ip": "",
            "sim_present": False,
            "valid": False,
        }
        self.net = None
    def init(self):
        try:
            self.net = Network()
            if not self.net.init():
                raise RuntimeError("Network.init() 返回 False")
            sim_ok = self.net.query_usim()
            self._data["sim_present"] = sim_ok
            if not sim_ok:
                print("[network] WARNING 未检测到 SIM 卡")
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[%s] ✓ 初始化完成 | SIM: %s" % (self.name, 'present' if sim_ok else 'missing'))
        except Exception as e:
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise
    def tick(self):
        pass
    def connect(self, timeout_ms=None):
        if not self.ctx["is_init"]:
            return False
        if timeout_ms is None:
            timeout_ms = self.cfg["connect_timeout_ms"]
        self.ctx["net_state"] = NET_STATE_CONNECTING
        self.ctx["is_busy"] = True
        try:
            self.net.attach()
            deadline = time.ticks_ms() + timeout_ms
            while time.ticks_diff(deadline, time.ticks_ms()) > 0:
                if self.net.is_connected():
                    self._data["valid"] = True
                    self.ctx["net_state"] = NET_STATE_CONNECTED
                    self.ctx["err_count"] = 0
                    print("[%s] ✓ 4G已连接" % self.name)
                    return True
                time.sleep_ms(500)
            self.ctx["net_state"] = NET_STATE_ERROR
            print("[%s] ✗ 连接超时" % self.name)
            return False
        except OSError as e:
            self.ctx["err_count"] += 1
            self.ctx["net_state"] = NET_STATE_ERROR
            print("[%s] ✗ attach失败: %s" % (self.name, e))
            return False
        except Exception as e:
            self.ctx["err_count"] += 1
            self.ctx["net_state"] = NET_STATE_ERROR
            print("[%s] ✗ 连接异常 (%s): %s" % (self.name, self.ctx['err_count'], e))
            return False
        finally:
            self.ctx["is_busy"] = False
    def disconnect(self):
        try:
            self.net.deinit()
            self.ctx["net_state"] = NET_STATE_DISCONNECTED
            self._data["valid"] = False
            print("[%s] ✓ 已断开" % self.name)
            return True
        except Exception as e:
            print("[%s] ✗ 断开失败: %s" % (self.name, e))
            return False
    def is_connected(self):
        try:
            return self.net.is_connected()
        except Exception:
            return False
    def set_apn(self, apn, username="", password=""):
        try:
            self.net.set_apn(apn, username, password)
            return True
        except Exception as e:
            print("[%s] ✗ APN设置失败: %s" % (self.name, e))
            return False
    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "connect_timeout_ms" in payload:
                self.cfg["connect_timeout_ms"] = int(payload["connect_timeout_ms"])
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[%s] 功耗状态: %s -> %s" % (self.name, old_state, payload['power_state']))
    def get_data(self):
        return {
            "ip": self._data["ip"],
            "sim_present": self._data["sim_present"],
            "valid": self._data["valid"],
            "net_state": self.ctx["net_state"],
            "timestamp": time.ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "net_state": self.ctx["net_state"],
        }
