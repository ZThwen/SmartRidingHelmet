"""
brief LED模块集成测试
note 测试LED模块在完整系统环境下的工作情况（事件流转、报警联动、配置更新、功耗切换）
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from config import (
    EVENT_LED_ERROR, EVENT_CONFIG_UPDATE,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED
)
from LED import LEDDriver


class IntegrationTest:
    def __init__(self):
        self.event_bus = None
        self.modules = []
        self.led = None
        self.test_results = {
            "alarm_blink_ok": False,
            "alarm_cancel_ok": False,
            "timer_toggle_ok": False,
            "config_update_ok": False,
            "power_switch_ok": False,
        }

    def setup(self):
        print("=" * 60)
        print("系统集成测试 - LED模块")
        print("=" * 60)

        # ====== 1. 创建事件总线 ======
        print("\n[步骤1] 创建事件总线")
        self.event_bus = EventBus()

        # ====== 2. 订阅关键事件 ======
        print("\n[步骤2] 订阅系统事件")
        self.event_bus.subscribe(EVENT_LED_ERROR, self._on_led_error)
        self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
        self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
        print("  已订阅: LED_ERROR, ALARM_TRIGGERED, ALARM_CANCELED")

        # ====== 3. 创建模块实例 ======
        print("\n[步骤3] 创建模块实例")
        self.led = LEDDriver(self.event_bus)
        self.modules.append(self.led)
        print("  已创建: {}".format(self.led.name))

    def _on_led_error(self, payload):
        print("\n[事件回调] LED_ERROR")
        print("  来源: {}".format(payload.get("source")))
        print("  错误码: {}".format(payload.get("code")))
        print("  错误信息: {}".format(payload.get("error")))

    def _on_alarm_triggered(self, payload):
        print("\n[事件回调] ALARM_TRIGGERED -> LED blink(30000, 200)")
        self.led.blink(30000, 200)

    def _on_alarm_canceled(self, payload):
        print("\n[事件回调] ALARM_CANCELED -> LED off")
        self.led.off()

    def init_modules(self):
        print("\n[步骤4] 初始化模块")
        for mod in self.modules:
            try:
                print("  -> 初始化 {}...".format(mod.name))
                mod.init()
                print("  {} 初始化成功".format(mod.name))
            except Exception as e:
                print("  {} 初始化失败: {}".format(mod.name, e))
                raise

    def test_alarm_blink(self):
        print("\n" + "-" * 60)
        print("[测试1] 报警触发LED闪烁")
        print("-" * 60)

        self.event_bus.publish(EVENT_ALARM_TRIGGERED, {"level": 2})
        self.event_bus.pump()

        status = self.led.get_status()
        data = self.led.get_data()
        if status["blink_mode"] and data["blink_interval"] == 200:
            print("  OK ALARM_TRIGGERED -> blink(30000,200)")
            self.test_results["alarm_blink_ok"] = True
        else:
            print("  FAIL 报警触发闪烁失败")

        print("  等待2秒观察Timer驱动闪烁...")
        time.sleep(2)

    def test_alarm_cancel(self):
        print("\n" + "-" * 60)
        print("[测试2] 取消报警LED熄灭")
        print("-" * 60)

        self.event_bus.publish(EVENT_ALARM_CANCELED, {})
        self.event_bus.pump()

        data = self.led.get_data()
        status = self.led.get_status()
        if data["state"] == "off" and not status["blink_mode"]:
            print("  OK ALARM_CANCELED -> LED off, blink stopped")
            self.test_results["alarm_cancel_ok"] = True
        else:
            print("  FAIL 取消报警失败")

    def test_timer_toggle(self):
        print("\n" + "-" * 60)
        print("[测试3] Timer回调翻转LED")
        print("-" * 60)

        self.led.blink(5000, 500)
        data = self.led.get_data()
        if data["state"] == "on":
            print("  OK 闪烁启动: state=on")
        else:
            print("  FAIL 闪烁启动异常")

        print("  等待1.5秒观察翻转...")
        time.sleep(1.5)

        data = self.led.get_data()
        if data["valid"]:
            print("  OK Timer翻转正常, 当前state={}".format(data["state"]))
            self.test_results["timer_toggle_ok"] = True
        else:
            print("  FAIL Timer翻转异常")

        self.led.off()

    def test_config_update(self):
        print("\n" + "-" * 60)
        print("[测试4] 配置更新测试")
        print("-" * 60)

        print("\n发布配置更新事件: 功耗 -> SUSPENDED")
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {"power_state": POWER_STATE_SUSPENDED})
        self.event_bus.pump()
        time.sleep(0.1)

        status = self.led.get_status()
        if status["power_state"] == POWER_STATE_SUSPENDED:
            print("  OK 功耗状态更新为SUSPENDED")
            self.test_results["config_update_ok"] = True
        else:
            print("  FAIL 功耗状态更新失败")

        print("\n恢复功耗 -> ACTIVE")
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {"power_state": POWER_STATE_ACTIVE})
        self.event_bus.pump()
        time.sleep(0.1)

    def test_power_switch(self):
        print("\n" + "-" * 60)
        print("[测试5] 功耗切换完整流程")
        print("-" * 60)

        self.led.on()
        self.led._on_config_update({"power_state": POWER_STATE_SUSPENDED})
        data = self.led.get_data()
        if data["state"] == "off":
            print("  OK SUSPENDED: LED熄灭")
        else:
            print("  FAIL SUSPENDED异常")

        self.led._on_config_update({"power_state": POWER_STATE_ACTIVE})
        data = self.led.get_data()
        if data["state"] == "on":
            print("  OK ACTIVE: LED恢复亮")
            self.test_results["power_switch_ok"] = True
        else:
            print("  FAIL ACTIVE恢复异常")

        self.led.off()

    def print_summary(self):
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)

        print("\n模块状态:")
        for mod in self.modules:
            status = mod.get_status()
            print("  {}:".format(mod.name))
            print("    is_init: {}".format(status["is_init"]))
            print("    err_count: {}".format(status["err_count"]))
            print("    power_state: {}".format(status["power_state"]))
            print("    blink_mode: {}".format(status["blink_mode"]))

        print("\n测试结果:")
        for key, val in self.test_results.items():
            print("  {}: {}".format(key, "通过" if val else "失败"))

        all_ok = all(self.test_results.values())
        print("\n总体评估: {}".format("测试通过" if all_ok else "测试失败"))
        print("=" * 60)

    def run(self):
        try:
            self.setup()
            self.init_modules()
            self.test_alarm_blink()
            self.test_alarm_cancel()
            self.test_timer_toggle()
            self.test_config_update()
            self.test_power_switch()
            self.print_summary()
        except Exception as e:
            print("\n测试异常: {}".format(e))
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    test = IntegrationTest()
    test.run()
