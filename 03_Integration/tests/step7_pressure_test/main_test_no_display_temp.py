"""
brief 智能骑行头盔系统入口 — 精简版（无 temp_humid + display，用于测试主循环阻塞根源）
note 集成 21 个模块（5 传感器 + 6 执行器/接口 + 1 网络 + 1 SMS + 8 Service）
note 移除 temp_humid 和 DisplayService，使用扁平初始化（无两阶段）
"""
import sys
import time
import gc
from machine import WDT, reset_cause, WDT_RESET

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_SYSTEM_READY, WDT_TIMEOUT_MS

# CHANGED: 移除 from Drivers.sensor.Temp_Humid import TempHumidDriver
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
# CHANGED: 移除 from Modules.display_service import DisplayService
from Modules.light_service import LightService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.navigation_service import NavigationService
from Modules.power_service import PowerService
from Modules.system_monitor import SystemMonitor


def main():
    """
    brief 系统入口: 21 个模块精简版（无 temp_humid + display，扁平初始化）
    note 用于测试 temp_humid/display 是否为主循环阻塞的根源
    """
    GC_THRESHOLD = 8000  # 内存阈值（bytes）
    GC_CHECK_INTERVAL = 500  # 每 500 次循环检查

    # 0. 检测复位原因
    try:
        cause = reset_cause()
        if cause == WDT_RESET:
            print("⚠️ 上次复位: 看门狗超时 (系统可能卡死过)")
        else:
            print("复位原因: %d (正常)" % cause)
    except Exception:
        pass

    print("🚀 智能骑行头盔系统启动... (精简版: 无 temp_humid + display)")

    # 1. 创建事件总线
    event_bus = EventBus()
    event_bus.debug = True

    # 2. 创建模块实例
    # --- 传感器 ---
    # CHANGED: 移除 temp_humid = TempHumidDriver(event_bus)
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
    # CHANGED: 移除 display = DisplayService(event_bus, lcd_driver=lcd, audio_driver=audio)
    # CHANGED: control_svc 传入 temp_humid=None
    control_svc = ControlService(event_bus, temp_humid=None, gnss=gnss, heart_rate=heart_rate, ble_driver=ble)
    light_svc = LightService(event_bus, pwm_led=pwm_led)
    ble_svc = BLEService(event_bus, ble_driver=ble)
    nav_svc = NavigationService(event_bus, audio_driver=audio)
    voice = VoiceDriver(event_bus)
    power_svc = PowerService(event_bus)

    # --- 监控服务（CHANGED: 移除 temp_humid 和 display）---
    sysmon = SystemMonitor(modules=[
        imu, gnss, light, battery_drv, heart_rate,
        button, led, audio, lcd, pwm_led, ble, sms,
        collision, audio_svc, alarm, control_svc, power_svc,
        light_svc, ble_svc, nav_svc, voice
    ])

    # 全局 init_order（CHANGED: 移除 lcd 和 display，扁平初始化）
    init_order = [imu, gnss, light, battery_drv,
                  button, led, audio, pwm_led, ble, sms, heart_rate,
                  collision, audio_svc, alarm, control_svc, power_svc,
                  light_svc, ble_svc, nav_svc, voice, sysmon]
    failed = []

    # 3. 扁平初始化（无两阶段）
    print("\n[初始化] 扁平初始化 %d 个模块" % len(init_order))
    for mod in init_order:
        try:
            print("  -> 初始化 %s..." % mod.name)
            mod.init()
            print("  ✓ %s 初始化成功" % mod.name)
        except Exception as e:
            print("  ✗ %s 初始化失败: %s — 跳过" % (mod.name, e))
            failed.append(mod)

    # 4. 发布系统就绪事件
    total = len(init_order)
    success = total - len(failed)
    event_bus.publish(EVENT_SYSTEM_READY, {
        "total": total,
        "success": success,
        "failed": [m.name for m in failed],
    })

    if failed:
        print("\n⚠️ 系统就绪（%d/%d 模块在线）" % (success, total))
        print("   离线: %s" % ', '.join(m.name for m in failed))
    else:
        print("\n✅ 系统就绪，%d 个模块在线" % success)

    # 启动硬件看门狗（系统就绪后）
    wdt = None
    try:
        wdt = WDT(timeout=WDT_TIMEOUT_MS)
        print("🐕 看门狗已启动 (超时: %ds)" % (WDT_TIMEOUT_MS // 1000))
    except Exception as e:
        print("⚠️ 看门狗启动失败: %s" % e)

    # 5. 主循环
    print("▶ 进入主循环（事件驱动）")
    loop_count = 0
    slow_modules = []          # 慢模块记录 [(name, cost_ms, ts), ...]
    try:
        while True:
            loop_start = time.ticks_ms()

            # 0. 喂看门狗（喂狗前记录状态快照）
            if wdt and sysmon.should_feed_wdt():
                sysmon._record_pre_feed_state(slow_modules)
                wdt.feed()
                slow_modules = []  # 喂狗后清空慢模块记录

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
                    slow_modules.append((mod.name, mod_cost, time.ticks_ms()))
                    if len(slow_modules) > 10:
                        slow_modules = slow_modules[-10:]

            # 5b. 系统监控
            sysmon.tick()

            # 5c. EventBus.pump 耗时测量
            pump_start = time.ticks_ms()
            event_bus.pump()
            pump_cost = time.ticks_diff(time.ticks_ms(), pump_start)
            if pump_cost > 5:
                print(f"⚠️ 真阻塞: [EventBus.pump] 耗时 {pump_cost}ms！")

            # 5d. CPU 总忙碌时间测量
            cpu_busy_time = time.ticks_diff(time.ticks_ms(), loop_start)
            if cpu_busy_time > 100:
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
