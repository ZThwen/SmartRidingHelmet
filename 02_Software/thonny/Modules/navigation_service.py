import time
import json
import _thread
from core.Base_Module import BaseModule
from core.config import (
    EVENT_NAV_CMD,
    TTS_NAV_ARRIVE, TTS_NAV_CANCEL,
)
# CPython 兼容：MicroPython 有 time.ticks_ms()，CPython 没有
try:
    _ticks_ms = time.ticks_ms
except AttributeError:
    def _ticks_ms():
        return int(time.time() * 1000)
_DIR_MAP = {
    "left":        "左转",
    "right":       "右转",
    "straight":    "直行",
    "slight_left":  "靠左",
    "slight_right": "靠右",
    "uturn":       "掉头",
    "arrive":      "到达目的地",
    "cancel":      "导航结束",
}
_DIR_SYMBOL = {
    "left":        "<",
    "right":       ">",
    "straight":    "^",
    "slight_left":  "<",
    "slight_right": ">",
    "uturn":       "U",
    "arrive":      "*",
    "cancel":      "x",
}
def _map_direction(dir_str):
    return _DIR_MAP.get(dir_str, "直行")
def _build_tts_text(dir_str, dist, road):
    if dir_str == "arrive":
        return TTS_NAV_ARRIVE
    if dir_str == "cancel":
        return TTS_NAV_CANCEL
    cn_dir = _map_direction(dir_str)
    if road:
        return "前方%d米%s进入%s" % (dist, cn_dir, road)
    else:
        return "前方%d米%s" % (dist, cn_dir)
def _build_lcd_text(dir_str, dist, road):
    if dir_str == "arrive":
        return "已到达"
    if dir_str == "cancel":
        return "导航结束"
    sym = _DIR_SYMBOL.get(dir_str, "^")
    if road:
        short_road = road[:10]
        return "%s %dm %s" % (sym, dist, short_road)
    else:
        return "%s %dm" % (sym, dist)
class NavigationService(BaseModule):
    def __init__(self, event_bus=None, audio_driver=None, lcd_driver=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "navigation"
        self.audio_driver = audio_driver
        self.lcd_driver = lcd_driver
        self.cfg = {
            "nav_line_y": 110,
            "nav_line_x": 5,
            "sample_ms": 1000,
        }
        self.ctx = {
            "is_init": False,
            "is_navigating": False,
            "is_tts_playing": False,
            "current_dir": "",
            "current_dist": 0,
            "current_road": "",
            "last_tick": 0,
            "err_count": 0,
        }
        self._data = {
            "is_navigating": False,
            "current_dir": "",
            "current_dist": 0,
            "current_road": "",
            "last_tts": "",
            "last_lcd": "",
        }
    def init(self):
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_NAV_CMD, self._on_nav_cmd)
            self.ctx["is_init"] = True
            print("[{}] 初始化完成".format(self.name))
        except Exception as e:
            print("[{}] 初始化失败: {}".format(self.name, e))
            raise
    def tick(self):
        pass
    def _on_nav_cmd(self, payload):
        print("[nav] 收到事件: %s" % str(payload)[:80])
        raw = payload.get("raw", "")
        try:
            cmd = json.loads(raw)
        except Exception as e:
            print("[nav] JSON解析失败: %s | raw=%s" % (e, str(raw)[:50]))
            self.ctx["err_count"] += 1
            return
        action = cmd.get("a", "")
        if action != "nav":
            return
        d = cmd.get("d", {})
        dir_str = d.get("dir", "straight")
        dist = d.get("dist", 0)
        road = d.get("road", "")
        self.ctx["current_dir"] = dir_str
        self.ctx["current_dist"] = dist
        self.ctx["current_road"] = road
        if dir_str in ("arrive", "cancel"):
            self.ctx["is_navigating"] = False
        else:
            self.ctx["is_navigating"] = True
        self._data["is_navigating"] = self.ctx["is_navigating"]
        self._data["current_dir"] = dir_str
        self._data["current_dist"] = dist
        self._data["current_road"] = road
        tts_text = _build_tts_text(dir_str, dist, road)
        self._data["last_tts"] = tts_text
        print("[nav] ▶ TTS: %s" % tts_text)
        if self.audio_driver:
            if self.ctx.get("is_tts_playing"):
                print("[nav] TTS 播放中，跳过")
            else:
                self.ctx["is_tts_playing"] = True
                svc_ref = self
                def _tts_thread(text, drv, svc):
                    try:
                        drv.play_tts(text)
                    except:
                        pass
                    svc.ctx["is_tts_playing"] = False
                _thread.start_new_thread(_tts_thread, (tts_text, self.audio_driver, svc_ref))
        lcd_text = _build_lcd_text(dir_str, dist, road)
        self._data["last_lcd"] = lcd_text
        self._write_nav_line(lcd_text)
        print("[nav] LCD: %s" % lcd_text)
    def _write_nav_line(self, text):
        if not self.lcd_driver:
            return
        try:
            if hasattr(self.lcd_driver, 'lcd') and hasattr(self.lcd_driver.lcd, 'show_string'):
                lcd = self.lcd_driver.lcd
                lcd.fill_rectangle(
                    self.cfg["nav_line_x"],
                    self.cfg["nav_line_y"],
                    150, 16, lcd.BLACK
                )
                lcd.show_string(
                    self.cfg["nav_line_x"],
                    self.cfg["nav_line_y"],
                    text, lcd.GREEN, lcd.BLACK
                )
        except Exception as e:
            print("[{}] LCD写入失败: {}".format(self.name, e))
            self.ctx["err_count"] += 1
    def get_data(self):
        return {
            "is_navigating": self._data["is_navigating"],
            "current_dir": self._data["current_dir"],
            "current_dist": self._data["current_dist"],
            "current_road": self._data["current_road"],
            "last_tts": self._data["last_tts"],
            "last_lcd": self._data["last_lcd"],
            "timestamp": _ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_navigating": self.ctx["is_navigating"],
            "current_dir": self.ctx["current_dir"],
            "current_dist": self.ctx["current_dist"],
            "current_road": self.ctx["current_road"],
            "err_count": self.ctx["err_count"],
        }
