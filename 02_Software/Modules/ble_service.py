"""
brief BLEService — BLE 推送服务
note 双线程架构：
       主线程：收事件 → 缓存 → tick() 拼装 JSON → send_queue.put()
       后台线程：send_queue.get() → BLEDriver.notify_data()
      绝不阻塞主循环，与 CloudService/LarkCloudService 相同模式
"""
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
    EVENT_NAV_CMD, EVENT_RIDE_CONTROL, EVENT_BLE_ALARM_ACK,
    EVENT_BATTERY_READY, EVENT_HEARTRATE_READY,
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
            "latest_battery": None,
            "latest_heart_rate": None,
            "latest_spo2": None,
        }

        # 控制状态快照（coalescing 缓冲，tick 周期统一推送）
        self._ctrl_snapshot = {
            "m": 0, "b": 0,  # t=7: 灯光
            "v": 5,           # t=8: 音量
            "p": 0,           # t=9: 电源
            "f": 0,           # t=7: 闪烁
            "dirty": False,   # 是否有未推送的控制状态
        }

        # 环形缓冲区（BLE 中断写入，tick 中 drain）
        self.cmd_buffer = ThreadSafeQueue(max_size=16)
        self.cmd_ready = False
        self._notify_tid = None
        self._connected_published = False

        self.send_queue = None

    def init(self):
        try:
            self.send_queue = ThreadSafeQueue(max_size=self.cfg["queue_max_size"])

            # 注册数据处理器（不覆盖 BLE 回调）
            if self._ble:
                self._ble.set_data_handler(self._on_ble_data)

            if self.event_bus:
                self.event_bus.subscribe(EVENT_BLE_CONNECTED, self._on_connected)
                self.event_bus.subscribe(EVENT_BLE_DISCONNECTED, self._on_disconnected)
                self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
                self.event_bus.subscribe(EVENT_IMU_READY, self._on_imu)
                self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
                self.event_bus.subscribe(EVENT_LIGHT_READY, self._on_light)
                self.event_bus.subscribe(EVENT_BATTERY_READY, self._on_battery)
                self.event_bus.subscribe(EVENT_HEARTRATE_READY, self._on_heartrate)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
                self.event_bus.subscribe(EVENT_CONTROL_STATE_CHANGED, self._on_control_state)

            self.ctx["thread_running"] = True
            old_size = _thread.stack_size(4096)
            self._notify_tid = _thread.start_new_thread(self._notify_thread, ())
            _thread.stack_size(old_size)

            self.ctx["is_init"] = True
            print("[%s] ✓ BLE 推送服务已启动" % self.name)

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise

    def tick(self):
        if not self.ctx["is_init"]:
            return

        self.ctx["last_hb"] = time.ticks_ms()
        # drain 环形缓冲区
        if self.cmd_ready:
            self.cmd_ready = False
            while self.cmd_buffer.size() > 0:
                item = self.cmd_buffer.get()
                if item is not None:
                    self._parse_and_route(item)

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

        # 控制状态快照推送（合并多条 EVENT_CONTROL_STATE_CHANGED 为 1 条）
        if self.ctx["ble_connected"] and self._ble:
            snap = self._ctrl_snapshot
            if snap["dirty"]:
                self.send_queue.put(
                    '{"t":7,"m":%d,"b":%d,"v":%d,"p":%d,"f":%d}' % (
                        snap["m"], snap["b"], snap["v"], snap["p"], snap["f"]))
                snap["dirty"] = False

    def _enqueue_merged(self):
        if not self.ctx["ble_connected"]:
            return
        if not self._ble:
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
        if self._data["latest_battery"] is not None:
            d["bat"] = self._data["latest_battery"]
        if self._data["latest_heart_rate"] is not None:
            d["hr"] = self._data["latest_heart_rate"]
            d["spo2"] = self._data["latest_spo2"]

        if not d:
            return
        self.send_queue.put(json.dumps({"t": 0, "d": d}))

    def _notify_thread(self):
        CIRCUIT_BREAKER_THRESHOLD = 10
        MAX_BLE_PAYLOAD = 244  # ATT_MTU(247) - 3(ATT header)
        while self.ctx["thread_running"]:
            try:
                data = None
                data = self.send_queue.get()
                if data is None:
                    time.sleep_ms(100)
                    continue
                if not self._ble:
                    continue
                if not self.ctx["ble_connected"]:
                    # ★ 调试日志：因 BLE 未连接而丢弃消息
                    print("[%s] DROP notify: BLE not connected, msg=%.50s" % (self.name, data))
                    continue
                if len(data) > MAX_BLE_PAYLOAD:
                    print("[%s] payload too large (%d > %d), dropped" % (
                        self.name, len(data), MAX_BLE_PAYLOAD))
                    continue
                if self.ctx["consecutive_errors"] >= CIRCUIT_BREAKER_THRESHOLD:
                    time.sleep_ms(500)
                    continue
                # ★ 调试日志：正在发送
                print("[%s] SEND notify: %s" % (self.name, data))
                self._ble.notify_data(data)
                self.ctx["err_count"] = 0
                self.ctx["consecutive_errors"] = 0
            except Exception as e:
                self.ctx["err_count"] += 1
                self.ctx["consecutive_errors"] += 1
                # ★ 调试日志：更详细的异常信息
                print("[%s] notify err (#%d): %s | msg=%.60s" % (self.name, self.ctx["err_count"], e, data if data is not None else 'N/A'))

    def _on_connected(self, payload):
        self.ctx["ble_connected"] = True
        self.ctx["consecutive_errors"] = 0
        self.ctx["force_push"] = True
        # ★ 调试日志：BLE 连接
        print("[%s] BLE CONNECTED" % self.name)

    def _on_disconnected(self, payload):
        self.ctx["ble_connected"] = False
        # ★ 调试日志：BLE 断开
        print("[%s] BLE DISCONNECTED" % self.name)
        if self.send_queue:
            self.send_queue.clear()
            # ★ 调试日志：队列清空
            print("[%s] BLE DISCONNECTED: queue cleared" % self.name)

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

    def _on_battery(self, payload):
        if not payload.get("valid", False):
            return
        self._data["latest_battery"] = payload.get("level")

    def _on_heartrate(self, payload):
        """brief 缓存心率血氧，由 _enqueue_merged 统一推送"""
        if not payload.get("valid"):
            return
        self._data["latest_heart_rate"] = payload.get("heart_rate")
        self._data["latest_spo2"] = payload.get("spo2")

    def _on_alarm(self, payload):
        alarm_type = payload.get("alarm_type", "collision")
        level = payload.get("level", 1)
        # 压缩载荷：15 字节（原 46 字节），避免超出 ATT_MTU 导致 +CME ERROR: 53
        type_code = 1 if alarm_type == "collision" else 2
        msg = json.dumps({"t": 5, "a": type_code, "l": level})
        # ★ 调试日志：报警事件到达
        print("[%s] ALARM_EVENT type=%s level=%d → queued: %s" % (self.name, alarm_type, level, msg))
        self.send_queue.put(msg)
        # ★ 调试日志：确认入队后的队列大小
        print("[%s] ALARM_EVENT queue_size=%d" % (self.name, self.send_queue.size()))
        self.ctx["force_push"] = False

    def _on_alarm_canceled(self, payload):
        self.send_queue.put('{"t":6,"d":{}}')

    def _on_control_state(self, payload):
        """
        brief 控制状态变更回调 — 快照合并（coalescing）
        note 不直接入队，改为更新快照；tick() 周期统一推送为 1 条消息
        param payload: EventBus 事件（含 source/timestamp 注入字段）
        """
        valid_keys = ("t", "m", "b", "v", "p", "f")
        data = {k: v for k, v in payload.items() if k in valid_keys}
        t = data.get("t")
        snap = self._ctrl_snapshot
        if t == 7:
            snap["m"] = data.get("m", snap["m"])
            snap["b"] = data.get("b", snap["b"])
            snap["v"] = data.get("v", snap["v"])
            snap["p"] = data.get("p", snap["p"])
            snap["f"] = data.get("f", snap["f"])
        snap["dirty"] = True

    # ==================== BLE 数据处理（modem 线程） ====================

    def _on_ble_data(self, evt):
        """
        brief BLE 数据事件处理器（modem 线程上下文）
        param evt: 事件字典（EVT_VAL_DATA）
        note 只处理数据写入，连接/断开/MTU 由 BLEDriver._callback 处理并通过 EventBus 通知
             中断快速返回：只写 buffer + 设 flag，不做 JSON 解析
        """
        try:
            uuid = evt.get("uuid")
            value = evt.get("value", "")
            # hex 解码
            if isinstance(value, str) and len(value) > 2:
                try:
                    clean = value.strip().replace(' ', '').replace('\n', '').replace('\r', '')
                    if len(clean) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in clean):
                        value = bytes.fromhex(clean).decode('utf-8')
                except:
                    pass
            # 写入环形缓冲区，设标志
            self.cmd_buffer.put({"uuid": uuid, "raw": value})
            self.cmd_ready = True

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] _on_ble_data 异常: %s" % (self.name, e))

    def _parse_and_route(self, item):
        """
        brief 解析环形缓冲区中的原始数据并路由到 EventBus
        param item: {"uuid": str, "raw": str}
        """
        try:
            uuid = item.get("uuid")
            value = item.get("raw", "")

            if uuid == self._ble.cfg["char_nav"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_NAV_CMD, {"raw": value})

            elif uuid == self._ble.cfg["char_ctrl"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_RIDE_CONTROL, {"raw": value})

            elif uuid == self._ble.cfg["char_ack"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_BLE_ALARM_ACK, {"raw": value})

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] _parse_and_route 异常: %s" % (self.name, e))

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
        # 等待后台线程安全退出（新版 SDK 推荐 _thread.join）
        if self._notify_tid is not None:
            try:
                import _thread
                _thread.join(self._notify_tid, 3000)
            except Exception as e:
                print("[%s] thread join err: %s" % (self.name, e))
        self.ctx["is_init"] = False
