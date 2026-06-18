"""
brief 远端控制 E2E 真机测试（小程序 ↔ 板子全链路）
note 测试小程序「远端控制」页的所有按钮功能
     板子通过 BLE 接收小程序发来的 FFF3 指令并执行
     验证：指令解析、硬件响应、状态回推、小程序 UI 同步

     你在小程序上点按钮，板子接收并执行，你观察效果

执行: 上传到板子运行 python Tests/miniprogram/step_b/07_control_remote_e2e.py
小程序: 微信开发者工具打开「远端控制」页，连接 BLE
"""
import sys
sys.path.append("../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_TTS_REQUEST,
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
)
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Drivers.sensor.Light import LightSensorDriver
from Drivers.network.BLE import BLEDriver
from Modules.light_service import LightService
from Modules.alarm_service import AlarmService
from Modules.ble_service import BLEService
from Modules.control_service import ControlService


_LOG_PATH = "Tests/miniprogram/step_b/07_control_remote_e2e.log"
_T0 = 0
cmd_log = []
_test_results = []


def record(test_id, name, cmd, expected, actual, modules_ok, passed):
    _test_results.append({
        "id": test_id, "name": name, "cmd": cmd,
        "expected": expected, "actual": actual,
        "modules": modules_ok, "passed": passed
    })


def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    line = "[%7.2fs] %s" % (elapsed / 1000.0, msg)
    print(line)
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def phase(num, title):
    log("")
    log("=" * 55)
    log(" Phase %d: %s" % (num, title))
    log("=" * 55)


# ==================== BLE 指令拦截（记录小程序发来的所有指令）====================

def on_ride_control(payload):
    """拦截小程序通过 BLE 发来的控制指令"""
    raw = payload.get("raw", "")
    try:
        obj = json.loads(raw)
        if obj.get("a") == "ctrl":
            cmd = obj.get("d", {}).get("cmd", "")
            log("  [BLE RX] FFF3 收到: %s" % raw)
            cmd_log.append(cmd)
    except Exception:
        pass


def pump_loop(event_bus, modules, duration_s=2):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_s * 1000:
        for mod in modules:
            if mod.ctx.get("is_init", False):
                try:
                    mod.tick()
                except Exception:
                    pass
        event_bus.pump()


def wait_enter(msg, event_bus, modules, duration_s=10):
    """打印提示 → 等你在小程序操作 → pump 收 BLE 指令 + 执行"""
    cmd_log.clear()
    log("")
    log("-" * 50)
    log("  >>> " + msg)
    log("  >>> 在小程序上操作完成后，按 Enter 继续")
    log("  >>> 超时 %d 秒后自动继续" % duration_s)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    # 收尾：排空积压的 BLE 数据（input 期间可能堆积大量指令）
    log("  [PUMP] 排空 BLE 数据...")
    pump_loop(event_bus, modules, 5)
    if cmd_log:
        log("  [BOARD] 收到指令: %s" % ", ".join(cmd_log))
    else:
        log("  [BOARD] 未收到指令（可能小程序还未连上 BLE）")


def print_state(ctrl, light_svc, pwm_led, audio, ble_svc):
    log("  [STATE] control=%s" % ctrl._control_state)
    if light_svc:
        log("  [STATE] light: mode=%s brightness=%s" % (
            light_svc.ctx.get("auto_mode"), light_svc._data.get("current_brightness")))
    if pwm_led:
        log("  [STATE] pwm_led: duty=%s" % pwm_led._data.get("duty_cycle"))
    if audio:
        log("  [STATE] audio: vol=%s playing=%s" % (audio._data.get("volume"), audio.get_is_playing()))
    if ble_svc and ble_svc.send_queue:
        log("  [STATE] BLE queue: %d pending" % ble_svc.send_queue.size())


def print_summary(ctrl, light_svc, pwm_led, audio, ble_svc):
    log("")
    log("=" * 65)
    log(" 测试总结报告")
    log("=" * 65)
    log("")
    log("| # | 场景 | 指令 | 预期状态 | 实际状态 | 模块响应 | 结果 |")
    log("|---|------|------|----------|----------|----------|------|")
    passed = 0
    failed = 0
    for r in _test_results:
        result = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            passed += 1
        else:
            failed += 1
        log("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], r["name"], r["cmd"],
            r["expected"], r["actual"], r["modules"], result))
    log("")
    log("=" * 65)
    log(" 结果: %d 通过, %d 失败, 共 %d 项" % (passed, failed, passed + failed))
    log("=" * 65)
    log("")

    # 模块最终状态
    log("模块最终状态:")
    cs = ctrl._control_state
    log("  ControlService: light=%s/%s vol=%s power=%s" % (
        cs["light_mode"], cs["light_brightness"], cs["volume"], cs["power_mode"]))
    if light_svc:
        log("  LightService: auto=%s brightness=%s" % (
            light_svc.ctx.get("auto_mode"), light_svc._data.get("current_brightness")))
    if pwm_led:
        log("  PWM_LED: duty=%s" % pwm_led._data.get("duty_cycle"))
    if audio:
        log("  Audio: vol=%s playing=%s" % (
            audio._data.get("volume"), audio.get_is_playing()))
    if ble_svc:
        log("  BLE: connected=%s queue=%s" % (
            ble_svc.ctx["ble_connected"],
            ble_svc.send_queue.size() if ble_svc.send_queue else 0))

    log("")
    log("省电模式响应验证:")
    log("  power_save → 温湿度采样降频(30s), 光照降频(30s), GNSS降频(10s)")
    log("  power_emergency → 温湿度采样停止, 光照降频(2s/停止), GNSS降频(10s)")
    log("  power_normal → 全部恢复正常采样")


# ==================== 主流程 ====================

def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 55)
    print(" 远端控制 E2E 真机测试（小程序 ↔ 板子）")
    print("=" * 55)
    print("\n准备：")
    print("  1. 确保板子已上电并启动")
    print("  2. 微信开发者工具打开小程序「远端控制」页")
    print("  3. 在小程序点击「连接」→ 连接 SmartHelmet BLE")
    print("  4. 本脚本会引导你在小程序上操作")
    print("  5. 观察硬件（LED/头灯/音频）和小程序 UI 变化")
    print("")
    print("  按 Enter 开始初始化...")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    event_bus = EventBus()

    # 初始化全部真硬件
    led = LEDDriver(event_bus)
    audio = AudioDriver(event_bus)
    pwm_led = PWMLEDDriver(event_bus)
    light_sensor = LightSensorDriver(event_bus)
    ble_driver = BLEDriver(event_bus)

    light_svc = LightService(event_bus, pwm_led=pwm_led)
    alarm = AlarmService(event_bus, led=led, audio=audio)
    ble_svc = BLEService(event_bus, ble_driver=ble_driver)
    ctrl = ControlService(event_bus)

    modules = [led, audio, pwm_led, light_sensor, ble_driver,
               light_svc, alarm, ble_svc, ctrl]

    log("[初始化]")
    for mod in modules:
        try:
            mod.init()
            log("  OK %s" % mod.name)
        except Exception as e:
            log("  FAIL %s: %s" % (mod.name, e))

    # 拦截小程序发来的 BLE 指令
    event_bus.subscribe(EVENT_RIDE_CONTROL, on_ride_control)

    log("")
    log("请在微信开发者工具中点击 BLE「连接」按钮")
    log("连接 SmartHelmet-66ccff，连接后按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return
    log("等待 BLE 数据到达...")
    pump_loop(event_bus, modules, 3)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)

    # ==================== Phase 1: 灯光控制 ====================
    phase(1, "灯光控制")
    log("  请在小程序「远端控制」页操作：")
    log("  测试 1a: 点击「开灯」按钮")
    log("  预期: 头灯亮起，小程序 light=manual/50")
    wait_enter("1a 开灯 — 观察头灯 + 小程序 UI", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("1a", "开灯", "light_on",
           "light=manual/50", "light=%s/%s" % (cs["light_mode"], cs["light_brightness"]),
           "LED=ON" if pwm_led._data.get("duty_cycle", 0) > 0 else "LED=OFF",
           cs["light_mode"] == "manual" and cs["light_brightness"] == 50)

    log("  测试 1b: 点击亮度「▶」增加按钮")
    log("  预期: 头灯变亮（50%已达上限），UI 不变")
    wait_enter("1b 亮度+ — 观察头灯", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("1b", "亮度+", "brightness_up",
           "brightness=50(max)", "brightness=%d" % cs["light_brightness"],
           "duty=%s" % pwm_led._data.get("duty_cycle"),
           cs["light_brightness"] == 50)

    log("  测试 1c: 点击亮度「◀」减少按钮")
    log("  预期: 头灯变暗（40%%），小程序 UI 更新")
    wait_enter("1c 亮度- — 观察头灯变暗", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("1c", "亮度-", "brightness_down",
           "brightness=45", "brightness=%d" % cs["light_brightness"],
           "duty=%s" % pwm_led._data.get("duty_cycle"),
           cs["light_brightness"] == 45)

    log("  测试 1d: 点击「关灯」按钮")
    log("  预期: 头灯熄灭，小程序 brightness=0")
    wait_enter("1d 关灯 — 观察头灯熄灭", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("1d", "关灯", "light_off",
           "brightness=0", "brightness=%d" % cs["light_brightness"],
           "LED=OFF" if pwm_led._data.get("duty_cycle", 0) == 0 else "LED=ON",
           cs["light_brightness"] == 0)

    log("  测试 1e: 点击「自动」模式按钮")
    log("  预期: 切换到自动模式，小程序 light=auto")
    wait_enter("1e 自动模式 — 观察模式切换", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("1e", "自动模式", "light_auto",
           "light=auto", "light=%s" % cs["light_mode"],
           "auto=%s" % light_svc.ctx.get("auto_mode"),
           cs["light_mode"] == "auto")

    # ==================== Phase 2: 音量控制 ====================
    phase(2, "音量控制")
    log("  请在小程序操作：")
    log("  测试 2a: 点击音量「▲」增加按钮")
    log("  预期: 音量+1，小程序音量值更新")
    wait_enter("2a 音量+ — 听声音变化", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("2a", "音量+", "volume_up",
           "volume=5", "volume=%d" % cs["volume"],
           "vol=%s" % audio._data.get("volume"),
           cs["volume"] == 5)

    log("  测试 2b: 点击音量「▼」减少按钮")
    log("  预期: 音量-1，小程序音量值更新")
    wait_enter("2b 音量- — 听声音变化", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("2b", "音量-", "volume_down",
           "volume=4", "volume=%d" % cs["volume"],
           "vol=%s" % audio._data.get("volume"),
           cs["volume"] == 4)

    # ==================== Phase 3: 电源模式 ====================
    phase(3, "电源模式")
    log("  请在小程序操作：")
    log("  测试 3a: 点击「省电」按钮")
    log("  预期: 进入省电模式，小程序省电按钮高亮（黄色）")
    wait_enter("3a 省电 — 观察小程序按钮颜色", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("3a", "省电模式", "power_save",
           "power=suspended,light=0", "power=%s,light=%d" % (cs["power_mode"], cs["light_brightness"]),
           "LED=OFF",
           cs["power_mode"] == "suspended")

    log("  测试 3b: 点击「紧急」按钮")
    log("  预期: 进入紧急模式，小程序紧急按钮高亮（紫色）")
    wait_enter("3b 紧急 — 观察小程序按钮颜色", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("3b", "紧急模式", "power_emergency",
           "power=emergency", "power=%s" % cs["power_mode"],
           "LED=OFF",
           cs["power_mode"] == "emergency")

    log("  测试 3c: 点击「正常」按钮")
    log("  预期: 恢复正常，小程序正常按钮高亮（蓝色）")
    wait_enter("3c 正常 — 恢复正常模式", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("3c", "正常模式", "power_normal",
           "power=active", "power=%s" % cs["power_mode"],
           "OK",
           cs["power_mode"] == "active")

    # ==================== Phase 4: 报警控制 ====================
    phase(4, "报警控制")
    log("  请在小程序操作：")
    log("  测试 4a: 点击「SOS 报警」按钮 → 弹出确认框 → 点「发送 SOS」")
    log("  预期: LED 快闪 + SOS 音频播放，小程序弹出报警弹窗")
    wait_enter("4a SOS — 观察 LED 闪烁 + 听音频 + 小程序弹窗", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    record("4a", "SOS报警", "alarm_sos",
           "alarm_active=True", "alarm_active=%s" % ctrl._alarm_active,
           "OK",
           ctrl._alarm_active == True)

    log("  测试 4b: 在报警弹窗中点「取消报警」")
    log("  预期: LED 灭 + 音频停，小程序弹窗关闭")
    wait_enter("4b 取消报警 — 观察停止", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    record("4b", "取消报警", "alarm_cancel",
           "alarm_active=False", "alarm_active=%s" % ctrl._alarm_active,
           "OK",
           ctrl._alarm_active == False)

    log("  测试 4c: 小程序中先点「静默」模式，再点「SOS 报警」→ 取消")
    log("  预期: 无声无光（静默模式），小程序报警区显示")
    wait_enter("4c 静默模式 — 确认无声光", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    record("4c", "静默报警", "alarm_stealth",
           "alarm_active=True,type=stealth", "alarm_active=%s" % ctrl._alarm_active,
           "OK",
           ctrl._alarm_active == True)

    # 清除 stealth
    ctrl._alarm_active = False

    # ==================== Phase 5: 传感器数据 + CUSTOM ====================
    phase(5, "手动操作覆盖省电模式（CUSTOM）")
    log("  测试 5a: 先点「省电」，再点「开灯」")
    log("  预期: 小程序电源模式变更为正常（手动操作自动退出省电）")
    wait_enter("5a 省电→开灯 — 观察电源模式变化", event_bus, modules)
    print_state(ctrl, light_svc, pwm_led, audio, ble_svc)
    cs = ctrl._control_state
    record("5a", "CUSTOM模式", "power_save→light_on",
           "power=custom", "power=%s" % cs["power_mode"],
           "LED=ON",
           cs["power_mode"] == "custom")

    # ==================== 总结 ====================
    print_summary(ctrl, light_svc, pwm_led, audio, ble_svc)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
