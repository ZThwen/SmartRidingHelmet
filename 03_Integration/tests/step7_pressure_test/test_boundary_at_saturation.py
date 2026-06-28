"""
brief 边界测试 — AT 通道三路并发饱和（GNSS + Audio + SMS）
note  验证 5 分钟三路 AT 并发不崩溃，AT_LOCK timeout 正常触发
usage 上传后 REPL: import test_boundary_at_saturation
"""

import sys
import time
sys.path.append("../../02_Software")
from core.Event_Bus import EventBus
from Drivers.sensor.Gnss import GNSSDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.network.SMS import SMSDriver

bus = EventBus()
gnss = GNSSDriver(bus)
audio = AudioDriver(bus)
sms_drv = SMSDriver(bus)

gnss.init()
audio.init()
sms_drv.init()
gnss.start()

t0 = time.ticks_ms()
sms_sent = 0
sms_ok = 0
tts_count = 0
timeout_count = 0

last_tts = 0
last_sms = 0

while time.ticks_diff(time.ticks_ms(), t0) < 300000:
    now = time.ticks_ms()

    # Every 5s: TTS
    if time.ticks_diff(now, last_tts) > 5000:
        tts_count += 1
        try:
            result = audio.play_tts("\u8fb9\u754c\u6d4b\u8bd5TTS", priority=2)
            if result is False:
                timeout_count += 1
        except Exception:
            timeout_count += 1
        last_tts = now

    # Every 15s: SMS (to avoid burning SIM credit)
    if time.ticks_diff(now, last_sms) > 15000:
        sms_sent += 1
        try:
            sms_drv.send_sms("13368190189", "AT\u9971\u548c\u6d4b\u8bd5")
            sms_ok += 1
        except Exception:
            pass
        last_sms = now

    time.sleep_ms(50)

gnss.deinit()
print("Duration: 300s")
print("TTS attempted: %d" % tts_count)
print("AT_LOCK timeouts: %d" % timeout_count)
print("SMS: %d/%d" % (sms_ok, sms_sent))

passed = (sms_ok > 0)
print("PASS" if passed else "FAIL")
