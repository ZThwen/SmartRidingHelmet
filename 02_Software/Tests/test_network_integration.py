"""
brief 4G网络模块集成测试
note 测试 NetworkDriver 在完整系统环境下的工作情况（事件流转、模块协作）
     验证 模块初始化、配置更新、连接/断开 等功能
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_SYSTEM_READY, EVENT_CONFIG_UPDATE
from Drivers.network.Network import NetworkDriver


class IntegrationTest:
    def __init__(self):
        self.event_bus = None
        self.modules = []
        self.test_results = {
            "init_ok": False,
            "config_update_ok": False,
            "connect_ok": False,
            "disconnect_ok": False,
        }

    def setup(self):
        """搭建集成测试环境"""
        print("=" * 60)
        print("集成环境测试 - 4G网络模块")
        print("=" * 60)

        print("\n[步骤 1] 创建事件总线")
        self.event_bus = EventBus()
        self.event_bus.debug = True

        print("\n[步骤 2] 订阅系统事件")
        self.event_bus.subscribe(EVENT_SYSTEM_READY, self._on_system_ready)
        self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
        print("  ✓ 已订阅: SYSTEM_READY, CONFIG_UPDATE")

        print("\n[步骤 3] 创建模块实例")
        net = NetworkDriver(self.event_bus)
        self.modules.append(net)
        print(f"  ✓ 已创建: {net.name}")

    # ==================== 事件回调 ====================
    def _on_system_ready(self, payload):
        print(f"\n[事件回调] SYSTEM_READY")
        print(f"  模块数量: {payload['modules_count']}")

    def _on_config_update(self, payload):
        print(f"\n[事件回调] CONFIG_UPDATE")
        print(f"  target: {payload.get('target')}")
        print(f"  connect_timeout_ms: {payload.get('connect_timeout_ms')}")

    def init_modules(self):
        """初始化所有模块"""
        print("\n[步骤 4] 初始化模块")
        for mod in self.modules:
            try:
                print(f"  -> 初始化 {mod.name}...")
                mod.init()
                print(f"  ✓ {mod.name} 初始化成功")
                self.test_results["init_ok"] = True
            except Exception as e:
                print(f"  ✗ {mod.name} 初始化失败: {e}")
                raise

        self.event_bus.publish(EVENT_SYSTEM_READY, {"modules_count": len(self.modules)})
        print(f"\n✅ 系统就绪，共启动 {len(self.modules)} 个模块")

    # ==================== 测试用例 ====================
    def test_config_update(self):
        """测试通过 EventBus 动态配置更新"""
        print("\n" + "-" * 60)
        print("[测试 1] 配置更新测试")
        print("-" * 60)

        net = self.modules[0]
        print(f"\n  更新前 timeout: {net.cfg['connect_timeout_ms']}ms")

        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "target": "network",
            "connect_timeout_ms": 45000
        })
        self.event_bus.pump()
        time.sleep_ms(100)

        print(f"  更新后 timeout: {net.cfg['connect_timeout_ms']}ms")
        if net.cfg["connect_timeout_ms"] == 45000:
            print("  ✓ 配置更新成功")
            self.test_results["config_update_ok"] = True
        else:
            print("  ✗ 配置更新失败")

    def test_connect_disconnect(self):
        """测试 4G 连接与断开"""
        print("\n" + "-" * 60)
        print("[测试 2] 4G 连接/断开测试")
        print("-" * 60)

        net = self.modules[0]

        print("  正在连接 4G 网络（超时 60 秒）...")
        connected = net.connect()
        self.test_results["connect_ok"] = connected

        if connected:
            print("  ✓ 4G 连接成功")
            data = net.get_data()
            status = net.get_status()
            print(f"  net_state: {status['net_state']}")
            print(f"  valid:     {data['valid']}")
        else:
            print("  ✗ 4G 连接失败")
            return

        print("\n  断开 4G 网络...")
        result = net.disconnect()
        status = net.get_status()
        self.test_results["disconnect_ok"] = result and status["net_state"] == "disconnected"
        print(f"  disconnect(): {'✓' if result else '✗'}")
        print(f"  断开后状态: {status['net_state']}")
        print(f"  {'✓ 断开成功' if self.test_results['disconnect_ok'] else '✗ 断开异常'}")

    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)

        print("\n模块最终状态:")
        for mod in self.modules:
            status = mod.get_status()
            print(f"  {mod.name}:")
            print(f"    is_init:    {status['is_init']}")
            print(f"    err_count:  {status['err_count']}")
            print(f"    net_state:  {status['net_state']}")

        print("\n测试结果:")
        results = [
            ("模块初始化",   self.test_results["init_ok"]),
            ("配置更新",     self.test_results["config_update_ok"]),
            ("4G 连接",     self.test_results["connect_ok"]),
            ("断开连接",     self.test_results["disconnect_ok"]),
        ]
        for name, ok in results:
            print(f"  {name}: {'✓' if ok else '✗'}")

        all_ok = all(v for v in self.test_results.values())
        print(f"\n总体评估: {'✅ 测试通过' if all_ok else '❌ 测试失败'}")
        print("=" * 60)

    def run(self):
        """执行集成测试"""
        try:
            self.setup()
            self.init_modules()
            self.test_config_update()
            self.test_connect_disconnect()
            self.print_summary()
        except Exception as e:
            print(f"\n❌ 测试异常终止: {e}")
            raise


if __name__ == "__main__":
    test = IntegrationTest()
    test.run()
