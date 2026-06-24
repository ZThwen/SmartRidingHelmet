"""
brief 电池电压 ADC 驱动模块
note 严格遵循四元组架构规范，使用ADC采集电池电压
      硬件：电源扩展板锂电池经分压后接 ADC1_IN14 (PC4)
      输出：五档电量（1-5），非百分比
"""
import time
from machine import ADC, Pin

from core.Base_Module import BaseModule
from core.config import (
    EVENT_BATTERY_READY, EVENT_SENSOR_ERROR,
    BATTERY_SAMPLE_MS, BATTERY_ADC_PIN, BATTERY_LEVEL_THRESHOLDS,
    BATTERY_DIVIDER_RATIO,
)


class BatteryDriver(BaseModule):

    def __init__(self, event_bus=None, adc_pin=BATTERY_ADC_PIN):
        super().__init__()
        self.event_bus = event_bus
        self.name = "BATTERY"

        self.cfg = {
            "sample_ms": BATTERY_SAMPLE_MS,
            "max_retry": 3,
            "adc_pin": adc_pin,
        }

        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "sample_count": 0,
            "err_count": 0,
        }

        self._data = {
            "raw": 0,
            "adc_mv": 0,       # ADC 引脚电压（分压后）
            "battery_mv": 0,   # 实际电池电压（分压前）
            "level": 0,
            "valid": False,
        }

    def init(self):
        try:
            self.adc = ADC(Pin(self.cfg["adc_pin"]))
            self.ctx["is_init"] = True
            print("[%s] init OK" % self.name)
        except Exception as e:
            print("[%s] init FAIL: %s" % (self.name, e))
            raise

    def tick(self):
        if not self.ctx["is_init"]:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return

        self.ctx["last_tick"] = now
        self.ctx["is_busy"] = True
        try:
            raw = self.adc.read_u16()
            # ADC 引脚电压 = raw / 65535 * 3300mV（参考电压 3.3V）
            adc_mv = raw * 3300 // 65535
            # 实际电池电压 = ADC 电压 * 分压比
            battery_mv = int(adc_mv * BATTERY_DIVIDER_RATIO)
            level = self._voltage_to_level(adc_mv)

            self.ctx["sample_count"] += 1
            self._data = {
                "raw": raw,
                "adc_mv": adc_mv,
                "battery_mv": battery_mv,
                "level": level,
                "valid": True,
                "sample_count": self.ctx["sample_count"],
            }
            self.ctx["err_count"] = 0

            if self.event_bus:
                self.event_bus.publish(EVENT_BATTERY_READY, self.get_data())

        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[%s] read err (%d): %s" % (self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False

    def _voltage_to_level(self, mv):
        for i, th in enumerate(BATTERY_LEVEL_THRESHOLDS):
            if mv < th:
                return i
        return len(BATTERY_LEVEL_THRESHOLDS)

    def get_data(self):
        d = dict(self._data)
        d["timestamp"] = time.ticks_ms()
        return d

    def get_status(self):
        return dict(self.ctx)
