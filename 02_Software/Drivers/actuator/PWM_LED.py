"""
brief PWM调光LED驱动模块
note 严格遵循四元组架构规范，使用PWM控制LED亮度
      Device层纯硬件控制，不包含业务逻辑
      硬件：Arduino D5引脚（STM32 PE11, TIM1_CH2）
      核心功能：输入占空比（0-100），直接控制LED亮度
"""
from pyb import Pin, Timer
import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_PWM_LED_ERROR, EVENT_POWER_STATE_CHANGE,
    PWM_LED_PIN, PWM_LED_TIMER_ID, PWM_LED_TIMER_CHANNEL,
    PWM_LED_FREQ, POWER_STATE_ACTIVE, POWER_STATE_CUSTOM,
    PWM_BLINK_ON_DUTY, PWM_BLINK_INTERVAL_MS,
    LIGHT_BRIGHTNESS_MAX,
)


class PWMLEDDriver(BaseModule):
    
    def __init__(self, event_bus=None):
        """
        brief 初始化PWM LED驱动模块实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "pwm_led"
        
        self.cfg = {
            "pin_name": PWM_LED_PIN,
            "timer_id": PWM_LED_TIMER_ID,
            "timer_channel": PWM_LED_TIMER_CHANNEL,
            "pwm_freq": PWM_LED_FREQ,
            "max_retry": 3,
            "blink_on_duty": PWM_BLINK_ON_DUTY,
            "blink_interval_ms": PWM_BLINK_INTERVAL_MS,
        }
        
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
            "blink_active": False,
            "blink_on": False,
            "blink_from_alarm": False,
            "blink_last_toggle": 0,
        }
        
        self._data = {
            "duty_cycle": 0,
            "valid": True,
        }
        
        self.led_pin = None
        self.pwm_timer = None
        self.pwm_channel = None
    
    def init(self):
        """
        brief 初始化PWM硬件并订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            self.led_pin = Pin(
                self.cfg["pin_name"],
                Pin.OUT,
                Pin.PULL_NONE
            )
            
            self.pwm_timer = Timer(self.cfg["timer_id"], freq=self.cfg["pwm_freq"])
            
            self.pwm_channel = self.pwm_timer.channel(
                self.cfg["timer_channel"],
                Timer.PWM,
                pin=self.led_pin
            )
            
            self.pwm_channel.pulse_width_percent(0)
            
            if self.event_bus:
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)
            
            self.ctx["is_init"] = True
            print("[{}] OK init | pin={}, timer={}, channel={}, freq={}Hz".format(
                self.name, self.cfg["pin_name"], self.cfg["timer_id"],
                self.cfg["timer_channel"], self.cfg["pwm_freq"]
            ))
            
        except Exception as e:
            print("[{}] FAIL init: {}".format(self.name, e))
            raise
    
    def tick(self):
        """
        brief 闪烁状态机
        note 主循环每轮调用，必须快速返回（<5ms），不能阻塞
        """
        if not self.ctx["blink_active"]:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["blink_last_toggle"]) < self.cfg["blink_interval_ms"]:
            return
        self.ctx["blink_last_toggle"] = now
        self.ctx["blink_on"] = not self.ctx["blink_on"]
        try:
            if self.ctx["blink_on"]:
                self.pwm_channel.pulse_width_percent(self.cfg["blink_on_duty"])
            else:
                self.pwm_channel.pulse_width_percent(0)
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] blink tick err: %s" % (self.name, e))
    
    def set_brightness(self, duty_cycle):
        """
        brief 设置LED亮度（通过PWM占空比）
        param duty_cycle: 占空比（0-100），0=熄灭，100=最亮
        note 直接调用即可调光，无需周期调度
        """
        if not self.ctx["is_init"]:
            return
        
        # 闪烁中拒绝外部亮度设置，防止打架
        if self.ctx.get("blink_active", False):
            return
        
        if self.ctx["power_state"] not in (POWER_STATE_ACTIVE, POWER_STATE_CUSTOM):
            return
        
        if duty_cycle < 0:
            duty_cycle = 0
        elif duty_cycle > LIGHT_BRIGHTNESS_MAX:
            duty_cycle = LIGHT_BRIGHTNESS_MAX
        
        try:
            self.ctx["is_busy"] = True
            
            self.pwm_channel.pulse_width_percent(duty_cycle)
            
            self._data["duty_cycle"] = duty_cycle
            self._data["valid"] = True
            self.ctx["err_count"] = 0
            
        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] set_brightness err ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_PWM_LED_ERROR, {
                        "module": self.name,
                        "error": str(e),
                        "timestamp": time.ticks_ms()
                    })
        finally:
            self.ctx["is_busy"] = False
    
    def start_blink(self, on_duty=None, interval_ms=None, from_alarm=False):
        """
        brief 开始闪烁
        param on_duty: 亮时占空比(%)，默认使用 cfg 配置
        param interval_ms: 闪烁间隔(ms)，默认使用 cfg 配置
        param from_alarm: 是否报警触发（True 时不可被手动指令中断）
        """
        if on_duty is not None:
            self.cfg["blink_on_duty"] = max(0, min(LIGHT_BRIGHTNESS_MAX, on_duty))
        if interval_ms is not None:
            self.cfg["blink_interval_ms"] = max(50, interval_ms)
        self.ctx["blink_active"] = True
        self.ctx["blink_from_alarm"] = from_alarm
        self.ctx["blink_on"] = False
        self.ctx["blink_last_toggle"] = time.ticks_ms()
        print("[%s] blink start (duty=%d, interval=%d, alarm=%s)" % (
            self.name, self.cfg["blink_on_duty"], self.cfg["blink_interval_ms"], from_alarm))
    
    def stop_blink(self):
        """brief 停止闪烁，熄灭LED"""
        was_active = self.ctx["blink_active"]
        self.ctx["blink_active"] = False
        self.ctx["blink_from_alarm"] = False
        if was_active:
            self.pwm_channel.pulse_width_percent(0)
            self._data["duty_cycle"] = 0
            print("[%s] blink stopped" % self.name)
    
    def set_blink_duty(self, duty):
        """brief 改变闪烁亮时占空比（闪烁中调用）"""
        duty = max(0, min(LIGHT_BRIGHTNESS_MAX, duty))
        self.cfg["blink_on_duty"] = duty
    
    def is_blink_active(self):
        """brief 查询闪烁状态"""
        return self.ctx.get("blink_active", False)
    
    def is_blink_from_alarm(self):
        """brief 查询是否报警触发的闪烁"""
        return self.ctx.get("blink_from_alarm", False)
    
    def _on_config_update(self, payload):
        """
        brief 配置更新回调
        param payload: 配置更新事件数据
        note 处理功耗状态变化
        """
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            new_state = payload["power_state"]
            print("[{}] power: {} -> {}".format(self.name, old_state, new_state))
            if new_state == POWER_STATE_CUSTOM:
                # CUSTOM: 手动操作覆盖省电模式，不改变亮度
                self.ctx["power_state"] = new_state
            elif new_state != POWER_STATE_ACTIVE:
                # 省电模式：停止手动闪烁，报警闪烁继续
                if self.ctx.get("blink_active") and not self.ctx.get("blink_from_alarm"):
                    self.stop_blink()
                else:
                    self.set_brightness(0)
                self.ctx["power_state"] = new_state
            else:
                self.ctx["power_state"] = new_state
    
    def get_data(self):
        """
        brief 获取PWM LED数据快照（供外部查询）
        return dict 数据副本，包含占空比和时间戳
        """
        return {
            "duty_cycle": self._data["duty_cycle"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }
    
    def get_status(self):
        """
        brief 获取PWM LED运行状态（供外部查询）
        return dict 状态快照，包含初始化状态、错误计数等
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }
    
    def deinit(self):
        """
        brief 反初始化PWM资源
        note 释放Timer和Channel资源
        """
        try:
            if self.pwm_channel:
                self.pwm_channel.pulse_width_percent(0)
            
            if self.pwm_timer:
                self.pwm_timer.deinit()
            
            self.pwm_timer = None
            self.pwm_channel = None
            self.ctx["is_init"] = False
            print("[{}] OK deinit".format(self.name))
            
        except Exception as e:
            print("[{}] deinit err: {}".format(self.name, e))
