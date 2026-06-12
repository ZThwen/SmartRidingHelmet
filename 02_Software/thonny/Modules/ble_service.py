import time
import json
import _thread
from core.Base_Module import BaseModule
from core.config import (
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    EVENT_TEMP_HUMID_READY, EVENT_IMU_READY,
    EVENT_GNSS_READY, EVENT_LIGHT_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_CONTROL_STATE_CHANGED,
    BLE_UPLOAD_INTERVAL_MS, BLE_KEEPALIVE_MS,
)
from Drivers.network.thread_queue import ThreadSafeQueue
class BLEService(BaseModule):
    def __init__(self, event_bus=None, ble_driver=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "ble_service"
        self._ble = ble_driver
        self.cfg = {
            "upload_interval_ms": BLE_UPLOAD_INTERVAL_MS,
            "keepalive_ms": BLE_KEEPALIVE_MS,
            "queue_max_size": 20,
        }
        self.ctx = {
            "is_init": False,
            "thread_running": False,
            "last_upload": 0,
            "last_keepalive": 0,
            "ble_connected": False,
            "err_count": 0,
            "force_push": False,
            "consecutive_errors": 0,
        }
        self._data = {
            "latest_temp": None,
            "latest_humid": None,
            "latest_ax": None,
            "latest_ay": None,
            "latest_az": None,
            "latest_lat": None,
            "latest_lon": None,
            "latest_alt": None,
            "latest_spd": None,
            "latest_cog": None,
            "latest_lux": None,
        }
        self.send_queue = None
    def init(self):
        try:
            self.send_queue = ThreadSafeQueue(max_size=self.cfg["queue_max_size"])
            if self.event_bus:
                self.event_bus.subscribe(EVENT_BLE_CONNECTED, self._on_connected)
                self.event_bus.subscribe(EVENT_BLE_DISCONNECTED, self._on_disconnected)
                self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
                self.event_bus.subscribe(EVENT_IMU_READY, self._on_imu)
                self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
                self.event_bus.subscribe(EVENT_LIGHT_READY, self._on_light)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
                self.event_bus.subscribe(EVENT_CONTROL_STATE_CHANGED, self._on_control_state)
            self.ctx["thread_running"] = True
            _thread.stack_size(4096)
            _thread.start_new_thread(self._notify_thread, ())
            self.ctx["is_init"] = True
            print("[%s] ✓ BLE 推送服务已启动" % self.name)
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise
    def tick(self):
        if not self.ctx["is_init"]:
            return
        now = time.ticks_ms()
        if self.ctx["force_push"]:
            self.ctx["force_push"] = False
            self.ctx["last_upload"] = now
            self._enqueue_merged()
        if time.ticks_diff(now, self.ctx["last_upload"]) < self.cfg["upload_interval_ms"]:
            pass
        else:
            self.ctx["last_upload"] = now
            self._enqueue_merged()
        if time.ticks_diff(now, self.ctx["last_keepalive"]) >= self.cfg["keepalive_ms"]:
            self.ctx["last_keepalive"] = now
            if self.ctx["ble_connected"]:
                self.send_queue.put('{"t":99,"d":{"s":"ok"}}')
    def _enqueue_merged(self):
        if not self.ctx["ble_connected"]:
            return
        if not self._ble or not self._ble.ctx["is_connected"]:
            return
        d = {}
        if self._data["latest_temp"] is not None:
            d["tmp"] = self._data["latest_temp"]
            d["hum"] = self._data["latest_humid"]
        if self._data["latest_lat"] is not None:
            d["lat"] = self._data["latest_lat"]
            d["lon"] = self._data["latest_lon"]
            d["spd"] = self._data["latest_spd"]
            d["alt"] = self._data["latest_alt"]
            if self._data["latest_cog"] is not None:
                d["cog"] = self._data["latest_cog"]
        if self._data["latest_lux"] is not None:
            d["lux"] = self._data["latest_lux"]
        if not d:
            return
        self.send_queue.put(json.dumps({"t": 0, "d": d}))
    def _notify_thread(self):
        CIRCUIT_BREAKER_THRESHOLD = 10
        while self.ctx["thread_running"]:
            try:
                data = self.send_queue.get()
                if data is None:
                    time.sleep_ms(100)
                    continue
                if not self._ble or not self._ble.ctx["is_connected"]:
                    continue
                if self.ctx["consecutive_errors"] >= CIRCUIT_BREAKER_THRESHOLD:
                    time.sleep_ms(500)
                    continue
                self._ble.notify_data(data)
                self.ctx["err_count"] = 0
                self.ctx["consecutive_errors"] = 0
            except Exception as e:
                self.ctx["err_count"] += 1
                self.ctx["consecutive_errors"] += 1
                print("[%s] 后台线程异常: %s" % (self.name, e))
    def _on_connected(self, payload):
        self.ctx["ble_connected"] = True
        self.ctx["consecutive_errors"] = 0
        self.ctx["force_push"] = True
    def _on_disconnected(self, payload):
        self.ctx["ble_connected"] = False
        if self.send_queue:
            self.send_queue.clear()
    def _on_temp_humid(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_temp"] = payload.get("temp")
        self._data["latest_humid"] = payload.get("humid")
    def _on_imu(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_ax"] = payload.get("acc_x")
        self._data["latest_ay"] = payload.get("acc_y")
        self._data["latest_az"] = payload.get("acc_z")
    def _on_gnss(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_lat"] = payload.get("latitude")
        self._data["latest_lon"] = payload.get("longitude")
        self._data["latest_alt"] = payload.get("altitude")
        self._data["latest_spd"] = payload.get("speed_kmh")
        self._data["latest_cog"] = payload.get("cog", 0.0)
    def _on_light(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_lux"] = payload.get("light_intensity")
    def _on_alarm(self, payload):
        alarm_type = payload.get("alarm_type", "collision")
        level = payload.get("level", 1)
        type_code = 1 if alarm_type == "collision" else 2
        msg = json.dumps({"t": 5, "a": type_code, "l": level})
        self.send_queue.put(msg)
        self.ctx["force_push"] = False
    def _on_alarm_canceled(self, payload):
        self.send_queue.put('{"t":6,"d":{}}')
    def _on_control_state(self, payload):
        msg = json.dumps({"t": 7, "d": payload})
        self.send_queue.put(msg)
    def get_data(self):
        return {
            "ble_connected": self.ctx["ble_connected"],
            "queue_size": self.send_queue.size() if self.send_queue else 0,
            "err_count": self.ctx["err_count"],
            "timestamp": time.ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "ble_connected": self.ctx["ble_connected"],
            "thread_running": self.ctx["thread_running"],
            "err_count": self.ctx["err_count"],
            "consecutive_errors": self.ctx["consecutive_errors"],
        }
    def deinit(self):
        self.ctx["thread_running"] = False
        time.sleep_ms(700)
        self.ctx["is_init"] = False
