"""
brief 语音控制 × PWM 闪烁 × BLE 端到端真机测试
note 使用真硬件：ASRPRO 语音模块、PWM LED（大灯）、BLE（手机小程序）
      每个场景前都有提示告诉你该观察什么
      测试 1-4: 语音闪烁 / 取消 / 休眠 / 唤醒
      测试 5-6: 语音蓝牙断开 / 重连
      测试 7-8: SOS 报警联动 PWM 闪烁 / 取消
      测试 9:  闪烁状态 BLE 推送 f 字段
      测试 10: 闪烁中调亮/调暗
执行: 上传到板子运行 python test_voice_blink_e2e.py
tags: E2E, 真机测试, 交互式
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_VOICE_CMD, EVENT_CONTROL_STATE_CHANGED,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    VOICE_CMD_MAP, CMD_TTS_MAP,
)
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.interface.Voice import VoiceDriver
from Drivers.network.BLE import BLEDriver
from Modules.light_service import LightService
from Modules.alarm_service import AlarmService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService
from Modules.audio_service import AudioService


# ==================== 全局状态 ====================
state_pushes = []
voice_cmds = []
alarm_events = []


def on_control_state(payload):
    state_pushes.append(payload)
    print("  [STATE PUSH] %s" % payload)


def on_voice_cmd(payload):
    voice_cmds.append(payload)
    print("  [VOICE CMD] %s" % payload)


def on_alarm(payload):
    alarm_events.append(payload)
    print("  [ALARM] %s" % payload)


def pump_loop(event_bus, times, delay_ms=10):
    for _ in range(times):
        event_bus.pump()
        time.sleep_ms(delay_ms)


def prompt_and_watch(msg, duration_s, event_bus, modules):
    print("\n  >>> %s (观察 %d 秒)" % (msg, duration_s))
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()
        time.sleep_ms(100)
    elapsed = time.ticks_diff(time.ticks_ms(), start) // 1000
    print("  ... %ds 完成" % elapsed)


def print_all_states(ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice):
    """打印所有相关模块状态"""
    print("  --- 模块状态快照 ---")
    print("  Voice: init={}, last_cmd={}, last_hex=0x{:02X}".format(
        voice.ctx["is_init"],
        voice._data["last_cmd"],
        voice._data["last_hex"]))
    print("  ControlService: init={}, err={}, state={}".format(
        ctrl.ctx["is_init"], ctrl.ctx["err_count"], ctrl._control_state))
    print("  LightService: init={}, auto_mode={}, blink={}, brightness={}".format(
        light_svc.ctx.get("is_init", False),
        light_svc.ctx.get("auto_mode", False),
        light_svc._data.get("blink_active", False),
        light_svc._data["current_brightness"]))
    print("  PWM_LED: init={}, duty={}, blink={}".format(
        pwm_led.ctx["is_init"],
        pwm_led._data["duty_cycle"],
        pwm_led._data.get("blink_active", False)))
    print("  AudioService: init={}".format(audio_svc.ctx.get("is_init", False)))
    print("  BLE: connected={}, queue_size={}".format(
        ble_svc.ctx.get("ble_connected", False),
        ble_svc.send_queue.size() if ble_svc.send_queue else 0))
    print("  状态回推次数: %d" % len(state_pushes))
    print("  语音指令次数: %d" % len(voice_cmds))
    print("  报警事件次数: %d" % len(alarm_events))


# ==================== 测试结果 ====================
test_results = []


def run_test(num, name, desc, event_bus, init_order, modules,
             ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
             watch_s=10):
    """执行一个 E2E 测试步骤"""
    print("\n" + "=" * 60)
    print("[测试 %d] %s" % (num, name))
    print("=" * 60)
    print(desc)
    print("-" * 40)
    input("  按 Enter 开始测试...")

    snap_before = len(state_pushes)
    voice_before = len(voice_cmds)

    prompt_and_watch("等待操作并观察", watch_s, event_bus, init_order)

    print("\n  新增状态回推: %d" % (len(state_pushes) - snap_before))
    print("  新增语音指令: %d" % (len(voice_cmds) - voice_before))
    print_all_states(ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice)

    result = input("\n  结果是否符合预期? (y/n): ").strip().lower()
    if result == "y":
        test_results.append((num, name, "PASS"))
        print("  PASS")
    else:
        test_results.append((num, name, "FAIL"))
        print("  FAIL")
    return result == "y"


# ==================== 主函数 ====================

def main():
    print("=" * 60)
    print(" 语音控制 x PWM 闪烁 x BLE E2E 真机测试")
    print("=" * 60)
    print("")
    print("测试环境要求:")
    print("  - NUCLEO-F413ZH + EC200U")
    print("  - ASRPRO 语音模块已安装并烧录 0x00-0x19")
    print("  - PWM LED（大灯）已连接到 PE11")
    print("  - 手机 BLE 连接（小程序已打开）")
    print("")
    print("请确认以上硬件就绪后按 Enter 开始初始化...")
    input()

    # ---- 创建事件总线 ----
    event_bus = EventBus()

    # ---- 创建 Device 层 ----
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    audio_svc = AudioService(event_bus, audio_driver=audio)
    pwm_led = PWMLEDDriver(event_bus)
    light_sensor = LightSensorDriver(event_bus)
    voice = VoiceDriver(event_bus)
    ble_driver = BLEDriver(event_bus)

    # ---- 创建 Service 层 ----
    light_svc = LightService(event_bus, pwm_led=pwm_led)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    ble_svc = BLEService(event_bus, ble_driver=ble_driver)
    ctrl = ControlService(event_bus)

    # ---- 初始化 ----
    init_order = [led, audio, audio_svc, pwm_led, light_sensor, voice, ble_driver,
                  light_svc, alarm, ble_svc, ctrl]
    print("\n[初始化阶段]")
    for mod in init_order:
        try:
            mod.init()
            print("  OK %s | is_init=%s" % (mod.name, mod.ctx.get("is_init", False)))
        except Exception as e:
            print("  FAIL %s: %s" % (mod.name, e))

    # ---- 订阅事件日志 ----
    event_bus.subscribe(EVENT_CONTROL_STATE_CHANGED, on_control_state)
    event_bus.subscribe(EVENT_VOICE_CMD, on_voice_cmd)
    event_bus.subscribe(EVENT_ALARM_TRIGGERED, on_alarm)
    event_bus.subscribe(EVENT_ALARM_CANCELED, on_alarm)

    # ---- 等待 BLE 连接 ----
    print("\n[等待 BLE 连接]")
    print("  BLE 广播名: SmartHelmet-66ccff")
    print("  请用手机小程序或 NRF Connect 连接...")
    print("  (如已连接可跳过，按 Enter 继续)")
    input("  按 Enter 跳过等待...")

    print("\n[初始化后状态]")
    print_all_states(ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice)

    # ==================== 测试场景 ====================

    run_test(1, "语音闪烁 -> PWM LED 闪烁", """操作:
  1. 对 ASRPRO 说: "闪烁"（hex 0x19）
预期结果:
  - TTS 播报: "灯光闪烁"
  - PWM LED 在 0%% 和 20%% 之间闪烁（间隔 500ms）
  - PWM LED 亮度较低（保护大功率 LED）
验证:
  - 肉眼观察 PWM LED 是否闪烁
  - 终端查看 Voice 日志 last_cmd=light_blink""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=15)

    run_test(2, "再次闪烁 -> 停止闪烁", """操作:
  1. 对 ASRPRO 说: "闪烁"（此时在闪烁中）
  2. 等待 2 秒确认闪烁状态
  3. 再次对 ASRPRO 说: "闪烁"
预期结果:
  - TTS 播报: "灯光闪烁"
  - PWM LED 停止闪烁
  - LED 熄灭
验证:
  - 肉眼观察 PWM LED 是否停止""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=15)

    run_test(3, "语音休眠 -> 指令被忽略", """操作:
  1. 对 ASRPRO 说: "休眠"（hex 0x18）
预期结果:
  - TTS 播报: "好的"
  - 后续语音指令被忽略（除"小洛包"外）
验证:
  2. 对 ASRPRO 说: "开灯" -- 应无反应，无 TTS
  3. 对 ASRPRO 说: "查询温度" -- 应无反应，无 TTS
  （如果上述指令仍有响应，则测试失败）""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=20)

    run_test(4, "小洛包 -> 唤醒恢复", """操作:
  1. 对 ASRPRO 说: "小洛包"（hex 0x00）
预期结果:
  - TTS 播报: "小洛包在，有什么指示"
  - 语音系统恢复接收指令
验证:
  2. 对 ASRPRO 说: "开灯"（hex 0x01）
  - TTS 播报: "灯光已开启"
  - PWM LED 亮起""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=15)

    run_test(5, "蓝牙断开 -> BLE 断开", """操作:
  1. 确保手机已通过 BLE 连接头盔
  2. 对 ASRPRO 说: "蓝牙断开"（hex 0x17）
预期结果:
  - TTS 播报: "蓝牙已断开"
  - 小程序显示 BLE 断开
  - 小程序不再接收传感器数据
验证:
  - 查看小程序连接状态""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=10)

    run_test(6, "蓝牙连接 -> BLE 重连", """操作:
  1. 在测试 5 之后（BLE 已断开）
  2. 对 ASRPRO 说: "蓝牙连接"（hex 0x16）
预期结果:
  - TTS 播报: "蓝牙正在连接"（注: CMD_TTS_MAP 无此 key，看实际播报）
  - BLE 重新广播
  - 小程序可重新搜索并连接头盔
验证:
  - 用手机扫描 BLE 设备，应看到 "SmartHelmet-66ccff"
  - 重新连接后观察 BLE 数据恢复""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=15)

    run_test(7, "SOS 报警 -> PWM 自动闪烁", """操作:
  1. 按 SW 按钮触发 SOS 报警（空闲状态按一次）
  2. 或通过小程序发送 SOS 指令
预期结果:
  - SOS 报警音播放
  - PWM LED 自动闪烁（20%% 占空比）
  - 报警闪烁不可被语音中断
验证:
  3. 在闪烁中对 ASRPRO 说: "关灯" -- PWM LED 应继续闪烁（报警优先级最高）
  - 小 LED（蓝色指示灯）同时闪烁""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=15)

    run_test(8, "报警取消 -> PWM 停止", """操作:
  1. 在测试 7 之后（SOS 报警中）
  2. 再次按 SW 按钮取消报警
  3. 或语音说 "取消报警"（hex 0x08）
预期结果:
  - 报警音停止
  - PWM LED 停止闪烁
  - 小 LED 熄灭
  - TTS "报警已取消"
验证:
  - 肉眼观察 PWM LED 是否熄灭""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=10)

    run_test(9, "闪烁状态 -> BLE 推送 f=1", """操作:
  1. 手机通过 BLE 连接头盔
  2. 打开小程序调试日志 / BLE 数据窗口
  3. 对 ASRPRO 说: "闪烁"
预期结果:
  - BLE 推送数据中包含 "f":1 字段
  - 格式: {"t":7,"m":...,"b":...,"v":...,"p":...,"f":1}
验证:
  - 查看 BLE 调试日志确认 f 字段
  - 停止闪烁后 f 字段应变为 0 或消失""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=15)

    run_test(10, "闪烁中调亮/调暗", """操作:
  1. 对 ASRPRO 说: "闪烁"（PWM LED 在 20%% 闪烁）
  2. 对 ASRPRO 说: "调亮"（hex 0x03）
预期结果:
  - PWM LED 闪烁亮度从 20%% -> 25%%
  3. 对 ASRPRO 说: "调暗"（hex 0x04）
预期结果:
  - PWM LED 闪烁亮度从 25%% -> 20%%
验证:
  - 肉眼观察闪烁亮度变化
  - 终端查看 PWM_LED duty 值""",
        event_bus, init_order, init_order,
        ctrl, light_svc, pwm_led, audio_svc, ble_svc, voice,
        watch_s=20)

    # ==================== 总结报告 ====================
    print("\n" + "=" * 60)
    print(" E2E 测试总结报告")
    print("=" * 60)
    passed = 0
    failed = 0
    for num, name, result in test_results:
        mark = "PASS" if result == "PASS" else "FAIL"
        icon = "+" if result == "PASS" else "-"
        print("  [%s] 测试 %d: %s" % (icon, num, name))
        if result == "PASS":
            passed += 1
        else:
            failed += 1
    print("-" * 60)
    print("  总计: %d 测试" % len(test_results))
    print("  通过: %d" % passed)
    print("  失败: %d" % failed)
    if failed == 0:
        print("  结果: ALL PASS")
    else:
        print("  结果: FAIL (%d/%d)" % (failed, len(test_results)))
    print("=" * 60)


if __name__ == "__main__":
    main()
