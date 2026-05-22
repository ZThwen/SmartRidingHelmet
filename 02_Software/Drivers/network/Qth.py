"""
brief QthDriver — 移远云 Qth SDK 驱动封装
note 封装 Qth SDK 的 init/start/sendTsl/state 接口
     不管理线程、不管理队列、不做重连——Qth SDK 内置自动重连
     初始化失败时静默降级，不影响其他模块

     导入路径: from Drivers.network.Qth import QthDriver
"""
from core.Base_Module import BaseModule
from core.config import (
    QTH_PRODUCT_ID, QTH_PRODUCT_KEY,
    QTH_DEVICE_KEY, QTH_SERVER, QTH_APP_VERSION,
)


class QthDriver(BaseModule):
    """移远云 Qth SDK 驱动封装"""

    def __init__(self):
        super().__init__()
        self.name = "qth"

        # ===================== cfg =====================
        self.cfg = {}

        # ===================== ctx =====================
        self.ctx = {
            "is_init": False,     # 初始化成功
            "err_count": 0,       # 连续错误计数
        }

        # ===================== _data =====================
        self._data = {}

        # ===================== 内部 =====================
        self._qth = None          # Qth 模块引用

    def init(self):
        """
        brief 初始化 Qth SDK 并连接移远云
        note 异常时静默降级，不 raise
        """
        try:
            import Qth

            Qth.init()
            Qth.setProductInfo(QTH_PRODUCT_ID, QTH_PRODUCT_KEY)
            Qth.setDK(QTH_DEVICE_KEY)
            Qth.setServer(QTH_SERVER)
            Qth.setVer(QTH_APP_VERSION)
            Qth.start()

            self._qth = Qth
            self.ctx["is_init"] = True
            print("[qth] ✓ Qth SDK 初始化成功")

        except ImportError:
            print("[qth] - Qth 库不可用，已跳过")

        except Exception as e:
            print("[qth] ✗ 初始化失败: %s" % e)
            self.ctx["err_count"] += 1

    def send_tsl(self, tsl_dict):
        """
        brief 上传物模型数据到移远云
        param tsl_dict: {功能ID: 值}，如 {1: 28.5, 2: 65.2}
        return True 发送成功，False 发送失败
        note 可能阻塞（网络 I/O），调用方需确保不在主线程
             Qth SDK 的 sendTsl 返回值不一定准确——实测返回 False 时数据仍可能到达平台
             测试应以平台侧是否收到数据为准
        """
        if not self.ctx["is_init"]:
            return False

        try:
            ret = self._qth.sendTsl(1, tsl_dict)
            if ret:
                self.ctx["err_count"] = 0
                return True
            else:
                self.ctx["err_count"] += 1
                return False

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[qth] sendTsl 异常: %s" % e)
            return False

    def is_connected(self):
        """
        brief 检查 Qth SDK 与移远云的连接状态
        return True 已连接，False 未连接
        """
        if not self.ctx["is_init"]:
            return False
        try:
            return self._qth.state()
        except Exception:
            return False

    def tick(self):
        """
        brief Qth SDK 内部管理连接和重连，tick 不做任何操作
        """
        pass

    def get_data(self):
        """返回当前连接状态"""
        return {"connected": self.is_connected()}
