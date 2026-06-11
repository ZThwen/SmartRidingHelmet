"""
brief 报警联动服务（AlarmService）
note 接收碰撞/SOS/GPS丢失等事件，协调 LED + Audio 驱动完成声光报警
      报警超时自动取消，SW按钮双击语义：空闲→SOS，报警中→取消
      Device 驱动由构造函数注入，LCD 交由 DisplayService 负责
"""
import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_COLLISION_DETECTED, EVENT_BUTTON_PRESSED,
    EVENT_BATTERY_LOW, EVENT_BATTERY_CRITICAL, EVENT_GPS_LOST,
    EVENT_CONFIG_UPDATE,
    ALARM_DURATION_MS, ALARM_ENABLE_LOCAL,
    AUDIO_ALARM_FILE_L1, AUDIO_ALARM_FILE_L2, AUDIO_ALARM_FILE_L3,
    AUDIO_SOS_FILE,
    TTS_BATTERY_LOW, TTS_BATTERY_CRITICAL, TTS_GPS_LOST,
    POWER_STATE_ACTIVE,
)


class AlarmService(BaseModule):
    def __init__(self, event_bus=None, led=None, audio=None):
        """
        brief 初始化报警联动服务实例
        param event_bus: 事件总线实例引用
        param led: LED 驱动实例（由主循环创建后注入）
        param audio: Audio 驱动实例（由主循环创建后注入）
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "alarm"

        # 注入的 Device 引用（可为 None，调用处有 None guard）
        self.led = led
        self.audio = audio

        # ======================= cfg：静态配置 =======================
        self.cfg = {
            "alarm_duration_ms": ALARM_DURATION_MS,
            "check_interval_ms": 100,
            "enable_local": ALARM_ENABLE_LOCAL,
        }

        # ======================= ctx：运行时上下文 =======================
        self.ctx = {
            "is_init": False,
            "last_tick": 0,
            "power_state": POWER_STATE_ACTIVE,
            "alarm_active": False,
            "alarm_type": "",
            "alarm_level": 0,
            "alarm_start": 0,
        }

        # ======================= _data：数据快照 =======================
        self._data = {
            "last_alarm": {},
        }

    def init(self):
        """
        brief 初始化服务：订阅事件 + 重置报警状态
        """
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_COLLISION_DETECTED, self._on_collision)
                self.event_bus.subscribe(EVENT_BUTTON_PRESSED, self._on_button_press)
                self.event_bus.subscribe(EVENT_GPS_LOST, self._on_gps_lost)
                self.event_bus.subscribe(EVENT_BATTERY_LOW, self._on_battery_low)
                self.event_bus.subscribe(EVENT_BATTERY_CRITICAL, self._on_battery_critical)
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)

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
        """
        brief 周期调度：超时检查 + 功耗守卫 + 时间片控制
        note 30s 超时精度 ±100ms，完全满足需求
        """
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["check_interval_ms"]:
            return

        if self.ctx["alarm_active"]:
            if time.ticks_diff(now, self.ctx["alarm_start"]) >= self.cfg["alarm_duration_ms"]:
                self._cancel_alarm()

        self.ctx["last_tick"] = now

    # ==================== 核心方法 ====================

    def _start_alarm(self, alarm_type, level):
        """
        brief 启动报警（所有报警入口统一经过此方法）
        param alarm_type: "collision" / "sos"
        param level: 1-3
        note
            - 同类型且 level<3 → 仅刷新超时计时器
            - Level 3 碰撞 → 升级为 sos
            - SOS 打断碰撞 → 先 cancel 再重启 SOS
        """
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
        """
        brief 取消报警：关闭声光 + 发布取消事件 + 重置状态
        """
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
        """
        brief 外部取消报警（供 ControlService 调用）
        note 公开接口，与 _cancel_alarm 逻辑一致
        """
        self._cancel_alarm()

    # ==================== 事件回调 ====================

    def _on_collision(self, payload):
        """碰撞检测事件回调"""
        level = payload.get("level", 1)
        self._start_alarm("collision", level)

    def _on_button_press(self, payload):
        """
        brief 按键事件回调（双重语义）
        note 空闲时=触发SOS，报警中=取消报警
        """
        if self.ctx["alarm_active"]:
            self._cancel_alarm()
        else:
            self._start_alarm("sos", 3)

    def _on_gps_lost(self, payload):
        """GPS 信号丢失→TTS 语音提示"""
        if self.audio:
            self.audio.play_tts(TTS_GPS_LOST)

    def _on_battery_low(self, payload):
        """低电量事件（stub，待 PowerService 就绪后启用）"""
        pass

    def _on_battery_critical(self, payload):
        """严重低电量事件（stub，待 PowerService 就绪后启用）"""
        pass

    def _on_config_update(self, payload):
        """配置更新回调"""
        if payload.get("target") == self.name:
            if "alarm_duration_ms" in payload:
                self.cfg["alarm_duration_ms"] = int(payload["alarm_duration_ms"])
                print("[%s] alarm_duration_ms → %sms" % (self.name, self.cfg["alarm_duration_ms"]))
            if "enable_local" in payload:
                self.cfg["enable_local"] = bool(payload["enable_local"])
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]

    # ==================== 辅助映射 ====================

    def _level_to_interval(self, level):
        """碰撞等级→LED 闪烁间隔(ms)"""
        return {1: 1000, 2: 500, 3: 200}.get(level, 1000)

    def _level_to_file(self, level):
        """碰撞等级→报警音频文件路径"""
        return {
            1: AUDIO_ALARM_FILE_L1,
            2: AUDIO_ALARM_FILE_L2,
            3: AUDIO_ALARM_FILE_L3,
        }.get(level, AUDIO_ALARM_FILE_L1)

    # ==================== 数据接口 ====================

    def get_data(self):
        """
        brief 获取报警数据快照
        return dict 数据副本
        """
        return {
            "alarm_active": self.ctx["alarm_active"],
            "alarm_type": self.ctx["alarm_type"],
            "alarm_level": self.ctx["alarm_level"],
            "last_alarm": dict(self._data["last_alarm"]),
            "timestamp": time.ticks_ms(),
        }

    def get_status(self):
        """
        brief 获取运行状态
        return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "power_state": self.ctx["power_state"],
            "alarm_active": self.ctx["alarm_active"],
        }
