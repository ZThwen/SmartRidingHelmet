"""
brief SMS 短信发送驱动（封装 quectel.SMS）
"""
import time
from core.Base_Module import BaseModule
from core.config import AT_LOCK
from quectel import SMS


class SMSDriver(BaseModule):

    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "SMS"
        self.sms = None
        self._sms_cooldown_until = 0  # 冷却期结束时间戳

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
        # 冷却期检查：失败后等 60s 再试
        if self._sms_cooldown_until > 0:
            if time.ticks_diff(time.ticks_ms(), self._sms_cooldown_until) < 0:
                return False  # 还在冷却
            # 冷却到期，重新初始化 SMS 模块（SMS() 内部发 AT 命令，需锁保护）
            try:
                AT_LOCK.acquire()
                try:
                    self.sms = SMS()  # 重新创建句柄
                finally:
                    AT_LOCK.release()
                self._sms_cooldown_until = 0
                print("[SMS] 冷却期结束，已重新初始化")
            except Exception as e:
                print("[SMS] 重新初始化失败: %s" % e)
                self._sms_cooldown_until = time.ticks_ms() + 60000  # 再冷却 60s
                return False
        try:
            self.ctx["is_busy"] = True
            AT_LOCK.acquire()  # 阻塞获取（SMS 高优先级，必须发送）
            try:
                result = self.sms.send(phone, message)
                if not result:
                    raise RuntimeError("SMS send returned error")
            finally:
                AT_LOCK.release()
            self._data["last_send_success"] = True
            self._data["last_send_time"] = time.ticks_ms()
            print("[SMS] 发送成功: %s" % phone)
            return True
        except Exception as e:
            # 进入冷却期，deinit 旧句柄
            try:
                self.sms.deinit()
            except:
                pass
            self.sms = None
            self._data["last_send_success"] = False
            self._sms_cooldown_until = time.ticks_ms() + 60000  # 60s 后重试
            print("[SMS] 发送失败，进入冷却期 60s")
            return False
        finally:
            self.ctx["is_busy"] = False

    def deinit(self):
        if self.sms:
            self.sms.deinit()
            self.sms = None
        self.ctx["is_init"] = False

    def tick(self):
        self.ctx["last_hb"] = time.ticks_ms()

    def get_data(self):
        return {
            "last_send_success": self._data["last_send_success"],
            "last_send_time": self._data["last_send_time"],
        }
