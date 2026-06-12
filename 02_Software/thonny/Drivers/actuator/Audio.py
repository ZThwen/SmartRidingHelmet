import time
from quectel import Audio as Audio
from core.Base_Module import BaseModule
from core.config import (EVENT_AUDIO_PLAYBACK_START, EVENT_AUDIO_PLAYBACK_END,
                    EVENT_AUDIO_ERROR, EVENT_VOLUME_CONTROL,
                    EVENT_CONFIG_UPDATE, EVENT_TTS_REQUEST,
                    POWER_STATE_ACTIVE,
                    AUDIO_TTS_SPEED, AUDIO_TTS_VOLUME, AUDIO_SPEAKER_VOLUME)

class AudioDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "audio"
        self.cfg = {
            "speaker_volume": AUDIO_SPEAKER_VOLUME,
            "tts_speed": AUDIO_TTS_SPEED,
            "tts_volume": AUDIO_TTS_VOLUME,
            "max_retry": 3,
        }
        self.ctx = {
            "is_init": False,
            "is_playing": False,
            "is_tts_playing": False,
            "current_file": None,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
        }
        self._data = {
            "playback_status": "idle",
            "volume": AUDIO_SPEAKER_VOLUME,
            "tts_speed": AUDIO_TTS_SPEED,
        }
        self.audio = None

    def init(self):
        try:
            self.audio = Audio()
            if not self.audio.init(self._audio_event_cb):
                raise RuntimeError("Audio init failed")
            self.audio.set_speaker_volume(self.cfg["speaker_volume"])
            self.audio.tts_set_speed(self.cfg["tts_speed"])
            self.audio.tts_set_volume(self.cfg["tts_volume"])
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
                self.event_bus.subscribe(EVENT_TTS_REQUEST, self._on_tts_request)
                self.event_bus.subscribe(EVENT_VOLUME_CONTROL, self._on_volume_control)
            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)
        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        pass

    def _on_volume_control(self, payload):
        cmd = payload.get("cmd", "")
        current = self._data.get("volume", AUDIO_SPEAKER_VOLUME)
        if cmd == "up":
            self.set_volume(min(current + 1, 5))
        elif cmd == "down":
            self.set_volume(max(current - 1, 0))

    def _audio_event_cb(self, event):
        if event == Audio.PLAY_END:
            self.ctx["is_playing"] = False
            self.ctx["current_file"] = None
            self._data["playback_status"] = "idle"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_END, {
                    "type": "playback", "file": None, "stopped": False})
        elif event == Audio.PLAY_STOP:
            self.ctx["is_playing"] = False
            self.ctx["current_file"] = None
            self._data["playback_status"] = "stopped"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_END, {
                    "type": "playback", "file": None, "stopped": True})
        elif event == Audio.TTS_END:
            self.ctx["is_tts_playing"] = False
            self._data["playback_status"] = "idle"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_END, {
                    "type": "tts", "stopped": False})
        elif event == Audio.TTS_STOP:
            self.ctx["is_tts_playing"] = False
            self._data["playback_status"] = "stopped"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_END, {
                    "type": "tts", "stopped": True})

    def _on_config_update(self, payload):
        if payload.get("target") == self.name:
            if "speaker_volume" in payload:
                self.set_volume(int(payload["speaker_volume"]))
            if "tts_speed" in payload:
                self.set_tts_speed(int(payload["tts_speed"]))
            if "tts_volume" in payload:
                self.set_tts_volume(int(payload["tts_volume"]))
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]

    def _on_tts_request(self, payload):
        text = payload.get("text", "")
        if text:
            self.stop()
            self.play_tts(text)

    def play_file(self, file_path):
        if not self.ctx["is_init"]:
            return False
        self.ctx["is_busy"] = True
        try:
            self.audio.play_local(file_path, False)
            self.ctx["is_playing"] = True
            self.ctx["current_file"] = file_path
            self._data["playback_status"] = "playing"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_START, {
                    "type": "playback", "file": file_path})
            self.ctx["err_count"] = 0
            return True
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] play err (%d): %s" % (self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_AUDIO_ERROR, self.get_error_data(e))
            return False
        finally:
            self.ctx["is_busy"] = False

    def play_tts(self, text):
        if not self.ctx["is_init"]:
            return False
        self.ctx["is_busy"] = True
        try:
            self.audio.tts_play(text)
            self.ctx["is_tts_playing"] = True
            self._data["playback_status"] = "playing"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_START, {
                    "type": "tts", "text": text})
            self.ctx["err_count"] = 0
            return True
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] tts err (%d): %s" % (self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_AUDIO_ERROR, self.get_error_data(e))
            return False
        finally:
            self.ctx["is_busy"] = False

    def stop(self):
        if not self.ctx["is_init"]:
            return False
        try:
            self.audio.play_stop()
            self.audio.tts_stop()
            self.ctx["is_playing"] = False
            self.ctx["is_tts_playing"] = False
            self.ctx["current_file"] = None
            self._data["playback_status"] = "stopped"
            return True
        except Exception as e:
            print("[%s] stop err: %s" % (self.name, e))
            return False

    def set_volume(self, volume):
        volume = max(0, min(5, int(volume)))
        try:
            self.audio.set_speaker_volume(volume)
            self.cfg["speaker_volume"] = volume
            self._data["volume"] = volume
            return True
        except Exception as e:
            print("[%s] vol err: %s" % (self.name, e))
            return False

    def get_volume(self):
        try:
            return self.audio.get_speaker_volume()
        except Exception:
            return self.cfg["speaker_volume"]

    def set_tts_speed(self, speed):
        speed = max(0, min(100, int(speed)))
        try:
            self.audio.tts_set_speed(speed)
            self.cfg["tts_speed"] = speed
            self._data["tts_speed"] = speed
            return True
        except Exception as e:
            print("[%s] tts_speed err: %s" % (self.name, e))
            return False

    def set_tts_volume(self, volume):
        volume = max(0, min(100, int(volume)))
        try:
            self.audio.tts_set_volume(volume)
            self.cfg["tts_volume"] = volume
            return True
        except Exception as e:
            print("[%s] tts_vol err: %s" % (self.name, e))
            return False

    def get_is_playing(self):
        return self.ctx["is_playing"] or self.ctx["is_tts_playing"]

    def get_data(self):
        return {
            "playback_status": self._data["playback_status"],
            "is_playing": self.get_is_playing(),
            "volume": self._data["volume"],
            "tts_speed": self._data["tts_speed"],
            "current_file": self.ctx["current_file"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "is_playing": self.ctx["is_playing"],
            "is_tts_playing": self.ctx["is_tts_playing"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }
