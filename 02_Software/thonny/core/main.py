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
def main():
    print("🚀 智能骑行头盔系统启动...")
    event_bus = EventBus()
    event_bus.debug = True
    temp_humid = TempHumidDriver(event_bus)
    imu = IMUDriver(event_bus)
    gnss = GNSSDriver(event_bus)
    light = LightSensorDriver(event_bus)
    button = Button(event_bus)
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    lcd = LCDDriver(event_bus)
    collision = CollisionService(event_bus)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    cloud = CloudService(event_bus)
    display = DisplayService(event_bus, lcd_driver=lcd, audio_driver=audio)
    init_order = [temp_humid, imu, gnss, light,
                  button, led, audio, lcd,
                  collision, alarm, cloud, display]
    failed = []
    print("\n[初始化阶段]")
    for mod in init_order:
        try:
            print("  -> 初始化 %s..." % mod.name)
            mod.init()
            print("  ✓ %s 初始化成功" % mod.name)
        except Exception as e:
            print("  ✗ %s 初始化失败: %s — 跳过" % (mod.name, e))
            failed.append(mod)
    success = len(init_order) - len(failed)
    event_bus.publish(EVENT_SYSTEM_READY, {
        "total": len(init_order),
        "success": success,
        "failed": [m.name for m in failed],
    })
    if failed:
        print("\n⚠️ 系统就绪（%s/%s 模块在线）" % (success, len(init_order)))
        print("   离线: %s" % ', '.join(m.name for m in failed))
    else:
        print("\n✅ 系统就绪，%s 个模块在线" % success)
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
                    print("[ERROR] %s.tick(): %s" % (mod.name, e))
            event_bus.pump()
            time.sleep_ms(10)
            loop_count += 1
            if loop_count % 200 == 0:
                print("\n--- 模块数据 (每 2 秒) ---")
                for mod in init_order:
                    if mod.ctx.get("is_init", False):
                        print("  [%s] %s" % (mod.name, mod.get_data()))
    except KeyboardInterrupt:
        print("\n✓ 系统已停止")
if __name__ == "__main__":
    main()
