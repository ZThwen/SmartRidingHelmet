"""
brief 光敏传感器模块集成测试
note 测试 Light 模块在完整系统环境下的工作情况（事件流转、模块协作）
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_SYSTEM_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE
from Drivers.sensor.Light import LightSensorDiver

try:
    from config import EVENT_LIGHT_READY
except ImportError:
    EVENT_LIGHT_READY = "LIGHT_READY"

class IntegrationTest:
    def __init__(self):
        self.event_bus = None
        self.modules = []
        self.test_results = {
            "event_received": False,
            "data_valid": False,
            "event_flow_ok": False,
            "continuous_ok": False
        }
        
    def setup(self):
        """
        brief 搭建集成测试环境
        """
        print("=" * 60)
        print("集成环境测试 - 光敏传感器模块")
        print("=" * 60)
        
        print("\n[步骤 1] 创建事件总线")
        self.event_bus = EventBus()
        self.event_bus.debug = True
        
        print("\n[步骤 2] 订阅系统事件")
        self.event_bus.subscribe(EVENT_SYSTEM_READY, self._on_system_ready)
        self.event_bus.subscribe(EVENT_LIGHT_READY, self._on_light_ready)
        self.event_bus.subscribe(EVENT_SENSOR_ERROR, self._on_sensor_error)
        print("  ✓ 已订阅: SYSTEM_READY, LIGHT_READY, SENSOR_ERROR")
        
        print("\n[步骤 3] 创建模块实例")
        light_sensor = LightSensorDiver(self.event_bus)
        self.modules.append(light_sensor)
        print(f"  ✓ 已创建: {light_sensor.name}")
        
    def _on_system_ready(self, payload):
        """
        brief 系统就绪事件回调
        """
        print(f"\n[事件回调] SYSTEM_READY")
        print(f"  模块数量: {payload['modules_count']}")
        
    def _on_light_ready(self, payload):
        """
        brief 光敏传感器数据就绪事件回调
        """
        self.test_results["event_received"] = True
        self.test_results["data_valid"] = payload["valid"]
        
        print(f"\n[事件回调] LIGHT_READY")
        print(f"  光照强度: {payload['light_intensity']}")
        print(f"  有效性: {payload['valid']}")
        print(f"  时间戳: {payload['timestamp']}")
        
    def _on_sensor_error(self, payload):
        """
        brief 传感器错误事件回调
        """
        print(f"\n[事件回调] SENSOR_ERROR")
        print(f"  来源: {payload.get('source', 'N/A')}")
        print(f"  错误信息: {payload.get('error', 'N/A')}")
        
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
        
        self.event_bus.publish(EVENT_SYSTEM_READY, {"modules_count": len(self.modules)})
        print(f"\n✅ 系统就绪，共启动 {len(self.modules)} 个模块")
        
    def test_event_flow(self):
        """
        brief 测试事件流转
        """
        print("\n" + "-" * 60)
        print("[测试 1] 事件流转测试")
        print("-" * 60)
        
        print("\n运行主循环 10 秒...")
        start_time = time.time()
        duration = 10
        
        while time.time() - start_time < duration:
            for mod in self.modules:
                mod.tick()
            
            self.event_bus.pump()
            time.sleep(0.01)
        
        if self.test_results["event_received"]:
            print("\n✓ 事件流转正常")
            self.test_results["event_flow_ok"] = True
        else:
            print("\n✗ 未接收到光照传感器事件")
            
    def test_config_update(self):
        """
        brief 测试动态配置更新
        """
        print("\n" + "-" * 60)
        print("[测试 2] 配置更新测试")
        print("-" * 60)
        
        print("\n发布配置更新事件: 采样间隔 -> 1000ms")
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "target": "light_Sensor",
            "sample_ms": 1000
        })
        
        self.event_bus.pump()
        time.sleep(0.1)
        
        light = self.modules[0]
        if light.cfg["sample_ms"] == 1000:
            print("✓ 配置更新成功")
        else:
            print("✗ 配置更新失败")
            
    def test_continuous_sampling(self):
        """
        brief 测试连续采样
        """
        print("\n" + "-" * 60)
        print("[测试 3] 连续采样测试")
        print("-" * 60)
        
        print("\n连续采样 5 次...")
        count = 0
        start_time = time.time()
        
        while count < 5 and time.time() - start_time < 15:
            for mod in self.modules:
                mod.tick()
            self.event_bus.pump()
            
            if self.test_results["data_valid"]:
                count += 1
                self.test_results["data_valid"] = False
                
            time.sleep(0.01)
            
        if count >= 5:
            self.test_results["continuous_ok"] = True
            print(f"\n✓ 成功采样 {count} 次")
        else:
            print(f"\n✗ 采样不足，仅 {count} 次")
        
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
            print(f"    err_count: {status['err_count']}")
            
        print("\n测试结果:")
        print(f"  事件接收: {'✓' if self.test_results['event_received'] else '✗'}")
        print(f"  事件流转: {'✓' if self.test_results['event_flow_ok'] else '✗'}")
        print(f"  配置更新: {'✓' if self.test_results['continuous_ok'] else '✗'}")
        
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
            self.setup()
            self.init_modules()
            
            self.test_event_flow()
            self.test_config_update()
            self.test_continuous_sampling()
            
            self.print_summary()
            
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test = IntegrationTest()
    test.run()
