"""
brief ControlService 端到端真机测试（调试版）
note 使用真硬件：BLE（手机 NRF Connect）、LightService、Audio、LED
      手机通过 NRF Connect 写入 FFF3 发送控制指令
      每个场景前都有提示告诉你该观察什么
执行: 上传到板子运行 python test_control_service_e2e.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, POWER_STATE_ACTIVE,
)
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.network.BLE import BLEDriver
from Modules.light_service import LightService
from Modules.alarm_service import AlarmService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService


# ==================== 全局状态 ====================
state_pushes = []
ble_rx_count = 0
ctrl_cmd_count = 0


def on_control_state(payload):
    state_pushes.append(payload)
    print("  [STATE PUSH] {}".format(payload))


def pump_loop(event_bus, times, delay_ms=10):
    for _ in range(times):
        event_bus.pump()
        time.sleep_ms(delay_ms)


def prompt_and_watch(msg, duration_s=5, event_bus=None, modules=None):
    print("\n  >>> {} (观察 {} 秒)".format(msg, duration_s))
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        if modules:
            for mod in modules:
                if mod.ctx.get("is_init", False):
                    try:
                        mod.tick()
                    except Exception:
                        pass
        if event_bus:
            event_bus.pump()
        time.sleep_ms(100)
    elapsed = time.ticks_diff(time.ticks_ms(), start) // 1000
    print("  ... {}s 完成".format(elapsed))


def print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc):
    """打印所有相关模块状态"""
    print("  --- 模块状态快照 ---")
    print("  ControlService: init={}, err={}, state={}".format(
        ctrl.ctx["is_init"], ctrl.ctx["err_count"], ctrl._control_state))
    print("  LightService: init={}, auto_mode={}, brightness={}".format(
        light_svc.ctx["is_init"], light_svc.ctx["auto_mode"],
        light_svc._data["current_brightness"]))
    print("  PWM_LED: init={}, duty={}".format(
        pwm_led.ctx["is_init"], pwm_led._data["duty_cycle"]))
    print("  Audio: init={}".format(audio.ctx["is_init"]))
    print("  BLE: connected={}, queue_size={}".format(
        ble_svc.ctx["ble_connected"],
        ble_svc.send_queue.size() if ble_svc.send_queue else 0))
    print("  状态回推次数: {}".format(len(state_pushes)))
    print("  BLE RX 次数: {}".format(ble_rx_count))
    print("  控制指令处理次数: {}".format(ctrl_cmd_count))


def main():
    global ble_rx_count, ctrl_cmd_count

    print("=" * 60)
    print(" ControlService 端到端真机测试（调试版）")
    print("=" * 60)
    print("\n准备：")
    print("  1. 手机打开 NRF Connect，连接头盔 BLE")
    print("  2. 找到 FFF3 特征值（Write）")
    print("  3. 按提示发送 JSON 指令")

    # 创建事件总线
    event_bus = EventBus()

    # 创建 Device 层
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    pwm_led = PWMLEDDriver(event_bus)
    light_sensor = LightSensorDriver(event_bus)
    ble_driver = BLEDriver(event_bus)

    # 创建 Service 层
    light_svc = LightService(event_bus, pwm_led=pwm_led)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    ble_svc = BLEService(event_bus, ble_driver=ble_driver)
    ctrl = ControlService(event_bus, light_service=light_svc,
                          audio_driver=audio, alarm_service=alarm)

    # 初始化
    init_order = [led, audio, pwm_led, light_sensor, ble_driver,
                  light_svc, alarm, ble_svc, ctrl]
    print("\n[初始化阶段]")
    for mod in init_order:
        try:
            mod.init()
            print("  OK {} | is_init={}".format(mod.name, mod.ctx.get("is_init", False)))
        except Exception as e:
            print("  FAIL {}: {}".format(mod.name, e))

    # 打印初始化后状态
    print("\n[初始化后状态]")
    print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc)

    # 订阅状态回推
    event_bus.subscribe(EVENT_CONTROL_STATE_CHANGED, on_control_state)

    # 订阅 BLE 接收日志
    def _log_ride_control(payload):
        global ble_rx_count
        ble_rx_count += 1
        raw = payload.get("raw", "")
        print("  [BLE RX #{}] {}".format(ble_rx_count, raw))
    event_bus.subscribe(EVENT_RIDE_CONTROL, _log_ride_control)

    # 订阅 ControlService 执行日志（通过 monkey-patch）
    orig_execute = ctrl._execute_cmd
    def _debug_execute(cmd, source="unknown"):
        global ctrl_cmd_count
        ctrl_cmd_count += 1
        print("  [CTRL EXEC #{}] cmd={} src={}".format(ctrl_cmd_count, cmd, source))
        print("    → 执行前状态: light_brightness={}, light_mode={}, volume={}".format(
            ctrl._control_state["light_brightness"],
            ctrl._control_state["light_mode"],
            ctrl._control_state["volume"]))
        orig_execute(cmd, source)
        print("    → 执行后状态: light_brightness={}, light_mode={}, volume={}".format(
            ctrl._control_state["light_brightness"],
            ctrl._control_state["light_mode"],
            ctrl._control_state["volume"]))
        # 打印被调用模块的状态
        if ctrl.light_service:
            print("    → LightService: auto_mode={}, brightness={}".format(
                ctrl.light_service.ctx["auto_mode"],
                ctrl.light_service._data["current_brightness"]))
        if ctrl.pwm_led if hasattr(ctrl, 'pwm_led') else pwm_led:
            print("    → PWM_LED: duty={}".format(pwm_led._data["duty_cycle"]))
    ctrl._execute_cmd = _debug_execute

    # 等待 BLE 连接
    print("\n[等待 BLE 连接]")
    print("  BLE 广播名: SmartHelmet-66ccff")
    print("  请用手机 NRF Connect 连接...")
    while not ble_svc.ctx.get("ble_connected", False):
        for mod in init_order:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()
        time.sleep_ms(100)
    print("  OK BLE 已连接")
    print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc)

    # 主循环辅助函数
    def run_with_pump(duration_ms):
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
            for mod in init_order:
                if mod.ctx.get("is_init", False):
                    try:
                        mod.tick()
                    except Exception:
                        pass
            event_bus.pump()
            time.sleep_ms(50)

    # ==================== 测试场景 ====================

    print("\n" + "=" * 60)
    print("[测试 1] 头灯开")
    print("=" * 60)
    print("  手机发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_on\"}}")
    print("  预期: 头灯亮起（50%亮度）")
    input("  按 Enter 开始...")
    prompt_and_watch("等待手动发送 light_on 指令", 15, event_bus, init_order)
    print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc)

    print("\n" + "=" * 60)
    print("[测试 2] 亮度调节")
    print("=" * 60)
    print("  手机发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"brightness_up\"}}")
    print("  预期: 亮度增加")
    input("  按 Enter 开始...")
    prompt_and_watch("等待手动发送 brightness_up 指令", 15, event_bus, init_order)
    print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc)

    print("\n" + "=" * 60)
    print("[测试 3] 头灯关")
    print("=" * 60)
    print("  手机发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_off\"}}")
    print("  预期: 头灯熄灭")
    input("  按 Enter 开始...")
    prompt_and_watch("等待手动发送 light_off 指令", 15, event_bus, init_order)
    print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc)

    print("\n" + "=" * 60)
    print("[测试 4] 音量调节")
    print("=" * 60)
    print("  手机发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"volume_up\"}}")
    print("  预期: 音量增加")
    input("  按 Enter 开始...")
    prompt_and_watch("等待手动发送 volume_up 指令", 15, event_bus, init_order)
    print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc)

    print("\n" + "=" * 60)
    print("[测试 5] 自动灯光模式")
    print("=" * 60)
    print("  手机发送: {\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_auto\"}}")
    print("  预期: 切换到自动模式，灯光随环境光变化")
    input("  按 Enter 开始...")
    prompt_and_watch("等待手动发送 light_auto 指令", 15, event_bus, init_order)
    print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc)

    print("\n" + "=" * 60)
    print("[测试 6] 状态回推")
    print("=" * 60)
    print("  已收到 {} 次状态回推".format(len(state_pushes)))
    if state_pushes:
        for i, s in enumerate(state_pushes):
            print("  [{}] {}".format(i, s))

    print("\n" + "=" * 60)
    print("[测试 7] 防抖验证")
    print("=" * 60)
    print("  快速连续发送 2 次 light_on，第二次应被忽略")
    print("  控制服务防抖间隔: {}ms".format(ctrl.cfg["cmd_debounce_ms"]))

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n最终状态:")
    print_all_states(ctrl, light_svc, pwm_led, audio, ble_svc)


if __name__ == "__main__":
    main()
