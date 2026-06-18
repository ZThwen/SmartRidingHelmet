"""
brief 静默报警 E2E 测试
note 专注验证小程序「静默」模式 → BLE FFF3 alarm_stealth → 板子接收全链路
     ！！！
     核心验证点：小程序日志必须有:
       [CTRL] onAlarmSos ENTER
       [CTRL] CtrlService.alarmStealth() calling...
       [BLE] sendCtrl -> FFF3: {"a":"ctrl","d":{"cmd":"alarm_stealth"}}
     缺任何一行 = 链路断裂
     ！！！

执行: 上传到板子运行 python Tests/miniprogram/step_b/05_alarm/test_alarm_stealth_e2e.py
小程序: 打开「远端控制」页，连接 BLE
"""
import sys
sys.path.append("../../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import (
    EVENT_RIDE_CONTROL,
)
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService


_LOG_PATH = "Tests/miniprogram/step_b/05_alarm/test_alarm_stealth_e2e.log"
_T0 = 0
_cmd_log = []


def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    line = "[%7.2fs] %s" % (elapsed / 1000.0, msg)
    print(line)
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def on_ride_control(payload):
    """拦截小程序发来的所有 BLE 控制指令"""
    raw = payload.get("raw", "")
    try:
        obj = json.loads(raw)
        if obj.get("a") == "ctrl":
            cmd = obj.get("d", {}).get("cmd", "")
            _cmd_log.append(cmd)
            log("  [BLE RX] FFF3 收到 cmd=%s" % cmd)
    except Exception:
        pass


def pump_for(bus, ble_svc, duration_ms):
    end = time.ticks_ms() + duration_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 55)
    print(" 静默报警 E2E 测试")
    print("=" * 55)
    print("")
    print(" 测试前确认：")
    print("  1. 微信开发者工具打开小程序「远端控制」页")
    print("  2. 已连接 BLE（SmartHelmet-66ccff）")
    print("  3. 看板子串口输出 + 小程序调试台日志")
    print("")
    print(" 操作步骤：")
    print("  ① 在小程序点「静默」按钮 → 高亮")
    print("  ② 在小程序点「SOS 报警」按钮")
    print("  ③ 在弹出的确认框点「发送静默」")
    print("  ④ 观察板子是否收到 alarm_stealth")
    print("")

    bus = EventBus()

    log("初始化 BLE...")
    ble_driver = BLEDriver(bus)
    ble_driver.init()
    ble_svc = BLEService(bus, ble_driver=ble_driver)
    ble_svc.init()
    bus.subscribe(EVENT_RIDE_CONTROL, on_ride_control)

    # 等待 BLE 连接
    log("请在微信开发者工具中连接 BLE，连接后按 Enter")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return

    log("等待 BLE 连接确认...")
    end = time.ticks_ms() + 15000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            log("✓ BLE 已连接")
            break
        time.sleep_ms(100)
    else:
        log("✗ 未检测到 BLE 连接")
        return

    # 排空初始数据
    pump_for(bus, ble_svc, 2000)
    _cmd_log.clear()

    # ==================== 测试会话 ====================
    log("")
    log("=" * 55)
    log(" 请按上述步骤操作小程序：")
    log("  ① 点「静默」→ 高亮")
    log("  ② 点「SOS 报警」→ 弹确认框")
    log("  ③ 点「发送静默」")
    log("=" * 55)
    log("")
    log("操作完成后按 Enter，板子会排空并打印收到的指令")
    log("（如无操作会超时等待 60 秒）")

    try:
        # 独立线程等用户输入 + 同时 pump BLE
        end = time.ticks_ms() + 60000
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            ble_svc.tick()
            bus.pump()
            # 检查是否收到 stealth 指令（提前退出）
            if "alarm_stealth" in _cmd_log:
                break
            time.sleep_ms(100)
    except KeyboardInterrupt:
        pass

    # 排空积压
    pump_for(bus, ble_svc, 3000)

    # ==================== 结果判定 ====================
    log("")
    log("=" * 55)
    log(" 结果")
    log("=" * 55)

    received_stealth = "alarm_stealth" in _cmd_log
    received_sos = "alarm_sos" in _cmd_log

    if _cmd_log:
        log(" 板子收到指令: %s" % ", ".join(_cmd_log))
    else:
        log(" 板子未收到任何指令")

    log("")
    log(" 判定：")
    if received_stealth:
        log(" ✅ 静默报警指令已正确送达板子")
        log(" ✅ 全链路通过")
    elif received_sos:
        log(" ❌ 板子收到的是 alarm_sos 而非 alarm_stealth")
        log("    小程序日志检查点：")
        log("    - [CTRL] alarmSos showModal mode=stealth  ✓/✗")
        log("    - [CTRL] CtrlService.alarmStealth() calling...  ✓/✗")
        log("   原因：onAlarmSos 中的 isStealth 判断未生效")
    else:
        log(" ❌ 板子未收到任何 BLE 指令")
        log("    小程序日志检查点：")
        log("    - [CTRL] onAlarmSos ENTER  ✓/✗")
        log("    - [BLE] sendCtrl -> FFF3: ...alarm_stealth...  ✓/✗")
        log("    - [CTRL] alarmSos blocked: no BLE  ✓/✗")
        log("")
        log("   常见原因：")
        log("   1. BLE 已断开 → 看有没有 'no BLE' toast")
        log("   2. JS 报错 → 看小程序调试台 console 有无红字")
        log("   3. 未点到确认框 → 看 [CTRL] alarmSos confirmed 日志")

    log("")
    log("=" * 55)
    if received_stealth:
        log(" ✅ 全部通过")
    else:
        log(" ❌ 测试未通过")
    log("=" * 55)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
