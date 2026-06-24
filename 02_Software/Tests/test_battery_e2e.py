"""
brief PowerService 电池检测 E2E 测试
note 需要硬件（电池扩展板 + NUCLEO-F413ZH + EC200U）
     上传到板子运行 python test_battery_e2e.py
     每个场景前暂停，让用户观察 TTS/状态变化

场景：
1. ADC 读数 + BLE 推送 + 实时电量监控
2. 语音 query_battery → TTS 播报"当前电量X档"
3. 低电量自动省电（自然发生，无需手动模拟）
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
import json
from core.config import (
    EVENT_BATTERY_READY,
    EVENT_TTS_REQUEST,
    EVENT_RIDE_CONTROL,
    EVENT_VOICE_CMD,
)
from Drivers.sensor.Battery import BatteryDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.network.BLE import BLEDriver
from Drivers.interface.Voice import VoiceDriver
from Modules.power_service import PowerService
from Modules.audio_service import AudioService
from Modules.control_service import ControlService
from Modules.ble_service import BLEService


class FakeUART:
    """模拟 UART，可预设接收缓冲区"""
    def __init__(self):
        self._buf = bytearray()

    def any(self):
        return len(self._buf)

    def read(self, n):
        data = self._buf[:n]
        self._buf = self._buf[n:]
        return bytes(data)

    def put(self, byte_val):
        self._buf.append(byte_val)


# ==================== 工具函数 ====================

tts_events = []


def on_tts_request(payload):
    tts_events.append(payload)
    print("  [TTS] %s" % payload.get("text", ""))


def on_battery_ready(payload):
    if payload.get("valid"):
        print("  [BAT] raw=%d adc=%dmV battery=%dmV level=%d" % (
            payload.get("raw", 0), payload.get("adc_mv", 0),
            payload.get("battery_mv", 0), payload.get("level", 0)))


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
        time.sleep_ms(50)


def prompt_and_watch(msg, duration_s=5):
    tts_events.clear()
    print("\n  >>> %s" % msg)
    print("  >>> 按回车开始（%d 秒观察）" % duration_s)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    print("  >>> 计时 %d 秒..." % duration_s)


# ==================== 场景 ====================

def main():
    print("=" * 60)
    print(" PowerService 电池检测 E2E 测试")
    print("=" * 60)
    print("\n准备：")
    print("  1. 电池扩展板已连接 ADC PC4")
    print("  2. 手机打开小程序或 NRF Connect")
    print("  3. 连接头盔 BLE（SmartHelmet-66ccff）")

    event_bus = EventBus()

    # 创建模块
    battery_drv = BatteryDriver(event_bus)
    audio = AudioDriver(event_bus)
    audio_svc = AudioService(event_bus, audio_driver=audio)
    ble_driver = BLEDriver(event_bus)
    ble_svc = BLEService(event_bus, ble_driver=ble_driver)
    voice = VoiceDriver(event_bus)
    power_svc = PowerService(event_bus)
    ctrl = ControlService(event_bus, power_svc=power_svc)

    modules = [battery_drv, audio, audio_svc, ble_driver, ble_svc, voice, power_svc, ctrl]

    # 初始化
    print("\n[初始化]")
    for mod in modules:
        try:
            mod.init()
            print("  OK %s" % mod.name)
        except Exception as e:
            print("  FAIL %s: %s" % (mod.name, e))

    event_bus.subscribe(EVENT_TTS_REQUEST, on_tts_request)
    event_bus.subscribe(EVENT_BATTERY_READY, on_battery_ready)

    # E2E 测试用：缩短电池采样间隔到 1 秒，方便观察
    battery_drv.cfg["sample_ms"] = 1000

    # 等待 BLE 连接
    print("\n等待 BLE 连接...")
    print("  手机连接头盔后按回车开始测试")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    # ==================== 场景 1: ADC 读数 + BLE 推送 ====================
    print("\n" + "=" * 60)
    print("场景 1: ADC 读数 + BLE 推送 + 实时电量监控")
    print("=" * 60)
    print("  预期: 每 1 秒打印 [BAT] raw/adc/battery/level, BLE push 含 bat 字段")
    print("  如果 level≤2，会自动触发 TTS '电量不足' + 省电模式")
    prompt_and_watch("观察实时电量数据（15 秒）", 15)
    pump_loop(event_bus, modules, 10)

    data = power_svc.get_data()
    print("\n  最终状态: level=%d, battery_mv=%d, is_low=%s, power_mode=%s, auto_suspended=%s" % (
        data["level"], data["battery_mv"], data["is_low"],
        data["power_mode"], data["auto_suspended"]))
    print("  [检查] 小程序环境卡片是否显示电量")

    # ==================== 场景 2: BLE 指令查询电量 ====================
    print("\n" + "=" * 60)
    print("场景 2: BLE 指令查询电量（BLEService → ControlService → TTS）")
    print("=" * 60)
    print("  链路: BLE FFF3 → _on_ble_data → cmd_buffer → _parse_and_route → EVENT_RIDE_CONTROL")
    print("  预期: TTS 播报'当前电量X档'")
    prompt_and_watch("BLE 查询电量", 8)
    raw = json.dumps({"a": "ctrl", "d": {"cmd": "query_battery"}})
    ble_svc._on_ble_data({"uuid": 0xFFF3, "value": raw})
    pump_loop(event_bus, modules, 3)

    if tts_events:
        print("  TTS: %s" % tts_events[-1].get("text"))
    else:
        print("  [WARN] 未收到 TTS")

    # ==================== 场景 3: 语音指令查询电量 ====================
    print("\n" + "=" * 60)
    print("场景 3: 语音指令查询电量（VoiceDriver → ControlService → TTS）")
    print("=" * 60)
    print("  链路: UART 0x13 → VoiceDriver.tick → _handle_hex → VOICE_CMD_MAP → EVENT_VOICE_CMD")
    print("  预期: TTS 播报'当前电量X档'")
    # 注入 FakeUART（E2E 中 VoiceDriver 已 init，需要替换 uart）
    fake_uart = FakeUART()
    voice.uart = fake_uart
    prompt_and_watch("语音查询电量", 8)
    fake_uart.put(0x13)  # 0x13 = query_battery
    pump_loop(event_bus, modules, 3)

    if tts_events:
        print("  TTS: %s" % tts_events[-1].get("text"))
    else:
        print("  [WARN] 未收到 TTS")

    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n检查清单:")
    print("  [ ] ADC 读数: [BAT] 日志正常输出")
    print("  [ ] BLE 推送: merged push 含 bat 字段")
    print("  [ ] BLE 指令查询: TTS 播报'当前电量X档'")
    print("  [ ] 语音指令查询: TTS 播报'当前电量X档'")
    if data["is_low"]:
        print("  [ ] 低电量: 自动省电 + TTS '电量不足'（已触发）")
    else:
        print("  [ ] 低电量: 电池电量正常，未触发省电")


if __name__ == "__main__":
    main()
