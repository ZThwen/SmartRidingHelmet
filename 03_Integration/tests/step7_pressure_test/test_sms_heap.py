"""
brief SMS Heap Test — 参照 test_sms_e2e 架构，通过 EventBus 完整链路发送 SMS
note 堆碎片假设：5min GNSS+TTS 后 SMS 因 EC200U 内部堆耗尽而 Malloc failed
usage REPL: import test_sms_heap
"""
import sys, time, gc, json
sys.path.append("../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_COLLISION_DETECTED,
    EVENT_SMS_PHONE_CONFIG, EVENT_TTS_REQUEST, EVENT_GNSS_READY,
)
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.network.SMS import SMSDriver
from Drivers.network.BLE import BLEDriver
from Drivers.sensor.Gnss import GNSSDriver
from Modules.alarm_service import AlarmService
from Modules.control_service import ControlService
from Modules.ble_service import BLEService
from Modules.audio_service import AudioService
from Modules.system_monitor import SystemMonitor

TEST_PHONE = "13800000000"


def _pump(bus, mods, ms):
    """快速泵循环"""
    end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(time.ticks_ms(), end) < 0:
        for m in mods:
            try:
                if m.ctx.get("is_init", False):
                    m.tick()
            except:
                pass
        bus.pump()


def _send_json(bus, cmd):
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})


def test_sms_heap():
    gc.collect()
    mem0 = gc.mem_free()
    t0 = time.ticks_ms()
    print("=" * 50)
    print(" SMS Heap Test (参照 test_sms_e2e 架构)")
    print(" 初始内存: %d" % mem0)
    print("=" * 50)

    bus = EventBus()

    # 同 E2E 的 8 模块 + GNSS
    led = LEDDriver(bus)
    audio = AudioDriver(bus)
    sms = SMSDriver(bus)
    ble = BLEDriver(bus)
    audio_svc = AudioService(bus, audio_driver=audio)
    alarm = AlarmService(bus, led=led, audio=audio, sms=sms)
    ble_svc = BLEService(bus, ble_driver=ble)
    ctrl = ControlService(bus)
    gnss = GNSSDriver(bus)

    mods_all = [led, audio, sms, ble, audio_svc, alarm, ble_svc, ctrl, gnss]
    mods_frag = [audio, audio_svc, gnss]  # 碎片化阶段最小集合

    # Init
    print("\n初始化...")
    for m in mods_all:
        try:
            m.init()
            print("  OK %s" % m.name)
        except Exception as e:
            print("  FAIL %s: %s" % (m.name, e))
            return
    audio_svc.audio_driver = audio

    sysmon = SystemMonitor(modules=mods_all)
    try:
        sysmon.init()
    except:
        pass

    wdt = None
    try:
        from machine import WDT
        wdt = WDT(timeout=8000)
        print("WDT: started")
    except:
        pass

    # Warmup 60s
    print("\n等待 EC200U 就绪 (60s)...")
    for i in range(60):
        _pump(bus, mods_all, 1000)
        if (i + 1) % 15 == 0:
            print("  %ds..." % (i + 1))
        if wdt:
            wdt.feed()

    # Config phone via EventBus chain
    print("\n配置手机号...")
    bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": TEST_PHONE})
    _pump(bus, mods_all, 3000)
    print("  手机号: %s" % alarm._sms_phone)

    # SMS 1: clean heap, via collision trigger
    print("\n--- SMS 1: 洁净堆 ---")
    bus.publish(EVENT_COLLISION_DETECTED, {"acc_total": 6.0, "level": 2})
    _pump(bus, mods_all, 8000)
    sms1_ok = sms._data.get("last_send_success", False)
    print("SMS1: %s" % ("OK" if sms1_ok else "FAIL"))
    _send_json(bus, "alarm_cancel")
    _pump(bus, mods_all, 2000)

    # Fragment: 5min GNSS + TTS
    print("\n碎片化: 5min GNSS(2s) + TTS(8s)...")
    tts_cnt = 0
    gps_cnt = 0
    last_gnss = 0
    next_tts = time.ticks_add(time.ticks_ms(), 8000)
    frag_start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), frag_start) < 300000:
        if wdt:
            wdt.feed()
        _pump(bus, mods_frag, 10)
        sysmon.tick()
        t = time.ticks_ms()
        if gnss.ctx.get("last_tick", 0) != last_gnss:
            last_gnss = gnss.ctx["last_tick"]
            gps_cnt += 1
        if time.ticks_diff(t, next_tts) >= 0:
            next_tts = time.ticks_add(t, 8000)
            bus.publish(EVENT_TTS_REQUEST, {"text": "碎片%d" % (tts_cnt + 1), "priority": 2})
            tts_cnt += 1

    # SMS 2: fragmented heap
    print("\n--- SMS 2: 碎片堆 ---")
    bus.publish(EVENT_COLLISION_DETECTED, {"acc_total": 6.0, "level": 2})
    _pump(bus, mods_all, 8000)
    sms2_ok = sms._data.get("last_send_success", False)
    print("SMS2: %s" % ("OK" if sms2_ok else "FAIL"))
    _send_json(bus, "alarm_cancel")
    _pump(bus, mods_all, 2000)

    # Results
    total_sec = time.ticks_diff(time.ticks_ms(), t0) // 1000
    gc.collect()
    mem_end = gc.mem_free()
    print("\n" + "=" * 50)
    print(" SMS Heap Test 结果")
    print("=" * 50)
    print("运行时长      : %ds" % total_sec)
    print("SMS1 (洁净)   : %s" % ("OK" if sms1_ok else "FAIL"))
    print("SMS2 (碎片)   : %s" % ("OK" if sms2_ok else "FAIL"))
    print("GNSS 轮询     : %d" % gps_cnt)
    print("TTS 发送      : %d" % tts_cnt)
    print("TTS 成功      : %d" % audio_svc._data.get("total_played", 0))
    print("内存          : %dK -> %dK" % (mem0 // 1024, mem_end // 1024))
    print("")
    if sms1_ok and not sms2_ok:
        print("结论: 堆碎片导致 Malloc failed")
    elif sms1_ok and sms2_ok:
        print("结论: 两次均成功，碎片化不够或假设不成立")
    else:
        print("结论: SMS1 已失败，非碎片问题")
    print("=" * 50)


test_sms_heap()
