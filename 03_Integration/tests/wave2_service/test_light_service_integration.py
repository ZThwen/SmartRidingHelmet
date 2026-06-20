"""
brief Wave 2 Service层集成测试：LightService + FakePWM + EventBus
note 验证 LightService 与事件总线的协同工作
     使用 FakePWM 隔离硬件依赖，专注 Service 层逻辑
     上传到板子运行：python test_light_service_integration.py
     依赖：NUCLEO-F413ZH 板子
"""
import sys
import time
sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_LIGHT_READY, EVENT_LIGHT_CONTROL, EVENT_CONFIG_UPDATE,
    EVENT_POWER_STATE_CHANGE,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    LIGHT_DAY_ADC_THRESHOLD, LIGHT_NIGHT_ADC_THRESHOLD,
    LIGHT_BRIGHTNESS_MIN, LIGHT_BRIGHTNESS_MAX, LIGHT_GAMMA,
)
from Modules.light_service import LightService


# ==================== 假驱动 ====================

class FakePWM:
    """brief 模拟 PWM LED 驱动，记录亮度调用"""
    def __init__(self):
        self.duty = 0
        self.calls = []

    def set_brightness(self, d):
        """记录每次亮度设置"""
        self.duty = d
        self.calls.append(d)


# ==================== 事件日志 ====================
event_log = []


def on_any_event(tag, payload):
    """记录事件到日志，tag为事件类型缩写"""
    event_log.append("%s:%s" % (tag, str(payload)[:60]))


# ==================== 系统构建 ====================

def make_system():
    """
    brief 构建 EventBus + FakePWM + LightService 测试系统
    return (bus, light, pwm) 元组
    """
    bus = EventBus()
    pwm = FakePWM()
    light = LightService(bus, pwm_led=pwm)
    light.init()

    # 事件日志订阅（每次新建系统时重置）
    event_log.clear()
    bus.subscribe(EVENT_LIGHT_READY, lambda p: on_any_event("LIGHT_RDY", p))
    bus.subscribe(EVENT_LIGHT_CONTROL, lambda p: on_any_event("LIGHT_CTRL", p))
    bus.subscribe(EVENT_CONFIG_UPDATE, lambda p: on_any_event("CFG", p))

    return bus, light, pwm


def send_event(bus, event_name, payload):
    """
    brief 发布事件并立即泵送
    param bus: EventBus 实例
    param event_name: 事件名称
    param payload: 事件数据字典
    """
    bus.publish(event_name, payload)
    bus.pump()


def pump_loop(bus, modules, duration_ms):
    """
    brief 执行 timed pump 循环，模拟主循环调度
    param bus: EventBus 实例
    param modules: 模块列表，每轮调用 tick()
    param duration_ms: 循环持续时间（ms）
    """
    end = time.ticks_add(time.ticks_ms(), duration_ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        for m in modules:
            m.tick()
        bus.pump()
        time.sleep_ms(100)


# ==================== 测试用例 ====================

def test_01_init_success():
    """Test 1: LightService 初始化成功，订阅事件正常"""
    print("\n--- test_01_init_success ---")
    bus, light, pwm = make_system()

    assert light.ctx["is_init"] == True, "LightService init failed"
    assert light.ctx["auto_mode"] == True, "Default should be auto mode"
    assert light.ctx["err_count"] == 0, "Should have no errors"
    assert light.name == "light_service", "Name should be light_service"

    # 验证事件可以到达（订阅成功）
    send_event(bus, EVENT_LIGHT_READY, {
        "light_intensity": 40000,
        "valid": True,
    })
    assert len(event_log) > 0, "Event should be logged (subscription works)"

    print("  OK init_success")
    print("    status: %s" % light.get_status())
    print("    events: %s" % event_log)


def test_02_dark_light_brightness_increases():
    """Test 2: 暗光环境 → PWM 亮度增加（gamma 映射）"""
    print("\n--- test_02_dark_light_brightness_increases ---")
    bus, light, pwm = make_system()

    # 初始亮度为 0
    assert pwm.duty == 0, "Initial brightness should be 0"

    # 发布暗光数据（ADC > night_threshold → 最亮）
    send_event(bus, EVENT_LIGHT_READY, {
        "light_intensity": 60000,  # > 50000 (night threshold)
        "valid": True,
    })

    # 验证亮度已设置（night → brightness_max = 50）
    data = light.get_data()
    assert data["current_brightness"] == LIGHT_BRIGHTNESS_MAX, \
        "Night brightness should be %d, got %d" % (LIGHT_BRIGHTNESS_MAX, data["current_brightness"])
    assert data["light_level"] == "night", "Level should be night"
    assert pwm.duty == LIGHT_BRIGHTNESS_MAX, \
        "FakePWM duty should be %d, got %d" % (LIGHT_BRIGHTNESS_MAX, pwm.duty)

    print("  OK dark_light_brightness_increases")
    print("    brightness: %d%%, level: %s" % (data["current_brightness"], data["light_level"]))
    print("    pwm calls: %s" % pwm.calls)


def test_03_bright_light_brightness_decreases():
    """Test 3: 亮光环境 → PWM 亮度降低/关闭"""
    print("\n--- test_03_bright_light_brightness_decreases ---")
    bus, light, pwm = make_system()

    # 先设置一个非零亮度（通过暗光）
    send_event(bus, EVENT_LIGHT_READY, {
        "light_intensity": 60000,
        "valid": True,
    })
    assert pwm.duty > 0, "Should have brightness after dark light"

    # 重置防抖（等待足够时间）
    time.sleep_ms(100)

    # 发布亮光数据（ADC < day_threshold → 灯不开）
    send_event(bus, EVENT_LIGHT_READY, {
        "light_intensity": 10000,  # < 30000 (day threshold)
        "valid": True,
    })

    data = light.get_data()
    assert data["current_brightness"] == 0, \
        "Day brightness should be 0, got %d" % data["current_brightness"]
    assert data["light_level"] == "day", "Level should be day"
    assert pwm.duty == 0, "FakePWM duty should be 0 for day"

    print("  OK bright_light_brightness_decreases")
    print("    brightness: %d%%, level: %s" % (data["current_brightness"], data["light_level"]))


def test_04_manual_mode_light_on():
    """Test 4: 手动模式 — light_on → 固定最大亮度"""
    print("\n--- test_04_manual_mode_light_on ---")
    bus, light, pwm = make_system()

    # 通过事件发布 light_on 指令
    send_event(bus, EVENT_LIGHT_CONTROL, {"cmd": "on"})

    data = light.get_data()
    assert data["mode"] == "manual", "Should switch to manual mode"
    assert data["current_brightness"] == LIGHT_BRIGHTNESS_MAX, \
        "on cmd should set brightness to %d, got %d" % (LIGHT_BRIGHTNESS_MAX, data["current_brightness"])
    assert pwm.duty == LIGHT_BRIGHTNESS_MAX, \
        "FakePWM duty should be %d" % LIGHT_BRIGHTNESS_MAX

    print("  OK manual_mode_light_on")
    print("    brightness: %d%%, mode: %s" % (data["current_brightness"], data["mode"]))


def test_05_manual_mode_light_off():
    """Test 5: 手动模式 — light_off → 亮度 0"""
    print("\n--- test_05_manual_mode_light_off ---")
    bus, light, pwm = make_system()

    # 先开灯
    send_event(bus, EVENT_LIGHT_CONTROL, {"cmd": "on"})
    assert pwm.duty == LIGHT_BRIGHTNESS_MAX, "Should be on first"

    # 关灯
    send_event(bus, EVENT_LIGHT_CONTROL, {"cmd": "off"})

    data = light.get_data()
    assert data["mode"] == "manual", "Should be in manual mode"
    assert data["current_brightness"] == 0, \
        "off cmd should set brightness to 0, got %d" % data["current_brightness"]
    assert pwm.duty == 0, "FakePWM duty should be 0"

    print("  OK manual_mode_light_off")
    print("    brightness: %d%%, mode: %s" % (data["current_brightness"], data["mode"]))


def test_06_auto_manual_toggle():
    """Test 6: 自动/手动模式切换"""
    print("\n--- test_06_auto_manual_toggle ---")
    bus, light, pwm = make_system()

    # 默认自动模式
    assert light.get_mode() == "auto", "Default should be auto"

    # 切换到手动（通过 light_on）
    send_event(bus, EVENT_LIGHT_CONTROL, {"cmd": "on"})
    assert light.get_mode() == "manual", "Should be manual after on"

    # 恢复自动模式
    send_event(bus, EVENT_LIGHT_CONTROL, {"cmd": "auto"})
    assert light.get_mode() == "auto", "Should be auto after auto cmd"
    assert light.ctx["auto_mode"] == True, "ctx auto_mode should be True"

    # 再次切换手动（通过 brightness_down）
    send_event(bus, EVENT_LIGHT_CONTROL, {"cmd": "brightness_down"})
    assert light.get_mode() == "manual", "Should be manual after brightness_down"

    print("  OK auto_manual_toggle")
    print("    events: %s" % event_log)


def test_07_get_data_valid():
    """Test 7: get_data() 返回有效数据"""
    print("\n--- test_07_get_data_valid ---")
    bus, light, pwm = make_system()

    data = light.get_data()

    # 验证返回字典包含所有必要字段
    assert "current_brightness" in data, "Missing current_brightness"
    assert "light_intensity" in data, "Missing light_intensity"
    assert "mode" in data, "Missing mode"
    assert "light_level" in data, "Missing light_level"
    assert "timestamp" in data, "Missing timestamp"

    # 验证初始值
    assert data["current_brightness"] == 0, "Initial brightness should be 0"
    assert data["light_intensity"] == 0, "Initial intensity should be 0"
    assert data["mode"] == "auto", "Initial mode should be auto"
    assert data["light_level"] == "unknown", "Initial level should be unknown"
    assert isinstance(data["timestamp"], int), "Timestamp should be int"

    # 验证 get_status() 也正常
    status = light.get_status()
    assert status["is_init"] == True, "Status should show init"
    assert status["auto_mode"] == True, "Status should show auto_mode"
    assert status["power_state"] == POWER_STATE_ACTIVE, "Status should show ACTIVE"
    assert status["err_count"] == 0, "Status should show 0 errors"

    print("  OK get_data_valid")
    print("    data: %s" % data)
    print("    status: %s" % status)


def test_08_power_state_suspended():
    """Test 8: 省电模式 SUSPENDED → 光照数据被忽略"""
    print("\n--- test_08_power_state_suspended ---")
    bus, light, pwm = make_system()

    # 先设置一些亮度
    send_event(bus, EVENT_LIGHT_READY, {
        "light_intensity": 60000,
        "valid": True,
    })
    brightness_before = light.get_data()["current_brightness"]
    assert brightness_before > 0, "Should have brightness before suspend"

    # 重置 FakePWM 调用记录
    pwm.calls = []

    # 切换到 SUSPENDED 模式
    send_event(bus, EVENT_CONFIG_UPDATE, {
        "power_state": POWER_STATE_SUSPENDED,
        "source": "test",
    })

    # 验证 power_state 已更新
    assert light.ctx["power_state"] == POWER_STATE_SUSPENDED, \
        "power_state should be SUSPENDED"

    # 等待防抖过期
    time.sleep_ms(100)

    # 发布暗光数据，应该被忽略
    send_event(bus, EVENT_LIGHT_READY, {
        "light_intensity": 60000,
        "valid": True,
    })

    # 验证亮度没有变化（LightService 在 SUSPENDED 模式下忽略光照数据）
    brightness_after = light.get_data()["current_brightness"]
    assert len(pwm.calls) == 0, \
        "FakePWM should not be called in SUSPENDED mode, got calls: %s" % pwm.calls

    print("  OK power_state_suspended")
    print("    power_state: %s" % light.ctx["power_state"])
    print("    brightness before: %d, after: %d (unchanged)" % (brightness_before, brightness_after))
    print("    pwm calls in suspend: %s" % pwm.calls)


# ==================== 主入口 ====================

def run_all():
    """运行所有 Wave 2 Service 层集成测试"""
    print("=" * 50)
    print("Wave 2 Service 层集成测试")
    print("LightService + FakePWM + EventBus")
    print("=" * 50)

    tests = [
        test_01_init_success,
        test_02_dark_light_brightness_increases,
        test_03_bright_light_brightness_decreases,
        test_04_manual_mode_light_on,
        test_05_manual_mode_light_off,
        test_06_auto_manual_toggle,
        test_07_get_data_valid,
        test_08_power_state_suspended,
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
