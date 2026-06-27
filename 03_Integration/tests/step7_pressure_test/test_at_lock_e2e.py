"""
brief AT 互斥锁 E2E 验证 — GNSS + Audio 并发不崩溃
note 验证 AT_LOCK 阻止 EC200U 多线程并发 AT 命令导致固件复位
usage 上传后 REPL: import test_at_lock_e2e
"""

import sys
import time
import gc

sys.path.append("../../02_Software")

from core.Event_Bus import EventBus
from core.config import EVENT_TTS_REQUEST, EVENT_GNSS_READY, AT_LOCK
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.actuator.Audio import AudioDriver
from Modules.audio_service import AudioService


def test_at_lock():
    gc.collect()
    mem0 = gc.mem_free()
    t0 = time.ticks_ms()

    print("=" * 50)
    print(" AT Lock E2E: GNSS + Audio 并发测试")
    print(" 初始内存: %d bytes" % mem0)
    print("=" * 50)

    bus = EventBus()

    gnss = GNSSDriver(bus)
    audio = AudioDriver(bus)
    audio_svc = AudioService(bus, audio_driver=audio)

    # Init
    print("\n初始化...")
    try:
        gnss.init()
        print("[gnss] OK")
    except Exception as e:
        print("[gnss] FAIL: %s" % e)
        return

    try:
        audio.init()
        print("[audio] OK")
    except Exception as e:
        print("[audio] FAIL: %s" % e)
        return

    try:
        audio_svc.init()
        print("[audio_service] OK")
    except Exception as e:
        print("[audio_svc] FAIL: %s" % e)
        return

    # Patch driver reference
    if audio_svc and audio:
        audio_svc.audio_driver = audio

    # SystemMonitor
    from Modules.system_monitor import SystemMonitor
    sysmon = SystemMonitor(modules=[gnss, audio, audio_svc])
    try:
        sysmon.init()
    except:
        pass

    # WDT
    wdt = None
    try:
        from machine import WDT
        wdt = WDT(timeout=8000)
        print("WDT: 已启动 (8s)")
    except:
        print("WDT: 不可用")

    # Wait for GNSS thread to start (5s delay)
    print("\n等待 GNSS 线程启动 (5s)...")
    gnss_thread_started = False
    for i in range(50):
        bus.pump()
        gnss.tick()
        audio.tick()
        audio_svc.tick()
        sysmon.tick()
        if wdt:
            wdt.feed()
        if gnss.ctx.get("thread_started", False):
            gnss_thread_started = True
            print("GNSS 线程已启动")
            break
        time.sleep_ms(200)

    if not gnss_thread_started:
        print("WARN: GNSS 线程未在预期时间启动")

    # Main test loop: inject TTS every 8s while GNSS polls
    print("\n开始并发测试 (5 分钟, GNSS 2s + TTS 8s)...")
    tts_count = 0
    tts_interval = 8000  # 8s
    next_tts = time.ticks_add(t0, tts_interval)
    gnss_polls = 0
    last_gnss = 0
    loop_count = 0
    ec200u_crashed = False
    audio_ok = True
    max_loop_ms = 0

    try:
        while True:
            now = time.ticks_ms()
            total_sec = time.ticks_diff(now, t0) // 1000
            loop_start = time.ticks_ms()

            # WDT
            if wdt:
                try:
                    wdt.feed()
                except:
                    pass

            # Module ticks
            try:
                gnss.tick()
            except Exception as e:
                print("GNSS tick error: %s" % e)

            try:
                audio.tick()
            except Exception as e:
                print("Audio tick error: %s" % e)

            try:
                audio_svc.tick()
            except Exception as e:
                print("AudioService tick error: %s" % e)

            bus.pump()
            sysmon.tick()

            loop_ms = time.ticks_diff(time.ticks_ms(), loop_start)
            if loop_ms > max_loop_ms:
                max_loop_ms = loop_ms
            time.sleep_ms(10)
            loop_count += 1

            # Count GNSS polls
            if gnss.ctx.get("last_tick", 0) != last_gnss:
                last_gnss = gnss.ctx["last_tick"]
                gnss_polls += 1

            # Inject TTS
            if time.ticks_diff(now, next_tts) >= 0:
                next_tts = time.ticks_add(now, tts_interval)
                bus.publish(EVENT_TTS_REQUEST, {
                    "text": "并发测试第%d次" % (tts_count + 1),
                    "priority": 2,
                })
                tts_count += 1

            # Check EC200U crash: if module restarts, it resets RTC to 1970
            # We can't directly detect this, but if GNSS thread dies, thread_started becomes False
            if not gnss.ctx.get("thread_running", True):
                ec200u_crashed = True
                print("\n!!! EC200U CRASH DETECTED: GNSS thread died !!!")
                break

            # 5 minutes
            if total_sec >= 300:
                break

    except KeyboardInterrupt:
        print("\n用户中断")

    # Results
    gc.collect()
    mem_end = gc.mem_free()

    print("\n" + "=" * 50)
    print(" AT Lock E2E 结果")
    print("=" * 50)
    print("运行时长      : %ds" % total_sec)
    print("EC200U 状态   : %s" % ("CRASHED" if ec200u_crashed else "ALIVE"))
    print("TTS 发送      : %d 次" % tts_count)
    print("TTS 成功      : %d 次" % audio_svc._data.get("total_played", 0))
    print("GNSS 轮询     : %d 次" % gnss_polls)
    print("AT 锁冲突跳过 : 未知（需 GNSS 内部计数）")
    print("内存          : %dKB -> %dKB" % (mem0 // 1024, mem_end // 1024))
    print("最大循环耗时  : %dms" % max_loop_ms)
    print("循环次数      : %d" % loop_count)
    print("")
    if ec200u_crashed:
        print("结果: FAIL — EC200U 固件崩溃")
    else:
        print("结果: PASS — 5 分钟 GNSS+Audio 并发无崩溃")
    print("=" * 50)


# Auto-run
test_at_lock()
