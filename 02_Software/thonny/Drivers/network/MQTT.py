import time
from umqtt.robust import MQTTClient
from core.Base_Module import BaseModule
from core.config import (EVENT_CONFIG_UPDATE, POWER_STATE_ACTIVE,
                    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
                    MQTT_CLIENT_ID, MQTT_KEEPALIVE, MQTT_MAX_RETRY,
                    MQTT_WILL_TOPIC, MQTT_WILL_MESSAGE, MQTT_WILL_QOS,
                    MQTT_WILL_RETAIN)
MQTT_STATE_DISCONNECTED  = "disconnected"
MQTT_STATE_CONNECTING    = "connecting"
MQTT_STATE_CONNECTED     = "connected"
MQTT_STATE_ERROR         = "error"
class MQTTDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "mqtt"
        self.cfg = {
            "broker": MQTT_BROKER,
            "port": MQTT_PORT,
            "client_id": MQTT_CLIENT_ID,
            "user": MQTT_USERNAME,
            "password": MQTT_PASSWORD,
            "keepalive": MQTT_KEEPALIVE,
            "max_retry": MQTT_MAX_RETRY,
            "will_topic": MQTT_WILL_TOPIC,
            "will_message": MQTT_WILL_MESSAGE,
            "will_qos": MQTT_WILL_QOS,
            "will_retain": MQTT_WILL_RETAIN,
        }
        self.ctx = {
            "is_init": False,
            "is_connected": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
            "mqtt_state": MQTT_STATE_DISCONNECTED,
        }
        self._data = {
            "connected": False,
            "valid": False,
        }
        self.client = None
        self._callback = None
    def init(self, broker=None, port=None, client_id=None,
             user=None, password=None, keepalive=None):
        try:
            b = broker if broker is not None else self.cfg["broker"]
            p = port if port is not None else self.cfg["port"]
            cid = client_id if client_id is not None else self.cfg["client_id"]
            u = user if user is not None else self.cfg["user"]
            pw = password if password is not None else self.cfg["password"]
            ka = keepalive if keepalive is not None else self.cfg["keepalive"]
            self.client = MQTTClient(
                client_id=cid,
                server=b,
                port=p,
                user=u,
                password=pw,
                keepalive=ka,
                ssl=None
            )
            try:
                self.client.set_last_will(
                    self.cfg["will_topic"],
                    self.cfg["will_message"],
                    self.cfg["will_retain"],
                    self.cfg["will_qos"],
                )
            except AttributeError:
                print("[%s] WARNING set_last_will 不可用，跳过遗嘱消息" % self.name)
            if self.client is None:
                raise RuntimeError("MQTT 客户端创建失败")
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[%s] ✓ 初始化完成 | broker:%s:%s client_id:%s" % (self.name, b, p, cid))
        except Exception as e:
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise
    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        pass
    def connect(self, timeout_ms=None):
        if not self.ctx["is_init"]:
            return False
        if self.ctx["is_connected"]:
            return True
        self.ctx["mqtt_state"] = MQTT_STATE_CONNECTING
        self.ctx["is_busy"] = True
        if timeout_ms is None:
            timeout_ms = 10000
        try:
            if self._callback:
                self.client.set_callback(self._callback)
            self.client.connect()
            self.ctx["is_connected"] = True
            self._data["connected"] = True
            self._data["valid"] = True
            self.ctx["mqtt_state"] = MQTT_STATE_CONNECTED
            self.ctx["err_count"] = 0
            print("[%s] ✓ MQTT 已连接" % self.name)
            return True
        except Exception as e:
            self.ctx["err_count"] += 1
            self.ctx["mqtt_state"] = MQTT_STATE_ERROR
            self._data["connected"] = False
            self._data["valid"] = False
            self.ctx["is_connected"] = False
            print("[%s] ✗ 连接失败: %s" % (self.name, e))
            return False
        finally:
            self.ctx["is_busy"] = False
    def publish(self, topic, payload, qos=0):
        if not self.ctx["is_init"] or not self.ctx["is_connected"]:
            return False
        try:
            self.client.publish(topic, payload, qos=qos)
            self.ctx["err_count"] = 0
            return True
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] publish 失败 (%s): %s" % (self.name, self.ctx['err_count'], e))
            if self.ctx["err_count"] >= self.cfg["max_retry"]:
                self.ctx["is_connected"] = False
                self._data["connected"] = False
            return False
    def subscribe(self, topic, qos=0):
        if not self.ctx["is_init"] or not self.ctx["is_connected"]:
            return False
        try:
            self.client.subscribe(topic, qos=qos)
            print("[%s] ✓ 已订阅: %s" % (self.name, topic))
            return True
        except Exception as e:
            print("[%s] subscribe 失败: %s" % (self.name, e))
            return False
    def set_callback(self, fn):
        self._callback = fn
        if self.client and self.ctx["is_connected"]:
            try:
                self.client.set_callback(fn)
            except Exception as e:
                print("[%s] set_callback 失败: %s" % (self.name, e))
    def check_msg(self):
        if not self.ctx["is_init"] or not self.ctx["is_connected"]:
            return
        try:
            self.client.check_msg()
        except Exception as e:
            print("[%s] check_msg 异常: %s" % (self.name, e))
    def disconnect(self):
        try:
            self.publish(self.cfg["will_topic"],
                        '{"status":"offline","reason":"normal"}',
                        qos=1)
            self.client.disconnect()
            self.ctx["is_connected"] = False
            self.ctx["mqtt_state"] = MQTT_STATE_DISCONNECTED
            self._data["connected"] = False
            self._data["valid"] = False
            print("[%s] ✓ 已断开" % self.name)
            return True
        except Exception as e:
            print("[%s] ✗ 断开失败: %s" % (self.name, e))
            return False
    def is_connected(self):
        return self.ctx["is_connected"]
    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "broker" in payload:
                self.cfg["broker"] = payload["broker"]
            if "port" in payload:
                self.cfg["port"] = int(payload["port"])
            if "client_id" in payload:
                self.cfg["client_id"] = payload["client_id"]
            if "keepalive" in payload:
                self.cfg["keepalive"] = int(payload["keepalive"])
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[%s] 功耗状态: %s -> %s" % (self.name, old_state, payload['power_state']))
    def get_data(self):
        return {
            "connected": self._data["connected"],
            "valid": self._data["valid"],
            "mqtt_state": self.ctx["mqtt_state"],
            "timestamp": time.ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_connected": self.ctx["is_connected"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "mqtt_state": self.ctx["mqtt_state"],
        }
