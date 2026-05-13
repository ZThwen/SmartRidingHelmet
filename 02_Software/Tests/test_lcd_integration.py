"""
brief LCD模块集成测试
note 测试LCD模块在完整系统环境下的工作情况（事件流转、配置更新、模块协作、翻转、图片显示）
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_SYSTEM_READY, EVENT_LCD_ERROR, EVENT_CONFIG_UPDATE
)
from Drivers.actuator.LCD import LCDDriver

try:
    from images import QQ_ICON_40x40
    _has_images = True
except ImportError:
    _has_images = False
    print("[警告] images.py 导入失败，图片集成测试将跳过")

try:
    from images1 import Quectel_Icon_160x20
    _has_images1 = True
except ImportError:
    _has_images1 = False
    print("[警告] images1.py 导入失败，图片集成测试将跳过")


class IntegrationTest:
    def __init__(self):
        self.event_bus = None
        self.modules = []
        self.test_results = {
            "event_received": False,
            "display_ok": False,
            "event_flow_ok": False,
            "config_update_ok": False,
            "continuous_ok": False,
            "rotation_ok": False,
            "image_ok": False
        }
        self.lcd = None

    def setup(self):
        """
        brief 搭建集成测试环境
        """
        print("=" * 60)
        print("系统集成测试 - LCD模块")
        print("=" * 60)

        # ====== 1. 创建事件总线 ======
        print("\n[步骤 1] 创建事件总线")
        self.event_bus = EventBus()
        self.event_bus.debug = True

        # ====== 2. 订阅关键事件 ======
        print("\n[步骤 2] 订阅系统事件")
        self.event_bus.subscribe(EVENT_SYSTEM_READY, self._on_system_ready)
        self.event_bus.subscribe(EVENT_LCD_ERROR, self._on_lcd_error)
        print("  已订阅: SYSTEM_READY, LCD_ERROR")

        # ====== 3. 创建模块实例 ======
        print("\n[步骤 3] 创建模块实例")
        self.lcd = LCDDriver(self.event_bus)
        self.modules.append(self.lcd)
        print("  已创建: {}".format(self.lcd.name))

    def _on_system_ready(self, payload):
        """
        brief 系统就绪事件回调
        """
        print("\n[事件回调] SYSTEM_READY")
        print("  模块数量: {}".format(payload["modules_count"]))

    def _on_lcd_error(self, payload):
        """
        brief LCD错误事件回调
        """
        print("\n[事件回调] LCD_ERROR")
        print("  来源: {}".format(payload["source"]))
        print("  错误码: {}".format(payload["code"]))
        print("  错误信息: {}".format(payload["error"]))

    def init_modules(self):
        """
        brief 初始化所有模块
        """
        print("\n[步骤 4] 初始化模块")
        for mod in self.modules:
            try:
                print("  -> 初始化 {}...".format(mod.name))
                mod.init()
                print("  {} 初始化成功".format(mod.name))
            except Exception as e:
                print("  {} 初始化失败: {}".format(mod.name, e))
                raise

        # 发布系统就绪事件
        self.event_bus.publish(EVENT_SYSTEM_READY, {"modules_count": len(self.modules)})
        print("\n系统就绪，共启动 {} 个模块".format(len(self.modules)))

    def test_event_flow(self):
        """
        brief 测试事件流转与显示功能
        """
        print("\n" + "-" * 60)
        print("[测试 1] 事件流转与显示功能测试")
        print("-" * 60)

        print("\n运行主循环 10 秒，交替显示正常数据和报警画面...")
        start_time = time.time()
        duration = 10
        cycle = 0

        while time.time() - start_time < duration:
            for mod in self.modules:
                mod.tick()
            self.event_bus.pump()

            # 模拟Service层调用LCD接口
            if cycle % 20 == 0:
                self.lcd.show_normal_data(
                    25.0 + cycle * 0.1,
                    65.0 + cycle * 0.5,
                    31.2304,
                    121.4737
                )
            elif cycle % 20 == 10:
                if cycle % 40 == 10:
                    self.lcd.show_alarm("collision")
                else:
                    self.lcd.show_alarm("sos")

            cycle += 1
            time.sleep(0.01)

        # 检查最终数据
        data = self.lcd.get_data()
        if data["valid"]:
            self.test_results["display_ok"] = True
            self.test_results["event_received"] = True
            self.test_results["event_flow_ok"] = True
            print("\n事件流转正常，LCD显示功能正常")
        else:
            print("\nLCD显示功能异常")

    def test_config_update(self):
        """
        brief 测试动态配置更新
        """
        print("\n" + "-" * 60)
        print("[测试 2] 配置更新测试")
        print("-" * 60)

        # 2.1 刷新间隔更新
        print("\n发布配置更新事件: 刷新间隔 -> 5000ms")
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "target": "lcd",
            "sample_ms": 5000
        })
        self.event_bus.pump()
        time.sleep(0.1)

        if self.lcd.cfg["sample_ms"] == 5000:
            print("  ✓ 刷新间隔配置更新成功")
        else:
            print("  ✗ 刷新间隔配置更新失败")

        # 2.2 功耗状态更新
        print("\n发布配置更新事件: 功耗状态 -> SUSPENDED")
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "power_state": "SUSPENDED"
        })
        self.event_bus.pump()
        time.sleep(0.1)

        status = self.lcd.get_status()
        if status["power_state"] == "SUSPENDED":
            print("  ✓ 功耗状态更新成功")
        else:
            print("  ✗ 功耗状态更新失败")

        # 恢复ACTIVE状态
        print("\n恢复功耗状态 -> ACTIVE")
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "power_state": "ACTIVE"
        })
        self.event_bus.pump()
        time.sleep(0.1)

        # 2.3 背光设置
        print("\n测试背光亮度设置...")
        self.lcd.set_backlight(60)
        data = self.lcd.get_data()
        if data["backlight"] == 60:
            print("  ✓ 背光设置成功 (60%)")
            self.test_results["config_update_ok"] = True
        else:
            print("  ✗ 背光设置失败")

        # 恢复默认刷新间隔
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "target": "lcd",
            "sample_ms": 2000
        })
        self.event_bus.pump()

    def test_continuous_display(self):
        """
        brief 测试连续显示切换
        """
        print("\n" + "-" * 60)
        print("[测试 3] 连续显示切换测试")
        print("-" * 60)

        print("\n连续切换显示模式 10 次...")
        success_count = 0
        for i in range(10):
            # 交替测试三种显示模式
            if i % 3 == 0:
                self.lcd.show_normal_data(20.0 + i, 50.0 + i, 31.23, 121.47)
            elif i % 3 == 1:
                self.lcd.show_alarm("collision")
            else:
                self.lcd.clear()

            for mod in self.modules:
                mod.tick()
            self.event_bus.pump()

            data = self.lcd.get_data()
            if data["valid"] or data["display_mode"] == "blank":
                success_count += 1

            time.sleep(0.1)

        if success_count >= 8:
            self.test_results["continuous_ok"] = True
            print("\n成功完成 {} 次显示切换".format(success_count))
        else:
            print("\n显示切换不足，仅 {} 次".format(success_count))

    def test_rotation(self):
        """
        brief 测试翻转（rotation）与事件流转协同
        """
        print("\n" + "-" * 60)
        print("[测试 4] 翻转（rotation）集成测试")
        print("-" * 60)

        rotation_ok = True
        for rot in range(4):
            print("\n测试 rotation={} ...".format(rot))
            try:
                self.lcd.lcd.set_rotation(rot)

                # 翻转后显示正常数据
                self.lcd.show_normal_data(25.3, 65.2, 31.2304, 121.4737)
                for mod in self.modules:
                    mod.tick()
                self.event_bus.pump()

                data = self.lcd.get_data()
                if data["valid"]:
                    print("  ✓ rotation={} 显示+事件流转正常".format(rot))
                else:
                    print("  ✗ rotation={} 显示异常".format(rot))
                    rotation_ok = False

                # 翻转后显示报警画面
                self.lcd.show_alarm("collision")
                for mod in self.modules:
                    mod.tick()
                self.event_bus.pump()

                time.sleep(0.5)
            except Exception as e:
                print("  ✗ rotation={} 异常: {}".format(rot, e))
                rotation_ok = False

        # 恢复默认rotation
        self.lcd.lcd.set_rotation(self.lcd.cfg["rotation"])
        self.lcd.clear()
        time.sleep(0.2)

        if rotation_ok:
            self.test_results["rotation_ok"] = True
            print("\n翻转集成测试通过")
        else:
            print("\n翻转集成测试失败")

    def test_show_image(self):
        """
        brief 测试图片显示与事件总线协同
        """
        print("\n" + "-" * 60)
        print("[测试 5] 图片显示集成测试")
        print("-" * 60)

        image_ok = True

        # 5.1 images.py - QQ图标
        if _has_images:
            print("\n显示 images.py QQ图标 (40x40)...")
            try:
                self.lcd.clear()
                time.sleep(0.1)
                self.lcd.show_image(0, 0, 40, 40, QQ_ICON_40x40)
                for mod in self.modules:
                    mod.tick()
                self.event_bus.pump()

                data = self.lcd.get_data()
                print("  ✓ QQ图标显示+事件流转正常")
                time.sleep(0.8)
            except Exception as e:
                print("  ✗ QQ图标显示异常: {}".format(e))
                image_ok = False
        else:
            print("\n跳过 images.py 导入失败")
            image_ok = False

        # 5.2 images1.py - Quectel图标
        if _has_images1:
            print("\n显示 images1.py Quectel图标 (160x20)...")
            try:
                self.lcd.clear()
                time.sleep(0.1)
                self.lcd.show_image(0, 54, 160, 20, Quectel_Icon_160x20)
                for mod in self.modules:
                    mod.tick()
                self.event_bus.pump()

                data = self.lcd.get_data()
                print("  ✓ Quectel图标显示+事件流转正常")
                time.sleep(0.8)
            except Exception as e:
                print("  ✗ Quectel图标显示异常: {}".format(e))
                image_ok = False
        else:
            print("\n跳过 images1.py 导入失败")
            image_ok = False

        if image_ok:
            self.test_results["image_ok"] = True
            print("\n图片显示集成测试通过")
        else:
            print("\n图片显示集成测试失败（或已跳过）")

    def print_summary(self):
        """
        brief 打印测试总结
        """
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)

        print("\n模块状态:")
        for mod in self.modules:
            status = mod.get_status()
            print("  {}:".format(mod.name))
            print("    is_init: {}".format(status["is_init"]))
            print("    is_busy: {}".format(status["is_busy"]))
            print("    err_count: {}".format(status["err_count"]))
            print("    power_state: {}".format(status["power_state"]))

        print("\n显示数据:")
        data = self.lcd.get_data()
        print("  display_mode: {}".format(data["display_mode"]))
        print("  backlight: {}%".format(data["backlight"]))
        print("  valid: {}".format(data["valid"]))

        print("\n测试结果:")
        print("  事件接收: {}".format("通过" if self.test_results["event_received"] else "失败"))
        print("  显示功能: {}".format("通过" if self.test_results["display_ok"] else "失败"))
        print("  事件流转: {}".format("通过" if self.test_results["event_flow_ok"] else "失败"))
        print("  配置更新: {}".format("通过" if self.test_results["config_update_ok"] else "失败"))
        print("  连续显示: {}".format("通过" if self.test_results["continuous_ok"] else "失败"))
        print("  翻转测试: {}".format("通过" if self.test_results["rotation_ok"] else "失败"))
        print("  图片显示: {}".format("通过" if self.test_results["image_ok"] else "失败"))

        all_ok = (
            self.test_results["event_received"] and
            self.test_results["display_ok"] and
            self.test_results["event_flow_ok"] and
            self.test_results["config_update_ok"] and
            self.test_results["continuous_ok"] and
            self.test_results["rotation_ok"] and
            self.test_results["image_ok"]
        )
        print("\n总体评估: {}".format("测试通过" if all_ok else "测试失败"))
        print("=" * 60)

    def run(self):
        """
        brief 执行集成测试
        """
        try:
            self.setup()
            self.init_modules()
            self.test_event_flow()
            self.test_config_update()
            self.test_continuous_display()
            self.test_rotation()
            self.test_show_image()
            self.print_summary()

        except Exception as e:
            print("\n测试异常: {}".format(e))
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    test = IntegrationTest()
    test.run()
