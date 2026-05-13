"""
brief LED驱动模块（GPIO控制 + 硬件定时器驱动闪烁）
note 严格遵循四元组架构规范
      Device层纯硬件控制，不包含业务逻辑
      Service层(AlarmService)调用LED公共接口实现声光报警
      闪烁由硬件定时器(Timer1)驱动，tick()直接pass，不阻塞主循环
      硬件：移远EC200U开发板 LED_BLUE (LD2)，参考 examples/pin.py
      初始化方式：Pin('LED_BLUE', Pin.OUT, Pin.PULL_NONE, value=0)
"""
from machine import Pin, Timer
import time

from core.Base_Module import BaseModule
from config import (
    EVENT_LED_ERROR, EVENT_CONFIG_UPDATE,
    LED_PIN_NAME, LED_BLINK_INTERVAL_MS,
    LED_BLINK_MIN_MS, LED_BLINK_MAX_MS,
    TIMER_ID_LED, POWER_STATE_ACTIVE
)


class LEDDriver(BaseModule):
    
    def __init__(self, event_bus=None):
        """
        brief 初始化LED驱动模块实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus  # 保存事件总线引用
        self.name = "led"           # 模块标识符（必须唯一）

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "pin_name": LED_PIN_NAME,           # LED引脚名称
            "blink_min_ms": LED_BLINK_MIN_MS,   # 闪烁最小间隔(ms)
            "blink_max_ms": LED_BLINK_MAX_MS,   # 闪烁最大间隔(ms)
            "blink_interval_ms": LED_BLINK_INTERVAL_MS,  # 默认闪烁间隔(ms)
            "timer_id": TIMER_ID_LED,           # 定时器ID
            "max_retry": 3,                     # 最大重试次数
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,           # 初始化完成标志
            "is_busy": False,           # 操作中标志（防重入）
            "err_count": 0,             # 错误计数
            "power_state": POWER_STATE_ACTIVE,  # 功耗状态
            "blink_timer": None,        # 闪烁定时器句柄
            "blink_mode": False,        # 闪烁模式标志
            "blink_remaining_ms": 0,    # 剩余闪烁时间(ms)
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "state": "off",             # LED状态: on/off
            "blink_duration": 0,        # 闪烁持续时间(ms)
            "blink_interval": 0,        # 闪烁间隔(ms)
            "valid": True,              # 数据有效性标志
        }

        # 硬件句柄
        self.led_pin = None             # LED引脚实例
        self.blink_timer = None         # 闪烁定时器实例

    def init(self):
        """
        brief 初始化LED硬件并订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        
        实现步骤：
        1. 初始化GPIO引脚为输出模式
        2. 订阅配置更新事件
        3. 设置初始化完成标志
        """
        try:
            # ====== 1. 硬件初始化 ======
            self.led_pin = Pin(
                self.cfg["pin_name"],
                Pin.OUT,
                Pin.PULL_NONE,
                value=0
            )

            # ====== 2. 订阅事件 ======
            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)

            # ====== 3. 设置初始化标志 ======
            self.ctx["is_init"] = True
            print("[{}] OK init | pin={}".format(self.name, self.cfg["pin_name"]))

        except Exception as e:
            print("[{}] FAIL init: {}".format(self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：LED模块主要通过硬件定时器工作，tick()为空实现
        note 主循环每轮调用，必须快速返回（<5ms），不能阻塞
        """
        pass

    def blink(self, duration_ms, interval_ms):
        """
        brief 启动LED闪烁
        param duration_ms: 闪烁持续时间(ms)
        param interval_ms: 闪烁间隔(ms)
        note 闪烁间隔会被限制在 [blink_min_ms, blink_max_ms] 范围内
        """
        if not self.ctx["is_init"]:
            return
        
        # 限制闪烁间隔在有效范围内
        if interval_ms < self.cfg["blink_min_ms"]:
            interval_ms = self.cfg["blink_interval_ms"]
        elif interval_ms > self.cfg["blink_max_ms"]:
            interval_ms = self.cfg["blink_interval_ms"]

        try:
            # 先停止之前的闪烁
            self._stop_blink()

            # 立即点亮LED开始闪烁序列
            self.led_pin.value(1)
            self.blink_timer = Timer(-1)  # 创建新定时器
            self._data["state"] = "on"
            self._data["blink_duration"] = duration_ms
            self._data["blink_interval"] = interval_ms
            self.ctx["blink_mode"] = True
            self.ctx["blink_remaining_ms"] = duration_ms
            self.ctx["blink_timer"] = self.blink_timer
            self._data["valid"] = True
            self.ctx["err_count"] = 0

            # 启动周期性定时器
            self.blink_timer.init(
                period=interval_ms,
                mode=Timer.PERIODIC,
                callback=self._blink_callback
            )

        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] blink start err ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LED_ERROR, self.get_error_data(e))

    def _blink_callback(self, arg):
        """
        brief 闪烁定时器回调函数
        param arg: 定时器参数（未使用）
        note 每次定时触发时切换LED状态，直到剩余时间为0
        """
        try:
            # 递减剩余闪烁时间
            self.ctx["blink_remaining_ms"] -= self._data["blink_interval"]

            # 闪烁时间结束
            if self.ctx["blink_remaining_ms"] <= 0:
                self.led_pin.value(0)
                self._data["state"] = "off"
                self._stop_blink()
                return

            # 切换LED状态
            if self._data["state"] == "on":
                self.led_pin.value(0)
                self._data["state"] = "off"
            else:
                self.led_pin.value(1)
                self._data["state"] = "on"

        except Exception as e:
            print("[{}] blink callback err: {}".format(self.name, e))
            self._stop_blink()

    def on(self):
        """
        brief 点亮LED（常亮模式）
        note 会先停止正在进行的闪烁
        """
        if not self.ctx["is_init"]:
            return
        try:
            # 停止闪烁模式
            self._stop_blink()
            
            # 点亮LED
            self.led_pin.value(1)
            self._data["state"] = "on"
            self._data["blink_duration"] = 0
            self._data["blink_interval"] = 0
            self._data["valid"] = True
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] on err ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LED_ERROR, self.get_error_data(e))

    def off(self):
        """
        brief 熄灭LED
        note 会先停止正在进行的闪烁
        """
        if not self.ctx["is_init"]:
            return
        try:
            # 停止闪烁模式
            self._stop_blink()
            
            # 熄灭LED
            self.led_pin.value(0)
            self._data["state"] = "off"
            self._data["blink_duration"] = 0
            self._data["blink_interval"] = 0
            self._data["valid"] = True
            self.ctx["err_count"] = 0
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] off err ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LED_ERROR, self.get_error_data(e))

    def _stop_blink(self):
        """
        brief 停止闪烁（私有方法）
        note 释放定时器资源，重置闪烁相关状态
        """
        if self.ctx["blink_timer"]:
            try:
                self.ctx["blink_timer"].deinit()
            except Exception:
                pass
        self.blink_timer = None
        self.ctx["blink_timer"] = None
        self.ctx["blink_mode"] = False
        self.ctx["blink_remaining_ms"] = 0

    def _on_config_update(self, payload):
        """
        brief 配置更新回调
        param payload: 配置更新事件数据
        note 处理功耗状态变化，非活动状态下关闭LED
        """
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[{}] power: {} -> {}".format(self.name, old_state, payload["power_state"]))

            # 进入低功耗状态：关闭LED
            if payload["power_state"] != POWER_STATE_ACTIVE:
                self._stop_blink()
                self.led_pin.value(0)
                self._data["state"] = "off"
            # 从低功耗恢复：点亮LED
            elif old_state != POWER_STATE_ACTIVE:
                self.led_pin.value(1)
                self._data["state"] = "on"

    def get_data(self):
        """
        brief 获取LED数据快照（供外部查询）
        return dict 数据副本，包含状态、闪烁参数和时间戳
        """
        return {
            "state": self._data["state"],
            "blink_duration": self._data["blink_duration"],
            "blink_interval": self._data["blink_interval"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        """
        brief 获取LED运行状态（供外部查询）
        return dict 状态快照，包含初始化状态、错误计数等
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "blink_mode": self.ctx["blink_mode"]
        }