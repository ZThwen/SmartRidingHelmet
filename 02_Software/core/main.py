"""
brief 智能骑行头盔系统入口 — v2 Step 7（开机动画版）
note 集成 23 个模块（6 传感器 + 6 执行器/接口 + 1 网络 + 1 SMS + 9 Service）
note 两阶段初始化：Phase A 先显示开机画面（LCD+Display），Phase B 后台初始化其余模块
"""
import sys
import time
import gc
from machine import WDT, reset_cause, WDT_RESET

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_SYSTEM_READY, WDT_TIMEOUT_MS

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
from Modules.system_monitor import SystemMonitor


def main():
    """
    brief 系统入口: 23 个模块全集成，v2 Step 7（开机动画 + 后台初始化）
    note 两阶段初始化：LCD+Display 先显示开机画面，其余模块后台 init（不阻塞显示）
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
    nav_svc = NavigationService(event_bus, audio_driver=audio)
    voice = VoiceDriver(event_bus)
    power_svc = PowerService(event_bus)

    # --- 监控服务 ---
    sysmon = SystemMonitor(modules=[
        temp_humid, imu, gnss, light, battery_drv, heart_rate,
        button, led, audio, lcd, pwm_led, ble, sms,
        collision, audio_svc, alarm, display, control_svc, power_svc,
        light_svc, ble_svc, nav_svc, voice
    ])

    # 全局 init_order（主循环 tick 顺序）
    init_order = [lcd, display,
                  temp_humid, imu, gnss, light, battery_drv,
                  button, led, audio, pwm_led, ble, sms, heart_rate,
                  collision, audio_svc, alarm, control_svc, power_svc,
                  light_svc, ble_svc, nav_svc, voice, sysmon]
    failed = []

    # 3. 两阶段初始化（先显示开机画面，后台初始化其余模块）
    # Phase A: 快速显示开机画面（LCD硬件自主刷新，不阻塞后续init）
    print("\n[Phase A: 显示开机画面]")
    for mod in [lcd, display]:
        try:
            print("  -> 初始化 %s..." % mod.name)
            mod.init()
            print("  ✓ %s 初始化成功" % mod.name)
        except Exception as e:
            print("  ✗ %s 初始化失败: %s — 跳过" % (mod.name, e))
            failed.append(mod)

    # Phase B: 其余模块后台初始化（开机画面持续显示，LCD硬件自主刷新不阻塞）
    # 顺序约束：HeartRate 必须在所有 quectel 模块之后
    phase_b_order = [temp_humid, imu, gnss, light, battery_drv,
                     button, led, audio, pwm_led, ble, sms, heart_rate,
                     collision, audio_svc, alarm, control_svc, power_svc,
                     light_svc, ble_svc, nav_svc, voice, sysmon]
    
    print("\n[Phase B: 后台初始化]（开机画面持续显示）")
    for mod in phase_b_order:
        # Audio init 后补注入 audio_driver 到 DisplayService（boot 期间 TTS 已延迟）
        if mod.name == "audio" and display.audio_driver is None:
            display.audio_driver = mod
            print("  -> 补注入 audio_driver 到 DisplayService")
        
        try:
            print("  -> 初始化 %s..." % mod.name)
            mod.init()
            print("  ✓ %s 初始化成功" % mod.name)
        except Exception as e:
            print("  ✗ %s 初始化失败: %s — 跳过" % (mod.name, e))
            failed.append(mod)

    # 4. 发布系统就绪事件（触发 DisplayService 切换到正常画面 + 补发 TTS）
    total = 2 + len(phase_b_order)
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
    try:
        while True:
            loop_start = time.ticks_ms()

            # 0. 喂看门狗
            if wdt and sysmon.should_feed_wdt():
                wdt.feed()

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
