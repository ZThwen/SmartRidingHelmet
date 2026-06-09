"""
brief 报警推送测试
note 验证报警功能：
     碰撞报警弹窗
     SOS 报警弹窗
     报警取消
执行: 上传到板子运行
"""
import sys
sys.path.append("../../..")
import time

from core.Event_Bus import EventBus
from core.config import EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED
from Drivers.network.BLE import BLEDriver
from Drivers.actuator.LED import LEDDriver
from Drivers.actuator.Audio import AudioDriver
from Modules.ble_service import BLEService
from Modules.alarm_service import AlarmService


_LOG_PATH = "Tests/miniprogram/step_b/05_alarm/test_alarm_push.log"
_T0 = 0


def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    line = "[%7.2fs] %s" % (elapsed / 1000.0, msg)
    print(line)
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def countdown(sec, msg):
    log("⏱ 倒计时: %ds — %s" % (sec, msg))
    for i in range(sec, 0, -1):
        log("  %ds..." % i)
        time.sleep(1)


def wait_ble(bus, ble_svc, timeout_s=20):
    log("▶ 等待 BLE 连接...")
    end = time.ticks_ms() + timeout_s * 1000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            return True
        time.sleep_ms(100)
    return False


def pump_for(bus, ble_svc, duration_ms):
    end = time.ticks_ms() + duration_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 报警推送测试")
    print("=" * 50)

    bus = EventBus()

    log("初始化 LED + Audio...")
    try:
        led = LEDDriver(bus)
        led.init()
        audio = AudioDriver(bus)
        audio.init()
        log("✓ LED + Audio 就绪")
    except Exception as e:
        log("✗ LED/Audio 失败: %s" % e)
        return

    log("初始化 BLE...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log("✓ BLE 就绪")
    except Exception as e:
        log("✗ BLE 失败: %s" % e)
        return

    log("初始化 AlarmService...")
    try:
        alarm_svc = AlarmService(bus, led=led, audio=audio)
        alarm_svc.init()
        log("✓ AlarmService 就绪")
    except Exception as e:
        log("✗ AlarmService 失败: %s" % e)
        return

    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接")
        return
    log("✓ BLE 已连接")

    log("")
    log("请在小程序「开始骑行」→「直接出发」")
    countdown(10, "等待操作")

    # === 测试 1: 碰撞报警 Lv2 ===
    log("")
    log("=" * 40)
    log(" 测试 1: 碰撞报警 Lv2")
    log("=" * 40)
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
    ble_svc.tick()
    bus.pump()
    pump_for(bus, ble_svc, 100)
    log("  [ ] 小程序: 红色报警弹窗（碰撞）")
    log("  [ ] 板子: LED 快闪 + 报警音")
    pump_for(bus, ble_svc, 5000)

    log("▶ 取消报警...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    ble_svc.tick()
    bus.pump()
    pump_for(bus, ble_svc, 100)
    log("  [ ] 小程序: 弹窗消失")
    pump_for(bus, ble_svc, 3000)

    # === 测试 2: SOS 报警 Lv3 ===
    log("")
    log("=" * 40)
    log(" 测试 2: SOS 报警 Lv3")
    log("=" * 40)
    bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos", "level": 3})
    ble_svc.tick()
    bus.pump()
    pump_for(bus, ble_svc, 100)
    log("  [ ] 小程序: 红色报警弹窗（SOS）")
    log("  [ ] 板子: LED 快闪 + SOS 音")
    pump_for(bus, ble_svc, 5000)

    log("▶ 取消报警...")
    bus.publish(EVENT_ALARM_CANCELED, {})
    ble_svc.tick()
    bus.pump()
    pump_for(bus, ble_svc, 100)
    log("  [ ] 小程序: 弹窗消失")
    pump_for(bus, ble_svc, 3000)

    # === 测试 3: 快速报警循环 ===
    log("")
    log("=" * 40)
    log(" 测试 3: 快速报警循环 (3 次)")
    log("=" * 40)
    for i in range(3):
        log("  [%d/3] 碰撞报警" % (i + 1))
        bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision", "level": 2})
        ble_svc.tick()
        bus.pump()
        pump_for(bus, ble_svc, 2000)
        log("  [%d/3] 取消" % (i + 1))
        bus.publish(EVENT_ALARM_CANCELED, {})
        ble_svc.tick()
        bus.pump()
        pump_for(bus, ble_svc, 2000)

    log("  [ ] 小程序: 3 次报警弹窗正常")
    log("  [ ] 小程序: 3 次取消正常")

    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
