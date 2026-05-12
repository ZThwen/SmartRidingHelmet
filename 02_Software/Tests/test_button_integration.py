"""
brief 按键模块集成测试
note 测试 Button 模块在完整系统环境下的工作情况（事件流转、模块协作）
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from config import (EVENT_SYSTEM_READY, EVENT_BUTTON_PRESSED, EVENT_BUTTON_ERROR,
                    EVENT_CONFIG_UPDATE, POWER_STATE_ACTIVE)
from Button import Button


class ButtonIntegrationTest:
    def __init__(self):
        self.event_bus = None
        self.modules = []
        self.test_results = {
            "event_received": False,
            "event_flow_ok": False,
            "continuous_ok": False,
            "button_press_count": 0
        }
        self.last_event_time = 0

    def setup(self):
        """
        brief 搭建集成测试环境
        """
        print("=" * 60)
        print("系统集成测试 - 按键模块")
        print("=" * 60)

        # 1. 创建事件总线
        print("\n[步骤 1] 创建事件总线")
        self.event_bus = EventBus()
        self.event_bus.debug = True

        # 2. 订阅关键事件
        print("\n[步骤 2] 订阅系统事件")
        self.event_bus.subscribe(EVENT_SYSTEM_READY, self._on_system_ready)
        self.event_bus.subscribe(EVENT_BUTTON_PRESSED, self._on_button_pressed)
        self.event_bus.subscribe(EVENT_BUTTON_ERROR, self._on_button_error)
        print("  ✓ 已订阅: SYSTEM_READY, BUTTON_PRESSED, BUTTON_ERROR")

        # 3. 创建模块实例
        print("\n[步骤 3] 创建模块实例")
        button = Button(self.event_bus)
        self.modules.append(button)
        print(f"  ✓ 已创建: {button.name}")

    def _on_system_ready(self, payload):
        """
        brief 系统就绪事件回调
        """
        print(f"\n[事件回调] SYSTEM_READY")
        print(f"  模块数量: {payload['modules_count']}")

    def _on_button_pressed(self, payload):
        """
        brief 按键按下事件回调
        """
        self.test_results["event_received"] = True
        self.test_results["button_press_count"] += 1
        self.last_event_time = payload["timestamp"]

        print(f"\n[事件回调] EVENT_BUTTON_PRESSED")
        print(f"  来源: {payload.get('source', 'unknown')}")
        print(f"  时间戳: {payload['timestamp']}")
        print(f"  按键次数: {self.test_results['button_press_count']}")

    def _on_button_error(self, payload):
        """
        brief 按键错误事件回调
        """
        print(f"\n[事件回调] BUTTON_ERROR")
        print(f"  来源: {payload.get('source', 'unknown')}")
        print(f"  错误码: {payload.get('code', 'unknown')}")
        print(f"  错误信息: {payload.get('error', 'unknown')}")

    def init_modules(self):
        """
        brief 初始化所有模块
        """
        print("\n[步骤 4] 初始化模块")
        for mod in self.modules:
            try:
                print(f"  -> 初始化 {mod.name}...")
                mod.init()
                print(f"  ✓ {mod.name} 初始化成功")
            except Exception as e:
                print(f"  ✗ {mod.name} 初始化失败: {e}")
                raise

        # 发布系统就绪事件
        self.event_bus.publish(EVENT_SYSTEM_READY, {"modules_count": len(self.modules)})
        print(f"\n✅ 系统就绪，共启动 {len(self.modules)} 个模块")

    def test_event_flow(self):
        """
        brief 测试事件流转
        """
        print("\n" + "-" * 60)
        print("[测试 1] 事件流转测试")
        print("-" * 60)

        # 运行主循环一段时间，等待用户按键
        print("\n运行主循环 15 秒...")
        print("请在这段时间内按下按键，观察事件触发情况")
        start_time = time.time()
        duration = 15

        while time.time() - start_time < duration:
            # 调度所有模块
            for mod in self.modules:
                mod.tick()

            # 事件泵
            self.event_bus.pump()

            # 延时
            time.sleep(0.01)

            # 更新剩余时间显示
            remaining = int(duration - (time.time() - start_time))
            if remaining % 5 == 0:
                print(f"  剩余时间: {remaining} 秒")

        # 验证结果
        if self.test_results["event_received"]:
            print("\n✓ 事件流转正常")
            self.test_results["event_flow_ok"] = True
        else:
            print("\n✗ 未接收到按键事件（请检查硬件连接）")

    def test_config_update(self):
        """
        brief 测试动态配置更新
        """
        print("\n" + "-" * 60)
        print("[测试 2] 配置更新测试")
        print("-" * 60)

        # 发布配置更新事件
        new_debounce = 200
        print(f"\n发布配置更新事件: 防抖时间 -> {new_debounce}ms")
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "target": "button",
            "debounce_ms": new_debounce
        })

        # 处理事件
        self.event_bus.pump()
        time.sleep(0.1)

        # 验证配置是否更新（检查模块是否支持动态配置）
        button = self.modules[0]
        # 注：Button模块当前未实现动态配置接收，这里仅演示框架
        print("  提示: Button模块当前使用默认防抖时间配置")
        print(f"  当前防抖时间: {button.cfg['debounce_ms']} ms")
        print("✓ 配置更新事件已发布（如需动态生效，请在Button模块中订阅CONFIG_UPDATE事件）")

    def test_continuous_stability(self):
        """
        brief 测试连续运行稳定性
        """
        print("\n" + "-" * 60)
        print("[测试 3] 连续运行稳定性测试")
        print("-" * 60)

        print("\n连续运行 20 次tick循环...")
        errors = 0
        start_time = time.time()

        for i in range(20):
            try:
                for mod in self.modules:
                    mod.tick()
                self.event_bus.pump()
                time.sleep(0.1)
            except Exception as e:
                errors += 1
                print(f"  ✗ 第 {i+1} 次循环出错: {e}")

        elapsed = time.time() - start_time
        if errors == 0:
            self.test_results["continuous_ok"] = True
            print(f"\n✓ 连续运行稳定，耗时 {elapsed:.2f} 秒")
        else:
            print(f"\n✗ 运行中出现 {errors} 次错误")

    def test_debounce_effectiveness(self):
        """
        brief 测试防抖效果
        """
        print("\n" + "-" * 60)
        print("[测试 4] 防抖效果测试")
        print("-" * 60)

        print("\n请快速连续按下按键，观察防抖效果...")
        print("等待 10 秒...")

        # 记录测试前的按键次数
        initial_count = self.test_results["button_press_count"]
        start_time = time.time()

        while time.time() - start_time < 10:
            for mod in self.modules:
                mod.tick()
            self.event_bus.pump()
            time.sleep(0.01)

        # 计算有效按键次数
        effective_presses = self.test_results["button_press_count"] - initial_count
        print(f"\n  有效按键次数: {effective_presses}")
        print(f"  防抖时间: {self.modules[0].cfg['debounce_ms']} ms")
        print("✓ 防抖测试完成（实际效果取决于按键操作频率）")

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
            print(f"  {mod.name}:")
            print(f"    is_init: {status['is_init']}")
            print(f"    is_busy: {status['is_busy']}")
            print(f"    err_count: {status['err_count']}")
            print(f"    power_state: {status['power_state']}")

        print("\n测试结果:")
        print(f"  事件接收: {'✓' if self.test_results['event_received'] else '✗'}")
        print(f"  事件流转: {'✓' if self.test_results['event_flow_ok'] else '✗'}")
        print(f"  连续运行: {'✓' if self.test_results['continuous_ok'] else '✗'}")
        print(f"  按键次数: {self.test_results['button_press_count']}")

        all_ok = (self.test_results["event_received"] and
                  self.test_results["event_flow_ok"] and
                  self.test_results["continuous_ok"])
        print(f"\n总体评估: {'✅ 测试通过' if all_ok else '❌ 测试失败'}")
        print("=" * 60)

    def run(self):
        """
        brief 执行集成测试
        """
        try:
            # 搭建环境
            self.setup()
            self.init_modules()

            # 执行测试
            self.test_event_flow()
            self.test_config_update()
            self.test_continuous_stability()
            self.test_debounce_effectiveness()

            # 打印总结
            self.print_summary()

        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    test = ButtonIntegrationTest()
    test.run()