"""
brief Wave 1 Device层集成测试：PWM_LED + BLE + EventBus
note 验证真实硬件驱动与事件总线的协同工作
     上传到板子运行：python test_device_integration.py
     依赖：NUCLEO-F413ZH + EC200U 硬件
"""
import sys
import time
sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_POWER_STATE_CHANGE, EVENT_PWM_LED_ERROR,
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
)
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.network.BLE import BLEDriver


# ==================== 事件日志 ====================
event_log = []


def on_any_event(tag, payload):
    """记录事件到日志，tag为事件类型缩写"""
    event_log.append("%s:%s" % (tag, str(payload)[:60]))


# ==================== 系统构建 ====================

_shared_ble = None  # 模块级 BLE 单例，硬件全局唯一


def make_system():
    """
    brief 构建 EventBus + PWMLEDDriver + BLEDriver 测试系统
    return (bus, pwm, ble) 元组
    note BLE 为 EC200U 硬件单例，只初始化一次，后续复用
    """
    global _shared_ble

    bus = EventBus()

    pwm = PWMLEDDriver(event_bus=bus)
    pwm.init()

    # BLE 硬件全局单例 — 只创建+初始化一次
    if _shared_ble is None:
        _shared_ble = BLEDriver(event_bus=bus)
        _shared_ble.init()
    else:
        # 更新 BLE 的 EventBus 引用，并在新总线上订阅 CONFIG_UPDATE
        _shared_ble.event_bus = bus
        bus.subscribe(EVENT_POWER_STATE_CHANGE, _shared_ble._on_config_update)

    ble = _shared_ble

    # 事件日志订阅（每次新建系统时重置）
    event_log.clear()
    bus.subscribe(EVENT_POWER_STATE_CHANGE, lambda p: on_any_event("CFG", p))
    bus.subscribe(EVENT_PWM_LED_ERROR, lambda p: on_any_event("PWM_ERR", p))
    bus.subscribe(EVENT_BLE_CONNECTED, lambda p: on_any_event("BLE_CONN", p))
    bus.subscribe(EVENT_BLE_DISCONNECTED, lambda p: on_any_event("BLE_DISC", p))

    return bus, pwm, ble


def send_event(bus, event_name, payload):
    """
    brief 发布事件并立即泵送
    param bus: EventBus 实例
    param event_name: 事件名称
    param payload: 事件数据字典
    """
    bus.publish(event_name, payload)
    bus.pump()


def pump_loop(bus, modules, cycles):
    """
    brief 执行多轮 pump 循环，模拟主循环调度
    param bus: EventBus 实例
    param modules: 模块列表，每轮调用 tick()
    param cycles: 循环次数
    """
    for i in range(cycles):
        for m in modules:
            m.tick()
        bus.pump()
        time.sleep_ms(50)


# ==================== 测试用例 ====================

def test_01_both_init():
    """Test 1: PWM_LED 和 BLE 驱动均初始化成功"""
    print("\n--- test_01_both_init ---")
    bus, pwm, ble = make_system()

    assert pwm.ctx["is_init"] == True, "PWM_LED init failed"
    assert ble.ctx["is_init"] == True, "BLE init failed"
    assert pwm.ctx["err_count"] == 0, "PWM_LED has errors"
    assert ble.ctx["err_count"] == 0, "BLE has errors"

    print("  OK both_init")
    print("    pwm status: %s" % pwm.get_status())
    print("    ble status: %s" % ble.get_status())


def test_02_pwm_tick_with_pump():
    """Test 2: PWM_LED tick() + EventBus pump() 不崩溃"""
    print("\n--- test_02_pwm_tick_with_pump ---")
    bus, pwm, ble = make_system()

    # PWM tick 是空实现，但必须不抛异常
    for _ in range(10):
        pwm.tick()
        bus.pump()
        time.sleep_ms(20)

    assert pwm.ctx["is_init"] == True, "PWM_LED lost init state"
    print("  OK pwm_tick_with_pump (10 cycles)")


def test_03_ble_tick_with_pump():
    """Test 3: BLE tick() + EventBus pump() — 验证广播状态"""
    print("\n--- test_03_ble_tick_with_pump ---")
    bus, pwm, ble = make_system()

    # BLE tick 检查 power_state，必须不抛异常
    for _ in range(10):
        ble.tick()
        bus.pump()
        time.sleep_ms(20)

    assert ble.ctx["is_init"] == True, "BLE lost init state"
    assert ble.ctx["power_state"] == POWER_STATE_ACTIVE, "BLE power_state not ACTIVE"
    print("  OK ble_tick_with_pump (10 cycles)")
    print("    ble power_state: %s" % ble.ctx["power_state"])


def test_04_combined_30_cycles():
    """Test 4: 两个驱动同时运行 30 轮 pump 循环"""
    print("\n--- test_04_combined_30_cycles ---")
    bus, pwm, ble = make_system()

    pump_loop(bus, [pwm, ble], 30)

    assert pwm.ctx["is_init"] == True, "PWM_LED lost init after 30 cycles"
    assert ble.ctx["is_init"] == True, "BLE lost init after 30 cycles"
    assert pwm.ctx["err_count"] == 0, "PWM_LED errors during 30 cycles"
    assert ble.ctx["err_count"] == 0, "BLE errors during 30 cycles"

    print("  OK combined_30_cycles")
    print("    events: %s" % event_log)
    print("    pwm: %s" % pwm.get_status())
    print("    ble: %s" % ble.get_status())


def test_05_pwm_brightness_via_event():
    """Test 5: 通过 EventBus 发送 CONFIG_UPDATE 事件控制 PWM 亮度"""
    print("\n--- test_05_pwm_brightness_via_event ---")
    bus, pwm, ble = make_system()

    # 初始亮度为 0
    assert pwm.get_data()["duty_cycle"] == 0, "Initial duty should be 0"

    # 通过事件设置亮度 50%
    send_event(bus, EVENT_POWER_STATE_CHANGE, {
        "power_state": POWER_STATE_ACTIVE,
        "source": "test",
    })

    # 直接调用 set_brightness 验证硬件响应
    pwm.set_brightness(50)
    data = pwm.get_data()
    assert data["duty_cycle"] == 50, "Duty should be 50 after set_brightness(50)"
    assert data["valid"] == True, "Data should be valid"

    # 设置 0% 熄灭
    pwm.set_brightness(0)
    data = pwm.get_data()
    assert data["duty_cycle"] == 0, "Duty should be 0 after set_brightness(0)"

    # 测试边界值钳位
    pwm.set_brightness(-10)
    assert pwm.get_data()["duty_cycle"] == 0, "Negative duty should clamp to 0"

    pwm.set_brightness(200)
    assert pwm.get_data()["duty_cycle"] == 100, "Over 100 duty should clamp to 100"

    print("  OK pwm_brightness_via_event")
    print("    events: %s" % event_log)


def test_06_power_state_suspend():
    """Test 6: 通过 POWER_STATE_CHANGE 事件切换省电模式，PWM 自动熄灭"""
    print("\n--- test_06_power_state_suspend ---")
    bus, pwm, ble = make_system()

    # 先设置亮度
    pwm.set_brightness(80)
    assert pwm.get_data()["duty_cycle"] == 80

    # 切换到 SUSPENDED 模式，PWM 应自动熄灭
    send_event(bus, EVENT_POWER_STATE_CHANGE, {
        "power_state": POWER_STATE_SUSPENDED,
        "source": "test",
    })

    assert pwm.ctx["power_state"] == POWER_STATE_SUSPENDED, "PWM power_state not updated"
    assert pwm.get_data()["duty_cycle"] == 0, "PWM should be 0 in SUSPENDED mode"
    assert ble.ctx["power_state"] == POWER_STATE_SUSPENDED, "BLE power_state not updated"

    print("  OK power_state_suspend")
    print("    events: %s" % event_log)


# ==================== 主入口 ====================

def run_all():
    """运行所有 Wave 1 Device 层集成测试"""
    print("=" * 50)
    print("Wave 1 Device 层集成测试")
    print("PWM_LED + BLE + EventBus")
    print("=" * 50)

    tests = [
        test_01_both_init,
        test_02_pwm_tick_with_pump,
        test_03_ble_tick_with_pump,
        test_04_combined_30_cycles,
        test_05_pwm_brightness_via_event,
        test_06_power_state_suspend,
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
        print("!!! 存在失败测试，请检查硬件连接 !!!")
    else:
        print("ALL PASS")


if __name__ == "__main__":
    run_all()
