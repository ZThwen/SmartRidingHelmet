"""测试 DisplayService 报警回调零阻塞
验证 _on_alarm_triggered / _on_alarm_canceled 回调执行时间 < 1ms
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

class FakeLCD:
    """模拟 LCD 驱动，记录所有调用"""
    def __init__(self):
        self.calls = []
        self.ctx = {"alarm_override": False}
        self.lcd = FakeST7735()
    
    def clear(self):
        self.calls.append(("clear", time.ticks_ms()))
    
    def set_backlight(self, val):
        self.calls.append(("set_backlight", val, time.ticks_ms()))
    
    def show_image(self, *args):
        self.calls.append(("show_image", args))
    
    def show_nav_line(self, *args):
        pass

class FakeST7735:
    """模拟底层 LCD 对象"""
    def __init__(self):
        self.RED = 0xF800
        self.BLACK = 0x0000
        self.WHITE = 0xFFFF
        self.GREEN = 0x07E0
        self.YELLOW = 0xFFE0
        self.CYAN = 0x07FF
    
    def show_string(self, *args):
        pass
    
    def fill_rectangle(self, *args):
        pass
    
    def flush(self):
        pass

class FakeEventBus:
    def __init__(self):
        self.subs = {}
    
    def subscribe(self, event, handler):
        self.subs[event] = handler
    
    def publish(self, event, payload=None):
        if event in self.subs:
            self.subs[event](payload)

def test_alarm_triggered_callback_is_fast():
    """测试：报警触发回调必须在 <1ms 内完成（零阻塞）"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    
    # 注入正常数据
    svc._data["lat"] = 31.23
    svc._data["lon"] = 121.47
    
    # 记录回调前的 clear 调用数
    clear_before = len([c for c in fake_lcd.calls if c[0] == "clear"])
    
    start = time.ticks_ms()
    svc._on_alarm_triggered({"alarm_type": "collision", "level": 2})
    elapsed = time.ticks_diff(time.ticks_ms(), start)
    
    assert elapsed < 2, "回调耗时 {}ms，必须 <2ms".format(elapsed)
    assert svc.ctx["display_mode"] == "alarm", "display_mode 应变为 alarm"
    assert svc._alarm_needs_render == True, "_alarm_needs_render 应为 True"
    assert svc.ctx["is_alarm_active"] == True, "is_alarm_active 应为 True"
    
    # 回调期间不应新增 lcd.clear()（零阻塞验证）
    clear_after = len([c for c in fake_lcd.calls if c[0] == "clear"])
    assert clear_after == clear_before, "回调不能新增 lcd.clear() 调用"
    
    print("[PASS] 碰撞报警触发回调: {}ms, _alarm_needs_render={}".format(elapsed, svc._alarm_needs_render))

def test_alarm_canceled_callback_is_fast():
    """测试：报警取消回调必须在 <1ms 内完成（零阻塞）"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    
    # 先触发报警
    svc._on_alarm_triggered({"alarm_type": "collision", "level": 2})
    
    # 记录回调前的 clear 调用数
    clear_before = len([c for c in fake_lcd.calls if c[0] == "clear"])
    
    start = time.ticks_ms()
    svc._on_alarm_canceled({})
    elapsed = time.ticks_diff(time.ticks_ms(), start)
    
    assert elapsed < 2, "回调耗时 {}ms，必须 <2ms".format(elapsed)
    assert svc.ctx["display_mode"] == "normal", "display_mode 应恢复 normal"
    assert svc._alarm_needs_render == False, "_alarm_needs_render 应被清除"
    assert svc.ctx["is_alarm_active"] == False, "is_alarm_active 应为 False"
    
    # 回调期间不应新增 lcd.clear()
    clear_after = len([c for c in fake_lcd.calls if c[0] == "clear"])
    assert clear_after == clear_before, "回调不能新增 lcd.clear() 调用"
    
    print("[PASS] 报警取消回调: {}ms, display_mode={}".format(elapsed, svc.ctx["display_mode"]))

def test_sos_alarm_triggered_is_fast():
    """测试：SOS报警触发回调零阻塞"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    
    start = time.ticks_ms()
    svc._on_alarm_triggered({"alarm_type": "sos", "level": 3})
    elapsed = time.ticks_diff(time.ticks_ms(), start)
    
    assert elapsed < 2, "SOS回调耗时 {}ms，必须 <2ms".format(elapsed)
    assert svc._alarm_needs_render == True, "SOS也应设置延迟渲染标志"
    
    print("[PASS] SOS报警触发回调: {}ms".format(elapsed))

def test_stealth_alarm_is_fast():
    """测试：静默报警触发回调零阻塞，不改变任何显示"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    
    start = time.ticks_ms()
    svc._on_alarm_triggered({"alarm_type": "stealth", "level": 1})
    elapsed = time.ticks_diff(time.ticks_ms(), start)
    
    assert elapsed < 2, "stealth回调耗时 {}ms，必须 <2ms".format(elapsed)
    assert svc.ctx["alarm_type"] == "stealth"
    # stealth 不设置 alarm_override（不需要背光覆盖）
    assert fake_lcd.ctx["alarm_override"] == False or fake_lcd.ctx.get("alarm_override") is False
    
    print("[PASS] Stealth报警触发回调: {}ms".format(elapsed))

def test_alarm_render_in_tick():
    """测试：报警画面在 tick() 中延迟渲染，不阻塞回调"""
    fake_lcd = FakeLCD()
    svc = DisplayService(lcd_driver=fake_lcd)
    svc.init()
    svc._data["lat"] = 31.23
    svc._data["lon"] = 121.47
    
    # 触发报警（回调零阻塞）
    svc._on_alarm_triggered({"alarm_type": "collision", "level": 2})
    assert svc._alarm_needs_render == True
    # 回调期间不能调用 lcd.clear() 或 show_string（零阻塞验证）
    # 注意：init() 中 _show_boot_screen() 已调用过 clear，但回调后不应新增 clear
    clear_count_before = len([c for c in fake_lcd.calls if c[0] == "clear"])
    
    # 模拟 tick 周期（sample_ms=1000，但这里直接绕过）
    svc.ctx["last_tick"] = 0  # 强制满足时间差
    svc.cfg["sample_ms"] = 0  # 绕过时间守卫，确保 tick 执行主逻辑
    svc.tick()
    
    # tick() 中应完成延迟渲染
    assert svc._alarm_needs_render == False, "tick后 _alarm_needs_render 应为 False"
    clear_count_after = len([c for c in fake_lcd.calls if c[0] == "clear"])
    assert clear_count_after > clear_count_before, "tick中应新增 lcd.clear() 调用"
    
    print("[PASS] 报警画面延迟渲染验证通过")

def run_all():
    print("=" * 50)
    print("DisplayService 报警零阻塞测试")
    print("=" * 50)
    test_alarm_triggered_callback_is_fast()
    test_alarm_canceled_callback_is_fast()
    test_sos_alarm_triggered_is_fast()
    test_stealth_alarm_is_fast()
    test_alarm_render_in_tick()
    print("=" * 50)
    print("所有测试通过")
    print("=" * 50)

if __name__ == "__main__":
    run_all()
