from core.Base_Module import BaseModule
from core.config import (
    QTH_PRODUCT_ID, QTH_PRODUCT_KEY,
    QTH_DEVICE_KEY, QTH_SERVER, QTH_APP_VERSION,
)
class QthDriver(BaseModule):
    def __init__(self):
        super().__init__()
        self.name = "qth"
        self.cfg = {}
        self.ctx = {
            "is_init": False,
            "err_count": 0,
        }
        self._data = {}
        self._qth = None
    def init(self):
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
        if not self.ctx["is_init"]:
            return False
        try:
            return self._qth.state()
        except Exception:
            return False
    def tick(self):
        pass
    def get_data(self):
        return {"connected": self.is_connected()}