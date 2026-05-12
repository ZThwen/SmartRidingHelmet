"""
brief GNSS模块集成测试
note 测试 GNSSDriver 在完整系统环境下的工作情况（事件流转、模块协作）
     验证 数据采集、状态管理、配置更新、GPS丢失检测 等功能
     室内无定位属于正常情况，测试逻辑已覆盖有定位/无定位两种分支
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (EVENT_SYSTEM_READY, EVENT_GNSS_READY, EVENT_GPS_LOST,
                    EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE)
from Drivers.sensor.GNSS import GNSSDriver, GNSS_STATE_IDLE, GNSS_STATE_SEARCH, GNSS_STATE_FIXED, GNSS_STATE_LOST


class IntegrationTest:
    def __init__(self):
        self.event_bus = None
        self.modules = []
        self.test_results = {
            "init_ok": False,
            "gnss_ready_event_ok": False,
            "gps_lost_detected": False,
            "config_update_ok": False,
            "stop_ok": False
        }
        self.event_log = []

    def setup(self):
        """搭建集成测试环境"""
        print("=" * 60)
        print("集成环境测试 - GNSS定位模块")
        print("=" * 60)

        print("\n[步骤 1] 创建事件总线")
        self.event_bus = EventBus()
        self.event_bus.debug = True

        print("\n[步骤 2] 订阅系统事件")
        self.event_bus.subscribe(EVENT_SYSTEM_READY, self._on_system_ready)
        self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss_ready)
        self.event_bus.subscribe(EVENT_GPS_LOST, self._on_gps_lost)
        self.event_bus.subscribe(EVENT_SENSOR_ERROR, self._on_sensor_error)
        print("  ✓ 已订阅: SYSTEM_READY, GNSS_READY, GPS_LOST, SENSOR_ERROR")

        print("\n[步骤 3] 创建模块实例")
        gnss = GNSSDriver(self.event_bus)
        self.modules.append(gnss)
        print(f"  ✓ 已创建: {gnss.name}")

    # ==================== 事件回调 ====================
    def _on_system_ready(self, payload):
        print(f"\n[事件回调] SYSTEM_READY")
        print(f"  模块数量: {payload['modules_count']}")

    def _on_gnss_ready(self, payload):
        self.event_log.append(("GNSS_READY", payload))
        print(f"\n[事件回调] GNSS_READY")
        print(f"  经度: {payload['longitude']:.4f}")
        print(f"  纬度: {payload['latitude']:.4f}")
        print(f"  有效: {payload['valid']}")
        self.test_results["gnss_ready_event_ok"] = True

    def _on_gps_lost(self, payload):
        self.event_log.append(("GPS_LOST", payload))
        print(f"\n[事件回调] GPS_LOST")
        print(f"  来源: {payload.get('source')}")
        self.test_results["gps_lost_detected"] = True

    def _on_sensor_error(self, payload):
        self.event_log.append(("SENSOR_ERROR", payload))
        print(f"\n[事件回调] SENSOR_ERROR")
        print(f"  来源: {payload.get('source')}")
        print(f"  错误: {payload.get('error')}")

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
    def test_data_collection(self):
        """测试 GNSS 数据采集与事件发布"""
        print("\n" + "-" * 60)
        print("[测试 1] 数据采集与事件发布测试")
        print("-" * 60)
        print("  每 2 秒采集一次，共 5 次")
        print("  note: 室内无定位属于正常情况")

        gnss = self.modules[0]

        for i in range(5):
            print(f"\n  --- 第 {i+1} 次采集 ---")
            for mod in self.modules:
                mod.tick()
            self.event_bus.pump()

            data = gnss.get_data()
            status = gnss.get_status()
            print(f"  定位状态: {status['gnss_state']}")
            print(f"  连续无定位: {status['no_fix_count']} 次")

            if data["valid"]:
                print(f"  经度: {data['longitude']:.4f}")
                print(f"  纬度: {data['latitude']:.4f}")
            else:
                print(f"  暂无定位数据")

            time.sleep(2)

        ready_count = len([e for e in self.event_log if e[0] == "GNSS_READY"])
        print(f"\n  收到 GNSS_READY 事件: {ready_count} 次")

    def test_gps_lost_detection(self):
        """测试 GPS 信号丢失检测（加速验证）"""
        print("\n" + "-" * 60)
        print("[测试 2] GPS 信号丢失检测测试")
        print("-" * 60)
        print("  将 lost_count 临时改为 2 次，快速触发丢失事件")

        gnss = self.modules[0]
        original_lost = gnss.cfg["lost_count"]
        gnss.cfg["lost_count"] = 2

        # 连续触发 tick 但保持在室内（get_location() 返回 None）
        for i in range(3):
            print(f"\n  第 {i+1} 次采集（无定位）")
            for mod in self.modules:
                mod.tick()
            self.event_bus.pump()
            status = gnss.get_status()
            print(f"  状态: {status['gnss_state']} | 无定位计数: {status['no_fix_count']}")
            time.sleep(1)

        # 恢复原配置
        gnss.cfg["lost_count"] = original_lost

        lost_count = len([e for e in self.event_log if e[0] == "GPS_LOST"])
        print(f"\n  收到 GPS_LOST 事件: {lost_count} 次")

    def test_config_update(self):
        """测试动态配置更新"""
        print("\n" + "-" * 60)
        print("[测试 3] 配置更新测试")
        print("-" * 60)

        gnss = self.modules[0]

        print(f"\n  更新前配置:")
        print(f"    sample_ms:  {gnss.cfg['sample_ms']}")
        print(f"    lost_count: {gnss.cfg['lost_count']}")

        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "target": "gnss",
            "sample_ms": 3000,
            "lost_count": 10
        })
        self.event_bus.pump()
        time.sleep_ms(100)

        print(f"\n  更新后配置:")
        print(f"    sample_ms:  {gnss.cfg['sample_ms']}")
        print(f"    lost_count: {gnss.cfg['lost_count']}")

        if gnss.cfg["sample_ms"] == 3000 and gnss.cfg["lost_count"] == 10:
            print("\n  ✓ 配置更新成功")
            self.test_results["config_update_ok"] = True
        else:
            print(f"\n  ✗ 配置更新失败")
            print(f"    期望 sample_ms=3000, 实际={gnss.cfg['sample_ms']}")
            print(f"    期望 lost_count=10, 实际={gnss.cfg['lost_count']}")

    def test_stop(self):
        """测试 GNSS 停止定位"""
        print("\n" + "-" * 60)
        print("[测试 4] GNSS 停止定位测试")
        print("-" * 60)

        gnss = self.modules[0]

        result = gnss.stop()
        status = gnss.get_status()
        print(f"\n  stop(): {'✓' if result else '✗'}")
        print(f"  停止后状态: {status['gnss_state']} (期望: {GNSS_STATE_IDLE})")

        if result and status["gnss_state"] == GNSS_STATE_IDLE:
            self.test_results["stop_ok"] = True
            print("  ✓ GNSS 已正常停止")
        else:
            print("  ✗ 停止异常")

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

        print("\n测试结果:")
        results = [
            ("模块初始化",    self.test_results["init_ok"]),
            ("GNSS数据事件", self.test_results["gnss_ready_event_ok"]),
            ("GPS丢失检测",  self.test_results["gps_lost_detected"]),
            ("配置更新",      self.test_results["config_update_ok"]),
            ("停止定位",      self.test_results["stop_ok"]),
        ]
        for name, ok in results:
            print(f"  {name}: {'✓' if ok else '✗'}")

        # GPS丢失检测在室内正常触发，室外不一定触发
        print(f"\n  注: GNSS数据事件在室外定位成功时才为 ✓")
        print(f"       GPS丢失检测在室内连续无定位时才为 ✓")
        print(f"       ⚠ 若在室外测试且信号良好，丢失检测为 ✗ 属于正常")

        all_ok = all(v for v in self.test_results.values())
        print(f"\n总体评估: {'✅ 测试通过' if all_ok else '❌ 测试失败'}")
        print("=" * 60)

    def run(self):
        """执行集成测试"""
        try:
            self.setup()
            self.init_modules()

            self.test_data_collection()
            self.test_gps_lost_detection()
            self.test_config_update()
            self.test_stop()

            self.print_summary()
        except Exception as e:
            print(f"\n❌ 测试异常终止: {e}")
            raise


if __name__ == "__main__":
    test = IntegrationTest()
    test.run()
