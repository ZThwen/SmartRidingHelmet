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
    EVENT_PWM_LED_ERROR, EVENT_CONFIG_UPDATE,
    PWM_LED_PIN, PWM_LED_TIMER_ID, PWM_LED_TIMER_CHANNEL,
    PWM_LED_FREQ, POWER_STATE_ACTIVE
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
        }
        
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
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
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
            
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
        brief 周期调度：PWM模块不需要周期调度，tick()为空实现
        note 主循环每轮调用，必须快速返回（<5ms），不能阻塞
        """
        pass
    
    def set_brightness(self, duty_cycle):
        """
        brief 设置LED亮度（通过PWM占空比）
        param duty_cycle: 占空比（0-100），0=熄灭，100=最亮
        note 直接调用即可调光，无需周期调度
        """
        if not self.ctx["is_init"]:
            return
        
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        
        if duty_cycle < 0:
            duty_cycle = 0
        elif duty_cycle > 100:
            duty_cycle = 100
        
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
    
    def _on_config_update(self, payload):
        """
        brief 配置更新回调
        param payload: 配置更新事件数据
        note 处理功耗状态变化
        """
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[{}] power: {} -> {}".format(self.name, old_state, payload["power_state"]))
            
            if payload["power_state"] != POWER_STATE_ACTIVE:
                self.set_brightness(0)
    
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
