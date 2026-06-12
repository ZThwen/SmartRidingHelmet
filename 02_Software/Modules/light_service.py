"""
brief 自适应灯光服务模块
note Service层业务逻辑，根据环境光照自动调节LED亮度
      需求：
      1. 白天（环境亮）→ 灯不开
      2. 下午/晚上（环境暗）→ 灯自动亮起
      3. 天越暗 → 灯越亮

      GL5528光敏电阻特性：
      - 光照强 → 电阻小 → ADC值小
      - 光照弱 → 电阻大 → ADC值大
"""
import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_LIGHT_READY, EVENT_LIGHT_CONTROL, EVENT_CONFIG_UPDATE, POWER_STATE_ACTIVE,
    LIGHT_DAY_ADC_THRESHOLD, LIGHT_NIGHT_ADC_THRESHOLD,
    LIGHT_BRIGHTNESS_MIN, LIGHT_BRIGHTNESS_MAX,
    LIGHT_GAMMA, LIGHT_BRIGHTNESS_THRESHOLD, LIGHT_DEBOUNCE_MS
)


class LightService(BaseModule):

    def __init__(self, event_bus=None, pwm_led=None):
        """
        brief 初始化自适应灯光服务实例
        param event_bus: 事件总线实例引用
        param pwm_led: PWM LED驱动实例引用
        """
        super().__init__()
        self.event_bus = event_bus
        self.pwm_led = pwm_led
        self.name = "light_service"

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "light_day_threshold": LIGHT_DAY_ADC_THRESHOLD,      # 白天阈值（ADC）
            "light_night_threshold": LIGHT_NIGHT_ADC_THRESHOLD,  # 晚上阈值（ADC）
            "brightness_min": LIGHT_BRIGHTNESS_MIN,              # 最小亮度（%）
            "brightness_max": LIGHT_BRIGHTNESS_MAX,              # 最大亮度（%）
            "gamma": LIGHT_GAMMA,                                # 非线性映射参数
            "brightness_threshold": LIGHT_BRIGHTNESS_THRESHOLD,  # 亮度变化阈值
            "debounce_ms": LIGHT_DEBOUNCE_MS,                    # 防抖间隔（ms）
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,                    # 初始化完成标志
            "power_state": POWER_STATE_ACTIVE,   # 功耗状态
            "auto_mode": True,                   # 自动调节模式
            "manual_brightness": 50,             # 手动亮度值
            "last_brightness": 0,                # 上次设置的亮度
            "last_update_tick": 0,               # 上次更新时间戳（防抖）
            "err_count": 0,                      # 错误计数
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "current_brightness": 0,   # 当前亮度
            "light_intensity": 0,      # 当前光照强度
            "mode": "auto",            # 当前模式
            "light_level": "unknown",  # 光照等级（day/transition/night）
        }

    def init(self):
        """
        brief 初始化服务：订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_LIGHT_READY, self._on_light_ready)
                self.event_bus.subscribe(EVENT_LIGHT_CONTROL, self._on_light_control)
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)

            self.ctx["is_init"] = True
            print("[{}] OK init | auto_mode={}".format(self.name, self.ctx["auto_mode"]))

        except Exception as e:
            print("[{}] FAIL init: {}".format(self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：Service层不需要周期调度
        note 事件驱动，tick()为空实现
        """
        pass

    def _on_light_control(self, payload):
        """
        brief 灯光控制指令回调（来自 ControlService）
        param payload: {cmd: "on"/"off"/"auto"/"brightness_up"/"brightness_down"}
        """
        cmd = payload.get("cmd", "")
        if cmd == "on":
            self.set_manual_brightness(50)
        elif cmd == "off":
            self.set_manual_brightness(0)
        elif cmd == "auto":
            self.set_auto_mode()
        elif cmd == "brightness_up":
            current = self._data.get("current_brightness", 0)
            self.set_manual_brightness(min(current + 10, 100))
        elif cmd == "brightness_down":
            current = self._data.get("current_brightness", 0)
            self.set_manual_brightness(max(current - 10, 0))

    def _on_light_ready(self, payload):
        """
        brief 光照数据就绪回调
        param payload: 光照数据 {light_intensity, valid, timestamp}
        note 根据光照强度计算目标亮度，调用PWM LED接口
        """
        if not self.ctx["is_init"]:
            return

        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        if not self.ctx["auto_mode"]:
            return

        if not payload.get("valid", False):
            return

        light_intensity = payload.get("light_intensity", 0)
        self._data["light_intensity"] = light_intensity

        target_brightness, light_level = self._calculate_brightness(light_intensity)
        self._data["light_level"] = light_level

        # 亮度变化阈值检查
        brightness_diff = abs(target_brightness - self.ctx["last_brightness"])
        if brightness_diff < self.cfg["brightness_threshold"]:
            return

        # 防抖检查
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_update_tick"]) < self.cfg["debounce_ms"]:
            return

        # 调用 PWM LED 驱动
        if self.pwm_led:
            try:
                self.pwm_led.set_brightness(target_brightness)
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[{}] pwm_led error ({}): {}".format(
                    self.name, self.ctx["err_count"], e))
                return

        self.ctx["last_brightness"] = target_brightness
        self.ctx["last_update_tick"] = now
        self._data["current_brightness"] = target_brightness

        print("[{}] light={} ({}), brightness={}%, level={}".format(
            self.name, light_intensity, light_level, target_brightness, light_level))

    def _calculate_brightness(self, light_intensity):
        """
        brief 根据光照强度计算目标亮度
        param light_intensity: 光照强度（ADC值）
        return (int, str) (目标亮度, 光照等级)
        note GL5528特性：ADC值大→光照弱，ADC值小→光照强
              逻辑：
              1. ADC值小（光照强）→ 灯不开（brightness=0）
              2. ADC值大（光照弱）→ 灯最亮（brightness=max）
              3. 过渡期 → 线性插值
        """
        light_day = self.cfg["light_day_threshold"]
        light_night = self.cfg["light_night_threshold"]
        brightness_min = self.cfg["brightness_min"]
        brightness_max = self.cfg["brightness_max"]
        gamma = self.cfg["gamma"]

        if light_intensity <= light_day:
            return (0, "day")

        if light_intensity >= light_night:
            normalized = 1.0
            brightness = brightness_min + (brightness_max - brightness_min) * pow(normalized, gamma)
            return (int(brightness), "night")

        normalized = (light_intensity - light_day) / (light_night - light_day)
        brightness = brightness_min + (brightness_max - brightness_min) * pow(normalized, gamma)

        if brightness < brightness_min:
            brightness = brightness_min
        elif brightness > brightness_max:
            brightness = brightness_max

        return (int(brightness), "transition")

    def set_manual_brightness(self, duty_cycle):
        """
        brief 手动设置亮度（覆盖自动调节）
        param duty_cycle: 占空比（0-100）
        note 切换到手动模式，立即设置亮度
        """
        if not self.ctx["is_init"]:
            return

        if duty_cycle < 0:
            duty_cycle = 0
        elif duty_cycle > 100:
            duty_cycle = 100

        self.ctx["auto_mode"] = False
        self.ctx["manual_brightness"] = duty_cycle
        self._data["mode"] = "manual"

        if self.pwm_led:
            try:
                self.pwm_led.set_brightness(duty_cycle)
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[{}] manual set error ({}): {}".format(
                    self.name, self.ctx["err_count"], e))
                return

        self._data["current_brightness"] = duty_cycle
        self.ctx["last_brightness"] = duty_cycle

        print("[{}] manual mode, brightness={}".format(self.name, duty_cycle))

    def set_auto_mode(self):
        """
        brief 恢复自动调节模式
        note 切换回自动模式，根据当前光照调节亮度
        """
        if not self.ctx["is_init"]:
            return

        self.ctx["auto_mode"] = True
        self._data["mode"] = "auto"

        print("[{}] auto mode enabled".format(self.name))

    def get_mode(self):
        """
        brief 获取当前模式
        return str "auto" 或 "manual"
        """
        return self._data["mode"]

    def _on_config_update(self, payload):
        """
        brief 配置更新回调处理
        param payload: 配置事件负载
        """
        if payload.get("target") == self.name:
            if "light_day_threshold" in payload:
                self.cfg["light_day_threshold"] = int(payload["light_day_threshold"])
            if "light_night_threshold" in payload:
                self.cfg["light_night_threshold"] = int(payload["light_night_threshold"])
            if "brightness_min" in payload:
                self.cfg["brightness_min"] = int(payload["brightness_min"])
            if "brightness_max" in payload:
                self.cfg["brightness_max"] = int(payload["brightness_max"])
            if "gamma" in payload:
                self.cfg["gamma"] = float(payload["gamma"])
            if "brightness_threshold" in payload:
                self.cfg["brightness_threshold"] = int(payload["brightness_threshold"])
            if "debounce_ms" in payload:
                self.cfg["debounce_ms"] = int(payload["debounce_ms"])

            print("[{}] config updated".format(self.name))

        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[{}] power: {} -> {}".format(self.name, old_state, payload["power_state"]))

    def get_data(self):
        """
        brief 获取当前亮度数据快照
        return dict {current_brightness, light_intensity, mode, light_level, timestamp}
        """
        return {
            "current_brightness": self._data["current_brightness"],
            "light_intensity": self._data["light_intensity"],
            "mode": self._data["mode"],
            "light_level": self._data["light_level"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        """
        brief 查询模块运行状态快照
        return dict {is_init, auto_mode, power_state, err_count}
        """
        return {
            "is_init": self.ctx["is_init"],
            "auto_mode": self.ctx["auto_mode"],
            "power_state": self.ctx["power_state"],
            "err_count": self.ctx["err_count"],
            "last_brightness": self.ctx["last_brightness"]
        }
