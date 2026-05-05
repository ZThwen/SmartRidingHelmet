"""
brief 系统入口与主循环调度
note 简化版架构：直接按顺序初始化模块，使用事件驱动通信
"""
import sys
import time

sys.path.append("..")

from Event_Bus import EventBus
from config import EVENT_SYSTEM_READY

# =================================================================
# 模块导入区（按依赖顺序）
# =================================================================
# from Drivers.sensor.Temp_Humid import TempHumidDriver
# from Drivers.sensor.imu import IMUDriver
# from Modules.collision_service import CollisionService
# from Modules.alarm_service import AlarmService
# from Modules.cloud_service import CloudService

def main():
    """
    brief 系统主函数：创建事件总线、初始化模块、运行主循环
    """
    print("🚀 智能骑行头盔系统启动...")
    
    # 1. 创建事件总线
    event_bus = EventBus()
    event_bus.debug = True  # 开启调试模式
    
    # 2. 创建模块实例（按依赖顺序）
    modules = []
    
    # 驱动层（设备适配）
    # temp_humid = TempHumidDriver(event_bus)
    # imu = IMUDriver(event_bus)
    # modules.extend([temp_humid, imu])
    
    # 业务层（算法/联动/网络）
    # collision = CollisionService(event_bus)
    # alarm = AlarmService(event_bus)
    # cloud = CloudService(event_bus)
    # modules.extend([collision, alarm, cloud])
    
    # 3. 按顺序初始化模块
    print("\n[初始化阶段]")
    for mod in modules:
        try:
            print(f"  -> 初始化 {mod.name}...")
            mod.init()
            print(f"  ✓ {mod.name} 初始化成功")
        except Exception as e:
            print(f"  ✗ {mod.name} 初始化失败: {e}")
            print("⛔ 系统启动失败，已停止")
            return
    
    # 4. 发布系统就绪事件
    event_bus.publish(EVENT_SYSTEM_READY, {"modules_count": len(modules)})
    print(f"\n✅ 系统就绪，共启动 {len(modules)} 个模块")
    
    # 5. 主循环
    print("▶ 进入主循环 (事件驱动)")
    try:
        while True:
            # 周期调度所有模块
            for mod in modules:
                try:
                    mod.tick()
                except Exception as e:
                    print(f"[ERROR] {mod.name}.tick() 异常: {e}")
            
            # 事件泵（处理事件队列）
            event_bus.pump()
            
            # 主循环延时
            time.sleep_ms(10)
            
    except KeyboardInterrupt:
        print("\n✓ 系统已停止")

if __name__ == "__main__":
    main()
