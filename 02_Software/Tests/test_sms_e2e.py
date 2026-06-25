"""
brief SMS 短信发送 E2E 测试
note 使用真实硬件：EC200U 模组 + SIM 卡
      验证：手机号配置、碰撞 SMS 发送、GPS 位置链接、改号
      需要真实手机号用于接收短信
执行: 上传到板子运行 python test_sms_e2e.py
"""
import sys
import time
import json
import gc
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_COLLISION_DETECTED,
    EVENT_ALARM_TRIGGERED, EVENT_SMS_PHONE_CONFIG,
    EVENT_TTS_REQUEST, EVENT_GNSS_READY,
)
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.network.SMS import SMSDriver
from Drivers.network.BLE import BLEDriver
from Modules.alarm_service import AlarmService
from Modules.control_service import ControlService
from Modules.ble_service import BLEService
from Modules.audio_service import AudioService


tts_events = []


def on_tts_request(payload):
    tts_events.append(payload)
    print("  [TTS] %s" % payload.get("text", ""))


def pump_loop(event_bus, modules, duration_s=3):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()


def prompt_and_watch(msg, event_bus, modules, duration_s=5):
    tts_events.clear()
    print("\n  >>> %s" % msg)
    print("  >>> 准备好后按回车开始（%d 秒观察）" % duration_s)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    print("  >>> 开始计时 %d 秒..." % duration_s)
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()
    print("  --- 收到 %d 次 TTS ---" % len(tts_events))


def send_json(event_bus, cmd):
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    event_bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    event_bus.pump()


def main():
    print("=" * 60)
    print(" SMS 端到端测试")
    print("=" * 60)
    print("\n准备：")
    print("  1. 确认 EC200U 已插入 SIM 卡并有网络信号")
    print("  2. 手机打开 NRF Connect 或微信小程序")
    print("  3. 连接头盔 BLE（SmartHelmet-66ccff）")
    print("  4. 准备一台真实手机用于接收短信")
    print("")
    print("  [注意] 测试会发送真实短信，可能产生通信费用！")
    print("  [注意] 请确保接收手机号正确")

    event_bus = EventBus()

    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    sms = SMSDriver(event_bus)
    ble_driver = BLEDriver(event_bus)
    alarm = AlarmService(event_bus, led=led, audio=audio, sms=sms)
    ble_svc = BLEService(event_bus, ble_driver=ble_driver)
    ctrl = ControlService(event_bus)
    audio_svc = AudioService(event_bus, audio_driver=audio)

    init_order = [led, audio, sms, ble_driver, audio_svc, alarm, ble_svc, ctrl]
    modules = [led, audio, sms, ble_driver, audio_svc, alarm, ble_svc, ctrl]

    print("\n[初始化]")
    for mod in init_order:
        try:
            mod.init()
            print("  OK %s" % mod.name)
        except Exception as e:
            print("  FAIL %s: %s" % (mod.name, e))

    event_bus.subscribe(EVENT_TTS_REQUEST, on_tts_request)

    print("\n等待 BLE 连接...")
    print("  连接后按回车开始测试")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    # ==================== 场景 1: BLE 配置手机号（真 E2E） ====================
    print("\n" + "=" * 60)
    print("场景 1: 通过 BLE 配置手机号")
    print("=" * 60)
    print("  在 NRF Connect / 小程序 FFF3 发送:")
    print('    {"a":"ctrl","d":{"cmd":"set_phone","phone":"13xxxxxxxxx"}}')
    print("  （注意格式：a=ctrl, d.cmd=set_phone, d.phone=你的手机号）")
    print("  预期: TTS 播报 '手机号已配置'")
    print("  发送完成后按回车继续...")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    pump_loop(event_bus, modules, 3)
    print("  当前手机号: %s" % alarm._sms_phone)

    if not alarm._sms_phone:
        print("  [WARN] 手机号未通过 BLE 配置，请输入号码手动配置")
        phone = input("  输入接收短信的手机号: ").strip()
        if phone:
            event_bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": phone})
            pump_loop(event_bus, modules, 2)
    else:
        phone = alarm._sms_phone
    gc.collect()

    # ==================== 场景 2: 碰撞后发送 SMS ====================
    print("\n" + "=" * 60)
    print("场景 2: 碰撞后发送 SMS")
    print("=" * 60)
    print("  预期结果:")
    print("    1. 手机收到 SMS: 'SOS:3'")
    print("    2. 头盔播放报警音 + LED 闪烁")
    print("    3. 等待 5-10 秒（SMS 发送需要时间）")
    print("\n  按回车后触发 SOS 报警...")
    print("  FFF3: '{\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_sos\"}}'")
    send_json(event_bus, "alarm_sos")
    prompt_and_watch("触发 SOS 报警 - 看手机是否收到 SMS", event_bus, modules, 15)

    print("\n  取消报警...")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)
    print("  请检查手机是否收到 SMS: 'SOS:3'")
    gc.collect()

    # ==================== 场景 3: 有 GPS 时发送位置链接 ====================
    print("\n" + "=" * 60)
    print("场景 3: 有 GPS 时发送位置链接")
    print("=" * 60)
    print("  预期结果:")
    print("    1. 如果 GNSS 已定位，短信包含高德地图链接")
    print("    2. 格式: 'SOS:3(GPS):https://uri.amap.com/...'")
    print("    3. 点击链接可查看位置")
    print("\n  发布 GNSS 模拟定位数据...")
    event_bus.publish(EVENT_GNSS_READY, {
        "latitude": 39.9042,
        "longitude": 116.4074,
        "altitude": 50,
        "speed": 0,
        "cog": 0,
        "satellites": 10,
        "valid": True,
    })
    pump_loop(event_bus, modules, 1)
    print("  GNSS 缓存: %s" % alarm._gnss_cache)

    print("\n  触发 SOS 报警（含 GPS 信息）...")
    print("  FFF3: '{\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_sos\"}}'")
    send_json(event_bus, "alarm_sos")
    prompt_and_watch("触发 SOS - 检查短信是否含高德地图链接", event_bus, modules, 15)

    print("\n  取消报警...")
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)
    print("  请检查手机收到的 SMS 是否包含高德地图链接")
    gc.collect()

    # ==================== 场景 4: 更换手机号（通过 BLE） ====================
    print("\n" + "=" * 60)
    print("场景 4: 通过 BLE 更换手机号")
    print("=" * 60)
    print("  验证手机号可被重新配置")
    print("  在 NRF Connect / 小程序 FFF3 发送（注意**完整格式**）:")
    print('    {"a":"ctrl","d":{"cmd":"set_phone","phone":"13xxxxxxxxx"}}')
    print("  ⚠️ 必须包含 a 和 d 外层字段，缺一不可")
    print("  预期: TTS 播报 '手机号已配置'")
    print("  请换成另一个手机号")
    print("  在 BLE 工具发送后，按回车继续...")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    pump_loop(event_bus, modules, 3)
    print("  当前手机号: %s" % alarm._sms_phone)

    if alarm._sms_phone == phone or not alarm._sms_phone:
        print("  [WARN] 手机号未更新（JSON 格式是否正确？有无 a/d 外层？）")
        new_phone = input("  手动输入新手机号（绕过 BLE）: ").strip()
        if new_phone:
            event_bus.publish(EVENT_SMS_PHONE_CONFIG, {"phone": new_phone})
            pump_loop(event_bus, modules, 2)
            phone = alarm._sms_phone
    else:
        phone = alarm._sms_phone

    print("\n  触发 SOS 报警 — 检查 SMS 是否发送到新号码...")
    print("  在 NRF Connect / 小程序 FFF3 发送:")
    print('    {"a":"ctrl","d":{"cmd":"alarm_sos"}}')
    print("  发送 alarm_sos 后按回车...")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    send_json(event_bus, "alarm_sos")
    prompt_and_watch("SOS - 新号码是否收到 SMS", event_bus, modules, 15)

    print("\n  取消报警...")
    print("  FFF3: '{\"a\":\"ctrl\",\"d\":{\"cmd\":\"alarm_cancel\"}}'")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    send_json(event_bus, "alarm_cancel")
    pump_loop(event_bus, modules, 2)

    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n检查清单:")
    print("  [ ] 场景 1: 配置手机号 - TTS 播报 '手机号已配置'")
    print("  [ ] 场景 2: 碰撞 SMS - 手机收到 'SOS:3'")
    print("  [ ] 场景 3: GPS 链接 - SMS 含高德地图链接")
    print("  [ ] 场景 4: 更换手机号 - 新号码收到 SMS")
    print("\nSMS 发送记录:")
    print("  手机号: %s" % alarm._sms_phone)
    print("  最后发送成功: %s" % sms._data["last_send_success"])
    print("  发送时间: %d" % sms._data["last_send_time"])

    # 清理资源
    print("\n[清理] 关闭 BLE 广播并释放资源...")
    try:
        ble_driver.deinit()
        sms.deinit()
    except Exception:
        pass
    gc.collect()
    print("[完成]")


if __name__ == "__main__":
    main()
