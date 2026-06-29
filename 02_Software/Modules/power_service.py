import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_BATTERY_READY, EVENT_BATTERY_LOW,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_MANUAL_ACTIVITY,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    BATTERY_AUTO_SUSPEND_LEVEL,
    TTS_BATTERY_LOW, PRIORITY_CTRL,
)


class PowerService(BaseModule):

    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "power_service"

        self.cfg = {
            "auto_suspend_level": BATTERY_AUTO_SUSPEND_LEVEL,
            "low_level": 2,
        }

        self.ctx = {
            "is_init": False,
            "err_count": 0,
        }

        self._data = {
            "level": 0,
            "battery_mv": 0,
            "valid": False,
            "power_mode": POWER_STATE_ACTIVE,
            "is_low": False,
            "auto_suspended": False,
        }

        # 手动操作锁定：用户操作后禁止自动省电，直到手动触发 power_save
        self._manual_locked = False
        # 报警状态标志：报警期间不自动省电（报警优先级最高）
        self._alarm_active = False

    def init(self):
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_BATTERY_READY, self._on_battery)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_power_state)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
                self.event_bus.subscribe(EVENT_MANUAL_ACTIVITY, self._on_manual_activity)

            self.ctx["is_init"] = True
            print("[%s] init OK" % self.name)
        except Exception as e:
            print("[%s] init FAIL: %s" % (self.name, e))
            raise

    def tick(self):
        self.ctx["last_hb"] = time.ticks_ms()

    def _on_battery(self, payload):
        if not payload.get("valid", False):
            return

        level = payload.get("level", 0)
        battery_mv = payload.get("battery_mv", 0)
        sample_count = payload.get("sample_count", 0)
        self._data["level"] = level
        self._data["battery_mv"] = battery_mv
        self._data["valid"] = True
        self._data["is_low"] = level <= self.cfg["low_level"]

        # 未接电池保护：ADC 读数过低视为未接电池，不触发省电
        if battery_mv < 1000:
            return

        # 启动宽限期：前3次采样不做省电决策（等待ADC稳定）
        if sample_count < 3:
            return

        # 手动锁定：用户操作过 → 跳过自动省电决策（数据采集照常）
        if self._manual_locked:
            return

        # 低电量自动省电：≤auto_suspend_level 且当前 ACTIVE 且未自动省电过
        # 报警优先级最高：报警期间不自动省电
        if (level <= self.cfg["auto_suspend_level"]
                and not self._data["auto_suspended"]
                and self._data["power_mode"] == POWER_STATE_ACTIVE
                and not self._alarm_active):
            self._data["auto_suspended"] = True
            if self.event_bus:
                self.event_bus.publish(EVENT_POWER_STATE_CHANGE, {
                    "power_state": POWER_STATE_SUSPENDED,
                })
                self.event_bus.publish(EVENT_BATTERY_LOW, {"level": level})
                self.event_bus.publish(EVENT_TTS_REQUEST, {
                    "text": TTS_BATTERY_LOW, "priority": PRIORITY_CTRL,
                })

        # 电量回升 → 自动恢复 ACTIVE
        if level > self.cfg["auto_suspend_level"] and self._data["auto_suspended"]:
            self._data["auto_suspended"] = False
            if self.event_bus:
                self.event_bus.publish(EVENT_POWER_STATE_CHANGE, {
                    "power_state": POWER_STATE_ACTIVE,
                })
            print("[%s] 电量回升，恢复正常模式" % self.name)

    def _on_power_state(self, payload):
        new_mode = payload.get("power_state", POWER_STATE_ACTIVE)
        self._data["power_mode"] = new_mode
        # 用户手动切换到 SUSPENDED → 解锁手动锁定，恢复自动省电
        if new_mode == POWER_STATE_SUSPENDED:
            self._manual_locked = False
        # 用户手动切换到 ACTIVE → 清除自动省电标记
        if new_mode == POWER_STATE_ACTIVE:
            self._data["auto_suspended"] = False

    def _on_alarm_triggered(self, payload):
        """报警触发：标记报警活跃，禁止自动省电"""
        self._alarm_active = True
        print("[%s] alarm active -> auto-suspend blocked" % self.name)

    def _on_alarm_canceled(self, payload):
        """报警取消：解除自动省电封锁"""
        self._alarm_active = False
        print("[%s] alarm canceled -> auto-suspend allowed" % self.name)

    def _on_manual_activity(self, payload):
        """用户手动操作 → 永久锁定，禁止自动省电"""
        if not self._manual_locked:
            self._manual_locked = True
            print("[%s] manual activity detected -> auto-suspend locked" % self.name)

    def get_data(self):
        return dict(self._data)

    def get_status(self):
        return dict(self.ctx)
