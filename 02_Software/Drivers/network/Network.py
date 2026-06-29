"""
brief 4G网络驱动 (EC200U)
note 纯硬件封装层，调用 quectel.Network 原生 API
     不做事件发布，状态由 CloudService 轮询
"""
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
        """
        brief 初始化模块：创建实例 + 检测 SIM + 订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        """
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
            print(f"[{self.name}] ✓ 初始化完成 | SIM: {'present' if sim_ok else 'missing'}")

        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """
        brief 周期调度
        note Network 为被动控制型设备，无主动采样需求，tick 保持空实现
              心跳更新确保 SystemMonitor 不误判离线
        """
        self.ctx["last_hb"] = time.ticks_ms()

    def connect(self, timeout_ms=None):
        """
        brief 连接4G网络:attach + 轮询注册状态
        param timeout_ms: 连接超时时间(ms)，默认 cfg.connect_timeout_ms
        return bool 是否连接成功
        """
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
                    print(f"[{self.name}] ✓ 4G已连接")
                    return True
                time.sleep_ms(500)

            self.ctx["net_state"] = NET_STATE_ERROR
            print(f"[{self.name}] ✗ 连接超时")
            return False

        except OSError as e:
            self.ctx["err_count"] += 1
            self.ctx["net_state"] = NET_STATE_ERROR
            print(f"[{self.name}] ✗ attach失败: {e}")
            return False

        except Exception as e:
            self.ctx["err_count"] += 1
            self.ctx["net_state"] = NET_STATE_ERROR
            print(f"[{self.name}] ✗ 连接异常 ({self.ctx['err_count']}): {e}")
            return False

        finally:
            self.ctx["is_busy"] = False

    def disconnect(self):
        """
        brief 断开4G网络连接
        return bool 是否成功断开
        """
        try:
            self.net.deinit()
            self.ctx["net_state"] = NET_STATE_DISCONNECTED
            self._data["valid"] = False
            print(f"[{self.name}] ✓ 已断开")
            return True
        except Exception as e:
            print(f"[{self.name}] ✗ 断开失败: {e}")
            return False

    def is_connected(self):
        """
        brief 查询网络连接状态
        return bool True=已连接，False=未连接
        """
        try:
            return self.net.is_connected()
        except Exception:
            return False

    def set_apn(self, apn, username="", password=""):
        """
        brief 设置APN接入点
        param apn: APN名称
        param username: 用户名（可选）
        param password: 密码（可选）
        return bool 是否设置成功
        """
        try:
            self.net.set_apn(apn, username, password)
            return True
        except Exception as e:
            print(f"[{self.name}] ✗ APN设置失败: {e}")
            return False

    def _on_config_update(self, payload):
        """
        brief 配置更新回调
        param payload: 配置事件负载
        """
        if payload.get("target") == self.name:
            if "connect_timeout_ms" in payload:
                self.cfg["connect_timeout_ms"] = int(payload["connect_timeout_ms"])

        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print(f"[{self.name}] 功耗状态: {old_state} -> {payload['power_state']}")

    def get_data(self):
        """
        brief 获取网络数据快照
        return dict 数据副本
        """
        return {
            "ip": self._data["ip"],
            "sim_present": self._data["sim_present"],
            "valid": self._data["valid"],
            "net_state": self.ctx["net_state"],
            "timestamp": time.ticks_ms(),
        }

    def get_status(self):
        """
        brief 查询模块运行状态
        return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "net_state": self.ctx["net_state"],
        }
