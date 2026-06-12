import machine
import time
from core.Base_Module import BaseModule
from core.config import (
    EVENT_LCD_ERROR, EVENT_CONFIG_UPDATE,
    LCD_BACKLIGHT_HIGH, LCD_SAMPLE_MS, POWER_STATE_ACTIVE
)
from st7735 import LCD
class LCDDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "lcd"
        self.cfg = {
            "spi_id": 1,
            "spi_baudrate": 20000000,
            "spi_polarity": 0,
            "spi_phase": 0,
            "dc_pin": "F12",
            "cs_pin": "D14",
            "rotation": 1,
            "sample_ms": LCD_SAMPLE_MS,
            "max_retry": 3,
        }
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE
        }
        self._data = {
            "display_mode": "blank",
            "temp": 0.0,
            "humid": 0.0,
            "lat": 0.0,
            "lon": 0.0,
            "alarm_type": "",
            "backlight": LCD_BACKLIGHT_HIGH,
            "valid": False,
        }
        self.spi = None
        self.lcd = None
    def init(self):
        try:
            self.spi = machine.SPI(
                self.cfg["spi_id"],
                baudrate=self.cfg["spi_baudrate"],
                polarity=self.cfg["spi_polarity"],
                phase=self.cfg["spi_phase"]
            )
            self.lcd = LCD(self.spi, dc_pin=self.cfg["dc_pin"], cs_pin=self.cfg["cs_pin"])
            self.lcd.set_rotation(self.cfg["rotation"])
            self.lcd.fill_screen(self.lcd.BLACK)
            self.lcd.flush()
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["is_init"] = True
            print("[%s] ✓ 初始化完成 | SPI%s @ %sHz, dc=%s, cs=%s" % (self.name, self.cfg['spi_id'], self.cfg['spi_baudrate'], self.cfg['dc_pin'], self.cfg['cs_pin']))
        except Exception as e:
            print("[%s] ✗ 初始化失败: %s" % (self.name, e))
            raise
    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return
        self.ctx["last_tick"] = now
    def show_normal_data(self, temp, humid, lat, lon):
        if not self.ctx["is_init"]:
            return
        if self._data["display_mode"] in ("alarm_collision", "alarm_sos", "alarm_unknown"):
            return
        if self.ctx["is_busy"]:
            return
        self.ctx["is_busy"] = True
        try:
            self.lcd.fill_screen(self.lcd.BLACK)
            self.lcd.show_string(0, 6, "Temp/Humi", self.lcd.BLUE, self.lcd.BLACK)
            temp_humi_str = "{}C / {}%".format(
                self._format_float(temp, 1),
                self._format_float(humid, 1)
            )
            self.lcd.show_string(0, 26, temp_humi_str, self.lcd.WHITE, self.lcd.BLACK)
            self.lcd.show_string(0, 46, "Position", self.lcd.BLUE, self.lcd.BLACK)
            lat_str = "Lat:{}".format(self._format_float(lat, 4))
            lon_str = "Lon:{}".format(self._format_float(lon, 4))
            self.lcd.show_string(0, 66, lat_str, self.lcd.WHITE, self.lcd.BLACK)
            self.lcd.show_string(0, 86, lon_str, self.lcd.WHITE, self.lcd.BLACK)
            self.lcd.flush()
            self._data["display_mode"] = "normal"
            self._data["temp"] = temp
            self._data["humid"] = humid
            self._data["lat"] = lat
            self._data["lon"] = lon
            self._data["alarm_type"] = ""
            self._data["valid"] = True
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] 显示异常 ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LCD_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
    def show_alarm(self, alarm_type):
        if not self.ctx["is_init"]:
            return
        if self.ctx["is_busy"]:
            return
        self.ctx["is_busy"] = True
        try:
            self.lcd.fill_screen(self.lcd.BLACK)
            if alarm_type == "collision":
                self.lcd.show_string(10, 40, "COLLISION!", self.lcd.RED, self.lcd.BLACK)
                self.lcd.show_string(30, 70, "SOS", self.lcd.RED, self.lcd.BLACK)
                self._data["display_mode"] = "alarm_collision"
                self._data["alarm_type"] = "collision"
            elif alarm_type == "sos":
                self.lcd.show_string(10, 40, "EMERGENCY!", self.lcd.RED, self.lcd.BLACK)
                self.lcd.show_string(30, 70, "SOS", self.lcd.RED, self.lcd.BLACK)
                self._data["display_mode"] = "alarm_sos"
                self._data["alarm_type"] = "sos"
            else:
                self.lcd.show_string(10, 40, "ALARM!", self.lcd.RED, self.lcd.BLACK)
                self.lcd.show_string(30, 70, "SOS", self.lcd.RED, self.lcd.BLACK)
                self._data["display_mode"] = "alarm_unknown"
                self._data["alarm_type"] = "unknown"
            self.lcd.flush()
            self._data["valid"] = True
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] 报警显示异常 ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LCD_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
    def clear(self):
        if not self.ctx["is_init"]:
            return
        if self.ctx["is_busy"]:
            return
        self.ctx["is_busy"] = True
        try:
            self.lcd.fill_screen(self.lcd.BLACK)
            self.lcd.flush()
            self._data["display_mode"] = "normal"
            self._data["temp"] = 0.0
            self._data["humid"] = 0.0
            self._data["lat"] = 0.0
            self._data["lon"] = 0.0
            self._data["alarm_type"] = ""
            self._data["valid"] = True
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 清屏异常 ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LCD_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
    def set_backlight(self, level):
        if not self.ctx["is_init"]:
            return
        if level > 100:
            level = 100
        elif level < 0:
            level = 0
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            level = 0
        old_backlight = self._data["backlight"]
        self._data["backlight"] = level
        if old_backlight > 0 and level == 0:
            print("[{}] 背光关闭，LCD进入休眠".format(self.name))
        elif old_backlight == 0 and level > 0:
            print("[{}] 背光恢复，LCD从休眠唤醒".format(self.name))
    def show_image(self, x, y, w, h, data):
        if not self.ctx["is_init"]:
            return
        if self.ctx["is_busy"]:
            return
        self.ctx["is_busy"] = True
        try:
            self.lcd.show_image(x, y, w, h, data)
            self.lcd.flush()
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 图标显示异常 ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LCD_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
    def _on_config_update(self, payload):
        if payload.get("target") == self.name and "sample_ms" in payload:
            self.cfg["sample_ms"] = int(payload["sample_ms"])
            print("[{}] 刷新间隔更新为 {}ms".format(self.name, self.cfg["sample_ms"]))
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[{}] 功耗状态: {} -> {}".format(self.name, old_state, payload["power_state"]))
            if payload["power_state"] != POWER_STATE_ACTIVE:
                self.set_backlight(0)
            elif old_state != POWER_STATE_ACTIVE:
                self.set_backlight(self._data["backlight"] or LCD_BACKLIGHT_HIGH)
    def _format_float(self, value, decimal_places):
        try:
            rounded = round(float(value), decimal_places)
            if decimal_places == 0:
                return str(int(rounded))
            fmt = "{{:.{}f}}".format(decimal_places)
            return fmt.format(rounded)
        except (TypeError, ValueError):
            return str(value)
    def get_data(self):
        return {
            "display_mode": self._data["display_mode"],
            "temp": self._data["temp"],
            "humid": self._data["humid"],
            "lat": self._data["lat"],
            "lon": self._data["lon"],
            "alarm_type": self._data["alarm_type"],
            "backlight": self._data["backlight"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }
