"""
brief Wave 2 Service层联合集成测试：ControlService + LightService + PWM_LED
note 验证完整事件链：BLE cmd → ControlService → EVENT_LIGHT_CONTROL → LightService → PWM_LED
     上传到板子运行：python test_light_control_integration.py
     依赖：NUCLEO-F413ZH 板（仅用 FakePWM，无需真实 PWM 硬件）

事件链：
    EVENT_RIDE_CONTROL → ControlService._on_ride_control()
        → _execute_cmd() → EVENT_LIGHT_CONTROL
            → LightService._on_light_control()
                → set_manual_brightness() / set_auto_mode()
                    → pwm_led.set_brightness()
"""
import sys
import time
import json

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_LIGHT_CONTROL, EVENT_LIGHT_READY,
    LIGHT_BRIGHTNESS_MAX, LIGHT_BRIGHTNESS_STEP,
)
from Modules.control_service import ControlService
from Modules.light_service import LightService


# ==================== Fake 驱动 ====================

class FakePWM:
    """
    brief 模拟 PWM LED 驱动，记录亮度变化
    note 替代真实 PWMLEDDriver，无需硬件即可测试事件链
    """

    def __init__(self):
        self.duty = 0
        self.history = []

    def set_brightness(self, duty):
        """记录每次亮度设置"""
        self.duty = duty
        self.history.append(duty)


# ==================== 事件日志 ====================
event_log = []


def on_any_event(tag, payload):
    """记录事件到日志，tag为事件类型缩写"""
    event_log.append("%s:%s" % (tag, str(payload)[:60]))


# ==================== 系统构建 ====================

def make_full_system():
    """
    brief 构建完整事件链测试系统
    note 组装 EventBus + ControlService + LightService + FakePWM
         订阅事件日志用于验证事件流转
    return (bus, ctrl, light, pwm) 元组
    """
    bus = EventBus()
    pwm = FakePWM()
    light = LightService(bus, pwm_led=pwm)
    ctrl = ControlService(bus)

    # 按初始化顺序 init
    light.init()
    ctrl.init()

    # 重置事件日志
    event_log.clear()

    # 事件日志订阅 — 追踪完整事件链
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: on_any_event("LIGHT_CTRL", p))
    bus.subscribe(EVENT_CONTROL_STATE_CHANGED, lambda p: on_any_event("STATE", p))
    bus.subscribe(EVENT_LIGHT_READY, lambda p: on_any_event("LIGHT_RDY", p))

    return bus, ctrl, light, pwm


def send_cmd(bus, ctrl, cmd):
    """
    brief 发送 BLE 控制指令并立即泵送事件
    param bus: EventBus 实例
    param ctrl: ControlService 实例
    param cmd: 指令字符串（如 "light_on"）
    note 重置防抖以确保连续发送不被丢弃
    """
    ctrl.ctx["last_cmd_tick"] = 0  # 重置防抖
    raw = json.dumps({"a": "ctrl", "d": {"cmd": cmd}})
    bus.publish(EVENT_RIDE_CONTROL, {"raw": raw})
    bus.pump()


# ==================== 灯光控制测试 ====================

def test_01_light_on():
    """Test 1: light_on → PWM duty = LIGHT_BRIGHTNESS_MAX (50%)"""
    print("\n--- test_01_light_on ---")
    bus, ctrl, light, pwm = make_full_system()

    send_cmd(bus, ctrl, "light_on")

    assert pwm.duty == LIGHT_BRIGHTNESS_MAX, \
        "light_on 后 PWM duty 应为 %d, 实际 %d" % (LIGHT_BRIGHTNESS_MAX, pwm.duty)
    assert light.get_mode() == "manual", \
        "light_on 后应为手动模式, 实际 %s" % light.get_mode()

    print("  OK light_on: duty=%d, mode=%s" % (pwm.duty, light.get_mode()))
    print("    events: %s" % event_log)


def test_02_light_off():
    """Test 2: light_off → PWM duty = 0"""
    print("\n--- test_02_light_off ---")
    bus, ctrl, light, pwm = make_full_system()

    # 先开灯
    send_cmd(bus, ctrl, "light_on")
    assert pwm.duty == LIGHT_BRIGHTNESS_MAX, "前置条件: 灯应已开启"

    # 关灯
    send_cmd(bus, ctrl, "light_off")

    assert pwm.duty == 0, \
        "light_off 后 PWM duty 应为 0, 实际 %d" % pwm.duty
    assert light.get_mode() == "manual", \
        "light_off 后应为手动模式, 实际 %s" % light.get_mode()

    print("  OK light_off: duty=%d, mode=%s" % (pwm.duty, light.get_mode()))
    print("    events: %s" % event_log)


def test_03_brightness_up():
    """Test 3: brightness_up → duty 增加 LIGHT_BRIGHTNESS_STEP (5)"""
    print("\n--- test_03_brightness_up ---")
    bus, ctrl, light, pwm = make_full_system()

    # 先开灯到最大亮度
    send_cmd(bus, ctrl, "light_on")
    assert pwm.duty == LIGHT_BRIGHTNESS_MAX, "前置: 灯应已开到最大"

    # 手动设置中间亮度作为起点
    light.set_manual_brightness(30)
    assert pwm.duty == 30, "前置: 亮度应设为 30"

    # 亮度增加
    send_cmd(bus, ctrl, "brightness_up")

    expected = 30 + LIGHT_BRIGHTNESS_STEP
    assert pwm.duty == expected, \
        "brightness_up 后 duty 应为 %d, 实际 %d" % (expected, pwm.duty)

    print("  OK brightness_up: 30 -> %d (step=%d)" % (pwm.duty, LIGHT_BRIGHTNESS_STEP))
    print("    events: %s" % event_log)


def test_04_brightness_down():
    """Test 4: brightness_down → duty 减少 LIGHT_BRIGHTNESS_STEP (5)"""
    print("\n--- test_04_brightness_down ---")
    bus, ctrl, light, pwm = make_full_system()

    # 手动设置中间亮度
    light.set_manual_brightness(30)
    assert pwm.duty == 30, "前置: 亮度应设为 30"

    # 亮度降低
    send_cmd(bus, ctrl, "brightness_down")

    expected = 30 - LIGHT_BRIGHTNESS_STEP
    assert pwm.duty == expected, \
        "brightness_down 后 duty 应为 %d, 实际 %d" % (expected, pwm.duty)
    assert light.get_mode() == "manual", \
        "brightness_down 后应为手动模式"

    print("  OK brightness_down: 30 -> %d (step=%d)" % (pwm.duty, LIGHT_BRIGHTNESS_STEP))
    print("    events: %s" % event_log)


def test_05_light_auto():
    """Test 5: light_auto → LightService 切换到自动模式"""
    print("\n--- test_05_light_auto ---")
    bus, ctrl, light, pwm = make_full_system()

    # 先切到手动模式
    send_cmd(bus, ctrl, "light_on")
    assert light.get_mode() == "manual", "前置: 应为手动模式"

    # 切回自动模式
    send_cmd(bus, ctrl, "light_auto")

    assert light.get_mode() == "auto", \
        "light_auto 后应为自动模式, 实际 %s" % light.get_mode()
    assert light.ctx["auto_mode"] == True, \
        "light.ctx auto_mode 应为 True"

    print("  OK light_auto: mode=%s, auto_mode=%s" % (light.get_mode(), light.ctx["auto_mode"]))
    print("    events: %s" % event_log)


def test_06_auto_mode_dark():
    """Test 6: 自动模式 — 暗环境(EVENT_LIGHT_READY 高ADC值) → PWM 自动亮起"""
    print("\n--- test_06_auto_mode_dark ---")
    bus, ctrl, light, pwm = make_full_system()

    # 切换到自动模式
    send_cmd(bus, ctrl, "light_auto")
    assert light.get_mode() == "auto", "前置: 应为自动模式"

    # 重置防抖以绕过时间检查
    light.ctx["last_update_tick"] = 0

    # 发布暗环境光照数据（ADC > 50000 → 夜晚 → 最大亮度）
    bus.publish(EVENT_LIGHT_READY, {
        "light_intensity": 55000,
        "valid": True,
    })
    bus.pump()

    # 暗环境: normalized=1.0, brightness = 5 + (50-5)*pow(1.0,1.5) = 50
    assert pwm.duty == LIGHT_BRIGHTNESS_MAX, \
        "暗环境自动亮度应为 %d, 实际 %d" % (LIGHT_BRIGHTNESS_MAX, pwm.duty)
    assert light._data["light_level"] == "night", \
        "光照等级应为 night, 实际 %s" % light._data["light_level"]

    print("  OK auto_dark: intensity=55000, duty=%d, level=%s" % (
        pwm.duty, light._data["light_level"]))
    print("    events: %s" % event_log)


def test_07_auto_mode_bright():
    """Test 7: 自动模式 — 亮环境(EVENT_LIGHT_READY 低ADC值) → PWM 关闭"""
    print("\n--- test_07_auto_mode_bright ---")
    bus, ctrl, light, pwm = make_full_system()

    # 切换到自动模式
    send_cmd(bus, ctrl, "light_auto")

    # 模拟先有过亮度，确保阈值检查通过
    light.ctx["last_brightness"] = 50
    light.ctx["last_update_tick"] = 0

    # 发布亮环境光照数据（ADC < 30000 → 白天 → 亮度 0）
    bus.publish(EVENT_LIGHT_READY, {
        "light_intensity": 10000,
        "valid": True,
    })
    bus.pump()

    # 亮环境: ADC < day_threshold → brightness = 0
    assert pwm.duty == 0, \
        "亮环境自动亮度应为 0, 实际 %d" % pwm.duty
    assert light._data["light_level"] == "day", \
        "光照等级应为 day, 实际 %s" % light._data["light_level"]

    print("  OK auto_bright: intensity=10000, duty=%d, level=%s" % (
        pwm.duty, light._data["light_level"]))
    print("    events: %s" % event_log)


def test_08_state_snapshot_brightness():
    """Test 8: ControlService 状态快照反映亮度变化"""
    print("\n--- test_08_state_snapshot_brightness ---")
    bus, ctrl, light, pwm = make_full_system()

    # 开灯 — 默认最大亮度
    send_cmd(bus, ctrl, "light_on")
    state = ctrl.get_data()["control_state"]
    assert state["light_mode"] == "manual", \
        "开灯后 light_mode 应为 manual"
    assert state["light_brightness"] == LIGHT_BRIGHTNESS_MAX, \
        "开灯后 brightness 应为 %d, 实际 %d" % (LIGHT_BRIGHTNESS_MAX, state["light_brightness"])

    # 亮度降低
    send_cmd(bus, ctrl, "brightness_down")
    state = ctrl.get_data()["control_state"]
    expected_bright = LIGHT_BRIGHTNESS_MAX - LIGHT_BRIGHTNESS_STEP
    assert state["light_brightness"] == expected_bright, \
        "brightness_down 后应为 %d, 实际 %d" % (expected_bright, state["light_brightness"])

    # 切自动模式
    send_cmd(bus, ctrl, "light_auto")
    state = ctrl.get_data()["control_state"]
    assert state["light_mode"] == "auto", \
        "light_auto 后 light_mode 应为 auto"

    print("  OK state_snapshot: brightness tracking correct")
    print("    final state: %s" % state)
    print("    events: %s" % event_log)


def test_09_event_log_state_changed():
    """Test 9: 每次指令后 event_log 包含 EVENT_CONTROL_STATE_CHANGED"""
    print("\n--- test_09_event_log_state_changed ---")
    bus, ctrl, light, pwm = make_full_system()

    cmds = ["light_on", "light_off", "brightness_up", "brightness_down", "light_auto"]

    for cmd in cmds:
        event_log.clear()
        send_cmd(bus, ctrl, cmd)

        # 检查 STATE 事件是否在日志中
        state_events = [e for e in event_log if e.startswith("STATE:")]
        assert len(state_events) > 0, \
            "cmd=%s 后应有 EVENT_CONTROL_STATE_CHANGED, 日志: %s" % (cmd, event_log)

    print("  OK event_log: STATE_CHANGED fired for all %d commands" % len(cmds))
    print("    cmds tested: %s" % cmds)


# ==================== 主入口 ====================

def run_all():
    """运行所有 Wave 2 Service层联合集成测试"""
    print("=" * 50)
    print("Wave 2 Service层联合集成测试")
    print("ControlService + LightService + FakePWM")
    print("事件链: BLE -> ControlService -> LightService -> PWM")
    print("=" * 50)

    tests = [
        test_01_light_on,
        test_02_light_off,
        test_03_brightness_up,
        test_04_brightness_down,
        test_05_light_auto,
        test_06_auto_mode_dark,
        test_07_auto_mode_bright,
        test_08_state_snapshot_brightness,
        test_09_event_log_state_changed,
    ]

    passed = 0
    failed = 0

    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print("  FAIL %s: %s" % (t.__name__, e))

    print("\n" + "=" * 50)
    print("结果: %d 通过, %d 失败 / 共 %d" % (passed, failed, len(tests)))
    print("=" * 50)

    if failed > 0:
        print("!!! 存在失败测试，请检查 !!!")
    else:
        print("ALL PASS")


if __name__ == "__main__":
    run_all()
