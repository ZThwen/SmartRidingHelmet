"""
brief Wave 3 通信层集成测试 - NavigationService
note 验证 NavigationService 接收 BLE 导航指令后正确驱动 TTS + LCD
     使用 FakeAudio + FakeLCD 隔离硬件，纯事件驱动验证
     上传到板子运行: python test_navigation_service_integration.py
"""
import sys
import time
import json

# CPython 兼容：MicroPython 专有函数垫片
if not hasattr(time, "ticks_ms"):
    time.ticks_ms = lambda: int(time.time() * 1000)
if not hasattr(time, "ticks_diff"):
    time.ticks_diff = lambda a, b: a - b
if not hasattr(time, "sleep_ms"):
    time.sleep_ms = lambda ms: time.sleep(ms / 1000.0)

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_NAV_CMD,
    EVENT_POWER_STATE_CHANGE, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
    TTS_NAV_ARRIVE, TTS_NAV_CANCEL,
)
from Modules.navigation_service import NavigationService, _map_direction


# ==================== Fake 硬件 ====================

class FakeAudio:
    """
    brief 模拟 AudioDriver，记录 play_tts 调用
    note NavigationService 在子线程调用 play_tts，
         FakeAudio 仅记录调用参数，不阻塞
    """
    def __init__(self):
        self.calls = []
        self.ctx = {"is_init": True, "is_busy": False}

    def play_tts(self, text):
        """记录 TTS 播放请求"""
        self.calls.append(("play_tts", text))
        return True

    def stop(self):
        """记录停止播放"""
        self.calls.append(("stop",))


class FakeLCD:
    """
    brief 模拟 LCDDriver，记录 show_string / fill_rectangle 调用
    note NavigationService 通过 lcd_driver.lcd 访问底层 LCD 对象
    """
    def __init__(self):
        self.calls = []
        self.ctx = {"is_init": True, "display_mode": "normal"}
        # 模拟 lcd 子对象（NavigationService._write_nav_line 通过 lcd_driver.lcd 访问）
        self.lcd = self
        self.WHITE = 0xFFFF
        self.BLACK = 0x0000
        self.RED = 0xF800
        self.GREEN = 0x07E0

    def show_string(self, x, y, text, fg, bg):
        """记录字符串显示"""
        self.calls.append(("show_string", x, y, text, fg, bg))

    def fill_rectangle(self, x, y, w, h, color):
        """矩形填充（用于清除旧内容）"""
        self.calls.append(("fill_rectangle", x, y, w, h, color))

    def clear(self):
        """清屏"""
        self.calls.append(("clear",))


# ==================== 系统构建 ====================

def make_system():
    """
    brief 构建最小测试系统：EventBus + FakeAudio + FakeLCD + NavigationService
    return (bus, audio, lcd, nav) 元组
    """
    bus = EventBus()
    audio = FakeAudio()
    lcd = FakeLCD()
    nav = NavigationService(bus, audio_driver=audio, lcd_driver=lcd)
    nav.init()
    return bus, audio, lcd, nav


def publish_nav(bus, dir_str, dist, road):
    """
    brief 发布导航指令事件
    param bus: EventBus 实例
    param dir_str: 方向字符串（如 "right", "left", "arrive"）
    param dist: 距离（米）
    param road: 路名（可为空字符串）
    """
    cmd = json.dumps({"a": "nav", "d": {"dir": dir_str, "dist": dist, "road": road}})
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()


def pump_loop(bus, duration_ms):
    """
    brief 泵循环辅助：在指定时间内持续泵送事件
    param bus: EventBus 实例
    param duration_ms: 持续时间（毫秒）
    note 使用 ticks_diff 计算剩余时间，避免阻塞
    """
    end = time.ticks_ms() + duration_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        bus.pump()
        time.sleep_ms(50)


def wait_tts_done(duration_ms):
    """
    brief 等待 TTS 子线程完成
    note NavigationService 在子线程调用 play_tts，
         需要短暂等待让线程执行完毕
    """
    pump_loop_dummy = duration_ms
    time.sleep_ms(duration_ms)


# ==================== 测试用例 ====================

def test_01_init_success():
    """测试1: init() 成功 → is_init=True, 订阅 EVENT_NAV_CMD"""
    bus, audio, lcd, nav = make_system()
    # 验证初始化标志
    assert nav.ctx["is_init"] is True, "init 应成功设置 is_init=True"
    # 验证事件订阅
    subs = bus._subscribers.get(EVENT_NAV_CMD, [])
    assert len(subs) > 0, "应订阅 EVENT_NAV_CMD"
    # 验证其他事件订阅
    subs_power = bus._subscribers.get(EVENT_POWER_STATE_CHANGE, [])
    assert len(subs_power) > 0, "应订阅 EVENT_POWER_STATE_CHANGE"
    subs_alarm = bus._subscribers.get(EVENT_ALARM_TRIGGERED, [])
    assert len(subs_alarm) > 0, "应订阅 EVENT_ALARM_TRIGGERED"
    subs_cancel = bus._subscribers.get(EVENT_ALARM_CANCELED, [])
    assert len(subs_cancel) > 0, "应订阅 EVENT_ALARM_CANCELED"
    print("  OK test_01_init_success")


def test_02_nav_right_200m():
    """测试2: 导航指令 right + dist=200 → TTS '前方200米右转'"""
    bus, audio, lcd, nav = make_system()
    publish_nav(bus, "right", 200, "测试路")
    # 等待 TTS 子线程完成
    wait_tts_done(200)
    # 验证 TTS 调用
    assert len(audio.calls) >= 1, "应调用 play_tts, 实际: %s" % audio.calls
    tts_text = audio.calls[0][1]
    assert "200" in tts_text, "TTS 应包含距离 200, 实际: %s" % tts_text
    assert "右转" in tts_text, "TTS 应包含方向 右转, 实际: %s" % tts_text
    # 验证状态更新
    assert nav.ctx["current_dir"] == "right", "方向应为 right"
    assert nav.ctx["current_dist"] == 200, "距离应为 200"
    assert nav.ctx["is_navigating"] is True, "应处于导航状态"
    print("  OK test_02_nav_right_200m")


def test_03_nav_left_100m():
    """测试3: 导航指令 left + dist=100 → TTS '前方100米左转'"""
    bus, audio, lcd, nav = make_system()
    publish_nav(bus, "left", 100, "")
    wait_tts_done(200)
    # 验证 TTS
    assert len(audio.calls) >= 1, "应调用 play_tts"
    tts_text = audio.calls[0][1]
    assert "100" in tts_text, "TTS 应包含距离 100, 实际: %s" % tts_text
    assert "左转" in tts_text, "TTS 应包含方向 左转, 实际: %s" % tts_text
    # 无路名时不应包含"进入"
    assert "进入" not in tts_text, "无路名时 TTS 不应包含'进入', 实际: %s" % tts_text
    print("  OK test_03_nav_left_100m")


def test_04_nav_arrive():
    """测试4: 导航指令 arrive → TTS TTS_NAV_ARRIVE ('已到达目的地')"""
    bus, audio, lcd, nav = make_system()
    publish_nav(bus, "arrive", 0, "")
    wait_tts_done(200)
    # 验证 TTS
    assert len(audio.calls) >= 1, "应调用 play_tts"
    tts_text = audio.calls[0][1]
    assert tts_text == TTS_NAV_ARRIVE, \
        "TTS 应为 '%s', 实际: '%s'" % (TTS_NAV_ARRIVE, tts_text)
    # 到达后导航状态应关闭
    assert nav.ctx["is_navigating"] is False, "到达后 is_navigating 应为 False"
    print("  OK test_04_nav_arrive")


def test_05_nav_cancel():
    """测试5: 导航指令 cancel → TTS TTS_NAV_CANCEL ('导航已结束')"""
    bus, audio, lcd, nav = make_system()
    # 先进入导航状态
    publish_nav(bus, "right", 200, "测试路")
    wait_tts_done(200)
    assert nav.ctx["is_navigating"] is True, "应先处于导航状态"
    # 发送 cancel
    publish_nav(bus, "cancel", 0, "")
    wait_tts_done(200)
    # 验证最后一次 TTS 为 cancel 文本
    tts_texts = [c[1] for c in audio.calls if c[0] == "play_tts"]
    assert len(tts_texts) >= 2, "应有至少 2 次 TTS 调用, 实际: %d" % len(tts_texts)
    last_tts = tts_texts[-1]
    assert last_tts == TTS_NAV_CANCEL, \
        "TTS 应为 '%s', 实际: '%s'" % (TTS_NAV_CANCEL, last_tts)
    # 取消后导航状态应关闭
    assert nav.ctx["is_navigating"] is False, "取消后 is_navigating 应为 False"
    print("  OK test_05_nav_cancel")


def test_06_direction_mapping():
    """测试6: 方向映射正确: straight→直行, uturn→掉头, slight_left→靠左"""
    # 验证 _map_direction 函数
    assert _map_direction("straight") == "直行", "straight 应映射为 直行"
    assert _map_direction("uturn") == "掉头", "uturn 应映射为 掉头"
    assert _map_direction("slight_left") == "靠左", "slight_left 应映射为 靠左"
    assert _map_direction("left") == "左转", "left 应映射为 左转"
    assert _map_direction("right") == "右转", "right 应映射为 右转"
    assert _map_direction("slight_right") == "靠右", "slight_right 应映射为 靠右"
    # 验证端到端：发送 slight_left 指令，TTS 包含"靠左"
    bus, audio, lcd, nav = make_system()
    publish_nav(bus, "slight_left", 300, "大路")
    wait_tts_done(200)
    assert len(audio.calls) >= 1, "应调用 play_tts"
    tts_text = audio.calls[0][1]
    assert "靠左" in tts_text, "TTS 应包含 靠左, 实际: %s" % tts_text
    # 验证 uturn
    bus2, audio2, lcd2, nav2 = make_system()
    publish_nav(bus2, "uturn", 50, "")
    wait_tts_done(200)
    assert len(audio2.calls) >= 1, "uturn 应调用 play_tts"
    tts_text2 = audio2.calls[0][1]
    assert "掉头" in tts_text2, "TTS 应包含 掉头, 实际: %s" % tts_text2
    print("  OK test_06_direction_mapping")


def test_07_lcd_display_updated():
    """测试7: LCD 显示更新 — 导航指令写入 LCD 底部导航行"""
    bus, audio, lcd, nav = make_system()
    publish_nav(bus, "right", 200, "中山路")
    wait_tts_done(200)
    # 验证 LCD 写入
    show_calls = [c for c in lcd.calls if c[0] == "show_string"]
    assert len(show_calls) >= 1, "应调用 show_string, 实际调用: %s" % lcd.calls
    # 验证 y 坐标为 110（导航行位置）
    nav_show = [c for c in show_calls if c[2] == 110]
    assert len(nav_show) >= 1, "应在 y=110 写导航行, 实际: %s" % show_calls
    # 验证文本包含方向符号和距离
    lcd_text = nav_show[0][3]  # show_string(x, y, text, fg, bg) 的 text
    assert ">" in lcd_text, "LCD 应包含 > 符号(右转), 实际: %s" % lcd_text
    assert "200" in lcd_text or "200m" in lcd_text, \
        "LCD 应包含距离, 实际: %s" % lcd_text
    # 验证 fill_rectangle 被调用（清除旧内容）
    fill_calls = [c for c in lcd.calls if c[0] == "fill_rectangle"]
    assert len(fill_calls) >= 1, "应调用 fill_rectangle 清除旧内容"
    print("  OK test_07_lcd_display_updated")


def test_08_power_suspended_nav_works():
    """测试8: SUSPENDED 电源状态 → 导航处理仍工作（TTS 正常，LCD 跳过）"""
    bus, audio, lcd, nav = make_system()
    # 先切换到 SUSPENDED 状态
    bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_SUSPENDED})
    bus.pump()
    assert nav.ctx["power_state"] == POWER_STATE_SUSPENDED, "电源状态应为 SUSPENDED"
    # 发送导航指令
    publish_nav(bus, "right", 150, "省电路")
    wait_tts_done(200)
    # TTS 应正常播放（SUSPENDED 不抑制 TTS）
    assert len(audio.calls) >= 1, "SUSPENDED 下 TTS 应正常播放"
    tts_text = audio.calls[0][1]
    assert "150" in tts_text, "TTS 应包含距离, 实际: %s" % tts_text
    assert "右转" in tts_text, "TTS 应包含方向, 实际: %s" % tts_text
    # LCD 应被跳过（SUSPENDED 模式不写 LCD）
    show_calls = [c for c in lcd.calls if c[0] == "show_string"]
    assert len(show_calls) == 0, \
        "SUSPENDED 下不应写 LCD, 实际: %s" % show_calls
    # 但数据状态应更新
    assert nav.ctx["current_dir"] == "right", "数据状态应更新"
    assert nav.ctx["current_dist"] == 150, "距离应更新"
    print("  OK test_08_power_suspended_nav_works")


def test_09_alarm_suppresses_tts():
    """测试9: 报警触发 → 导航 TTS 被抑制（静默报警期间不播放 TTS）"""
    bus, audio, lcd, nav = make_system()
    # 触发静默报警（stealth 类型抑制 TTS）
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "stealth"})
    bus.pump()
    assert nav.ctx["alarm_active"] is True, "报警应激活"
    assert nav.ctx["alarm_type"] == "stealth", "报警类型应为 stealth"
    # 发送导航指令
    publish_nav(bus, "left", 100, "报警路")
    wait_tts_done(200)
    # TTS 不应被调用（静默报警期间跳过）
    tts_calls = [c for c in audio.calls if c[0] == "play_tts"]
    assert len(tts_calls) == 0, \
        "静默报警期间不应调用 play_tts, 实际: %s" % tts_calls
    # 但数据状态应更新（导航数据仍然记录）
    assert nav.ctx["current_dir"] == "left", "数据状态应更新"
    assert nav.ctx["current_dist"] == 100, "距离应更新"
    # 报警取消后，TTS 应恢复
    bus.publish(EVENT_ALARM_CANCELED, {})
    bus.pump()
    assert nav.ctx["alarm_active"] is False, "报警应已取消"
    # 再次发送导航指令
    publish_nav(bus, "right", 200, "恢复路")
    wait_tts_done(200)
    tts_calls_after = [c for c in audio.calls if c[0] == "play_tts"]
    assert len(tts_calls_after) >= 1, \
        "报警取消后 TTS 应恢复, 实际: %s" % tts_calls_after
    print("  OK test_09_alarm_suppresses_tts")


# ==================== 主入口 ====================

def run_all():
    """运行所有测试"""
    print("=" * 50)
    print(" Wave 3 NavigationService 集成测试")
    print("=" * 50)

    tests = [
        test_01_init_success,
        test_02_nav_right_200m,
        test_03_nav_left_100m,
        test_04_nav_arrive,
        test_05_nav_cancel,
        test_06_direction_mapping,
        test_07_lcd_display_updated,
        test_08_power_suspended_nav_works,
        test_09_alarm_suppresses_tts,
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

    print("")
    print("=" * 50)
    print(" 结果: %d 通过 / %d 失败 / 总计 %d" % (passed, failed, len(tests)))
    print("=" * 50)
    if failed == 0:
        print(" 全部通过!")
    return failed


if __name__ == "__main__":
    run_all()
