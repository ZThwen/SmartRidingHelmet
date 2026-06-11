from quectel import BLE
import time
from core.Base_Module import BaseModule
from core.config import (
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    EVENT_NAV_CMD, EVENT_RIDE_CONTROL, EVENT_BLE_ALARM_ACK,
    EVENT_CONFIG_UPDATE, POWER_STATE_ACTIVE,
    BLE_DEVICE_NAME, BLE_SERVICE_UUID, BLE_CHAR_DATA,
    BLE_CHAR_NAV, BLE_CHAR_CTRL, BLE_CHAR_ACK,
    BLE_MTU,
)
CCCD_UUID = 0x2902
class BLEDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "ble"
        self.cfg = {
            "device_name": BLE_DEVICE_NAME,
            "service_uuid": BLE_SERVICE_UUID,
            "char_data": BLE_CHAR_DATA,
            "char_nav": BLE_CHAR_NAV,
            "char_ctrl": BLE_CHAR_CTRL,
            "char_ack": BLE_CHAR_ACK,
            "mtu": BLE_MTU,
        }
        self.ctx = {
            "is_init": False,
            "is_connected": False,
            "mtu": 23,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
        }
        self._data = {
            "connected_addr": "",
            "connected_time": 0,
        }
        self._ble = None
        self._connected_published = False
    def init(self):
        try:
            self._ble = BLE()
            ok = self._ble.init(self._callback)
            if not ok:
                raise RuntimeError("BLE.init() 返回 False")
            time.sleep_ms(200)
            self._ble.set_dataformat(BLE.DATAFMT_STRING)
            self._ble.start(self.cfg["device_name"])
            self._ble.add_service(0, self.cfg["service_uuid"], True)
            props = BLE.PROP_READ | BLE.PROP_WRITE | BLE.PROP_NOTIFY | BLE.PROP_INDICATE
            perm = BLE.PERM_READ | BLE.PERM_WRITE
            char_max_len = 244
            self._ble.add_character(0, 0, props, self.cfg["char_data"])
            self._ble.set_character_value(0, 0, perm, self.cfg["char_data"], char_max_len, "00")
            self._ble.add_descriptor(0, 0, perm, CCCD_UUID, "0000")
            self._ble.add_character(0, 1, BLE.PROP_READ | BLE.PROP_WRITE, self.cfg["char_nav"])
            self._ble.set_character_value(0, 1, perm, self.cfg["char_nav"], char_max_len, "00")
            self._ble.add_descriptor(0, 1, perm, CCCD_UUID, "0000")
            self._ble.add_character(0, 2, BLE.PROP_READ | BLE.PROP_WRITE, self.cfg["char_ctrl"])
            self._ble.set_character_value(0, 2, perm, self.cfg["char_ctrl"], char_max_len, "00")
            self._ble.add_descriptor(0, 2, perm, CCCD_UUID, "0000")
            self._ble.add_character(0, 3, BLE.PROP_READ | BLE.PROP_WRITE, self.cfg["char_ack"])
            self._ble.set_character_value(0, 3, perm, self.cfg["char_ack"], char_max_len, "00")
            self._ble.add_descriptor(0, 3, perm, CCCD_UUID, "0000")
            self._ble.advertise()
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[%s] ✓ 初始化完成 | %s | addr=%s" % (
                self.name, self.cfg["device_name"], self._ble.get_addr()))
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise
    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
    def notify_data(self, json_str):
        if not self.ctx["is_connected"]:
            return
        try:
            self._ble.notify(self.cfg["char_data"], len(json_str), json_str)
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] notify 失败: %s" % (self.name, e))
    def exchange_mtu(self, mtu=None):
        if mtu is None:
            mtu = self.cfg["mtu"]
        try:
            self._ble.exchange_mtu(mtu)
        except Exception as e:
            print("[%s] MTU 协商失败: %s" % (self.name, e))
    def stop(self):
        try:
            self._ble.stop()
            self._ble.deinit()
            self.ctx["is_connected"] = False
            self.ctx["is_init"] = False
            print("[%s] ✓ 已停止" % self.name)
        except Exception as e:
            print("[%s] 停止失败: %s" % (self.name, e))
    def _callback(self, evt):
        try:
            event_id = evt.get("event")
            if event_id == BLE.EVT_CONNECTED:
                self.ctx["is_connected"] = True
                self._connected_published = True
                self._data["connected_time"] = time.ticks_ms()
                print("[%s] 手机已连接" % self.name)
                if self.event_bus:
                    self.event_bus.publish(EVENT_BLE_CONNECTED, {
                        "addr": self._ble.get_addr() if self._ble else "",
                        "timestamp": time.ticks_ms(),
                    })
            elif event_id == BLE.EVT_DISCONNECTED:
                self.ctx["is_connected"] = False
                self._connected_published = False
                print("[%s] 手机已断开" % self.name)
                if self.event_bus:
                    self.event_bus.publish(EVENT_BLE_DISCONNECTED, {
                        "timestamp": time.ticks_ms(),
                    })
            elif event_id == BLE.EVT_MTU:
                self.ctx["mtu"] = evt.get("mtu", 23)
                print("[%s] MTU = %d" % (self.name, self.ctx["mtu"]))
                if not self._connected_published:
                    self.ctx["is_connected"] = True
                    self._connected_published = True
                    self._data["connected_time"] = time.ticks_ms()
                    print("[%s] 手机已连接 (via MTU)" % self.name)
                    if self.event_bus:
                        self.event_bus.publish(EVENT_BLE_CONNECTED, {
                            "addr": self._ble.get_addr() if self._ble else "",
                            "timestamp": time.ticks_ms(),
                        })
            elif event_id == BLE.EVT_VAL_DATA:
                uuid = evt.get("uuid")
                value = evt.get("value", "")
                if isinstance(value, str) and len(value) > 2:
                    try:
                        clean = value.strip().replace(' ', '').replace('\n', '').replace('\r', '')
                        if len(clean) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in clean):
                            value = bytes.fromhex(clean).decode('utf-8')
                    except:
                        pass
                if uuid == self.cfg["char_nav"]:
                    if self.event_bus:
                        self.event_bus.publish(EVENT_NAV_CMD, {"raw": value})
                elif uuid == self.cfg["char_ctrl"]:
                    if self.event_bus:
                        self.event_bus.publish(EVENT_RIDE_CONTROL, {"raw": value})
                elif uuid == self.cfg["char_ack"]:
                    if self.event_bus:
                        self.event_bus.publish(EVENT_BLE_ALARM_ACK, {"raw": value})
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] _callback 异常: %s" % (self.name, e))
    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "mtu" in payload:
                self.cfg["mtu"] = int(payload["mtu"])
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]
    def get_data(self):
        return {
            "is_connected": self.ctx["is_connected"],
            "mtu": self.ctx["mtu"],
            "connected_addr": self._data["connected_addr"],
            "timestamp": time.ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_connected": self.ctx["is_connected"],
            "err_count": self.ctx["err_count"],
            "mtu": self.ctx["mtu"],
            "power_state": self.ctx["power_state"],
        }