"""
brief BLE 数据解析验证测试
note 验证 BLE 数据编解码链路：
     1. 板子 json.dumps → BLE notify → 小程序 _ab2str → JSON.parse
     2. 小程序 JSON.stringify → _str2ab → BLE write → 板子 json.loads
     3. 中文路名编解码正确
执行: 上传到板子运行，小程序端观察
"""
import sys
sys.path.append("../../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import EVENT_NAV_CMD
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService
from Drivers.actuator.Audio import AudioDriver


_LOG_PATH = "Tests/miniprogram/step_b/02_data_parsing/test_ble_parse.log"
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
    print(" BLE 数据解析验证测试")
    print("=" * 50)

    bus = EventBus()

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

    # 初始化 NavigationService
    log("初始化 NavigationService...")
    try:
        audio = AudioDriver(bus)
        audio.init()
        nav_svc = NavigationService(bus, audio_driver=audio, lcd_driver=None)
        nav_svc.init()
        log("✓ NavigationService 就绪")
    except Exception as e:
        log("✗ NavigationService 失败: %s" % e)
        return

    # 监听 nav 命令
    nav_received = []
    def on_nav(data):
        raw = data.get("raw", "")
        log("  [nav] raw=%s" % str(raw)[:80])
        try:
            cmd = json.loads(raw)
            d = cmd.get("d", {})
            log("  [nav] 解析成功: dir=%s dist=%s road=%s" % (
                d.get("dir"), d.get("dist"), d.get("road")))
            nav_received.append(cmd)
        except Exception as e:
            log("  [nav] 解析失败: %s" % e)
    bus.subscribe(EVENT_NAV_CMD, on_nav)

    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接")
        return
    log("✓ BLE 已连接")

    # === 测试 1: 板子发送纯 ASCII JSON ===
    log("")
    log("=" * 40)
    log(" 测试 1: 板子→小程序 纯 ASCII JSON")
    log("=" * 40)
    log("  请在小程序观察: 数据卡片正常更新")
    from core.config import EVENT_TEMP_HUMID_READY
    bus.publish(EVENT_TEMP_HUMID_READY, {"temp": 25.5, "humid": 60.0, "valid": True})
    ble_svc.tick()
    bus.pump()
    pump_for(bus, ble_svc, 1000)
    log("  [ ] 小程序: 温度显示 25.5°C")
    log("  [ ] 小程序: 湿度显示 60%")
    pump_for(bus, ble_svc, 5000)

    # === 测试 2: 小程序发送 nav 命令（板子接收）===
    log("")
    log("=" * 40)
    log(" 测试 2: 小程序→板子 nav 命令")
    log("=" * 40)
    log("  请在小程序「开始骑行」→「设置目的地」→「开始导航」")
    log("  观察: 板子是否能解析 nav 命令")

    end = time.ticks_ms() + 30000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)

    log("")
    log("  收到 %d 条 nav 命令" % len(nav_received))
    if nav_received:
        log("  ✓ nav 命令解析成功")
        for i, cmd in enumerate(nav_received[:3]):
            d = cmd.get("d", {})
            log("    [%d] dir=%s dist=%s road=%s" % (
                i + 1, d.get("dir"), d.get("dist"), d.get("road")))
    else:
        log("  ✗ 未收到 nav 命令或解析失败")

    # === 总结 ===
    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)
    log("  [ ] 板子→小程序: JSON 解析正确")
    log("  [ ] 小程序→板子: nav 命令解析正确")
    log("  [ ] 中文路名: 编解码正确")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
