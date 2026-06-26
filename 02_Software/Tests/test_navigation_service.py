"""
brief NavigationService 单模块测试（纯 fake 数据）
note 不依赖真实 Audio/LCD 硬件，使用 Fake 对象记录调用
     验证事件流转、JSON 解析、方向映射、TTS 文本构造、LCD 写入
执行: 上传到板子运行 python test_navigation_service.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_NAV_CMD,
    TTS_NAV_TURN, TTS_NAV_ROAD, TTS_NAV_ARRIVE, TTS_NAV_CANCEL,
)
from Modules.navigation_service import NavigationService


class FakeAudio:
    def __init__(self):
        self.calls = []
        self.ctx = {"is_init": True, "is_busy": False}
    def play_tts(self, text):
        self.calls.append(("play_tts", text))
        return True
    def stop(self):
        self.calls.append(("stop",))


class FakeLCD:
    """模拟 LCDDriver，记录 show_string 调用"""
    def __init__(self):
        self.calls = []
        self.ctx = {"is_init": True, "display_mode": "normal"}
        # 模拟 lcd 子对象（DisplayService 的写入方式）
        self.lcd = self
        self.WHITE = 0xFFFF
        self.BLACK = 0x0000
        self.RED = 0xF800
        self.GREEN = 0x07E0
    def show_string(self, x, y, text, fg, bg):
        self.calls.append(("show_string", x, y, text, fg, bg))
    def fill_rectangle(self, x, y, w, h, color):
        self.calls.append(("fill_rectangle", x, y, w, h, color))
    def clear(self):
        self.calls.append(("clear",))


def make_service():
    """创建已 init 的 NavigationService 及 Fake 设备"""
    bus = EventBus()
    audio = FakeAudio()
    lcd = FakeLCD()
    svc = NavigationService(bus, audio_driver=audio)
    svc.init()
    return svc, bus, audio, lcd


# ==================== 测试用例 ====================

def test_parse_nav_right():
    """右转指令 → TTS 播报 + LCD 导航行"""
    svc, bus, audio, lcd = make_service()
    cmd = '{"a":"nav","d":{"dir":"right","dist":200,"road":"中山路"}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()
    # TTS: "前方200米右转进入中山路"
    assert len(audio.calls) == 1, "play_tts called once"
    assert audio.calls[0][0] == "play_tts"
    assert "200" in audio.calls[0][1]
    assert "右转" in audio.calls[0][1]
    assert "中山路" in audio.calls[0][1]
    # LCD: 底部写导航行
    assert any(c[0] == "show_string" and c[2] == 110 for c in lcd.calls), "LCD y=110"
    print("  OK parse_nav_right")


def test_parse_nav_straight():
    """直行指令 → TTS 播报"""
    svc, bus, audio, lcd = make_service()
    cmd = '{"a":"nav","d":{"dir":"straight","dist":500,"road":"人民路"}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()
    assert "直行" in audio.calls[0][1]
    assert "500" in audio.calls[0][1]
    print("  OK parse_nav_straight")


def test_parse_nav_arrive():
    """到达目的地 → TTS 播报"""
    svc, bus, audio, lcd = make_service()
    cmd = '{"a":"nav","d":{"dir":"arrive","dist":0,"road":""}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()
    assert TTS_NAV_ARRIVE in audio.calls[0][1]
    print("  OK parse_nav_arrive")


def test_parse_nav_cancel():
    """导航取消 → TTS 播报"""
    svc, bus, audio, lcd = make_service()
    cmd = '{"a":"nav","d":{"dir":"cancel","dist":0,"road":""}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()
    assert TTS_NAV_CANCEL in audio.calls[0][1]
    print("  OK parse_nav_cancel")


def test_direction_mapping():
    """所有方向映射正确"""
    from Modules.navigation_service import _map_direction
    assert _map_direction("left") == "左转"
    assert _map_direction("right") == "右转"
    assert _map_direction("straight") == "直行"
    assert _map_direction("slight_left") == "靠左"
    assert _map_direction("slight_right") == "靠右"
    assert _map_direction("uturn") == "掉头"
    assert _map_direction("arrive") == "到达目的地"
    assert _map_direction("cancel") == "导航结束"
    assert _map_direction("unknown") == "直行"  # fallback
    print("  OK direction_mapping")


def test_no_audio_no_crash():
    """无 Audio 引用时不崩溃"""
    bus = EventBus()
    svc = NavigationService(bus, audio_driver=None)
    svc.init()
    cmd = '{"a":"nav","d":{"dir":"right","dist":200,"road":"中山路"}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()
    # 不崩溃即通过
    print("  OK no_audio_no_crash")


def test_invalid_json_no_crash():
    """非法 JSON 不崩溃"""
    svc, bus, audio, lcd = make_service()
    bus.publish(EVENT_NAV_CMD, {"raw": "not json"})
    bus.pump()
    assert len(audio.calls) == 0, "invalid json → no TTS"
    print("  OK invalid_json_no_crash")


def test_non_nav_action_ignored():
    """非 nav action 被忽略"""
    svc, bus, audio, lcd = make_service()
    cmd = '{"a":"ctrl","d":{"cmd":"start"}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()
    assert len(audio.calls) == 0, "non-nav action → no TTS"
    print("  OK non_nav_action_ignored")


def test_nav_state_tracking():
    """导航状态正确跟踪"""
    svc, bus, audio, lcd = make_service()
    assert svc.ctx["is_navigating"] == False
    cmd = '{"a":"nav","d":{"dir":"right","dist":200,"road":"中山路"}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()
    assert svc.ctx["is_navigating"] == True
    assert svc.ctx["current_dir"] == "right"
    assert svc.ctx["current_dist"] == 200
    assert svc.ctx["current_road"] == "中山路"
    # 到达 → 停止导航
    cmd2 = '{"a":"nav","d":{"dir":"arrive","dist":0,"road":""}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd2})
    bus.pump()
    assert svc.ctx["is_navigating"] == False
    print("  OK nav_state_tracking")


def test_no_road_name():
    """无路名时 TTS 不包含"进入" """
    svc, bus, audio, lcd = make_service()
    cmd = '{"a":"nav","d":{"dir":"left","dist":100,"road":""}}'
    bus.publish(EVENT_NAV_CMD, {"raw": cmd})
    bus.pump()
    tts_text = audio.calls[0][1]
    assert "进入" not in tts_text
    assert "左转" in tts_text
    print("  OK no_road_name")


def test_get_data():
    """get_data 返回当前导航状态"""
    svc, bus, _, _ = make_service()
    d = svc.get_data()
    assert "is_navigating" in d
    assert "current_dir" in d
    print("  OK get_data")


def test_get_status():
    """get_status 返回模块状态"""
    svc, bus, _, _ = make_service()
    s = svc.get_status()
    assert "is_init" in s
    assert s["is_init"] == True
    print("  OK get_status")


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print(" NavigationService 单元测试")
    print("=" * 50)

    tests = [
        test_parse_nav_right,
        test_parse_nav_straight,
        test_parse_nav_arrive,
        test_parse_nav_cancel,
        test_direction_mapping,
        test_no_audio_no_crash,
        test_invalid_json_no_crash,
        test_non_nav_action_ignored,
        test_nav_state_tracking,
        test_no_road_name,
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
    print("=" * 50)
    print(" 结果: {} 通过, {} 失败".format(passed, failed))
    print("=" * 50)


if __name__ == "__main__":
    main()
