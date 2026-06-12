import time
from core.Base_Module import BaseModule
from core.config import (
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_COLLISION_DETECTED, EVENT_BUTTON_PRESSED,
    EVENT_BATTERY_LOW, EVENT_BATTERY_CRITICAL, EVENT_GPS_LOST,
    EVENT_CONFIG_UPDATE, EVENT_ALARM_CONTROL,
    ALARM_DURATION_MS, ALARM_ENABLE_LOCAL,
    AUDIO_ALARM_FILE_L1, AUDIO_ALARM_FILE_L2, AUDIO_ALARM_FILE_L3,
    AUDIO_SOS_FILE,
    TTS_BATTERY_LOW, TTS_BATTERY_CRITICAL, TTS_GPS_LOST,
    POWER_STATE_ACTIVE,
)
class AlarmService(BaseModule):
    def __init__(self, event_bus=None, led=None, audio=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "alarm"
        self.led = led
        self.audio = audio
        self.cfg = {
            "alarm_duration_ms": ALARM_DURATION_MS,
            "check_interval_ms": 100,
            "enable_local": ALARM_ENABLE_LOCAL,
        }
        self.ctx = {
            "is_init": False,
            "last_tick": 0,
            "power_state": POWER_STATE_ACTIVE,
            "alarm_active": False,
            "alarm_type": "",
            "alarm_level": 0,
            "alarm_start": 0,
        }
        self._data = {
            "last_alarm": {},
        }
    def init(self):
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_COLLISION_DETECTED, self._on_collision)
                self.event_bus.subscribe(EVENT_BUTTON_PRESSED, self._on_button_press)
                self.event_bus.subscribe(EVENT_GPS_LOST, self._on_gps_lost)
                self.event_bus.subscribe(EVENT_BATTERY_LOW, self._on_battery_low)
                self.event_bus.subscribe(EVENT_BATTERY_CRITICAL, self._on_battery_critical)
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
                self.event_bus.subscribe(EVENT_ALARM_CONTROL, self._on_alarm_control)
            self.ctx["alarm_active"] = False
            self.ctx["alarm_type"] = ""
            self.ctx["alarm_level"] = 0
            self.ctx["alarm_start"] = 0
            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)
        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise
    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["check_interval_ms"]:
            return
        if self.ctx["alarm_active"]:
            if time.ticks_diff(now, self.ctx["alarm_start"]) >= self.cfg["alarm_duration_ms"]:
                self._cancel_alarm()
        self.ctx["last_tick"] = now
    def _start_alarm(self, alarm_type, level):
        if alarm_type == "collision" and level >= 3:
            alarm_type = "sos"
        if self.ctx["alarm_active"]:
            if alarm_type == self.ctx["alarm_type"]:
                self.ctx["alarm_start"] = time.ticks_ms()
                return
            if alarm_type != self.ctx["alarm_type"]:
                self._cancel_alarm()
        self.ctx["alarm_active"] = True
        self.ctx["alarm_type"] = alarm_type
        self.ctx["alarm_level"] = level
        self.ctx["alarm_start"] = time.ticks_ms()
        if self.cfg["enable_local"]:
            if alarm_type == "collision":
                if self.led:
                    self.led.blink(self.cfg["alarm_duration_ms"],
                                   self._level_to_interval(level))
                if self.audio:
                    self.audio.play_file(self._level_to_file(level))
            elif alarm_type == "sos":
                if self.led:
                    self.led.blink(self.cfg["alarm_duration_ms"], 200)
                if self.audio:
                    self.audio.play_file(AUDIO_SOS_FILE)
        if self.event_bus:
            self.event_bus.publish(EVENT_ALARM_TRIGGERED, {
                "alarm_type": alarm_type,
                "level": level,
                "timestamp": time.ticks_ms(),
            })
    def _cancel_alarm(self):
        if not self.ctx["alarm_active"]:
            return
        if self.led:
            self.led.off()
        if self.audio:
            self.audio.stop()
        if self.event_bus:
            self.event_bus.publish(EVENT_ALARM_CANCELED, {
                "duration": time.ticks_diff(
                    time.ticks_ms(), self.ctx["alarm_start"]),
                "timestamp": time.ticks_ms(),
            })
        self.ctx["alarm_active"] = False
        self.ctx["alarm_type"] = ""
        self.ctx["alarm_level"] = 0
        self.ctx["alarm_start"] = 0
    def cancel_alarm(self):
        self._cancel_alarm()
    def trigger_sos(self):
        self._start_alarm("sos", 3)
    def trigger_stealth_alarm(self):
        if self.ctx["alarm_active"]:
            self._cancel_alarm()
        self.ctx["alarm_active"] = True
        self.ctx["alarm_type"] = "stealth"
        self.ctx["alarm_level"] = 1
        self.ctx["alarm_start"] = time.ticks_ms()
        if self.event_bus:
            self.event_bus.publish(EVENT_ALARM_TRIGGERED, {
                "alarm_type": "stealth",
                "level": 1,
                "timestamp": time.ticks_ms(),
            })
        print("[{}] stealth alarm triggered".format(self.name))
    def _on_collision(self, payload):
        level = payload.get("level", 1)
        self._start_alarm("collision", level)
    def _on_button_press(self, payload):
        if self.ctx["alarm_active"]:
            self._cancel_alarm()
        else:
            self._start_alarm("sos", 3)
    def _on_gps_lost(self, payload):
        if self.audio:
            self.audio.play_tts(TTS_GPS_LOST)
    def _on_battery_low(self, payload):
        pass
    def _on_battery_critical(self, payload):
        pass
    def _on_alarm_control(self, payload):
        cmd = payload.get("cmd", "")
        if cmd == "cancel":
            self.cancel_alarm()
        elif cmd == "sos":
            self.trigger_sos()
        elif cmd == "stealth":
            self.trigger_stealth_alarm()
    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "alarm_duration_ms" in payload:
                self.cfg["alarm_duration_ms"] = int(payload["alarm_duration_ms"])
                print("[%s] alarm_duration_ms → %sms" % (self.name, self.cfg["alarm_duration_ms"]))
            if "enable_local" in payload:
                self.cfg["enable_local"] = bool(payload["enable_local"])
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]
    def _level_to_interval(self, level):
        return {1: 1000, 2: 500, 3: 200}.get(level, 1000)
    def _level_to_file(self, level):
        return {
            1: AUDIO_ALARM_FILE_L1,
            2: AUDIO_ALARM_FILE_L2,
            3: AUDIO_ALARM_FILE_L3,
        }.get(level, AUDIO_ALARM_FILE_L1)
    def get_data(self):
        return {
            "alarm_active": self.ctx["alarm_active"],
            "alarm_type": self.ctx["alarm_type"],
            "alarm_level": self.ctx["alarm_level"],
            "last_alarm": dict(self._data["last_alarm"]),
            "timestamp": time.ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "power_state": self.ctx["power_state"],
            "alarm_active": self.ctx["alarm_active"],
        }
