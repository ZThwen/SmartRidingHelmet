"""
brief 压力测试 — 30 分钟稳定性基线（全指标）
note 不依赖 main.py，独立创建所有模块实例。
       运行 30 分钟，结束后输出完整报告。
usage 上传后在 REPL: import stress_test_30min
"""

import sys
import time
import gc

sys.path.append("../../02_Software")

from core.Event_Bus import EventBus
from core.config import EVENT_SYSTEM_READY
from Modules.system_monitor import SystemMonitor

# 传感器
from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.sensor.Battery import BatteryDriver
from Drivers.sensor.HeartRate import HeartRateDriver

# 接口
from Drivers.interface.Button import Button
from Drivers.interface.Voice import VoiceDriver

# 执行器
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver

# 网络
from Drivers.network.BLE import BLEDriver
from Drivers.network.SMS import SMSDriver

# 服务
from Modules.collision_service import CollisionService
from Modules.audio_service import AudioService
from Modules.alarm_service import AlarmService
from Modules.display_service import DisplayService
from Modules.light_service import LightService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.navigation_service import NavigationService
from Modules.power_service import PowerService


def stress_test():
    gc.collect()
    mem0 = gc.mem_free()
    t0 = time.ticks_ms()

    print("=" * 50)
    print(" 压力测试: 30 分钟稳定性基线（全指标）")
    print(" 初始内存: %d bytes" % mem0)
    print("=" * 50)

    # ====== 创建 EventBus + 模块 ======
    bus = EventBus()

    modules = [
        TempHumidDriver(bus),
        IMUDriver(bus),
        GNSSDriver(bus),
        LightSensorDriver(bus),
        BatteryDriver(bus),
        HeartRateDriver(bus),
        Button(bus),
        VoiceDriver(bus),
        LEDDriver(bus),
        AudioDriver(bus),
        LCDDriver(bus),
        PWMLEDDriver(bus),
        BLEDriver(bus),
        SMSDriver(bus),
        CollisionService(bus),
        AudioService(bus),
        AlarmService(bus),
        DisplayService(bus),
        LightService(bus),
        BLEService(bus),
        ControlService(bus),
        NavigationService(bus),
        PowerService(bus),
    ]

    # ====== 初始化 ======
    print("\n初始化模块...")
    boot_start = time.ticks_ms()
    ok = []
    fail = []
    ble_drv = None
    audio_svc = None
    for mod in modules:
        try:
            mod.init()
            ok.append(mod)
            if mod.name == "ble":
                ble_drv = mod
            if mod.name == "audio_service":
                audio_svc = mod
        except Exception:
            fail.append(mod.name)
    print("OK=%d FAIL=%d" % (len(ok), len(fail)))
    boot_time_sec = time.ticks_diff(time.ticks_ms(), boot_start) // 1000

    # Patch AudioService with AudioDriver reference
    audio_drv = None
    for mod in ok:
        if mod.name == "audio":
            audio_drv = mod
            break
    if audio_svc and audio_drv:
        audio_svc.audio_driver = audio_drv
        print("[stress] Patched audio_svc.audio_driver")

    if not ok:
        print("无可用模块，退出")
        return

    # ====== SystemMonitor ======
    sysmon = SystemMonitor(modules=ok)
    try:
        sysmon.init()
    except Exception:
        pass

    # ====== WDT ======
    wdt = None
    try:
        from machine import WDT, WDT_RESET, reset_cause
        cause = reset_cause()
        if cause == WDT_RESET:
            print("WARNING: 上次为 WDT 复位")
        wdt = WDT(timeout=8000)
        print("WDT: 已启动 (8s)")
    except Exception:
        print("WDT: 不可用，跳过")

    # ====== 等待 BLE 就绪 ======
    ble_ready_sec = 0
    if ble_drv:
        for i in range(100):
            if ble_drv.ctx.get("is_init", False):
                ble_ready_sec = time.ticks_diff(time.ticks_ms(), boot_start) // 1000
                break
            if wdt:
                try:
                    wdt.feed()
                except:
                    pass
            time.sleep_ms(200)


    # 发布系统就绪
    bus.publish(EVENT_SYSTEM_READY, {"total": len(ok), "success": len(ok), "failed": []})

    # ====== 主循环 ======
    loop_count = 0
    module_errors = 0
    pump_errors = 0
    wdt_feed_errors = 0
    max_loop_ms = 0
    mem_min = mem0
    mem_max = mem0
    critical_ok_sec = 0
    any_ok_sec = 0
    total_sec = 0
    last_crit_check = t0
    completed = False

    print("\n开始运行 (Ctrl+C 停止)...")

    try:
        while True:
            now = time.ticks_ms()
            total_sec = time.ticks_diff(now, t0) // 1000
            loop_count += 1
            loop_start = time.ticks_ms()

            # WDT 门控
            if wdt:
                try:
                    feed = sysmon.should_feed_wdt() if hasattr(sysmon, 'should_feed_wdt') else True
                    if feed:
                        wdt.feed()
                except Exception:
                    wdt_feed_errors += 1
                    try:
                        wdt.feed()
                    except Exception:
                        pass

            # 模块 tick
            for mod in ok:
                try:
                    if mod.ctx.get("is_init", False):
                        mod.tick()
                except Exception:
                    module_errors += 1

            # EventBus pump
            try:
                bus.pump()
            except Exception:
                pump_errors += 1

            # SystemMonitor tick
            try:
                sysmon.tick()
            except Exception:
                module_errors += 1

            loop_cost = time.ticks_diff(time.ticks_ms(), loop_start)
            if loop_cost > max_loop_ms:
                max_loop_ms = loop_cost
            time.sleep_ms(10)

            # 每秒统计：内存 + 存活时间
            if time.ticks_diff(now, last_crit_check) >= 1000:
                last_crit_check = now
                gc.collect()
                mem_now = gc.mem_free()
                if mem_now < mem_min:
                    mem_min = mem_now
                if mem_now > mem_max:
                    mem_max = mem_now

                if sysmon.ctx.get("critical_alive", True):
                    critical_ok_sec += 1
                if sysmon.ctx.get("any_alive", True):
                    any_ok_sec += 1

            # 安全退出条件
            if total_sec >= 1800:  # 30 min
                completed = True
                break

    except KeyboardInterrupt:
        print("\n用户中断")
        completed = False

    # ====== 收集最终数据 ======
    gc.collect()
    mem_end = gc.mem_free()

    # WDT 复位次数：从 sysmon 获取
    wdt_resets = sysmon.ctx.get("reset_count", 0) if sysmon else 0

    # 模块心跳统计
    module_health = sysmon.ctx.get("module_health", {}) if sysmon else {}
    alive_modules = sum(1 for h in module_health.values() if h.get("last_hb", 0) > 0)
    total_modules = len(module_health)

    # ====== 离线模块诊断 ======
    print("")
    print("--- 离线模块诊断 ---")
    for m in ok:
        try:
            name = m.name if hasattr(m, 'name') else "?"
            hb = m.ctx.get("last_hb", 0) if hasattr(m, 'ctx') else 0
            is_init = m.ctx.get("is_init", False) if hasattr(m, 'ctx') else False
            tier = module_health.get(name, {}).get("tier", "?")
            abandoned = getattr(m, '_abandoned', None)
            abandoned_flag = "ABANDONED" if abandoned else ""
            print("  %-20s hb=%d init=%s tier=%-10s %s" %
                  (name, hb, is_init, tier, abandoned_flag))
        except Exception:
            print("  %-20s ERROR reading" % getattr(m, 'name', '?'))
    print("--- 诊断结束 ---")
    print("")

    # BLE 状态
    ble_init = ble_drv and ble_drv.ctx.get("is_init", False)
    ble_conn = ble_drv and ble_drv.ctx.get("is_connected", False)
    if ble_init and ble_conn:
        ble_status = "Connected"
    elif ble_init:
        ble_status = "Init(no conn)"
    else:
        ble_status = "Not init"
    avg_loop_ms = total_sec * 1000 / loop_count if loop_count else 0
    crit_pct = critical_ok_sec * 100 // total_sec if total_sec > 0 else 0

    # Audio TTS count
    tts_total = audio_svc._data.get("total_played", 0) if audio_svc else 0
    mem_retention = mem_end * 100 // mem0 if mem0 > 0 else 0
    status = "完成" if completed else "中断"



    print("\n" + "=" * 50)
    print(" 压力测试结果")
    print("=" * 50)
    print("========== 稳定性指标 ==========")
    print("运行时长      : %ds (%dmin) [%s]" % (total_sec, total_sec // 60, status))
    print("WDT 复位      : %d 次" % wdt_resets)
    print("内存          : %dKB->%dKB->%dKB (%d%%)" % (
        mem0 // 1024, mem_min // 1024, mem_end // 1024, mem_retention))
    print("关键模块存活  : %d/%ds (%d%%)" % (critical_ok_sec, total_sec, crit_pct))
    print("模块心跳      : %d/%d 在线" % (alive_modules, total_modules))
    print("")
    print("========== 性能指标 ==========")
    print("平均主循环周期: %.1fms" % avg_loop_ms)
    print("最慢主循环周期: %dms" % max_loop_ms)
    print("启动完成时间  : %ds" % boot_time_sec)
    print("BLE 就绪时间  : %ds" % ble_ready_sec)
    print("")
    print("========== 负载指标 ==========")
    print("TTS 已播      : %d 次" % tts_total)
    print("事件吞吐      : %.1f ops/min" % (loop_count * 60.0 / total_sec if total_sec else 0))
    print("泵异常        : %d 次" % pump_errors)
    print("模块异常      : %d 次" % module_errors)
    print("WDT 馈异常    : %d 次" % wdt_feed_errors)
    print("循环次数      : %d" % loop_count)
    print("")
    print("========== 连接状态 ==========")
    print("BLE 状态      : %s" % ble_status)
    print("=" * 50)


# 自动运行
stress_test()
