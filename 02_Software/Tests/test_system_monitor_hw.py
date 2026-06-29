"""
brief SystemMonitor E2E 集成测试 — 使用真实模块
note 导入全部 23 个模块，创建实例并初始化。
      硬件未连接的模块会 init 失败（被跳过）。
      成功 init 的模块会正常 tick，SystemMonitor 监控所有心跳。
usage 上传后在 REPL: import test_system_monitor_hw
"""

import sys
import time
import gc

sys.path.append("..")

from core.Event_Bus import EventBus
from Modules.system_monitor import SystemMonitor

# ====== 导入所有模块 ======
from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.sensor.Battery import BatteryDriver
from Drivers.sensor.HeartRate import HeartRateDriver

from Drivers.interface.Button import Button
from Drivers.interface.Voice import VoiceDriver

from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver

from Drivers.network.BLE import BLEDriver
from Drivers.network.SMS import SMSDriver

from Modules.collision_service import CollisionService
from Modules.audio_service import AudioService
from Modules.alarm_service import AlarmService
from Modules.display_service import DisplayService
from Modules.light_service import LightService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.navigation_service import NavigationService
from Modules.power_service import PowerService


def e2e_test():
    gc.collect()
    mem_start = gc.mem_free()

    print("=" * 55)
    print(" SystemMonitor E2E — 真实模块集成测试")
    print("=" * 55)
    print("内存: %d bytes" % mem_start)

    # ====== 创建 EventBus ======
    bus = EventBus()

    # ====== 创建所有模块实例 ======
    print("\n创建模块实例...")
    all_modules = [

        # 传感器
        TempHumidDriver(bus),
        IMUDriver(bus),
        GNSSDriver(bus),
        LightSensorDriver(bus),
        BatteryDriver(bus),
        HeartRateDriver(bus),

        # 接口
        Button(bus),
        VoiceDriver(bus),

        # 执行器
        LEDDriver(bus),
        AudioDriver(bus),
        LCDDriver(bus),
        PWMLEDDriver(bus),

        # 网络
        BLEDriver(bus),
        SMSDriver(bus),

        # 服务
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
    ok_modules = []
    failed_modules = []

    for mod in all_modules:
        try:
            mod.init()
            ok_modules.append(mod)
            print("  [OK] %s" % mod.name)
        except Exception as e:
            failed_modules.append(mod)
            # 不打印详细错误，避免刷屏
            print("  [--] %s (硬件未连接，跳过)" % mod.name)

    print("\n已初始化: %d | 失败: %d" % (len(ok_modules), len(failed_modules)))

    if len(ok_modules) == 0:
        print("❌ 无可用模块，终止测试")
        return

    # ====== 创建 SystemMonitor ======
    sysmon = SystemMonitor(modules=ok_modules)
    sysmon.init()
    print("SystemMonitor: is_init=%s reset=%d safe=%s" % (
        sysmon.ctx["is_init"], sysmon.ctx["reset_count"], sysmon.ctx["safe_mode"]))

    # 跳过宽限期
    sysmon._boot_tick = time.ticks_ms() - 20000
    sysmon.ctx["start_time"] = sysmon._boot_tick

    # ====== Phase 1: 运行 8 秒，建立心跳 ======
    print("\n--- Phase 1: 运行 8 秒 (建立心跳) ---")
    for sec in range(8):
        for mod in ok_modules:
            try:
                mod.tick()
            except Exception:
                pass
        bus.pump()
        sysmon.tick()
        time.sleep_ms(1000)
        print("  [%ds]" % (sec + 1))

    # ====== Phase 2: 心跳检查 ======
    print("\n--- Phase 2: 心跳状态 ---")
    sysmon.ctx["last_scan"] = 0
    sysmon.tick()

    health = sysmon.ctx["module_health"]
    alive = []
    dead = []

    for mod in ok_modules:
        h = health.get(mod.name, {})
        s = h.get("state", "?")
        age = h.get("age_ms", 0)
        if s == "OK":
            alive.append("%s(%dms)" % (mod.name, age))
        else:
            dead.append("%s=%s(%dms)" % (mod.name, s, age))

    print("  存活 (%d):" % len(alive))
    for a in alive:
        print("    %s" % a)
    if dead:
        print("  异常 (%d):" % len(dead))
        for d in dead:
            print("    %s" % d)

    # ====== Phase 3: WDT 门控 ======
    print("\n--- Phase 3: WDT 门控 ---")
    feed = sysmon.should_feed_wdt()
    if feed:
        print("  should_feed_wdt() = True ✅")
    else:
        print("  should_feed_wdt() = False")
        # 检查原因
        crit = sysmon._critical
        for m in crit:
            age = time.ticks_diff(time.ticks_ms(), m.ctx.get("last_hb", 0))
            print("    %s: last_hb %dms ago" % (m.name, age))
        print("  ⚠️ 关键模块失联 — 如果在真机上 WDT 会触发复位")

    # ====== Phase 4: 持续监测 12 秒 ======
    print("\n--- Phase 4: 持续监测 12 秒 ---")
    for sec in range(12):
        for mod in ok_modules:
            try:
                mod.tick()
            except Exception:
                pass
        bus.pump()
        sysmon.tick()
        time.sleep_ms(1000)

        if (sec + 1) % 4 == 0:
            h = sysmon.ctx["module_health"]
            t = [n for n, v in h.items() if v.get("state") == "TIMEOUT"]
            print("  [%ds] alive=%d timeout=%d %s" % (
                sec + 1, len(alive) - len(t), len(t),
                ("⚠️ " + str(t)) if t else ""))

    # ====== Phase 5: 内存 ======
    print("\n--- Phase 5: 内存 ---")
    gc.collect()
    mem_end = gc.mem_free()
    delta = mem_start - mem_end
    print("  内存: %d → %d (增长 %d bytes) %s" % (
        mem_start, mem_end, delta,
        "⚠️ 超过 10KB" if delta > 10000 else "✅"))

    # ====== 汇总 ======
    print("\n" + "=" * 55)
    print(" E2E 测试: 完成 (见上方日志)")
    print(" 初始化成功: %d 模块" % len(ok_modules))
    print(" 初始化失败: %d 模块 (硬件未连接)" % len(failed_modules))
    print("=" * 55)


# 自动运行
e2e_test()
