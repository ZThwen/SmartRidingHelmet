"""
brief SMS 短信发送驱动（封装 quectel.SMS）
"""
import time
from core.Base_Module import BaseModule
from quectel import SMS


class SMSDriver(BaseModule):

    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "SMS"
        self.sms = None

        self.cfg = {}
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "err_count": 0,
        }
        self._data = {
            "last_send_success": False,
            "last_send_time": 0,
        }

    def init(self):
        try:
            self.sms = SMS()
            self.ctx["is_init"] = True
            print("[%s] init OK" % self.name)
        except Exception as e:
            print("[%s] init FAIL: %s" % (self.name, e))
            raise

    def send_sms(self, phone, message):
        """
        brief 发送 SMS
        note 阻塞 3-5 秒，必须在后台线程调用
        """
        if not self.sms or not self.ctx["is_init"]:
            return False
        try:
            self.ctx["is_busy"] = True
            self.sms.send(phone, message)
            self._data["last_send_success"] = True
            self._data["last_send_time"] = time.ticks_ms()
            print("[SMS] 发送成功: %s" % phone)
            return True
        except Exception as e:
            self._data["last_send_success"] = False
            print("[SMS] 发送失败: %s" % e)
            return False
        finally:
            self.ctx["is_busy"] = False

    def deinit(self):
        if self.sms:
            self.sms.deinit()
            self.sms = None
        self.ctx["is_init"] = False

    def tick(self):
        pass

    def get_data(self):
        return {
            "last_send_success": self._data["last_send_success"],
            "last_send_time": self._data["last_send_time"],
        }
