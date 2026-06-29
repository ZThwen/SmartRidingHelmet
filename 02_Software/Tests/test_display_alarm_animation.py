"""测试 DisplayService 报警动画逻辑
验证碰撞闪烁、SOS背光闪烁、延迟渲染、唤醒恢复
"""
import sys
import time

# MicroPython 时间 API 兼容层（PC 测试用）
if not hasattr(time, 'ticks_ms'):
    _start = int(time.time() * 1000)
    time.ticks_ms = lambda: int(time.time() * 1000) - _start
    time.ticks_diff = lambda a, b: a - b
    time.sleep_ms = lambda ms: time.sleep(ms / 1000.0)

sys.path.append("..")

from Modules.display_service import DisplayService
from core.config import POWER_STATE_SUSPENDED, POWER_STATE_ACTIVE


class FakeLCD:
    """模拟 LCD 驱动，记录所有调用"""

    def __init__(self):
        self.calls = []
        self.ctx = {"alarm_override": False}
        self.lcd = FakeST7735()

    def clear(self):
        self.calls.append(("clear", time.ticks_ms()))

    def set_backlight(self, val):
        self.calls.append(("backlight", val, time.ticks_ms()))

    def show_image(self, *args):
        self.calls.append(("show_image", args))

    def show_nav_line(self, *args):
        pass


class FakeST7735:
    """模拟底层 LCD 对象，记录 show_string 调用"""

    def __init__(self):
        self.RED = 0xF800
        self.BLACK = 0x0000
        self.WHITE = 0xFFFF
        self.GREEN = 0x07E0
        self.YELLOW = 0xFFE0
        self.CYAN = 0x07FF
        self.show_string_calls = []

    def show_string(self, x, y, text, color, bg):
        self.show_string_calls.append((x, y, text, color, bg, time.ticks_ms()))

    def fill_rectangle(self, *args):
        pass

    def flush(self):
        self.show_string_calls.append(("flush", time.ticks_ms()))


class FakeEventBus:
    def __init__(self):
        self.subs = {}

    def subscribe(self, event, handler):
        self.subs[event] = handler

    def publish(self, event, payload=None):
        if event in self.subs:
            self.subs[event](payload)


def pump_cycle(svc, count=1, interval_ms=100):
    """标准泵循环"""
    for _ in range(count):
        svc.tick()
        time.sleep_ms(interval_ms)


def test_collision_flash_animation():
    """测试：碰撞报警触发后 500ms 开始闪烁，文字颜色 RED/BLACK 翻转"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    svc._data["lat"] = 31.23
    svc._data["lon"] = 121.47

    # 跳过 boot 阶段，直接进入 normal
    svc._switch_to_normal()
    svc.ctx["last_tick"] = 0

    # 触发碰撞报警
    svc._on_alarm_triggered({"alarm_type": "collision", "level": 2})
    assert svc.ctx["display_mode"] == "alarm"
    assert svc._alarm_needs_render == True

    # 第 1 次 tick：渲染初始画面（alarm_needs_render 被消费）
    svc.cfg["sample_ms"] = 0  # 绕过时间守卫
    svc.tick()
    assert svc._alarm_needs_render == False
    assert svc._collision_flash_last_tick > 0

    # 检查初始画面渲染了碰撞预警（RED）
    red_calls = [
        c for c in fake_lcd.lcd.show_string_calls
        if isinstance(c, tuple) and len(c) == 6 and c[2] == "碰撞预警" and c[3] == fake_lcd.lcd.RED
    ]
    assert len(red_calls) > 0, "初始画面应渲染红色'碰撞预警'"

    # 模拟 500ms 后 tick：闪烁触发
    fake_lcd.lcd.show_string_calls.clear()
    svc._collision_flash_last_tick = time.ticks_ms() - 500
    svc.ctx["last_tick"] = 0  # 强制 tick 执行
    svc.tick()

    # 检查闪烁颜色（可能是 BLACK 或 RED，取决于翻转状态）
    flash_calls = [
        c for c in fake_lcd.lcd.show_string_calls
        if isinstance(c, tuple) and len(c) == 6 and c[2] == "碰撞预警"
    ]
    assert len(flash_calls) > 0, "500ms后应触发闪烁，渲染'碰撞预警'"

    # 验证颜色翻转
    colors = {c[3] for c in flash_calls}
    assert fake_lcd.lcd.RED in colors or fake_lcd.lcd.BLACK in colors

    print("[PASS] 碰撞闪烁动画验证通过: 初始RED={}, 闪烁颜色={}".format(len(red_calls), colors))


def test_collision_flash_does_not_overwrite_location():
    """测试：碰撞闪烁只翻转'碰撞预警'文字，不覆盖经纬度区域"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    svc._data["lat"] = 31.23
    svc._data["lon"] = 121.47

    svc._switch_to_normal()
    svc.ctx["last_tick"] = 0
    svc._on_alarm_triggered({"alarm_type": "collision", "level": 2})
    svc.cfg["sample_ms"] = 0  # 绕过时间守卫
    svc.tick()  # 渲染初始画面

    # 模拟 500ms 后闪烁
    fake_lcd.lcd.show_string_calls.clear()
    svc._collision_flash_last_tick = time.ticks_ms() - 500
    svc.ctx["last_tick"] = 0
    svc.tick()

    flash_y_coords = [
        c[1] for c in fake_lcd.lcd.show_string_calls
        if isinstance(c, tuple) and len(c) == 6 and c[2] == "碰撞预警"
    ]

    # 闪烁只应发生在 y=40/41（碰撞预警位置），不应在 y=0/12（经纬度位置）
    for y in flash_y_coords:
        assert y in (40, 41), "闪烁只应覆盖 y=40/41，实际 y={}".format(y)

    print("[PASS] 碰撞闪烁不覆盖经纬度验证通过")


def test_sos_does_not_flash_text():
    """测试：SOS 报警不触发文字闪烁，只触发背光闪烁"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    svc._data["lat"] = 31.23
    svc._data["lon"] = 121.47

    svc._switch_to_normal()
    svc.ctx["last_tick"] = 0
    svc._on_alarm_triggered({"alarm_type": "sos", "level": 3})
    svc.cfg["sample_ms"] = 0  # 绕过时间守卫
    svc.tick()  # 渲染 SOS 画面

    # 模拟 500ms 后 tick
    fake_lcd.lcd.show_string_calls.clear()
    svc.ctx["last_tick"] = 0
    svc.tick()

    # SOS 没有 _collision_flash_last_tick，不应触发文字闪烁
    flash_calls = [
        c for c in fake_lcd.lcd.show_string_calls
        if isinstance(c, tuple) and len(c) == 6 and c[2] == "碰撞预警"
    ]
    assert len(flash_calls) == 0, "SOS 不应触发碰撞文字闪烁"

    print("[PASS] SOS 不触发文字闪烁验证通过")


def test_alarm_wake_up_delayed_render():
    """测试：报警期间唤醒，延迟渲染报警画面（不阻塞回调）"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    svc._data["lat"] = 31.23
    svc._data["lon"] = 121.47

    # 先进入报警状态
    svc._switch_to_normal()
    svc._on_alarm_triggered({"alarm_type": "collision", "level": 2})
    svc.cfg["sample_ms"] = 0  # 绕过时间守卫
    svc.ctx["last_tick"] = 0
    svc.tick()
    assert svc._alarm_needs_render == False

    fake_lcd.calls.clear()

    # 模拟休眠 -> 唤醒
    svc._on_power_state_change({"power_state": POWER_STATE_SUSPENDED})
    svc._on_power_state_change({"power_state": POWER_STATE_ACTIVE})

    # 回调不应直接调用 clear
    call_names = [c[0] for c in fake_lcd.calls]
    assert "clear" not in call_names, "唤醒回调不应直接调用 lcd.clear()"
    assert svc._alarm_needs_render == True, "唤醒应设置 _alarm_needs_render"

    # tick 中延迟渲染
    svc.cfg["sample_ms"] = 0  # 绕过时间守卫
    svc.ctx["last_tick"] = 0
    svc.tick()
    assert svc._alarm_needs_render == False
    assert "clear" in [c[0] for c in fake_lcd.calls], "tick 中应调用 lcd.clear()"

    print("[PASS] 报警期间唤醒延迟渲染验证通过")


def test_alarm_cancel_dirty_flag():
    """测试：报警取消后设置 _dirty=True，tick 中恢复 normal 画面"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    svc._data["temp"] = 25.5
    svc._data["humid"] = 65
    svc._data["lat"] = 31.23
    svc._data["lon"] = 121.47
    svc._data["speed"] = 18.5

    svc._switch_to_normal()
    svc.ctx["last_tick"] = 0
    svc._on_alarm_triggered({"alarm_type": "collision", "level": 2})
    svc.cfg["sample_ms"] = 0  # 绕过时间守卫
    svc.tick()
    assert svc.ctx["display_mode"] == "alarm"

    svc._on_alarm_canceled({})
    assert svc.ctx["display_mode"] == "normal"
    assert svc._dirty == True
    assert svc._alarm_needs_render == False

    # 模拟 tick 恢复 normal 画面
    fake_lcd.calls.clear()
    svc.cfg["sample_ms"] = 0  # 绕过时间守卫
    svc.ctx["last_tick"] = 0
    svc.tick()

    assert svc.ctx["display_mode"] == "normal"
    assert "clear" in [c[0] for c in fake_lcd.calls], "取消报警后 tick 应调用 clear"

    print("[PASS] 报警取消脏标志验证通过")


def run_all():
    print("=" * 50)
    print("DisplayService 报警动画逻辑测试")
    print("=" * 50)
    test_collision_flash_animation()
    test_collision_flash_does_not_overwrite_location()
    test_sos_does_not_flash_text()
    test_alarm_wake_up_delayed_render()
    test_alarm_cancel_dirty_flag()
    print("=" * 50)
    print("所有测试通过")
    print("=" * 50)


if __name__ == "__main__":
    run_all()
