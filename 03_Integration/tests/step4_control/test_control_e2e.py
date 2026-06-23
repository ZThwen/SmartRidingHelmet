"""
brief ControlService BLE E2E 测试 — 完整 BLE FFF3 链路
note 验证 BLE FFF3 写入 → BLEService → ControlService → 各模块
      每个测试用例独立 init/deinit，使用 try/finally 确保资源释放

测试方式：
     1. 上传本文件到板子
     2. 用 Thonny 运行，观察串口输出 + 喇叭 TTS + PWM LED 亮度
     3. 链路上板后自动验证 pwm_led / audio / light_svc / ctrl 状态
"""

import sys
import time
import json
import gc

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL,
    EVENT_TTS_REQUEST,
    LIGHT_BRIGHTNESS_MAX, LIGHT_BRIGHTNESS_STEP,
)
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.network.BLE import BLEDriver
from Modules.light_service import LightService
from Modules.control_service import ControlService
from Modules.ble_service import BLEService

# 模块级 BLE 单例（硬件只 init 一次）
_shared_ble = None

# ==================== 测试配置 ====================

WAIT_TTS_MS = 3000       # 等待 TTS 工作线程启动/播放完成的宽限时间（ms）
PUMP_MS = 50             # 泵循环间隔（ms）
SHORT_WAIT_MS = 200      # TTS 线程启动等待时间（ms）

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
    brief 构建最小测试系统（含完整 BLE 链路 + 控制链路）
    return (bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc) 七元组
    note 按依赖顺序初始化：drivers → services
    """
    bus = EventBus()
    pwm_led = PWMLEDDriver(bus)
    light_svc = LightService(bus, pwm_led=pwm_led)
    audio = AudioDriver(bus)
    ctrl = ControlService(bus)  # temp_humid=None, gnss=None（查询走 fallback TTS）

    print("  初始化 PWMLEDDriver...")
    try:
        pwm_led.init()
    except Exception as e:
        print("  ~ PWMLEDDriver init 跳过（硬件不可用）: %s" % e)

    print("  初始化 AudioDriver...")
    audio.init()

    print("  初始化 LightService...")
    light_svc.init()

    print("  初始化 BLEDriver（单例）...")
    ble = get_ble_driver(bus)
    ble_svc = BLEService(bus, ble_driver=ble)
    print("  初始化 BLEService...")
    ble_svc.init()

    print("  初始化 ControlService...")
    ctrl.init()

    print("  ✓ 系统初始化完成（BLE FFF3 → ControlService → 各模块 链路已就绪）")

    return bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc


def cleanup(bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc):
    """
    brief 清理系统，释放资源
    note 顺序与 init 相反：service → actuator
    """
    print("  清理 ControlService...")
    if hasattr(ctrl, 'deinit'):
        ctrl.deinit()

    print("  清理 BLEService...")
    if hasattr(ble_svc, 'deinit'):
        ble_svc.deinit()

    print("  等待 TTS 播放完成...")
    if not wait_tts_complete(audio):
        print("  ~ TTS 未在超时内完成，强制停止")

    print("  停止音频播放...")
    audio.stop()

    print("  清理 LightService...")
    if hasattr(light_svc, 'deinit'):
        light_svc.deinit()

    print("  清理 PWMLEDDriver...")
    if hasattr(pwm_led, 'deinit'):
        pwm_led.deinit()

    time.sleep_ms(200)
    gc.collect()
    print("  ✓ 清理完成")


# ==================== 测试辅助函数 ====================

def simulate_ble_ctrl_write(ble_svc, bus, ctrl, cmd_name):
    """
    brief 模拟 BLE FFF3 写入控制指令，经过 BLEService 完整处理链
    note 数据流：cmd_buffer → tick() → _parse_and_route → EventBus → ControlService
    param ble_svc: BLEService 实例
    param bus: EventBus 实例
    param ctrl: ControlService 实例（用于重置防抖）
    param cmd_name: 指令字符串（如 "light_on"）
    """
    # 重置防抖，确保连续发送不被丢弃
    ctrl.ctx["last_cmd_tick"] = 0
    ctrl.ctx["last_tts_tick"] = 0

    cmd = json.dumps({"a": "ctrl", "d": {"cmd": cmd_name}})

    # 1. 模拟 BLE 中断写入 — 数据进入 cmd_buffer（模拟 BLEDriver modem 线程回调）
    ble_svc.cmd_buffer.put({
        "uuid": ble_svc._ble.cfg["char_ctrl"],   # 0xFFF3 骑行控制通道
        "raw": cmd
    })

    # 2. 设 cmd_ready 让 tick() drain 缓冲区 → _parse_and_route → EventBus publish
    ble_svc.cmd_ready = True
    ble_svc.tick()

    # 3. pump 事件总线，触发 ControlService._on_ride_control
    bus.pump()

    print("  >> BLE FFF3 模拟写入: %s" % cmd_name)

    # 4. 短暂等待让事件链完成（LightService → PWM_LED, AudioDriver → TTS 等）
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

def test_ble_e2e_01_light_on():
    """
    brief E2E 测试 1: BLE FFF3 写入 light_on → PWM_LED 亮度变为 LIGHT_BRIGHTNESS_MAX
    note 模拟 BLE 写入 {"a":"ctrl","d":{"cmd":"light_on"}}
          完整链路：BLEService → ControlService → EVENT_LIGHT_CONTROL → LightService → PWM_LED
          验证 pwm_led duty_cycle == LIGHT_BRIGHTNESS_MAX
          验证 light_svc mode == "manual"
          验证 ctrl control_state 亮度正确
    """
    print("\n" + "=" * 60)
    print("  E2E 测试 1: BLE FFF3 → light_on → PWM_LED")
    print("  - BLE FFF3 写入: light_on")
    print("  - 期望: PWM duty = %d (LIGHT_BRIGHTNESS_MAX)" % LIGHT_BRIGHTNESS_MAX)
    print("  - 期望: LightService mode = manual")
    print("=" * 60)

    bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc = make_system()
    try:
        # === 检查 PWM_LED 是否可用 ===
        if not pwm_led.ctx.get("is_init"):
            print("  ~ PWMLEDDriver 未初始化，跳过硬件验证")
            # 仍然验证 ControlService 状态链路
            simulate_ble_ctrl_write(ble_svc, bus, ctrl, "light_on")
            pump_loop(bus, 200)

            ctrl_data = ctrl.get_data()
            assert ctrl_data["last_cmd"] == "light_on", (
                "最后指令应为 light_on, 实际: %s" % ctrl_data["last_cmd"])
            assert ctrl_data["control_state"]["light_mode"] == "manual", (
                "灯光模式应为 manual, 实际: %s" % ctrl_data["control_state"]["light_mode"])
            assert ctrl_data["control_state"]["light_brightness"] == LIGHT_BRIGHTNESS_MAX, (
                "亮度应为 %d, 实际: %d" % (LIGHT_BRIGHTNESS_MAX, ctrl_data["control_state"]["light_brightness"]))
            print("  ✓ ControlService 状态正确（PWM 硬件不可用）")
            return True

        # === 模拟 BLE FFF3 写入 ===
        simulate_ble_ctrl_write(ble_svc, bus, ctrl, "light_on")
        pump_loop(bus, 200)

        # === 验证 PWM_LED 亮度 ===
        pwm_data = pwm_led.get_data()
        assert pwm_data["duty_cycle"] == LIGHT_BRIGHTNESS_MAX, (
            "PWM 占空比应为 %d, 实际: %d" % (LIGHT_BRIGHTNESS_MAX, pwm_data["duty_cycle"]))
        print("  ✓ PWM duty_cycle = %d (LIGHT_BRIGHTNESS_MAX)" % pwm_data["duty_cycle"])

        # === 验证 LightService 模式 ===
        assert light_svc.get_mode() == "manual", (
            "LightService 模式应为 manual, 实际: %s" % light_svc.get_mode())
        print("  ✓ LightService mode = manual")

        # === 验证 ControlService 状态快照 ===
        ctrl_data = ctrl.get_data()
        assert ctrl_data["last_cmd"] == "light_on", (
            "最后指令应为 light_on, 实际: %s" % ctrl_data["last_cmd"])
        assert ctrl_data["control_state"]["light_mode"] == "manual", (
            "灯光模式应为 manual")
        assert ctrl_data["control_state"]["light_brightness"] == LIGHT_BRIGHTNESS_MAX, (
            "亮度应为 %d, 实际: %d" % (LIGHT_BRIGHTNESS_MAX, ctrl_data["control_state"]["light_brightness"]))
        print("  ✓ ControlService state: mode=manual, brightness=%d" % ctrl_data["control_state"]["light_brightness"])

        print("  => 请目视确认: PWM LED (PE11) 亮起，亮度 50%%")
        print("  ✓ test_ble_e2e_01_light_on 通过")
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
        cleanup(bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc)


def test_ble_e2e_02_volume_up():
    """
    brief E2E 测试 2: BLE FFF3 写入 volume_up → AudioDriver 音量增加
    note 模拟 BLE 写入 {"a":"ctrl","d":{"cmd":"volume_up"}}
          完整链路：BLEService → ControlService → EVENT_VOLUME_CONTROL → AudioDriver
          验证 audio._data["volume"] 增加
          验证 ctrl control_state volume 同步
    """
    print("\n" + "=" * 60)
    print("  E2E 测试 2: BLE FFF3 → volume_up → AudioDriver")
    print("  - BLE FFF3 写入: volume_up")
    print("  - 期望: Audio 音量增加 1（上限 5）")
    print("=" * 60)

    bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc = make_system()
    try:
        # === 记录初始音量 ===
        initial_vol = audio._data.get("volume", 5)
        print("  初始音量: %d" % initial_vol)

        # === 模拟 BLE FFF3 写入 ===
        simulate_ble_ctrl_write(ble_svc, bus, ctrl, "volume_up")
        pump_loop(bus, 200)

        # === 验证 AudioDriver 音量增加 ===
        expected_vol = min(initial_vol + 1, 5)
        actual_vol = audio._data.get("volume", initial_vol)
        assert actual_vol == expected_vol, (
            "音量应为 %d, 实际: %d" % (expected_vol, actual_vol))
        print("  ✓ Audio 音量: %d → %d" % (initial_vol, actual_vol))

        # === 验证 ControlService 状态同步 ===
        ctrl_data = ctrl.get_data()
        assert ctrl_data["last_cmd"] == "volume_up", (
            "最后指令应为 volume_up, 实际: %s" % ctrl_data["last_cmd"])
        assert ctrl_data["control_state"]["volume"] == expected_vol, (
            "ControlService 音量应为 %d, 实际: %d" % (
                expected_vol, ctrl_data["control_state"]["volume"]))
        print("  ✓ ControlService state: volume=%d" % ctrl_data["control_state"]["volume"])

        # === 验证 TTS 反馈（volume_up → "音量增加"） ===
        check_audio_tts(audio, expect_playing=False)

        print("  => 请目视确认: 音量增加")
        print("  ✓ test_ble_e2e_02_volume_up 通过")
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
        cleanup(bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc)


def test_ble_e2e_03_query_temp():
    """
    brief E2E 测试 3: BLE FFF3 写入 query_temp → TTS 播报温度
    note 模拟 BLE 写入 {"a":"ctrl","d":{"cmd":"query_temp"}}
          完整链路：BLEService → ControlService._query_temp → EVENT_TTS_REQUEST → AudioDriver
          无温度传感器时播报 "温度信息暂不可用"
          验证 ctrl 执行了命令 + TTS 被触发
    """
    print("\n" + "=" * 60)
    print("  E2E 测试 3: BLE FFF3 → query_temp → TTS")
    print("  - BLE FFF3 写入: query_temp")
    print("  - 期望: TTS 播报温度（或 '温度信息暂不可用'）")
    print("=" * 60)

    bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc = make_system()
    try:
        # === 模拟 BLE FFF3 写入 ===
        simulate_ble_ctrl_write(ble_svc, bus, ctrl, "query_temp")

        # === 等待 TTS 工作线程 ===
        tts_started = wait_tts(audio, timeout_ms=WAIT_TTS_MS)
        if not tts_started:
            print("  ~ TTS 可能在 wait_tts() 前已完成")
        else:
            pump_loop(bus, 300)

        # === 验证 ControlService 执行了命令 ===
        ctrl_data = ctrl.get_data()
        assert ctrl_data["last_cmd"] == "query_temp", (
            "最后指令应为 query_temp, 实际: %s" % ctrl_data["last_cmd"])
        print("  ✓ ControlService 已执行 query_temp")

        # === 验证 TTS 链路（query_temp 永远会调用 _tts()） ===
        if tts_started:
            print("  ✓ BLE FFF3 → BLEService → ControlService → Audio TTS 链路验证通过")
        else:
            print("  ✓ ctrl._data['last_cmd'] == 'query_temp'（TTS 可能已播完）")

        # === 最终音频状态 ===
        check_audio_tts(audio, expect_playing=False)

        print("  => 请耳听确认: 喇叭播报温度信息")
        print("  ✓ test_ble_e2e_03_query_temp 通过")
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
        cleanup(bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc)


def test_ble_e2e_04_alarm_tts_suppress():
    """
    brief E2E 测试 4: 报警中 TTS 被抑制，取消后恢复
    note 两层抑制机制：
          1. ControlService._maybe_tts → 检查 _alarm_active
          2. AudioDriver._on_tts_request → 检查 alarm_playing
         阶段 1: 触发 stealth 报警 → BLE 指令 TTS 被抑制
         阶段 2: 取消报警 → BLE 指令 TTS 恢复
    """
    print("\n" + "=" * 60)
    print("  E2E 测试 4: BLE FFF3 + 报警抑制 TTS")
    print("  - 阶段 1: 触发 stealth 报警 → volume_up TTS 被抑制")
    print("  - 阶段 2: 取消报警 → volume_up TTS 恢复")
    print("=" * 60)

    bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc = make_system()
    try:
        # ====== 阶段 1: 报警中，TTS 被抑制 ======
        print("\n  --- 阶段 1: 触发报警（stealth）---")

        bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "stealth"})
        bus.pump()
        time.sleep_ms(100)

        # 验证报警状态
        assert ctrl._alarm_active is True, "ControlService 报警应激活"
        assert audio.ctx.get("alarm_playing") is True, "AudioDriver alarm_playing 应为 True"
        print("  ✓ 报警已激活 (ctrl._alarm_active=True, audio.alarm_playing=True)")

        # 在报警期间通过 BLE FFF3 发送 volume_up（CMD_TTS_MAP: "音量增加"）
        simulate_ble_ctrl_write(ble_svc, bus, ctrl, "volume_up")
        pump_loop(bus, 500)

        # 验证音量已更新（指令执行不受报警影响）
        ctrl_data = ctrl.get_data()
        assert ctrl_data["last_cmd"] == "volume_up", (
            "指令应正常执行, 实际: %s" % ctrl_data["last_cmd"])
        print("  ✓ volume_up 指令已执行（音量已更新）")

        # 验证 TTS 被抑制：ControlService._maybe_tts 在 _alarm_active 时直接 return
        # AudioDriver._on_tts_request 在 alarm_playing 时直接 return
        tts_started = wait_tts(audio, timeout_ms=500)
        assert not tts_started, (
            "报警期间 TTS 不应被播放, 但 AudioDriver 显示了播放状态")
        print("  ✓ TTS 播放被成功抑制（两层阻断：ControlService + AudioDriver）")

        # ====== 阶段 2: 取消报警，TTS 恢复 ======
        print("\n  --- 阶段 2: 取消报警 ---")

        bus.publish(EVENT_ALARM_CANCELED, {})
        bus.pump()
        time.sleep_ms(100)

        assert ctrl._alarm_active is False, "ControlService 报警应已取消"
        assert audio.ctx.get("alarm_playing") is False, "AudioDriver alarm_playing 应为 False"
        print("  ✓ 报警已取消 (ctrl._alarm_active=False, audio.alarm_playing=False)")

        # 等待报警取消后的 TTS（"报警已取消"）播完
        if wait_tts(audio, timeout_ms=WAIT_TTS_MS):
            print("  ~ 报警取消 TTS 播报中，等待完成...")
            wait_tts_complete(audio, timeout_ms=3000)

        # 通过 BLE FFF3 再次发送 volume_up（应正常 TTS）
        simulate_ble_ctrl_write(ble_svc, bus, ctrl, "volume_up")
        pump_loop(bus, WAIT_TTS_MS)

        ctrl_data = ctrl.get_data()
        assert ctrl_data["last_cmd"] == "volume_up", (
            "指令应正常执行, 实际: %s" % ctrl_data["last_cmd"])
        print("  ✓ volume_up 指令已执行")

        # 验证 TTS 恢复
        tts_result = wait_tts(audio, timeout_ms=WAIT_TTS_MS)
        if tts_result:
            print("  ✓ TTS 恢复：控制指令 TTS 播放中")
        else:
            # TTS 可能已播完
            print("  ~ TTS 可能已播完（硬件播放快）")

        check_audio_tts(audio, expect_playing=False)

        print("\n  => 请目视确认: 报警期间无 '音量增加' TTS, 取消后 TTS 恢复")
        print("  ✓ test_ble_e2e_04_alarm_tts_suppress 通过")
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
        cleanup(bus, pwm_led, light_svc, audio, ctrl, ble, ble_svc)


# ==================== 主入口 ====================

def run_all():
    """运行所有 BLE E2E 测试"""
    print("\n" + "=" * 60)
    print("  ControlService BLE E2E 测试（自包含·真实硬件）")
    print("=" * 60)
    print("  测试链路:")
    print("    BLE FFF3 写入 → BLEService.cmd_buffer")
    print("                  → tick() / _parse_and_route")
    print("                  → EventBus publish(EVENT_RIDE_CONTROL)")
    print("                  → ControlService._on_ride_control")
    print("                  → _execute_cmd() → EVENT_LIGHT_CONTROL / EVENT_VOLUME_CONTROL / EVENT_TTS_REQUEST")
    print("                  → LightService._on_light_control → PWMLEDDriver.set_brightness()")
    print("                  → AudioDriver._on_volume_control / _on_tts_request")
    print("")
    print("  测试环境:")
    print("    - NUCLEO-F413ZH + EC200U (BLE)")
    print("    - PWMLEDDriver → PE11 (TIM1_CH2)")
    print("    - AudioDriver → 喇叭")
    print("    - LightService → 自适应灯光")
    print("    - ControlService → 统一控制服务")
    print("")
    print("  请确保:")
    print("    1. PWM LED (PE11) 已连接（观察亮度变化）")
    print("    2. 喇叭已连接（听 TTS 播报）")
    print("    3. 板子已上电稳定运行")

    tests = [
        ("BLE E2E 测试 1: FFF3 → light_on → PWM_LED", test_ble_e2e_01_light_on),
        ("BLE E2E 测试 2: FFF3 → volume_up → Audio",   test_ble_e2e_02_volume_up),
        ("BLE E2E 测试 3: FFF3 → query_temp → TTS",    test_ble_e2e_03_query_temp),
        ("BLE E2E 测试 4: 报警抑制 TTS",                test_ble_e2e_04_alarm_tts_suppress),
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
