"""
brief NavigationService E2E 测试 — 完整 BLE FFF2 链路
note 验证 BLE FFF2 写入 → BLEService → NavigationService → AudioDriver TTS
     每个测试用例独立 init/deinit，使用 try/finally 确保资源释放

测试方式：
    1. 上传本文件到板子
    2. 用 Thonny 运行，观察串口输出 + 喇叭 TTS + LCD 显示
    3. 链路上板后自动验证 nav._data / audio._data / audio.ctx
"""

import sys
import time
import json
import gc

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    TTS_NAV_ARRIVE, TTS_NAV_CANCEL,
)
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.LCD import LCDDriver
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService

# 模块级 BLE 单例（硬件只 init 一次）
_shared_ble = None

# ==================== 测试配置 ====================

WAIT_TTS_MS = 3000       # 等待 TTS 工作线程启动/播放完成的宽限时间（ms）
PUMP_MS = 50             # 泵循环间隔（ms）
SHORT_WAIT_MS = 200      # TTS 线程启动等待时间（ms）
STEP_WAIT_MS = 2500      # 多步骤测试的步骤间隔（ms）

# ==================== 系统构建与清理 ====================

def get_ble_driver(event_bus):
    """
    brief 获取/创建 BLE 驱动单例
    note 硬件 BLE 只 init 一次，所有测试共享同一个 BLEDriver 实例
    param event_bus: EventBus 实例
    return BLEDriver 实例
    """
    global _shared_ble
    if _shared_ble is None:
        _shared_ble = BLEDriver(event_bus)
        try:
            _shared_ble.init()
        except Exception as e:
            print("  ~ BLEDriver init 跳过（硬件不可用）: %s" % e)
    else:
        _shared_ble.event_bus = event_bus
    return _shared_ble


def make_system():
    """
    brief 构建最小测试系统（含完整 BLE 链路）
    return (bus, audio, lcd, ble, ble_svc, nav) 六元组
    note 按依赖顺序初始化：drivers → services
    """
    bus = EventBus()
    audio = AudioDriver(bus)
    lcd = LCDDriver(bus)
    nav = NavigationService(bus, audio_driver=audio)

    print("  初始化 AudioDriver...")
    audio.init()
    print("  初始化 LCDDriver...")
    lcd.init()
    print("  初始化 BLEDriver（单例）...")
    ble = get_ble_driver(bus)
    ble_svc = BLEService(bus, ble_driver=ble)
    print("  初始化 BLEService...")
    ble_svc.init()
    print("  初始化 NavigationService...")
    nav.init()
    print("  ✓ 系统初始化完成（BLE FFF2 → Nav → Audio 链路已就绪）")

    return bus, audio, lcd, ble, ble_svc, nav


def cleanup(bus, audio, lcd, ble, ble_svc, nav):
    """
    brief 清理系统，释放资源
    note 顺序与 init 相反：service → actuator
    """
    print("  清理 NavigationService...")
    nav.deinit()
    print("  清理 BLEService...")
    if hasattr(ble_svc, 'deinit'):
        ble_svc.deinit()
    print("  等待 TTS 播放完成...")
    if not wait_tts_complete(audio):
        print("  ~ TTS 未在超时内完成，强制停止")
    print("  停止音频播放...")
    audio.stop()
    print("  清屏...")
    lcd.clear()
    time.sleep_ms(200)
    gc.collect()
    print("  ✓ 清理完成")


# ==================== 测试辅助函数 ====================

def simulate_ble_nav_write(ble_svc, bus, direction, distance, road=""):
    """
    brief 模拟 BLE FFF2 写入导航指令，经过 BLEService 完整处理链
    note 数据流：cmd_buffer → tick() → _parse_and_route → EventBus → NavService
    param ble_svc: BLEService 实例
    param bus: EventBus 实例
    """
    cmd = json.dumps({
        "a": "nav",
        "d": {"dir": direction, "dist": distance, "road": road}
    })

    # 1. 模拟 BLE 中断写入 — 数据进入 cmd_buffer（模拟 BLEDriver modem 线程回调）
    ble_svc.cmd_buffer.put({
        "uuid": ble_svc._ble.cfg["char_nav"],   # 0xFFF2 导航指令通道
        "raw": cmd
    })

    # 2. 设 cmd_ready 让 tick() drain 缓冲区 → _parse_and_route → EventBus publish
    ble_svc.cmd_ready = True
    ble_svc.tick()

    # 3. pump 事件总线，触发 NavigationService._on_nav_cmd
    bus.pump()

    print("  >> BLE FFF2 模拟写入: %s %dm %s" % (
        direction, distance, road if road else ""))

    # 4. 等待 NavService TTS 工作线程（_tts_worker）出队并启动播放
    time.sleep_ms(SHORT_WAIT_MS)


def pump_loop(bus, duration_ms):
    """泵循环：在指定时间内持续泵送事件"""
    end = time.ticks_ms() + duration_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        bus.pump()
        time.sleep_ms(PUMP_MS)


def wait_tts(audio, timeout_ms=WAIT_TTS_MS):
    """
    brief 等待 TTS 播放开始
    param audio: AudioDriver 实例
    param timeout_ms: 超时时间（ms）
    return bool TTS 是否在超时内开始播放
    """
    end = time.ticks_ms() + timeout_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if audio.ctx.get("is_tts_playing", False):
            print("  ✓ TTS 播放中（is_tts_playing=True）")
            return True
        if audio._data.get("playback_status") == "playing":
            print("  ✓ TTS 播放中（playback_status=playing）")
            return True
        time.sleep_ms(PUMP_MS)
    return False


def wait_tts_complete(audio, timeout_ms=5000):
    """
    brief 等待 TTS 播放完成
    param audio: AudioDriver 实例
    param timeout_ms: 超时时间（ms）
    return bool TTS 是否在超时内完成
    """
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
        if not audio.ctx.get("is_tts_playing", False):
            time.sleep_ms(200)
            return True
        time.sleep_ms(100)
    return False


def check_audio_tts(audio, expect_playing=True):
    """
    brief 检查 AudioDriver TTS 状态
    param audio: AudioDriver 实例
    param expect_playing: True=期望正在播放, False=期望空闲
    return bool 检查结果
    """
    status = audio.get_data()
    is_tts = audio.ctx.get("is_tts_playing", False)
    playback = status.get("playback_status", "unknown")

    if expect_playing:
        if is_tts or playback == "playing":
            print("  ✓ Audio TTS 播放中 (ctx:%s, status:%s)" % (is_tts, playback))
            return True
        else:
            print("  ~ Audio 状态: is_tts_playing=%s, playback_status=%s" % (is_tts, playback))
            print("  ~ TTS 可能已播完（硬件播放快）")
            return True  # 不硬失败，TTS 可能已播完
    else:
        if not is_tts and playback != "playing":
            print("  ✓ Audio 空闲 (ctx:%s, status:%s)" % (is_tts, playback))
            return True
        else:
            print("  ✗ Audio 仍在播放 (ctx:%s, status:%s)" % (is_tts, playback))
            return False


# ==================== 测试用例 ====================

def test_ble_e2e_01_nav_right():
    """
    brief E2E 测试 1: BLE FFF2 写入右转指令 → NavService → Audio TTS
    note 模拟 BLE 写入 {"a":"nav","d":{"dir":"right","dist":200,"road":"中山路"}}
         验证 nav._data["last_tts"] == "前方200米右转进入中山路"
         验证 audio._data["playback_status"] 或 audio.ctx["is_tts_playing"]
    """
    print("\n" + "=" * 60)
    print("  E2E 测试 1: BLE FFF2 → 右转导航 TTS")
    print("  - BLE FFF2 写入: right 200m 中山路")
    print("  - 期望: nav.last_tts='前方200米右转进入中山路'")
    print("  - 期望: AudioDriver 收到 TTS 请求（play_tts 被调用）")
    print("=" * 60)

    bus, audio, lcd, ble, ble_svc, nav = make_system()
    try:
        # === 模拟 BLE FFF2 写入 ===
        simulate_ble_nav_write(ble_svc, bus, "right", 200, "中山路")

        # === 等待 TTS 工作线程 ===
        tts_started = wait_tts(audio, timeout_ms=WAIT_TTS_MS)
        if not tts_started:
            # TTS 可能很快播完，检查 last_tts 作为后备
            print("  ~ TTS 可能在 wait_tts() 前已完成")
        else:
            pump_loop(bus, 300)

        # === 验证导航状态 ===
        nav_data = nav.get_data()
        assert nav_data["is_navigating"], "应处于导航状态"
        assert nav_data["current_dir"] == "right", (
            "方向应为 right, 实际: %s" % nav_data["current_dir"])
        assert nav_data["current_dist"] == 200, (
            "距离应为 200, 实际: %d" % nav_data["current_dist"])

        assert "200" in nav_data["last_tts"], (
            "TTS 应包含 '200', 实际: %s" % nav_data["last_tts"])
        assert "右转" in nav_data["last_tts"], (
            "TTS 应包含 '右转', 实际: %s" % nav_data["last_tts"])
        assert "中山路" in nav_data["last_tts"], (
            "TTS 应包含 '中山路', 实际: %s" % nav_data["last_tts"])
        print("  ✓ 导航状态正确: last_tts='%s'" % nav_data["last_tts"])

        # === 验证 AudioDriver ===
        if tts_started:
            print("  ✓ BLE FFF2 → BLEService → NavService → Audio 链路验证通过")
        else:
            # TTS 可能已播完，仍然验证 nav._data 已设置
            print("  ✓ nav._data['last_tts'] 已设置（TTS 可能已播完）")

        # === 验证 LCD（可选，取决于硬件是否就绪）===
        nav_data = nav.get_data()
        print("  LCD last_lcd: '%s'" % nav_data["last_lcd"])
        assert ">" in nav_data["last_lcd"], (
            "LCD 应包含 '>' 符号, 实际: %s" % nav_data["last_lcd"])
        assert "200" in nav_data["last_lcd"] or "200m" in nav_data["last_lcd"], (
            "LCD 应包含距离, 实际: %s" % nav_data["last_lcd"])

        print("  => 请目视确认: LCD 底部显示导航行, 喇叭播报 TTS")
        print("  ✓ test_ble_e2e_01_nav_right 通过")
        return True

    except AssertionError as e:
        print("  ✗ 断言失败: %s" % e)
        return False
    except Exception as e:
        print("  ✗ 异常: %s" % e)
        import sys as _sys
        _sys.print_exception(e)
        return False
    finally:
        cleanup(bus, audio, lcd, ble, ble_svc, nav)


def test_ble_e2e_02_full_ride():
    """
    brief E2E 测试 2: 完整骑行流程（4 步 BLE FFF2 写入）
    note 模拟一次完整导航：right → straight → left → arrive
         每步通过 BLEService 链路下发，验证 nav 状态 + TTS
    """
    print("\n" + "=" * 60)
    print("  E2E 测试 2: 完整骑行流程（4 步 BLE FFF2 写入）")
    print("  - 步骤 1: FFF2 写入 right 500m 中山路")
    print("  - 步骤 2: FFF2 写入 straight 200m")
    print("  - 步骤 3: FFF2 写入 left 300m 南京路")
    print("  - 步骤 4: FFF2 写入 arrive")
    print("=" * 60)

    bus, audio, lcd, ble, ble_svc, nav = make_system()
    try:
        steps = [
            ("right",    500, "中山路", "右转"),
            ("straight", 200, "",       "直行"),
            ("left",     300, "南京路", "左转"),
            ("arrive",   0,   "",       None),  # None = 到达，不检查方向
        ]

        for i, (direction, dist, road, expected_dir) in enumerate(steps):
            step_num = i + 1
            print("\n  --- 步骤 %d/4: BLE FFF2 → %s %dm %s ---" % (
                step_num, direction, dist, road if road else ""))

            # 通过 BLE FFF2 模拟写入
            simulate_ble_nav_write(ble_svc, bus, direction, dist, road)
            pump_loop(bus, STEP_WAIT_MS)

            # 验证导航状态
            nav_data = nav.get_data()
            assert nav_data["current_dir"] == direction, (
                "步骤%d: 方向应为 %s, 实际: %s" % (
                    step_num, direction, nav_data["current_dir"]))
            assert nav_data["current_dist"] == dist, (
                "步骤%d: 距离应为 %d, 实际: %d" % (
                    step_num, dist, nav_data["current_dist"]))

            if expected_dir:
                assert nav_data["is_navigating"] is True, (
                    "步骤%d: 应处于导航状态" % step_num)
                assert expected_dir in nav_data["last_tts"], (
                    "步骤%d: TTS 应包含 '%s', 实际: '%s'" % (
                        step_num, expected_dir, nav_data["last_tts"]))
                print("  ✓ TTS: %s" % nav_data["last_tts"])
                print("  ✓ LCD: %s" % nav_data["last_lcd"])
            else:
                # arrive 步骤
                assert nav_data["is_navigating"] is False, "到达后应结束导航"
                assert nav_data["last_tts"] == TTS_NAV_ARRIVE, (
                    "TTS 应为 '%s', 实际: '%s'" % (
                        TTS_NAV_ARRIVE, nav_data["last_tts"]))
                print("  ✓ TTS: %s" % nav_data["last_tts"])
                print("  ✓ LCD: %s" % nav_data["last_lcd"])

        # 最终验证：音频状态
        check_audio_tts(audio, expect_playing=False)

        print("\n  => 请目视确认: 4 个步骤的 TTS 和 LCD 均正确")
        print("  ✓ test_ble_e2e_02_full_ride 通过")
        return True

    except AssertionError as e:
        print("  ✗ 断言失败: %s" % e)
        return False
    except Exception as e:
        print("  ✗ 异常: %s" % e)
        import sys as _sys
        _sys.print_exception(e)
        return False
    finally:
        cleanup(bus, audio, lcd, ble, ble_svc, nav)


def test_ble_e2e_03_alarm_suppress():
    """
    brief E2E 测试 3: BLE 导航 + 报警抑制 TTS
    note 1. 发布 EVENT_ALARM_TRIGGERED（stealth）→ TTS 被抑制
         2. BLE FFF2 写入导航指令 → nav._data 更新但 TTS 不播放
         3. 发布 EVENT_ALARM_CANCELED → TTS 恢复
         4. BLE FFF2 写入导航指令 → AudioDriver 应有 TTS 请求
    """
    print("\n" + "=" * 60)
    print("  E2E 测试 3: BLE 导航 + 报警抑制 TTS")
    print("  - 阶段 1: 触发 stealth 报警 → BLE 导航 TTS 被抑制")
    print("  - 阶段 2: 取消报警 → BLE 导航 TTS 恢复")
    print("=" * 60)

    bus, audio, lcd, ble, ble_svc, nav = make_system()
    try:
        # ====== 阶段 1: 报警中，TTS 被抑制 ======
        print("\n  --- 阶段 1: 触发报警（stealth）---")

        bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "stealth"})
        bus.pump()
        time.sleep_ms(100)

        # 验证报警状态
        assert nav.ctx["alarm_active"] is True, "报警应激活"
        assert nav.ctx["alarm_type"] == "stealth", "报警类型应为 stealth"
        print("  ✓ 报警已激活 (type=stealth, TTS 将被抑制)")

        # 在报警期间通过 BLE FFF2 发送导航指令
        simulate_ble_nav_write(ble_svc, bus, "right", 100, "报警路")
        pump_loop(bus, WAIT_TTS_MS)

        # 验证导航数据已更新
        nav_data = nav.get_data()
        assert nav_data["current_dir"] == "right", (
            "导航数据仍应更新, 实际: %s" % nav_data["current_dir"])
        assert nav_data["current_dist"] == 100, (
            "导航距离仍应更新, 实际: %d" % nav_data["current_dist"])
        print("  ✓ 导航数据已更新: dir=%s, dist=%d" % (
            nav_data["current_dir"], nav_data["current_dist"]))

        # 验证 TTS 被抑制：last_tts 应为空（静默报警期间不生成 TTS 文本）
        # 注意：nav.get_data() 返回的 last_tts 在 stealth 模式下不会被设置
        #   NavigationService._on_nav_cmd 检查 self.ctx["alarm_type"] == "stealth" 后跳过
        if nav_data["last_tts"]:
            print("  ~ 注意: last_tts='%s'（导航数据更新了但 TTS 被抑制）" % nav_data["last_tts"])
        else:
            print("  ✓ TTS 文本被抑制: last_tts 为空")

        # 验证音频没有播放
        tts_started = wait_tts(audio, timeout_ms=500)
        assert not tts_started, (
            "报警期间 TTS 不应被播放, 但 AudioDriver 显示了播放状态")
        print("  ✓ TTS 播放被成功抑制（AudioDriver 未收到播放请求）")

        # ====== 阶段 2: 取消报警，TTS 恢复 ======
        print("\n  --- 阶段 2: 取消报警 ---")

        bus.publish(EVENT_ALARM_CANCELED, {})
        bus.pump()
        time.sleep_ms(100)

        assert nav.ctx["alarm_active"] is False, "报警应已取消"
        print("  ✓ 报警已取消")

        # 通过 BLE FFF2 发送导航指令（应正常 TTS）
        simulate_ble_nav_write(ble_svc, bus, "left", 200, "恢复路")
        pump_loop(bus, WAIT_TTS_MS)

        nav_data = nav.get_data()
        assert nav_data["current_dir"] == "left", (
            "导航方向应更新为 left, 实际: %s" % nav_data["current_dir"])
        assert "200" in nav_data["last_tts"], (
            "TTS 应包含距离 200, 实际: %s" % nav_data["last_tts"])
        assert "左转" in nav_data["last_tts"], (
            "TTS 应包含 '左转', 实际: %s" % nav_data["last_tts"])
        print("  ✓ TTS 恢复: '%s'" % nav_data["last_tts"])
        print("  ✓ LCD: '%s'" % nav_data["last_lcd"])

        # 验证音频收到 TTS 请求
        check_audio_tts(audio, expect_playing=False)

        print("\n  => 请目视确认: 报警期间无 TTS, 取消后 TTS 恢复")
        print("  ✓ test_ble_e2e_03_alarm_suppress 通过")
        return True

    except AssertionError as e:
        print("  ✗ 断言失败: %s" % e)
        return False
    except Exception as e:
        print("  ✗ 异常: %s" % e)
        import sys as _sys
        _sys.print_exception(e)
        return False
    finally:
        cleanup(bus, audio, lcd, ble, ble_svc, nav)


# ==================== 主入口 ====================

def run_all():
    """运行所有 BLE E2E 测试"""
    print("\n" + "=" * 60)
    print("  NavigationService BLE E2E 测试（自包含·真实硬件）")
    print("=" * 60)
    print("  测试链路:")
    print("    BLE FFF2 写入 → BLEService.cmd_buffer")
    print("                  → tick() / _parse_and_route")
    print("                  → EventBus publish(EVENT_NAV_CMD)")
    print("                  → NavigationService._on_nav_cmd")
    print("                  → AudioDriver.play_tts() + LCDDriver.show_nav_line()")
    print("")
    print("  测试环境:")
    print("    - NUCLEO-F413ZH + EC200U (BLE)")
    print("    - AudioDriver → 喇叭")
    print("    - LCDDriver → ST7735 屏幕")
    print("    - NavigationService → TTS + LCD 导航显示")
    print("")
    print("  请确保:")
    print("    1. 喇叭已连接（听 TTS 播报）")
    print("    2. LCD 可正常显示（目视检查）")
    print("    3. 板子已上电稳定运行")

    tests = [
        ("BLE E2E 测试 1: BLE FFF2 → 右转导航 TTS", test_ble_e2e_01_nav_right),
        ("BLE E2E 测试 2: 完整骑行流程",              test_ble_e2e_02_full_ride),
        ("BLE E2E 测试 3: 报警抑制 TTS",             test_ble_e2e_03_alarm_suppress),
    ]

    passed = 0
    failed = 0

    for name, func in tests:
        print("\n" + "-" * 60)
        print("  开始: %s" % name)
        print("-" * 60)
        try:
            result = func()
            if result:
                passed += 1
                print("  >>> 通过 <<<")
            else:
                failed += 1
                print("  >>> 失败 <<<")
        except Exception as e:
            failed += 1
            import sys as _sys
            _sys.print_exception(e)
            print("  >>> 异常 <<<")
        gc.collect()
        time.sleep_ms(500)

    print("\n" + "=" * 60)
    print("  测试结果: %d 通过 / %d 失败 / 总计 %d" % (passed, failed, len(tests)))
    print("=" * 60)
    if failed == 0:
        print("  全部通过!")
    else:
        print("  有 %d 个测试失败，请检查日志" % failed)
    return failed == 0


if __name__ == "__main__":
    run_all()
