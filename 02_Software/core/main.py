"""
brief 智能骑行头盔系统入口 — v1 正式版
note 集成 18 个模块（4 传感器 + 5 执行器 + 6 Service + 3 Network）
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_SYSTEM_READY

from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.sensor.Light import LightSensorDriver

from Drivers.interface.Button import Button
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver

from Modules.collision_service import CollisionService
from Modules.alarm_service import AlarmService
from Modules.cloud_service import CloudService
from Modules.display_service import DisplayService
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.network.BLE import BLE
from Modules.light_service import LightService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.navigation_service import NavigationService


def main():
    """
    brief 系统入口: 18 个模块全集成，v1 正式版
    """
    print("🚀 智能骑行头盔系统启动...")

    # 1. 创建事件总线
    event_bus = EventBus()
    event_bus.debug = True

    # 2. 创建模块实例
    # --- 传感器 ---
    temp_humid = TempHumidDriver(event_bus)
    imu = IMUDriver(event_bus)
    gnss = GNSSDriver(event_bus)
    light = LightSensorDriver(event_bus)

    # --- 执行器 ---
    button = Button(event_bus)
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    lcd = LCDDriver(event_bus)

    # --- 服务（注入 Device 引用）---
    collision = CollisionService(event_bus)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    cloud = CloudService(event_bus)
    display = DisplayService(event_bus, lcd_driver=lcd, audio_driver=audio)

    # --- PWM LED + 自适应灯光 ---
    pwm_led = PWMLEDDriver(event_bus)
    light_svc = LightService(event_bus, pwm_led=pwm_led)

    # --- BLE + 远端控制 + 导航 ---
    ble = BLE(event_bus)
    ble_svc = BLEService(event_bus)
    control = ControlService(event_bus)
    nav = NavigationService(event_bus, lcd_driver=lcd, audio_driver=audio)

    # 3. 按序初始化（传感器 → 执行器 → 服务）
    init_order = [temp_humid, imu, gnss, light,
                  button, led, audio, lcd, pwm_led,
                  collision, alarm, cloud, display,
                  light_svc, ble, ble_svc, control, nav]
    failed = []

    print("\n[初始化阶段]")
    for mod in init_order:
        try:
            print(f"  -> 初始化 {mod.name}...")
            mod.init()
            print(f"  ✓ {mod.name} 初始化成功")
        except Exception as e:
            print(f"  ✗ {mod.name} 初始化失败: {e} — 跳过")
            failed.append(mod)

    # 4. 发布系统就绪事件
    success = len(init_order) - len(failed)
    event_bus.publish(EVENT_SYSTEM_READY, {
        "total": len(init_order),
        "success": success,
        "failed": [m.name for m in failed],
    })

    if failed:
        print(f"\n⚠️ 系统就绪（{success}/{len(init_order)} 模块在线）")
        print(f"   离线: {', '.join(m.name for m in failed)}")
    else:
        print(f"\n✅ 系统就绪，{success} 个模块在线")

    # 5. 主循环
    print("▶ 进入主循环（事件驱动）")
    loop_count = 0
    try:
        while True:
            for mod in init_order:
                if not mod.ctx.get("is_init", False):
                    continue
                try:
                    mod.tick()
                except Exception as e:
                    print(f"[ERROR] {mod.name}.tick(): {e}")

            event_bus.pump()
            time.sleep_ms(10)

            # 每 2 秒打印一次数据快照
            loop_count += 1
            if loop_count % 200 == 0:
                print("\n--- 模块数据 (每 2 秒) ---")
                for mod in init_order:
                    if mod.ctx.get("is_init", False):
                        print(f"  [{mod.name}] {mod.get_data()}")

    except KeyboardInterrupt:
        print("\n✓ 系统已停止")


if __name__ == "__main__":
    main()
