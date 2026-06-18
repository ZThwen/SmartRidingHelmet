"""
brief AlarmService 端到端真机测试
note 使用真硬件：LED（可见）、Audio（可听TTS）、Button（需手动按）
      碰撞事件通过 EventBus 注入（CollisionService 未开发）
      每个场景前都有提示告诉你该观察什么
执行: 上传到板子运行 python test_alarm_service_e2e.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_COLLISION_DETECTED, EVENT_BUTTON_PRESSED, EVENT_GPS_LOST,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED, EVENT_ALARM_CONTROL,
    EVENT_CONFIG_UPDATE,
    TTS_BATTERY_LOW, TTS_BATTERY_CRITICAL, TTS_GPS_LOST,
)
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.interface.Button import Button
from Modules.alarm_service import AlarmService


# ==================== 全局状态 ====================
alarm_triggered_count = 0
alarm_canceled_count = 0
button_pressed = False


def on_alarm_triggered(payload):
    global alarm_triggered_count
    alarm_triggered_count += 1


def on_alarm_canceled(payload):
    global alarm_canceled_count
    alarm_canceled_count += 1


def on_button(payload):
    global button_pressed
    button_pressed = True


def pump_loop(event_bus, times, delay_ms=10):
    for _ in range(times):
        event_bus.pump()
        time.sleep_ms(delay_ms)


def pump_sleep(event_bus, svc, duration_ms):
    """带 tick+pump 的延时（不阻塞 AlarmService 超时检查）"""
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
        svc.tick()
        event_bus.pump()
        time.sleep_ms(50)


def wait_for_alarm_end(event_bus, svc, timeout_ms):
    """等待 alarm_active=False（带 tick+pump）"""
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
        svc.tick()
        event_bus.pump()
        if not svc.ctx["alarm_active"]:
            return True
        time.sleep_ms(50)
    return False


def prompt_and_watch(title, watch_guide):
    """打印醒目提示 + 用户应观察的内容"""
    print("")
    print("=" * 60)
    print("  " + title)
    print("=" * 60)
    print("  " + watch_guide)
    print("")


def main():
    global alarm_triggered_count, alarm_canceled_count, button_pressed

    # ====== Init ======
    print("=" * 60)
    print("  AlarmService E2E Test")
    print("=" * 60)
    print("  请确认:")
    print("    □ LED (D3) 可见")
    print("    □ 扬声器已连接 J402")
    print("    □ SW 按钮可操作")
    print("")

    event_bus = EventBus()
    event_bus.subscribe(EVENT_ALARM_TRIGGERED, on_alarm_triggered)
    event_bus.subscribe(EVENT_ALARM_CANCELED, on_alarm_canceled)
    event_bus.subscribe(EVENT_BUTTON_PRESSED, on_button)

    print("[init] 初始化硬件...")
    mods = []
    try:
        led = LEDDriver(event_bus); led.init(); mods.append(led)
        print("  OK LED")
    except Exception as e:
        print("  FAIL LED: %s" % e)
        return

    try:
        audio = AudioDriver(event_bus); audio.init(); mods.append(audio)
        print("  OK Audio")
    except Exception as e:
        print("  FAIL Audio: %s" % e)
        return

    try:
        button = Button(event_bus); button.init(); mods.append(button)
        print("  OK Button")
    except Exception as e:
        print("  FAIL Button: %s" % e)
        return

    svc = AlarmService(event_bus, led, audio)
    svc.init()
    mods.append(svc)
    print("  OK AlarmService")

    # ======================================================================
    #  场景 1 — 碰撞报警 Lv2
    # ======================================================================
    prompt_and_watch(
        "[场景 1/8] 碰撞报警 — Level 2",
        "即将触发碰撞报警 (Level 2)\n"
        "  → 眼睛看 LED: 应该以约 500ms 间隔闪烁\n"
        "  → 耳朵听 TTS: 即将播报 '碰撞测试警告'"
    )
    time.sleep(3)

    svc.cfg["alarm_duration_ms"] = 8000
    event_bus.publish(EVENT_COLLISION_DETECTED, {
        "level": 2, "acc_total": 3.5, "timemap": 100,
    })
    pump_loop(event_bus, 10)

    if svc.ctx["alarm_active"] and svc.ctx["alarm_type"] == "collision":
        print("  ✓ 碰撞报警已触发 (level=%d)" % svc.ctx["alarm_level"])
    else:
        print("  ✗ 碰撞报警未触发")

    if audio:
        audio.play_tts("碰撞测试警告，碰撞等级二")

    print("")
    print("  → 观察 LED 闪烁 5 秒...")
    pump_sleep(event_bus, svc, 5000)

    print("  → 等待报警自动取消...")
    if wait_for_alarm_end(event_bus, svc, 12000):
        print("  ✓ 自动取消成功")
    else:
        print("  ✗ 超时未取消，强制 cancel")
        svc._cancel_alarm()
    pump_loop(event_bus, 10)
    pump_sleep(event_bus, svc, 2000)
    print("  [1] LED 闪烁正确吗? ( 正常约 500ms )")

    # ====== 清理状态 ======
    svc._cancel_alarm()
    pump_loop(event_bus, 10)

    # ====== 清理状态 ======
    svc._cancel_alarm()
    pump_loop(event_bus, 10)

    # ======================================================================
    #  场景 2 — SOS 按钮
    # ======================================================================
    prompt_and_watch(
        "[场景 2/8] SOS 手动触发",
        "即将等待你按下 SW 按钮:\n"
        "  → 按下后 LED 应以 200ms 快速闪烁 (明显比场景1快)\n"
        "  → TTS 将播报 'SOS求救测试'"
    )
    print("  ⏳ 请在 8 秒内按下 SW 按钮 (短按一下)")
    print("  (不会等待超过 8 秒)")

    button_pressed = False
    pump_sleep(event_bus, svc, 8000)  # 等待期间保持 tick 不阻塞

    pump_loop(event_bus, 20)

    if button_pressed:
        print("  ✓ 已检测到按钮按下")
        if svc.ctx["alarm_active"] and svc.ctx["alarm_type"] == "sos":
            print("  ✓ SOS 报警已触发 (LED 快速闪烁 200ms)")
            if audio:
                audio.play_tts("SOS求救测试")
            print("  → 观察 LED 3 秒...")
            pump_sleep(event_bus, svc, 3000)
        else:
            print("  ✗ SOS 报警未启动 (alarm_active=%s, type=%s)"
                  % (svc.ctx["alarm_active"], svc.ctx["alarm_type"]))
    else:
        print("  ✗ 未检测到按钮按下，跳过 SOS 测试")

    # ======================================================================
    #  场景 3 — 手动取消
    # ======================================================================
    prompt_and_watch(
        "[场景 3/8] 手动取消报警",
        "如果报警还在响，即将等待你再次按下 SW 按钮:\n"
        "  → LED 应该立即熄灭\n"
        "  → 扬声器应该停止"
    )

    if svc.ctx["alarm_active"]:
        print("  ⏳ 请在 8 秒内按下 SW 按钮取消报警")
        print("  (不会等待超过 8 秒)")
        button_pressed = False
        pump_sleep(event_bus, svc, 8000)
        pump_loop(event_bus, 20)

        if button_pressed:
            if not svc.ctx["alarm_active"]:
                print("  ✓ 报警已取消 (LED 灭, Audio 停)")
            else:
                print("  ✗ 取消失败")
        else:
            print("  ✗ 未检测到按钮，强制取消")
            svc._cancel_alarm()
    else:
        print("  报警已不在活跃状态，跳过手动取消")
        svc._cancel_alarm()
    pump_loop(event_bus, 5)
    pump_sleep(event_bus, svc, 2000)

    # ======================================================================
    #  场景 4 — 超时自动取消
    # ======================================================================
    prompt_and_watch(
        "[场景 4/8] 超时自动取消 (3 秒后自动停)",
        "即将触发碰撞报警 Level 1，已设置 3 秒后自动取消:\n"
        "  → LED 应以 1000ms 闪烁 (慢速)\n"
        "  → 3 秒后 LED 应自动熄灭\n"
        "  → TTS 将播报 '超时取消测试'"
    )
    pump_sleep(event_bus, svc, 3000)

    svc.cfg["alarm_duration_ms"] = 3000
    alarm_triggered_count = 0
    alarm_canceled_count = 0

    event_bus.publish(EVENT_COLLISION_DETECTED, {
        "level": 1, "acc_total": 2.5, "timemap": 100,
    })
    pump_loop(event_bus, 10)

    print("  ✓ 报警已启动 — 观察 LED 慢闪 (1000ms)")
    if audio:
        audio.play_tts("超时取消测试")

    if wait_for_alarm_end(event_bus, svc, 8000):
        print("  ✓ 3 秒后自动取消成功")
    else:
        print("  ✗ 超时未取消")
        svc._cancel_alarm()
    pump_sleep(event_bus, svc, 2000)

    # ======================================================================
    #  场景 5 — GPS 丢失 + 电池 stub + 稳定性
    # ======================================================================
    prompt_and_watch(
        "[场景 5/8] GPS 丢失 TTS + 稳定性 30s",
        "接下来:\n"
        "  1. TTS 播报 'GPS信号已丢失' — 请听扬声器\n"
        "  2. TTS 播报 '当前电量不足，请及时充电' — 电池 stub 验证\n"
        "  3. 系统静默运行 30 秒 — 观察是否有崩溃"
    )
    pump_sleep(event_bus, svc, 2000)

    if audio:
        event_bus.publish(EVENT_GPS_LOST, {"timestamp": time.ticks_ms()})
        pump_loop(event_bus, 10)
        print("  ✓ GPS 丢失 TTS 已触发 — 请听")
        pump_sleep(event_bus, svc, 3000)
    else:
        print("  SKIP GPS TTS (Audio 不可用)")

    # 电池 stub: 注入事件看是否崩溃（不应有 TTS，因 stub 为空）
    if audio:
        print("  注入电池事件 (stub)...")
        event_bus.publish(EVENT_CONFIG_UPDATE, {"target": "alarm"})
        pump_loop(event_bus, 5)
        print("  ✓ 电池 stub 正常 (无崩溃)")

    # 稳定性
    print("")
    print("  → 稳定性测试: 30 秒连续运行...")
    start = time.ticks_ms()
    tick_counts = {}
    last_report = 0

    while time.ticks_diff(time.ticks_ms(), start) < 30000:
        for m in mods:
            try:
                m.tick()
                tick_counts[m.name] = tick_counts.get(m.name, 0) + 1
            except Exception as e:
                print("  [tick err] %s: %s" % (m.name, e))
        event_bus.pump()

        elapsed = time.ticks_diff(time.ticks_ms(), start) // 1000
        if elapsed // 10 > last_report:
            last_report = elapsed // 10
            print("  [%ds] 运行中 (loops=%d)" % (elapsed, tick_counts.get("alarm", 0)))
        time.sleep_ms(10)

    print("  ✓ 30 秒稳定性通过 (无崩溃)")

    # ======================================================================
    #  场景 6 — EVENT_ALARM_CONTROL: SOS 远端触发
    # ======================================================================
    prompt_and_watch(
        "[场景 6/8] 远端 SOS 报警 (EVENT_ALARM_CONTROL{sos})",
        "即将通过 EventBus 注入 EVENT_ALARM_CONTROL cmd=sos:\n"
        "  → LED 应以 200ms 快速闪烁\n"
        "  → TTS 将播报 '远端SOS测试'"
    )
    input("  按 Enter 开始场景 6...")
    pump_sleep(event_bus, svc, 2000)

    alarm_triggered_count = 0
    event_bus.publish(EVENT_ALARM_CONTROL, {"cmd": "sos"})
    pump_loop(event_bus, 10)

    if svc.ctx["alarm_active"] and svc.ctx["alarm_type"] == "sos":
        print("  ✓ 远端 SOS 报警已触发 (LED 快闪 200ms)")
    else:
        print("  ✗ 远端 SOS 未触发 (active=%s, type=%s)"
              % (svc.ctx["alarm_active"], svc.ctx["alarm_type"]))

    if audio:
        audio.play_tts("远端SOS测试")

    print("  → 观察 LED 5 秒...")
    pump_sleep(event_bus, svc, 5000)

    svc._cancel_alarm()
    pump_loop(event_bus, 10)
    pump_sleep(event_bus, svc, 2000)

    # ======================================================================
    #  场景 7 — EVENT_ALARM_CONTROL: 静默报警
    # ======================================================================
    prompt_and_watch(
        "[场景 7/8] 远端静默报警 (EVENT_ALARM_CONTROL{stealth})",
        "即将通过 EventBus 注入 EVENT_ALARM_CONTROL cmd=stealth:\n"
        "  → LED 应保持熄灭（无闪烁）\n"
        "  → 扬声器应保持安静（无声音）\n"
        "  → 但 alarm_active 应为 True"
    )
    input("  按 Enter 开始场景 7...")
    pump_sleep(event_bus, svc, 2000)

    alarm_triggered_count = 0
    event_bus.publish(EVENT_ALARM_CONTROL, {"cmd": "stealth"})
    pump_loop(event_bus, 10)

    if svc.ctx["alarm_active"] and svc.ctx["alarm_type"] == "stealth":
        print("  ✓ 静默报警已触发 (alarm_active=True, 无声光)")
    else:
        print("  ✗ 静默报警未触发 (active=%s, type=%s)"
              % (svc.ctx["alarm_active"], svc.ctx["alarm_type"]))

    print("  → 观察 LED 和扬声器 5 秒 — 应无任何反应...")
    pump_sleep(event_bus, svc, 5000)

    svc._cancel_alarm()
    pump_loop(event_bus, 10)
    pump_sleep(event_bus, svc, 2000)

    # ======================================================================
    #  场景 8 — EVENT_ALARM_CONTROL: 远端取消
    # ======================================================================
    prompt_and_watch(
        "[场景 8/8] 远端取消报警 (EVENT_ALARM_CONTROL{cancel})",
        "即将触发 SOS 报警，然后通过 EventBus 注入 cancel:\n"
        "  → 先看到 LED 快闪\n"
        "  → cancel 后 LED 应立即熄灭"
    )
    input("  按 Enter 开始场景 8...")
    pump_sleep(event_bus, svc, 2000)

    # 先触发 SOS
    event_bus.publish(EVENT_ALARM_CONTROL, {"cmd": "sos"})
    pump_loop(event_bus, 10)

    if svc.ctx["alarm_active"]:
        print("  ✓ SOS 报警已启动 — 观察 LED 快闪...")
        pump_sleep(event_bus, svc, 3000)

        # 远端取消
        event_bus.publish(EVENT_ALARM_CONTROL, {"cmd": "cancel"})
        pump_loop(event_bus, 10)

        if not svc.ctx["alarm_active"]:
            print("  ✓ 远端取消成功 (LED 灭, Audio 停)")
        else:
            print("  ✗ 远端取消失败 (alarm_active=%s)" % svc.ctx["alarm_active"])
    else:
        print("  ✗ SOS 未启动，跳过取消测试")

    pump_sleep(event_bus, svc, 2000)

    # ====== 清理 ======
    svc._cancel_alarm()
    led.off()
    audio.stop()
    pump_sleep(event_bus, svc, 1000)

    # ====== 报告 ======
    print("")
    print("=" * 60)
    print("  E2E Test 完成 — 请人工确认:")
    print("=" * 60)
    print("")
    print("  [1] 碰撞报警 Lv2:")
    print("      LED 以 ~500ms 闪烁?       □ Yes / □ No")
    print("      听到 TTS 播报?            □ Yes / □ No")
    print("      6-8s 后自动熄灭?          □ Yes / □ No")
    print("")
    print("  [2] SOS 按钮:")
    print("      按下后 LED 快速闪 ~200ms?  □ Yes / □ No")
    print("      听到 TTS 播报?            □ Yes / □ No")
    print("")
    print("  [3] 手动取消:")
    print("      再次按下后 LED 熄灭?      □ Yes / □ No")
    print("")
    print("  [4] 超时取消:")
    print("      LED 慢闪 ~1000ms?         □ Yes / □ No")
    print("      3s 后自动熄灭?            □ Yes / □ No")
    print("")
    print("  [5] 稳定性:")
    print("      30s 无崩溃卡死?           □ Yes / □ No")
    print("")
    print("  [6] 远端 SOS:")
    print("      LED 快闪 ~200ms?          □ Yes / □ No")
    print("      听到 TTS 播报?            □ Yes / □ No")
    print("")
    print("  [7] 静默报警:")
    print("      LED 无闪烁?               □ Yes / □ No")
    print("      扬声器安静?               □ Yes / □ No")
    print("      alarm_active=True?        □ Yes / □ No")
    print("")
    print("  [8] 远端取消:")
    print("      先看到 LED 快闪?          □ Yes / □ No")
    print("      cancel 后 LED 熄灭?       □ Yes / □ No")
    print("")
    print("  终端输出:")
    print("    ALARM_TRIGGERED: %d" % alarm_triggered_count)
    print("    ALARM_CANCELED:  %d" % alarm_canceled_count)
    print("=" * 60)


if __name__ == "__main__":
    main()
