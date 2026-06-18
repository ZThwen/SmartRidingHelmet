"""
brief 灯光交互式测试（实时模式 + TTS）
note 连上 BLE 后，小程序操作灯光，板子实时处理并显示
     主线程连续 pump，Ctrl+C 退出
     包含 AudioDriver 验证 TTS 播报

用法: python Tests/miniprogram/step_b/09_light_interactive.py
"""
import sys
sys.path.append("../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_TTS_REQUEST,
)
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.sensor.Light import LightSensorDriver
from Modules.light_service import LightService
from Modules.control_service import ControlService
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


def main():
    bus = EventBus()

    print("=" * 50)
    print(" 灯光交互式测试（实时模式）")
    print("=" * 50)

    # 初始化
    print(" 初始化模块...")
    pwm_led = PWMLEDDriver(bus)
    pwm_led.init()
    audio = AudioDriver(bus)
    audio.init()
    light_sensor = LightSensorDriver(bus)
    light_sensor.init()
    light_svc = LightService(bus, pwm_led=pwm_led)
    light_svc.init()
    ble_driver = BLEDriver(bus)
    ble_driver.init()
    ble_svc = BLEService(bus, ble_driver=ble_driver)
    ble_svc.init()
    ctrl = ControlService(event_bus=bus)
    ctrl.init()
    modules = [pwm_led, audio, light_sensor, light_svc, ble_driver, ble_svc, ctrl]

    # 实时打印收到的指令
    def on_ctrl(raw):
        try:
            obj = json.loads(raw.get("raw", ""))
            if obj.get("a") == "ctrl":
                cmd = obj.get("d", {}).get("cmd", "")
                print("  >>> 收到: %s" % cmd)
        except Exception:
            pass
    bus.subscribe(EVENT_RIDE_CONTROL, on_ctrl)

    # 打印状态回推
    def on_state(p):
        t = p.get("t")
        if t == 7:
            print("  <<< ctrl m=%s b=%s v=%s p=%s" % (
                p.get("m"), p.get("b"), p.get("v"), p.get("p")))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, on_state)

    # 打印 TTS 播报
    def on_tts(p):
        print("  [TTS] %s" % p.get("text", ""))
    bus.subscribe(EVENT_TTS_REQUEST, on_tts)

    print(" 微信开发者工具连接 BLE → 按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    # 等待 BLE
    print(" 等待 BLE 连接...")
    for _ in range(200):
        ble_svc.tick()
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            print(" ✓ BLE 已连接")
            break
        time.sleep_ms(100)
    else:
        print(" ✗ BLE 未连接，退出")
        return

    # 排空初始数据
    print(" 排空初始数据...")
    end = time.ticks_ms() + 3000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        bus.pump()

    cs = ctrl._control_state
    print("")
    print("=" * 50)
    print(" 实时模式已启动！Ctrl+C 退出")
    print(" 在小程序上操作灯光，下面即时显示")
    print("=" * 50)
    print(" 初始: PWM=%d%% 显示=%d%% mode=%s" % (
        pwm_led._data.get("duty_cycle", 0),
        pwm_led._data.get("duty_cycle", 0) * 2,
        cs["light_mode"],
    ))

    # 连续 pump 直到 Ctrl+C
    try:
        while True:
            for mod in modules:
                if mod.ctx.get("is_init", False):
                    try:
                        mod.tick()
                    except Exception:
                        pass
            bus.pump()
            time.sleep_ms(10)
    except KeyboardInterrupt:
        pass

    # 最终状态
    cs = ctrl._control_state
    print("")
    print(" 最终: PWM=%d%% 显示=%d%% mode=%s" % (
        pwm_led._data.get("duty_cycle", 0),
        pwm_led._data.get("duty_cycle", 0) * 2,
        cs["light_mode"],
    ))


if __name__ == "__main__":
    main()
