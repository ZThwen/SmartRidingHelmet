import time
from core.Base_Module import BaseModule
from core.config import (
    EVENT_IMU_READY, EVENT_COLLISION_DETECTED, EVENT_CONFIG_UPDATE,
    COLLISION_THRESHOLD_SUSPECT, COLLISION_THRESHOLD_LIKELY,
    COLLISION_THRESHOLD_HIGH, COLLISION_THRESHOLD_CONFIRMED,
    COLLISION_WINDOW_SIZE, COLLISION_WINDOW_DURATION_MS,
    COLLISION_PULSE_MIN_WIDTH_MS, COLLISION_PRE_WINDOW_MS,
    COLLISION_FREE_FALL_THRESHOLD, COLLISION_VARIANCE_THRESHOLD,
    COLLISION_PEAK_COUNT_THRESHOLD, COLLISION_COOLDOWN_MS,
    COLLISION_LEVEL1_MAX_G, COLLISION_LEVEL2_MAX_G,
    COLLISION_LEVEL1_MAX_DURATION_MS, COLLISION_LEVEL2_MAX_DURATION_MS,
    POWER_STATE_ACTIVE,
)
G = 9.8
class CollisionService(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "collision"
        self.cfg = {
            "threshold_suspect": COLLISION_THRESHOLD_SUSPECT,
            "threshold_likely": COLLISION_THRESHOLD_LIKELY,
            "threshold_high": COLLISION_THRESHOLD_HIGH,
            "threshold_confirmed": COLLISION_THRESHOLD_CONFIRMED,
            "window_size": COLLISION_WINDOW_SIZE,
            "window_duration_ms": COLLISION_WINDOW_DURATION_MS,
            "pulse_min_width_ms": COLLISION_PULSE_MIN_WIDTH_MS,
            "pre_window_ms": COLLISION_PRE_WINDOW_MS,
            "free_fall_threshold": COLLISION_FREE_FALL_THRESHOLD,
            "variance_threshold": COLLISION_VARIANCE_THRESHOLD,
            "peak_count_threshold": COLLISION_PEAK_COUNT_THRESHOLD,
            "cooldown_ms": COLLISION_COOLDOWN_MS,
            "level1_max_g": COLLISION_LEVEL1_MAX_G,
            "level2_max_g": COLLISION_LEVEL2_MAX_G,
            "level1_max_duration_ms": COLLISION_LEVEL1_MAX_DURATION_MS,
            "level2_max_duration_ms": COLLISION_LEVEL2_MAX_DURATION_MS,
            "check_interval_ms": 100,
            "debug": False,
        }
        self.ctx = {
            "is_init": False,
            "last_tick": 0,
            "power_state": POWER_STATE_ACTIVE,
            "window": [],
            "collision_count": 0,
            "last_collision_ts": 0,
        }
        self._data = {
            "status": "normal",
            "last_peak": 0.0,
            "last_level": 0,
        }
    def init(self):
        try:
            if  self.event_bus:
                self.event_bus.subscribe(EVENT_IMU_READY, self._on_imu_data)
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            self.ctx["window"] = []
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成")
        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise
    def tick(self):
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["check_interval_ms"]:
            return
        self.ctx["last_tick"] = now
    def _on_imu_data(self, payload):
        if not payload.get("valid", False):
            return
        acc_total = payload.get("acc_total", 0.0)
        timestamp = payload.get("timestamp", time.ticks_ms())
        acc_g = acc_total / G
        self._update_window(acc_g, timestamp)
        if acc_g < self.cfg["threshold_suspect"]:
            return
        level = self._detect_collision()
        if level is None:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_collision_ts"]) < self.cfg["cooldown_ms"]:
            return
        self._data["status"] = "collision"
        self._data["last_peak"] = acc_g
        self._data["last_level"] = level
        self.ctx["collision_count"] += 1
        self.ctx["last_collision_ts"] = now
        if self.event_bus:
            self.event_bus.publish(EVENT_COLLISION_DETECTED, {
                "acc_total": round(acc_total, 3),
                "level": level,
                "timestamp": now,
            })
    def _update_window(self, acc_g, timestamp):
        self.ctx["window"].append({"acc_g": acc_g, "timestamp": timestamp})
        cutoff = timestamp - self.cfg["window_duration_ms"]
        self.ctx["window"] = [x for x in self.ctx["window"] if x["timestamp"] >= cutoff]
        if len(self.ctx["window"]) > self.cfg["window_size"] + 2:
            self.ctx["window"] = self.ctx["window"][-(self.cfg["window_size"] + 2):]
    def _detect_collision(self):
        window = self.ctx["window"]
        if len(window) < 3:
            return None
        acc_values = [x["acc_g"] for x in window]
        peak_val = max(acc_values)
        peak_idx = acc_values.index(peak_val)
        if peak_val < self.cfg["threshold_suspect"]:
            return None
        if peak_val > self.cfg["threshold_confirmed"]:
            return 3
        if peak_idx == len(acc_values) - 1:
            return None
        if not self._check_pulse_width(window, peak_idx, peak_val):
            return None
        if self._check_freefall(window, peak_idx):
            return None
        if self._check_oscillation(window, peak_idx):
            return None
        return self._determine_level(peak_val, window, peak_idx)
    def _check_pulse_width(self, window, peak_idx, peak_val):
        suspect = self.cfg["threshold_suspect"]
        left_idx = peak_idx
        while left_idx > 0 and window[left_idx - 1]["acc_g"] >= suspect:
            left_idx -= 1
        right_idx = peak_idx
        while right_idx < len(window) - 1 and window[right_idx + 1]["acc_g"] >= suspect:
            right_idx += 1
        pulse_width = window[right_idx]["timestamp"] - window[left_idx]["timestamp"]
        return pulse_width >= self.cfg["pulse_min_width_ms"]
    def _check_freefall(self, window, peak_idx):
        peak_ts = window[peak_idx]["timestamp"]
        cutoff = peak_ts - self.cfg["pre_window_ms"]
        for x in window:
            if cutoff <= x["timestamp"] < peak_ts:
                if x["acc_g"] < self.cfg["free_fall_threshold"]:
                    return True
        return False
    def _check_oscillation(self, window, peak_idx):
        acc_values = [x["acc_g"] for x in window]
        if len(acc_values) < 2:
            return False
        mean = sum(acc_values) / len(acc_values)
        variance = sum((x - mean) ** 2 for x in acc_values) / len(acc_values)
        if variance < self.cfg["variance_threshold"]:
            return False
        peak_count = 0
        for i in range(1, len(acc_values) - 1):
            if acc_values[i] > acc_values[i - 1] and acc_values[i] >= acc_values[i + 1]:
                peak_count += 1
        return peak_count >= self.cfg["peak_count_threshold"]
    def _determine_level(self, peak_val, window, peak_idx):
        start_ts = window[0]["timestamp"]
        end_ts = window[-1]["timestamp"]
        duration = end_ts - start_ts
        if peak_val <= self.cfg["level1_max_g"] or duration <= self.cfg["level1_max_duration_ms"]:
            return 1
        if peak_val <= self.cfg["level2_max_g"] or duration <= self.cfg["level2_max_duration_ms"]:
            return 2
        return 3
    def _on_config_update(self, payload):
        if payload.get("target") in (self.name, "", None):
            for key in self.cfg:
                if key in payload:
                    self.cfg[key] = type(self.cfg[key])(payload[key])
                    print(f"[{self.name}] 配置更新: {key} = {self.cfg[key]}")
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print(f"[{self.name}] 功耗状态: {old_state} -> {payload['power_state']}")
    def get_data(self):
        return {
            "status": self._data["status"],
            "last_peak": self._data["last_peak"],
            "last_level": self._data["last_level"],
            "window_size": len(self.ctx.get("window", [])),
            "timestamp": time.ticks_ms(),
        }
    def get_status(self):
        return {
            "is_init": self.ctx["is_init"],
            "power_state": self.ctx["power_state"],
            "collision_count": self.ctx["collision_count"],
            "last_collision_ts": self.ctx.get("last_collision_ts", 0),
        }