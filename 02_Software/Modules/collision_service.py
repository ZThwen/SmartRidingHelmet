"""
brief 碰撞检测服务 (CollisionService)
note 订阅IMU加速度数据，通过三级判决算法检测真实碰撞，排除骑行颠簸误报
      第一级：物理量纲归一化(m/s² → g)
      第二级：滑动窗口 + 多级阈值初步检测
      第三级：防误报鉴别器(脉冲宽度/失重前兆/振荡判别)
      区分碰撞等级(轻微/中等/严重)，发布碰撞事件供AlarmService联动报警
"""
import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_IMU_READY, EVENT_COLLISION_DETECTED, EVENT_CONFIG_UPDATE, EVENT_POWER_STATE_CHANGE,
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
        """
        brief 初始化碰撞检测服务实例
        param event_bus: 事件总线实例引用
        note 三级判决所需的所有阈值参数从 core.config 读取
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "collision"

        # ======================= cfg：静态配置 =======================
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

        # ======================= ctx：运行时上下文 =======================
        self.ctx = {
            "is_init": False,
            "last_tick": 0,
            "power_state": POWER_STATE_ACTIVE,
            "window": [],
            "collision_count": 0,
            "last_collision_ts": 0,
        }

        # ======================= _data：数据快照 =======================
        self._data = {
            "status": "normal",
            "last_peak": 0.0,
            "last_level": 0,
        }

    def init(self):
        """
        brief 初始化服务：订阅 IMU 数据事件 + 重置滑动窗口
        """
        try:
            if  self.event_bus:
                self.event_bus.subscribe(EVENT_IMU_READY, self._on_imu_data)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)

            self.ctx["window"] = []
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成")

        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """
        brief 周期调度：功耗守卫 + 时间片控制
        note 当前为保留占位，判决逻辑在 _on_imu_data 回调中执行
        """
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["check_interval_ms"]:
            return

        self.ctx["last_tick"] = now

    def _on_imu_data(self, payload):
        """
        brief IMU 加速度数据回调入口
        param payload: {"valid", "acc_total", "timestamp"} 等字段
        note 完成 g 值归一化 → 滑动窗口更新 → 三级判决 → 冷却守卫 → 发布事件
        """
        if not payload.get("valid", False):
            return

        # ====== 第一级：物理量纲归一化 (m/s² → g) ======
        acc_total = payload.get("acc_total", 0.0)
        timestamp = payload.get("timestamp", time.ticks_ms())
        acc_g = acc_total / G

        # ====== 第二级：滑动窗口更新 ======
        self._update_window(acc_g, timestamp)

        if acc_g < self.cfg["threshold_suspect"]:
            return

        # ====== 第三级：防误报鉴别 ======
        level = self._detect_collision()
        if level is None:
            return

        # ====== 冷却守卫：防重复触发 ======
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
        """
        brief 维护滑动窗口（时间窗口 + 数量上限双约束）
        param acc_g: 归一化后的加速度值（单位 g）
        param timestamp: 数据时间戳（ms）
        """
        self.ctx["window"].append({"acc_g": acc_g, "timestamp": timestamp})

        # 按时间窗口裁剪过期数据
        cutoff = timestamp - self.cfg["window_duration_ms"]
        self.ctx["window"] = [x for x in self.ctx["window"] if x["timestamp"] >= cutoff]

        # 按数量上限裁剪
        if len(self.ctx["window"]) > self.cfg["window_size"] + 2:
            self.ctx["window"] = self.ctx["window"][-(self.cfg["window_size"] + 2):]

    def _detect_collision(self):
        """
        brief 三级判决算法核心：峰值判定 → 脉冲宽度 → 失重前兆 → 振荡判别 → 等级映射
        return int（等级 1-3）或 None（非碰撞）
        """
        window = self.ctx["window"]
        if len(window) < 3:
            return None

        acc_values = [x["acc_g"] for x in window]
        peak_val = max(acc_values)
        peak_idx = acc_values.index(peak_val)

        if peak_val < self.cfg["threshold_suspect"]:
            return None

        # 峰值超过确认阈值 → 直接判为严重碰撞
        if peak_val > self.cfg["threshold_confirmed"]:
            return 3

        # 峰值位于窗口末尾 → 未过确认期，暂不判决
        if peak_idx == len(acc_values) - 1:
            return None

        # 脉冲宽度鉴别：排除窄脉冲干扰
        if not self._check_pulse_width(window, peak_idx, peak_val):
            return None

        # 失重前兆检测：碰撞前出现自由落体 → 判为非骑行碰撞
        if self._check_freefall(window, peak_idx):
            return None

        # 振荡判别：排除连续颠簸路段误报
        if self._check_oscillation(window, peak_idx):
            return None

        return self._determine_level(peak_val, window, peak_idx)

    def _check_pulse_width(self, window, peak_idx, peak_val):
        """
        brief 脉冲宽度鉴别：排除窄脉冲干扰（如敲击传感器）
        param window: 滑动窗口数据
        param peak_idx: 峰值索引
        param peak_val: 峰值（g）
        return bool True=有效碰撞脉冲
        """
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
        """
        brief 失重前兆检测：碰撞前出现 <free_fall_threshold 则判为自由落体（SOS 场景）
        param window: 滑动窗口数据
        param peak_idx: 峰值索引
        return bool True=存在失重前兆（非骑行碰撞）
        """
        peak_ts = window[peak_idx]["timestamp"]
        cutoff = peak_ts - self.cfg["pre_window_ms"]
        for x in window:
            if cutoff <= x["timestamp"] < peak_ts:
                if x["acc_g"] < self.cfg["free_fall_threshold"]:
                    return True
        return False

    def _check_oscillation(self, window, peak_idx):
        """
        brief 振荡判别：方差 + 峰值计数排除连续颠簸路段误报
        param window: 滑动窗口数据
        param peak_idx: 峰值索引
        return bool True=振荡特征匹配（判为颠簸非碰撞）
        """
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
        """
        brief 根据峰值和持续时间确定碰撞等级
        param peak_val: 加速度峰值（g）
        param window: 滑动窗口数据
        param peak_idx: 峰值索引
        return int 1（轻微）/ 2（中等）/ 3（严重）
        """
        start_ts = window[0]["timestamp"]
        end_ts = window[-1]["timestamp"]
        duration = end_ts - start_ts

        if peak_val <= self.cfg["level1_max_g"] and duration <= self.cfg["level1_max_duration_ms"]:
            return 1
        if peak_val <= self.cfg["level2_max_g"] and duration <= self.cfg["level2_max_duration_ms"]:
            return 2
        return 3

    def _on_config_update(self, payload):
        """
        brief 配置更新回调
        param payload: 配置事件负载
        note 支持动态更新所有 cfg 键值 + 功耗状态切换
        """
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
        """
        brief 获取碰撞检测数据快照
        return dict 数据副本
        """
        return {
            "status": self._data["status"],
            "last_peak": self._data["last_peak"],
            "last_level": self._data["last_level"],
            "window_size": len(self.ctx.get("window", [])),
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
            "collision_count": self.ctx["collision_count"],
            "last_collision_ts": self.ctx.get("last_collision_ts", 0),
        }