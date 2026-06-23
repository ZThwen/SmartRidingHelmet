"""
brief PWM_LED驱动模块单元测试
note 测试PWMLEDDriver的初始化、占空比设置(0%/50%/100%)、连续tick()稳定性、
     get_data()/get_status()返回值校验
     硬件：PE11, TIM1_CH2, 1000Hz
     运行环境：MicroPython on NUCLEO-F413ZH（禁止PC端执行）
"""
import time
import sys

sys.path.append("../../../02_Software")

from core.config import (
    EVENT_PWM_LED_ERROR, EVENT_CONFIG_UPDATE,
    PWM_LED_PIN, PWM_LED_TIMER_ID, PWM_LED_TIMER_CHANNEL,
    PWM_LED_FREQ, POWER_STATE_ACTIVE,
)
from core.Event_Bus import EventBus
from Drivers.actuator.PWM_LED import PWMLEDDriver


def _pump_loop(mod, bus, duration_ms, interval_ms=10):
    """
    brief 泵循环辅助函数：在指定时长内反复调用tick()和pump()
    param mod: 模块实例
    param bus: EventBus实例
    param duration_ms: 循环持续时间（ms）
    param interval_ms: 每次循环间隔（ms）
    note 禁止使用time.sleep()，统一用ticks_diff守卫
    """
    end = time.ticks_add(time.ticks_ms(), duration_ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        mod.tick()
        bus.pump()
        time.sleep_ms(interval_ms)


def test_pwm_led():
    print("=" * 50)
    print("PWM_LED单模块测试开始")
    print("=" * 50)

    event_bus = EventBus()
    pwm = PWMLEDDriver(event_bus=event_bus)
    pass_count = 0
    fail_count = 0

    # ====== [步骤1] 初始化 PWMLEDDriver ======
    print("\n[步骤1] 初始化 PWMLEDDriver...")
    try:
        pwm.init()
        print("  OK 初始化成功")
        pass_count += 1
    except Exception as e:
        print("  FAIL 初始化失败: {}".format(e))
        return

    # ====== [步骤2] 验证init()后is_init=True ======
    print("\n[步骤2] 验证init()后is_init=True...")
    status = pwm.get_status()
    if status["is_init"] is True:
        print("  OK is_init={}".format(status["is_init"]))
        pass_count += 1
    else:
        print("  FAIL is_init={} (期望True)".format(status["is_init"]))
        fail_count += 1

    # ====== [步骤3] set_brightness(50) → duty_cycle≈50% ======
    print("\n[步骤3] set_brightness(50) 占空比50%...")
    pwm.set_brightness(50)
    data = pwm.get_data()
    if data["duty_cycle"] == 50:
        print("  OK duty_cycle={}".format(data["duty_cycle"]))
        pass_count += 1
    else:
        print("  FAIL duty_cycle={} (期望50)".format(data["duty_cycle"]))
        fail_count += 1
    time.sleep_ms(200)

    # ====== [步骤4] set_brightness(0) → duty_cycle≈0% ======
    print("\n[步骤4] set_brightness(0) 占空比0%...")
    pwm.set_brightness(0)
    data = pwm.get_data()
    if data["duty_cycle"] == 0:
        print("  OK duty_cycle={}".format(data["duty_cycle"]))
        pass_count += 1
    else:
        print("  FAIL duty_cycle={} (期望0)".format(data["duty_cycle"]))
        fail_count += 1
    time.sleep_ms(200)

    # ====== [步骤5] set_brightness(100) → duty_cycle≈100% ======
    print("\n[步骤5] set_brightness(100) 占空比100%...")
    pwm.set_brightness(100)
    data = pwm.get_data()
    if data["duty_cycle"] == 100:
        print("  OK duty_cycle={}".format(data["duty_cycle"]))
        pass_count += 1
    else:
        print("  FAIL duty_cycle={} (期望100)".format(data["duty_cycle"]))
        fail_count += 1
    time.sleep_ms(200)

    # ====== [步骤6] 越界限幅测试 ======
    print("\n[步骤6] 越界限幅测试...")
    pwm.set_brightness(-10)
    data = pwm.get_data()
    if data["duty_cycle"] == 0:
        print("  OK set_brightness(-10) 限幅为0")
        pass_count += 1
    else:
        print("  FAIL set_brightness(-10) duty_cycle={} (期望0)".format(data["duty_cycle"]))
        fail_count += 1

    pwm.set_brightness(200)
    data = pwm.get_data()
    if data["duty_cycle"] == 100:
        print("  OK set_brightness(200) 限幅为100")
        pass_count += 1
    else:
        print("  FAIL set_brightness(200) duty_cycle={} (期望100)".format(data["duty_cycle"]))
        fail_count += 1

    # ====== [步骤7] 连续100次tick()不崩溃 ======
    print("\n[步骤7] 连续100次tick()稳定性测试...")
    tick_err = False
    try:
        for i in range(100):
            pwm.tick()
            event_bus.pump()
        print("  OK 100次tick()无异常")
        pass_count += 1
    except Exception as e:
        print("  FAIL tick()异常: {}".format(e))
        fail_count += 1
        tick_err = True

    if not tick_err:
        # 再用泵循环辅助函数跑500ms
        try:
            _pump_loop(pwm, event_bus, 500, 10)
            print("  OK 泵循环500ms无异常")
            pass_count += 1
        except Exception as e:
            print("  FAIL 泵循环异常: {}".format(e))
            fail_count += 1

    # ====== [步骤8] get_data()返回有效值 ======
    print("\n[步骤8] get_data()返回值校验...")
    pwm.set_brightness(75)
    data = pwm.get_data()
    data_ok = True
    if "duty_cycle" not in data:
        print("  FAIL 缺少duty_cycle字段")
        data_ok = False
    elif data["duty_cycle"] != 75:
        print("  FAIL duty_cycle={} (期望75)".format(data["duty_cycle"]))
        data_ok = False

    if "valid" not in data:
        print("  FAIL 缺少valid字段")
        data_ok = False
    elif data["valid"] is not True:
        print("  FAIL valid={} (期望True)".format(data["valid"]))
        data_ok = False

    if "timestamp" not in data:
        print("  FAIL 缺少timestamp字段")
        data_ok = False

    if data_ok:
        print("  OK get_data: duty_cycle={}, valid={}, timestamp={}".format(
            data["duty_cycle"], data["valid"], data["timestamp"]))
        pass_count += 1
    else:
        fail_count += 1

    # ====== [步骤9] get_status()返回is_init=True ======
    print("\n[步骤9] get_status()返回值校验...")
    status = pwm.get_status()
    status_ok = True
    for key in ("is_init", "is_busy", "err_count", "power_state"):
        if key not in status:
            print("  FAIL 缺少{}字段".format(key))
            status_ok = False

    if status["is_init"] is not True:
        print("  FAIL is_init={} (期望True)".format(status["is_init"]))
        status_ok = False

    if status_ok:
        print("  OK get_status: is_init={}, is_busy={}, err_count={}, power={}".format(
            status["is_init"], status["is_busy"],
            status["err_count"], status["power_state"]))
        pass_count += 1
    else:
        fail_count += 1

    # ====== [步骤10] 功耗状态切换 ======
    print("\n[步骤10] 功耗状态切换测试...")
    pwm.set_brightness(80)
    pwm._on_config_update({"power_state": "SUSPENDED"})
    data = pwm.get_data()
    if data["duty_cycle"] == 0:
        print("  OK SUSPENDED状态占空比归零")
        pass_count += 1
    else:
        print("  FAIL SUSPENDED后duty_cycle={} (期望0)".format(data["duty_cycle"]))
        fail_count += 1

    pwm._on_config_update({"power_state": "ACTIVE"})
    pwm.set_brightness(60)
    data = pwm.get_data()
    if data["duty_cycle"] == 60:
        print("  OK 恢复ACTIVE后set_brightness(60)正常")
        pass_count += 1
    else:
        print("  FAIL ACTIVE恢复后duty_cycle={} (期望60)".format(data["duty_cycle"]))
        fail_count += 1

    # ====== [步骤11] deinit清理 ======
    print("\n[步骤11] deinit清理...")
    try:
        pwm.deinit()
        status = pwm.get_status()
        if status["is_init"] is False:
            print("  OK deinit后is_init=False")
            pass_count += 1
        else:
            print("  FAIL deinit后is_init={} (期望False)".format(status["is_init"]))
            fail_count += 1
    except Exception as e:
        print("  FAIL deinit异常: {}".format(e))
        fail_count += 1

    # ====== 测试总结 ======
    print("\n" + "=" * 50)
    print("PWM_LED单模块测试完成: 通过={}, 失败={}".format(pass_count, fail_count))
    print("=" * 50)


if __name__ == "__main__":
    test_pwm_led()
