"""
brief PWMLEDDriver 闪烁功能单元测试
note 不依赖真实硬件，使用 Fake PWM 通道验证
      验证闪烁启停、tick 切换、占空比钳位、省电模式交互
执行: 上传到板子运行 python test_pwm_led_blink.py
"""
import sys
import time
sys.path.append("..")

from core.config import (
    PWM_BLINK_ON_DUTY, PWM_BLINK_INTERVAL_MS,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
    EVENT_POWER_STATE_CHANGE,
)


class FakePWMChannel:
    """记录 pulse_width_percent 调用"""
    def __init__(self):
        self.calls = []
        self._duty = 0

    def pulse_width_percent(self, duty):
        self.calls.append(("pulse_width_percent", duty))
        self._duty = duty


class FakePin:
    """Fake Pin for init bypass"""
    OUT = 0
    PULL_NONE = 0

    def __init__(self, name, mode, pull):
        self.name = name


def make_pwm():
    """创建已 init 的 PWMLEDDriver + Fake 通道"""
    from Drivers.actuator.PWM_LED import PWMLEDDriver
    pwm = PWMLEDDriver()
    pwm.pwm_channel = FakePWMChannel()
    pwm.ctx["is_init"] = True
    pwm.ctx["power_state"] = POWER_STATE_ACTIVE
    return pwm


# ==================== 测试用例 ====================

def test_init():
    """初始化后 blink 相关 ctx 字段存在且正确"""
    pwm = make_pwm()
    assert pwm.ctx["blink_active"] == False
    assert pwm.ctx["blink_on"] == False
    assert pwm.ctx["blink_from_alarm"] == False
    assert pwm.ctx["blink_last_toggle"] == 0
    assert pwm.cfg["blink_on_duty"] == PWM_BLINK_ON_DUTY
    assert pwm.cfg["blink_interval_ms"] == PWM_BLINK_INTERVAL_MS
    print("  OK init")


def test_start_blink():
    """start_blink() 设置 blink_active=True, blink_from_alarm=False"""
    pwm = make_pwm()
    pwm.start_blink()
    assert pwm.is_blink_active() == True
    assert pwm.is_blink_from_alarm() == False
    print("  OK start_blink")


def test_start_blink_alarm():
    """start_blink(from_alarm=True) 设置 blink_from_alarm=True"""
    pwm = make_pwm()
    pwm.start_blink(from_alarm=True)
    assert pwm.is_blink_active() == True
    assert pwm.is_blink_from_alarm() == True
    print("  OK start_blink(from_alarm=True)")


def test_start_blink_params():
    """start_blink() 支持自定义 duty 和 interval"""
    pwm = make_pwm()
    pwm.start_blink(on_duty=30, interval_ms=300)
    assert pwm.cfg["blink_on_duty"] == 30
    assert pwm.cfg["blink_interval_ms"] == 300
    print("  OK start_blink custom params")


def test_stop_blink():
    """stop_blink() 清除闪烁状态并熄灭 LED"""
    pwm = make_pwm()
    pwm.start_blink()
    pwm.stop_blink()
    assert pwm.is_blink_active() == False
    assert pwm.is_blink_from_alarm() == False
    assert pwm.pwm_channel._duty == 0
    print("  OK stop_blink")


def test_tick_toggle():
    """tick() 在时间到达后切换 0%↔on_duty"""
    pwm = make_pwm()
    pwm.start_blink()
    # 强制触发：让 ticks_diff 超过 interval
    pwm.ctx["blink_last_toggle"] = time.ticks_ms() - pwm.cfg["blink_interval_ms"] - 100
    pwm.tick()
    # 第一次 tick → blink_on 变为 True → duty=blink_on_duty
    assert pwm.ctx["blink_on"] == True
    assert pwm.pwm_channel._duty == PWM_BLINK_ON_DUTY
    # 第二次 tick → blink_on 变为 False → duty=0
    pwm.ctx["blink_last_toggle"] = time.ticks_ms() - pwm.cfg["blink_interval_ms"] - 100
    pwm.tick()
    assert pwm.ctx["blink_on"] == False
    assert pwm.pwm_channel._duty == 0
    print("  OK tick toggle 0%%<->%d%%" % PWM_BLINK_ON_DUTY)


def test_tick_no_premature():
    """tick() 在间隔未到时不切换"""
    pwm = make_pwm()
    pwm.start_blink()
    old_toggle = pwm.ctx["blink_last_toggle"]
    pwm.tick()
    assert pwm.ctx["blink_last_toggle"] == old_toggle
    assert pwm.ctx["blink_on"] == False
    print("  OK tick no premature")


def test_set_blink_duty():
    """set_blink_duty(30) 改变闪烁亮度"""
    pwm = make_pwm()
    pwm.set_blink_duty(30)
    assert pwm.cfg["blink_on_duty"] == 30
    print("  OK set_blink_duty(30)")


def test_set_blink_duty_clamp():
    """set_blink_duty() 越界钳位到 0-100"""
    pwm = make_pwm()
    pwm.set_blink_duty(-5)
    assert pwm.cfg["blink_on_duty"] == 0
    pwm.set_blink_duty(200)
    assert pwm.cfg["blink_on_duty"] == 100
    print("  OK set_blink_duty clamp")


def test_is_blink_active():
    """is_blink_active() 查询闪烁状态"""
    pwm = make_pwm()
    assert pwm.is_blink_active() == False
    pwm.start_blink()
    assert pwm.is_blink_active() == True
    print("  OK is_blink_active")


def test_is_blink_from_alarm():
    """is_blink_from_alarm() 查询报警标记"""
    pwm = make_pwm()
    pwm.start_blink(from_alarm=True)
    assert pwm.is_blink_from_alarm() == True
    print("  OK is_blink_from_alarm")


def test_set_brightness_blocked():
    """闪烁中 set_brightness() 被拒绝"""
    pwm = make_pwm()
    pwm.start_blink()
    pwm.set_brightness(50)
    assert pwm._data["duty_cycle"] != 50
    print("  OK set_brightness blocked during blink")


def test_set_brightness_normal():
    """非闪烁时 set_brightness() 正常"""
    pwm = make_pwm()
    pwm.set_brightness(50)
    assert pwm._data["duty_cycle"] == 50
    print("  OK set_brightness normal")


def test_power_save_stop_manual():
    """省电模式停止手动闪烁"""
    pwm = make_pwm()
    pwm.start_blink(from_alarm=False)
    pwm._on_config_update({"power_state": POWER_STATE_SUSPENDED})
    assert pwm.is_blink_active() == False
    print("  OK power save stops manual blink")


def test_power_save_keep_alarm():
    """省电模式保持报警闪烁"""
    pwm = make_pwm()
    pwm.start_blink(from_alarm=True)
    pwm._on_config_update({"power_state": POWER_STATE_SUSPENDED})
    assert pwm.is_blink_active() == True
    print("  OK power save keeps alarm blink")


def test_get_data():
    """get_data() 返回正确字段"""
    pwm = make_pwm()
    d = pwm.get_data()
    assert "duty_cycle" in d
    assert "valid" in d
    assert "timestamp" in d
    print("  OK get_data")


def test_get_status():
    """get_status() 返回正确字段"""
    pwm = make_pwm()
    s = pwm.get_status()
    assert "is_init" in s
    assert "err_count" in s
    assert "power_state" in s
    print("  OK get_status")


# ==================== 入口 ====================

def main():
    print("=" * 55)
    print(" PWM LED Blink 单元测试")
    print("=" * 55)

    tests = [
        test_init,
        test_start_blink,
        test_start_blink_alarm,
        test_start_blink_params,
        test_stop_blink,
        test_tick_toggle,
        test_tick_no_premature,
        test_set_blink_duty,
        test_set_blink_duty_clamp,
        test_is_blink_active,
        test_is_blink_from_alarm,
        test_set_brightness_blocked,
        test_set_brightness_normal,
        test_power_save_stop_manual,
        test_power_save_keep_alarm,
        test_get_data,
        test_get_status,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print("  FAIL {}: {}".format(t.__name__, e))
            failed += 1

    print("")
    print("=" * 55)
    print(" 结果: {} 通过, {} 失败 / 共 {}".format(passed, failed, len(tests)))
    print("=" * 55)


if __name__ == "__main__":
    main()
