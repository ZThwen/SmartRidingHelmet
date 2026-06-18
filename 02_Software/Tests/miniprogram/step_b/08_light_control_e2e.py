"""
brief 远程灯光控制 E2E 测试
note 专注验证小程序「远端控制」页灯光功能全链路
     ！！！
     核心验证：小程序点击 → BLE FFF3 发送 → 板子接收并执行
     每步都有预期输出，对比实际日志即可定位断点
     ！！！

执行: 上传到板子运行 python Tests/miniprogram/step_b/.../test_light_control_e2e.py
小程序: 打开「远端控制」页，连接 BLE
"""
import sys
sys.path.append("../../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_LIGHT_CONTROL, EVENT_POWER_STATE_CHANGE,
)
from Drivers.network.BLE import BLEDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.sensor.Light import LightSensorDriver
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.light_service import LightService


_LOG_PATH = "Tests/miniprogram/step_b/08_light_control_e2e.log"
_T0 = 0
_cmd_log = []
_state_pushes = []
_light_events = []


def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    line = "[%7.2fs] %s" % (elapsed / 1000.0, msg)
    print(line)
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def on_ride_control(payload):
    raw = payload.get("raw", "")
    try:
        obj = json.loads(raw)
        if obj.get("a") == "ctrl":
            cmd = obj.get("d", {}).get("cmd", "")
            _cmd_log.append(cmd)
            log("  [BLE RX] FFF3: %s" % raw)
    except Exception:
        pass


def on_control_state(payload):
    _state_pushes.append(payload)
    t = payload.get("t")
    if t == 7:
        log("  [PUSH t=7] m=%s b=%s v=%s p=%s" % (
            payload.get("m"), payload.get("b"), payload.get("v"), payload.get("p")))
    elif t == 8:
        log("  [PUSH t=8] v=%s" % payload.get("v"))
    elif t == 9:
        log("  [PUSH t=9] p=%s" % payload.get("p"))


def on_light_control(payload):
    _light_events.append(payload)
    log("  [LIGHT_EVENT] cmd=%s" % payload.get("cmd"))


def pump_for(bus, modules, duration_ms):
    end = time.ticks_ms() + duration_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        bus.pump()


def wait_ble(bus, ble_svc, timeout_s=20):
    log("▶ 等待 BLE 连接...")
    end = time.ticks_ms() + timeout_s * 1000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            return True
        time.sleep_ms(100)
    return False


def check(step, ok, detail=""):
    if ok:
        log("  ✓ %s" % step)
    else:
        log("  ✗ %s %s" % (step, detail))


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 55)
    print(" 远程灯光控制 E2E 测试")
    print("=" * 55)
    print("")
    print(" 测试前确认：")
    print("  1. 微信开发者工具打开小程序「远端控制」页")
    print("  2. 已连接 BLE（SmartHelmet-66ccff）")
    print("  3. 观察板子串口 + 小程序调试台")
    print("")

    bus = EventBus()

    # 初始化
    log("初始化模块...")
    pwm_led = PWMLEDDriver(bus)
    pwm_led.init()
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
    modules = [pwm_led, light_sensor, light_svc, ble_driver, ble_svc, ctrl]

    # 订阅事件
    bus.subscribe(EVENT_RIDE_CONTROL, on_ride_control)
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, on_control_state)
    bus.subscribe(EVENT_LIGHT_CONTROL, on_light_control)

    # 等待 BLE
    log("请在微信开发者工具中连接 BLE，连接后按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    if not wait_ble(bus, ble_svc, 15):
        log("✗ BLE 未连接")
        return
    log("✓ BLE 已连接")
    pump_for(bus, modules, 2000)

    # ==================== 测试 1: 开灯 ====================
    log("")
    log("=" * 55)
    log(" 测试 1: 点击「手动」→ 点击「开灯」")
    log("=" * 55)
    log(" 小程序操作：① 点「手动」 ② 点「开灯」")
    log(" 预期：板子收到 light_on, PWM 输出, t=7 回推")
    _cmd_log.clear()
    _light_events.clear()
    _state_pushes.clear()
    log(" 操作完成后按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    pump_for(bus, modules, 5000)

    received_light_on = "light_on" in _cmd_log
    check("板子收到 light_on 指令", received_light_on, "cmd_log=%s" % _cmd_log)
    check("EVENT_LIGHT_CONTROL 触发",
          any(e.get("cmd") == "on" for e in _light_events))
    check("PWM 有输出", pwm_led._data.get("duty_cycle", 0) > 0,
          "duty=%s" % pwm_led._data.get("duty_cycle"))
    check("状态回推 t=7 收到", any(p.get("t") == 7 for p in _state_pushes))

    # ==================== 测试 2: 亮度+ ====================
    log("")
    log("=" * 55)
    log(" 测试 2: 点击亮度「▶」")
    log("=" * 55)
    log(" 小程序操作：点亮度「▶」增加按钮")
    _cmd_log.clear()
    _light_events.clear()
    prev_duty = pwm_led._data.get("duty_cycle", 0)
    log(" 操作完成后按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    pump_for(bus, modules, 5000)

    received_bri_up = "brightness_up" in _cmd_log
    check("板子收到 brightness_up", received_bri_up)
    check("亮度已增加", pwm_led._data.get("duty_cycle", 0) >= prev_duty,
          "prev=%d now=%d" % (prev_duty, pwm_led._data.get("duty_cycle", 0)))

    # ==================== 测试 3: 亮度- ====================
    log("")
    log("=" * 55)
    log(" 测试 3: 点击亮度「◀」")
    log("=" * 55)
    log(" 小程序操作：点亮度「◀」减少按钮")
    _cmd_log.clear()
    _light_events.clear()
    prev_duty = pwm_led._data.get("duty_cycle", 0)
    log(" 操作完成后按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    pump_for(bus, modules, 5000)

    received_bri_down = "brightness_down" in _cmd_log
    check("板子收到 brightness_down", received_bri_down)
    check("亮度已减少", pwm_led._data.get("duty_cycle", 0) <= prev_duty,
          "prev=%d now=%d" % (prev_duty, pwm_led._data.get("duty_cycle", 0)))

    # ==================== 测试 4: 关灯 ====================
    log("")
    log("=" * 55)
    log(" 测试 4: 点击「关灯」")
    log("=" * 55)
    log(" 小程序操作：点「关灯」按钮")
    _cmd_log.clear()
    _light_events.clear()
    log(" 操作完成后按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    pump_for(bus, modules, 5000)

    received_off = "light_off" in _cmd_log
    check("板子收到 light_off", received_off)
    check("PWM 输出为 0", pwm_led._data.get("duty_cycle", 0) == 0,
          "duty=%s" % pwm_led._data.get("duty_cycle"))

    # ==================== 测试 5: 自动模式 ====================
    log("")
    log("=" * 55)
    log(" 测试 5: 点击「自动」")
    log("=" * 55)
    log(" 小程序操作：点「自动」模式按钮")
    _cmd_log.clear()
    _light_events.clear()
    log(" 操作完成后按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    pump_for(bus, modules, 5000)

    received_auto = "light_auto" in _cmd_log
    check("板子收到 light_auto", received_auto)
    check("EVENT_LIGHT_CONTROL auto 触发",
          any(e.get("cmd") == "auto" for e in _light_events))

    # ==================== 汇总 ====================
    log("")
    log("=" * 55)
    log(" 测试完成")
    log("=" * 55)
    log("")
    log(" 检查清单：")
    log("  [%s] 测试1: 开灯 → light_on + PWM 输出" % ("✓" if received_light_on else " "))
    log("  [%s] 测试2: 亮度+ → brightness_up" % ("✓" if received_bri_up else " "))
    log("  [%s] 测试3: 亮度- → brightness_down" % ("✓" if received_bri_down else " "))
    log("  [%s] 测试4: 关灯 → light_off + PWM=0" % ("✓" if received_off else " "))
    log("  [%s] 测试5: 自动 → light_auto" % ("✓" if received_auto else " "))
    log("")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
