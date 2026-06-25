"""
brief 智能骑行头盔系统入口 — v2 Step 7
note 集成 23 个模块（6 传感器 + 6 执行器/接口 + 1 网络 + 1 SMS + 9 Service）
"""
import sys
import time
import gc

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_SYSTEM_READY

from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.sensor.Battery import BatteryDriver
from Drivers.sensor.HeartRate import HeartRateDriver

from Drivers.interface.Button import Button
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver

from Drivers.network.BLE import BLEDriver
from Drivers.network.SMS import SMSDriver
from Drivers.interface.Voice import VoiceDriver

from Modules.collision_service import CollisionService
from Modules.audio_service import AudioService
from Modules.alarm_service import AlarmService
from Modules.display_service import DisplayService
from Modules.light_service import LightService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.navigation_service import NavigationService
from Modules.power_service import PowerService


def main():
    """
    brief 系统入口: 23 个模块全集成，v2 Step 7（新增 BatteryDriver + PowerService + HeartRate + SMS）
    """
    GC_THRESHOLD = 8000  # 内存阈值（bytes）
    GC_CHECK_INTERVAL = 500  # 每 500 次循环检查
    
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
    battery_drv = BatteryDriver(event_bus)
    heart_rate = HeartRateDriver(event_bus)

    # --- 执行器 ---
    button = Button(event_bus)
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    lcd = LCDDriver(event_bus)
    pwm_led = PWMLEDDriver(event_bus)
    ble = BLEDriver(event_bus)
    sms = SMSDriver(event_bus)

    # --- 服务（注入 Device 引用）---
    collision = CollisionService(event_bus)
    audio_svc = AudioService(event_bus, audio_driver=audio)
    alarm = AlarmService(event_bus, led=led, audio=audio, sms=sms)
    display = DisplayService(event_bus, lcd_driver=lcd, audio_driver=audio)
    control_svc = ControlService(event_bus, temp_humid=temp_humid, gnss=gnss, heart_rate=heart_rate, ble_driver=ble)
    light_svc = LightService(event_bus, pwm_led=pwm_led)
    ble_svc = BLEService(event_bus, ble_driver=ble)
    nav_svc = NavigationService(event_bus, audio_driver=audio, lcd_driver=lcd)
    voice = VoiceDriver(event_bus)
    power_svc = PowerService(event_bus)

    # 3. 按序初始化（传感器 → 执行器 → 服务）
    init_order = [temp_humid, imu, gnss, light, battery_drv, heart_rate,
                  button, led, audio, lcd, pwm_led, ble, sms,
                  collision, audio_svc, alarm, display, control_svc, power_svc,
                  light_svc, ble_svc, nav_svc, voice]
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
            loop_start = time.ticks_ms()

            # 5a. 逐模块 tick + 单模块耗时监控
            for mod in init_order:
                if not mod.ctx.get("is_init", False):
                    continue
                mod_start = time.ticks_ms()
                try:
                    mod.tick()
                except Exception as e:
                    print(f"[ERROR] {mod.name}.tick(): {e}")
                mod_cost = time.ticks_diff(time.ticks_ms(), mod_start)
                if mod_cost > 5:
                    print(f"⚠️ 真阻塞: [{mod.name}] tick 耗时 {mod_cost}ms！")

            # 5b. EventBus.pump 耗时测量
            pump_start = time.ticks_ms()
            event_bus.pump()
            pump_cost = time.ticks_diff(time.ticks_ms(), pump_start)
            if pump_cost > 5:
                print(f"⚠️ 真阻塞: [EventBus.pump] 耗时 {pump_cost}ms！")

            # 5c. CPU 总忙碌时间测量
            cpu_busy_time = time.ticks_diff(time.ticks_ms(), loop_start)
            if cpu_busy_time > 8:
                print(f"🔴 警告: 主循环 CPU 忙碌时间 {cpu_busy_time}ms，挤压了 sleep 时间！")

            time.sleep_ms(10)

            # 每 500 次循环检查内存（约 5 秒）
            loop_count += 1
            if loop_count % GC_CHECK_INTERVAL == 0:
                free_bytes = gc.mem_free()
                if free_bytes < GC_THRESHOLD:
                    print(f"[GC] 内存 {free_bytes} bytes，执行回收")
                    gc.collect()
                    print(f"  -> 回收后 {gc.mem_free()} bytes")

            # 每 200 次循环（约 2 秒）打印一次数据快照
            if loop_count % 200 == 0:
                print("\n--- 模块数据 (每 2 秒) ---")
                for mod in init_order:
                    if mod.ctx.get("is_init", False):
                        print(f"  [{mod.name}] {mod.get_data()}")

    except KeyboardInterrupt:
        print("\n✓ 系统已停止")


if __name__ == "__main__":
    main()
