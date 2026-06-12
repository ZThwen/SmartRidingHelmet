import time
import ujson
import _thread
from core.Base_Module import BaseModule
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_IMU_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED, EVENT_CONFIG_UPDATE,
    EVENT_NETWORK_CONNECTED, EVENT_NETWORK_DISCONNECTED,
    EVENT_DATA_UPLOAD_SUCCESS, EVENT_DATA_UPLOAD_FAILED,
    MQTT_TOPIC_DATA, MQTT_TOPIC_CONFIG,
    MQTT_QOS_DATA, MQTT_QOS_CONFIG,
    CLOUD_UPLOAD_INTERVAL_MS,
)
from Drivers.network.Network import NetworkDriver
from Drivers.network.MQTT import MQTTDriver
from Drivers.network.thread_queue import ThreadSafeQueue
class CloudService(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "cloud"
        self.cfg = {
            "upload_interval_ms": CLOUD_UPLOAD_INTERVAL_MS,
            "max_retry": 3,
        }
        self.ctx = {
            "is_init": False,
            "is_network_ready": False,
            "is_mqtt_ready": False,
            "thread_running": False,
            "err_count": 0,
            "last_upload": 0,
            "alarm_active": False,
            "alarm_info": {},
        }
        self._data = {
            "latest_temp": None,
            "latest_humid": None,
            "latest_imu": None,
            "latest_gnss": None,
        }
        self.network = None
        self.mqtt = None
        self.send_queue = None
    def init(self):
        try:
            self.network = NetworkDriver()
            self.mqtt = MQTTDriver()
            self.network.init()
            self.mqtt.init()
            self.mqtt.set_callback(self._on_mqtt_message)
            self.send_queue = ThreadSafeQueue(max_size=100)
            if self.event_bus:
                self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
                self.event_bus.subscribe(EVENT_IMU_READY, self._on_imu)
                self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            if self.network.connect():
                if self.mqtt.connect():
                    self.mqtt.subscribe(MQTT_TOPIC_CONFIG, qos=MQTT_QOS_CONFIG)
                    self.ctx["is_network_ready"] = True
                    self.ctx["is_mqtt_ready"] = True
                    if self.event_bus:
                        self.event_bus.publish(EVENT_NETWORK_CONNECTED, {})
            self.ctx["thread_running"] = True
            old_stack = _thread.stack_size(4096)
            _thread.start_new_thread(self._network_thread, ())
            _thread.stack_size(old_stack)
            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)
        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise
    def tick(self):
        now = time.ticks_ms()
        if not self.ctx["is_mqtt_ready"]:
            if time.ticks_diff(now, self.ctx.get("last_reconnect", 0)) < 10000:
                pass
            else:
                self.ctx["last_reconnect"] = now
                try:
                    if self.network.connect():
                        if self.mqtt.connect():
                            self.mqtt.subscribe(MQTT_TOPIC_CONFIG, qos=MQTT_QOS_CONFIG)
                            self.ctx["is_network_ready"] = True
                            self.ctx["is_mqtt_ready"] = True
                            if self.event_bus:
                                self.event_bus.publish(EVENT_NETWORK_CONNECTED, {})
                except Exception:
                    self.ctx["is_network_ready"] = False
                    self.ctx["is_mqtt_ready"] = False
        if time.ticks_diff(now, self.ctx["last_upload"]) < self.cfg["upload_interval_ms"]:
            return
        self.ctx["last_upload"] = now
        try:
            gnss = self._data["latest_gnss"]
            if self.ctx["alarm_active"]:
                alarm = self.ctx["alarm_info"]
                payload = {
                    "type": "alarm",
                    "alarm_type": alarm.get("alarm_type", "unknown"),
                    "level": alarm.get("level", 1),
                    "latitude": alarm.get("lat"),
                    "longitude": alarm.get("lon"),
                    "altitude": alarm.get("alt"),
                    "timestamp": time.ticks_ms(),
                }
            else:
                payload = {
                    "type": "normal",
                    "temp": self._data["latest_temp"],
                    "humidity": self._data["latest_humid"],
                    "speed_kmh": gnss["speed_kmh"] if gnss else None,
                    "latitude": gnss["lat"] if gnss else None,
                    "longitude": gnss["lon"] if gnss else None,
                    "altitude": gnss["alt"] if gnss else None,
                    "signal_quality": gnss["signal_quality"] if gnss else None,
                    "timestamp": time.ticks_ms(),
                }
            json_str = ujson.dumps(payload)
            self.send_queue.put(json_str)
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] tick 拼装异常 (%s): %s" % (self.name, self.ctx["err_count"], e))
    def _on_temp_humid(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_temp"] = payload["temp"]
        self._data["latest_humid"] = payload["humid"]
    def _on_imu(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_imu"] = {
            "X": payload["acc_x"],
            "Y": payload["acc_y"],
            "Z": payload["acc_z"],
            "total": payload["acc_total"],
        }
    def _on_gnss(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_gnss"] = {
            "lat": payload["latitude"],
            "lon": payload["longitude"],
            "alt": payload["altitude"],
            "speed_kmh": payload["speed_kmh"],
            "signal_quality": payload.get("signal_quality", "none"),
        }
    def _on_alarm(self, payload):
        gnss = self._data["latest_gnss"]
        self.ctx["alarm_active"] = True
        self.ctx["alarm_info"] = {
            "alarm_type": payload.get("alarm_type", "unknown"),
            "level": payload.get("level", 1),
            "lat": gnss["lat"] if gnss else None,
            "lon": gnss["lon"] if gnss else None,
            "alt": gnss["alt"] if gnss else None,
        }
        print("[%s] 报警态激活: %s 等级%s" % (self.name,
              self.ctx["alarm_info"]["alarm_type"],
              self.ctx["alarm_info"]["level"]))
    def _on_alarm_canceled(self, payload):
        self.ctx["alarm_active"] = False
        self.ctx["alarm_info"] = {}
        print("[%s] 报警态解除，恢复数据上传" % self.name)
    def _network_thread(self):
        while self.ctx["thread_running"]:
            data = self.send_queue.get(timeout_ms=1000)
            if data and self.ctx["is_mqtt_ready"]:
                try:
                    self.mqtt.publish(MQTT_TOPIC_DATA, data, qos=MQTT_QOS_DATA)
                    if self.event_bus:
                        self.event_bus.publish(EVENT_DATA_UPLOAD_SUCCESS, {})
                    self.ctx["err_count"] = 0
                except Exception as e:
                    self.ctx["err_count"] += 1
                    self.ctx["is_mqtt_ready"] = False
                    if self.event_bus:
                        self.event_bus.publish(EVENT_DATA_UPLOAD_FAILED, {
                            "error": str(e),
                        })
            if self.ctx["is_mqtt_ready"]:
                try:
                    self.mqtt.check_msg()
                except Exception:
                    self.ctx["is_mqtt_ready"] = False
    def _on_mqtt_message(self, topic, msg):
        try:
            config = ujson.loads(msg)
            if self.event_bus:
                self.event_bus.publish(EVENT_CONFIG_UPDATE, config)
        except Exception as e:
            print("[cloud] MQTT 消息解析失败: %s" % e)
    def get_data(self):
        return {
            "latest_gnss": self._data["latest_gnss"],
            "alarm_active": self.ctx["alarm_active"],
            "queue_size": self.send_queue.size() if self.send_queue else 0,
            "timestamp": time.ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_network_ready": self.ctx["is_network_ready"],
            "is_mqtt_ready": self.ctx["is_mqtt_ready"],
            "thread_running": self.ctx["thread_running"],
            "err_count": self.ctx["err_count"],
        }
    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "upload_interval_ms" in payload:
                self.cfg["upload_interval_ms"] = int(payload["upload_interval_ms"])
                print("[%s] 上传间隔更新为 %sms" % (self.name, self.cfg["upload_interval_ms"]))
