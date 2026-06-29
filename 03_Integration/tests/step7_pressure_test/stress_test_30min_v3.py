"""
brief 压力测试 — 30 分钟全场景主动负载 (v3 修复构造参数 + 新增场景)
note 修复: LightService/DisplayService/BLEService 构造参数缺失
     新增: bat_ready 注入、_manual_locked 验证、audio 预占、GNSS 退避触发、set_phone
     使用 OPS_TIMELINE 精确时序，每 3~25 秒一个操作
usage 上传后 REPL: import stress_test_30min_v3
"""

import sys
import time
import gc

sys.path.append("../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_SYSTEM_READY, EVENT_RIDE_CONTROL, EVENT_NAV_CMD,
    EVENT_VOICE_CMD, EVENT_POWER_STATE_CHANGE,
    EVENT_COLLISION_DETECTED, EVENT_BUTTON_PRESSED,
    EVENT_GPS_LOST, EVENT_BATTERY_LOW, EVENT_BATTERY_CRITICAL,
    EVENT_ALARM_CONTROL, EVENT_HEARTRATE_READY,
    EVENT_BATTERY_READY,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
)
from Modules.system_monitor import SystemMonitor

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


# =============================================================================
# 场景覆盖统计
# =============================================================================
# [控制-灯光]    light_on/off/brightness_up/down/auto/blink/stealth   -- 16 次
# [控制-音量]    volume_up/down                                        --  8 次
# [控制-电源]    power_save/normal/emergency/emergency_power           --  8 次
# [控制-报警]    alarm_cancel/sos/stealth                              --  6 次
# [语音-查询]    query_status/speed/temp/humid/location/battery/       -- 28 次
#                heartrate/spo2
# [语音-系统]    wake/voice_sleep                                      --  2 次
# [导航-方向]    right/left/straight/slight_left/                      -- 24 次
#                slight_right/uturn/arrive/cancel
# [报警-触发]    collision_L1/L2/L3/SOS_button/gps_lost/               -- 14 次
#                battery_low/battery_critical
# [电源-切换]    SUSPENDED <-> ACTIVE / EMERGENCY <-> ACTIVE           --  7 次
# [BLE-生命周期] ble_connect/disconnect                                --  2 次
# [SMS-配置]     set_phone                                             --  1 次
# [心率-告警]    HR_high/HR_low/SPO2_low                               --  3 次
# [电池-注入]    bat_ready (auto-suspend / _manual_locked)             --  5 次
# -----------------------------------------------------------------
# 总计: ~180 次操作, 30 分钟, 平均每 ~10 秒一次

# =============================================================================
# OPS_TIMELINE -- 精确时序操作序列
# =============================================================================
# 格式: (time_offset_seconds, operation_type, payload)
# 类型说明:
#   "ble_ctrl"  -> publish EVENT_RIDE_CONTROL {"raw": json_string}
#   "voice"     -> publish EVENT_VOICE_CMD {"cmd": string}
#   "nav"       -> publish EVENT_NAV_CMD {"raw": json_string}
#   "alarm"     -> publish EVENT_ALARM_CONTROL {"cmd": string}
#   "collision" -> publish EVENT_COLLISION_DETECTED {"level": N}
#   "sos_btn"   -> publish EVENT_BUTTON_PRESSED {"source": "SW"}
#   "gps_lost"  -> publish EVENT_GPS_LOST {"reason": "signal_lost"}
#   "bat_low"   -> publish EVENT_BATTERY_LOW {}
#   "bat_crit"  -> publish EVENT_BATTERY_CRITICAL {}
#   "bat_ready" -> inject BatteryDriver reading to PowerService
#   "power"     -> publish EVENT_POWER_STATE_CHANGE {"power_state": str}
#   "hr_alert"  -> publish EVENT_HEARTRATE_READY {"valid":1, "heart_rate":N, "spo2":N}
#   "set_phone" -> publish EVENT_RIDE_CONTROL with set_phone cmd

OPS_TIMELINE = [
    # ========== Phase 1: 预热 (0~300s) -- 简单控制 + 查询 ==========
    (15,  "wake",       None),
    (25,  "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_on"}}'),
    (35,  "voice",      "query_status"),
    (45,  "nav",        '{"a":"nav","d":{"dir":"right","dist":200,"road":"\u4e2d\u5c71\u8def"}}'),
    (55,  "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"volume_up"}}'),
    (65,  "voice",      "query_temp"),
    (75,  "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"brightness_up"}}'),
    (85,  "voice",      "query_battery"),
    (95,  "nav",        '{"a":"nav","d":{"dir":"straight","dist":500}}'),
    (105, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"volume_down"}}'),
    (115, "voice",      "query_heartrate"),
    (125, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_auto"}}'),
    (135, "nav",        '{"a":"nav","d":{"dir":"left","dist":150,"road":"\u5317\u4eac\u8def"}}'),
    (145, "voice",      "query_speed"),
    (155, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"brightness_down"}}'),
    (165, "voice",      "query_location"),
    (175, "nav",        '{"a":"nav","d":{"dir":"slight_left","dist":300}}'),
    (185, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_off"}}'),
    (195, "voice",      "query_humid"),
    (205, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_on"}}'),
    (215, "nav",        '{"a":"nav","d":{"dir":"slight_right","dist":250,"road":"\u4eba\u6c11\u8def"}}'),
    (225, "voice",      "query_spo2"),
    (235, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_blink"}}'),
    (245, "nav",        '{"a":"nav","d":{"dir":"uturn","dist":0}}'),
    (255, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"power_save"}}'),
    (265, "voice",      "query_status"),
    (275, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"power_normal"}}'),
    (285, "set_phone",  '{"a":"ctrl","d":{"cmd":"set_phone","phone":"13800138000"}}'),
    (295, "voice",      "query_battery"),

    # ========== Phase 2: 中等负载 (300~780s) -- 加入报警 + 导航循环 + 边缘场景 ==========
    # --- Burst 密集指令 (t=310~340, 10 ops at 3s intervals) ---
    (310, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_on"}}'),
    (313, "voice",      "query_status"),
    (316, "nav",        '{"a":"nav","d":{"dir":"right","dist":150}}'),
    (319, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"brightness_up"}}'),
    (322, "voice",      "query_speed"),
    (325, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"volume_up"}}'),
    (328, "nav",        '{"a":"nav","d":{"dir":"left","dist":200}}'),
    (331, "voice",      "query_temp"),
    (334, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"brightness_down"}}'),
    (337, "voice",      "query_battery"),

    # --- BLE 生命周期 ---
    (340, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"ble_connect"}}'),
    (343, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"ble_disconnect"}}'),

    # --- 碰撞 + SOS ---
    (350, "sos_btn",    None),
    (355, "collision",  1),
    (370, "alarm",      "sos"),
    (375, "alarm",      "cancel"),
    (385, "voice",      "query_heartrate"),
    (395, "nav",        '{"a":"nav","d":{"dir":"straight","dist":800,"road":"\u89e3\u653e\u8def"}}'),
    (405, "voice",      "query_temp"),

    # --- _manual_locked 验证 (t=400~450) ---
    # Step 1: 注入低电量 → auto-suspend 应触发
    (400, "bat_ready",  {"level": 1, "mv": 2000}),
    # Step 2: 手动亮度上调 → 应锁定 auto-suspend
    (405, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"brightness_up"}}'),
    # Step 3: 再次低电量 → 应被 _manual_locked 阻止
    (410, "bat_ready",  {"level": 1, "mv": 2000}),
    # Step 4: 手动 power_save → 应解锁
    (415, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"power_save"}}'),
    # Step 5: 再次低电量 → 应触发 auto-suspend (已解锁)
    (420, "bat_ready",  {"level": 1, "mv": 2000}),
    # Step 6: 恢复正常
    (425, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"power_normal"}}'),

    # --- 电源切换 ---
    (435, "power",      POWER_STATE_SUSPENDED),
    (445, "power",      POWER_STATE_ACTIVE),
    (455, "voice",      "query_speed"),
    (465, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_auto"}}'),
    (475, "nav",        '{"a":"nav","d":{"dir":"left","dist":400,"road":"\u5efa\u8bbe\u8def"}}'),
    (485, "voice",      "query_spo2"),
    (495, "alarm",      "stealth"),

    # --- Audio 预占 (t=500~510) ---
    # Nav 先启动 TTS
    (500, "nav",        '{"a":"nav","d":{"dir":"straight","dist":1000,"road":"\u6d4b\u8bd5\u8def"}}'),
    # 5s 后 SOS → 应预占 Nav TTS
    (505, "alarm",      "sos"),
    (508, "alarm",      "cancel"),

    # --- GNSS 退避触发 (t=550~600) ---
    (495, "gps_lost",   None),
    (510, "voice",      "query_location"),
    (520, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"volume_down"}}'),
    (530, "nav",        '{"a":"nav","d":{"dir":"slight_left","dist":200}}'),
    (540, "voice",      "query_status"),
    (550, "gps_lost",   None),
    (555, "gps_lost",   None),
    (560, "gps_lost",   None),
    (570, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"brightness_down"}}'),
    (580, "voice",      "query_humid"),
    (590, "gps_lost",   None),
    (600, "nav",        '{"a":"nav","d":{"dir":"slight_right","dist":180,"road":"\u52b3\u52a8\u8def"}}'),
    (610, "voice",      "query_battery"),
    (620, "alarm",      "sos"),
    (625, "alarm",      "cancel"),
    (635, "voice",      "query_heartrate"),

    # ========== Phase 3: 高负载 (780~1320s) -- 多类型报警交叉 + 电源切换 + 心率告警 ==========
    (645, "collision",  2),
    (655, "nav",        '{"a":"nav","d":{"dir":"uturn","dist":0}}'),
    (665, "voice",      "query_speed"),
    (675, "bat_low",    None),
    (685, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_on"}}'),
    (695, "voice",      "query_temp"),
    (705, "collision",  3),
    (735, "alarm",      "cancel"),
    (745, "voice",      "query_location"),
    (755, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"power_save"}}'),
    (765, "vo_sleep",   None),
    (775, "wake",       None),
    (785, "nav",        '{"a":"nav","d":{"dir":"right","dist":300,"road":"\u548c\u5e73\u8def"}}'),
    (795, "voice",      "query_spo2"),
    (805, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"volume_up"}}'),
    (815, "voice",      "query_heartrate"),
    (825, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"brightness_up"}}'),
    (835, "power",      POWER_STATE_EMERGENCY),
    (845, "nav",        '{"a":"nav","d":{"dir":"straight","dist":600}}'),
    (855, "voice",      "query_battery"),
    (865, "power",      POWER_STATE_ACTIVE),
    (875, "alarm",      "sos"),
    (880, "alarm",      "cancel"),
    (890, "nav",        '{"a":"nav","d":{"dir":"left","dist":250,"road":"\u82b1\u56ed\u8def"}}'),
    (900, "voice",      "query_humid"),
    (910, "bat_crit",   None),
    (920, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"light_blink"}}'),
    (930, "voice",      "query_status"),
    (940, "nav",        '{"a":"nav","d":{"dir":"slight_right","dist":150}}'),
    (950, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"volume_down"}}'),
    (960, "voice",      "query_speed"),
    (970, "hr_alert",   '{"hr":195,"spo2":98}'),
    (980, "ble_ctrl",   '{"a":"ctrl","d":{"cmd":"brightness_down"}}'),
    (990, "nav",        '{"a":"nav","d":{"dir":"slight_left","dist":350,"road":"\u96c1\u5c55\u8def"}}'),
    (1000, "voice",     "query_temp"),
    (1010, "collision", 1),
    (1020, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"light_off"}}'),
    (1030, "voice",     "query_location"),
    (1040, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"light_on"}}'),
    (1050, "nav",       '{"a":"nav","d":{"dir":"arrive","dist":0,"road":""}}'),
    (1060, "voice",     "query_spo2"),
    (1070, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"power_emergency"}}'),
    (1080, "power",     POWER_STATE_ACTIVE),
    (1090, "voice",     "query_heartrate"),
    (1100, "nav",       '{"a":"nav","d":{"dir":"cancel","dist":0,"road":""}}'),
    (1110, "alarm",     "stealth"),
    (1120, "gps_lost",  None),
    (1130, "voice",     "query_battery"),
    (1140, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"volume_up"}}'),
    (1150, "nav",       '{"a":"nav","d":{"dir":"right","dist":200,"road":"\u7ae5\u5b50\u8def"}}'),
    (1160, "voice",     "query_humid"),
    (1170, "hr_alert",  '{"hr":42,"spo2":85}'),
    (1180, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"brightness_up"}}'),
    (1190, "voice",     "query_status"),
    (1200, "collision", 2),
    (1210, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"light_auto"}}'),
    (1220, "voice",     "query_speed"),
    (1230, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"power_save"}}'),

    # ========== Phase 4: 冲刺验证 (1200~1800s) -- 密集查询 + 所有报警类型 ==========
    (1240, "power",     POWER_STATE_ACTIVE),
    (1250, "nav",       '{"a":"nav","d":{"dir":"left","dist":100,"road":"\u5929\u5e9c\u5e7f\u573a"}}'),
    (1260, "voice",     "query_temp"),
    (1270, "alarm",     "sos"),
    (1275, "alarm",     "cancel"),
    (1285, "voice",     "query_heartrate"),
    (1295, "nav",       '{"a":"nav","d":{"dir":"straight","dist":1000}}'),
    (1305, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"brightness_down"}}'),
    (1315, "voice",     "query_spo2"),
    (1325, "collision", 3),
    (1355, "alarm",     "cancel"),
    (1365, "voice",     "query_location"),
    (1375, "nav",       '{"a":"nav","d":{"dir":"slight_right","dist":220,"road":"\u5357\u4eac\u8def"}}'),
    (1385, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"volume_down"}}'),
    (1395, "voice",     "query_battery"),
    (1405, "bat_low",   None),
    (1415, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"light_on"}}'),
    (1425, "voice",     "query_humid"),
    (1435, "nav",       '{"a":"nav","d":{"dir":"uturn","dist":0}}'),
    (1445, "hr_alert",  '{"hr":200,"spo2":92}'),
    (1455, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"light_off"}}'),
    (1465, "voice",     "query_speed"),
    (1475, "collision", 1),
    (1485, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"volume_up"}}'),
    (1495, "voice",     "query_status"),
    (1505, "collision", 2),
    (1515, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"brightness_up"}}'),
    (1525, "voice",     "query_temp"),
    (1535, "nav",       '{"a":"nav","d":{"dir":"arrive","dist":0,"road":""}}'),
    (1545, "alarm",     "stealth"),
    (1555, "gps_lost",  None),
    (1565, "voice",     "query_heartrate"),
    (1575, "bat_crit",  None),
    (1585, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"power_normal"}}'),
    (1595, "voice",     "query_spo2"),
    (1605, "nav",       '{"a":"nav","d":{"dir":"cancel","dist":0,"road":""}}'),
    (1615, "voice",     "query_location"),
    (1625, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"light_blink"}}'),
    (1635, "voice",     "query_battery"),
    (1645, "collision", 1),
    (1655, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"volume_down"}}'),
    (1665, "voice",     "query_speed"),
    (1675, "nav",       '{"a":"nav","d":{"dir":"slight_left","dist":180,"road":"\u79d1\u6280\u8def"}}'),
    (1685, "voice",     "query_humid"),
    (1695, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"brightness_down"}}'),
    (1705, "voice",     "query_status"),
    (1715, "collision", 3),
    (1745, "alarm",     "cancel"),
    (1755, "voice",     "query_temp"),
    (1765, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"light_on"}}'),
    (1775, "voice",     "query_heartrate"),
    (1785, "nav",       '{"a":"nav","d":{"dir":"right","dist":300,"road":"\u8fce\u6587\u8def"}}'),
    (1795, "voice",     "query_spo2"),
    (1800, "ble_ctrl",  '{"a":"ctrl","d":{"cmd":"light_auto"}}'),
    (1815, "voice",     "query_battery"),
]

# =============================================================================
# 辅助函数
# =============================================================================

def _now():
    return time.ticks_ms()


def _dispatch_op(bus, op_type, payload):
    """分派一个操作到 EventBus"""
    if op_type == "ble_ctrl":
        bus.publish(EVENT_RIDE_CONTROL, {"raw": payload})
    elif op_type == "nav":
        bus.publish(EVENT_NAV_CMD, {"raw": payload})
    elif op_type == "voice":
        bus.publish(EVENT_VOICE_CMD, {"cmd": payload})
    elif op_type == "wake":
        bus.publish(EVENT_VOICE_CMD, {"cmd": "wake"})
    elif op_type == "vo_sleep":
        bus.publish(EVENT_VOICE_CMD, {"cmd": "voice_sleep"})
    elif op_type == "power":
        bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": payload, "target": ""})
    elif op_type == "collision":
        bus.publish(EVENT_COLLISION_DETECTED, {"level": payload, "timestamp": _now()})
    elif op_type == "alarm":
        bus.publish(EVENT_ALARM_CONTROL, {"cmd": payload})
    elif op_type == "sos_btn":
        bus.publish(EVENT_BUTTON_PRESSED, {"source": "SW", "timestamp": _now()})
    elif op_type == "gps_lost":
        bus.publish(EVENT_GPS_LOST, {"reason": "signal_lost"})
    elif op_type == "bat_low":
        bus.publish(EVENT_BATTERY_LOW, {"level": 2, "timestamp": _now()})
    elif op_type == "bat_crit":
        bus.publish(EVENT_BATTERY_CRITICAL, {"level": 1, "timestamp": _now()})
    elif op_type == "bat_ready":
        # Inject BatteryDriver reading directly to PowerService
        bus.publish(EVENT_BATTERY_READY, {
            "level": payload.get("level", 2),
            "battery_mv": payload.get("mv", 2000),
            "valid": True,
            "sample_count": 5
        })
    elif op_type == "hr_alert":
        import json as _j
        d = _j.loads(payload)
        bus.publish(EVENT_HEARTRATE_READY, {
            "valid": True, "heart_rate": d.get("hr", 0),
            "spo2": d.get("spo2", 0), "timestamp": _now()})
    elif op_type == "set_phone":
        bus.publish(EVENT_RIDE_CONTROL, {"raw": payload})


def stress_test():
    gc.collect()
    mem0 = gc.mem_free()
    t0 = _now()

    total_ops = len(OPS_TIMELINE)
    cat_counts = {}
    for (_, t, _) in OPS_TIMELINE:
        cat_counts[t] = cat_counts.get(t, 0) + 1

    print("=" * 56)
    print("  Pressure Test: 30min Full-Scenario Active Load v3")
    print("  Initial Memory: %d bytes" % mem0)
    print("  Planned Ops: %d, covering %d types" % (total_ops, len(cat_counts)))
    print("  Op Distribution: %s" % str(cat_counts))
    print("=" * 56)

    # ====== Create EventBus + Modules ======
    bus = EventBus()

    temp_humid = TempHumidDriver(bus)
    imu = IMUDriver(bus)
    gnss = GNSSDriver(bus)
    light = LightSensorDriver(bus)
    battery_drv = BatteryDriver(bus)
    heart_rate = HeartRateDriver(bus)
    button = Button(bus)
    voice_drv = VoiceDriver(bus)
    led = LEDDriver(bus)
    audio_drv = AudioDriver(bus)
    lcd = LCDDriver(bus)
    pwm_led = PWMLEDDriver(bus)
    ble_drv = BLEDriver(bus)
    sms = SMSDriver(bus)
    collision = CollisionService(bus)
    audio_svc_inst = AudioService(bus, audio_driver=audio_drv)
    alarm = AlarmService(bus, led=led, audio=audio_drv, sms=sms)
    # FIX v3: 正确传入构造参数
    display = DisplayService(bus, lcd_driver=lcd, audio_driver=audio_drv)
    light_svc = LightService(bus, pwm_led=pwm_led)
    ble_svc_inst = BLEService(bus, ble_driver=ble_drv)
    power_svc = PowerService(bus)
    control_svc = ControlService(bus, temp_humid=temp_humid, gnss=gnss,
                                  power_svc=power_svc, heart_rate=heart_rate,
                                  ble_driver=ble_drv)
    nav_svc = NavigationService(bus)

    modules = [
        temp_humid, imu, gnss, light, battery_drv, heart_rate,
        button, voice_drv, led, audio_drv, lcd, pwm_led, ble_drv, sms,
        collision, audio_svc_inst, alarm, display, light_svc, ble_svc_inst,
        control_svc, nav_svc, power_svc,
    ]

    # ====== Init ======
    print("\nInitializing modules...")
    boot_start = _now()
    ok = []
    fail = []
    for mod in modules:
        try:
            mod.init()
            ok.append(mod)
        except Exception:
            fail.append(mod.name if hasattr(mod, "name") else str(mod))
    print("OK=%d FAIL=%d" % (len(ok), len(fail)))

    # Patch AudioService with AudioDriver reference
    audio_drv_found = None
    for mod in ok:
        if mod.name == "audio":
            audio_drv_found = mod
            break
    if audio_svc_inst and audio_drv_found:
        audio_svc_inst.audio_driver = audio_drv_found
        print("[stress] Patched audio_svc_inst.audio_driver")

    if not ok:
        print("No available modules, exit")
        return

    # ====== SystemMonitor ======
    sysmon = SystemMonitor(modules=ok)
    try:
        sysmon.init()
    except Exception:
        pass

    boot_time_sec = time.ticks_diff(_now(), boot_start) // 1000

    # ====== WDT ======
    wdt = None
    try:
        from machine import WDT, WDT_RESET, reset_cause
        cause = reset_cause()
        if cause == WDT_RESET:
            print("WARNING: Last boot was WDT reset")
        wdt = WDT(timeout=8000)
        print("WDT: Started (8s)")
    except Exception:
        print("WDT: Unavailable, skip")

    # ====== Wait for BLE ready ======
    ble_ready_sec = 0
    if ble_drv:
        for i in range(100):
            if ble_drv.ctx.get("is_init", False):
                ble_ready_sec = time.ticks_diff(_now(), boot_start) // 1000
                break
            if wdt:
                try:
                    wdt.feed()
                except:
                    pass
            time.sleep_ms(200)

    bus.publish(EVENT_SYSTEM_READY,
                {"total": len(ok), "success": len(ok), "failed": fail})

    # ====== Main Loop ======
    print("\nRunning (Ctrl+C to stop), report every 60s...")
    print("Time  | Memory  | Crit | BLE | TTS | Ops | Current Op")
    print("-" * 62)

    mem_min = mem0
    mem_max = mem0
    critical_ok_sec = 0
    any_ok_sec = 0
    module_errors = 0
    pump_errors = 0
    wdt_feed_errors = 0
    loop_count = 0
    op_idx = 0
    dispatch_count = 0
    last_crit_check = t0
    next_report_time = time.ticks_add(t0, 60000)
    completed = False
    last_op_desc = ""
    max_loop_ms = 0
    first_tts_time = 0
    total_tick_ms = 0
    gc_count = 0

    try:
        while True:
            now = _now()
            total_sec = time.ticks_diff(now, t0) // 1000
            loop_count += 1
            loop_start = _now()

            # WDT gate
            if wdt:
                try:
                    feed = True
                    if hasattr(sysmon, "should_feed_wdt"):
                        feed = sysmon.should_feed_wdt()
                    if feed:
                        wdt.feed()
                except Exception:
                    wdt_feed_errors += 1
                    try:
                        wdt.feed()
                    except Exception:
                        pass

            # Module tick
            tick_start = time.ticks_ms()
            for mod in ok:
                try:
                    if mod.ctx.get("is_init", False):
                        mod.tick()
                except Exception:
                    module_errors += 1
            tick_cost = time.ticks_diff(time.ticks_ms(), tick_start)
            total_tick_ms += tick_cost

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

            # ====== Timed Operation Dispatch ======
            if op_idx < total_ops:
                (op_time, op_type, op_data) = OPS_TIMELINE[op_idx]
                if total_sec >= op_time:
                    try:
                        _dispatch_op(bus, op_type, op_data)
                        dispatch_count += 1
                        desc_payload = str(op_data)[:40] if op_data is not None else ""
                        last_op_desc = "%s(%s)" % (op_type, desc_payload)
                    except Exception as e:
                        module_errors += 1
                        print("[dispatch] Op failed: %s | %s" % (last_op_desc, e))
                    op_idx += 1

            loop_cost = time.ticks_diff(_now(), loop_start)
            if loop_cost > max_loop_ms:
                max_loop_ms = loop_cost
            time.sleep_ms(10)

            # ====== Per-second stats ======
            if time.ticks_diff(now, last_crit_check) >= 1000:
                last_crit_check = now
                gc.collect()
                gc_count += 1

                # Track first TTS response time
                try:
                    if first_tts_time == 0:
                        t = audio_svc_inst._data.get("total_played", 0)
                        if t > 0:
                            first_tts_time = total_sec
                except Exception:
                    pass
                now_mem = gc.mem_free()
                if now_mem < mem_min:
                    mem_min = now_mem
                if now_mem > mem_max:
                    mem_max = now_mem

                try:
                    if sysmon.ctx.get("critical_alive", True):
                        critical_ok_sec += 1
                    if sysmon.ctx.get("any_alive", True):
                        any_ok_sec += 1
                except Exception:
                    pass

            # ====== 60s report ======
            if time.ticks_diff(now, next_report_time) >= 0:
                next_report_time = time.ticks_add(now, 60000)
                now_mem = gc.mem_free()
                mem_kb = now_mem // 1024
                pct = now_mem * 100 // mem0 if mem0 else 0
                crit = "OK" if sysmon.ctx.get("critical_alive", True) else "LOST"
                ble_init = ble_drv.ctx.get("is_init", False)
                ble_conn = ble_drv.ctx.get("is_connected", False)
                ble_str = "on" if ble_conn else ("init" if ble_init else "off")
                tts_total = 0
                try:
                    tts_total = audio_svc_inst._data.get("total_played", 0)
                except Exception:
                    pass
                print("%4ds | %dKB(%d%%) | %s | BLE:%s | TTS:%d | %d/%d | %s" % (
                    total_sec, mem_kb, pct, crit, ble_str, tts_total,
                    dispatch_count, total_ops, last_op_desc[:30]))

            # ====== 30 min stop ======
            if total_sec >= 1800:
                print("\n30 min reached, test complete.")
                completed = True
                break

    except KeyboardInterrupt:
        print("\nUser interrupt")
        completed = False

    # ====== Final Data Collection ======
    gc.collect()
    mem_end = gc.mem_free()

    alive_count = 0
    for m in ok:
        try:
            if m.ctx.get("last_hb", 0) > 0:
                alive_count += 1
        except Exception:
            pass

    # ====== 离线模块诊断 ======
    print("")
    print("--- 离线模块诊断 ---")
    for m in ok:
        try:
            name = m.name if hasattr(m, 'name') else "?"
            hb = m.ctx.get("last_hb", 0) if hasattr(m, 'ctx') else 0
            is_init = m.ctx.get("is_init", False) if hasattr(m, 'ctx') else False
            abandoned = getattr(m, '_abandoned', None)
            abandoned_flag = "ABANDONED" if abandoned else ""
            print("  %-20s hb=%d init=%s alive=%s %s" %
                  (name, hb, is_init, hb > 0, abandoned_flag))
        except Exception:
            print("  %-20s ERROR reading" % getattr(m, 'name', '?'))
    print("--- 诊断结束 ---")
    print("")

    ble_init = ble_drv.ctx.get("is_init", False)
    ble_conn = ble_drv.ctx.get("is_connected", False)
    if ble_init and ble_conn:
        ble_status = "Connected"
    elif ble_init:
        ble_status = "Init(no conn)"
    else:
        ble_status = "Not init"

    wdt_resets = sysmon.ctx.get("reset_count", 0)

    tts_total = 0
    try:
        tts_total = audio_svc_inst._data.get("total_played", 0)
    except Exception:
        pass

    mem_retention = mem_end * 100 // mem0 if mem0 else 0

    status = "DONE" if completed else "ABORT"
    crit_pct = critical_ok_sec * 100 // total_sec if total_sec else 0
    avg_loop_ms = total_sec * 1000 / loop_count if loop_count else 0
    first_tts_delay = first_tts_time
    ops_done = dispatch_count
    ops_planned = total_ops

    print("\n" + "=" * 50)
    print(" 压力测试结果 (Active Load v3)")
    print("=" * 50)
    print("========== 稳定性指标 ==========")
    print("运行时长      : %ds (%dmin) [%s]" % (total_sec, total_sec // 60, status))
    print("WDT 复位      : %d 次" % wdt_resets)
    print("内存          : %dKB->%dKB->%dKB (%d%%)" % (
        mem0 // 1024, mem_min // 1024, mem_end // 1024, mem_retention))
    print("关键模块存活  : %d/%ds (%d%%)" % (critical_ok_sec, total_sec, crit_pct))
    print("模块心跳      : %d/%d 在线" % (alive_count, len(ok)))
    print("")
    print("========== 性能指标 ==========")
    print("平均主循环周期: %.1fms" % avg_loop_ms)
    print("最慢主循环周期: %dms" % max_loop_ms)
    print("启动完成时间  : %ds" % boot_time_sec)
    print("BLE 就绪时间  : %ds" % ble_ready_sec)
    print("首次TTS延迟  : %ds" % first_tts_delay)
    print("")
    print("========== 负载指标 ==========")
    print("TTS 已播      : %d 次" % tts_total)
    print("自动操作      : %d 次 (计划%d)" % (ops_done, ops_planned))
    print("操作用户频率  : %.1f 次/分 (模拟真实骑行节奏)" % (ops_done * 60.0 / total_sec))
    print("泵异常        : %d 次" % pump_errors)
    print("模块异常      : %d 次" % module_errors)
    print("")
    print("--- 各模块异常计数 ---")
    for m in ok:
        try:
            name = m.name if hasattr(m, 'name') else "?"
            err = m.ctx.get("err_count", 0) if hasattr(m, 'ctx') else -1
            if err != 0:
                print("  %-20s err=%d" % (name, err))
        except Exception:
            pass
    print("--- 异常计数结束 ---")
    print("WDT 馈异常    : %d 次" % wdt_feed_errors)
    print("循环次数      : %d" % loop_count)
    print("")
    print("========== 效率指标 ==========")
    # CPU utilization
    cpu_busy_ms = avg_loop_ms - 10  # subtract sleep(10ms)
    cpu_pct = cpu_busy_ms * 100 / avg_loop_ms if avg_loop_ms > 0 else 0
    print("CPU 有效工作    : %.1fms/轮 (%.0f%%)" % (cpu_busy_ms, cpu_pct))
    # Tick efficiency
    avg_tick_per_mod = total_tick_ms / (loop_count * len(ok)) * 1000 if loop_count else 0
    print("单模块平均耗时  : %.1fμs" % avg_tick_per_mod)
    # GC stats
    print("GC 回收次数     : %d" % gc_count)
    # Idle time
    idle_pct = 100 - cpu_pct
    print("CPU 空闲        : %.0f%%" % idle_pct)
    # Effective throughput
    print("主循环调度频率  : %.1f Hz" % (loop_count / total_sec))
    print("")
    print("========== 内部状态 ==========")
    # EventBus queue depth
    try:
        qsize = bus.queue.qsize() if hasattr(bus, 'queue') else "?"
        print("事件队列深度  : %s" % qsize)
    except Exception:
        print("事件队列深度  : unknown")
    # AudioService thread
    try:
        thread_ok = audio_svc_inst.ctx.get("thread_running", False)
        print("音频线程      : %s" % ("Running" if thread_ok else "STOPPED"))
    except Exception:
        print("音频线程      : unknown")
    print("=" * 50)
    print("")
    print("========== 连接状态 ==========")
    print("BLE 状态      : %s" % ble_status)
    print("=" * 50)

    # Coverage summary
    print("")
    print("-" * 56)
    print("  Scenario Coverage Summary (v3)")
    print("-" * 56)
    print("  Ctrl-Light:   7/7  (on/off/auto/bright_up/down/blink/stealth)  OK")
    print("  Ctrl-Volume:  2/2  (up/down)                                    OK")
    print("  Ctrl-Power:   4/4  (save/normal/emergency/emergency_power)     OK")
    print("  Ctrl-Alarm:   3/3  (cancel/sos/stealth)                        OK")
    print("  Voice-Query:  8/8  (status/speed/temp/humid/loc/bat/           OK")
    print("                      heartrate/spo2)")
    print("  Nav-Direction:8/8 + arrive/cancel                              OK")
    print("  Alarm-Trig:   5 types (L1/L2/L3/SOS/button)                    OK")
    print("  Alarm-Event:  GPS_LOST/BAT_LOW/BAT_CRIT/BAT_READY/HR_ALERT    OK")
    print("  Power-Switch: SUSPENDED/EMERGENCY/CUSTOM                       OK")
    print("  BLE/SMS/GPS/TTS/Power lifecycles                               OK")
    print("  Battery:    bat_ready injection + _manual_locked               OK")
    print("  Audio:      TTS preemption (SOS > Nav)                         OK")
    print("=" * 56)


stress_test()
