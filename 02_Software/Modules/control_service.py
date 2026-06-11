"""
brief 统一控制服务（ControlService）
note Service层业务服务，接收BLE远端控制指令，路由到对应设备驱动

功能：
1. 订阅 EVENT_RIDE_CONTROL 事件（来自 BLE FFF3 写入）
2. 解析 JSON 控制指令
3. 路由到 LightService / AudioDriver / AlarmService
4. 状态回推（EVENT_CONTROL_STATE_CHANGED）

数据流：
    小程序(按钮) → BLE FFF3 → EVENT_RIDE_CONTROL → ControlService → 设备驱动
    语音模块(未来) → UART → VoiceDriver → EVENT_VOICE_CMD → ControlService → 设备驱动
"""
import time
import json

from core.Base_Module import BaseModule
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_VOICE_CMD,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
)

# CPython 兼容
try:
    _ticks_ms = time.ticks_ms
except AttributeError:
    def _ticks_ms():
        return int(time.time() * 1000)


class ControlService(BaseModule):
    """
    统一控制服务：BLE 远端 + 本地语音 → 统一入口 → 设备驱动

    注入依赖：
        light_service: LightService（灯光控制）
        audio_driver: AudioDriver（音量控制）
        alarm_service: AlarmService（报警取消）
    """

    def __init__(self, event_bus=None, light_service=None,
                 audio_driver=None, alarm_service=None):
        """
        brief 初始化控制服务实例
        param event_bus: 事件总线实例引用
        param light_service: LightService 实例（灯光控制）
        param audio_driver: AudioDriver 实例（音量控制）
        param alarm_service: AlarmService 实例（报警取消）
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "control_service"

        # 注入的依赖（可为 None，调用处有 None guard）
        self.light_service = light_service
        self.audio_driver = audio_driver
        self.alarm_service = alarm_service

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "brightness_step": 10,       # 亮度调节步长 (%)
            "volume_step": 1,            # 音量调节步长
            "volume_max": 7,             # 最大音量
            "volume_min": 0,             # 最小音量
            "default_brightness": 50,    # 开灯默认亮度 (%)
            "cmd_debounce_ms": 300,      # 指令防抖间隔 (ms)
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,
            "err_count": 0,
            "last_cmd_tick": 0,          # 上次指令时间戳（防抖）
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "last_cmd": "",              # 上次执行的指令
            "last_cmd_source": "",       # 指令来源（ble / voice）
        }

        # 控制状态（回推到小程序）
        self._control_state = {
            "light_mode": "auto",        # auto / manual
            "light_brightness": 0,       # 0-100
            "volume": 5,                 # 0-7
            "power_mode": "active",      # active / suspended
        }

        # 指令分发表
        self._cmd_handlers = {
            "light_on":       self._cmd_light_on,
            "light_off":      self._cmd_light_off,
            "brightness_up":  self._cmd_brightness_up,
            "brightness_down": self._cmd_brightness_down,
            "light_auto":     self._cmd_light_auto,
            "volume_up":      self._cmd_volume_up,
            "volume_down":    self._cmd_volume_down,
            "alarm_cancel":   self._cmd_alarm_cancel,
            "power_save":     self._cmd_power_save,
            "power_normal":   self._cmd_power_normal,
        }

    def init(self):
        """
        brief 初始化服务：订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_RIDE_CONTROL, self._on_ride_control)
                # 语音指令预留（等 VoiceDriver 就绪后启用）
                # self.event_bus.subscribe(EVENT_VOICE_CMD, self._on_voice_cmd)

            self.ctx["is_init"] = True
            print("[{}] OK init".format(self.name))

        except Exception as e:
            print("[{}] FAIL init: {}".format(self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：纯事件驱动，tick()为空实现
        """
        pass

    # ==================== 事件回调 ====================

    def _on_ride_control(self, payload):
        """
        brief BLE 远端控制事件回调
        param payload: {"raw": "{\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_on\"}}"}
        """
        raw = payload.get("raw", "")
        try:
            cmd_obj = json.loads(raw)
        except Exception as e:
            print("[{}] JSON解析失败: {} | raw={}".format(
                self.name, e, str(raw)[:50]))
            self.ctx["err_count"] += 1
            return

        if cmd_obj.get("a") != "ctrl":
            return

        cmd = cmd_obj.get("d", {}).get("cmd", "")
        self._execute_cmd(cmd, source="ble")

    def _on_voice_cmd(self, payload):
        """
        brief 语音指令事件回调（等 VoiceDriver 就绪后启用）
        param payload: {"cmd": "light_on", "id": 1}
        """
        cmd = payload.get("cmd", "")
        self._execute_cmd(cmd, source="voice")

    # ==================== 指令执行 ====================

    def _execute_cmd(self, cmd, source="unknown"):
        """
        brief 执行控制指令（统一入口）
        param cmd: 指令字符串
        param source: 指令来源（ble / voice）
        """
        if not cmd:
            return

        # 防抖
        now = _ticks_ms()
        if time.ticks_diff(now, self.ctx["last_cmd_tick"]) < self.cfg["cmd_debounce_ms"]:
            return

        handler = self._cmd_handlers.get(cmd)
        if handler:
            try:
                handler()
                self.ctx["last_cmd_tick"] = now
                self._data["last_cmd"] = cmd
                self._data["last_cmd_source"] = source
                self._push_state()
                print("[{}] cmd={} src={}".format(self.name, cmd, source))
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[{}] cmd执行异常: {} | cmd={}".format(
                    self.name, e, cmd))
        else:
            print("[{}] unknown cmd: {}".format(self.name, cmd))

    # ==================== 指令实现 ====================

    def _cmd_light_on(self):
        if self.light_service:
            self.light_service.set_manual_brightness(self.cfg["default_brightness"])
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = self.cfg["default_brightness"]

    def _cmd_light_off(self):
        if self.light_service:
            self.light_service.set_manual_brightness(0)
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = 0

    def _cmd_brightness_up(self):
        if self.light_service:
            current = self._control_state["light_brightness"]
            new_val = min(current + self.cfg["brightness_step"], 100)
            self.light_service.set_manual_brightness(new_val)
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = new_val

    def _cmd_brightness_down(self):
        if self.light_service:
            current = self._control_state["light_brightness"]
            new_val = max(current - self.cfg["brightness_step"], 0)
            self.light_service.set_manual_brightness(new_val)
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = new_val

    def _cmd_light_auto(self):
        if self.light_service:
            self.light_service.set_auto_mode()
            self._control_state["light_mode"] = "auto"

    def _cmd_volume_up(self):
        if self.audio_driver:
            current = self._control_state["volume"]
            new_vol = min(current + self.cfg["volume_step"], self.cfg["volume_max"])
            try:
                self.audio_driver.set_volume(new_vol)
            except Exception:
                pass
            self._control_state["volume"] = new_vol

    def _cmd_volume_down(self):
        if self.audio_driver:
            current = self._control_state["volume"]
            new_vol = max(current - self.cfg["volume_step"], self.cfg["volume_min"])
            try:
                self.audio_driver.set_volume(new_vol)
            except Exception:
                pass
            self._control_state["volume"] = new_vol

    def _cmd_alarm_cancel(self):
        if self.alarm_service:
            self.alarm_service.cancel_alarm()

    def _cmd_power_save(self):
        if self.event_bus:
            self.event_bus.publish(EVENT_POWER_STATE_CHANGE, {
                "power_state": POWER_STATE_SUSPENDED
            })
        self._control_state["power_mode"] = "suspended"

    def _cmd_power_normal(self):
        if self.event_bus:
            self.event_bus.publish(EVENT_POWER_STATE_CHANGE, {
                "power_state": POWER_STATE_ACTIVE
            })
        self._control_state["power_mode"] = "active"

    # ==================== 状态回推 ====================

    def _push_state(self):
        """
        brief 推送控制状态到 BLE（通过 EventBus）
        """
        if self.event_bus:
            self.event_bus.publish(EVENT_CONTROL_STATE_CHANGED,
                                   dict(self._control_state))

    # ==================== 数据接口 ====================

    def get_data(self):
        """
        brief 获取控制数据快照
        return dict {last_cmd, last_cmd_source, control_state, timestamp}
        """
        return {
            "last_cmd": self._data["last_cmd"],
            "last_cmd_source": self._data["last_cmd_source"],
            "control_state": dict(self._control_state),
            "timestamp": _ticks_ms(),
        }

    def get_status(self):
        """
        brief 获取运行状态快照
        return dict {is_init, err_count, control_state}
        """
        return {
            "is_init": self.ctx["is_init"],
            "err_count": self.ctx["err_count"],
            "control_state": dict(self._control_state),
        }
