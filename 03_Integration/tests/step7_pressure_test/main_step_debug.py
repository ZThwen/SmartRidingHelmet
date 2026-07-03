"""
brief 步骤诊断工具 — 逐模块组测试，定位主循环冻结根因
note Phase 1 验证基础架构（LCD + EventBus + 主循环 + WDT），确保最小系统存活
note Phase 2 按组递增测试模块（A-I），每组运行 60s，用心跳检测冻结
note 无 temp_humid、无 display_service、无两阶段 init、无 debug 打印洪流
"""
import sys
import time
import gc
from machine import WDT, reset_cause, WDT_RESET

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import WDT_TIMEOUT_MS

# ============================================================
# Phase 1: 基础架构验证
# ============================================================

def run_phase1():
    """
    brief 验证最小系统：LCD init + EventBus pump + 主循环心跳 + WDT 喂狗
    return (event_bus, lcd, wdt) 或失败退出
    """
    print("=" * 50)
    print("Phase 1: 基础架构验证")
    print("=" * 50)

    # 检测上次复位原因
    try:
        cause = reset_cause()
        if cause == WDT_RESET:
            print("WARN: 上次复位 = WDT 超时 (系统曾卡死)")
        else:
            print("复位原因: %d (正常)" % cause)
    except Exception:
        pass

    # 1. 创建 EventBus（不开 debug，减少输出）
    event_bus = EventBus()
    event_bus.debug = False

    # 订阅一个测试事件 — 周期性触发，证明 pump 正常
    pump_ok_count = [0]

    def _on_phase1_test(data):
        pump_ok_count[0] += 1

    event_bus.subscribe("PHASE1_TEST", _on_phase1_test)

    # 2. LCD init（不依赖 DisplayService，直接驱动测试）
    print("[Phase1] 初始化 LCD ...")
    from Drivers.actuator.LCD import LCDDriver
    lcd = LCDDriver(event_bus)
    try:
        lcd.init()
        print("[Phase1] OK: LCD 初始化成功")
    except Exception as e:
        print("[Phase1] FAIL: LCD 初始化失败: %s" % e)
        # 不中断 — LCD 失败不影响核心测试

    # 3. WDT 启动（8s 超时）
    wdt = None
    try:
        wdt = WDT(timeout=WDT_TIMEOUT_MS)
        print("[Phase1] OK: WDT 已启动 (%ds)" % (WDT_TIMEOUT_MS // 1000))
    except Exception as e:
        print("[Phase1] FAIL: WDT 启动失败: %s" % e)

    # 4. 主循环：15 秒心跳测试
    print("[Phase1] 主循环启动 (15 秒) ...")
    start = time.ticks_ms()
    last_beat = time.ticks_ms()
    count = 0

    while True:
        count += 1

        # 喂狗（P1 不依赖 sysmon）
        if wdt:
            wdt.feed()

        # 每 500 轮发布一次测试事件 → pump 触发回调
        if count % 500 == 1:
            event_bus.publish("PHASE1_TEST", {})

        # 泵事件
        event_bus.pump()

        time.sleep_ms(10)

        # 每秒心跳
        now = time.ticks_ms()
        if time.ticks_diff(now, last_beat) >= 1000:
            elapsed = time.ticks_diff(now, start) // 1000
            print("BEAT: %ds  rounds=%d  pump_ok=%d" % (elapsed, count, pump_ok_count[0]))
            last_beat = now

        if time.ticks_diff(now, start) >= 15000:
            break

    print("[Phase1] PASS: 基础架构正常\n")
    return event_bus, lcd, wdt


# ============================================================
# Phase 2: 模块组测试 — 递增 init + 60s 生存测试
# ============================================================

def test_module_group(event_bus, wdt, group_label, modules_to_init, all_tick_order,
                      duration_sec=60):
    """
    brief 测试一个模块组：init → 60s 主循环 → PASS/FAIL
    param group_label: 组标签 (如 "A", "B")
    param modules_to_init: 本轮待 init 的模块列表
    param all_tick_order: 所有已 init 模块的 tick 顺序（包含本轮 + 前序组）
    param duration_sec: 运行时长 (秒)
    return True=PASS, False=FAIL
    """
    print("-" * 50)
    print("[Group %s] 初始化模块..." % group_label)

    # Step 1: Init 本轮模块
    for mod in modules_to_init:
        if mod is None:
            continue
        try:
            mod.init()
            print("  OK: %s" % mod.name)
        except Exception as e:
            print("  FAIL: %s init 失败: %s" % (mod.name, str(e)[:60]))
            return False

    # Step 2: 主循环 (duration_sec 秒，禁用 WDT 以观察冻结)
    print("[Group %s] 运行 %ds 生存测试..." % (group_label, duration_sec))
    start = time.ticks_ms()
    last_beat = time.ticks_ms()
    count = 0

    while True:
        count += 1

        # 喂狗（如果启用）
        if wdt:
            wdt.feed()

        # Tick 所有已 init 模块
        for mod in all_tick_order:
            if mod is None:
                continue
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception as e:
                    print("  [tick err] %s: %s" % (mod.name, str(e)[:40]))

        # 泵事件
        event_bus.pump()

        time.sleep_ms(10)

        # 每 5 秒心跳
        now = time.ticks_ms()
        if time.ticks_diff(now, last_beat) >= 5000:
            elapsed = time.ticks_diff(now, start) // 1000
            mem_free = gc.mem_free()
            print("BEAT: %ds  rounds=%d  mem=%d" % (elapsed, count, mem_free))
            last_beat = now

        # 达到指定时长 → 退出
        if time.ticks_diff(now, start) >= duration_sec * 1000:
            break

    print("[Group %s] PASS after %ds" % (group_label, duration_sec))
    return True


def run_phase2(event_bus, lcd, wdt):
    """
    brief 按组递增测试模块 A-I
    note 每组先 init 再 tick 60s；init 失败或冻结则标记 FAIL 并停止
    note 依赖关系：后序组可能依赖前序组的驱动实例（如 alarm 依赖 led/audio/sms）
    """
    print("=" * 50)
    print("Phase 2: 模块组测试 (A-I)")
    print("=" * 50)

    # ================================================================
    # 创建所有模块实例（仅构造，不 init）
    # 依赖链：传感器独立 → 执行器独立 → quectel 模块必须在 heart_rate 前
    # Service 层依赖 Device 层实例（作为构造参数传入）
    # ================================================================

    # --- Group A: 传感器 ---
    from Drivers.sensor.imu import IMUDriver
    from Drivers.sensor.Gnss import GNSSDriver
    from Drivers.sensor.Light import LightSensorDriver
    from Drivers.sensor.Battery import BatteryDriver

    imu = IMUDriver(event_bus)
    gnss = GNSSDriver(event_bus)
    light = LightSensorDriver(event_bus)
    battery_drv = BatteryDriver(event_bus)

    group_A = [imu, gnss, light, battery_drv]

    # --- Group B: 执行器 ---
    from Drivers.interface.Button import Button
    from Drivers.actuator.LED import LEDDriver
    from Drivers.actuator.Audio import AudioDriver
    from Drivers.actuator.PWM_LED import PWMLEDDriver

    button = Button(event_bus)
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    pwm_led = PWMLEDDriver(event_bus)

    group_B = [button, led, audio, pwm_led]

    # --- Group C: 网络 (quectel 模块) ---
    from Drivers.network.BLE import BLEDriver
    from Drivers.network.SMS import SMSDriver

    ble = BLEDriver(event_bus)
    sms = SMSDriver(event_bus)

    group_C = [ble, sms]

    # --- Group D: 心率 UART9 (必须在 quectel 模块之后) ---
    from Drivers.sensor.HeartRate import HeartRateDriver

    heart_rate = HeartRateDriver(event_bus)

    group_D = [heart_rate]

    # --- Group E: 语音 UART2 ---
    from Drivers.interface.Voice import VoiceDriver

    voice = VoiceDriver(event_bus)

    group_E = [voice]

    # --- Group F: 低层服务 ---
    from Modules.collision_service import CollisionService
    from Modules.audio_service import AudioService

    collision = CollisionService(event_bus)
    audio_svc = AudioService(event_bus, audio_driver=audio)

    group_F = [collision, audio_svc]

    # --- Group G: 中层服务 ---
    from Modules.alarm_service import AlarmService
    from Modules.control_service import ControlService
    from Modules.power_service import PowerService

    # ControlService temp_humid=None（无温湿度模块）
    alarm = AlarmService(event_bus, led=led, audio=audio, sms=sms)
    control_svc = ControlService(event_bus, temp_humid=None, gnss=gnss,
                                 heart_rate=heart_rate, ble_driver=ble)
    power_svc = PowerService(event_bus)

    group_G = [alarm, control_svc, power_svc]

    # --- Group H: 高层服务 ---
    from Modules.light_service import LightService
    from Modules.ble_service import BLEService
    from Modules.navigation_service import NavigationService

    light_svc = LightService(event_bus, pwm_led=pwm_led)
    ble_svc = BLEService(event_bus, ble_driver=ble)
    nav_svc = NavigationService(event_bus, audio_driver=audio)

    group_H = [light_svc, ble_svc, nav_svc]

    # --- Group I: 系统监控 ---
    from Modules.system_monitor import SystemMonitor

    all_mods = [
        imu, gnss, light, battery_drv,
        button, led, audio, pwm_led,
        ble, sms, heart_rate, voice,
        collision, audio_svc, alarm, control_svc, power_svc,
        light_svc, ble_svc, nav_svc,
    ]
    sysmon = SystemMonitor(modules=all_mods)

    group_I = [sysmon]

    # ================================================================
    # 按序测试每组
    # ================================================================
    all_tick = []  # 累计已 init 的模块（tick 顺序）

    groups = [
        ("A", group_A),
        ("B", group_B),
        ("C", group_C),
        ("D", group_D),
        ("E", group_E),
        ("F", group_F),
        ("G", group_G),
        ("H", group_H),
        ("I", group_I),
    ]

    for label, mods in groups:
        # tick_order = 前序已 init 模块 + 本轮模块
        tick_order = list(all_tick) + [m for m in mods if m is not None]
        ok = test_module_group(event_bus, wdt, label, mods, tick_order)
        if not ok:
            print("\n*** Group %s FAILED — 停止测试 ***" % label)
            return
        # 累积本轮模块到 tick 列表
        all_tick.extend([m for m in mods if m is not None])

    print("\n" + "=" * 50)
    print("Phase 2 ALL PASS — 所有 9 组模块 60s 生存测试通过")
    print("=" * 50)


# ============================================================
# Main
# ============================================================

def main():
    """
    brief 诊断工具入口
    note Phase 1 → Phase 2；Phase 1 失败则退出，不继续
    """
    try:
        event_bus, lcd, wdt = run_phase1()
    except Exception as e:
        print("Phase 1 FAIL: %s" % e)
        return

    try:
        run_phase2(event_bus, lcd, wdt)
    except Exception as e:
        print("Phase 2 FAIL: %s" % e)


if __name__ == "__main__":
    main()
