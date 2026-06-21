"""
brief 音频驱动模块
note 纯硬件控制层，封装 quectel.Audio 原生API，提供音频播放/TTS/录音接口
     不包含任何业务逻辑，由 AlarmService 调用公共接口触发播放
"""
import time

from quectel import Audio as Audio

from core.Base_Module import BaseModule
from core.config import (EVENT_AUDIO_PLAYBACK_START, EVENT_AUDIO_PLAYBACK_END,
                    EVENT_AUDIO_ERROR, EVENT_VOLUME_CONTROL,
                    EVENT_CONFIG_UPDATE, EVENT_TTS_REQUEST, EVENT_POWER_STATE_CHANGE,
                    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
                    POWER_STATE_ACTIVE,
                    AUDIO_TTS_SPEED, AUDIO_TTS_VOLUME, AUDIO_SPEAKER_VOLUME)


class AudioDriver(BaseModule):
    """
    brief 音频驱动：播放音频文件、TTS语音播报、录音
    note
        - EC200U 仅支持喇叭通道（device=2），由 quectel.Audio 默认处理
        - Audio 与 TTS 共用底层播放队列，stop_all 会清空所有待播放任务
        - 回调在底层中断线程执行，内部禁止耗时操作
    """
    def __init__(self, event_bus=None):
        """
        brief 初始化音频驱动实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "audio"

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "speaker_volume": AUDIO_SPEAKER_VOLUME,  # 扬声器音量 0-5
            "tts_speed": AUDIO_TTS_SPEED,            # TTS 语速 0-100
            "tts_volume": AUDIO_TTS_VOLUME,          # TTS 音量 0-100
            "max_retry": 3,                           # 连续失败最大重试次数
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,          # 硬件初始化完成标志
            "is_playing": False,       # 音频文件播放中标志
            "is_tts_playing": False,   # TTS 播报中标志
            "current_file": None,      # 当前播放文件名
            "err_count": 0,            # 连续操作错误计数
            "power_state": POWER_STATE_ACTIVE,  # 功耗状态
            "alarm_playing": False,    # 报警音频播放中标志
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "playback_status": "idle",           # 播放状态: idle/playing/stopped
            "volume": AUDIO_SPEAKER_VOLUME,      # 当前音量
            "tts_speed": AUDIO_TTS_SPEED,        # 当前 TTS 语速
        }

        self.audio = None

    def init(self):
        """
        brief 初始化模块：创建 Audio 实例 + 注册回调 + 配置初始参数
        note  失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            # 1. 创建 Audio 实例
            self.audio = Audio()

            # 2. 初始化硬件并注册回调
            if not self.audio.init(self._audio_event_cb):
                raise RuntimeError("Audio 硬件初始化失败")

            # 3. 配置初始参数
            self.audio.set_speaker_volume(self.cfg["speaker_volume"])
            self.audio.tts_set_speed(self.cfg["tts_speed"])
            self.audio.tts_set_volume(self.cfg["tts_volume"])

            # 4. 订阅事件
            if self.event_bus:
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)
                self.event_bus.subscribe(EVENT_TTS_REQUEST, self._on_tts_request)
                self.event_bus.subscribe(EVENT_VOLUME_CONTROL, self._on_volume_control)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)

            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成 | 音量:{self.cfg['speaker_volume']} TTS语速:{self.cfg['tts_speed']}")

        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """
        brief 周期调度
        note Audio 为被动控制型设备，无主动采样需求，tick 保持轻量
        """
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        # Audio 无需周期性采样，保持空实现维持生命周期
        pass

    def _on_volume_control(self, payload):
        """
        brief 音量控制指令回调（来自 ControlService）
        param payload: {cmd: "up"/"down"}
        """
        cmd = payload.get("cmd", "")
        current = self._data.get("volume", AUDIO_SPEAKER_VOLUME)
        if cmd == "up":
            self.set_volume(min(current + 1, 5))
        elif cmd == "down":
            self.set_volume(max(current - 1, 0))

    # ==================== 事件回调 ====================
    def _audio_event_cb(self, event):
        """
        brief Audio 底层回调（在中断/回调线程执行）
        note 回调中禁止耗时/阻塞操作，只做状态更新 + 事件发布
        param event: 播放状态码（Audio.PLAY_END / PLAY_STOP / TTS_END / TTS_STOP）
        """
        if event == Audio.PLAY_END:
            self.ctx["is_playing"] = False
            self.ctx["current_file"] = None
            self._data["playback_status"] = "idle"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_END, {
                    "type": "playback", "file": None,
                    "stopped": False
                })

        elif event == Audio.PLAY_STOP:
            self.ctx["is_playing"] = False
            self.ctx["current_file"] = None
            self._data["playback_status"] = "stopped"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_END, {
                    "type": "playback", "file": None,
                    "stopped": True
                })

        elif event == Audio.TTS_END:
            self.ctx["is_tts_playing"] = False
            self._data["playback_status"] = "idle"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_END, {
                    "type": "tts", "stopped": False
                })

        elif event == Audio.TTS_STOP:
            self.ctx["is_tts_playing"] = False
            self._data["playback_status"] = "stopped"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_END, {
                    "type": "tts", "stopped": True
                })

    def _on_config_update(self, payload):
        """
        brief 配置更新回调处理
        param payload: 配置事件负载
        note
            - target == self.name: 模块特定参数（音量、语速）
            - power_state: 全局功耗状态
        """
        if payload.get("target") == self.name:
            if "speaker_volume" in payload:
                self.set_volume(int(payload["speaker_volume"]))
            if "tts_speed" in payload:
                self.set_tts_speed(int(payload["tts_speed"]))
            if "tts_volume" in payload:
                self.set_tts_volume(int(payload["tts_volume"]))

        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print(f"[{self.name}] 功耗状态: {old_state} -> {payload['power_state']}")

    def _on_tts_request(self, payload):
        """
        brief TTS 播报请求回调
        param payload: {text: "当前温度28度"}
        note 先停止当前播报再播放新的，防止重叠
              报警中拒绝 TTS（报警音优先）
        """
        if self.ctx.get("alarm_playing"):
            return  # 报警中，拒绝 TTS
        text = payload.get("text", "")
        if text:
            self.stop()
            self.play_tts(text)

    def _on_alarm_triggered(self, payload):
        """报警触发：标记报警播放中"""
        self.ctx["alarm_playing"] = True

    def _on_alarm_canceled(self, payload):
        """报警取消：清除报警播放标志"""
        self.ctx["alarm_playing"] = False

    # ==================== 公共接口（供 Service 层调用）====================
    def play_file(self, file_path):
        """
        brief 播放音频文件
        param file_path: 文件路径（如 "SD:alarm_l2.mp3"）
        return bool 是否成功发起播放
        note 播放完成/停止通过回调事件通知
        """
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
                    "type": "playback", "file": file_path
                })
            self.ctx["err_count"] = 0
            return True
        except Exception as e:
            self.ctx["err_count"] += 1
            print(f"[{self.name}] 播放失败 ({self.ctx['err_count']}): {e}")
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_AUDIO_ERROR, self.get_error_data(e))
            return False
        finally:
            self.ctx["is_busy"] = False

    def play_tts(self, text):
        """
        brief TTS 语音播报
        param text: 待播报文本（支持中文）
        return bool 是否成功发起播报
        """
        if not self.ctx["is_init"]:
            return False
        self.ctx["is_busy"] = True
        try:
            self.audio.tts_play(text)
            self.ctx["is_tts_playing"] = True
            self._data["playback_status"] = "playing"
            if self.event_bus:
                self.event_bus.publish(EVENT_AUDIO_PLAYBACK_START, {
                    "type": "tts", "text": text
                })
            self.ctx["err_count"] = 0
            return True
        except Exception as e:
            self.ctx["err_count"] += 1
            print(f"[{self.name}] TTS播报失败 ({self.ctx['err_count']}): {e}")
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_AUDIO_ERROR, self.get_error_data(e))
            return False
        finally:
            self.ctx["is_busy"] = False

    def stop(self):
        """
        brief 停止所有播放（音频 + TTS）
        return bool 停止是否成功
        """
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
            print(f"[{self.name}] 停止播放失败: {e}")
            return False

    def set_volume(self, volume):
        """
        brief 设置扬声器音量
        param volume: 音量值 0-5
        return bool 设置是否成功
        """
        volume = max(0, min(5, int(volume)))
        try:
            self.audio.set_speaker_volume(volume)
            self.cfg["speaker_volume"] = volume
            self._data["volume"] = volume
            return True
        except Exception as e:
            print(f"[{self.name}] 设置音量失败: {e}")
            return False

    def get_volume(self):
        """
        brief 获取当前扬声器音量
        return int 当前音量值 (0-5)
        """
        try:
            return self.audio.get_speaker_volume()
        except Exception:
            return self.cfg["speaker_volume"]

    def set_tts_speed(self, speed):
        """
        brief 设置 TTS 播报语速
        param speed: 语速值 (0-100)
        return bool 设置是否成功
        """
        speed = max(0, min(100, int(speed)))
        try:
            self.audio.tts_set_speed(speed)
            self.cfg["tts_speed"] = speed
            self._data["tts_speed"] = speed
            return True
        except Exception as e:
            print(f"[{self.name}] 设置TTS语速失败: {e}")
            return False

    def set_tts_volume(self, volume):
        """
        brief 设置 TTS 播报音量
        param volume: 音量值 (0-100)
        return bool 设置是否成功
        note TTS 音量在 Audio 扬声器音量基础上叠加增益
        """
        volume = max(0, min(100, int(volume)))
        try:
            self.audio.tts_set_volume(volume)
            self.cfg["tts_volume"] = volume
            return True
        except Exception as e:
            print(f"[{self.name}] 设置TTS音量失败: {e}")
            return False

    def get_is_playing(self):
        """
        brief 查询是否有播放正在进行
        return bool True=正在播放
        """
        return self.ctx["is_playing"] or self.ctx["is_tts_playing"]

    # ==================== 辅助方法 ====================
    def get_data(self):
        """
        brief 获取当前音频播放状态快照
        return dict {playback_status, is_playing, volume, current_file, timestamp}
        """
        return {
            "playback_status": self._data["playback_status"],
            "is_playing": self.get_is_playing(),
            "volume": self._data["volume"],
            "tts_speed": self._data["tts_speed"],
            "current_file": self.ctx["current_file"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        """
        brief 查询模块运行状态快照
        return dict {is_init, is_playing, is_tts_playing, err_count, power_state}
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_playing": self.ctx["is_playing"],
            "is_tts_playing": self.ctx["is_tts_playing"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }
